"""Le contrôle budgétaire. Voir L4-T03.

Mode paramétrable PAR AXE et par projet : `bloquant`, `avertissement` ou `inactif`. Certains
bailleurs exigent le blocage, d'autres l'interdisent : la souplesse est une exigence contractuelle.

Appliqué à la VALIDATION d'une écriture et à l'OUVERTURE d'un engagement. Une opération dépasse une
ligne de budget quand son effet net dépasse le disponible de cette ligne (budget − engagé −
consommé) ; une opération qui restitue du budget (contre-passation, crédit) ne dépasse jamais.

Quel mode pour une ligne de budget ? Celui de ses axes : une ligne qui renseigne composante et
catégorie est soumise au plus strict des deux modes ; une ligne sans axe, à celui de l'axe
« projet ». Un axe sans paramétrage est en `avertissement` : on informe sans bloquer, puisque le
blocage est une exigence qu'une organisation choisit et qu'aucune n'est activée d'office.

Limite connue : seules les lignes de budget qui COUVRENT l'opération sont contrôlées. Une dépense
qu'aucune ligne ne couvre échappe au contrôle (elle apparaît « hors budget » dans les écarts).
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import connection, transaction

from core.audit import journaliser

from .models import AXES_CONTROLE, ControleBudgetaire, ModeControle
from .services import BudgetInvalide, _habilite

ZERO = Decimal(0)
MODE_PAR_DEFAUT = ModeControle.AVERTISSEMENT
RIGUEUR = {ModeControle.INACTIF: 0, ModeControle.AVERTISSEMENT: 1, ModeControle.BLOQUANT: 2}
# colonnes de la ligne de budget -> axe de contrôle
COLONNES_AXES = (
    ("dim1_id", "dim1"),
    ("dim2_id", "dim2"),
    ("dim3_id", "dim3"),
    ("dim4_id", "dim4"),
    ("agreement_id", "agreement"),
    ("category_id", "category"),
    ("site_id", "site"),
)


@dataclass(frozen=True)
class Depassement:
    ligne_id: object
    axes: tuple[str, ...]  # axes renseignés par la ligne de budget
    mode: str
    budget: Decimal
    engage: Decimal
    consomme: Decimal
    impact: Decimal

    @property
    def disponible(self) -> Decimal:
        return self.budget - self.engage - self.consomme

    @property
    def depassement(self) -> Decimal:
        """De combien la ligne serait dépassée une fois l'opération prise en compte."""
        return self.engage + self.consomme + self.impact - self.budget

    def __str__(self) -> str:
        axes = "+".join(self.axes) or "projet"
        return (
            f"ligne {axes} : disponible {self.disponible}, opération {self.impact}, "
            f"dépassement {self.depassement}"
        )


@dataclass
class ResultatControle:
    bloquants: list[Depassement] = field(default_factory=list)
    avertissements: list[Depassement] = field(default_factory=list)

    @property
    def conforme(self) -> bool:
        return not self.bloquants and not self.avertissements


class DepassementBudgetaire(ValueError):
    """Un contrôle `bloquant` refuse l'opération."""

    def __init__(self, depassements: list[Depassement]):
        self.depassements = depassements
        super().__init__(
            "Dépassement budgétaire bloquant : " + " ; ".join(str(d) for d in depassements)
        )


def mode_effectif(project_id, axe: str, date: datetime.date) -> str:
    """Le mode en vigueur à `date` pour un axe, ou le mode par défaut."""
    version = (
        ControleBudgetaire.objects.filter(project_id=project_id, axe=axe, valid_from__lte=date)
        .exclude(valid_to__lte=date)
        .first()
    )
    return version.mode if version else MODE_PAR_DEFAUT


def parametrer_controle(
    *, utilisateur, project_id, axe: str, mode: str, date_effet: datetime.date, motif: str = ""
) -> ControleBudgetaire:
    """Règle le mode d'un axe à partir de `date_effet` : clôt la version en cours, en ouvre une.

    Habilitation `parametrer`. Jamais de modification en place.
    """
    if axe not in AXES_CONTROLE:
        raise BudgetInvalide(f"axe de contrôle inconnu : {axe}")
    if mode not in ModeControle.values:
        raise BudgetInvalide(f"mode de contrôle inconnu : {mode}")
    _habilite(utilisateur, "parametrer", project_id)
    with transaction.atomic():
        with connection.cursor() as cur:  # une seule modification à la fois par axe
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                [f"controle:{project_id}:{axe}"],
            )
        versions = ControleBudgetaire.objects.filter(project_id=project_id, axe=axe)
        en_cours = versions.filter(valid_to__isnull=True).first()
        if en_cours is not None:
            if date_effet <= en_cours.valid_from:
                raise BudgetInvalide(
                    f"La nouvelle version doit prendre effet après le {en_cours.valid_from} "
                    "(début de la version en cours)"
                )
            ControleBudgetaire.objects.filter(pk=en_cours.pk).update(valid_to=date_effet)
        numero = (versions.order_by("-version").values_list("version", flat=True).first() or 0) + 1
        nouvelle = ControleBudgetaire.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            axe=axe,
            mode=mode,
            version=numero,
            valid_from=date_effet,
            motif=(motif or "").strip(),
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=nouvelle.org_id,
            actor_id=utilisateur.id,
            action="budget_control_configured",
            object_type="controle_budgetaire",
            object_id=nouvelle.id,
            project_id=project_id,
            before={"mode": en_cours.mode if en_cours else None},
            after={"axe": axe, "mode": mode, "valid_from": str(date_effet), "motif": motif},
        )
    return nouvelle


def _classer(project_id, date, rangees) -> ResultatControle:
    """Classe les lignes (budget, engagé, consommé, impact, axes) en bloquants ou avertissements."""
    resultat = ResultatControle()
    modes: dict[str, str] = {}
    for ligne_id, budget, engage, consomme, impact, *drapeaux in rangees:
        if impact <= 0:
            continue  # une opération qui restitue du budget ne dépasse jamais
        axes = tuple(
            axe for (_, axe), present in zip(COLONNES_AXES, drapeaux, strict=True) if present
        )
        mode = ModeControle.INACTIF
        for axe in axes or ("projet",):
            modes.setdefault(axe, mode_effectif(project_id, axe, date))
            if RIGUEUR[modes[axe]] >= RIGUEUR[mode]:
                mode = modes[axe]
        depassement = Depassement(ligne_id, axes, mode, budget, engage, consomme, impact)
        if depassement.depassement <= 0 or mode == ModeControle.INACTIF:
            continue
        (resultat.bloquants if mode == ModeControle.BLOQUANT else resultat.avertissements).append(
            depassement
        )
    return resultat


_DRAPEAUX = ", ".join(f"b.{colonne} IS NOT NULL" for colonne, _ in COLONNES_AXES)
_GROUPE = ", ".join(f"b.{colonne}" for colonne, _ in COLONNES_AXES)


def evaluer_ecriture(ecriture) -> ResultatControle:
    """Confronte une écriture (ses charges budgétées) aux lignes de budget qui la couvrent."""
    with connection.cursor() as cur:
        cur.execute(
            f"""SELECT b.id, b.montant_base, s.engage, s.consomme,
                       SUM(l.debit - l.credit), {_DRAPEAUX}
                  FROM comptabilite_ligneecriture l
                  JOIN referentiels_compte c ON c.id = l.account_id
                  JOIN exercices_exercice ex ON ex.id = %s
                  JOIN exercices_periode pe ON pe.id = %s
                  JOIN budget_versionbudget v ON v.project_id = %s AND v.status = 'approuve'
                  JOIN budget_lignebudget b ON b.version_id = v.id
                  JOIN budget_soldebudgetaire s ON s.ligne_id = b.id
                 WHERE l.entry_id = %s
                   AND budget_compte_budgete(c.code, c.classe)
                   AND budget_ligne_couvre(b, ex.annee, pe.numero, l.dim1_id, l.dim2_id, l.dim3_id,
                                           l.dim4_id, l.agreement_id, l.category_id, l.site_id)
                 GROUP BY b.id, b.montant_base, s.engage, s.consomme, {_GROUPE}
                 ORDER BY b.id""",  # noqa: S608
            [ecriture.exercice_id, ecriture.periode_id, ecriture.project_id, ecriture.pk],
        )
        rangees = cur.fetchall()
    return _classer(ecriture.project_id, ecriture.accounting_date, rangees)


def evaluer_engagement(
    project_id,
    *,
    annee,
    periode,
    montant,
    dim_ids=(None, None, None, None),
    agreement_id=None,
    category_id=None,
    site_id=None,
    date: datetime.date | None = None,
    verrouiller: bool = False,
) -> ResultatControle:
    """Confronte un engagement envisagé aux lignes de budget qui le couvrent.

    `verrouiller` pose un verrou de ligne sur les soldes concernés : deux engagements simultanés
    sur le même disponible ne passent pas ensemble.
    """
    with connection.cursor() as cur:
        cur.execute(
            f"""SELECT b.id, b.montant_base, s.engage, s.consomme, %s::numeric, {_DRAPEAUX}
                  FROM budget_versionbudget v
                  JOIN budget_lignebudget b ON b.version_id = v.id
                  JOIN budget_soldebudgetaire s ON s.ligne_id = b.id
                 WHERE v.project_id = %s AND v.status = 'approuve'
                   AND budget_ligne_couvre(b, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                 ORDER BY b.id {"FOR UPDATE OF s" if verrouiller else ""}""",  # noqa: S608
            [
                Decimal(str(montant)),
                project_id,
                annee,
                periode,
                *dim_ids,
                agreement_id,
                category_id,
                site_id,
            ],
        )
        rangees = cur.fetchall()
    return _classer(project_id, date or datetime.date.today(), rangees)


def appliquer(resultat: ResultatControle, *, utilisateur, objet_type, objet_id, project_id) -> list:
    """Bloque si un contrôle bloquant est franchi ; sinon trace les avertissements.

    Retourne la liste des avertissements (texte) pour l'appelant.
    """
    if resultat.bloquants:
        # Pas de trace d'audit ici : le refus annule la transaction de l'appelant, trace comprise.
        raise DepassementBudgetaire(resultat.bloquants)
    textes = [str(d) for d in resultat.avertissements]
    if textes:
        journaliser(
            org_id=utilisateur.org_id,
            actor_id=utilisateur.id,
            action="budget_overrun_warning",
            object_type=objet_type,
            object_id=objet_id,
            project_id=project_id,
            after={"lignes": textes},
        )
    return textes
