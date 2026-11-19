"""Suivi des avances. Voir L4-T07.

Une avance est une somme versée à un tiers (agent, prestataire…) avant la dépense qu'elle finance.
Elle se JUSTIFIE ensuite, par des dépenses prouvées ou par un remboursement. Tant qu'elle n'est pas
entièrement justifiée à l'échéance (date de versement + délai applicable), elle est « non justifiée
au-delà du délai » : c'est ce que le lot L6 contrôle.

Rien ne dérive : l'avance et ses justifications sont en ajout seul ; le reste à justifier se CALCULE
(`montant - Σ justifications`), il n'est stocké nulle part.
"""

from django.db import models
from django.db.models import Q

from core.fields import MontantField
from core.models import ModeleOrganisation
from niveau1_socle.referentiels.models import Tiers


class DelaiAvance(ModeleOrganisation):
    """Le délai de justification d'un projet, en jours. Versionné (`[valid_from, valid_to[`, sans
    chevauchement) : une avance garde le délai en vigueur le jour de son versement."""

    project_id = models.UUIDField(db_index=True)
    jours = models.PositiveIntegerField()
    version = models.PositiveIntegerField()
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)  # exclu
    motif = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "project_id", "version"], name="uq_delaiavance_version"
            ),
            models.CheckConstraint(condition=Q(jours__gt=0), name="delaiavance_jours_positifs"),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gt=models.F("valid_from")),
                name="delaiavance_dates_coherentes",
            ),
        ]


class Avance(ModeleOrganisation):
    project_id = models.UUIDField(db_index=True)
    tiers = models.ForeignKey(Tiers, on_delete=models.PROTECT, related_name="+")
    reference = models.CharField(max_length=60)
    libelle = models.CharField(max_length=255, blank=True, default="")
    montant = MontantField()  # monnaie de tenue du projet
    date_versement = models.DateField()
    delai_jours = models.PositiveIntegerField()  # figé au versement
    ligne_ecriture_id = models.UUIDField(null=True, blank=True)  # la ligne comptable du versement

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "project_id", "reference"], name="uq_avance_reference"
            ),
            models.CheckConstraint(condition=Q(montant__gt=0), name="avance_montant_positif"),
            models.CheckConstraint(condition=Q(delai_jours__gt=0), name="avance_delai_positif"),
        ]

    def __str__(self) -> str:
        return self.reference


class TypeJustification(models.TextChoices):
    DEPENSE = "depense", "Dépense justifiée"
    REMBOURSEMENT = "remboursement", "Remboursement de l'excédent"


class JustificationAvance(ModeleOrganisation):
    avance = models.ForeignKey(Avance, on_delete=models.PROTECT, related_name="justifications")
    type = models.CharField(max_length=13, choices=TypeJustification.choices)
    montant = MontantField()
    date_justification = models.DateField()
    reference = models.CharField(max_length=100, blank=True, default="")  # pièce justificative
    ligne_ecriture_id = models.UUIDField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(montant__gt=0), name="justificationavance_montant_positif"
            ),
            models.CheckConstraint(
                condition=Q(type__in=TypeJustification.values),
                name="justificationavance_type_ferme",
            ),
        ]
