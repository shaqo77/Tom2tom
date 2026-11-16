"""Import d'un relevé bancaire au format MT940 ou CAMT.053. Voir L9-T05 (complément).

Le fichier donne le solde d'OUVERTURE, les mouvements et le solde de CLÔTURE. L'import vérifie que
ouverture + mouvements = clôture (sinon le relevé est incohérent et RIEN n'est écrit), que le
compte et la devise sont ceux du compte bancaire, puis enregistre les mouvements (rejouables : une
référence déjà importée est ignorée, refusée si ses valeurs changent) et les deux soldes de relevé.

Sécurité : le numéro de compte du fichier sert à reconnaître le compte et n'apparaît dans aucun
message ; un fichier CAMT contenant une DTD ou une entité est refusé (aucune expansion d'entités).
Un compte en devise étrangère demande un `taux` explicite (aucun taux n'est lu dans le fichier).
"""

import datetime
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction

from core.audit import journaliser
from core.metier import decimal as nombre_decimal
from core.metier import habilite, refuser
from niveau1_socle.financements.models import CompteBancaire
from niveau1_socle.rapprochement.services import _contexte, importer_mouvements

from .services import poser_solde_releve

TAILLE_MAX = 10 * 1024 * 1024  # 10 Mio : un relevé mensuel pèse quelques centaines de Kio
ZERO = Decimal("0")


@dataclass
class MouvementLu:
    reference: str
    date: datetime.date
    montant: Decimal  # signé : positif = encaissement
    libelle: str = ""


@dataclass
class Releve:
    reference: str
    compte: str  # tel que la banque l'écrit (jamais affiché)
    devise: str
    date_ouverture: datetime.date
    solde_ouverture: Decimal
    date_cloture: datetime.date
    solde_cloture: Decimal
    mouvements: list[MouvementLu] = field(default_factory=list)


# --- MT940 -------------------------------------------------------------------------------------

_SOLDE = re.compile(r"^([CD])(\d{6})([A-Z]{3})(\d+(?:,\d*)?)$")
_MOUVEMENT = re.compile(
    r"^(\d{6})(\d{4})?(RC|RD|C|D)[A-Z]?(\d+(?:,\d*)?)N[A-Z0-9]{3}(.*)$", re.DOTALL
)


def _date_yymmdd(texte: str) -> datetime.date:
    annee = int(texte[:2])
    try:
        return datetime.date(
            2000 + annee if annee < 70 else 1900 + annee, int(texte[2:4]), int(texte[4:6])
        )
    except ValueError:
        refuser("releve.date_invalide", valeur=texte)


def _montant_mt940(texte: str) -> Decimal:
    try:
        return Decimal(texte.replace(",", ".") if "," in texte else texte)
    except InvalidOperation:
        refuser("releve.montant_invalide", valeur=texte)


def _solde_mt940(valeur: str):
    m = _SOLDE.match(valeur.strip())
    if m is None:
        refuser("releve.solde_illisible", valeur=valeur.strip()[:40])
    signe = 1 if m.group(1) == "C" else -1
    return _date_yymmdd(m.group(2)), signe * _montant_mt940(m.group(4)), m.group(3)


def lire_mt940(contenu: str) -> list[Releve]:
    """Lit un ou plusieurs relevés MT940 (enveloppe SWIFT `{4:` … `-}` tolérée)."""
    champs: list[tuple[str, str]] = []
    for ligne in contenu.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if re.match(r"^:[0-9]{2}[A-Z]?:", ligne):
            etiquette, _, reste = ligne[1:].partition(":")
            champs.append((etiquette, reste))
        elif ligne.startswith(("-}", "}")) or ligne.strip() in ("-", ""):
            continue
        elif champs:  # ligne de continuation (surtout du :86:)
            etiquette, reste = champs[-1]
            champs[-1] = (etiquette, f"{reste}\n{ligne}")
    releves: list[Releve] = []
    courant: dict | None = None
    for etiquette, valeur in champs:
        if etiquette == "20":
            courant = {"reference": valeur.strip(), "mouvements": [], "compte": "", "devise": ""}
            releves.append(courant)  # type: ignore[arg-type]
        elif courant is None:
            continue
        elif etiquette == "25":
            courant["compte"] = valeur.strip()
        elif etiquette in ("60F", "60M"):
            courant["date_ouverture"], courant["solde_ouverture"], courant["devise"] = _solde_mt940(
                valeur
            )
        elif etiquette in ("62F", "62M"):
            courant["date_cloture"], courant["solde_cloture"], devise = _solde_mt940(valeur)
            if devise != courant["devise"]:
                refuser("releve.devises_differentes")
        elif etiquette == "61":
            m = _MOUVEMENT.match(valeur.split("\n", 1)[0].strip())
            if m is None:
                refuser("releve.mouvement_illisible", valeur=valeur[:40])
            montant = _montant_mt940(m.group(4))
            sens = {"C": 1, "D": -1, "RC": -1, "RD": 1}[
                m.group(3)
            ]  # une annulation inverse le sens
            _, _, reference_banque = m.group(5).partition("//")
            courant["mouvements"].append(
                {
                    "date": _date_yymmdd(m.group(1)),
                    "montant": sens * montant,
                    "banque": reference_banque.strip(),
                }
            )
        elif etiquette == "86" and courant["mouvements"]:
            courant["mouvements"][-1]["libelle"] = " ".join(valeur.split())[:255]
    resultat = []
    for r in releves:
        manquants = [
            c for c in ("compte", "date_ouverture", "date_cloture", "devise") if not r.get(c)
        ]
        if manquants:
            refuser("releve.champ_manquant", champ=manquants[0])
        resultat.append(
            Releve(
                reference=r["reference"],
                compte=r["compte"],
                devise=r["devise"],
                date_ouverture=r["date_ouverture"],
                solde_ouverture=r["solde_ouverture"],
                date_cloture=r["date_cloture"],
                solde_cloture=r["solde_cloture"],
                mouvements=_references(r["reference"], r["mouvements"]),
            )
        )
    if not resultat:
        refuser("releve.aucun_releve")
    return resultat


def _references(reference_releve: str, bruts: list[dict]) -> list[MouvementLu]:
    """Une référence STABLE par mouvement : celle de la banque si elle existe et est unique dans le
    relevé, sinon `<référence du relevé>:<rang>` : rejouer le même fichier redonne les mêmes."""
    vus: dict[str, int] = {}
    for b in bruts:
        if b["banque"] and b["banque"] != "NONREF":
            vus[b["banque"]] = vus.get(b["banque"], 0) + 1
    mouvements = []
    for rang, b in enumerate(bruts, start=1):
        banque = b["banque"]
        reference = (
            banque
            if banque and banque != "NONREF" and vus[banque] == 1
            else f"{reference_releve}:{rang:04d}"
        )
        mouvements.append(MouvementLu(reference, b["date"], b["montant"], b.get("libelle", "")))
    return mouvements


# --- CAMT.053 ----------------------------------------------------------------------------------


def _local(balise: str) -> str:
    return balise.rsplit("}", 1)[-1]


def _enfant(noeud, *chemin):
    for nom in chemin:
        noeud = next((e for e in noeud if _local(e.tag) == nom), None)
        if noeud is None:
            return None
    return noeud


def _texte(noeud, *chemin) -> str:
    e = _enfant(noeud, *chemin)
    return (e.text or "").strip() if e is not None else ""


def _date_iso(texte: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(texte[:10])
    except ValueError:
        refuser("releve.date_invalide", valeur=texte[:20])


def lire_camt053(contenu: bytes) -> list[Releve]:
    """Lit un relevé CAMT.053 (une ou plusieurs `Stmt`). Refuse toute DTD ou entité."""
    entete = contenu[:4096].upper()
    if b"<!DOCTYPE" in entete or b"<!ENTITY" in contenu.upper():
        refuser("releve.xml_dangereux")
    try:
        racine = ET.fromstring(contenu)
    except ET.ParseError:
        refuser("releve.xml_illisible")
    releves = []
    for stmt in (e for e in racine.iter() if _local(e.tag) == "Stmt"):
        soldes = {}
        for bal in (e for e in stmt if _local(e.tag) == "Bal"):
            code = _texte(bal, "Tp", "CdOrPrtry", "Cd")
            montant = _enfant(bal, "Amt")
            if code in ("OPBD", "CLBD") and montant is not None:
                valeur = nombre_decimal(montant.text, "solde", signe="positif_ou_nul")
                signe = -1 if _texte(bal, "CdtDbtInd") == "DBIT" else 1
                soldes[code] = (
                    _date_iso(_texte(bal, "Dt", "Dt")),
                    signe * valeur,
                    montant.get("Ccy", ""),
                )
        if "OPBD" not in soldes or "CLBD" not in soldes:
            refuser("releve.champ_manquant", champ="solde")
        reference = _texte(stmt, "Id")
        bruts = []
        for entree in (e for e in stmt if _local(e.tag) == "Ntry"):
            valeur = nombre_decimal(_texte(entree, "Amt"), "montant", signe="positif")
            sens = -1 if _texte(entree, "CdtDbtInd") == "DBIT" else 1
            if _texte(entree, "RvslInd").lower() == "true":
                sens = -sens
            bruts.append(
                {
                    "date": _date_iso(
                        _texte(entree, "BookgDt", "Dt") or _texte(entree, "BookgDt", "DtTm")
                    ),
                    "montant": sens * valeur,
                    "banque": _texte(entree, "AcctSvcrRef") or _texte(entree, "NtryRef"),
                    "libelle": " ".join(_texte(entree, "AddtlNtryInf").split())[:255],
                }
            )
        releves.append(
            Releve(
                reference=reference,
                compte=_texte(stmt, "Acct", "Id", "IBAN")
                or _texte(stmt, "Acct", "Id", "Othr", "Id"),
                devise=soldes["OPBD"][2],
                date_ouverture=soldes["OPBD"][0],
                solde_ouverture=soldes["OPBD"][1],
                date_cloture=soldes["CLBD"][0],
                solde_cloture=soldes["CLBD"][1],
                mouvements=_references(reference, bruts),
            )
        )
    if not releves:
        refuser("releve.aucun_releve")
    return releves


# --- l'import ----------------------------------------------------------------------------------


def lire_releves(contenu: bytes | str, format: str | None = None) -> list[Releve]:
    """Lit le fichier ; le format (`mt940` ou `camt053`) se devine au contenu, s'il manque."""
    octets = contenu.encode("utf-8") if isinstance(contenu, str) else bytes(contenu)
    if not octets or len(octets) > TAILLE_MAX:
        refuser("releve.fichier_invalide")
    if format is None:
        format = "camt053" if octets.lstrip()[:1] == b"<" else "mt940"
    if format == "camt053":
        return lire_camt053(octets)
    if format == "mt940":
        try:
            texte = octets.decode("utf-8")
        except UnicodeDecodeError:
            texte = octets.decode("latin-1")
        return lire_mt940(texte)
    refuser("releve.format_inconnu", format=str(format)[:20])


def _normaliser(numero: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", numero.upper())


def importer_releve(
    *,
    utilisateur,
    compte: CompteBancaire,
    contenu: bytes | str,
    format: str | None = None,
    taux=None,
) -> dict:
    """Importe un relevé MT940 ou CAMT.053 sur le compte, en TOUT OU RIEN.

    Retourne `{"mouvements_importes", "mouvements_ignores", "soldes_poses"}` cumulés sur les relevés
    du fichier. Habilitation « comptabiliser » (comme l'import de mouvements).
    """
    habilite(utilisateur, "comptabiliser", compte.project_id)
    releves = lire_releves(contenu, format)
    _, _, etrangere = _contexte(compte)
    if etrangere:
        taux = (
            nombre_decimal(taux, "taux")
            if taux is not None
            else refuser("releve.taux_obligatoire", devise=compte.devise_id)
        )
    importes = ignores = soldes = 0
    with transaction.atomic():
        for releve in releves:
            if _normaliser(releve.compte) != _normaliser(compte.numero):
                refuser("releve.autre_compte", compte=compte.code)
            if releve.devise != compte.devise_id:
                refuser("releve.autre_devise", releve=releve.devise, compte=compte.devise_id)
            total = sum((m.montant for m in releve.mouvements), ZERO)
            if releve.solde_ouverture + total != releve.solde_cloture:
                refuser(
                    "releve.incoherent",
                    reference=releve.reference,
                    ouverture=releve.solde_ouverture,
                    mouvements=total,
                    cloture=releve.solde_cloture,
                )
            nouveaux, deja = importer_mouvements(
                utilisateur=utilisateur,
                compte=compte,
                mouvements=[
                    {
                        "reference": m.reference,
                        "date": m.date,
                        "montant": m.montant,
                        "libelle": m.libelle,
                    }
                    | ({"taux": taux} if etrangere else {})
                    for m in releve.mouvements
                ],
            )
            importes += len(nouveaux)
            ignores += deja
            for jour, solde in (
                (releve.date_ouverture, releve.solde_ouverture),
                (releve.date_cloture, releve.solde_cloture),
            ):
                soldes += poser_solde_releve(compte, jour, solde, releve.reference, utilisateur)
        journaliser(
            org_id=compte.org_id,
            actor_id=utilisateur.id,
            action="bank_statement_imported",
            object_type="compte_bancaire",
            object_id=compte.id,
            project_id=compte.project_id,
            after={
                "releves": len(releves),
                "importes": importes,
                "ignores": ignores,
                "soldes": soldes,
            },
        )
    return {"mouvements_importes": importes, "mouvements_ignores": ignores, "soldes_poses": soldes}
