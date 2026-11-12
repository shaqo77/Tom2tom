"""Langage restreint d'assertion de cohérence. Voir L0-T06.

Les assertions ne sont jamais évaluées directement comme du Python : on
recompile d'abord l'expression en un sous-arbre sécurisé, puis on utilise les
mêmes évaluateurs arithmétiques que pour les formules. L'objectif est de
n'autoriser aucune construction d'exécution, aucun SQL fourni par l'utilisateur
et aucune comparaison ambiguë, rien que ce qui peut faire échouer la
pubication avec un message nommé.
"""

import ast
import operator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .formules import FormuleInvalide, evaluer

# Comparaisons indifférentes, nécessaires pour les contrôles de cohérence.
COMPARATEURS = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}

# Nom réservé pour désigner un solde `BALANCE(...)` pendant l'évaluation.
SALTE_BALANCE = "__BALANCE_"


class AssertionInvalide(FormuleInvalide):
    """L'assertion propose un langage invalide ou dangereux."""


class AssertionsViolees(ValueError):
    """Une ou plusieurs assertions sont fausses. Propage le rapport complet."""

    def __init__(self, controles: list):
        self.controles = tuple(controles)
        self.violations = tuple(
            controle for controle in controles if not controle.reussi
        )
        messages = [
            f"{controle.rubrique}[{controle.colonne}]: {controle.expression} "
            f"({controle.operateur} {controle.droite}) => {controle.gauche} != {controle.droite}"
            for controle in self.violations
        ]
        super().__init__("Assertions de cohérence violées : " + " ; ".join(messages))


@dataclass(frozen=True)
class ControleAssertion:
    rubrique: str
    colonne: str
    expression: str
    reussi: bool
    gauche: Decimal
    droite: Decimal
    ecart: Decimal
    operateur: str


@dataclass(frozen=True)
class AssertionPreparee:
    expression: str
    operateur: str
    noms_balances: dict[str, str]
    prefixes: tuple[str, ...]
    codes_sources: list[str]

