"""La bibliothèque de contrôles livrée : huit familles et trois contrôles de risque. Voir L6-T01.

Chaque contrôle est une DONNÉE (une condition structurée du langage fermé de `conditions.py`), pas
du code. Ils s'installent EN BROUILLON dans un projet (`services.installer_bibliotheque`) : le
système n'active jamais un contrôle de lui-même (règle 9) et un contrôle actif doit avoir son
exigence source (L5-T03).

Un contrôle dont la condition compare deux grandeurs (une dépense à un plafond) s'écrit sur le
RESTE : le contexte (`contextes.py`) fournit le disponible, le contrôle exige qu'il reste
positif ou nul. Un plafond absent ne déclenche rien : la condition d'applicabilité
(`est_renseigne`) rend le contrôle non applicable, noté au journal seulement.

Trois familles se paramètrent par une fabrique plutôt que par une valeur livrée : les règles de
pièces (aucune liste universelle de justificatifs), l'éligibilité (nature, zone, date,
bénéficiaire : ce que le projet a configuré) et les seuils de risque.
"""

import datetime
from dataclasses import dataclass, field

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


@dataclass(frozen=True)
class DefinitionControle:
    code: str
    famille: str
    label: dict
    type_regle: str
    severity: str
    expression: dict
    action_corrective: str
    applicable_si: dict | None = None
    parametres: dict = field(default_factory=dict)


def _expr(type_regle: str, *conditions) -> dict:
    return {"type_regle": type_regle, "conditions": list(conditions)}


def _c(champ: str, op: str, valeur=None) -> dict:
    return {"champ": champ, "op": op} | ({} if valeur is None else {"valeur": valeur})


def _definition(code, famille, fr, en, severity, action, expression, applicable_si=None, **kw):
    return DefinitionControle(
        code=code,
        famille=famille,
        label={"fr": fr, "en": en},
        type_regle=expression["type_regle"],
        severity=severity,
        expression=expression,
        action_corrective=action,
        applicable_si=applicable_si,
        **kw,
    )


def _reste_positif(code, fr, en, champ, action):
    return _definition(
        code,
        "budget",
        fr,
        en,
        "bloquant",
        action,
        _expr("budget", _c(champ, "gte", "0")),
        _expr("budget", _c(champ, "est_renseigne")),
    )


# --- les contrôles livrés tels quels -------------------------------------------------------

LIVRES: tuple[DefinitionControle, ...] = (
    # Codification
    _definition(
        "COD-CATEGORIE",
        "codification",
        "Dépense sans catégorie",
        "Expense without category",
        "bloquant",
        "Imputer la dépense à une catégorie de l'accord",
        _expr("codification", _c("categorie", "est_renseigne")),
    ),
    _definition(
        "COD-SOURCE",
        "codification",
        "Dépense sans source de financement",
        "Expense without funding source",
        "bloquant",
        "Renseigner la source de financement de la dépense",
        _expr("codification", _c("source", "est_renseigne")),
    ),
    _definition(
        "COD-AXE-1",
        "codification",
        "Dépense sans axe obligatoire (axe 1)",
        "Expense without mandatory axis (axis 1)",
        "bloquant",
        "Renseigner l'axe analytique obligatoire",
        _expr("codification", _c("axe_1", "est_renseigne")),
    ),
    # Budget
    _reste_positif(
        "BUD-LIGNE",
        "Dépassement de la ligne budgétaire",
        "Budget line overrun",
        "disponible_ligne",
        "Demander un transfert budgétaire ou réduire la dépense",
    ),
    _reste_positif(
        "BUD-CATEGORIE",
        "Dépassement du plafond de catégorie",
        "Category ceiling overrun",
        "disponible_categorie",
        "Demander une réallocation entre catégories",
    ),
    _reste_positif(
        "BUD-ALLOCATION",
        "Dépassement de l'allocation de la catégorie",
        "Category allocation overrun",
        "disponible_allocation",
        "Demander une réallocation entre catégories",
    ),
    _reste_positif(
        "BUD-ACCORD",
        "Dépassement du plafond de l'accord",
        "Agreement ceiling overrun",
        "disponible_accord",
        "Demander un avenant à l'accord de financement",
    ),
    # Pièces
    _definition(
        "PIE-DOUBLON",
        "pieces",
        "Doublon de facture",
        "Duplicate invoice",
        "bloquant",
        "Vérifier qu'il ne s'agit pas d'une même facture saisie deux fois",
        _expr("pieces", _c("facture_en_double", "est_faux")),
    ),
    _definition(
        "PIE-ETAT-CERTIFIE",
        "pieces",
        "Pièce manquante pour une dépense destinée à un état certifié",
        "Missing supporting document for an expense meant for a certified statement",
        "bloquant",
        "Rattacher la pièce justificative à l'opération",
        _expr("pieces", _c("pieces", "est_renseigne")),
        _expr("pieces", _c("destinee_etat_certifie", "est_vrai")),
    ),
    # Trésorerie
    _definition(
        "TRE-ECART",
        "tresorerie",
        "Écart de rapprochement non justifié",
        "Unjustified reconciliation difference",
        "bloquant",
        "Justifier l'écart ou passer l'écriture de régularisation",
        _expr("tresorerie", _c("ecart_rapprochement", "eq", "0")),
        _expr("tresorerie", _c("ecart_justifie", "est_faux")),
    ),
    _definition(
        "TRE-SOLDE-DESIGNE",
        "tresorerie",
        "Solde du compte désigné incohérent",
        "Inconsistent designated account balance",
        "bloquant",
        "Rapprocher le solde bancaire du solde attendu",
        _expr("tresorerie", _c("ecart_solde", "eq", "0")),
    ),
    # Avances
    _definition(
        "AVA-NON-JUSTIFIEE",
        "avances",
        "Avance non justifiée",
        "Unjustified advance",
        "avertissement",
        "Justifier l'avance par des dépenses ou un remboursement",
        _expr("avances", _c("justifiee", "est_vrai")),
    ),
    _definition(
        "AVA-DELAI",
        "avances",
        "Avance au-delà du délai applicable",
        "Advance beyond the applicable deadline",
        "bloquant",
        "Justifier l'avance ou la rembourser sans délai",
        _expr("avances", _c("jours_de_retard", "lte", 0)),
    ),
    # Rapport
    _definition(
        "RAP-RUBRIQUE-VIDE",
        "rapport",
        "Rubrique obligatoire vide",
        "Empty mandatory line",
        "bloquant",
        "Renseigner la rubrique ou en justifier l'absence",
        _expr("rapport", _c("rubrique_vide", "est_faux")),
        _expr("rapport", _c("rubrique_obligatoire", "est_vrai")),
    ),
    _definition(
        "RAP-COMPTE-NON-MAPPE",
        "rapport",
        "Compte non mappé",
        "Unmapped account",
        "bloquant",
        "Compléter le mapping des comptes cités (règle 8)",
        _expr("rapport", _c("comptes_non_mappes", "est_absent")),
    ),
    _definition(
        "RAP-ASSERTION",
        "rapport",
        "Assertion non vérifiée",
        "Unverified assertion",
        "bloquant",
        "Corriger les données jusqu'à ce que l'assertion soit vérifiée",
        _expr("rapport", _c("assertions_non_verifiees", "est_absent")),
    ),
    # Cohérence
    _definition(
        "COH-ETATS",
        "coherence",
        "Incohérence entre états d'une période",
        "Inconsistency between statements of a period",
        "bloquant",
        "Rapprocher les deux états et corriger l'écart",
        _expr("coherence", _c("ecart_entre_etats", "eq", "0")),
    ),
    _definition(
        "COH-PERIODES",
        "coherence",
        "Incohérence entre deux périodes",
        "Inconsistency between two periods",
        "bloquant",
        "Rapprocher le solde de clôture et le solde d'ouverture",
        _expr("coherence", _c("ecart_entre_periodes", "eq", "0")),
    ),
    _definition(
        "COH-CUMUL",
        "coherence",
        "Rupture de cumul",
        "Cumulative break",
        "bloquant",
        "Corriger la période qui rompt le cumul",
        _expr("coherence", _c("rupture_de_cumul", "eq", "0")),
    ),
)
PAR_CODE = {d.code: d for d in LIVRES}


# --- les fabriques : ce que le projet a configuré -------------------------------------------


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
    return _definition(
        code, "pieces", f"Pièce exigée : {type_piece}", f"Required document: {type_piece}",
        "bloquant", f"Rattacher une pièce de type « {type_piece} » à l'opération",
        _expr("pieces", _c("pieces", "est_renseigne")),
        _expr("pieces", *portee) if portee else None,
        parametres={"type_piece": type_piece, "validee": validee},
    )  # fmt: skip


def eligibilite_nature(code: str, natures: list[str]) -> DefinitionControle:
    return _definition(
        code, "eligibilite", "Nature de dépense non éligible", "Ineligible expense type",
        "bloquant", "Imputer la dépense à une nature éligible ou la retirer de l'état",
        _expr("eligibilite", _c("nature", "in", list(natures))),
    )  # fmt: skip


def eligibilite_zone(code: str, zones: list[str]) -> DefinitionControle:
    return _definition(
        code, "eligibilite", "Zone non éligible", "Ineligible area", "bloquant",
        "Vérifier la zone d'exécution de la dépense",
        _expr("eligibilite", _c("zone", "in", list(zones))),
    )  # fmt: skip


def eligibilite_periode(code: str, du: datetime.date, au: datetime.date) -> DefinitionControle:
    """Dépense datée dans `[du, au[` : la fin est exclue."""
    return _definition(
        code, "eligibilite", "Dépense hors de la période d'éligibilité",
        "Expense outside the eligibility period", "bloquant",
        "Vérifier la date de la dépense face à la période d'éligibilité",
        _expr("eligibilite", _c("date", "entre", [du.isoformat(), au.isoformat()])),
    )  # fmt: skip


def eligibilite_beneficiaires_exclus(code: str, exclus: list[str]) -> DefinitionControle:
    return _definition(
        code, "eligibilite", "Bénéficiaire exclu", "Excluded beneficiary", "bloquant",
        "Choisir un bénéficiaire éligible",
        _expr("eligibilite", _c("beneficiaire", "not_in", list(exclus))),
        _expr("eligibilite", _c("beneficiaire", "est_renseigne")),
    )  # fmt: skip


def risque_categorie_consommee(seuil_pct: str = "80") -> DefinitionControle:
    """Catégorie consommée au-delà d'un seuil paramétré (en %) : un avertissement."""
    return _definition(
        "RIS-CATEGORIE-SEUIL", "risque", f"Catégorie consommée au-delà de {seuil_pct} %",
        f"Category consumed beyond {seuil_pct}%", "avertissement",
        "Anticiper une réallocation ou ralentir les engagements",
        _expr("risque", _c("taux_consommation_categorie", "lte", seuil_pct)),
        _expr("risque", _c("taux_consommation_categorie", "est_renseigne")),
    )  # fmt: skip


def risque_avance_non_apuree(delai_jours: int = 90) -> DefinitionControle:
    """Avance non apurée depuis plus d'un délai paramétré : une information."""
    return _definition(
        "RIS-AVANCE-NON-APUREE", "risque",
        f"Avance non apurée depuis plus de {delai_jours} jours",
        f"Advance not cleared for more than {delai_jours} days", "information",
        "Relancer le bénéficiaire pour la justification",
        _expr("risque", _c("jours_avance_non_apuree", "lte", delai_jours)),
        _expr("risque", _c("jours_avance_non_apuree", "est_renseigne")),
    )  # fmt: skip


def risque_rejets_repetes(maximum: int = 3) -> DefinitionControle:
    """Rejets répétés sur une même catégorie : une information."""
    return _definition(
        "RIS-REJETS-REPETES", "risque", f"Plus de {maximum} rejets sur une même catégorie",
        f"More than {maximum} rejections on the same category", "information",
        "Examiner la cause commune de ces rejets avant de redéposer",
        _expr("risque", _c("rejets_categorie", "lte", maximum)),
        _expr("risque", _c("rejets_categorie", "est_renseigne")),
    )  # fmt: skip


def livres_avec_risque() -> tuple[DefinitionControle, ...]:
    """Les contrôles livrés, trois contrôles de risque aux seuils par défaut compris."""
    return (
        *LIVRES,
        risque_categorie_consommee(),
        risque_avance_non_apuree(),
        risque_rejets_repetes(),
    )
