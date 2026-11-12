"""Import du plan comptable depuis un fichier Excel ou CSV. Voir L2-T07.

Trois temps : proposition de correspondance des colonnes, validation humaine
(`CorrespondanceImport`), import rejouable. Règles :
- rejouer ne crée jamais de doublon (clé : le code du compte) ;
- un compte déjà présent et différent est un CONFLIT, jamais un écrasement ;
- une ligne invalide arrête tout l'import : rien n'est écrit (tout ou rien) ;
- la hiérarchie se déduit des codes (préfixe le plus long présent dans le fichier
  ou le plan), et seul un compte feuille est imputable.
"""

import csv
import hashlib
import io
import re
import unicodedata
import uuid
from dataclasses import dataclass, field

import openpyxl
from django.db import transaction

from core.audit import journaliser

from .models import Compte, StatutCorrespondance

OBLIGATOIRES = ("code", "label:fr", "sens_normal")
SYNONYMES = {
    "code": {
        "code",
        "compte",
        "ncompte",
        "numerocompte",
        "numcompte",
        "numero",
        "codecompte",
        "account",
        "accountnumber",
        "accountcode",
    },
    "label:fr": {
        "libelle",
        "intitule",
        "designation",
        "nom",
        "libellefr",
        "intitulefr",
        "labelfr",
        "label",
    },
    "label:en": {"libelleen", "intituleen", "labelen", "name", "accountname"},
    "sens_normal": {"sens", "sensnormal", "sensducompte", "dc", "debitcredit"},
    "imputable": {"imputable", "imputation", "postable"},
    "actif": {"actif", "active"},
    "parent": {"parent", "compteparent", "codeparent", "rattachement"},
}
SENS = {
    "d": "debit",
    "debit": "debit",
    "dr": "debit",
    "c": "credit",
    "credit": "credit",
    "cr": "credit",
}
VRAI = {"oui", "o", "yes", "y", "1", "true", "vrai", "x"}
FAUX = {"non", "n", "no", "0", "false", "faux"}
CODE = re.compile(r"^[1-9][0-9]*$")


class CorrespondanceNonValidee(PermissionError):
    """Seule une correspondance validée par un humain permet d'importer."""


class ImportRejete(ValueError):
    """Des lignes sont invalides : rien n'a été écrit. `rejets` les nomme."""

    def __init__(self, rejets: list["Rejet"]):
        self.rejets = rejets
        super().__init__(
            "Import rejeté : " + " ; ".join(f"ligne {r.ligne} ({r.raison})" for r in rejets[:10])
        )


@dataclass(frozen=True)
class Rejet:
    ligne: int
    raison: str


@dataclass(frozen=True)
class Conflit:
    code: str
    differences: dict  # champ -> (valeur en base, valeur du fichier)


@dataclass
class RapportImport:
    crees: int = 0
    inchanges: int = 0
    conflits: list[Conflit] = field(default_factory=list)
    rejets: list[Rejet] = field(default_factory=list)


@dataclass(frozen=True)
class Proposition:
    colonnes: dict
    non_reconnues: list
    manquantes: list


# --- lecture ------------------------------------------------------------------------------


def _texte(valeur) -> str:
    if valeur is None:
        return ""
    if isinstance(valeur, float) and valeur.is_integer():
        valeur = int(valeur)  # Excel enregistre 601 comme 601.0
    return str(valeur).strip()


def lire_fichier(contenu: bytes, nom: str) -> tuple[list[str], list[dict]]:
    """Lit un classeur .xlsx ou un CSV. Retourne les en-têtes et une rangée par ligne.

    La ligne 1 porte les en-têtes ; la rangée n°i est donc la ligne i + 2 du fichier.
    """
    if contenu[:4] == b"PK\x03\x04":
        classeur = openpyxl.load_workbook(io.BytesIO(contenu), read_only=True, data_only=True)
        lignes = [
            [_texte(c) for c in ligne] for ligne in classeur.active.iter_rows(values_only=True)
        ]
    else:
        try:
            texte = contenu.decode("utf-8-sig")
        except UnicodeDecodeError:
            texte = contenu.decode("cp1252")
        try:
            dialecte = csv.Sniffer().sniff(texte[:4096], delimiters=",;\t|")
        except csv.Error:
            dialecte = csv.excel
        lignes = [[_texte(c) for c in ligne] for ligne in csv.reader(io.StringIO(texte), dialecte)]
    while lignes and not any(lignes[-1]):
        lignes.pop()
    if not lignes:
        return [], []
    entetes, corps = lignes[0], lignes[1:]
    return entetes, [
        dict(zip(entetes, ligne + [""] * len(entetes), strict=False)) for ligne in corps
    ]


# --- proposition de correspondance --------------------------------------------------------


def _normaliser(entete: str) -> str:
    sans_accent = unicodedata.normalize("NFKD", entete).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sans_accent.lower())


def proposer_correspondance(entetes: list[str]) -> Proposition:
    """Propose, pour chaque champ, la colonne dont l'en-tête lui ressemble. Un humain valide."""
    colonnes: dict[str, str] = {}
    utilisees: set[str] = set()
    for champ, synonymes in SYNONYMES.items():
        for entete in entetes:
            if entete not in utilisees and _normaliser(entete) in synonymes:
                colonnes[champ] = entete
                utilisees.add(entete)
                break
    return Proposition(
        colonnes=colonnes,
        non_reconnues=[e for e in entetes if e not in utilisees],
        manquantes=[c for c in OBLIGATOIRES if c not in colonnes],
    )


# --- analyse et import --------------------------------------------------------------------


def _valeur(rangee: dict, correspondance, champ: str):
    colonne = correspondance.colonnes.get(champ)
    valeur = _texte(rangee.get(colonne)) if colonne else ""
    return valeur or _texte(correspondance.valeurs_defaut.get(champ))


def _libelle(rangee: dict, correspondance) -> dict:
    """Libellé multilingue : une colonne « label:<langue> » du fichier par langue.

    En base, un seul JSONB : jamais une colonne par langue.
    """
    champs = set(correspondance.colonnes) | set(correspondance.valeurs_defaut)
    libelle = {}
    for champ in sorted(c for c in champs if c.startswith("label:")):
        if valeur := _valeur(rangee, correspondance, champ):
            libelle[champ.removeprefix("label:")] = valeur
    return libelle


def _booleen(valeur: str, defaut: bool):
    if valeur == "":
        return defaut, None
    minuscule = valeur.lower()
    if minuscule in VRAI:
        return True, None
    if minuscule in FAUX:
        return False, None
    return defaut, f"valeur booléenne inconnue : {valeur!r}"


def _candidats(rangees, correspondance, rapport):
    """Valide chaque rangée. Retourne {code: (ligne, champs)} des rangées valides."""
    candidats: dict[str, tuple[int, dict]] = {}
    for indice, rangee in enumerate(rangees):
        ligne = indice + 2
        code = _valeur(rangee, correspondance, "code")
        raison = None
        if not CODE.match(code):
            raison = f"code invalide : {code!r}"
        elif code in candidats:
            raison = (
                f"code {code} en double dans le fichier (première fois ligne {candidats[code][0]})"
            )
        libelle = _libelle(rangee, correspondance)
        if raison is None and "fr" not in libelle:
            raison = "libellé français absent"
        sens = SENS.get(_valeur(rangee, correspondance, "sens_normal").lower())
        if raison is None and sens is None:
            raison = f"sens inconnu : {_valeur(rangee, correspondance, 'sens_normal')!r}"
        actif, erreur_actif = _booleen(_valeur(rangee, correspondance, "actif"), True)
        imputable_dit, erreur_imp = _booleen(_valeur(rangee, correspondance, "imputable"), None)
        raison = raison or erreur_actif or erreur_imp
        if raison:
            rapport.rejets.append(Rejet(ligne, raison))
            continue
        candidats[code] = (
            ligne,
            {
                "label": libelle,
                "sens_normal": sens,
                "actif": actif,
                "imputable_dit": imputable_dit,
                "parent_dit": _valeur(rangee, correspondance, "parent") or None,
            },
        )
    return candidats


def _analyser(contenu: bytes, nom: str, correspondance):
    """Analyse sans rien écrire. Retourne (rapport, comptes à créer dans l'ordre des niveaux)."""
    _, rangees = lire_fichier(contenu, nom)
    rapport = RapportImport()
    candidats = _candidats(rangees, correspondance, rapport)
    existants = {c.code: c for c in Compte.objects.select_related("parent")}
    codes = set(candidats) | set(existants)

    def parent_de(code, champs):
        if champs["parent_dit"]:
            return champs["parent_dit"]
        proches = [code[:n] for n in range(len(code) - 1, 0, -1) if code[:n] in codes]
        return proches[0] if proches else None

    parents = {code: parent_de(code, champs) for code, (_, champs) in candidats.items()}
    avec_enfants = {p for p in parents.values() if p} | {
        c.parent.code for c in existants.values() if c.parent
    }

    a_creer: dict[str, dict] = {}
    for code, (ligne, champs) in candidats.items():
        parent = parents[code]
        a_enfants = code in avec_enfants
        if champs["imputable_dit"] is True and a_enfants:
            rapport.rejets.append(
                Rejet(ligne, f"le compte {code} est déclaré imputable mais a des enfants")
            )
            continue
        imputable = (not a_enfants) if champs["imputable_dit"] is None else champs["imputable_dit"]
        if parent and parent not in codes:
            rapport.rejets.append(Rejet(ligne, f"parent {parent} introuvable"))
            continue
        souhaite = {
            "label": champs["label"],
            "sens_normal": champs["sens_normal"],
            "actif": champs["actif"],
            "imputable": imputable,
            "parent": parent,
        }
        if code in existants:
            actuel = existants[code]
            reel = {
                "label": actuel.label,
                "sens_normal": actuel.sens_normal,
                "actif": actuel.actif,
                "imputable": actuel.imputable,
                "parent": actuel.parent.code if actuel.parent else None,
            }
            differences = {k: (reel[k], souhaite[k]) for k in souhaite if reel[k] != souhaite[k]}
            if differences:
                rapport.conflits.append(Conflit(code, differences))
            else:
                rapport.inchanges += 1
            continue
        if parent in existants and existants[parent].imputable:
            rapport.rejets.append(
                Rejet(
                    ligne, f"le parent {parent} existe déjà et est imputable : il n'a pas d'enfant"
                )
            )
            continue
        a_creer[code] = {"ligne": ligne, **souhaite}
    rapport.crees = len(a_creer)
    return rapport, a_creer, existants


def simuler_import(contenu: bytes, nom: str, correspondance) -> RapportImport:
    """Rejoue l'analyse de l'import sans rien écrire."""
    return _analyser(contenu, nom, correspondance)[0]


def importer_plan_comptable(
    contenu: bytes, nom: str, correspondance, *, utilisateur
) -> RapportImport:
    """Importe un plan comptable. Exige une correspondance validée ; tout ou rien."""
    if correspondance.statut != StatutCorrespondance.VALIDEE:
        raise CorrespondanceNonValidee(
            f"La correspondance « {correspondance.nom} » n'a pas été validée par un responsable"
        )
    with transaction.atomic():
        rapport, a_creer, existants = _analyser(contenu, nom, correspondance)
        if rapport.rejets:
            raise ImportRejete(rapport.rejets)

        identifiants = {code: c.id for code, c in existants.items()}
        identifiants.update({code: uuid.uuid4() for code in a_creer})

        def profondeur(code):
            niveau, courant = 0, a_creer[code]["parent"]
            while courant in a_creer:
                niveau, courant = niveau + 1, a_creer[courant]["parent"]
            return niveau

        # Les parents d'abord : le déclencheur de hiérarchie lit le parent à l'insertion.
        niveaux: dict[int, list[Compte]] = {}
        for code, champs in a_creer.items():
            niveaux.setdefault(profondeur(code), []).append(
                Compte(
                    id=identifiants[code],
                    org_id=correspondance.org_id,
                    code=code,
                    label=champs["label"],
                    classe=int(code[0]),
                    sens_normal=champs["sens_normal"],
                    imputable=champs["imputable"],
                    actif=champs["actif"],
                    parent_id=identifiants[champs["parent"]] if champs["parent"] else None,
                    created_by=getattr(utilisateur, "id", None),
                )
            )
        for niveau in sorted(niveaux):
            Compte.objects.bulk_create(niveaux[niveau])

        journaliser(
            org_id=correspondance.org_id,
            actor_id=getattr(utilisateur, "id", None),
            action="referential_imported",
            object_type="correspondance_import",
            object_id=correspondance.id,
            after={
                "fichier": nom,
                "sha256": hashlib.sha256(contenu).hexdigest(),
                "crees": rapport.crees,
                "inchanges": rapport.inchanges,
                "conflits": len(rapport.conflits),
            },
        )
    return rapport
