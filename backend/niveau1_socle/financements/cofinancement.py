"""Cofinancement : l'arithmétique de la ventilation. Voir L4-T05.

La tâche où une erreur détruit la confiance du client : le total est TOUJOURS conservé, au
centime, pour tout montant, toute clé, toute devise.

Trois règles, toutes prouvées par un test de propriété :

1. Les parts d'une clé sont NORMALISÉES pour sommer EXACTEMENT à 1 : la dernière se calcule par
   différence, jamais par division (`normaliser_parts`).
2. Chaque part est arrondie VERS ZÉRO (`ROUND_DOWN`) : la somme des parts ne dépasse jamais le
   montant, donc le reliquat n'est jamais négatif et il n'y a jamais de montant à retrancher.
3. Le reliquat (quelques pas de la devise, au plus un par part) va à un porteur d'arrondi désigné
   dans la clé, jamais à un accord tiré au hasard : deux ventilations du même montant donnent
   toujours le même résultat.

Le pas d'arrondi est celui de la DEVISE (0,01 pour deux décimales, 1 pour le franc de Djibouti), pas
un centime codé en dur : en franc de Djibouti, 0,01 n'existe pas.
"""

from collections.abc import Iterable, Sequence
from decimal import ROUND_DOWN, Decimal

from core.i18n import msg

CENTIME = Decimal("0.01")
PRECISION_PART = Decimal("0.0000000001")  # dix décimales : celles de la colonne `share`
UN = Decimal(1)
ZERO = Decimal(0)


class VentilationImpossible(ValueError):
    """Les entrées ne permettent pas une ventilation conservative."""


def pas_de_devise(decimales: int) -> Decimal:
    """Le plus petit montant exprimable dans une devise : 1, 0,1, 0,01, 0,001…"""
    return Decimal(1).scaleb(-decimales)


def normaliser_parts(poids: Sequence[int | Decimal]) -> list[Decimal]:
    """Transforme des poids (60, 30, 10) en parts qui somment EXACTEMENT à 1.

    Toutes les parts sauf la dernière sont arrondies vers zéro à dix décimales ; la dernière est la
    différence à 1. Jamais de division finale : la somme est exacte par construction.
    """
    poids = [Decimal(str(p)) for p in poids]
    if not poids or any(p <= 0 for p in poids):
        raise VentilationImpossible(msg("cofinancement.cle_moins_part_chaque_poids"))
    total = sum(poids, ZERO)
    parts = [(p / total).quantize(PRECISION_PART, rounding=ROUND_DOWN) for p in poids[:-1]]
    parts.append(UN - sum(parts, ZERO))
    return parts


def ventiler(
    montant: Decimal,
    parts: Iterable[tuple[object, Decimal]],
    porteur,
    pas: Decimal = CENTIME,
) -> list[tuple[object, Decimal]]:
    """Répartit `montant` entre des accords selon `parts` `[(accord, part), …]`.

    Le total est conservé : la somme des montants rendus égale `montant`, exactement. Un montant
    négatif (remboursement, contre-passation) est le miroir exact de la ventilation de son opposé.
    Le montant doit être un multiple de `pas`.
    """
    montant = Decimal(montant)
    parts = [(accord, Decimal(part)) for accord, part in parts]
    if not parts:
        raise VentilationImpossible(msg("cofinancement.cle_cofinancement_moins_part"))
    if sum((part for _, part in parts), ZERO) != UN or any(part <= 0 for _, part in parts):
        raise VentilationImpossible(msg("cofinancement.parts_doivent_etre_positives_sommer"))
    if porteur not in {accord for accord, _ in parts}:
        raise VentilationImpossible(msg("cofinancement.porteur_arrondi_doit_etre_accords"))
    if montant != montant.quantize(pas):
        raise VentilationImpossible(
            msg("cofinancement.montant_multiple_devise", montant=montant, pas=pas)
        )
    if montant < 0:
        return [(accord, -part) for accord, part in ventiler(-montant, parts, porteur, pas)]

    ventile = [
        (accord, (montant * part).quantize(pas, rounding=ROUND_DOWN)) for accord, part in parts
    ]
    reliquat = montant - sum((m for _, m in ventile), ZERO)  # jamais négatif avec ROUND_DOWN
    ventile = [(a, m + reliquat) if a == porteur else (a, m) for a, m in ventile]

    if sum((m for _, m in ventile), ZERO) != montant or any(m < 0 for _, m in ventile):
        # Garde-fou explicite (un `assert` disparaît avec `python -O`) : ne doit jamais arriver.
        raise VentilationImpossible("Ventilation non conservative")
    return ventile
