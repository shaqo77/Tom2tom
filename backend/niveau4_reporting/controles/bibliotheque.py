"""La bibliothèque de contrôles livrée : huit familles et trois contrôles de risque. Voir L6-T01.

Les contrôles sont des DONNÉES (`catalogue/bibliotheque.json`) : une condition structurée du langage
fermé de `conditions.py`, un libellé et une action corrective en français ET en anglais. Ajouter ou
corriger un contrôle livré est une modification de ce fichier, validée au chargement (langage,
schéma, langues, codes), jamais du code. La LOGIQUE reste ici : comment une fabrique construit
la condition d'une règle de pièce ou d'éligibilité à partir de ce que le projet a configuré.

Ils s'installent EN BROUILLON dans un projet (`services.installer_bibliotheque`) : le système
n'active jamais un contrôle de lui-même (règle 9) et un contrôle actif doit avoir son exigence
source (L5-T03).

Un contrôle dont la condition compare deux grandeurs (une dépense à un plafond) s'écrit sur le
RESTE : le contexte (`contextes.py`) fournit le disponible, le contrôle exige qu'il reste positif
ou nul. Un plafond absent ne déclenche rien : la condition d'applicabilité (`est_renseigne`) rend le
contrôle non applicable, noté au journal seulement.

Trois familles se paramètrent par une fabrique plutôt que par une valeur livrée : les règles de
pièces (aucune liste universelle de justificatifs), l'éligibilité (nature, zone, date,
bénéficiaire : ce que le projet a configuré) et les seuils de risque.
"""

import datetime
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from core.i18n import LANGUES, champs_du_gabarit, normaliser_textes

from . import conditions

FAMILLES = (
    "codification",
    "budget",
    "pieces",
    "tresorerie",
    "avances",
    "rapport",
    "coherence",
    "eligibilite",
    "risque",
)
SEVERITES = ("bloquant", "avertissement", "information")
FICHIER = Path(__file__).resolve().parent / "catalogue" / "bibliotheque.json"
TAILLE_MAX = 1_000_000
CODE = re.compile(r"^[A-Z][A-Z0-9-]{2,63}$")


class BibliothequeInvalide(ValueError):
    """Le catalogue de contrôles est incohérent : on refuse de démarrer avec lui."""


@dataclass(frozen=True)
class DefinitionControle:
    code: str
    famille: str
    label: dict
    type_regle: str
    severity: str
    expression: dict
    action_corrective: dict
    applicable_si: dict | None = None
    parametres: dict = field(default_factory=dict)


def _textes(valeur, ou: str, *, gabarit: bool = False) -> dict:
    """Un texte multilingue COMPLET (toutes les langues gérées), ou on refuse le catalogue."""
    try:
        textes = normaliser_textes(valeur, obligatoire=True)
    except ValueError as erreur:
        raise BibliothequeInvalide(f"{ou} : {erreur}") from erreur
    manquantes = [langue for langue in LANGUES if langue not in textes]
    if manquantes:
        raise BibliothequeInvalide(f"{ou} : langue(s) manquante(s) {manquantes}")
    if gabarit:
        for texte in textes.values():
            champs_du_gabarit(texte)
    return textes


def _definition_de(brut: dict, ou: str) -> DefinitionControle:
    inconnues = set(brut) - {
        "code", "famille", "severity", "type_regle", "label", "action_corrective",
        "expression", "applicable_si", "parametres",
    }  # fmt: skip
    if inconnues:
        raise BibliothequeInvalide(f"{ou} : clés inconnues {sorted(inconnues)}")
    code = brut.get("code", "")
    if not CODE.match(code):
        raise BibliothequeInvalide(f"{ou} : code « {code} » invalide")
    if brut.get("famille") not in FAMILLES:
        raise BibliothequeInvalide(f"{ou} : famille « {brut.get('famille')} » inconnue")
    if brut.get("severity") not in SEVERITES:
        raise BibliothequeInvalide(f"{ou} : sévérité « {brut.get('severity')} » inconnue")
    try:
        conditions.preparer_expression(brut.get("expression"), brut.get("type_regle"))
        if brut.get("applicable_si") is not None:
            conditions.preparer_expression(brut["applicable_si"], brut.get("type_regle"))
    except conditions.ConditionInvalide as erreur:
        raise BibliothequeInvalide(f"{code} : {erreur}") from erreur
    return DefinitionControle(
        code=code,
        famille=brut["famille"],
        label=_textes(brut.get("label"), f"{code} (libellé)"),
        type_regle=brut["type_regle"],
        severity=brut["severity"],
        expression=brut["expression"],
        action_corrective=_textes(brut.get("action_corrective"), f"{code} (action corrective)"),
        applicable_si=brut.get("applicable_si"),
        parametres=brut.get("parametres") or {},
    )


def valider_catalogue(brut: dict) -> tuple[tuple[DefinitionControle, ...], dict]:
    """`(contrôles livrés, modèles de fabriques)` ou lève `BibliothequeInvalide`."""
    if not isinstance(brut, dict) or set(brut) != {"version", "controles", "modeles"}:
        raise BibliothequeInvalide("le catalogue a une version, des contrôles et des modèles")
    definitions = tuple(_definition_de(c, f"contrôle {i}") for i, c in enumerate(brut["controles"]))
    codes = [d.code for d in definitions]
    if len(codes) != len(set(codes)):
        raise BibliothequeInvalide("deux contrôles ont le même code")
    modeles = {}
    for nom, modele in brut["modeles"].items():
        ou = f"modèle {nom}"
        if modele.get("famille") not in FAMILLES or modele.get("severity") not in SEVERITES:
            raise BibliothequeInvalide(f"{ou} : famille ou sévérité inconnue")
        modeles[nom] = {
            **modele,
            "label": _textes(modele.get("label"), f"{ou} (libellé)", gabarit=True),
            "action_corrective": _textes(
                modele.get("action_corrective"), f"{ou} (action corrective)", gabarit=True
            ),
        }
    return definitions, modeles


@lru_cache(maxsize=1)
def _catalogue():
    if FICHIER.stat().st_size > TAILLE_MAX:
        raise BibliothequeInvalide(f"{FICHIER.name} dépasse {TAILLE_MAX} octets")
    return valider_catalogue(json.loads(FICHIER.read_text(encoding="utf-8")))


LIVRES: tuple[DefinitionControle, ...] = _catalogue()[0]
PAR_CODE = {d.code: d for d in LIVRES}


# --- les fabriques : ce que le projet a configuré -------------------------------------------


def _expr(type_regle: str, *conds) -> dict:
    return {"type_regle": type_regle, "conditions": list(conds)}


def _c(champ: str, op: str, valeur=None) -> dict:
    return {"champ": champ, "op": op} | ({} if valeur is None else {"valeur": valeur})


def _depuis_modele(nom, code, expression, applicable_si=None, parametres=None, **params):
    modele = _catalogue()[1][nom]
    return DefinitionControle(
        code=code,
        famille=modele["famille"],
        label={langue: t.format_map(params) for langue, t in modele["label"].items()},
        type_regle=expression["type_regle"],
        severity=modele["severity"],
        expression=expression,
        action_corrective={
            langue: t.format_map(params) for langue, t in modele["action_corrective"].items()
        },
        applicable_si=applicable_si,
        parametres=parametres or {},
    )


def regle_de_piece(
    code: str,
    type_piece: str,
    *,
    validee: bool = False,
    categories: list[str] | None = None,
    methodes: list[str] | None = None,
    seuil_montant: str | None = None,
    natures: list[str] | None = None,
) -> DefinitionControle:
    """Une pièce requise : type exigé, et portée (catégorie, méthode, seuil, nature de dépense).

    La pièce doit être du bon type ET rattachée à l'opération (et validée si `validee`), sinon elle
    compte comme absente. Les portées se cumulent (toutes doivent être vraies pour que la règle
    s'applique) ; sans portée, la règle vaut pour toute dépense.
    """
    portee = []
    if categories:
        portee.append(_c("categorie", "in", list(categories)))
    if methodes:
        portee.append(_c("methode", "in", list(methodes)))
    if seuil_montant is not None:
        portee.append(_c("montant", "gte", seuil_montant))
    if natures:
        portee.append(_c("nature", "in", list(natures)))
    return _depuis_modele(
        "regle_de_piece",
        code,
        _expr("pieces", _c("pieces", "est_renseigne")),
        _expr("pieces", *portee) if portee else None,
        {"type_piece": type_piece, "validee": validee},
        type_piece=type_piece,
    )


def eligibilite_nature(code: str, natures: list[str]) -> DefinitionControle:
    return _depuis_modele(
        "eligibilite_nature", code, _expr("eligibilite", _c("nature", "in", list(natures)))
    )


def eligibilite_zone(code: str, zones: list[str]) -> DefinitionControle:
    return _depuis_modele(
        "eligibilite_zone", code, _expr("eligibilite", _c("zone", "in", list(zones)))
    )


def eligibilite_periode(code: str, du: datetime.date, au: datetime.date) -> DefinitionControle:
    """Dépense datée dans `[du, au[` : la fin est exclue."""
    return _depuis_modele(
        "eligibilite_periode",
        code,
        _expr("eligibilite", _c("date", "entre", [du.isoformat(), au.isoformat()])),
    )


def eligibilite_beneficiaires_exclus(code: str, exclus: list[str]) -> DefinitionControle:
    return _depuis_modele(
        "eligibilite_beneficiaires_exclus",
        code,
        _expr("eligibilite", _c("beneficiaire", "not_in", list(exclus))),
        _expr("eligibilite", _c("beneficiaire", "est_renseigne")),
    )


def _risque(nom: str, champ: str, seuil, **params) -> DefinitionControle:
    code = _catalogue()[1][nom]["code"]
    return _depuis_modele(
        nom,
        code,
        _expr("risque", _c(champ, "lte", seuil)),
        _expr("risque", _c(champ, "est_renseigne")),
        **params,
    )


def risque_categorie_consommee(seuil_pct: str | None = None) -> DefinitionControle:
    """Catégorie consommée au-delà d'un seuil paramétré (en %) : un avertissement."""
    seuil = (
        seuil_pct
        if seuil_pct is not None
        else _catalogue()[1]["risque_categorie_consommee"]["defaut"]["seuil_pct"]
    )
    return _risque(
        "risque_categorie_consommee", "taux_consommation_categorie", seuil, seuil_pct=seuil
    )


def risque_avance_non_apuree(delai_jours: int | None = None) -> DefinitionControle:
    """Avance non apurée depuis plus d'un délai paramétré : une information."""
    delai = (
        delai_jours
        if delai_jours is not None
        else _catalogue()[1]["risque_avance_non_apuree"]["defaut"]["delai_jours"]
    )
    return _risque("risque_avance_non_apuree", "jours_avance_non_apuree", delai, delai_jours=delai)


def risque_rejets_repetes(maximum: int | None = None) -> DefinitionControle:
    """Rejets répétés sur une même catégorie : une information."""
    seuil = (
        maximum
        if maximum is not None
        else _catalogue()[1]["risque_rejets_repetes"]["defaut"]["maximum"]
    )
    return _risque("risque_rejets_repetes", "rejets_categorie", seuil, maximum=seuil)


def livres_avec_risque() -> tuple[DefinitionControle, ...]:
    """Les contrôles livrés, trois contrôles de risque aux seuils par défaut compris."""
    return (
        *LIVRES,
        risque_categorie_consommee(),
        risque_avance_non_apuree(),
        risque_rejets_repetes(),
    )
