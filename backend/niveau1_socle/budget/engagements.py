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
from niveau1_socle.organisations.models import BaseComptable, Projet

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
    ligne_passation=None,
    **identifiants,
) -> Engagement:
    """Ouvre un engagement. Le montant est en monnaie de tenue du projet.

    `ligne_passation` rattache l'engagement à un marché du plan (L9-T02) : si la méthode du
    marché exige l'avis de non-objection, l'engagement est REFUSÉ tant que l'avis n'est pas
    obtenu. Sans marché, l'engagement reste possible (dépense hors passation).
    """
    _habilite(utilisateur, "saisir", project_id)
    # La base comptable du projet décide s'il réserve du budget : la caisse pure n'engage rien.
    if (
        Projet.objects.values_list("accounting_basis", flat=True).get(pk=project_id)
        == BaseComptable.ENCAISSEMENTS
    ):
        raise BudgetInvalide(msg("engagements.projet_en_caisse_sans_engagement"))
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
    if ligne_passation is not None:
        _verifier_marche(ligne_passation, project_id)
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
            ligne_passation=ligne_passation,
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
            after={
                "reference": engagement.reference,
                "montant": str(montant),
                "marche": ligne_passation.reference if ligne_passation else None,
            },
        )
    engagement.avertissements_budgetaires = avertissements
    return engagement


def _verifier_marche(ligne, project_id) -> None:
    """Le marché est du même projet, vivant, et son avis de non-objection est suffisant."""
    from niveau1_socle.marches.avis import avis_manquants
    from niveau1_socle.marches.models import LignePassation, StatutLigne

    courante = LignePassation.objects.get(pk=ligne.pk)
    if courante.project_id != project_id:
        raise BudgetInvalide(msg("passation.engagement_autre_projet", reference=courante.reference))
    if courante.statut == StatutLigne.ANNULE:
        raise BudgetInvalide(
            msg("passation.engagement_marche_annule", reference=courante.reference)
        )
    manquants = avis_manquants(courante)
    if manquants:
        raise BudgetInvalide(
            msg(
                "passation.engagement_sans_avis",
                reference=courante.reference,
                objets=", ".join(m for m in manquants if m) or "—",
            )
        )


def apurer_engagement(engagement: Engagement, *, utilisateur, montant) -> Engagement:
    """Apure tout ou partie d'un engagement ouvert. Apuré en totalité, il passe à « soldé ».

    Un engagement rattaché à un marché (L9-T04) ne s'apure QUE par décompte certifié : l'apurement
    à la main contournerait les soldes contractuels.
    """
    montant = Decimal(str(montant))
    with transaction.atomic():
        courant = Engagement.objects.select_for_update().get(pk=engagement.pk)
        _habilite(utilisateur, "saisir", courant.project_id)
        if courant.ligne_passation_id is not None:
            raise BudgetInvalide(
                msg("passation.apurement_par_decompte", reference=courant.reference)
            )
        apurer_verrouille(courant, utilisateur=utilisateur, montant=montant)
    engagement.refresh_from_db()
    return engagement


def apurer_verrouille(courant: Engagement, *, utilisateur, montant: Decimal) -> None:
    """Apure un engagement DÉJÀ verrouillé (`select_for_update`) dans la transaction en cours.

    L'habilitation est l'affaire de l'appelant : « saisir » pour l'apurement direct, « valider »
    pour la certification d'un décompte.
    """
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
