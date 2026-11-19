"""Budgets et versions. Voir L4-T01.

Une version de budget est un INSTANTANÉ COMPLET : ses lignes disent tout le budget, pas un écart
par rapport à la version précédente. Une révision ou une réallocation crée donc une nouvelle version
qui reprend les lignes de l'ancienne, modifiées ; l'ancienne reste consultable, intacte.
Une version approuvée est immuable (la base le garantit).
"""

from django.db import models
from django.db.models import Q

from core.fields import MontantField, TauxField
from core.models import ModeleOrganisation
from niveau1_socle.referentiels.models import Devise, ValeurDimension


class TypeVersion(models.TextChoices):
    INITIAL = "initial", "Budget initial"
    REVISION = "revision", "Révision"
    REALLOCATION = "reallocation", "Réallocation"


class StatutVersion(models.TextChoices):
    BROUILLON = "brouillon", "Brouillon"
    APPROUVE = "approuve", "Approuvé"
    CLOS = "clos", "Clos (remplacé)"


class VersionBudget(ModeleOrganisation):
    project_id = models.UUIDField(db_index=True)
    numero = models.PositiveIntegerField()  # rang dans le projet, sans trou
    type = models.CharField(max_length=12, choices=TypeVersion.choices)
    status = models.CharField(
        max_length=9, choices=StatutVersion.choices, default=StatutVersion.BROUILLON
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )  # la version que celle-ci révise
    motif = models.TextField(blank=True, default="")  # obligatoire hors budget initial
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.UUIDField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "project_id", "numero"], name="uq_versionbudget_numero"
            ),
            # Un seul budget initial par projet ; une seule version approuvée « courante ».
            models.UniqueConstraint(
                fields=["project_id"],
                condition=Q(type=TypeVersion.INITIAL),
                name="uq_versionbudget_un_initial",
            ),
            models.UniqueConstraint(
                fields=["project_id"],
                condition=Q(status=StatutVersion.APPROUVE),
                name="uq_versionbudget_une_courante",
            ),
            # Une seule version en préparation à la fois : deux brouillons partis de la même version
            # courante se contrediraient à l'approbation.
            models.UniqueConstraint(
                fields=["project_id"],
                condition=Q(status=StatutVersion.BROUILLON),
                name="uq_versionbudget_un_brouillon",
            ),
            models.CheckConstraint(
                condition=Q(type__in=TypeVersion.values), name="versionbudget_type_ferme"
            ),
            models.CheckConstraint(
                condition=Q(status__in=StatutVersion.values), name="versionbudget_statut_ferme"
            ),
            # `isnull` explicite : un CHECK laisse passer NULL (voir L3-T06).
            models.CheckConstraint(
                condition=(
                    Q(type=TypeVersion.INITIAL, parent__isnull=True)
                    | (~Q(type=TypeVersion.INITIAL) & Q(parent__isnull=False))
                ),
                name="versionbudget_parent_coherent",
            ),
            models.CheckConstraint(
                condition=Q(type=TypeVersion.INITIAL) | ~Q(motif=""),
                name="versionbudget_motif_obligatoire",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=StatutVersion.BROUILLON, approved_at__isnull=True)
                    | (
                        ~Q(status=StatutVersion.BROUILLON)
                        & Q(approved_at__isnull=False)
                        & Q(approved_by__isnull=False)
                    )
                ),
                name="versionbudget_approbation_coherente",
            ),
        ]

    def __str__(self) -> str:
        return f"Budget v{self.numero} ({self.type}, {self.status})"


class LigneBudget(ModeleOrganisation):
    """Un montant sur une combinaison d'axes, pour une année ou une période."""

    version = models.ForeignKey(VersionBudget, on_delete=models.CASCADE, related_name="lignes")
    annee = models.PositiveSmallIntegerField()
    periode = models.PositiveSmallIntegerField(null=True, blank=True)  # 1..12 ; nul = année entière

    dim1 = models.ForeignKey(
        ValeurDimension, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    dim2 = models.ForeignKey(
        ValeurDimension, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    dim3 = models.ForeignKey(
        ValeurDimension, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    dim4 = models.ForeignKey(
        ValeurDimension, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    agreement_id = models.UUIDField(null=True, blank=True)  # accord (L4-T04)
    category_id = models.UUIDField(null=True, blank=True)  # catégorie (L4-T04)
    site_id = models.UUIDField(null=True, blank=True)

    montant = MontantField()  # dans la devise du budget
    devise = models.ForeignKey(Devise, on_delete=models.PROTECT, related_name="+")
    taux_budget = TauxField(default=1)  # distinct du taux comptable (spécification §3.4)
    montant_base = MontantField()  # en monnaie de tenue du projet : montant × taux, arrondi

    class Meta:
        constraints = [
            # Une combinaison n'apparaît qu'une fois par version (NULL compte comme une valeur).
            models.UniqueConstraint(
                fields=[
                    "version",
                    "annee",
                    "periode",
                    "dim1",
                    "dim2",
                    "dim3",
                    "dim4",
                    "agreement_id",
                    "category_id",
                    "site_id",
                ],
                nulls_distinct=False,
                name="uq_lignebudget_combinaison",
            ),
            models.CheckConstraint(condition=Q(montant__gte=0), name="lignebudget_montant_positif"),
            models.CheckConstraint(
                condition=Q(montant_base__gte=0), name="lignebudget_montant_base_positif"
            ),
            models.CheckConstraint(condition=Q(taux_budget__gt=0), name="lignebudget_taux_positif"),
            models.CheckConstraint(
                condition=Q(periode__isnull=True) | Q(periode__gte=1, periode__lte=12),
                name="lignebudget_periode_bornee",
            ),
            models.CheckConstraint(
                condition=Q(annee__gte=1900, annee__lte=2200), name="lignebudget_annee_bornee"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.annee}/{self.periode or 'A'} {self.montant}"


class StatutEngagement(models.TextChoices):
    OUVERT = "ouvert", "Ouvert"
    SOLDE = "solde", "Soldé (entièrement apuré)"
    ANNULE = "annule", "Annulé"


class Engagement(ModeleOrganisation):
    """Une réservation de budget : une dépense décidée, pas encore comptabilisée. Voir L4-T02.

    Le rattachement à un marché soumis à avis de non-objection est posé en L9-T02 ; l'apurement
    par les décomptes arrive avec L9-T04. Montants en monnaie de tenue du projet. Le montant non
    apuré (`montant - apure`, tant que l'engagement est ouvert) réduit le disponible budgétaire.
    """

    project_id = models.UUIDField(db_index=True)
    reference = models.CharField(max_length=60)
    libelle = models.CharField(max_length=255, blank=True, default="")
    annee = models.PositiveSmallIntegerField()
    periode = models.PositiveSmallIntegerField(null=True, blank=True)  # 1..12 ; nul = année entière
    dim1 = models.ForeignKey(
        ValeurDimension, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    dim2 = models.ForeignKey(
        ValeurDimension, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    dim3 = models.ForeignKey(
        ValeurDimension, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    dim4 = models.ForeignKey(
        ValeurDimension, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    agreement_id = models.UUIDField(null=True, blank=True)
    category_id = models.UUIDField(null=True, blank=True)
    site_id = models.UUIDField(null=True, blank=True)
    # Le marché prévu au plan que cet engagement réserve (L9-T02) ; nul = engagement sans marché.
    ligne_passation = models.ForeignKey(
        "marches.LignePassation",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="engagements",
    )
    montant = MontantField()
    apure = MontantField(default=0)
    status = models.CharField(
        max_length=6, choices=StatutEngagement.choices, default=StatutEngagement.OUVERT
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "project_id", "reference"], name="uq_engagement_reference"
            ),
            models.CheckConstraint(condition=Q(montant__gt=0), name="engagement_montant_positif"),
            models.CheckConstraint(
                condition=Q(apure__gte=0, apure__lte=models.F("montant")),
                name="engagement_apure_borne",
            ),
            models.CheckConstraint(
                condition=Q(status__in=StatutEngagement.values), name="engagement_statut_ferme"
            ),
            models.CheckConstraint(
                condition=~Q(status=StatutEngagement.SOLDE) | Q(apure=models.F("montant")),
                name="engagement_solde_coherent",
            ),
            models.CheckConstraint(
                condition=Q(periode__isnull=True) | Q(periode__gte=1, periode__lte=12),
                name="engagement_periode_bornee",
            ),
        ]

    @property
    def non_apure(self):
        return self.montant - self.apure if self.status == StatutEngagement.OUVERT else 0

    def __str__(self) -> str:
        return f"{self.reference} ({self.status})"


class SoldeBudgetaire(ModeleOrganisation):
    """Le consommé et l'engagé d'une ligne de la version approuvée courante. Voir L4-T02.

    Maintenu PAR LA BASE, dans la transaction de ce qui le fait bouger (comptabilisation d'une
    écriture, création ou apurement d'un engagement). `recalculer_soldes` le reconstruit depuis
    les écritures et les engagements, et `verifier_soldes` compare les deux : un solde
    pré-agrégé qui dérive en silence serait pire que pas de solde du tout.

    disponible = montant_base de la ligne − engagé (non apuré) − consommé (comptabilisé)
    """

    project_id = models.UUIDField(db_index=True)
    version = models.ForeignKey(VersionBudget, on_delete=models.PROTECT, related_name="+")
    ligne = models.OneToOneField(LigneBudget, on_delete=models.PROTECT, related_name="solde")
    consomme = MontantField(default=0)
    engage = MontantField(default=0)

    @property
    def disponible(self):
        return self.ligne.montant_base - self.engage - self.consomme


class ModeControle(models.TextChoices):
    BLOQUANT = "bloquant", "Bloquant"
    AVERTISSEMENT = "avertissement", "Avertissement"
    INACTIF = "inactif", "Inactif"


# Axes sur lesquels un mode se paramètre ; « projet » vaut pour une ligne de budget sans axe.
AXES_CONTROLE = ("projet", "dim1", "dim2", "dim3", "dim4", "agreement", "category", "site")


class ControleBudgetaire(ModeleOrganisation):
    """Le mode de contrôle du disponible pour un axe d'un projet. Voir L4-T03.

    Versionné comme toute configuration (guide B.6) : validité `[valid_from, valid_to[`, sans
    chevauchement pour un même projet et un même axe. Changer de mode, c'est clore la version
    en cours et en ouvrir une autre : les décisions passées restent explicables.
    """

    project_id = models.UUIDField(db_index=True)
    axe = models.CharField(max_length=10)
    mode = models.CharField(max_length=13, choices=ModeControle.choices)
    version = models.PositiveIntegerField()
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)  # exclu
    motif = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "project_id", "axe", "version"], name="uq_controlebudget_version"
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gt=models.F("valid_from")),
                name="controlebudget_dates_coherentes",
            ),
            models.CheckConstraint(
                condition=Q(mode__in=ModeControle.values), name="controlebudget_mode_ferme"
            ),
            models.CheckConstraint(
                condition=Q(axe__in=AXES_CONTROLE), name="controlebudget_axe_ferme"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.axe}: {self.mode} v{self.version}"
