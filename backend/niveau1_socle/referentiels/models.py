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
