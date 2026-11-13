"""Le profil de décaissement : résolution, règle de calcul, contrôles. Voir L5-T03bis.

La règle de calcul, à ne jamais contourner :

    montant_a_retirer = dépense_éligible × funding_rate de la catégorie,
                        sur l'assiette définie par tax_basis

avec un arrondi DÉTERMINISTE vers zéro, au pas de la monnaie de tenue, comme la ventilation de
cofinancement : on ne réclame jamais au bailleur un centime de plus que le taux ne l'autorise.

Le profil est RÉSOLU à la date de l'opération (`profil_en_vigueur`), jamais au présent : une demande
de juin se contrôle avec le profil de juin, même si un avenant en a changé les seuils en décembre.
"""

import datetime
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from ..models import (
    AssietteTaxes,
    MethodeDecaissement,
    MethodeDecaissementCode,
    PlafondCompte,
    ProfilDecaissement,
    RegleFinancementCategorie,
    StatutProfil,
)

ZERO = Decimal(0)
# Le type de demande de retrait (L4-T06) et la méthode de décaissement du profil qui l'autorise.
METHODE_DU_TYPE = {
    "retrait": MethodeDecaissementCode.AVANCE,
    "reapprovisionnement": MethodeDecaissementCode.REMBOURSEMENT,
    "paiement_direct": MethodeDecaissementCode.PAIEMENT_DIRECT,
    "engagement_special": MethodeDecaissementCode.ENGAGEMENT_SPECIAL,
}


class ProfilViole(ValueError):
    """Une opération ne respecte pas le profil de décaissement en vigueur."""


def profil_en_vigueur(accord, date: datetime.date) -> ProfilDecaissement | None:
    """Le profil ACTIF de l'accord à `date` (validité `[valid_from, valid_to[`), ou rien."""
    return (
        ProfilDecaissement.objects.filter(
            accord=accord, status=StatutProfil.ACTIF, valid_from__lte=date
        )
        .exclude(valid_to__lte=date)
        .first()
    )


def accord_a_un_profil(accord) -> bool:
    """Vrai si un profil a déjà été en vigueur pour cet accord (actif ou remplacé)."""
    return ProfilDecaissement.objects.filter(
        accord=accord, status__in=[StatutProfil.ACTIF, StatutProfil.REMPLACE]
    ).exists()


def regle_pour(profil: ProfilDecaissement, categorie) -> RegleFinancementCategorie | None:
    """La règle de la catégorie, ou à défaut celle de sa catégorie parente la plus proche : une
    sous-catégorie hérite du taux de la catégorie dont elle relève."""
    regles = {r.category_id: r for r in profil.regles.all()}
    courante = categorie
    while courante is not None:
        if courante.pk in regles:
            return regles[courante.pk]
        courante = courante.parent
    return None


def methode_pour(profil: ProfilDecaissement, type_demande: str) -> MethodeDecaissement | None:
    return profil.methodes.filter(method=METHODE_DU_TYPE[type_demande]).first()


def montant_a_retirer(
    depense: Decimal,
    funding_rate: Decimal,
    tax_basis: str = AssietteTaxes.TAXES_COMPRISES,
    *,
    taxes: Decimal = ZERO,
    pas: Decimal = Decimal(1),
) -> Decimal:
    """`dépense × taux`, sur l'assiette voulue, arrondi vers zéro au `pas` de la monnaie.

    `taxes_included` : la base est la dépense TTC ; `net_of_taxes` : la dépense moins ses taxes.
    """
    depense, taxes = Decimal(depense), Decimal(taxes)
    if depense < 0 or taxes < 0 or taxes > depense:
        raise ProfilViole(
            "Une dépense et ses taxes sont positives, les taxes ne dépassant pas la dépense"
        )
    if not ZERO < Decimal(funding_rate) <= Decimal(1):
        raise ProfilViole("Un taux de financement est dans ]0 ; 1]")
    base = depense - taxes if tax_basis == AssietteTaxes.HORS_TAXES else depense
    return (base * Decimal(funding_rate)).quantize(pas, rounding=ROUND_DOWN)


def verifier_eligibilite(profil: ProfilDecaissement, regle, date_depense: datetime.date) -> None:
    """Une dépense antérieure à la date d'éligibilité, ou hors de la fenêtre de sa catégorie, n'est
    pas finançable. Le refus NOMME la date."""
    if profil.eligibility_date and date_depense < profil.eligibility_date:
        raise ProfilViole(
            f"La dépense du {date_depense} est antérieure à la date d'éligibilité du profil "
            f"({profil.eligibility_date}) : elle n'est pas finançable"
        )
    if regle.eligibility_from and date_depense < regle.eligibility_from:
        raise ProfilViole(
            f"La dépense du {date_depense} est antérieure au début d'éligibilité de la catégorie "
            f"({regle.eligibility_from})"
        )
    if regle.eligibility_to and date_depense > regle.eligibility_to:
        raise ProfilViole(
            f"La dépense du {date_depense} est postérieure à la fin d'éligibilité de la catégorie "
            f"({regle.eligibility_to})"
        )


def verifier_delai(profil: ProfilDecaissement, date_demande: datetime.date) -> None:
    if profil.disbursement_deadline and date_demande > profil.disbursement_deadline:
        raise ProfilViole(
            f"Le délai de décaissement est dépassé : date limite {profil.disbursement_deadline}, "
            f"demande du {date_demande}"
        )


def plafond_des_comptes(profil: ProfilDecaissement) -> Decimal | None:
    """La somme des plafonds FIXES des comptes désignés du profil ; rien s'il n'y en a pas."""
    plafonds = [
        c.ceiling_amount
        for c in profil.comptes.all()
        if c.ceiling_kind == PlafondCompte.FIXE and c.ceiling_amount is not None
    ]
    return sum(plafonds, ZERO) if plafonds else None


@dataclass(frozen=True)
class MinimumDemande:
    montant: Decimal
    explication: str


def minimum_de_demande(profil: ProfilDecaissement, methode) -> MinimumDemande | None:
    """Le minimum d'une demande : une valeur fixe, ou un pourcentage du plafond du compte."""
    if methode.min_application_amount is not None:
        return MinimumDemande(
            methode.min_application_amount, f"montant minimum de {methode.min_application_amount}"
        )
    if methode.min_application_pct_of_ceiling is not None:
        plafond = plafond_des_comptes(profil)
        if plafond is None:
            raise ProfilViole(
                "Le montant minimum est un pourcentage du plafond du compte désigné, "
                "mais aucun plafond fixe n'est paramétré dans le profil"
            )
        seuil = (plafond * methode.min_application_pct_of_ceiling).quantize(
            Decimal(1), rounding=ROUND_DOWN
        )
        pct = methode.min_application_pct_of_ceiling * 100
        return MinimumDemande(seuil, f"{pct.normalize():f} % du plafond ({plafond}), soit {seuil}")
    return None


def documents_exiges(methode: MethodeDecaissement, depenses: list[Decimal]) -> list[str]:
    """Les pièces à fournir. Une dépense au-delà du seuil de documentation exige les COPIES de
    pièces (`records`) et non l'état certifié (`soe`)."""
    exiges = set(methode.supporting_docs)
    seuil = methode.full_doc_threshold
    if seuil is not None and any(d > seuil for d in depenses):
        exiges = (exiges - {"soe"}) | {"records"}
    return sorted(exiges)
