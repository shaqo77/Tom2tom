"""Ordonnancement des rubriques calculées. Voir L0-T03."""

from graphlib import CycleError, TopologicalSorter

from core.i18n import msg

from .formules import FormuleInvalide, references


class ReferenceCirculaire(FormuleInvalide):
    """Deux rubriques se référencent mutuellement, directement ou non."""


def ordonner(formules: dict[str, str], codes_connus: list[str]) -> list[str]:
    """Retourne les codes des rubriques calculées dans l'ordre d'évaluation.

    `formules` : {code_rubrique: expression}. Les rubriques d'agrégat
    n'y figurent pas — leurs valeurs viennent de la base.
    """
    graphe = {
        code: references(expr, codes_connus) & set(formules) for code, expr in formules.items()
    }
    try:
        return list(TopologicalSorter(graphe).static_order())
    except CycleError as e:
        chaine = " → ".join(e.args[1])
        raise ReferenceCirculaire(msg("dependances.reference_circulaire", chaine=chaine)) from e
