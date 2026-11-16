"""La demande d'export complet d'une organisation. Voir L8-T03.

L'export se DEMANDE (interface), se PRODUIT en tâche de fond, puis se TÉLÉCHARGE par un lien signé à
durée limitée. L'archive produite est stockée avec son empreinte ; une fois prête, la ligne ne
change plus.
"""

from django.db import models
from django.db.models import Q

from core.models import ModeleOrganisation


class StatutExport(models.TextChoices):
    DEMANDE = "demande", "Demandé"
    EN_COURS = "en_cours", "En cours de production"
    PRET = "pret", "Prêt"
    ECHEC = "echec", "En échec"


class ExportOrganisation(ModeleOrganisation):
    demandeur_id = models.UUIDField()
    statut = models.CharField(
        max_length=9, choices=StatutExport.choices, default=StatutExport.DEMANDE
    )
    produit_le = models.DateTimeField(null=True, blank=True)
    file_ref = models.CharField(max_length=512, blank=True, default="")
    sha256 = models.CharField(max_length=64, blank=True, default="")
    taille = models.PositiveBigIntegerField(null=True, blank=True)
    nombre_tables = models.PositiveIntegerField(null=True, blank=True)
    erreur = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(statut__in=StatutExport.values), name="export_statut_ferme"
            ),
            # Prêt : l'archive existe et son empreinte est connue ; sinon, rien de tout cela.
            models.CheckConstraint(
                condition=~Q(statut="pret")
                | (~Q(file_ref="") & ~Q(sha256="") & Q(taille__isnull=False)),
                name="export_pret_complet",
            ),
        ]
