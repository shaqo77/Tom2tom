"""Sources externes du moteur d'états : des rubriques qui ne viennent pas du grand livre.

Une rubrique `{"type": "external", "source": "<nom>", "item": "<élément>"}` lit sa valeur auprès
d'une source DÉCLARÉE (registre fermé : on n'exécute jamais un nom venu d'un modèle). Une source
déclare ses éléments ; un élément inconnu est refusé À LA COMPILATION, pas à la génération. Elle
reçoit les paramètres de l'état et rend un `Decimal` ; la même valeur vaut pour toutes les colonnes.

Une source ne contrôle aucune habilitation : celle de l'état (publier) l'est en amont ; elle ne
renvoie que des montants, jamais un numéro de compte ni une donnée nominative.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from core.i18n import msg


class SourceIncomplete(ValueError):
    """La source ne peut pas répondre : une donnée requise manque. Aucun état n'est produit."""


@dataclass(frozen=True)
class SourceExterne:
    nom: str
    elements: frozenset[str]
    lire: Callable[[str, Mapping[str, Any]], Decimal]


REGISTRE: dict[str, SourceExterne] = {}


def enregistrer(
    nom: str, elements: set[str] | frozenset[str], lire: Callable[[str, Mapping[str, Any]], Decimal]
) -> None:
    """Déclare une source. Idempotent : le démarrage de l'application peut la redéclarer."""
    REGISTRE[nom] = SourceExterne(nom, frozenset(elements), lire)


def verifier(source: object, element: object) -> None:
    """Refuse une source ou un élément inconnu (appelé à la compilation du modèle)."""
    from .compilateur import ModeleEtatInvalide

    declaree = REGISTRE.get(source) if isinstance(source, str) else None
    if declaree is None:
        raise ModeleEtatInvalide(
            msg("compilateur.source_externe_inconnue", source=str(source)[:40])
        )
    if element not in declaree.elements:
        raise ModeleEtatInvalide(
            msg(
                "compilateur.element_externe_inconnu",
                source=declaree.nom,
                element=str(element)[:40],
            )
        )


def lire(source: str, element: str, parametres: Mapping[str, Any]) -> Decimal:
    valeur = REGISTRE[source].lire(element, parametres)
    return valeur if isinstance(valeur, Decimal) else Decimal(str(valeur))
