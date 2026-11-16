"""Le plan de passation des marchés. Voir L9-T01.

Des MÉTHODES de passation (versionnées, avec leurs seuils), un PLAN par projet, des LIGNES
prévisionnelles (montant, méthode, calendrier) et l'HISTORIQUE de leur avancement. Aucun seuil n'est
inventé : chaque projet pose les siens, par méthode et par devise.
"""

from django.db import models
from django.db.models import Q

from core.fields import MontantField
from core.models import ModeleOrganisation


class MethodePassation(ModeleOrganisation):
    """Une méthode de passation, pour une plage de montants `[seuil_min, seuil_max[`, versionnée."""

    project_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=32)
    version = models.PositiveIntegerField(default=1)
    label = models.JSONField()  # {"fr": …, "en": …}
    devise = models.CharField(max_length=3)
    seuil_min = MontantField(default=0)
    seuil_max = MontantField(null=True, blank=True)  # exclu ; vide : sans plafond
    exige_non_objection = models.BooleanField(default=False)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)  # exclu

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project_id", "code", "version"], name="uq_methodepassation_version"
            ),
            models.CheckConstraint(condition=Q(seuil_min__gte=0), name="methode_seuil_min_positif"),
            models.CheckConstraint(
                condition=Q(seuil_max__isnull=True) | Q(seuil_max__gt=models.F("seuil_min")),
                name="methode_plage_non_vide",
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gt=models.F("valid_from")),
                name="methode_validite_coherente",
            ),
        ]


class PlanPassation(ModeleOrganisation):
    project_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=40)
    nom = models.CharField(max_length=200)
    date_debut = models.DateField()
    date_fin = models.DateField()
    cree_par = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project_id", "code"], name="uq_planpassation_code"),
            models.CheckConstraint(
                condition=Q(date_debut__lte=models.F("date_fin")), name="plan_periode_coherente"
            ),
        ]


class StatutLigne(models.TextChoices):
    PREVU = "prevu", "Prévu"
    LANCE = "lance", "Lancé"
    ATTRIBUE = "attribue", "Attribué"
    SIGNE = "signe", "Signé"
    ANNULE = "annule", "Annulé"


class LignePassation(ModeleOrganisation):
    plan = models.ForeignKey(PlanPassation, on_delete=models.PROTECT, related_name="lignes")
    project_id = models.UUIDField(db_index=True)
    reference = models.CharField(max_length=40)
    libelle = models.CharField(max_length=255)
    montant_prevu = MontantField()
    devise = models.CharField(max_length=3)
    methode = models.ForeignKey(MethodePassation, on_delete=models.PROTECT, related_name="lignes")
    # Instantané de la méthode à la création : l'avis de non-objection (L9-T02) ne change pas si la
    # méthode est révisée plus tard.
    non_objection_requise = models.BooleanField()
    categorie_id = models.UUIDField(null=True, blank=True)
    date_lancement_prevue = models.DateField()
    date_attribution_prevue = models.DateField()
    date_signature_prevue = models.DateField()
    statut = models.CharField(max_length=9, choices=StatutLigne.choices, default=StatutLigne.PREVU)

    class Meta:
        indexes = [models.Index(fields=["project_id", "statut"])]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "reference"], name="uq_lignepassation_reference"
            ),
            models.CheckConstraint(condition=Q(montant_prevu__gt=0), name="ligne_montant_positif"),
            models.CheckConstraint(
                condition=Q(statut__in=StatutLigne.values), name="lignepassation_statut_ferme"
            ),
            models.CheckConstraint(
                condition=Q(date_lancement_prevue__lte=models.F("date_attribution_prevue"))
                & Q(date_attribution_prevue__lte=models.F("date_signature_prevue")),
                name="ligne_calendrier_ordonne",
            ),
        ]


class EtapeAvancement(ModeleOrganisation):
    """Une étape franchie par une ligne, avec sa date et son auteur. En ajout seul."""

    ligne = models.ForeignKey(LignePassation, on_delete=models.PROTECT, related_name="etapes")
    statut = models.CharField(max_length=9, choices=StatutLigne.choices)
    date_effet = models.DateField()
    note = models.TextField(blank=True, default="")
    par = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ligne", "statut"], name="uq_etape_une_fois"),
            models.CheckConstraint(
                condition=Q(statut__in=StatutLigne.values), name="etape_statut_ferme"
            ),
            # Annuler se justifie.
            models.CheckConstraint(
                condition=~Q(statut="annule") | ~Q(note=""), name="etape_annulation_motivee"
            ),
        ]
