"""Grand livre : journaux, écritures et lignes. Voir L3-T01 et architecture §3.3.

Les statuts gardent leurs codes d'origine (`draft`, `validated`, `posted`, `locked`) :
les déclencheurs de L3-T02 à L3-T05 les citent. Les objets qui n'existent qu'aux lots
suivants (site, accord, catégorie, marché, compte bancaire, clé de cofinancement)
sont des UUID sans clé étrangère pour l'instant ; L4 et L9 y poseront leurs clés.
"""

from django.db import models
from django.db.models import Q
from django.utils import timezone

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
    # La version de schéma qui a alimenté la saisie : un schéma utilisé ne change plus (L3-T06).
    schema = models.ForeignKey(
        "SchemaEcriture",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ecritures",
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
            # Une écriture ne se contre-passe qu'une fois (L3-T05b).
            models.UniqueConstraint(
                fields=["reverses"],
                condition=Q(reverses__isnull=False),
                name="uq_ecriture_une_contrepassation",
            ),
            # `origin = reversal` et `reverses` vont ensemble, dans les deux sens.
            models.CheckConstraint(
                condition=(Q(origin=OrigineEcriture.CONTREPASSATION) & Q(reverses__isnull=False))
                | (~Q(origin=OrigineEcriture.CONTREPASSATION) & Q(reverses__isnull=True)),
                name="ecriture_contrepassation_coherente",
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
    # La version de clé de cofinancement qui a produit la ligne (L4-T05) : sans elle, modifier la
    # clé plus tard rendrait l'historique inexplicable. Clé étrangère posée en SQL (financements).
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


class SchemaEcriture(ModeleOrganisation):
    """Une pièce type (achat avec TVA, recette…), versionnée comme toute configuration (B.6).

    Validité `[valid_from, valid_to[`, sans chevauchement pour un même code. Une version utilisée
    par au moins une écriture ne se modifie plus : on en crée une nouvelle.
    """

    code = models.CharField(max_length=32)
    version = models.PositiveIntegerField()
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)  # exclu
    label = models.JSONField()
    journal = models.ForeignKey(
        Journal, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org_id", "code", "version"], name="uq_schema_version"),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gt=models.F("valid_from")),
                name="schema_dates_coherentes",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} v{self.version}"


class RegleSchema(models.TextChoices):
    BASE = "base", "Montant saisi"
    TAUX = "taux", "Montant × taux"
    SOLDE = "solde", "Contrepartie automatique"


class LigneSchema(ModeleOrganisation):
    """Une ligne de schéma : un compte, un sens, une règle de calcul d'un ensemble fermé."""

    schema = models.ForeignKey(SchemaEcriture, on_delete=models.CASCADE, related_name="lignes")
    rang = models.PositiveSmallIntegerField()
    compte = models.ForeignKey(Compte, on_delete=models.PROTECT, related_name="+")
    sens = models.CharField(max_length=6, null=True, blank=True)  # nul pour la contrepartie
    regle = models.CharField(max_length=16, choices=RegleSchema.choices)
    # Un taux (0,18 pour 18 %) n'est pas un montant : précision propre, jamais de flottant.
    taux = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    axes = models.JSONField(default=dict, blank=True)  # {"dim1": "COMP-A"} : axes par défaut

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["schema", "rang"], name="uq_ligneschema_rang"),
            models.CheckConstraint(condition=Q(rang__gte=1), name="ligneschema_rang_positif"),
            models.CheckConstraint(
                condition=Q(regle__in=RegleSchema.values), name="ligneschema_regle_fermee"
            ),
            # La forme de chaque règle : la contrepartie déduit son sens et n'a pas de taux ;
            # la base a un sens et pas de taux ; la règle taux a un sens et un taux > 0.
            models.CheckConstraint(
                # `isnull=False` est explicite : en SQL, `taux > 0` ou `sens IN (…)` sur NULL vaut
                # NULL, et un CHECK laisse passer NULL.
                condition=(
                    Q(regle=RegleSchema.SOLDE, sens__isnull=True, taux__isnull=True)
                    | Q(
                        regle=RegleSchema.BASE,
                        sens__isnull=False,
                        sens__in=["debit", "credit"],
                        taux__isnull=True,
                    )
                    | Q(
                        regle=RegleSchema.TAUX,
                        sens__isnull=False,
                        sens__in=["debit", "credit"],
                        taux__isnull=False,
                        taux__gt=0,
                    )
                ),
                name="ligneschema_forme",
            ),
            models.UniqueConstraint(
                fields=["schema"],
                condition=Q(regle=RegleSchema.SOLDE),
                name="uq_ligneschema_une_contrepartie",
            ),
        ]


class StatutLettrage(models.TextChoices):
    ACTIF = "actif", "Actif"
    ANNULE = "annule", "Annulé"


class Lettrage(ModeleOrganisation):
    """Un groupe de lignes de solde nul sur un même compte, un même tiers, un même projet.

    Lettrer MARQUE des lignes comptabilisées (`LigneEcriture.reconciliation_id`) sans les
    modifier : elles restent immuables. Un lettrage ne se supprime pas ; on le dé-lettre, ce qui
    l'annule avec son auteur, sa date et son motif, et son code n'est jamais réutilisé.
    """

    code = models.CharField(max_length=10)
    account = models.ForeignKey(Compte, on_delete=models.PROTECT, related_name="+")
    partner = models.ForeignKey(Tiers, on_delete=models.PROTECT, related_name="+")
    project_id = models.UUIDField(db_index=True)
    status = models.CharField(
        max_length=6, choices=StatutLettrage.choices, default=StatutLettrage.ACTIF
    )
    lettre_at = models.DateTimeField(default=timezone.now)
    lettre_by = models.UUIDField(null=True, blank=True)
    annule_at = models.DateTimeField(null=True, blank=True)
    annule_by = models.UUIDField(null=True, blank=True)
    motif_annulation = models.TextField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org_id", "account", "code"], name="uq_lettrage_code"),
            models.CheckConstraint(
                condition=Q(status__in=StatutLettrage.values), name="lettrage_statut_ferme"
            ),
            # `isnull=False` explicite : un CHECK laisse passer NULL (voir L3-T06).
            models.CheckConstraint(
                condition=(
                    Q(
                        status=StatutLettrage.ACTIF,
                        annule_at__isnull=True,
                        annule_by__isnull=True,
                        motif_annulation__isnull=True,
                    )
                    | Q(
                        status=StatutLettrage.ANNULE,
                        annule_at__isnull=False,
                        annule_by__isnull=False,
                        motif_annulation__isnull=False,
                    )
                ),
                name="lettrage_annulation_coherente",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class StatutANouveau(models.TextChoices):
    ACTIF = "actif", "Actif"
    REMPLACE = "remplace", "Remplacé"


class ANouveau(ModeleOrganisation):
    """Une génération des à-nouveaux d'un exercice. Voir L3-T08 (b).

    Versionnée : régénérer, tant que l'exercice d'origine n'est pas verrouillé, crée une version
    de plus. L'écriture de l'ancienne version est contre-passée (une écriture comptabilisée ne se
    modifie jamais) et la nouvelle la remplace. Une seule version est active par exercice.
    """

    project_id = models.UUIDField(db_index=True)
    exercice_source = models.ForeignKey(Exercice, on_delete=models.PROTECT, related_name="+")
    exercice_cible = models.ForeignKey(Exercice, on_delete=models.PROTECT, related_name="+")
    version = models.PositiveIntegerField()
    status = models.CharField(
        max_length=8, choices=StatutANouveau.choices, default=StatutANouveau.ACTIF
    )
    ecriture = models.ForeignKey(Ecriture, on_delete=models.PROTECT, related_name="+")
    ecriture_annulation = models.ForeignKey(
        Ecriture, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    compte_resultat = models.CharField(max_length=20)
    resultat = MontantField()  # bénéfice positif, perte négative
    empreinte = models.CharField(max_length=64)  # SHA-256 des lignes : deux versions se comparent
    genere_at = models.DateTimeField(default=timezone.now)
    genere_by = models.UUIDField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "exercice_source", "version"], name="uq_anouveau_version"
            ),
            models.UniqueConstraint(
                fields=["exercice_source"],
                condition=Q(status=StatutANouveau.ACTIF),
                name="uq_anouveau_un_actif",
            ),
            models.CheckConstraint(condition=Q(version__gte=1), name="anouveau_version_positive"),
            models.CheckConstraint(
                condition=Q(status__in=StatutANouveau.values), name="anouveau_statut_ferme"
            ),
            # `isnull=False` explicite : un CHECK laisse passer NULL (voir L3-T06).
            models.CheckConstraint(
                condition=(
                    Q(status=StatutANouveau.ACTIF, ecriture_annulation__isnull=True)
                    | Q(status=StatutANouveau.REMPLACE, ecriture_annulation__isnull=False)
                ),
                name="anouveau_annulation_coherente",
            ),
        ]

    def __str__(self) -> str:
        return f"À-nouveaux {self.exercice_source} v{self.version}"


class TypePiece(models.TextChoices):
    FACTURE = "facture", "Facture"
    BON_DE_COMMANDE = "bon_de_commande", "Bon de commande"
    CONTRAT = "contrat", "Contrat"
    PREUVE_DE_PAIEMENT = "preuve_de_paiement", "Preuve de paiement"
    AUTRE = "autre", "Autre"


class PieceJustificative(ModeleOrganisation):
    """Un fichier scanné qui justifie une écriture. Voir L7-T03.

    Le fichier vit dans le stockage adressé par le contenu (`niveau3_config.stockage`) ; ici
    n'est gardée que sa référence et son empreinte SHA-256, relue à chaque lecture. Une pièce
    s'AJOUTE : elle ne se modifie ni ne se supprime. Elle n'est pas une écriture du grand livre :
    on peut joindre un scan à une écriture comptabilisée, sans la toucher.
    """

    project_id = models.UUIDField(db_index=True)
    ecriture = models.ForeignKey(Ecriture, on_delete=models.PROTECT, related_name="pieces")
    type_piece = models.CharField(max_length=24, choices=TypePiece.choices)
    nom = models.CharField(max_length=255)
    file_ref = models.CharField(max_length=512)
    sha256 = models.BinaryField()
    taille = models.PositiveIntegerField()
    ajoutee_par = models.UUIDField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(type_piece__in=TypePiece.values), name="piece_type_ferme"
            ),
            models.UniqueConstraint(fields=["ecriture", "sha256"], name="uq_piece_par_ecriture"),
        ]
