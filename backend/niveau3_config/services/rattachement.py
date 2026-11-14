"""Le rattachement : tout objet de configuration actif a une exigence source. Voir L5-T03.

La règle qui donne sa valeur au produit : un objet de configuration ACTIF (mapping, rubrique
d'état, contrôle, périodicité…) doit se rattacher à au moins une exigence ACTIVE du projet, valable
à la date considérée. Un objet actif sans exigence source est une ANOMALIE DE CONFIGURATION,
signalée par le système lui-même (`detecter_configuration_orpheline`). C'est ce qui rend le
dossier de conformité (L7) générable automatiquement, et ce qui empêche la configuration de
redevenir une boîte noire.

Chaque type d'objet déclare comment lister ses objets actifs et comment vérifier qu'un identifiant
existe (`enregistrer_cible`). Les mappings sont branchés ici ; les modèles d'états, rubriques et
contrôles s'y brancheront avec le lot L6 sans rien changer à ce module.

Habilitation : `parametrer`. Un rattachement est en AJOUT SEUL (la base l'impose) : on ne détache
pas, on remplace l'objet ou l'exigence par une version nouvelle.
"""

import datetime
from collections.abc import Callable
from dataclasses import dataclass

from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.i18n import Liste, msg
from niveau1_socle.habilitations.permissions import est_habilite
from niveau4_reporting.mapping.models import StatutMapping, TableMapping

from ..models import Exigence, RattachementExigence, StatutExigence, TypeCible

STATUTS_RATTACHABLES = (
    StatutExigence.PROPOSEE,
    StatutExigence.VALIDEE,
    StatutExigence.ACTIVE,
)


class RattachementInvalide(ValueError):
    """Le rattachement demandé ne respecte pas les règles."""


class ConfigurationOrpheline(ValueError):
    """Des objets de configuration actifs n'ont pas d'exigence source ; `orphelins` les liste."""

    def __init__(self, orphelins: list["Orphelin"]):
        self.orphelins = orphelins
        super().__init__(
            msg(
                "rattachement.configuration_sans_exigence_source",
                details=Liste(
                    [
                        msg(
                            "rattachement.orphelin",
                            type=o.target_type,
                            libelle=o.libelle,
                            raison=o.raison,
                        )
                        for o in orphelins
                    ]
                ),
            )
        )


@dataclass(frozen=True)
class Orphelin:
    target_type: str
    target_id: object
    libelle: str
    raison: str


@dataclass(frozen=True)
class SourceCible:
    lister_actifs: Callable[[object, datetime.date], list[tuple[object, str]]]
    existe: Callable[[object, object], bool]  # (project_id, target_id) -> bool


def _mappings_actifs(project_id, date):
    mappings = TableMapping.objects.filter(
        project_id=project_id, status=StatutMapping.ACTIF, valid_from__lte=date
    ).exclude(valid_to__lte=date)
    return [(m.pk, f"{m.code} v{m.version}") for m in mappings.order_by("code", "version")]


def _mapping_existe(project_id, target_id):
    return TableMapping.objects.filter(pk=target_id, project_id=project_id).exists()


SOURCES: dict[str, SourceCible] = {
    TypeCible.MAPPING: SourceCible(_mappings_actifs, _mapping_existe),
}


def enregistrer_cible(target_type: str, source: SourceCible) -> None:
    """Branche un type d'objet de configuration sur la règle (point d'extension de L6)."""
    if target_type not in TypeCible.values:
        raise ValueError(msg("rattachement.type_cible_inconnu", target_type=target_type))
    SOURCES[target_type] = source


def _habilite(utilisateur, project_id) -> None:
    if not est_habilite(utilisateur, "parametrer", project_id):
        raise PermissionDenied(msg("rattachement.vous_etes_habilite_parametrer_projet"))


def rattacher(
    *, utilisateur, exigence: Exigence, target_type: str, target_id
) -> RattachementExigence:
    """Rattache un objet de configuration à l'exigence qui le justifie. Idempotent.

    Quand le type de l'objet est branché, l'objet doit exister dans le projet de l'exigence. Une
    exigence remplacée ou rejetée ne justifie plus rien : on ne s'y rattache pas.
    """
    _habilite(utilisateur, exigence.project_id)
    if target_type not in TypeCible.values:
        raise RattachementInvalide(msg("rattachement.type_cible_inconnu", target_type=target_type))
    source = SOURCES.get(target_type)
    if source is not None and not source.existe(exigence.project_id, target_id):
        raise RattachementInvalide(
            msg(
                "rattachement.objet_existe_projet_exigence",
                target_id=target_id,
                target_type=target_type,
            )
        )
    with transaction.atomic():
        courante = Exigence.objects.select_for_update().get(pk=exigence.pk)
        if courante.status not in STATUTS_RATTACHABLES:
            raise RattachementInvalide(
                msg(
                    "rattachement.exigence_v_elle_justifie_plus",
                    code=courante.code,
                    version=courante.version,
                    status=courante.status,
                )
            )
        rattachement, cree = RattachementExigence.objects.get_or_create(
            exigence=courante,
            target_type=target_type,
            target_id=target_id,
            defaults={"org_id": utilisateur.org_id, "created_by": utilisateur.id},
        )
        if cree:
            journaliser(
                org_id=courante.org_id,
                actor_id=utilisateur.id,
                action="requirement_bound",
                object_type="exigence",
                object_id=courante.id,
                project_id=courante.project_id,
                after={"target_type": target_type, "target_id": str(target_id)},
            )
    return rattachement


def _exigences_justifiantes(project_id, date):
    return Exigence.objects.filter(
        project_id=project_id, status=StatutExigence.ACTIVE, valid_from__lte=date
    ).exclude(valid_to__lte=date)


def detecter_configuration_orpheline(
    project_id, date: datetime.date | None = None
) -> list[Orphelin]:
    """Les objets de configuration ACTIFS à `date` sans exigence source ACTIVE et valable à `date`.

    Pour chaque orphelin, la raison distingue « aucun rattachement » de « rattaché seulement à
    des exigences non actives ou hors validité » : un oubli, ou un défaut de suivi.
    """
    date = date or datetime.date.today()
    justifiantes = set(_exigences_justifiantes(project_id, date).values_list("pk", flat=True))
    orphelins = []
    for target_type, source in sorted(SOURCES.items()):
        for target_id, libelle in source.lister_actifs(project_id, date):
            liees = set(
                RattachementExigence.objects.filter(
                    target_type=target_type, target_id=target_id
                ).values_list("exigence_id", flat=True)
            )
            if liees & justifiantes:
                continue
            raison = msg(
                "rattachement.raison_exigences_non_actives"
                if liees
                else "rattachement.raison_aucun_rattachement"
            )
            orphelins.append(Orphelin(target_type, target_id, libelle, raison))
    return orphelins


def exiger_configuration_sans_orphelin(project_id, date: datetime.date | None = None) -> None:
    orphelins = detecter_configuration_orpheline(project_id, date)
    if orphelins:
        raise ConfigurationOrpheline(orphelins)
