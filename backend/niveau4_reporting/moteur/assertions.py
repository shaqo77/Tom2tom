"""Langage restreint d'assertion de cohérence. Voir L0-T06.

Une assertion est une promesse que l'état se fait à lui-même : « cette
rubrique vaut le solde des comptes de trésorerie », par exemple. Elle est
vérifiée à la génération, colonne par colonne, et sa violation **bloque** la
publication au lieu d'être consignée quelque part où personne ne la lira.

SÉCURITÉ — lisez `formules.py` avant de modifier ce fichier.

Une assertion vient d'un utilisateur, au même titre qu'une formule. Elle n'est
donc jamais évaluée telle quelle : on la recompile d'abord en un arbre dont
chaque nœud a été admis explicitement, puis on confie les deux côtés de la
comparaison aux évaluateurs de `formules.py`. Le seul ajout au langage des
formules est `BALANCE('préfixe')`, qui ne lit aucune valeur fournie par
l'utilisateur : le compilateur la remplace par une colonne qu'il a lui-même
écrite.
"""

import ast
import re
from dataclasses import dataclass
from decimal import Decimal

from core.i18n import Liste, msg

from .formules import FormuleInvalide, evaluer, valider

# Comparaisons admises. Aucune n'est ambiguë : pas de chaînage, pas de
# conjonction — une assertion dit une chose et une seule, sans quoi son
# rapport d'échec ne saurait pas quoi nommer.
COMPARATEURS = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}

NOM_BALANCE = "BALANCE"
# Préfixe des variables que le compilateur substitue aux appels BALANCE. Il
# commence par deux tirets bas : aucun code de rubrique ne peut le porter,
# donc aucune collision n'est possible avec le modèle de l'utilisateur.
PREFIXE_VARIABLE_BALANCE = "__BALANCE_"
MOTIF_PREFIXE_COMPTE = re.compile(r"^[0-9A-Za-z]+$")


class AssertionInvalide(FormuleInvalide):
    """L'assertion sort du langage admis, ou cherche à en sortir."""


@dataclass(frozen=True)
class ControleAssertion:
    """Résultat d'une assertion pour une rubrique et une colonne données."""

    rubrique: str
    colonne: str
    expression: str
    comparateur: str
    reussi: bool
    gauche: Decimal
    droite: Decimal
    ecart: Decimal


class AssertionsViolees(ValueError):
    """Au moins une assertion est fausse : l'état n'est pas publiable.

    Porte le rapport complet, pas seulement les échecs : un contrôle réussi
    est une information utile pour qui doit comprendre pourquoi un autre a
    échoué.
    """

    def __init__(self, controles):
        self.controles = tuple(controles)
        self.violations = tuple(controle for controle in self.controles if not controle.reussi)
        details = Liste(
            [
                msg(
                    "assertions.violation",
                    rubrique=controle.rubrique,
                    colonne=controle.colonne,
                    expression=controle.expression,
                    gauche=controle.gauche,
                    comparateur=controle.comparateur,
                    droite=controle.droite,
                    ecart=controle.ecart,
                )
                for controle in self.violations
            ]
        )
        super().__init__(msg("assertions.assertions_violees", details=details))


@dataclass(frozen=True)
class AssertionPreparee:
    """Assertion analysée, prête à être compilée puis évaluée."""

    expression: str
    comparateur: str
    source_gauche: str
    source_droite: str
    # Préfixe de compte -> nom de la variable qui portera son solde.
    noms_balances: dict[str, str]
    prefixes: tuple[str, ...]
    codes_sources: list[str]


class _SubstitutionBalance(ast.NodeTransformer):
    """Remplace chaque `BALANCE('6')` par une variable nommée par nos soins."""

    def __init__(self) -> None:
        self.noms: dict[str, str] = {}

    def visit_Call(self, noeud: ast.Call) -> ast.AST:  # noqa: N802 (API de ast)
        if not (isinstance(noeud.func, ast.Name) and noeud.func.id == NOM_BALANCE):
            self.generic_visit(noeud)
            return noeud
        if noeud.keywords or len(noeud.args) != 1:
            raise AssertionInvalide(
                msg("assertions.attend_exactement_prefixe_compte", NOM_BALANCE=NOM_BALANCE)
            )
        argument = noeud.args[0]
        if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
            raise AssertionInvalide(
                msg("assertions.prefixe_doit_etre_chaine_litterale", NOM_BALANCE=NOM_BALANCE)
            )
        prefixe = argument.value
        if not MOTIF_PREFIXE_COMPTE.match(prefixe):
            raise AssertionInvalide(msg("assertions.prefixe_compte_invalide", prefixe=prefixe))
        nom = self.noms.setdefault(prefixe, f"{PREFIXE_VARIABLE_BALANCE}{len(self.noms)}")
        return ast.copy_location(ast.Name(id=nom, ctx=ast.Load()), noeud)


def _refuser_constantes_non_numeriques(noeud: ast.AST) -> None:
    """Après substitution, plus aucune chaîne n'a de raison d'être là.

    Les seules chaînes du langage sont les préfixes de `BALANCE`, déjà
    consommés. Laisser passer les autres repousserait l'erreur jusqu'à une
    conversion en Decimal, loin de sa cause.
    """
    for n in ast.walk(noeud):
        if isinstance(n, ast.Constant) and (
            isinstance(n.value, bool) or not isinstance(n.value, int | float)
        ):
            raise AssertionInvalide(msg("assertions.constante_non_numerique", value=n.value))


def analyser_assertion(expression: str, codes_connus: list[str]) -> AssertionPreparee:
    """Analyse l'assertion et refuse tout ce qui n'est pas une comparaison."""
    if not isinstance(expression, str) or not expression.strip():
        raise AssertionInvalide(msg("assertions.assertion_vide"))
    try:
        arbre = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise AssertionInvalide(msg("assertions.syntaxe_invalide", e=e)) from e

    comparaison = arbre.body
    if not isinstance(comparaison, ast.Compare):
        raise AssertionInvalide(msg("assertions.assertion_comparaison_rien_autre"))
    if len(comparaison.ops) != 1 or len(comparaison.comparators) != 1:
        raise AssertionInvalide(msg("assertions.comparaison_chainee_assertion_compare_deux"))
    comparateur = COMPARATEURS.get(type(comparaison.ops[0]))
    if comparateur is None:
        raise AssertionInvalide(
            msg("assertions.comparateur_interdit", nom=type(comparaison.ops[0]).__name__)
        )

    substitution = _SubstitutionBalance()
    gauche = substitution.visit(comparaison.left)
    droite = substitution.visit(comparaison.comparators[0])
    for cote in (gauche, droite):
        _refuser_constantes_non_numeriques(cote)

    noms_balances = dict(substitution.noms)
    codes_sources = [*codes_connus, *noms_balances.values()]
    source_gauche, source_droite = ast.unparse(gauche), ast.unparse(droite)
    # Le reste du langage est exactement celui des formules : on le fait dire
    # par formules.valider plutôt que de le redire ici, où il divergerait.
    for source in (source_gauche, source_droite):
        try:
            valider(source, codes_sources)
        except AssertionInvalide:
            raise
        except FormuleInvalide as e:
            raise AssertionInvalide(msg("assertions.assertion_refusee", e=e)) from e

    return AssertionPreparee(
        expression=expression,
        comparateur=comparateur,
        source_gauche=source_gauche,
        source_droite=source_droite,
        noms_balances=noms_balances,
        prefixes=tuple(noms_balances),
        codes_sources=codes_sources,
    )


def _comparer(comparateur: str, gauche: Decimal, droite: Decimal) -> bool:
    if comparateur == "==":
        return gauche == droite
    if comparateur == "!=":
        return gauche != droite
    if comparateur == "<":
        return gauche < droite
    if comparateur == "<=":
        return gauche <= droite
    if comparateur == ">":
        return gauche > droite
    return gauche >= droite


def controler_assertion(
    assertion: str | AssertionPreparee,
    valeurs: dict[str, Decimal],
    codes_connus: list[str],
    balances: dict[str, Decimal],
    *,
    rubrique: str,
    colonne: str,
) -> ControleAssertion:
    """Évalue l'assertion pour une colonne et retourne son rapport.

    Les deux côtés sont conservés même quand le contrôle réussit : sans eux,
    un échec ne dirait pas de combien l'état se trompe, et l'écart est
    précisément ce que lira le comptable.
    """
    if isinstance(assertion, str):
        assertion = analyser_assertion(assertion, codes_connus)

    valeurs_etendues = dict(valeurs)
    for prefixe, nom in assertion.noms_balances.items():
        valeurs_etendues[nom] = balances.get(prefixe, Decimal(0))

    gauche = evaluer(assertion.source_gauche, valeurs_etendues, assertion.codes_sources)
    droite = evaluer(assertion.source_droite, valeurs_etendues, assertion.codes_sources)
    return ControleAssertion(
        rubrique=rubrique,
        colonne=colonne,
        expression=assertion.expression,
        comparateur=assertion.comparateur,
        reussi=_comparer(assertion.comparateur, gauche, droite),
        gauche=gauche,
        droite=droite,
        ecart=gauche - droite,
    )
