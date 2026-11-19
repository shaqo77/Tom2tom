"""La reprise de données : balance d'origine, pièces reprises, rapport signé. Voir L8-T01/T02.

Une reprise est acceptée à ÉCART NUL sur la balance générale ET sur le cumul par accord, et par une
signature nominative d'une autre personne que celle qui l'a ouverte.
"""

from django.db import models
from django.db.models import Q

from core.fields import MontantField
from core.models import ModeleOrganisation


class ModeReprise(models.TextChoices):
    OUVERTURE = "ouverture", "Soldes d'ouverture"
    HISTORIQUE = "historique", "Historique des écritures"


class StatutReprise(models.TextChoices):
    EN_COURS = "en_cours", "En cours"
    REFUSEE = "refusee", "Refusée (écart non nul)"
    CONTROLEE = "controlee", "Contrôlée à écart nul"
    ACCEPTEE = "acceptee", "Acceptée et signée"


class Reprise(ModeleOrganisation):
    project_id = models.UUIDField(db_index=True)
    nom = models.CharField(max_length=200)
    date_bascule = models.DateField()
    devise = models.CharField(max_length=3)  # la monnaie de tenue de la reprise
    mode = models.CharField(max_length=10, choices=ModeReprise.choices, null=True, blank=True)
    statut = models.CharField(
        max_length=10, choices=StatutReprise.choices, default=StatutReprise.EN_COURS
    )
    balance_sha256 = models.BinaryField(null=True, blank=True)  # empreinte du fichier de balance
    cree_par = models.UUIDField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(statut__in=StatutReprise.values), name="reprise_statut_ferme"
            ),
            models.CheckConstraint(
                condition=Q(mode__isnull=True) | Q(mode__in=ModeReprise.values),
                name="reprise_mode_ferme",
            ),
        ]


class LigneBalanceOrigine(ModeleOrganisation):
    """Une ligne de la balance d'origine (celle du progiciel quitté), agrégée par clé."""

    reprise = models.ForeignKey(Reprise, on_delete=models.PROTECT, related_name="balance")
    compte = models.CharField(max_length=20)
    accord = models.CharField(max_length=60, blank=True, default="")
    axe1 = models.CharField(max_length=20, blank=True, default="")
    debit = MontantField(default=0)
    credit = MontantField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["reprise", "compte", "accord", "axe1"], name="uq_balance_origine_cle"
            ),
            models.CheckConstraint(
                condition=Q(debit__gte=0, credit__gte=0), name="balance_origine_positive"
            ),
        ]


class PieceReprise(ModeleOrganisation):
    """Une pièce de l'historique source et l'écriture qu'elle a produite.

    `cle` identifie la pièce DANS LA SOURCE (journal, numéro, date) ; `contenu_sha256` en empreinte
    les lignes. Rejouer l'import retrouve la pièce par sa clé : même contenu, rien à faire ;
    contenu différent, c'est un CONFLIT signalé, jamais un écrasement ni un doublon.
    """

    reprise = models.ForeignKey(Reprise, on_delete=models.PROTECT, related_name="pieces")
    cle = models.CharField(max_length=64)
    contenu_sha256 = models.BinaryField()
    ecriture_id = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["reprise", "cle"], name="uq_piece_reprise_cle"),
        ]


class RapportReprise(ModeleOrganisation):
    """Le rapport du contrôle d'une reprise : écarts ligne à ligne, signature nominative."""

    reprise = models.ForeignKey(Reprise, on_delete=models.PROTECT, related_name="rapports")
    accepte = models.BooleanField()  # écart nul sur la balance générale ET le cumul par accord
    ecart_general = MontantField()  # somme des écarts absolus par compte
    ecart_accords = MontantField()  # somme des écarts absolus par accord
    nombre_ecritures = models.PositiveIntegerField()
    ecarts = models.JSONField()  # une entrée par écart : dimension, clé, origine, reprise, écart
    contenu_sha256 = models.BinaryField()
    signe_par = models.UUIDField(null=True, blank=True)
    signe_nom = models.CharField(max_length=150, blank=True, default="")
    signe_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(signe_par__isnull=True) & Q(signe_le__isnull=True) & Q(signe_nom=""))
                | (Q(signe_par__isnull=False) & Q(signe_le__isnull=False) & ~Q(signe_nom="")),
                name="rapport_reprise_signature_complete",
            ),
            # On ne signe que ce qui est accepté : un rapport à écart non nul ne se signe pas.
            models.CheckConstraint(
                condition=Q(signe_par__isnull=True) | Q(accepte=True),
                name="rapport_reprise_signe_seulement_si_accepte",
            ),
        ]
