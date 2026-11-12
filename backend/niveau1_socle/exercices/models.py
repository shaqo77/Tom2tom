"""Exercices et périodes d'un projet. Voir L1-T04 et architecture §3.3.

Un exercice porte douze périodes contiguës. Une période est `ouverte`, puis
`close` (clôturée par un service qui journalise la décision), puis
`verrouillee` : ce dernier état est définitif et garanti par la base.
Le contrôle « une période close refuse une écriture » est posé en L3-T03.

Les dates d'un exercice sont des dates calendaires, bornes incluses : du
1ᵉʳ janvier au 31 décembre. La convention semi-ouverte `[du, au[` du guide §B.6
vaut pour les VERSIONS de configuration, pas pour le calendrier comptable.
"""

from django.db import models
from django.db.models import Q

from core.models import ModeleOrganisation


class StatutExercice(models.TextChoices):
    OUVERT = "ouvert", "Ouvert"
    CLOS = "clos", "Clos"


class StatutPeriode(models.TextChoices):
    OUVERTE = "ouverte", "Ouverte"
    CLOSE = "close", "Close"
    VERROUILLEE = "verrouillee", "Verrouillée"


class Exercice(ModeleOrganisation):
    project_id = models.UUIDField(db_index=True)
    annee = models.PositiveIntegerField()  # année de début de l'exercice
    date_debut = models.DateField()
    date_fin = models.DateField()  # incluse
    status = models.CharField(
        max_length=8, choices=StatutExercice.choices, default=StatutExercice.OUVERT
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "project_id", "annee"], name="uq_exercice_annee"
            ),
            models.CheckConstraint(
                condition=Q(date_fin__gte=models.F("date_debut")),
                name="exercice_dates_coherentes",
            ),
            models.CheckConstraint(
                condition=Q(status__in=StatutExercice.values), name="exercice_statut_ferme"
            ),
        ]

    def __str__(self) -> str:
        return f"Exercice {self.annee}"


class Periode(ModeleOrganisation):
    exercice = models.ForeignKey(Exercice, on_delete=models.PROTECT, related_name="periodes")
    numero = models.PositiveSmallIntegerField()  # 1..12, rang dans l'exercice
    date_debut = models.DateField()
    date_fin = models.DateField()  # incluse
    status = models.CharField(
        max_length=11, choices=StatutPeriode.choices, default=StatutPeriode.OUVERTE
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["exercice", "numero"], name="uq_periode_numero"),
            models.CheckConstraint(
                condition=Q(numero__gte=1, numero__lte=12), name="periode_numero_1_12"
            ),
            models.CheckConstraint(
                condition=Q(date_fin__gte=models.F("date_debut")),
                name="periode_dates_coherentes",
            ),
            models.CheckConstraint(
                condition=Q(status__in=StatutPeriode.values), name="periode_statut_ferme"
            ),
        ]

    def __str__(self) -> str:
        return f"P{self.numero:02d} ({self.status})"
