"""Trésorerie : soldes de relevé, appariement des demandes, prévisions, justification des écarts.

Voir L9-T05. Les comptes bancaires et les mouvements de relevé existent depuis L3-T07 et L4-T04 ;
ce module ajoute ce qui manquait à la lecture de la trésorerie :

- le SOLDE DU RELEVÉ, enregistré (le solde d'ouverture n'était jusqu'ici qu'un paramètre) ;
- l'APPARIEMENT d'un mouvement d'encaissement à une demande de retrait, UNE SEULE FOIS ;
- les PRÉVISIONS par période et par axe, révisées sans jamais être écrasées ;
- la JUSTIFICATION explicite des écarts de l'état de reconstitution du compte désigné.
"""

from django.db import models
from django.db.models import Q

from core.fields import MontantField
from core.models import ModeleOrganisation
from niveau1_socle.decaissements.models import DemandeRetrait
from niveau1_socle.financements.models import CompteBancaire
from niveau1_socle.rapprochement.models import MouvementReleve
from niveau1_socle.referentiels.models import ValeurDimension


class SoldeReleve(ModeleOrganisation):
    """Le solde de clôture d'un jour, tel que le relevé de la banque le donne. Ajout seul."""

    compte = models.ForeignKey(CompteBancaire, on_delete=models.PROTECT, related_name="+")
    project_id = models.UUIDField(db_index=True)
    date_solde = models.DateField()
    solde = MontantField()  # devise du compte ; peut être négatif (découvert)
    reference = models.CharField(max_length=100, blank=True, default="")  # n° du relevé
    saisi_par = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["compte", "date_solde"], name="uq_soldereleve_jour"),
        ]


class AppariementDemande(ModeleOrganisation):
    """Un encaissement du relevé apparié à une demande de retrait. Voir L9-T05.

    UN mouvement n'est apparié qu'à UNE demande à la fois (index unique partiel sur les
    appariements actifs) : l'annuler (motivé) permet de le réapparier ailleurs.
    """

    mouvement = models.ForeignKey(MouvementReleve, on_delete=models.PROTECT, related_name="+")
    demande = models.ForeignKey(DemandeRetrait, on_delete=models.PROTECT, related_name="+")
    project_id = models.UUIDField(db_index=True)
    apparie_par = models.UUIDField()
    annule_at = models.DateTimeField(null=True, blank=True)
    annule_par = models.UUIDField(null=True, blank=True)
    motif_annulation = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["mouvement"],
                condition=Q(annule_at__isnull=True),
                name="uq_appariement_un_mouvement_une_demande",
            ),
            models.CheckConstraint(
                condition=(
                    Q(annule_at__isnull=True, annule_par__isnull=True, motif_annulation="")
                    | (
                        Q(annule_at__isnull=False, annule_par__isnull=False)
                        & ~Q(motif_annulation="")
                    )
                ),
                name="appariement_annulation_coherente",
            ),
        ]


class PrevisionTresorerie(ModeleOrganisation):
    """Une prévision d'encaissements et de décaissements, pour un mois et un axe. Ajout seul.

    On RÉVISE sans écraser : chaque révision (1, 2, 3…) est conservée, la courante est la plus
    haute. Un axe nul est la prévision « tous axes ».
    """

    project_id = models.UUIDField(db_index=True)
    devise = models.CharField(max_length=3)
    annee = models.PositiveSmallIntegerField()
    mois = models.PositiveSmallIntegerField()
    axe = models.ForeignKey(
        ValeurDimension, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    revision = models.PositiveSmallIntegerField()
    encaissements = MontantField(default=0)
    decaissements = MontantField(default=0)
    motif = models.TextField(blank=True, default="")  # pourquoi réviser (obligatoire dès la 2e)
    etablie_par = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project_id", "devise", "annee", "mois", "axe", "revision"],
                condition=Q(axe__isnull=False),
                name="uq_prevision_revision_axe",
            ),
            models.UniqueConstraint(
                fields=["project_id", "devise", "annee", "mois", "revision"],
                condition=Q(axe__isnull=True),
                name="uq_prevision_revision_sans_axe",
            ),
            models.CheckConstraint(condition=Q(mois__gte=1, mois__lte=12), name="prevision_mois"),
            models.CheckConstraint(condition=Q(revision__gte=1), name="prevision_revision"),
            models.CheckConstraint(
                condition=Q(encaissements__gte=0, decaissements__gte=0), name="prevision_positive"
            ),
            models.CheckConstraint(
                condition=Q(revision=1) | ~Q(motif=""), name="prevision_revision_motivee"
            ),
        ]


class CibleEcart(models.TextChoices):
    RELEVE = "releve", "Écart avec le solde du relevé"
    COMPTABLE = "comptable", "Écart avec le grand livre"


class JustificationEcart(ModeleOrganisation):
    """L'explication d'une partie de l'écart d'un état de reconstitution. Ajout seul.

    L'écart est « justifié » quand la somme (signée) des justifications égale exactement l'écart.
    """

    compte = models.ForeignKey(CompteBancaire, on_delete=models.PROTECT, related_name="+")
    project_id = models.UUIDField(db_index=True)
    date_debut = models.DateField()
    date_fin = models.DateField()
    cible = models.CharField(max_length=10, choices=CibleEcart.choices)
    montant = MontantField()  # signé, non nul : la part de l'écart que ce texte explique
    explication = models.TextField()
    saisie_par = models.UUIDField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(cible__in=CibleEcart.values), name="justifecart_cible_fermee"
            ),
            models.CheckConstraint(condition=~Q(montant=0), name="justifecart_montant_non_nul"),
            models.CheckConstraint(condition=~Q(explication=""), name="justifecart_expliquee"),
            models.CheckConstraint(
                condition=Q(date_fin__gte=models.F("date_debut")), name="justifecart_periode"
            ),
        ]
