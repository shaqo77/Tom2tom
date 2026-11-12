"""Analyseur et évaluateur de formules d'états.

SÉCURITÉ — lisez ceci avant de modifier quoi que ce soit.

Une formule vient d'un utilisateur. L'évaluer avec eval() permettrait
d'exécuter n'importe quel code sur le serveur. Nous utilisons donc
l'analyseur syntaxique de Python, puis nous REFUSONS tout nœud qui
n'est pas dans la liste blanche ci-dessous.

Ne jamais ajouter ast.Attribute, ast.Subscript, ast.comprehension
ni ast.IfExp à NOEUDS_AUTORISES : chacun rouvre une voie d'exécution.
"""

import ast
import re
from decimal import Decimal

NOEUDS_AUTORISES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Name,
    ast.Call,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.USub,
    ast.UAdd,
    ast.Load,
)
FONCTIONS_AUTORISEES = {"SUM", "ABS", "MIN", "MAX", "ROUND"}
MOTIF_PLAGE = re.compile(r"\b([A-Z]\d+)\s*:\s*([A-Z]\d+)\b")


class FormuleInvalide(ValueError):
    """Formule refusée : syntaxe, rubrique inconnue, ou construction interdite."""


def _etendre_plages(formule: str, codes_connus: list[str]) -> str:
    """R110:R180 devient R110,R120,…,R180 selon l'ordre réel des rubriques."""

    def remplacer(m: re.Match) -> str:
        debut, fin = m.group(1), m.group(2)
        try:
            i, j = codes_connus.index(debut), codes_connus.index(fin)
        except ValueError as e:
            raise FormuleInvalide(f"rubrique inconnue dans la plage {debut}:{fin}") from e
        if i > j:
            raise FormuleInvalide(f"plage inversée {debut}:{fin}")
        return ",".join(codes_connus[i : j + 1])

    return MOTIF_PLAGE.sub(remplacer, formule)


def references(formule: str, codes_connus: list[str]) -> set[str]:
    """Rubriques citées par la formule. Sert au graphe de dépendances."""
    arbre = valider(formule, codes_connus)
    return {
        n.id
        for n in ast.walk(arbre)
        if isinstance(n, ast.Name) and n.id not in FONCTIONS_AUTORISEES
    }


def valider(formule: str, codes_connus: list[str]) -> ast.Expression:
    """Analyse et refuse tout ce qui n'est pas une expression arithmétique."""
    try:
        arbre = ast.parse(_etendre_plages(formule, codes_connus), mode="eval")
    except SyntaxError as e:
        raise FormuleInvalide(f"syntaxe invalide : {e}") from e

    for noeud in ast.walk(arbre):
        if not isinstance(noeud, NOEUDS_AUTORISES):
            raise FormuleInvalide(f"construction interdite : {type(noeud).__name__}")
        if isinstance(noeud, ast.Call):
            if not isinstance(noeud.func, ast.Name) or noeud.func.id not in FONCTIONS_AUTORISEES:
                raise FormuleInvalide("fonction non autorisée")
        if isinstance(noeud, ast.Name) and noeud.id not in FONCTIONS_AUTORISEES:
            if noeud.id not in codes_connus:
                raise FormuleInvalide(f"rubrique inconnue : {noeud.id}")
    return arbre


def evaluer(formule: str, valeurs: dict[str, Decimal], codes_connus: list[str]) -> Decimal:
    """Évalue la formule. Tous les calculs sont faits en Decimal."""
    arbre = valider(formule, codes_connus)

    def _eval(n: ast.AST) -> Decimal:
        if isinstance(n, ast.Expression):
            return _eval(n.body)
        if isinstance(n, ast.Constant):
            if not isinstance(n.value, int | float | str):
                raise FormuleInvalide("constante non numérique")
            return Decimal(str(n.value))
        if isinstance(n, ast.Name):
            return valeurs.get(n.id, Decimal(0))
        if isinstance(n, ast.UnaryOp):
            v = _eval(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp):
            g, d = _eval(n.left), _eval(n.right)
            if isinstance(n.op, ast.Add):
                return g + d
            if isinstance(n.op, ast.Sub):
                return g - d
            if isinstance(n.op, ast.Mult):
                return g * d
            if isinstance(n.op, ast.Div):
                if d == 0:
                    raise FormuleInvalide("division par zéro")
                return g / d
        if isinstance(n, ast.Call):
            args = [_eval(a) for a in n.args]
            nom = n.func.id
            if nom == "SUM":
                return sum(args, Decimal(0))
            if nom == "ABS":
                return abs(args[0])
            if nom == "MIN":
                return min(args)
            if nom == "MAX":
                return max(args)
            if nom == "ROUND":
                decimales = int(args[1]) if len(args) > 1 else 2
                return args[0].quantize(Decimal(1).scaleb(-decimales))
            raise FormuleInvalide(f"fonction non autorisée : {nom}")
        raise FormuleInvalide(f"nœud non géré : {type(n).__name__}")

    return _eval(arbre)
