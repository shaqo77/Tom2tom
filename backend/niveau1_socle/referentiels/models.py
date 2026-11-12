"""Référentiels du socle : devises et taux (L2-T01).

Les devises sont un référentiel GÉNÉRAL (ISO 4217), commun à toutes les
organisations et administré hors de l'application : le rôle applicatif n'a que
la lecture. Les taux, eux, appartiennent à une organisation (taux de bailleur,
de budget…) et sont isolés par la RLS.
"""

from django.db import models
from django.db.models import Q

from core.fields import TauxField
from core.models import ModeleOrganisation


class Devise(models.Model):
    code = models.CharField(max_length=3, primary_key=True)  # ISO 4217
    label = models.JSONField()  # {"fr": …, "en": …}
    decimales = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(code__regex=r"^[A-Z]{3}$"), name="devise_code_iso3"),
            models.CheckConstraint(condition=Q(decimales__lte=4), name="devise_decimales_bornees"),
        ]

    def __str__(self) -> str:
        return self.code


class TypeTaux(models.TextChoices):
    OFFICIEL = "officiel", "Taux officiel"
    BAILLEUR = "bailleur", "Taux du bailleur"
    CLOTURE = "cloture", "Taux de clôture"
    BUDGET = "budget", "Taux budgétaire"


class Taux(ModeleOrganisation):
    """Unités de monnaie de tenue de l'organisation pour une unité de `devise`.

    Un taux n'est jamais écrasé : un nouveau taux est une nouvelle ligne.
    L'immuabilité est garantie par déclencheur, même en SQL direct.
    """

    devise = models.ForeignKey(Devise, on_delete=models.PROTECT, related_name="taux")
    date = models.DateField()
    taux = TauxField()
    type_taux = models.CharField(max_length=16, choices=TypeTaux.choices)
    source = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "devise", "date", "type_taux"], name="uq_taux_jour_type"
            ),
            models.CheckConstraint(condition=Q(taux__gt=0), name="taux_strictement_positif"),
            models.CheckConstraint(
                condition=Q(type_taux__in=TypeTaux.values), name="taux_type_ferme"
            ),
        ]
        indexes = [models.Index(fields=["org_id", "devise", "type_taux", "-date"])]


class SensNormal(models.TextChoices):
    DEBIT = "debit", "Débit"
    CREDIT = "credit", "Crédit"


class Compte(ModeleOrganisation):
    """Compte du plan comptable d'une organisation. Voir L2-T02.

    Hiérarchie : un compte imputable est une FEUILLE. Un total (non imputable) a
    des enfants ; un compte qui a des enfants ne devient pas imputable. La base
    le garantit par déclencheur.
    """

    code = models.CharField(max_length=20)
    label = models.JSONField()  # {"fr": …, "en": …, "ar": …}
    classe = models.PositiveSmallIntegerField()  # premier chiffre du code
    sens_normal = models.CharField(max_length=6, choices=SensNormal.choices)
    imputable = models.BooleanField(default=True)
    actif = models.BooleanField(default=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="enfants"
    )
    paquet_id = models.UUIDField(null=True, blank=True)  # paquet réglementaire d'origine (L2-T05)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org_id", "code"], name="uq_compte_code"),
            models.CheckConstraint(
                condition=Q(code__regex=r"^[1-9][0-9]*$"), name="compte_code_numerique"
            ),
            models.CheckConstraint(
                condition=Q(classe__gte=1, classe__lte=9), name="compte_classe_1_9"
            ),
            models.CheckConstraint(
                condition=Q(sens_normal__in=SensNormal.values), name="compte_sens_ferme"
            ),
            models.CheckConstraint(
                condition=Q(parent__isnull=True) | ~Q(parent=models.F("id")),
                name="compte_pas_son_propre_parent",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class TypeAxe(models.TextChoices):
    GESTION = "gestion", "Axe de gestion"
    AUXILIAIRE = "auxiliaire", "Axe auxiliaire"


class PlanDimension(ModeleOrganisation):
    """Plan d'axe : relie un EMPLACEMENT fixe (1 à 4) au plan métier que l'organisation y place.

    Un modèle clé-valeur serait plus souple mais interdirait l'indexation efficace
    et les contraintes d'intégrité, alors que chaque état agrège sur ces colonnes.
    """

    kind = models.CharField(max_length=10, choices=TypeAxe.choices)
    slot = models.PositiveSmallIntegerField()
    code = models.CharField(max_length=32)
    label = models.JSONField()
    is_mandatory = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "kind", "slot"], name="uq_plandimension_emplacement"
            ),
            models.UniqueConstraint(fields=["org_id", "code"], name="uq_plandimension_code"),
            models.CheckConstraint(
                condition=Q(slot__gte=1, slot__lte=4), name="plandimension_slot"
            ),
            models.CheckConstraint(
                condition=Q(kind__in=TypeAxe.values), name="plandimension_type_ferme"
            ),
        ]

    def __str__(self) -> str:
        return self.code


class ValeurDimension(ModeleOrganisation):
    """Valeur d'un plan d'axe, hiérarchique (composante > activité > tâche).

    Seules les feuilles s'imputent ; un déclencheur le garantit en base.
    """

    plan = models.ForeignKey(PlanDimension, on_delete=models.PROTECT, related_name="valeurs")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="enfants"
    )
    code = models.CharField(max_length=20)
    label = models.JSONField()
    is_postable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "plan", "code"], name="uq_valeurdimension_code"
            ),
            models.CheckConstraint(
                condition=Q(parent__isnull=True) | ~Q(parent=models.F("id")),
                name="valeurdimension_pas_son_propre_parent",
            ),
        ]

    def __str__(self) -> str:
        return self.code
