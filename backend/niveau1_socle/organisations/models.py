"""Organisation (le locataire) et projet. Voir L1-T01 et architecture §3.2.

L'organisation est la frontière d'ISOLATION : la Row-Level Security la protège
(chaque organisation ne voit que sa propre fiche). Le projet est une frontière
d'HABILITATION : il porte `org_id` comme toute table métier, mais n'est pas
isolé par RLS (le tableau de bord multi-projets l'interdit ; lot L1-T05).
"""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q

from core.models import ModeleBase, ModeleOrganisation


class Organisation(ModeleBase):
    """L'entité juridique qui exploite la plateforme. Son `id` EST l'`org_id`."""

    code = models.CharField(max_length=32, unique=True)
    raison_sociale = models.CharField(max_length=255)
    pays = models.CharField(max_length=2)
    monnaie_tenue = models.CharField(max_length=3)
    langues_actives = models.JSONField(default=list)
    # Le validateur d'une pièce n'en est pas l'auteur. Activée par défaut (L1-T06).
    separation_des_taches = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(pays__regex=r"^[A-Z]{2}$"), name="organisation_pays_iso2"
            ),
            models.CheckConstraint(
                condition=Q(monnaie_tenue__regex=r"^[A-Z]{3}$"),
                name="organisation_monnaie_iso3",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class BaseComptable(models.TextChoices):
    ENCAISSEMENTS = "cash", "Comptabilité de caisse"
    ENGAGEMENTS = "accrual", "Comptabilité d'engagement"
    CAISSE_AVEC_ENGAGEMENTS = "cash_with_commitments", "Caisse avec engagements"


class StatutProjet(models.TextChoices):
    PREPARATION = "preparing", "En préparation"
    ACTIF = "active", "Actif"
    CLOTURE_EN_COURS = "closing", "En cours de clôture"
    CLOS = "closed", "Clos"


class Projet(ModeleOrganisation):
    code = models.CharField(max_length=32)
    label = models.JSONField()  # {"fr": …, "en": …, "ar": …}
    start_date = models.DateField(null=True, blank=True)
    closing_date = models.DateField(null=True, blank=True)
    last_disbursement_date = models.DateField(null=True, blank=True)
    # Code ISO 4217 en attendant le référentiel des devises (L2-T01).
    base_currency = models.CharField(max_length=3)
    accounting_basis = models.CharField(max_length=24, choices=BaseComptable.choices)
    status = models.CharField(
        max_length=16, choices=StatutProjet.choices, default=StatutProjet.PREPARATION
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org_id", "code"], name="uq_projet_code"),
            models.CheckConstraint(
                condition=Q(accounting_basis__in=BaseComptable.values),
                name="projet_base_comptable_fermee",
            ),
            models.CheckConstraint(
                condition=Q(status__in=StatutProjet.values), name="projet_statut_ferme"
            ),
            models.CheckConstraint(
                condition=Q(base_currency__regex=r"^[A-Z]{3}$"), name="projet_devise_iso3"
            ),
            # Dates calendaires contractuelles : bornes incluses.
            models.CheckConstraint(
                condition=Q(closing_date__isnull=True)
                | Q(start_date__isnull=True)
                | Q(closing_date__gte=models.F("start_date")),
                name="projet_dates_coherentes",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class Utilisateur(AbstractUser):
    """Compte utilisateur, rattaché à UNE organisation.

    Cette table est volontairement hors Row-Level Security : le login doit la
    lire avant que l'organisation de la requête soit connue. C'est l'unique
    exception à l'isolation par `org_id`, déclarée et verrouillée par
    `tests/test_isolation.py` (TABLES_SANS_ISOLATION). Un compte de plateforme
    (`org_id` nul) ne voit, lui, aucune donnée métier : sans périmètre, les
    politiques ne laissent rien passer.
    """

    # Clé UUID, comme created_by / actor_id partout ailleurs.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org_id = models.UUIDField(null=True, blank=True, db_index=True)

    def __str__(self) -> str:
        return self.username
