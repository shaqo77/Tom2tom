"""Modèles de base. Voir 03_GUIDE_DEMARRAGE.md §B.3."""

import uuid

from django.db import models


class ModeleBase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.UUIDField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.UUIDField(null=True, blank=True)

    class Meta:
        abstract = True


class ModeleOrganisation(ModeleBase):
    """Tout modèle métier hérite de celui-ci. Sans exception.

    N'écrivez JAMAIS « WHERE org_id = ... » à la main : c'est la base
    qui s'en charge, par Row-Level Security. Un filtre écrit à la main
    est un filtre qu'on peut oublier.
    """

    org_id = models.UUIDField(db_index=True)

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """Journal d'audit en ajout seul, chaîné par empreinte.

    Les droits UPDATE et DELETE sont retirés au rôle applicatif par migration.
    """

    id = models.BigAutoField(primary_key=True)
    org_id = models.UUIDField(db_index=True)
    occurred_at = models.DateTimeField(auto_now_add=True)
    actor_id = models.UUIDField(null=True)
    actor_ip = models.GenericIPAddressField(null=True)
    action = models.CharField(max_length=32)
    object_type = models.CharField(max_length=64)
    object_id = models.UUIDField(null=True)
    project_id = models.UUIDField(null=True)
    before = models.JSONField(null=True)
    after = models.JSONField(null=True)
    prev_hash = models.BinaryField(null=True)
    hash = models.BinaryField()

    class Meta:
        db_table = "core_auditlog"
        indexes = [models.Index(fields=["org_id", "id"])]

    def __str__(self) -> str:
        return f"{self.occurred_at:%Y-%m-%d %H:%M} {self.action} {self.object_type}"
