"""Le disponible budgétaire : lecture, vérification, reconstruction. Voir L4-T02.

    disponible = Σ lignes de la version approuvée courante
               − Σ engagements non apurés
               − Σ lignes d'écriture comptabilisées

Les soldes sont tenus par la base (voir la migration 0004). Ce module les LIT, les COMPARE au calcul
complet et les RECONSTRUIT. Toute divergence est une alerte : écrite au journal d'audit et au
journal technique, et la commande `verifier_soldes` sort en erreur.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import connection, transaction

from core.audit import journaliser

from .models import SoldeBudgetaire

alerte = logging.getLogger("sigf.budget.alerte")
ZERO = Decimal(0)


@dataclass(frozen=True)
class Divergence:
    ligne_id: object
    project_id: object
    consomme_incremental: Decimal
    consomme_calcule: Decimal
    engage_incremental: Decimal
    engage_calcule: Decimal


@dataclass(frozen=True)
class SituationLigne:
    solde: SoldeBudgetaire
    budget: Decimal
    engage: Decimal
    consomme: Decimal

    @property
    def disponible(self) -> Decimal:
        return self.budget - self.engage - self.consomme


def situation(project_id) -> list[SituationLigne]:
    """Une rangée par ligne de la version approuvée courante : budget, engagé, consommé."""
    soldes = SoldeBudgetaire.objects.filter(
        project_id=project_id, version__status="approuve"
    ).select_related("ligne", "version")
    return [
        SituationLigne(s, s.ligne.montant_base, s.engage, s.consomme)
        for s in soldes.order_by("ligne__annee", "ligne__periode", "ligne__id")
    ]


def disponible_total(project_id) -> Decimal:
    """Somme des disponibles des lignes de la version courante (peut compter deux fois une même
    dépense couverte par deux lignes : utile par ligne, pas comme grand total)."""
    return sum((rangee.disponible for rangee in situation(project_id)), ZERO)


def comparer_soldes(project_id=None) -> list[Divergence]:
    """Compare le solde incrémental au calcul complet ; vide si tout concorde."""
    with connection.cursor() as cur:
        cur.execute(
            """SELECT COALESCE(s.ligne_id, c.ligne_id), s.project_id,
                      s.consomme, c.consomme, s.engage, c.engage
                 FROM (SELECT s.* FROM budget_soldebudgetaire s
                         JOIN budget_versionbudget v ON v.id = s.version_id
                                                    AND v.status = 'approuve'
                        WHERE %s::uuid IS NULL OR s.project_id = %s::uuid) s
                 FULL JOIN budget_calculer_soldes(%s::uuid) c ON c.ligne_id = s.ligne_id
                WHERE s.ligne_id IS NULL OR c.ligne_id IS NULL
                   OR s.consomme <> c.consomme OR s.engage <> c.engage
                ORDER BY 1""",
            [project_id, project_id, project_id],
        )
        return [
            Divergence(ligne, projet, ci or ZERO, cc or ZERO, ei or ZERO, ec or ZERO)
            for ligne, projet, ci, cc, ei, ec in cur.fetchall()
        ]


def verifier_soldes(org_id, project_id=None, *, acteur_id=None) -> list[Divergence]:
    """Comparaison + alerte : toute divergence est tracée au journal d'audit et signalée."""
    divergences = comparer_soldes(project_id)
    if divergences:
        alerte.error("Soldes budgétaires divergents : %d ligne(s)", len(divergences))
        journaliser(
            org_id=org_id,
            actor_id=acteur_id,
            action="budget_balance_divergence",
            object_type="solde_budgetaire",
            object_id=divergences[0].ligne_id,
            project_id=project_id,
            after={
                "lignes": len(divergences),
                "exemples": [
                    {
                        "ligne": str(d.ligne_id),
                        "consomme": [str(d.consomme_incremental), str(d.consomme_calcule)],
                        "engage": [str(d.engage_incremental), str(d.engage_calcule)],
                    }
                    for d in divergences[:10]
                ],
            },
        )
    return divergences


def recalculer_soldes(org_id, project_id=None, *, acteur_id=None) -> list[Divergence]:
    """Reconstruit TOUS les soldes depuis le grand livre et les engagements.

    Retourne ce qui était divergent avant la correction (vide si rien n'avait dérivé). Une
    correction est une alerte comme une autre : tracée, jamais silencieuse.
    """
    with transaction.atomic():
        divergences = verifier_soldes(org_id, project_id, acteur_id=acteur_id)
        with connection.cursor() as cur:
            cur.execute(
                """UPDATE budget_soldebudgetaire s
                      SET consomme = c.consomme, engage = c.engage, updated_at = now()
                     FROM budget_calculer_soldes(%s::uuid) c
                    WHERE c.ligne_id = s.ligne_id
                      AND (s.consomme <> c.consomme OR s.engage <> c.engage)""",
                [project_id],
            )
        journaliser(
            org_id=org_id,
            actor_id=acteur_id,
            action="budget_balances_recalculated",
            object_type="solde_budgetaire",
            object_id=None,
            project_id=project_id,
            after={"corriges": len(divergences)},
        )
    return divergences
