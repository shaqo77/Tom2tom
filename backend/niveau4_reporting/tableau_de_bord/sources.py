"""Les requêtes que le tableau de bord ET sa descente partagent. Voir L10-T02.

Une seule définition de chaque ensemble d'objets : le tableau les additionne, la descente les liste.
Deux copies finiraient par diverger, et le contrôle « la somme du détail égale l'indicateur » n'y
survivrait pas.
"""

import datetime
from decimal import Decimal

from niveau1_socle.budget.models import (
    Engagement,
    LigneBudget,
    StatutEngagement,
    StatutVersion,
    VersionBudget,
)
from niveau1_socle.financements.services import montant_courant
from niveau1_socle.tresorerie.models import AppariementDemande

from .filtres import Filtres, accords_du_filtre


def version_budget(project_id, code: str) -> VersionBudget | None:
    """La version courante (`budget_approuve`) ou initiale (`budget_initial`) du projet.

    Les bases garantissent au plus une de chaque (`uq_versionbudget_une_courante`, `…_un_initial`) :
    le choix n'est pas ambigu. La version COURANTE est celle d'aujourd'hui, pas celle de `jour`.
    """
    if code == "budget_approuve":
        return VersionBudget.objects.filter(
            project_id=project_id, status=StatutVersion.APPROUVE
        ).first()
    return VersionBudget.objects.filter(project_id=project_id, type="initial").first()


def lignes_budget(version: VersionBudget | None, ids_accords):
    if version is None:
        return LigneBudget.objects.none()
    lignes = LigneBudget.objects.filter(version=version)
    if ids_accords is not None:
        lignes = lignes.filter(agreement_id__in=ids_accords)
    return lignes


def montant_accord(accord, jour: datetime.date) -> Decimal:
    """Le montant de l'accord À LA DATE du tableau (un avenant postérieur n'y compte pas)."""
    return montant_courant(accord, jour)


def appariements_recus(project_id, filtres: Filtres, jour: datetime.date):
    """Les encaissements appariés à une demande, dont le mouvement date de `jour` au plus tard."""
    accords = [a.pk for a in accords_du_filtre(project_id, filtres)]
    recus = AppariementDemande.objects.filter(
        project_id=project_id,
        annule_at__isnull=True,
        demande__accord__in=accords,
        mouvement__date_operation__lte=min(filtres.au, jour) if filtres.au else jour,
    ).select_related("mouvement__compte")
    if filtres.du:
        recus = recus.filter(mouvement__date_operation__gte=filtres.du)
    return recus


def engagements_ouverts(project_id, ids_accords, jour: datetime.date):
    engagements = Engagement.objects.filter(
        project_id=project_id, status=StatutEngagement.OUVERT, annee__lte=jour.year
    )
    if ids_accords is not None:
        engagements = engagements.filter(agreement_id__in=ids_accords)
    return engagements
