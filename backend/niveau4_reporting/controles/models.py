"""Les contrôles, leur journal d'évaluation et les décisions humaines. Voir L6-T01.

Un `Controle` est un objet de configuration versionné (`[valid_from, valid_to[`), rattaché à
l'exigence qui le justifie (L5-T03). Son `expression` est une condition structurée (voir
`conditions.py`), jamais du texte libre. Chaque évaluation laisse une ligne du journal, en ajout
seul ; un contrôle à vérifier à la main est tranché par une décision, elle aussi en ajout seul.
"""

from django.db import models
from django.db.models import Q

from core.models import ModeleOrganisation

from .conditions import TYPES_DE_REGLE


class Severite(models.TextChoices):
    BLOQUANT = "bloquant", "Bloquant"
    AVERTISSEMENT = "avertissement", "Avertissement"
    INFORMATION = "information", "Information"


class ModeControle(models.TextChoices):
    AUTOMATIQUE = "automatique", "Automatique"
    MANUEL = "manuel", "À vérifier par une personne"


class StatutControle(models.TextChoices):
    BROUILLON = "draft", "Brouillon"
    VALIDE = "validated", "Validé"
    ACTIF = "active", "Actif"
    REMPLACE = "superseded", "Remplacé"
    REJETE = "rejected", "Rejeté"


class Resultat(models.TextChoices):
    REUSSI = "reussi", "Réussi"
    BLOQUANT = "bloquant", "Bloquant"
    AVERTISSEMENT = "avertissement", "Avertissement"
    INFORMATION = "information", "Information"
    A_VERIFIER = "a_verifier", "À vérifier"
    # Un contrôle conditionnel non applicable n'existe que dans le journal, pas dans l'interface.
    NON_APPLICABLE = "non_applicable", "Non applicable"


class TypeDeclencheur(models.TextChoices):
    UTILISATEUR = "utilisateur", "Utilisateur"
    SERVICE = "service", "Service"


class Decision(models.TextChoices):
    CONFORME = "conforme", "Conforme"
    NON_CONFORME = "non_conforme", "Non conforme"


class Controle(ModeleOrganisation):
    project_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1)
    label = models.JSONField()  # {"fr": …, "en": …}
    type_regle = models.CharField(max_length=24)
    severity = models.CharField(max_length=14, choices=Severite.choices)
    mode = models.CharField(
        max_length=12, choices=ModeControle.choices, default=ModeControle.AUTOMATIQUE
    )
    expression = models.JSONField(null=True, blank=True)
    applicable_si = models.JSONField(null=True, blank=True)  # même forme ; sinon non applicable
    # Règle de pièces : {"type_piece": "facture", "validee": true}. Vide pour les autres règles.
    parametres = models.JSONField(default=dict, blank=True)
    action_corrective = models.JSONField(blank=True, default=dict)  # {"fr": …, "en": …}
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)  # exclu : [valid_from, valid_to[
    status = models.CharField(
        max_length=12, choices=StatutControle.choices, default=StatutControle.BROUILLON
    )
    validated_by = models.UUIDField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "project_id", "code", "version"], name="uq_controle_version"
            ),
            models.CheckConstraint(
                condition=Q(severity__in=Severite.values), name="controle_severite_fermee"
            ),
            models.CheckConstraint(
                condition=Q(mode__in=ModeControle.values), name="controle_mode_ferme"
            ),
            models.CheckConstraint(
                condition=Q(status__in=StatutControle.values), name="controle_statut_ferme"
            ),
            models.CheckConstraint(
                condition=Q(type_regle__in=list(TYPES_DE_REGLE)), name="controle_type_regle_ferme"
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gt=models.F("valid_from")),
                name="controle_dates_coherentes",
            ),
            # Automatique : une expression ; manuel : aucune (rien à évaluer par le système).
            models.CheckConstraint(
                condition=(Q(mode=ModeControle.AUTOMATIQUE) & Q(expression__isnull=False))
                | (Q(mode=ModeControle.MANUEL) & Q(expression__isnull=True)),
                name="controle_expression_selon_mode",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=[StatutControle.VALIDE, StatutControle.ACTIF])
                | Q(validated_by__isnull=False, validated_at__isnull=False),
                name="controle_validation_obligatoire",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} v{self.version}"


class EvaluationControle(ModeleOrganisation):
    """Une ligne du journal : en ajout seul, jamais modifiée ni supprimée."""

    controle = models.ForeignKey(Controle, on_delete=models.PROTECT, related_name="evaluations")
    controle_version = models.PositiveIntegerField()
    project_id = models.UUIDField(db_index=True)
    objet_type = models.CharField(max_length=40)
    objet_id = models.UUIDField(null=True, blank=True)
    resultat = models.CharField(max_length=14, choices=Resultat.choices)
    severity = models.CharField(max_length=14, choices=Severite.choices)
    valeur_constatee = models.TextField(blank=True, default="")
    valeur_attendue = models.TextField(blank=True, default="")
    # Figés à l'écriture dans CHAQUE langue (le journal est immuable) : {"fr": …, "en": …}.
    message = models.JSONField(blank=True, default=dict)
    action_corrective = models.JSONField(blank=True, default=dict)
    # Le profil de décaissement résolu à la date de l'opération (L5-T04), s'il y en a un.
    profile_version_id = models.UUIDField(null=True, blank=True)
    exigence_id = models.UUIDField(null=True, blank=True)
    exigence_code = models.CharField(max_length=64, blank=True, default="")
    exigence_clause = models.CharField(max_length=255, blank=True, default="")
    evaluee_le = models.DateField()  # la date de l'opération contrôlée
    declencheur_type = models.CharField(max_length=12, choices=TypeDeclencheur.choices)
    declencheur_id = models.UUIDField(null=True, blank=True)  # l'utilisateur
    declencheur_nom = models.CharField(max_length=64, blank=True, default="")  # le service

    class Meta:
        indexes = [models.Index(fields=["project_id", "objet_type", "objet_id"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(resultat__in=Resultat.values), name="evaluation_resultat_ferme"
            ),
            models.CheckConstraint(
                condition=Q(severity__in=Severite.values), name="evaluation_severite_fermee"
            ),
            models.CheckConstraint(
                condition=Q(declencheur_type__in=TypeDeclencheur.values),
                name="evaluation_declencheur_ferme",
            ),
            # Un utilisateur déclenche, ou un service nommé : jamais l'un sans l'autre.
            models.CheckConstraint(
                condition=(
                    Q(declencheur_type=TypeDeclencheur.UTILISATEUR)
                    & Q(declencheur_id__isnull=False)
                    & Q(declencheur_nom="")
                )
                | (
                    Q(declencheur_type=TypeDeclencheur.SERVICE)
                    & Q(declencheur_id__isnull=True)
                    & ~Q(declencheur_nom="")
                ),
                name="evaluation_declencheur_coherent",
            ),
        ]


class DecisionControle(ModeleOrganisation):
    """La décision d'une personne sur un contrôle à vérifier. En ajout seul."""

    evaluation = models.ForeignKey(
        EvaluationControle, on_delete=models.PROTECT, related_name="decisions"
    )
    decision = models.CharField(max_length=14, choices=Decision.choices)
    motif = models.TextField()
    decided_by = models.UUIDField()
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(decision__in=Decision.values), name="decision_controle_fermee"
            ),
            models.CheckConstraint(condition=~Q(motif=""), name="decision_controle_motivee"),
        ]


class Justification(ModeleOrganisation):
    """Ce qu'une personne dit d'une anomalie : elle EXPLIQUE, elle n'autorise rien. Ajout seul.

    Textuelle, nominative (l'auteur est figé avec son nom) et conservée. Une justification ne lève
    jamais un blocage : seule une correction ou une dérogation approuvée le fait.
    """

    evaluation = models.ForeignKey(
        EvaluationControle, on_delete=models.PROTECT, related_name="justifications"
    )
    texte = models.TextField()
    auteur_id = models.UUIDField()
    auteur_nom = models.CharField(max_length=150)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~Q(texte=""), name="justification_texte_obligatoire"),
        ]


class StatutDerogation(models.TextChoices):
    DEMANDEE = "demandee", "Demandée"
    APPROUVEE = "approuvee", "Approuvée"
    REFUSEE = "refusee", "Refusée"


class Derogation(ModeleOrganisation):
    """L'autorisation formelle de poursuivre malgré UN contrôle bloquant, sur UN objet. L6-T02.

    Le résultat initial (l'évaluation visée) n'est ni effacé ni réécrit : la dérogation s'ajoute à
    côté. Elle vaut pour `[valide_du, valide_jusquau[` (fin exclue), pour le contrôle et l'objet de
    l'évaluation visée, et son approbateur est une autre personne que son demandeur.
    """

    evaluation = models.ForeignKey(
        EvaluationControle, on_delete=models.PROTECT, related_name="derogations"
    )
    controle = models.ForeignKey(Controle, on_delete=models.PROTECT, related_name="derogations")
    project_id = models.UUIDField(db_index=True)
    objet_type = models.CharField(max_length=40)
    objet_id = models.UUIDField(null=True, blank=True)
    motif = models.TextField()
    justificatif = models.CharField(max_length=255)  # référence du document justificatif
    valide_du = models.DateField()
    valide_jusquau = models.DateField()  # exclu
    statut = models.CharField(
        max_length=10, choices=StatutDerogation.choices, default=StatutDerogation.DEMANDEE
    )
    demandeur_id = models.UUIDField()
    approbateur_id = models.UUIDField(null=True, blank=True)
    decidee_le = models.DateTimeField(null=True, blank=True)
    motif_decision = models.TextField(blank=True, default="")

    class Meta:
        indexes = [models.Index(fields=["project_id", "objet_type", "objet_id"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(statut__in=StatutDerogation.values), name="derogation_statut_ferme"
            ),
            models.CheckConstraint(condition=~Q(motif=""), name="derogation_motivee"),
            models.CheckConstraint(condition=~Q(justificatif=""), name="derogation_justifiee"),
            models.CheckConstraint(
                condition=Q(valide_du__lt=models.F("valide_jusquau")),
                name="derogation_periode_non_vide",
            ),
            # Jamais son propre approbateur.
            models.CheckConstraint(
                condition=Q(approbateur_id__isnull=True)
                | ~Q(approbateur_id=models.F("demandeur_id")),
                name="derogation_approbateur_distinct",
            ),
            # Décidée = un approbateur, une date, un motif ; demandée = rien de tout cela.
            models.CheckConstraint(
                condition=(
                    Q(statut=StatutDerogation.DEMANDEE)
                    & Q(approbateur_id__isnull=True)
                    & Q(decidee_le__isnull=True)
                )
                | (
                    ~Q(statut=StatutDerogation.DEMANDEE)
                    & Q(approbateur_id__isnull=False)
                    & Q(decidee_le__isnull=False)
                    & ~Q(motif_decision="")
                ),
                name="derogation_decision_coherente",
            ),
        ]
