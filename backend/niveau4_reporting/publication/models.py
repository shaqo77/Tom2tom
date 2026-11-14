"""Le rapport publié et scellé. Voir L6-T04.

Une ligne est ÉCRITE UNE FOIS et ne change plus : c'est la trace de ce qui a été transmis. Elle
garde de quoi rejouer le rapport tel qu'il a été produit : le modèle d'état en entier (copie, pas
référence : le modèle d'aujourd'hui n'est pas celui d'alors), les paramètres, les versions de
mappings, la configuration, et les valeurs. Le scellé en est l'empreinte (`scellement.py`).
"""

from django.db import models
from django.db.models import Q

from core.models import ModeleOrganisation


class RapportPublie(ModeleOrganisation):
    project_id = models.UUIDField(db_index=True)
    template_code = models.CharField(max_length=64)
    template_version = models.PositiveIntegerField(null=True, blank=True)
    modele = models.JSONField()  # le modèle d'état tel qu'utilisé
    period_from = models.DateField()
    period_to = models.DateField()
    params = models.JSONField(default=dict)
    config_version = models.JSONField(default=dict)
    # {"code de mapping": {"id": uuid, "version": n}}
    mapping_versions = models.JSONField(default=dict)
    dataset_hash = models.BinaryField()
    values = models.JSONField()  # {"rubrique/colonne": "montant canonique"}
    seal = models.BinaryField()
    published_by = models.UUIDField()
    published_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=["project_id", "template_code", "period_to"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(period_from__lte=models.F("period_to")),
                name="rapport_periode_coherente",
            ),
        ]


class FichierRapport(ModeleOrganisation):
    """Un fichier produit pour un rapport publié, avec son empreinte. Ajout seul. Voir L6-T05.

    Le contenu est gardé en base (`contenu`) avec son SHA-256 ; à la lecture on RECALCULE
    l'empreinte et on la compare à celle enregistrée : un fichier altéré ne sort jamais comme bon.
    """

    rapport = models.ForeignKey(RapportPublie, on_delete=models.PROTECT, related_name="files")
    format = models.CharField(max_length=8)  # xlsx | pdf
    langue = models.CharField(max_length=8)
    nom = models.CharField(max_length=200)
    contenu = models.BinaryField()
    sha256 = models.CharField(max_length=64)
    taille = models.PositiveIntegerField()
    produit_par = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["rapport", "format", "langue"], name="uq_fichier_rapport_format_langue"
            ),
            models.CheckConstraint(
                condition=Q(format__in=["xlsx", "pdf"]), name="fichier_format_ferme"
            ),
        ]


class MotifRejet(ModeleOrganisation):
    """Un motif pour lequel un bailleur a déjà rejeté (ou rejetterait) un rapport. L6-T07.

    Donnée, pas code : on ajoute un motif appris d'un rejet sans déployer. Il pointe le CONTRÔLE qui
    le détecte ; la simulation de revue le rejoue et marque les constats qui le recoupent.
    """

    project_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64)
    label = models.JSONField()  # {"fr": …, "en": …}
    controle_code = models.CharField(max_length=64)
    source = models.TextField(blank=True, default="")  # où ce rejet a été constaté
    actif = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project_id", "code"], name="uq_motifrejet_code"),
        ]


class AvisRevue(models.TextChoices):
    GO = "go", "Go"
    GO_RESERVES = "go_reserves", "Go avec réserves"
    NO_GO = "no_go", "No-go"


class SimulationRevue(ModeleOrganisation):
    """Le résultat d'une simulation de revue bailleur, gardé tel quel. Ajout seul."""

    project_id = models.UUIDField(db_index=True)
    objet_type = models.CharField(max_length=40)
    objet_id = models.UUIDField(null=True, blank=True)
    date_effet = models.DateField()
    avis = models.CharField(max_length=12, choices=AvisRevue.choices)
    constats = models.JSONField()  # la liste des constats, textes figés dans chaque langue
    lancee_par = models.UUIDField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(avis__in=AvisRevue.values), name="simulation_avis_ferme"
            ),
        ]


class ResultatSoumission(models.TextChoices):
    EN_ATTENTE = "en_attente", "En attente"
    ACCEPTE = "accepte", "Accepté"
    REJETE = "rejete", "Rejeté"


class SoumissionBailleur(ModeleOrganisation):
    """Un envoi réel d'un rapport au bailleur et son issue. Alimente l'indicateur phare.

    `numero_envoi` compte les envois d'un même rapport (modèle, période) : le premier envoi est le
    seul qui compte pour « accepté au premier envoi ». L'issue se pose UNE fois.
    """

    project_id = models.UUIDField(db_index=True)
    template_code = models.CharField(max_length=64)
    period_to = models.DateField()
    numero_envoi = models.PositiveSmallIntegerField()
    rapport_id = models.UUIDField(null=True, blank=True)
    simulation = models.ForeignKey(
        SimulationRevue, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    envoyee_le = models.DateField()
    resultat = models.CharField(
        max_length=12, choices=ResultatSoumission.choices, default=ResultatSoumission.EN_ATTENTE
    )
    motif_rejet = models.TextField(blank=True, default="")
    decidee_le = models.DateField(null=True, blank=True)
    saisie_par = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project_id", "template_code", "period_to", "numero_envoi"],
                name="uq_soumission_envoi",
            ),
            models.CheckConstraint(
                condition=Q(resultat__in=ResultatSoumission.values),
                name="soumission_resultat_ferme",
            ),
            models.CheckConstraint(condition=Q(numero_envoi__gte=1), name="soumission_numero_pos"),
            # Une issue porte sa date ; un rejet porte son motif ; « en attente » ne porte rien.
            models.CheckConstraint(
                condition=(
                    Q(resultat="en_attente") & Q(decidee_le__isnull=True) & Q(motif_rejet="")
                )
                | (Q(resultat="accepte") & Q(decidee_le__isnull=False) & Q(motif_rejet=""))
                | (Q(resultat="rejete") & Q(decidee_le__isnull=False) & ~Q(motif_rejet="")),
                name="soumission_issue_coherente",
            ),
        ]
