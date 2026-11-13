"""Rapprochement bancaire. Voir L3-T07 (partie b).

Un MOUVEMENT DE RELEVÉ est une ligne du relevé de la banque, dans la devise du compte (positif :
encaissement, qui est un débit au grand livre). Rapprocher, c'est apparier des lignes
comptabilisées du compte et des mouvements du relevé, EN DEVISE ET EN MONNAIE DE TENUE. S'il reste
une différence de valorisation en monnaie de tenue, elle devient une ÉCRITURE EXPLICITE d'écart de
change, qui entre dans le groupe.

Comme le lettrage : rapprocher ne modifie aucune ligne comptabilisée, seul le marqueur
`bank_match_id` change ; un rapprochement ne se supprime pas, il s'annule (motif, auteur, date) ;
son code n'est jamais réutilisé.
"""

from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.fields import MontantField, TauxField
from core.models import ModeleOrganisation
from niveau1_socle.comptabilite.models import Ecriture
from niveau1_socle.financements.models import CompteBancaire


class StatutRapprochement(models.TextChoices):
    ACTIF = "actif", "Actif"
    ANNULE = "annule", "Annulé"


class Rapprochement(ModeleOrganisation):
    project_id = models.UUIDField(db_index=True)
    compte = models.ForeignKey(CompteBancaire, on_delete=models.PROTECT, related_name="+")
    code = models.CharField(max_length=12)
    status = models.CharField(
        max_length=6, choices=StatutRapprochement.choices, default=StatutRapprochement.ACTIF
    )
    rapproche_at = models.DateTimeField(default=timezone.now)
    rapproche_by = models.UUIDField(null=True, blank=True)
    # Différence de valorisation en monnaie de tenue (relevé − grand livre), et son écriture.
    ecart_change = MontantField(default=0)
    ecriture_ecart = models.ForeignKey(
        Ecriture, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    ecriture_ecart_annulation = models.ForeignKey(
        Ecriture, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    annule_at = models.DateTimeField(null=True, blank=True)
    annule_by = models.UUIDField(null=True, blank=True)
    motif_annulation = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "compte", "code"], name="uq_rapprochement_code"
            ),
            models.CheckConstraint(
                condition=Q(status__in=StatutRapprochement.values),
                name="rapprochement_statut_ferme",
            ),
            # `isnull` explicite : un CHECK laisse passer NULL (voir L3-T06).
            models.CheckConstraint(
                condition=(
                    Q(status=StatutRapprochement.ACTIF, annule_at__isnull=True)
                    | (
                        Q(status=StatutRapprochement.ANNULE, annule_at__isnull=False)
                        & ~Q(motif_annulation="")
                    )
                ),
                name="rapprochement_annulation_coherente",
            ),
            # Un écart de change non nul a son écriture ; un écart nul n'en a pas.
            models.CheckConstraint(
                condition=(
                    Q(ecart_change=0, ecriture_ecart__isnull=True)
                    | (~Q(ecart_change=0) & Q(ecriture_ecart__isnull=False))
                ),
                name="rapprochement_ecart_a_son_ecriture",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.compte.code}/{self.code}"


class MouvementReleve(ModeleOrganisation):
    project_id = models.UUIDField(db_index=True)
    compte = models.ForeignKey(CompteBancaire, on_delete=models.PROTECT, related_name="mouvements")
    reference = models.CharField(max_length=100)  # référence de la banque : rejouer n'ajoute rien
    date_operation = models.DateField()
    libelle = models.CharField(max_length=255, blank=True, default="")
    montant = MontantField()  # devise du compte ; positif = encaissement
    taux = TauxField(default=1)  # vers la monnaie de tenue, le jour de l'opération
    montant_base = MontantField()  # montant × taux, arrondi à la monnaie de tenue
    rapprochement = models.ForeignKey(  # marqueur : seul champ qui change après l'import
        Rapprochement, null=True, blank=True, on_delete=models.PROTECT, related_name="mouvements"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "compte", "reference"], name="uq_mouvement_reference"
            ),
            models.CheckConstraint(condition=~Q(montant=0), name="mouvement_montant_non_nul"),
            models.CheckConstraint(condition=Q(taux__gt=0), name="mouvement_taux_positif"),
        ]

    def __str__(self) -> str:
        return f"{self.compte.code} {self.reference} {self.montant}"
