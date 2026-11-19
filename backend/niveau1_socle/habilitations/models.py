"""Rôles et habilitations par projet et par site. Voir L1-T05 et architecture §8.

L'organisation est isolée par la RLS ; le projet l'est par HABILITATION, vérifiée
au serveur à chaque requête (`permissions.HabilitationRequise`). Ces tables
portent `org_id` et sont, elles, sous RLS.
"""

from django.db import models
from django.db.models import Q

from core.models import ModeleOrganisation

# Ensemble fermé des opérations : en ajouter une est une migration, pas un réglage.
OPERATIONS = (
    "consulter",
    "saisir",
    "valider",
    "comptabiliser",
    "parametrer",
    "exporter",
    "publier",
    "voir_numero_compte",  # le numéro complet d'un compte bancaire (L4-T04)
)


class Role(ModeleOrganisation):
    code = models.CharField(max_length=32)
    label = models.JSONField()  # {"fr": …, "en": …}
    operations = models.JSONField(default=list)  # sous-ensemble de OPERATIONS

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org_id", "code"], name="uq_role_code"),
        ]

    def __str__(self) -> str:
        return self.code


class Habilitation(ModeleOrganisation):
    """Un utilisateur tient un rôle sur un projet, éventuellement limité à un site."""

    user_id = models.UUIDField(db_index=True)
    project_id = models.UUIDField(db_index=True)
    site = models.CharField(max_length=20, null=True, blank=True)  # nul : tous les sites
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="habilitations")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "user_id", "project_id", "site", "role"],
                name="uq_habilitation",
                nulls_distinct=False,  # deux habilitations « tous sites » identiques : un doublon
            ),
            models.CheckConstraint(
                condition=Q(site__isnull=True) | ~Q(site=""), name="habilitation_site_non_vide"
            ),
        ]
