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


class ObjetAvis(models.TextChoices):
    """Ce sur quoi le bailleur est consulté (liste fermée ; « autre » pour le reste)."""

    DOSSIER = "dossier", "Dossier de consultation"
    EVALUATION = "evaluation", "Rapport d'évaluation"
    CONTRAT = "contrat", "Projet de contrat"
    AVENANT = "avenant", "Avenant"
    AUTRE = "autre", "Autre"


class StatutAvis(models.TextChoices):
    DEMANDE = "demande", "Demandé"
    OBTENU = "obtenu", "Obtenu"
    REFUSE = "refuse", "Refusé"


class NaturePieceAvis(models.TextChoices):
    DEMANDE = "demande", "Pièce de la demande"
    REPONSE = "reponse", "Réponse du bailleur"


class AvisNonObjection(ModeleOrganisation):
    """Une demande d'avis de non-objection sur une ligne du plan, et sa réponse. Voir L9-T02.

    Une fois décidé (obtenu ou refusé) l'avis est figé : après un refus on DEMANDE À NOUVEAU
    (nouvel avis du même objet), le refus reste dans l'historique.
    """

    ligne = models.ForeignKey(LignePassation, on_delete=models.PROTECT, related_name="avis")
    project_id = models.UUIDField(db_index=True)
    objet = models.CharField(max_length=12, choices=ObjetAvis.choices)
    statut = models.CharField(max_length=8, choices=StatutAvis.choices, default=StatutAvis.DEMANDE)
    date_demande = models.DateField()
    date_decision = models.DateField(null=True, blank=True)
    reference_bailleur = models.CharField(max_length=120, blank=True, default="")
    motif = models.TextField(blank=True, default="")
    demande_par = models.UUIDField()
    decide_par = models.UUIDField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(objet__in=ObjetAvis.values), name="avis_objet_ferme"
            ),
            models.CheckConstraint(
                condition=Q(statut__in=StatutAvis.values), name="avis_statut_ferme"
            ),
            # Décidé ⇔ une date et un auteur de décision ; jamais avant la demande.
            models.CheckConstraint(
                condition=(
                    Q(statut="demande", date_decision__isnull=True, decide_par__isnull=True)
                    | (
                        ~Q(statut="demande")
                        & Q(date_decision__isnull=False, decide_par__isnull=False)
                        & Q(date_decision__gte=models.F("date_demande"))
                    )
                ),
                name="avis_decision_coherente",
            ),
            models.CheckConstraint(
                condition=~Q(statut="refuse") | ~Q(motif=""), name="avis_refus_motive"
            ),
        ]


class PieceAvis(ModeleOrganisation):
    """Un fichier joint à un avis (demande envoyée, réponse reçue), en ajout seul."""

    avis = models.ForeignKey(AvisNonObjection, on_delete=models.PROTECT, related_name="pieces")
    nature = models.CharField(max_length=8, choices=NaturePieceAvis.choices)
    nom = models.CharField(max_length=255)
    file_ref = models.CharField(max_length=512)
    sha256 = models.BinaryField()
    taille = models.PositiveIntegerField()
    ajoutee_par = models.UUIDField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(nature__in=NaturePieceAvis.values), name="pieceavis_nature_fermee"
            ),
            models.UniqueConstraint(fields=["avis", "sha256"], name="uq_pieceavis_par_avis"),
        ]


class Contrat(ModeleOrganisation):
    """Le contrat conclu pour une ligne du plan. Voir L9-T03.

    Il porte sa valeur INITIALE ; les avenants portent les valeurs suivantes, sans jamais modifier
    le contrat en place (la valeur courante est celle du dernier avenant). Un contrat par ligne.
    """

    ligne = models.OneToOneField(LignePassation, on_delete=models.PROTECT, related_name="contrat")
    project_id = models.UUIDField(db_index=True)
    reference = models.CharField(max_length=60)
    tiers = models.ForeignKey("referentiels.Tiers", on_delete=models.PROTECT, related_name="+")
    objet = models.CharField(max_length=255)
    montant_initial = MontantField()
    devise = models.CharField(max_length=3)
    date_signature = models.DateField()
    date_debut = models.DateField()
    date_fin_initiale = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "project_id", "reference"], name="uq_contrat_reference"
            ),
            models.CheckConstraint(
                condition=Q(montant_initial__gt=0), name="contrat_montant_positif"
            ),
            models.CheckConstraint(
                condition=Q(date_fin_initiale__gte=models.F("date_debut")),
                name="contrat_periode_coherente",
            ),
        ]


class AvenantContrat(ModeleOrganisation):
    """Un avenant : il PORTE la nouvelle valeur (montant total, date de fin), en ajout seul.

    Numéroté sans trou par contrat. Sur un marché soumis à non-objection, il s'appuie sur un avis
    OBTENU d'objet « avenant » que nul autre avenant n'a utilisé.
    """

    contrat = models.ForeignKey(Contrat, on_delete=models.PROTECT, related_name="avenants")
    project_id = models.UUIDField(db_index=True)
    numero = models.PositiveSmallIntegerField()
    date_effet = models.DateField()
    montant = MontantField()  # le NOUVEAU montant total du contrat
    date_fin = models.DateField()  # la NOUVELLE date de fin
    motif = models.TextField()
    avis = models.OneToOneField(
        AvisNonObjection, null=True, blank=True, on_delete=models.PROTECT, related_name="avenant"
    )
    cree_par = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["contrat", "numero"], name="uq_avenant_numero"),
            models.CheckConstraint(condition=Q(numero__gte=1), name="avenant_numero_positif"),
            models.CheckConstraint(
                condition=Q(montant__gt=0), name="avenantcontrat_montant_positif"
            ),
            models.CheckConstraint(condition=~Q(motif=""), name="avenantcontrat_motive"),
        ]


class TypeGarantie(models.TextChoices):
    BONNE_EXECUTION = "bonne_execution", "Garantie de bonne exécution"
    AVANCE = "avance", "Garantie de restitution d'avance"
    RETENUE = "retenue", "Garantie de retenue"
    ASSURANCE = "assurance", "Assurance"


class StatutGarantie(models.TextChoices):
    ACTIVE = "active", "Active"
    LIBEREE = "liberee", "Libérée"
    APPELEE = "appelee", "Appelée"


class Garantie(ModeleOrganisation):
    """Une garantie ou assurance attachée à un contrat, avec son échéance. Voir L9-T03.

    Son contenu est figé ; seul le statut avance : active → libérée (mainlevée) ou appelée.
    Une prolongation est une NOUVELLE garantie ; l'ancienne se libère.
    """

    contrat = models.ForeignKey(Contrat, on_delete=models.PROTECT, related_name="garanties")
    project_id = models.UUIDField(db_index=True)
    type_garantie = models.CharField(max_length=16, choices=TypeGarantie.choices)
    emetteur = models.CharField(max_length=255)
    reference = models.CharField(max_length=60)
    montant = MontantField()
    devise = models.CharField(max_length=3)
    date_emission = models.DateField()
    date_echeance = models.DateField()
    statut = models.CharField(
        max_length=8, choices=StatutGarantie.choices, default=StatutGarantie.ACTIVE
    )
    date_cloture = models.DateField(null=True, blank=True)
    note_cloture = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "contrat", "reference"], name="uq_garantie_reference"
            ),
            models.CheckConstraint(
                condition=Q(type_garantie__in=TypeGarantie.values), name="garantie_type_ferme"
            ),
            models.CheckConstraint(
                condition=Q(statut__in=StatutGarantie.values), name="garantie_statut_ferme"
            ),
            models.CheckConstraint(condition=Q(montant__gt=0), name="garantie_montant_positif"),
            models.CheckConstraint(
                condition=Q(date_echeance__gte=models.F("date_emission")),
                name="garantie_periode_coherente",
            ),
            # Clôturée ⇔ une date de clôture ; un appel se motive.
            models.CheckConstraint(
                condition=(Q(statut="active", date_cloture__isnull=True))
                | (~Q(statut="active") & Q(date_cloture__isnull=False)),
                name="garantie_cloture_coherente",
            ),
            models.CheckConstraint(
                condition=~Q(statut="appelee") | ~Q(note_cloture=""), name="garantie_appel_motive"
            ),
        ]


class StatutDecompte(models.TextChoices):
    SOUMIS = "soumis", "Soumis"
    CERTIFIE = "certifie", "Certifié"
    REJETE = "rejete", "Rejeté"


class Decompte(ModeleOrganisation):
    """Un décompte (situation) présenté sur un contrat. Voir L9-T04.

    `montant_brut` est dans la devise du contrat. Certifié par une AUTRE personne que celle qui
    l'a soumis, il apure l'engagement du marché (`montant_apure`, en monnaie de tenue du projet)
    dans la même transaction. Certifié ou rejeté, il est définitif : on corrige par un décompte
    suivant. Numéroté sans trou par contrat.
    """

    contrat = models.ForeignKey(Contrat, on_delete=models.PROTECT, related_name="decomptes")
    project_id = models.UUIDField(db_index=True)
    numero = models.PositiveSmallIntegerField()
    date_decompte = models.DateField()
    montant_brut = MontantField()
    retenue = MontantField(default=0)
    avancement_physique = models.DecimalField(max_digits=6, decimal_places=2)  # % cumulé, 0 à 100
    facture_reference = models.CharField(max_length=60, blank=True, default="")
    facture_date = models.DateField(null=True, blank=True)
    soumis_par = models.UUIDField()
    statut = models.CharField(
        max_length=8, choices=StatutDecompte.choices, default=StatutDecompte.SOUMIS
    )
    decide_par = models.UUIDField(null=True, blank=True)
    date_decision = models.DateField(null=True, blank=True)
    engagement = models.ForeignKey(
        "budget.Engagement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="decomptes",
    )
    montant_apure = MontantField(null=True, blank=True)  # monnaie de tenue du projet
    motif_rejet = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["contrat", "numero"], name="uq_decompte_numero"),
            models.CheckConstraint(condition=Q(numero__gte=1), name="decompte_numero_positif"),
            models.CheckConstraint(condition=Q(montant_brut__gt=0), name="decompte_brut_positif"),
            models.CheckConstraint(
                condition=Q(retenue__gte=0, retenue__lte=models.F("montant_brut")),
                name="decompte_retenue_bornee",
            ),
            models.CheckConstraint(
                condition=Q(avancement_physique__gte=0, avancement_physique__lte=100),
                name="decompte_avancement_borne",
            ),
            models.CheckConstraint(
                condition=Q(statut__in=StatutDecompte.values), name="decompte_statut_ferme"
            ),
            # Soumis : sans décision. Certifié : engagement, montant apuré, date, décideur ≠ auteur.
            # Rejeté : décideur, date et motif.
            models.CheckConstraint(
                condition=(
                    Q(statut="soumis", decide_par__isnull=True, engagement__isnull=True)
                    | (
                        Q(statut="certifie", engagement__isnull=False, montant_apure__gt=0)
                        & Q(decide_par__isnull=False, date_decision__isnull=False)
                        & ~Q(decide_par=models.F("soumis_par"))
                    )
                    | (
                        Q(statut="rejete", engagement__isnull=True, decide_par__isnull=False)
                        & Q(date_decision__isnull=False)
                        & ~Q(motif_rejet="")
                    )
                ),
                name="decompte_decision_coherente",
            ),
        ]


class Paiement(ModeleOrganisation):
    """Un paiement sur un décompte certifié, en ajout seul. Voir L9-T04."""

    decompte = models.ForeignKey(Decompte, on_delete=models.PROTECT, related_name="paiements")
    project_id = models.UUIDField(db_index=True)
    reference = models.CharField(max_length=60)
    date_paiement = models.DateField()
    montant = MontantField()
    enregistre_par = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["decompte", "reference"], name="uq_paiement_reference"),
            models.CheckConstraint(condition=Q(montant__gt=0), name="paiement_montant_positif"),
        ]
