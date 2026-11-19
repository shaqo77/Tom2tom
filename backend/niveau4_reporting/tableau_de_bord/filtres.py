"""Le périmètre du tableau de bord : les projets que l'utilisateur peut consulter, filtrés."""

import datetime
import uuid
from dataclasses import dataclass

from niveau1_socle.financements.models import Accord, StatutAccord
from niveau1_socle.habilitations.models import Habilitation
from niveau1_socle.organisations.models import Projet, StatutProjet
from niveau3_config.services.activation import resoudre_configuration

CONFIGURE = "configure"
NON_CONFIGURE = "non_configure"


@dataclass(frozen=True)
class Filtres:
    """Les filtres du tableau de bord. L'organisation est celle de l'utilisateur (isolation par la
    base) ; tous les autres sont facultatifs. `statut_projet` vaut « actif » par défaut : un tableau
    de bord regarde les projets en cours, sauf demande contraire (`None` : tous).

    `statut_configuration` : `configure` si au moins une exigence est active à la date du tableau,
    `non_configure` sinon.
    """

    projets: frozenset[uuid.UUID] | None = None
    bailleur_id: uuid.UUID | None = None
    accord_id: uuid.UUID | None = None
    devise: str | None = None
    du: datetime.date | None = None
    au: datetime.date | None = None
    statut_accord: str | None = None
    statut_projet: str | None = StatutProjet.ACTIF
    statut_configuration: str | None = None

    @property
    def restreint_les_accords(self) -> bool:
        """Vrai si un filtre désigne des accords précis (bailleur ou accord)."""
        return self.bailleur_id is not None or self.accord_id is not None


def accords_du_filtre(project_id, filtres: Filtres):
    """Les accords du projet qui satisfont les filtres d'accord (bailleur, accord, statut)."""
    accords = Accord.objects.filter(project_id=project_id)
    if filtres.bailleur_id:
        accords = accords.filter(bailleur_id=filtres.bailleur_id)
    if filtres.accord_id:
        accords = accords.filter(pk=filtres.accord_id)
    if filtres.statut_accord:
        accords = accords.filter(status=filtres.statut_accord)
    else:  # ni brouillon ni annulé par défaut : un accord qui ne finance pas ne se compte pas
        accords = accords.exclude(status__in=[StatutAccord.BROUILLON, StatutAccord.ANNULE])
    if filtres.devise:
        accords = accords.filter(devise_id=filtres.devise)
    return accords


def perimetre(utilisateur, filtres: Filtres, jour: datetime.date) -> list[Projet]:
    """Les projets du tableau de bord : consultables par l'utilisateur, puis filtrés.

    Un projet sans habilitation « consulter » n'y figure JAMAIS, quel que soit le filtre demandé.
    """
    ids = set(
        Habilitation.objects.filter(
            user_id=utilisateur.id, role__operations__contains=["consulter"], site__isnull=True
        ).values_list("project_id", flat=True)
    )
    if filtres.projets is not None:
        ids &= set(filtres.projets)
    projets = Projet.objects.filter(pk__in=ids).order_by("code")
    if filtres.statut_projet:
        projets = projets.filter(status=filtres.statut_projet)
    retenus = []
    for projet in projets:
        if (filtres.restreint_les_accords or filtres.statut_accord) and not accords_du_filtre(
            projet.id, filtres
        ).exists():
            continue
        if filtres.statut_configuration:
            configure = bool(resoudre_configuration(projet.id, jour).exigences)
            if configure != (filtres.statut_configuration == CONFIGURE):
                continue
        retenus.append(projet)
    return retenus


def ids_accords_du_filtre(projet, filtres: Filtres):
    """Les accords que le filtre désigne, ou `None` si aucun filtre d'accord ne restreint."""
    if not filtres.restreint_les_accords:
        return None
    return list(accords_du_filtre(projet.id, filtres).values_list("pk", flat=True))
