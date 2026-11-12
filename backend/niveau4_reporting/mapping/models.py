"""Tables et règles de mapping versionnées. Voir L0-T04."""

from django.db import models
from django.db.models import Q

from core.models import ModeleOrganisation


class StatutMapping(models.TextChoices):
    BROUILLON = "draft", "Brouillon"
    VALIDE = "validated", "Validé"
    ACTIF = "active", "Actif"
    REMPLACE = "superseded", "Remplacé"


class TableMapping(ModeleOrganisation):
    """Une version d'une nomenclature bailleur pour un projet."""

    project_id = models.UUIDField(null=True, blank=True, db_index=True)
    donor_profile_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64)
    version = models.PositiveIntegerField()
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)  # exclu : [valid_from, valid_to[
    status = models.CharField(
        max_length=16,
        choices=StatutMapping.choices,
        default=StatutMapping.BROUILLON,
    )
    validated_by = models.UUIDField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "mapping_table"
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "project_id", "donor_profile_id", "code", "version"],
                name="uq_mapping_version",
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gt=models.F("valid_from")),
                name="mapping_dates_coherentes",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=[StatutMapping.VALIDE, StatutMapping.ACTIF])
                | Q(validated_by__isnull=False, validated_at__isnull=False),
                name="mapping_validation_obligatoire",
            ),
        ]
        indexes = [
            models.Index(
                fields=["project_id", "donor_profile_id", "code", "valid_from"],
                name="idx_mapping_recherche",
            ),
        ]


class RegleMapping(ModeleOrganisation):
    """Première règle prioritaire dont tous les critères correspondent."""

    table = models.ForeignKey(
        TableMapping,
        on_delete=models.CASCADE,
        related_name="regles",
    )
    priority = models.PositiveIntegerField()
    match = models.JSONField()
    target_code = models.CharField(max_length=64)
    condition_expr = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "mapping_rule"
        ordering = ["priority"]
        constraints = [
            models.UniqueConstraint(
                fields=["table", "priority"],
                name="uq_mapping_regle_priorite",
            ),
        ]
