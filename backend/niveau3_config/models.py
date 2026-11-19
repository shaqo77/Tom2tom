"""Registre des exigences, version minimale. Voir L0-T08 et architecture §4.

Tout objet de configuration (rubrique, mapping, contrôle) se rattache à
l'exigence qui le justifie, et chaque exigence cite le paragraphe d'un
document dont l'empreinte est conservée. Les ensembles fermés sont contraints
EN BASE : le code applicatif s'oublie.
"""

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from core.fields import MontantField
from core.models import ModeleOrganisation


class TypeDocument(models.TextChoices):
    ACCORD_FINANCEMENT = "financing_agreement", "Accord de financement"
    DFIL = "dfil", "Lettre de décaissement et d'information financière"
    MANUEL_EXECUTION = "implementation_manual", "Manuel d'exécution"
    PTBA = "awp_budget", "Plan de travail et budget annuel"
    MODELE_RAPPORT = "report_template", "Modèle de rapport"
    INSTRUCTION = "instruction", "Instruction complémentaire"


class DocumentReference(ModeleOrganisation):
    """Document contractuel du projet. L'empreinte fige ce que la citation vise."""

    project_id = models.UUIDField(db_index=True)
    kind = models.CharField(max_length=32, choices=TypeDocument.choices)
    title = models.CharField(max_length=255)
    version = models.CharField(max_length=32, blank=True, default="")
    issued_on = models.DateField(null=True, blank=True)
    file_ref = models.CharField(max_length=512)
    sha256 = models.BinaryField()
    superseded_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="remplace"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=TypeDocument.values),
                name="documentreference_type_ferme",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} (v{self.version})"


class Periodicite(models.TextChoices):
    MENSUELLE = "monthly", "Mensuelle"
    TRIMESTRIELLE = "quarterly", "Trimestrielle"
    SEMESTRIELLE = "semiannual", "Semestrielle"
    ANNUELLE = "annual", "Annuelle"
    EVENEMENT = "event", "À l'événement"


class Obligation(models.TextChoices):
    OBLIGATOIRE = "mandatory", "Obligatoire"
    CONDITIONNELLE = "conditional", "Conditionnelle"
    FACULTATIVE = "optional", "Facultative"


class StatutExigence(models.TextChoices):
    PROPOSEE = "proposed", "Proposée"
    VALIDEE = "validated", "Validée"
    ACTIVE = "active", "Active"
    REMPLACEE = "superseded", "Remplacée"
    REJETEE = "rejected", "Rejetée"


class OrigineExigence(models.TextChoices):
    MANUELLE = "manual", "Saisie manuelle"
    ASSISTEE = "assisted", "Proposée par l'assistant"


class Exigence(ModeleOrganisation):
    """Une exigence du registre, versionnée, avec sa source documentaire."""

    project_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64)
    donor_profile_id = models.UUIDField(null=True, blank=True)
    document = models.ForeignKey(
        DocumentReference, on_delete=models.PROTECT, related_name="exigences"
    )
    # {"annex": "2", "page": 37, "paragraph": "4.2", "quote": "…texte exact…"}
    citation = models.JSONField()
    subject = models.CharField(max_length=255)
    rule = models.JSONField()
    periodicity = models.CharField(
        max_length=16, choices=Periodicite.choices, null=True, blank=True
    )
    due_offset_days = models.IntegerField(null=True, blank=True)
    obligation = models.CharField(max_length=16, choices=Obligation.choices)
    condition_expr = models.TextField(null=True, blank=True)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)  # exclu : [valid_from, valid_to[
    version = models.PositiveIntegerField()
    status = models.CharField(
        max_length=16, choices=StatutExigence.choices, default=StatutExigence.PROPOSEE
    )
    source = models.CharField(max_length=16, choices=OrigineExigence.choices)
    # Confiance de l'assistant d'extraction : un ratio, pas un montant.
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    validated_by = models.UUIDField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    # L'empreinte du document sur le texte duquel la citation a été RETROUVÉE (L5-T02). La base
    # exige qu'elle soit posée pour toute exigence validée ou active, et qu'elle soit celle du
    # document référencé : une citation jamais vérifiée n'entre pas dans le registre actif.
    citation_verifiee_sha256 = models.BinaryField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "project_id", "code", "version"],
                name="uq_exigence_version",
            ),
            # La contrainte clé de L0-T08 : aucune exigence validée ou active
            # sans validateur nommé et daté. Posée en base, pas dans l'application.
            models.CheckConstraint(
                condition=~Q(status__in=[StatutExigence.VALIDEE, StatutExigence.ACTIVE])
                | Q(validated_by__isnull=False, validated_at__isnull=False),
                name="exigence_validation_obligatoire",
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gt=models.F("valid_from")),
                name="exigence_dates_coherentes",
            ),
            models.CheckConstraint(
                condition=Q(status__in=StatutExigence.values),
                name="exigence_statut_ferme",
            ),
            models.CheckConstraint(
                condition=Q(obligation__in=Obligation.values),
                name="exigence_obligation_fermee",
            ),
            models.CheckConstraint(
                condition=Q(periodicity__isnull=True) | Q(periodicity__in=Periodicite.values),
                name="exigence_periodicite_fermee",
            ),
            models.CheckConstraint(
                condition=Q(source__in=OrigineExigence.values),
                name="exigence_origine_fermee",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} v{self.version}"


class TypeCible(models.TextChoices):
    MODELE_ETAT = "report_template", "Modèle d'état"
    RUBRIQUE = "report_row", "Rubrique d'état"
    MAPPING = "mapping", "Mapping"
    CONTROLE = "control", "Contrôle"
    CHAMP = "field", "Champ"


class RattachementExigence(ModeleOrganisation):
    """Relie un objet de configuration à l'exigence qui le justifie."""

    exigence = models.ForeignKey(Exigence, on_delete=models.PROTECT, related_name="rattachements")
    target_type = models.CharField(max_length=32, choices=TypeCible.choices)
    target_id = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["exigence", "target_type", "target_id"],
                name="uq_rattachement_exigence",
            ),
            models.CheckConstraint(
                condition=Q(target_type__in=TypeCible.values),
                name="rattachement_type_cible_ferme",
            ),
        ]


# --- Profil de décaissement (L5-T03bis, architecture §4bis) ---------------------------------


class RegimeDecaissement(models.TextChoices):
    SUR_TRANSACTIONS = "transaction_based", "Sur transactions"
    SUR_RAPPORT = "report_based", "Sur rapport"


class StatutProfil(models.TextChoices):
    BROUILLON = "draft", "Brouillon"
    VALIDE = "validated", "Validé"
    ACTIF = "active", "Actif"
    REMPLACE = "superseded", "Remplacé"
    REJETE = "rejected", "Rejeté"


class ProfilDecaissement(ModeleOrganisation):
    """Ce qui varie d'un projet à l'autre chez un même bailleur : régime, dates, méthodes, seuils,
    comptes désignés, taux de financement par catégorie. Versionné avec date d'effet.

    Les ensembles sont FERMÉS et contraints en base : ajouter une méthode ou une pièce exigée est
    une migration, jamais un paramétrage client.
    """

    project_id = models.UUIDField(db_index=True)
    accord = models.ForeignKey(
        "financements.Accord", on_delete=models.PROTECT, related_name="profils"
    )
    version = models.PositiveIntegerField()
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)  # exclu : [valid_from, valid_to[
    regime = models.CharField(max_length=20, choices=RegimeDecaissement.choices)
    effectiveness_date = models.DateField(null=True, blank=True)  # entrée en vigueur
    eligibility_date = models.DateField(
        null=True, blank=True
    )  # dépenses antérieures non finançables
    closing_date = models.DateField(null=True, blank=True)
    disbursement_deadline = models.DateField(null=True, blank=True)  # clôture + période de grâce
    requirement = models.ForeignKey(
        Exigence, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )  # la règle qui le justifie
    status = models.CharField(
        max_length=12, choices=StatutProfil.choices, default=StatutProfil.BROUILLON
    )
    rejection_reason = models.TextField(blank=True, default="")
    validated_by = models.UUIDField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "project_id", "accord", "version"], name="uq_profil_version"
            ),
            models.CheckConstraint(
                condition=Q(regime__in=RegimeDecaissement.values), name="profil_regime_ferme"
            ),
            models.CheckConstraint(
                condition=Q(status__in=StatutProfil.values), name="profil_statut_ferme"
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gt=models.F("valid_from")),
                name="profil_dates_coherentes",
            ),
            # Les dates du profil se suivent, quand elles sont renseignées (toutes les paires).
            *(
                models.CheckConstraint(
                    condition=Q(**{f"{a}__isnull": True})
                    | Q(**{f"{b}__isnull": True})
                    | Q(**{f"{a}__lte": models.F(b)}),
                    name=f"profil_jalons_{i}",
                )
                for i, (a, b) in enumerate(
                    [
                        ("effectiveness_date", "eligibility_date"),
                        ("eligibility_date", "closing_date"),
                        ("closing_date", "disbursement_deadline"),
                        ("eligibility_date", "disbursement_deadline"),
                    ]
                )
            ),
            models.CheckConstraint(
                condition=~Q(status__in=[StatutProfil.VALIDE, StatutProfil.ACTIF])
                | Q(validated_by__isnull=False, validated_at__isnull=False),
                name="profil_validation_obligatoire",
            ),
            models.CheckConstraint(
                condition=~Q(status=StatutProfil.REJETE) | ~Q(rejection_reason=""),
                name="profil_rejet_motive",
            ),
        ]

    def __str__(self) -> str:
        return f"profil {self.accord_id} v{self.version} ({self.status})"


class MethodeDecaissementCode(models.TextChoices):
    AVANCE = "advance", "Avance"
    REMBOURSEMENT = "reimbursement", "Remboursement"
    PAIEMENT_DIRECT = "direct_payment", "Paiement direct"
    ENGAGEMENT_SPECIAL = "special_commitment", "Engagement spécial"


PIECES_EXIGEES = ("soe", "records", "ifr", "summary_sheet")  # état certifié, copies, RFI, fiche


class MethodeDecaissement(ModeleOrganisation):
    profil = models.ForeignKey(
        ProfilDecaissement, on_delete=models.CASCADE, related_name="methodes"
    )
    method = models.CharField(max_length=20, choices=MethodeDecaissementCode.choices)
    is_enabled = models.BooleanField(default=True)
    supporting_docs = ArrayField(models.CharField(max_length=16), default=list)
    full_doc_threshold = MontantField(null=True, blank=True)  # au-delà : copies de pièces exigées
    min_application_amount = MontantField(null=True, blank=True)  # montant minimum, valeur fixe…
    min_application_pct_of_ceiling = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )  # …ou % du plafond du compte désigné

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["profil", "method"], name="uq_methode_par_profil"),
            models.CheckConstraint(
                condition=Q(method__in=MethodeDecaissementCode.values),
                name="methode_ensemble_ferme",
            ),
            models.CheckConstraint(
                condition=Q(min_application_amount__isnull=True)
                | Q(min_application_pct_of_ceiling__isnull=True),
                name="methode_un_seul_minimum",
            ),
            models.CheckConstraint(
                condition=Q(min_application_amount__isnull=True) | Q(min_application_amount__gte=0),
                name="methode_minimum_positif",
            ),
            models.CheckConstraint(
                condition=Q(min_application_pct_of_ceiling__isnull=True)
                | Q(min_application_pct_of_ceiling__gte=0, min_application_pct_of_ceiling__lte=1),
                name="methode_pourcentage_borne",
            ),
            models.CheckConstraint(
                condition=Q(full_doc_threshold__isnull=True) | Q(full_doc_threshold__gte=0),
                name="methode_seuil_documentation_positif",
            ),
            models.CheckConstraint(
                condition=Q(supporting_docs__contained_by=list(PIECES_EXIGEES)),
                name="methode_pieces_ensemble_ferme",
            ),
        ]


class PlafondCompte(models.TextChoices):
    FIXE = "fixed", "Fixe"
    VARIABLE = "variable", "Variable"


class RegleCompteDesigne(ModeleOrganisation):
    profil = models.ForeignKey(ProfilDecaissement, on_delete=models.CASCADE, related_name="comptes")
    bank_account = models.ForeignKey(
        "financements.CompteBancaire", on_delete=models.PROTECT, related_name="+"
    )
    currency = models.ForeignKey("referentiels.Devise", on_delete=models.PROTECT, related_name="+")
    ceiling_kind = models.CharField(max_length=8, choices=PlafondCompte.choices)
    ceiling_amount = MontantField(null=True, blank=True)
    replenishment_threshold_pct = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["profil", "bank_account"], name="uq_regle_compte"),
            models.CheckConstraint(
                condition=Q(ceiling_kind__in=PlafondCompte.values),
                name="regle_compte_plafond_ferme",
            ),
            # Un plafond fixe a un montant ; un plafond variable n'en porte pas.
            models.CheckConstraint(
                condition=(
                    Q(ceiling_kind=PlafondCompte.FIXE, ceiling_amount__isnull=False)
                    | Q(ceiling_kind=PlafondCompte.VARIABLE, ceiling_amount__isnull=True)
                ),
                name="regle_compte_plafond_coherent",
            ),
            models.CheckConstraint(
                condition=Q(ceiling_amount__isnull=True) | Q(ceiling_amount__gte=0),
                name="regle_compte_plafond_positif",
            ),
            models.CheckConstraint(
                condition=Q(replenishment_threshold_pct__isnull=True)
                | Q(replenishment_threshold_pct__gte=0, replenishment_threshold_pct__lte=1),
                name="regle_compte_seuil_borne",
            ),
        ]


class AssietteTaxes(models.TextChoices):
    HORS_TAXES = "net_of_taxes", "Hors taxes"
    TAXES_COMPRISES = "taxes_included", "Taxes comprises"


class RegleFinancementCategorie(ModeleOrganisation):
    """Allocation ET taux de financement d'une catégorie, versionnés avec le profil.

        montant_a_retirer = dépense éligible × funding_rate, sur l'assiette `tax_basis`

    Son identifiant est persisté sur chaque ligne de demande de retrait : sans cela, une
    réallocation ultérieure rendrait inexplicable le montant d'une demande déjà soumise.
    """

    profil = models.ForeignKey(ProfilDecaissement, on_delete=models.CASCADE, related_name="regles")
    category = models.ForeignKey(
        "financements.Categorie", on_delete=models.PROTECT, related_name="+"
    )
    allocation = MontantField()
    funding_rate = models.DecimalField(max_digits=9, decimal_places=6)
    tax_basis = models.CharField(max_length=16, choices=AssietteTaxes.choices)
    eligibility_from = models.DateField(null=True, blank=True)
    eligibility_to = models.DateField(null=True, blank=True)  # incluse
    requires_prior_review = models.BooleanField(default=False)
    max_per_contract = MontantField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["profil", "category"], name="uq_regle_categorie"),
            models.CheckConstraint(
                condition=Q(funding_rate__gt=0, funding_rate__lte=1), name="regle_taux_dans_0_1"
            ),
            models.CheckConstraint(
                condition=Q(tax_basis__in=AssietteTaxes.values), name="regle_assiette_fermee"
            ),
            models.CheckConstraint(
                condition=Q(allocation__gte=0), name="regle_allocation_positive"
            ),
            models.CheckConstraint(
                condition=Q(eligibility_from__isnull=True)
                | Q(eligibility_to__isnull=True)
                | Q(eligibility_from__lte=models.F("eligibility_to")),
                name="regle_eligibilite_coherente",
            ),
            models.CheckConstraint(
                condition=Q(max_per_contract__isnull=True) | Q(max_per_contract__gte=0),
                name="regle_plafond_contrat_positif",
            ),
        ]


class StatutReallocation(models.TextChoices):
    DEMANDEE = "requested", "Demandée"
    APPROUVEE = "approved", "Approuvée"
    REJETEE = "rejected", "Rejetée"


class Reallocation(ModeleOrganisation):
    """Un transfert de montant d'une catégorie à une autre : un ÉVÉNEMENT, pas une modification.

    À l'approbation, le transfert crée une nouvelle version du profil de décaissement (allocations
    modifiées, `valid_from` = date d'effet) ; l'ancienne est conservée. L'approbateur est
    distinct du demandeur, par le service et par la base. Une réallocation décidée ne se modifie
    plus.
    """

    project_id = models.UUIDField(db_index=True)
    accord = models.ForeignKey(
        "financements.Accord", on_delete=models.PROTECT, related_name="reallocations"
    )
    source = models.ForeignKey("financements.Categorie", on_delete=models.PROTECT, related_name="+")
    cible = models.ForeignKey("financements.Categorie", on_delete=models.PROTECT, related_name="+")
    montant = MontantField()
    devise = models.ForeignKey("referentiels.Devise", on_delete=models.PROTECT, related_name="+")
    date_effet = models.DateField()
    motif = models.TextField()
    document = models.ForeignKey(
        DocumentReference, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    status = models.CharField(
        max_length=10, choices=StatutReallocation.choices, default=StatutReallocation.DEMANDEE
    )
    demandeur = models.UUIDField()
    approbateur = models.UUIDField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    motif_rejet = models.TextField(blank=True, default="")
    # La version de profil créée à l'approbation : unique, donc une double approbation concurrente
    # n'en produit qu'une.
    profil_cree = models.OneToOneField(
        ProfilDecaissement,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reallocation_origine",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=StatutReallocation.values), name="realloc_statut_ferme"
            ),
            models.CheckConstraint(condition=Q(montant__gt=0), name="realloc_montant_positif"),
            models.CheckConstraint(
                condition=~Q(source=models.F("cible")), name="realloc_source_differente_cible"
            ),
            # Approuvée : approbateur nommé, distinct du demandeur, version créée. NULL ne passe
            # pas : on teste explicitement les trois.
            models.CheckConstraint(
                condition=~Q(status=StatutReallocation.APPROUVEE)
                | (
                    Q(
                        approbateur__isnull=False,
                        profil_cree__isnull=False,
                        decided_at__isnull=False,
                    )
                    & ~Q(approbateur=models.F("demandeur"))
                ),
                name="realloc_approbation_complete",
            ),
            models.CheckConstraint(
                condition=~Q(status=StatutReallocation.REJETEE)
                | (Q(approbateur__isnull=False, decided_at__isnull=False) & ~Q(motif_rejet="")),
                name="realloc_rejet_motive",
            ),
            models.CheckConstraint(
                condition=~Q(status=StatutReallocation.DEMANDEE)
                | Q(profil_cree__isnull=True, approbateur__isnull=True),
                name="realloc_demandee_sans_decision",
            ),
        ]

    def __str__(self) -> str:
        return f"réallocation {self.montant} {self.source_id}→{self.cible_id} ({self.status})"


class StatutEcheance(models.TextChoices):
    A_REMETTRE = "a_remettre", "À remettre"
    REMISE = "remise", "Remise"
    ANNULEE = "annulee", "Annulée"


class Echeance(ModeleOrganisation):
    """Une échéance de remise, générée depuis une exigence périodique ACTIVE. Voir L6-T06.

    Elle porte l'exigence PRÉCISE (donc sa version) qui l'a produite : la date et la source restent
    lisibles même quand l'exigence est révisée plus tard. Le « feu » (vert, orange, rouge) ne se
    stocke pas : il se calcule à la date du jour.
    """

    project_id = models.UUIDField(db_index=True)
    exigence = models.ForeignKey(Exigence, on_delete=models.PROTECT, related_name="echeances")
    periode_debut = models.DateField()
    periode_fin = models.DateField()
    date_echeance = models.DateField()
    statut = models.CharField(
        max_length=12, choices=StatutEcheance.choices, default=StatutEcheance.A_REMETTRE
    )
    rapport_id = models.UUIDField(null=True, blank=True)  # le rapport publié qui l'a remise
    remise_le = models.DateTimeField(null=True, blank=True)
    remise_par = models.UUIDField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["project_id", "date_echeance"])]
        constraints = [
            models.UniqueConstraint(
                fields=["exigence", "periode_fin"], name="uq_echeance_exigence_periode"
            ),
            models.CheckConstraint(
                condition=Q(statut__in=StatutEcheance.values), name="echeance_statut_ferme"
            ),
            models.CheckConstraint(
                condition=Q(periode_debut__lte=models.F("periode_fin")),
                name="echeance_periode_coherente",
            ),
            models.CheckConstraint(
                condition=~Q(statut="remise")
                | Q(rapport_id__isnull=False, remise_le__isnull=False, remise_par__isnull=False),
                name="echeance_remise_tracee",
            ),
        ]
