"""Grand livre : journaux, écritures et lignes. Voir L3-T01 et architecture §3.3.

Les statuts gardent leurs codes d'origine (`draft`, `validated`, `posted`, `locked`) :
les déclencheurs de L3-T02 à L3-T05 les citent. Les objets qui n'existent qu'aux lots
suivants (site, accord, catégorie, marché, compte bancaire, clé de cofinancement)
sont des UUID sans clé étrangère pour l'instant ; L4 et L9 y poseront leurs clés.
"""

from django.db import models
from django.db.models import Q

from core.fields import MontantField, TauxField
from core.models import ModeleOrganisation
from niveau1_socle.exercices.models import Exercice, Periode
from niveau1_socle.referentiels.models import Compte, Devise, Tiers, ValeurDimension


class Journal(ModeleOrganisation):
    code = models.CharField(max_length=20)
    label = models.JSONField()  # {"fr": …, "en": …}
    actif = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org_id", "code"], name="uq_journal_code"),
        ]

    def __str__(self) -> str:
        return self.code


class StatutEcriture(models.TextChoices):
    BROUILLON = "draft", "Brouillon"
    VALIDEE = "validated", "Validée"
    COMPTABILISEE = "posted", "Comptabilisée"
    VERROUILLEE = "locked", "Verrouillée"


class OrigineEcriture(models.TextChoices):
    SAISIE = "saisie", "Saisie"
    IMPORT = "import", "Import"
    HORS_LIGNE = "offline", "Capture hors ligne"
    CONTREPASSATION = "reversal", "Contre-passation"
    MODULE = "module", "Module métier"


class Ecriture(ModeleOrganisation):
    """Une pièce comptable. Le numéro n'est attribué qu'à la comptabilisation."""

    project_id = models.UUIDField(db_index=True)
    exercice = models.ForeignKey(Exercice, on_delete=models.PROTECT, related_name="ecritures")
    periode = models.ForeignKey(Periode, on_delete=models.PROTECT, related_name="ecritures")
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, related_name="ecritures")
    number = models.CharField(max_length=40, null=True, blank=True)
    accounting_date = models.DateField()
    document_date = models.DateField(null=True, blank=True)
    document_ref = models.CharField(max_length=100, blank=True, default="")
    label = models.CharField(max_length=255)
    status = models.CharField(
        max_length=9, choices=StatutEcriture.choices, default=StatutEcriture.BROUILLON
    )
    currency = models.ForeignKey(Devise, on_delete=models.PROTECT, related_name="+")
    fx_rate = TauxField(default=1)
    origin = models.CharField(max_length=8, choices=OrigineEcriture.choices)
    origin_module = models.CharField(max_length=32, null=True, blank=True)
    origin_ref = models.UUIDField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=100, null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.UUIDField(null=True, blank=True)
    reverses = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="contrepassations"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "journal", "exercice", "number"], name="uq_ecriture_numero"
            ),
            models.UniqueConstraint(
                fields=["org_id", "idempotency_key"], name="uq_ecriture_idempotence"
            ),
            models.CheckConstraint(
                condition=Q(status__in=StatutEcriture.values), name="ecriture_statut_ferme"
            ),
            models.CheckConstraint(
                condition=Q(origin__in=OrigineEcriture.values), name="ecriture_origine_fermee"
            ),
            # Comptabilisée ou verrouillée : numérotée, horodatée, attribuée à quelqu'un.
            models.CheckConstraint(
                condition=Q(status__in=[StatutEcriture.BROUILLON, StatutEcriture.VALIDEE])
                | Q(number__isnull=False, posted_at__isnull=False, posted_by__isnull=False),
                name="ecriture_comptabilisee_numerotee",
            ),
            # Réciproque : avant la comptabilisation, pas de numéro (L3-T04). Il est attribué
            # par la base, jamais choisi par l'appelant.
            models.CheckConstraint(
                condition=Q(number__isnull=True)
                | Q(status__in=[StatutEcriture.COMPTABILISEE, StatutEcriture.VERROUILLEE]),
                name="ecriture_numero_a_la_comptabilisation",
            ),
            models.CheckConstraint(
                condition=Q(reverses__isnull=True) | ~Q(reverses=models.F("id")),
                name="ecriture_ne_se_contrepasse_pas",
            ),
        ]
        indexes = [models.Index(fields=["org_id", "project_id", "periode"])]

    def __str__(self) -> str:
        return self.number or f"brouillon {self.pk}"


class LigneEcriture(ModeleOrganisation):
    """Une ligne d'écriture : un compte, un sens, des axes d'analyse."""

    project_id = models.UUIDField(db_index=True)
    entry = models.ForeignKey(Ecriture, on_delete=models.CASCADE, related_name="lignes")
    line_no = models.PositiveSmallIntegerField()
    account = models.ForeignKey(Compte, on_delete=models.PROTECT, related_name="+")
    partner = models.ForeignKey(
        Tiers, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    # Axes de gestion et axes auxiliaires : quatre emplacements fixes chacun.
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
    aux1 = models.ForeignKey(
        ValeurDimension, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    aux2 = models.ForeignKey(
        ValeurDimension, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    aux3 = models.ForeignKey(
        ValeurDimension, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    aux4 = models.ForeignKey(
        ValeurDimension, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    # Objets des lots suivants : UUID sans clé étrangère jusqu'à leur création.
    site_id = models.UUIDField(null=True, blank=True)
    agreement_id = models.UUIDField(null=True, blank=True)  # accord (L4-T04)
    category_id = models.UUIDField(null=True, blank=True)  # catégorie (L4-T04)
    contract_id = models.UUIDField(null=True, blank=True)  # marché (L9)
    bank_account_id = models.UUIDField(null=True, blank=True)
    cofunding_key_version_id = models.UUIDField(null=True, blank=True)  # L4-T05

    # Monnaie de tenue, puis devise d'origine.
    debit = MontantField(default=0)
    credit = MontantField(default=0)
    currency = models.ForeignKey(Devise, on_delete=models.PROTECT, related_name="+")
    fx_rate = TauxField(default=1)
    debit_cur = MontantField(default=0)
    credit_cur = MontantField(default=0)

    reconciliation_id = models.UUIDField(null=True, blank=True)  # lettrage (L3-T07)
    bank_match_id = models.UUIDField(null=True, blank=True)
    label = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entry", "line_no"], name="uq_ligne_numero"),
            models.CheckConstraint(condition=Q(line_no__gte=1), name="ligne_numero_positif"),
            models.CheckConstraint(
                condition=Q(debit__gte=0, credit__gte=0), name="ligne_montants_positifs"
            ),
            models.CheckConstraint(condition=Q(debit=0) | Q(credit=0), name="ligne_un_seul_sens"),
        ]
        indexes = [models.Index(fields=["org_id", "project_id", "account"])]


class Compteur(ModeleOrganisation):
    """Dernier numéro attribué, par journal et par exercice. Voir L3-T04.

    Il n'est jamais écrit par l'application : seul le déclencheur de comptabilisation
    l'incrémente, dans la transaction de la comptabilisation. Annuler la transaction annule
    le numéro, ce qu'une séquence PostgreSQL ne fait pas.
    """

    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, related_name="+")
    exercice = models.ForeignKey(Exercice, on_delete=models.PROTECT, related_name="+")
    dernier = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "journal", "exercice"], name="uq_compteur_journal_exercice"
            ),
            models.CheckConstraint(condition=Q(dernier__gte=1), name="compteur_positif"),
        ]
