"""Registre des exigences, version minimale. Voir L0-T08 et architecture §4.

Tout objet de configuration (rubrique, mapping, contrôle) se rattache à
l'exigence qui le justifie, et chaque exigence cite le paragraphe d'un
document dont l'empreinte est conservée. Les ensembles fermés sont contraints
EN BASE : le code applicatif s'oublie.
"""

from django.db import models
from django.db.models import Q

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
