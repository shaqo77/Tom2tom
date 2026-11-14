"""Les profils de bailleurs : une bibliothèque réutilisable, jamais une obligation. Voir L5-T05.

Un profil met des exigences À DISPOSITION d'un projet ; ce sont les documents contractuels du projet
qui décident lesquelles s'appliquent. Importer un profil ne produit donc que des exigences
`proposed` (voir `services.importer_profil` et le déclencheur de la migration 0002).
"""

from django.db import models
from django.db.models import Q

from core.models import ModeleOrganisation

MENTION_LORSQUE_REQUIS = "lorsque requis"


class StatutProfilBailleur(models.TextChoices):
    BROUILLON = "draft", "Brouillon"
    PUBLIE = "published", "Publié"


class TypeElement(models.TextChoices):
    REFERENCE_DOCUMENTAIRE = "document_reference", "Référence documentaire"
    FAMILLE_ETATS = "report_family", "Famille d'états"
    MODELE = "report_template", "Modèle de rapport"
    PRESENTATION = "presentation_rule", "Règle de présentation"
    PERIODICITE = "periodicity", "Périodicité et délai type"
    CONTROLE = "check", "Contrôle"
    FORMAT = "export_format", "Format d'exportation"
    NOMENCLATURE = "nomenclature", "Nomenclature"


class ProfilBailleur(ModeleOrganisation):
    """Un profil, versionné : une fois publié, il ne change plus (on en publie une version)."""

    bailleur = models.ForeignKey(
        "financements.Bailleur",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="profils_bibliotheque",
    )
    code = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1)
    label = models.JSONField()  # {"fr": …, "en": …}
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=10, choices=StatutProfilBailleur.choices, default=StatutProfilBailleur.BROUILLON
    )
    published_by = models.UUIDField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org_id", "code", "version"], name="uq_profil_bailleur_version"
            ),
            models.CheckConstraint(
                condition=Q(status__in=StatutProfilBailleur.values),
                name="profil_bailleur_statut_ferme",
            ),
            models.CheckConstraint(
                condition=~Q(status=StatutProfilBailleur.PUBLIE)
                | Q(published_by__isnull=False, published_at__isnull=False),
                name="profil_bailleur_publication_tracee",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} v{self.version}"


class ElementProfil(ModeleOrganisation):
    """Un élément de la bibliothèque. S'il porte une `exigence`, l'importer en propose une."""

    profil = models.ForeignKey(ProfilBailleur, on_delete=models.CASCADE, related_name="elements")
    kind = models.CharField(max_length=24, choices=TypeElement.choices)
    code = models.CharField(max_length=64)
    label = models.JSONField()
    contenu = models.JSONField(default=dict)
    # {"subject", "rule", "obligation", "periodicity", "due_offset_days", "condition_expr"}
    exigence = models.JSONField(null=True, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "code"]
        constraints = [
            models.UniqueConstraint(fields=["profil", "kind", "code"], name="uq_element_profil"),
            models.CheckConstraint(
                condition=Q(kind__in=TypeElement.values), name="element_profil_type_ferme"
            ),
        ]

    @property
    def mention(self) -> str:
        """Aucun élément n'est un modèle universel : le document du projet décide (L5-T06)."""
        return MENTION_LORSQUE_REQUIS

    def __str__(self) -> str:
        return f"{self.profil_id}/{self.kind}/{self.code}"
