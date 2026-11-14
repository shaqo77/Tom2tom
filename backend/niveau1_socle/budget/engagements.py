"""Engagements : réserver du budget avant la dépense. Voir L4-T02 (version minimale).

Création, apurement et annulation passent par ces services ; le solde budgétaire suit par
déclencheur, dans la même transaction. Habilitation `saisir`.
"""

import logging
from decimal import Decimal

from django.db import transaction

from core.audit import journaliser
from core.i18n import msg
from niveau1_socle.exercices.services import TransitionInterdite

from .controle import appliquer, evaluer_engagement
from .models import Engagement, StatutEngagement
from .services import (
    IDENTIFIANTS_LIBRES,
    BudgetInvalide,
    _axes,
    _habilite,
)

journal_technique = logging.getLogger(__name__)


def creer_engagement(
    *,
    utilisateur,
    project_id,
    reference: str,
    annee: int,
    montant,
    periode: int | None = None,
    libelle: str = "",
    axes: dict | None = None,
    **identifiants,
) -> Engagement:
    """Ouvre un engagement. Le montant est en monnaie de tenue du projet."""
    _habilite(utilisateur, "saisir", project_id)
    montant = Decimal(str(montant))
    if montant <= 0:
        raise BudgetInvalide(msg("engagements.engagement_montant_strictement_positif"))
    if not (reference or "").strip():
        raise BudgetInvalide(msg("engagements.reference_engagement_obligatoire"))
    if periode is not None and not 1 <= periode <= 12:
        raise BudgetInvalide(msg("engagements.periode_comprise_entre_1_12"))
    inconnus = set(identifiants) - set(IDENTIFIANTS_LIBRES)
    if inconnus:
        raise BudgetInvalide(msg("engagements.identifiant_inconnu", v1=sorted(inconnus)))
    with transaction.atomic():
        axes_resolus = _axes(axes)
        # Contrôle budgétaire (L4-T03), avec verrou sur les soldes : deux engagements simultanés
        # sur le même disponible ne passent pas ensemble.
        avertissements = appliquer(
            evaluer_engagement(
                project_id,
                annee=annee,
                periode=periode,
                montant=montant,
                dim_ids=tuple(
                    getattr(axes_resolus.get(champ), "id", None)
                    for champ in ("dim1", "dim2", "dim3", "dim4")
                ),
                agreement_id=identifiants.get("agreement_id"),
                category_id=identifiants.get("category_id"),
                site_id=identifiants.get("site_id"),
                verrouiller=True,
            ),
            utilisateur=utilisateur,
            objet_type="engagement",
            objet_id=None,
            project_id=project_id,
        )
        engagement = Engagement.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            reference=reference.strip(),
            libelle=libelle,
            annee=annee,
            periode=periode,
            montant=montant,
            created_by=utilisateur.id,
            **axes_resolus,
            **{cle: valeur for cle, valeur in identifiants.items() if valeur},
        )
        journaliser(
            org_id=engagement.org_id,
            actor_id=utilisateur.id,
            action="engagement_created",
            object_type="engagement",
            object_id=engagement.id,
            project_id=project_id,
            after={"reference": engagement.reference, "montant": str(montant)},
        )
    engagement.avertissements_budgetaires = avertissements
    return engagement


def apurer_engagement(engagement: Engagement, *, utilisateur, montant) -> Engagement:
    """Apure tout ou partie d'un engagement ouvert. Apuré en totalité, il passe à « soldé »."""
    montant = Decimal(str(montant))
    with transaction.atomic():
        courant = Engagement.objects.select_for_update().get(pk=engagement.pk)
        _habilite(utilisateur, "saisir", courant.project_id)
        if courant.status != StatutEngagement.OUVERT:
            raise TransitionInterdite(
                msg(
                    "engagements.engagement_on_apure_engagement_ouvert",
                    reference=courant.reference,
                    status=courant.status,
                )
            )
        if montant <= 0:
            raise BudgetInvalide(msg("engagements.montant_apurer_strictement_positif"))
        reste = courant.montant - courant.apure
        if montant > reste:
            raise BudgetInvalide(
                msg("engagements.on_peut_apurer_plus_reste", reste=reste, montant=montant)
            )
        apure = courant.apure + montant
        solde = apure == courant.montant
        Engagement.objects.filter(pk=courant.pk).update(
            apure=apure, status=StatutEngagement.SOLDE if solde else StatutEngagement.OUVERT
        )
        journaliser(
            org_id=courant.org_id,
            actor_id=utilisateur.id,
            action="engagement_cleared",
            object_type="engagement",
            object_id=courant.id,
            project_id=courant.project_id,
            before={"apure": str(courant.apure)},
            after={"apure": str(apure), "status": "solde" if solde else "ouvert"},
        )
    engagement.refresh_from_db()
    return engagement


def annuler_engagement(engagement: Engagement, *, utilisateur, motif: str) -> Engagement:
    """Annule un engagement ouvert : le reste non apuré redevient disponible."""
    if not (motif or "").strip():
        raise BudgetInvalide(msg("engagements.motif_annulation_obligatoire"))
    with transaction.atomic():
        courant = Engagement.objects.select_for_update().get(pk=engagement.pk)
        _habilite(utilisateur, "saisir", courant.project_id)
        if courant.status != StatutEngagement.OUVERT:
            raise TransitionInterdite(
                msg(
                    "engagements.engagement_il_s_annule_plus",
                    reference=courant.reference,
                    status=courant.status,
                )
            )
        Engagement.objects.filter(pk=courant.pk).update(status=StatutEngagement.ANNULE)
        journaliser(
            org_id=courant.org_id,
            actor_id=utilisateur.id,
            action="engagement_cancelled",
            object_type="engagement",
            object_id=courant.id,
            project_id=courant.project_id,
            before={"status": "ouvert", "non_apure": str(courant.montant - courant.apure)},
            after={"status": "annule", "motif": motif.strip()},
        )
    engagement.refresh_from_db()
    return engagement
