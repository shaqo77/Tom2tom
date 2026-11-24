"""Demandes de retrait de fonds (DRF). Voir L4-T06.

    préparée ─soumettre─▶ soumise ─▶ acceptée ─▶ remboursée
        │                   │  ╲        │
     annulée            rejetée  contestée ◀─┘ (retour possible vers acceptée ou rejetée)

Ce qui est GARANTI PAR LA BASE, pour tout rôle :
- une dépense (ligne d'écriture) n'est justifiée que par UNE demande en cours (index unique
  partiel) ;
- une dépense d'une demande rejetée ne redevient sélectionnable que par le lien `reprise_de` ;
- le plafond de chaque catégorie (et de ses catégories parentes) et le montant de l'accord ne sont
  jamais dépassés, même par deux soumissions simultanées (verrou de ligne sur les soldes, et refus
  par la base si l'on tentait de passer outre) ;
- le cycle est fermé, le contenu d'une demande soumise ne change plus, rien ne se supprime.
"""

from django.db import models
from django.db.models import Q

from core.fields import MontantField
from core.models import ModeleOrganisation
from niveau1_socle.financements.models import Accord, Categorie


class TypeDemande(models.TextChoices):
    RETRAIT = "retrait", "Retrait"
    REAPPROVISIONNEMENT = "reapprovisionnement", "Réapprovisionnement"
    PAIEMENT_DIRECT = "paiement_direct", "Paiement direct"
    ENGAGEMENT_SPECIAL = "engagement_special", "Engagement spécial"


class StatutDemande(models.TextChoices):
    PREPAREE = "preparee", "Préparée"
    SOUMISE = "soumise", "Soumise"
    ACCEPTEE = "acceptee", "Acceptée"
    REJETEE = "rejetee", "Rejetée"
    CONTESTEE = "contestee", "Contestée"
    REMBOURSEE = "remboursee", "Remboursée"
    ANNULEE = "annulee", "Annulée"


# Statuts dont le montant pèse sur le plafond des catégories et sur l'accord.
STATUTS_COMPTES = (
    StatutDemande.SOUMISE,
    StatutDemande.ACCEPTEE,
    StatutDemande.CONTESTEE,
    StatutDemande.REMBOURSEE,
)


class DemandeRetrait(ModeleOrganisation):
    project_id = models.UUIDField(db_index=True)
    accord = models.ForeignKey(Accord, on_delete=models.PROTECT, related_name="demandes")
    numero = models.CharField(max_length=80)
    type = models.CharField(max_length=20, choices=TypeDemande.choices)
    status = models.CharField(
        max_length=10, choices=StatutDemande.choices, default=StatutDemande.PREPAREE
    )
    periode_debut = models.DateField()
    periode_fin = models.DateField()
    # Somme de ce qui est demandé au bailleur (`montant_a_retirer` des lignes).
    montant_total = MontantField(default=0)
    # Le profil de décaissement résolu à la date de la demande (L5-T03bis) : régime, seuils, taux.
    # Il est FIGÉ à la préparation ; sans profil (accord jamais paramétré), il reste vide.
    profil_version = models.ForeignKey(
        "niveau3_config.ProfilDecaissement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    pieces_exigees = models.JSONField(
        default=list, blank=True
    )  # soe | records | ifr | summary_sheet
    pieces_fournies = models.JSONField(default=list, blank=True)
    # La demande représentée pointe vers la rejetée dont elle reprend les dépenses.
    reprise_de = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reprises"
    )
    motif_rejet = models.TextField(blank=True, default="")
    motif_contestation = models.TextField(blank=True, default="")
    soumise_le = models.DateTimeField(null=True, blank=True)
    soumise_par = models.UUIDField(null=True, blank=True)
    cle_idempotence = models.CharField(max_length=100, null=True, blank=True)
    # L'état certifié de dépenses, figé à la soumission, et son empreinte SHA-256.
    etat_certifie = models.JSONField(null=True, blank=True)
    empreinte_etat = models.CharField(max_length=64, blank=True, default="")
    decidee_le = models.DateTimeField(null=True, blank=True)
    decidee_par = models.UUIDField(null=True, blank=True)

    class Meta:
        constraints = [
            # Unique PAR ACCORD : deux accords au format BAD ont chacun leur suite « 0001ABC… ».
            models.UniqueConstraint(
                fields=["org_id", "accord", "numero"], name="uq_demande_numero"
            ),
            models.UniqueConstraint(
                fields=["org_id", "cle_idempotence"],
                condition=Q(cle_idempotence__isnull=False),
                name="uq_demande_cle_idempotence",
            ),
            models.CheckConstraint(
                condition=Q(type__in=TypeDemande.values), name="demande_type_ferme"
            ),
            models.CheckConstraint(
                condition=Q(status__in=StatutDemande.values), name="demande_statut_ferme"
            ),
            models.CheckConstraint(
                condition=Q(periode_fin__gte=models.F("periode_debut")),
                name="demande_periode_coherente",
            ),
            models.CheckConstraint(
                condition=Q(montant_total__gte=0), name="demande_montant_positif"
            ),
            models.CheckConstraint(
                condition=Q(reprise_de__isnull=True) | ~Q(reprise_de=models.F("id")),
                name="demande_pas_sa_propre_reprise",
            ),
            # Un rejet et une contestation se motivent (`isnull` : un CHECK laisse passer NULL).
            models.CheckConstraint(
                condition=~Q(status=StatutDemande.REJETEE) | ~Q(motif_rejet=""),
                name="demande_motif_de_rejet_obligatoire",
            ),
            models.CheckConstraint(
                condition=~Q(status=StatutDemande.CONTESTEE) | ~Q(motif_contestation=""),
                name="demande_motif_de_contestation_obligatoire",
            ),
            models.CheckConstraint(
                condition=Q(status__in=[StatutDemande.PREPAREE, StatutDemande.ANNULEE])
                | (Q(etat_certifie__isnull=False) & ~Q(empreinte_etat="")),
                name="demande_etat_certifie_des_la_soumission",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.numero} ({self.status})"


class EtatLigneDemande(models.TextChoices):
    ACTIF = "actif", "Justifiée par la demande"
    ANNULE = "annule", "Libérée (demande annulée)"
    REJETE = "rejete", "Libérée (demande rejetée, reprise seulement)"


class LigneDemande(ModeleOrganisation):
    """Une dépense justifiée par une demande. Les valeurs sont celles du grand livre à la
    préparation : la base les vérifie et les recopie, l'appelant ne les dicte pas."""

    demande = models.ForeignKey(DemandeRetrait, on_delete=models.PROTECT, related_name="lignes")
    ligne_ecriture_id = models.UUIDField(db_index=True)
    categorie = models.ForeignKey(Categorie, on_delete=models.PROTECT, related_name="+")
    montant = MontantField()  # la dépense éligible, telle que le grand livre la porte
    # Ce qui est demandé au bailleur : dépense × taux de la règle (L5-T03bis). Sans profil, la
    # base le fixe à la dépense (taux de 100 %).
    montant_a_retirer = MontantField(default=0)
    # La règle de financement et le profil qui ont produit ce montant, PERSISTÉS : une réallocation
    # ultérieure ne rend jamais inexplicable une demande déjà soumise.
    regle_financement = models.ForeignKey(
        "niveau3_config.RegleFinancementCategorie",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    profil_version = models.ForeignKey(
        "niveau3_config.ProfilDecaissement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    taux_applique = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    piece = models.CharField(max_length=100, blank=True, default="")  # numéro de la pièce
    date_piece = models.DateField()
    # Le contrat que la dépense règle, quand elle en règle un (Lot 3-B) : il permet « une seule
    # devise par demande » et « même méthode pour les demandes d'un contrat » (manuel BAD, p. 25).
    contrat = models.ForeignKey(
        "marches.Contrat", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    etat = models.CharField(
        max_length=6, choices=EtatLigneDemande.choices, default=EtatLigneDemande.ACTIF
    )

    class Meta:
        constraints = [
            # LE contrôle anti-doublon : une dépense n'est justifiée que par une demande en cours.
            models.UniqueConstraint(
                fields=["ligne_ecriture_id"],
                condition=Q(etat=EtatLigneDemande.ACTIF),
                name="uq_lignedemande_une_demande_en_cours",
            ),
            models.UniqueConstraint(
                fields=["demande", "ligne_ecriture_id"], name="uq_lignedemande_une_fois"
            ),
            models.CheckConstraint(condition=Q(montant__gt=0), name="lignedemande_montant_positif"),
            models.CheckConstraint(
                condition=Q(montant_a_retirer__gte=0, montant_a_retirer__lte=models.F("montant")),
                name="lignedemande_retrait_dans_la_depense",
            ),
            # `isnull` explicite : une ligne sous profil porte sa règle, son profil et son taux,
            # une ligne hors profil n'en porte aucun (un CHECK laisse passer NULL).
            models.CheckConstraint(
                condition=(
                    Q(
                        regle_financement__isnull=True,
                        profil_version__isnull=True,
                        taux_applique__isnull=True,
                    )
                    | Q(
                        regle_financement__isnull=False,
                        profil_version__isnull=False,
                        taux_applique__isnull=False,
                    )
                ),
                name="lignedemande_regle_profil_taux_ensemble",
            ),
            models.CheckConstraint(
                condition=Q(etat__in=EtatLigneDemande.values), name="lignedemande_etat_ferme"
            ),
        ]


class MiseAEcart(ModeleOrganisation):
    """Une dépense écartée d'une demande, avec son motif : ce qu'on n'a PAS demandé se justifie."""

    demande = models.ForeignKey(DemandeRetrait, on_delete=models.PROTECT, related_name="ecarts")
    ligne_ecriture_id = models.UUIDField()
    motif = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["demande", "ligne_ecriture_id"], name="uq_ecart_une_fois"
            ),
            models.CheckConstraint(condition=~Q(motif=""), name="ecart_motif_obligatoire"),
        ]


class SoldeCategorie(ModeleOrganisation):
    """Le montant des demandes en cours sur une catégorie (et ses sous-catégories). Maintenu par la
    base ; verrouillé (`FOR UPDATE`) par toute soumission, ce qui sérialise les demandes qui se
    disputent le même disponible."""

    categorie = models.OneToOneField(Categorie, on_delete=models.PROTECT, related_name="solde")
    utilise = MontantField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(utilise__gte=0), name="soldecategorie_positif"),
        ]


class SoldeAccord(ModeleOrganisation):
    """Le montant des demandes en cours sur un accord, face à son montant courant."""

    accord = models.OneToOneField(Accord, on_delete=models.PROTECT, related_name="solde_demandes")
    utilise = MontantField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(utilise__gte=0), name="soldeaccord_positif"),
        ]
