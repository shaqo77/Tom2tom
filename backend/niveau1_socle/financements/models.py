"""Bailleurs, accords, catégories, comptes bancaires, avenants. Voir L4-T04.

    Bailleur ─▶ Accord (prêt | don | contrepartie) ─▶ Catégorie ─▶ Sous-catégorie
                  ├─▶ Compte bancaire (désigné, spécial, opérationnel, contrepartie, transit)
                  └─▶ Avenants (jamais de modification en place : ils portent la nouvelle valeur)

Deux accords d'un même bailleur sur un même projet coexistent sans rien partager : chaque accord a
ses catégories et ses paramètres.
"""

from django.db import models
from django.db.models import Q

from core.fields import MontantField
from core.models import ModeleOrganisation
from niveau1_socle.referentiels.models import Devise
from niveau3_config.models import DocumentReference


class Bailleur(ModeleOrganisation):
    code = models.CharField(max_length=32)
    nom = models.CharField(max_length=255)
    pays = models.CharField(max_length=2, blank=True, default="")  # ISO 3166-1 alpha-2
    actif = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org_id", "code"], name="uq_bailleur_code"),
            models.CheckConstraint(
                condition=Q(pays="") | Q(pays__regex=r"^[A-Z]{2}$"), name="bailleur_pays_iso2"
            ),
        ]

    def __str__(self) -> str:
        return self.code


class NatureAccord(models.TextChoices):
    PRET = "pret", "Prêt"
    DON = "don", "Don"
    CONTREPARTIE = "contrepartie", "Contrepartie"


class StatutAccord(models.TextChoices):
    BROUILLON = "brouillon", "Brouillon"
    ACTIF = "actif", "Actif"
    SUSPENDU = "suspendu", "Suspendu"
    CLOS = "clos", "Clos"
    ANNULE = "annule", "Annulé"


class Accord(ModeleOrganisation):
    """Un accord de financement. Le montant COURANT est celui du dernier avenant, sinon le montant
    initial : l'accord lui-même ne change pas de montant (voir `montant_courant`).

    Un accord suspendu refuse toute nouvelle imputation et toute nouvelle demande de décaissement,
    sans être clos ; ses opérations historiques restent consultables.
    """

    project_id = models.UUIDField(db_index=True)
    bailleur = models.ForeignKey(Bailleur, on_delete=models.PROTECT, related_name="accords")
    numero = models.CharField(max_length=60)
    libelle = models.CharField(max_length=255, blank=True, default="")
    nature = models.CharField(max_length=12, choices=NatureAccord.choices)
    status = models.CharField(
        max_length=9, choices=StatutAccord.choices, default=StatutAccord.BROUILLON
    )
    devise = models.ForeignKey(Devise, on_delete=models.PROTECT, related_name="+")
    montant_initial = MontantField()
    date_effet = models.DateField(null=True, blank=True)
    date_fin_eligibilite = models.DateField(null=True, blank=True)
    date_cloture = models.DateField(null=True, blank=True)
    date_limite_decaissement = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org_id", "numero"], name="uq_accord_numero"),
            models.CheckConstraint(
                condition=Q(montant_initial__gte=0), name="accord_montant_positif"
            ),
            models.CheckConstraint(
                condition=Q(nature__in=NatureAccord.values), name="accord_nature_fermee"
            ),
            models.CheckConstraint(
                condition=Q(status__in=StatutAccord.values), name="accord_statut_ferme"
            ),
            # date d'effet <= fin d'éligibilité <= clôture <= limite de décaissement, quand elles
            # sont renseignées : les six paires, pour qu'une date vide ne dispense de rien.
            *(
                models.CheckConstraint(
                    condition=Q(**{f"{a}__isnull": True})
                    | Q(**{f"{b}__isnull": True})
                    | Q(**{f"{a}__lte": models.F(b)}),
                    name=f"accord_dates_{i}",
                )
                for i, (a, b) in enumerate(
                    [
                        ("date_effet", "date_fin_eligibilite"),
                        ("date_effet", "date_cloture"),
                        ("date_effet", "date_limite_decaissement"),
                        ("date_fin_eligibilite", "date_cloture"),
                        ("date_fin_eligibilite", "date_limite_decaissement"),
                        ("date_cloture", "date_limite_decaissement"),
                    ]
                )
            ),
        ]

    def __str__(self) -> str:
        return f"{self.numero} ({self.status})"


class Categorie(ModeleOrganisation):
    """Catégorie de dépenses d'un accord, avec ses sous-catégories (`parent`).

    Son identité est son `code` DANS l'accord : stable d'une version de profil de décaissement à
    l'autre (les versions de profil, L5, référencent le code, jamais un identifiant interne).
    """

    accord = models.ForeignKey(Accord, on_delete=models.PROTECT, related_name="categories")
    code = models.CharField(max_length=32)
    label = models.JSONField()  # {"fr": …, "en": …}
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="enfants"
    )
    plafond = MontantField(null=True, blank=True)
    devise = models.ForeignKey(Devise, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["accord", "code"], name="uq_categorie_code"),
            models.CheckConstraint(
                condition=Q(plafond__isnull=True) | Q(plafond__gte=0),
                name="categorie_plafond_positif",
            ),
            models.CheckConstraint(
                condition=Q(parent__isnull=True) | ~Q(parent=models.F("id")),
                name="categorie_pas_son_propre_parent",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.accord.numero}/{self.code}"


class AvenantAccord(ModeleOrganisation):
    """Un avenant : il PORTE la nouvelle valeur, il ne modifie jamais l'accord en place."""

    accord = models.ForeignKey(Accord, on_delete=models.PROTECT, related_name="avenants")
    reference = models.CharField(max_length=60)
    date_avenant = models.DateField()
    document = models.ForeignKey(DocumentReference, on_delete=models.PROTECT, related_name="+")
    montant_revise = MontantField()
    motif = models.TextField(blank=True, default="")
    # La version de profil de décaissement créée à la suite (L5-T04bis) : UUID jusqu'à son lot.
    profile_version_id = models.UUIDField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["accord", "reference"], name="uq_avenant_reference"),
            models.CheckConstraint(
                condition=Q(montant_revise__gte=0), name="avenant_montant_positif"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.accord.numero}/{self.reference}"


class TypeCompte(models.TextChoices):
    DESIGNE = "designe", "Compte désigné"
    SPECIAL = "special", "Compte spécial"
    OPERATIONNEL = "operationnel", "Compte opérationnel"
    CONTREPARTIE = "contrepartie", "Compte de contrepartie"
    TRANSIT = "transit", "Compte de transit"


class CompteBancaire(ModeleOrganisation):
    """Un compte bancaire du projet. Le NUMÉRO COMPLET n'est lisible que d'une habilitation dédiée
    (`voir_numero_compte`) et chaque lecture est journalisée ; partout ailleurs, `numero_masque`.
    """

    project_id = models.UUIDField(db_index=True)
    accord = models.ForeignKey(
        Accord, null=True, blank=True, on_delete=models.PROTECT, related_name="comptes"
    )
    code = models.CharField(max_length=32)
    libelle = models.CharField(max_length=255, blank=True, default="")
    type = models.CharField(max_length=12, choices=TypeCompte.choices)
    devise = models.ForeignKey(Devise, on_delete=models.PROTECT, related_name="+")
    banque = models.CharField(max_length=120)
    numero = models.CharField(max_length=64)
    plafond = MontantField(null=True, blank=True)
    seuil_reapprovisionnement = MontantField(null=True, blank=True)
    actif = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org_id", "code"], name="uq_comptebancaire_code"),
            models.UniqueConstraint(fields=["org_id", "numero"], name="uq_comptebancaire_numero"),
            models.CheckConstraint(
                condition=Q(type__in=TypeCompte.values), name="comptebancaire_type_ferme"
            ),
            models.CheckConstraint(
                condition=Q(plafond__isnull=True) | Q(plafond__gte=0),
                name="comptebancaire_plafond_positif",
            ),
            models.CheckConstraint(
                condition=Q(seuil_reapprovisionnement__isnull=True)
                | Q(seuil_reapprovisionnement__gte=0),
                name="comptebancaire_seuil_positif",
            ),
            models.CheckConstraint(
                condition=Q(plafond__isnull=True)
                | Q(seuil_reapprovisionnement__isnull=True)
                | Q(seuil_reapprovisionnement__lte=models.F("plafond")),
                name="comptebancaire_seuil_sous_plafond",
            ),
        ]

    @property
    def numero_masque(self) -> str:
        return masquer_numero(self.numero)

    def __str__(self) -> str:  # jamais le numéro complet : ce texte finit dans les journaux
        return f"{self.code} ({self.banque} {self.numero_masque})"

    def __repr__(self) -> str:
        return f"<CompteBancaire {self.code} {self.numero_masque}>"


def masquer_numero(numero: str) -> str:
    """Ne laisse voir que les quatre derniers caractères."""
    reste = (numero or "")[-4:]
    return "•" * max(len(numero or "") - len(reste), 0) + reste
