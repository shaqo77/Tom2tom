"""Fabrique de profils de décaissement pour les tests (L5-T03bis)."""

import datetime
import uuid
from decimal import Decimal

from django.utils import timezone

from niveau3_config.models import (
    MethodeDecaissement,
    ProfilDecaissement,
    RegleCompteDesigne,
    RegleFinancementCategorie,
)

D = Decimal


def creer_profil(
    organisation,
    projet,
    accord,
    *,
    version=1,
    valid_from=datetime.date(2026, 1, 1),
    valid_to=None,
    regime="transaction_based",
    statut="active",
    eligibility_date=None,
    closing_date=None,
    disbursement_deadline=None,
    methodes=("reimbursement",),
    regles=(),
    comptes=(),
    **champs,
):
    """Un profil, ses méthodes (`str` ou `dict`), ses règles `(catégorie, taux[, champs])` et ses
    comptes désignés `dict(compte=…, plafond=…)`."""
    profil = ProfilDecaissement.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        accord=accord,
        version=version,
        valid_from=valid_from,
        valid_to=valid_to,
        regime=regime,
        status="draft",  # les enfants ne s'ajoutent qu'à un brouillon (L5-T04) ; on fige ensuite
        eligibility_date=eligibility_date,
        closing_date=closing_date,
        disbursement_deadline=disbursement_deadline,
        **champs,
    )
    for methode in methodes:
        donnees = {"method": methode} if isinstance(methode, str) else dict(methode)
        donnees.setdefault("supporting_docs", ["soe"])
        MethodeDecaissement.objects.create(org_id=organisation.id, profil=profil, **donnees)
    for categorie, taux, *reste in regles:
        RegleFinancementCategorie.objects.create(
            org_id=organisation.id,
            profil=profil,
            category=categorie,
            funding_rate=D(str(taux)),
            allocation=D(10**9),
            tax_basis="taxes_included",
            **(reste[0] if reste else {}),
        )
    for compte in comptes:
        RegleCompteDesigne.objects.create(
            org_id=organisation.id,
            profil=profil,
            bank_account=compte["compte"],
            currency_id=compte.get("devise", "DJF"),
            ceiling_kind="fixed" if compte.get("plafond") is not None else "variable",
            ceiling_amount=compte.get("plafond"),
        )
    if statut != "draft":
        validation = (
            {"validated_by": uuid.uuid4(), "validated_at": timezone.now()}
            if statut in ("validated", "active")
            else {}
        )
        ProfilDecaissement.objects.filter(pk=profil.pk).update(status=statut, **validation)
        profil.refresh_from_db()
    return profil
