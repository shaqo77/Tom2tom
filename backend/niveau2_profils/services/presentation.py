"""Présenter un profil : chaque élément se lit « lorsque requis ». Voir L5-T06.

Il n'existe pas de modèle Banque mondiale universel : le DFIL du projet décide. Toute présentation
d'un profil (écran, guide, export) passe par `presenter_profil`, qui ajoute la mention à CHAQUE
élément et l'avertissement en tête. Présenter un profil comme universel serait une erreur de
conception.
"""

from ..models import MENTION_LORSQUE_REQUIS, ProfilBailleur

AVERTISSEMENT = (
    "Ce profil n'est pas un modèle universel : les documents contractuels du projet "
    "(DFIL, accord de financement) déterminent ce qui s'applique."
)


def presenter_profil(profil: ProfilBailleur, langue: str = "fr") -> dict:
    return {
        "code": profil.code,
        "version": profil.version,
        "libelle": profil.label.get(langue) or next(iter(profil.label.values())),
        "avertissement": AVERTISSEMENT,
        "elements": [
            {
                "type": element.kind,
                "code": element.code,
                "libelle": element.label.get(langue) or next(iter(element.label.values())),
                "mention": element.mention,
                "a_une_exigence": element.exigence is not None,
            }
            for element in profil.elements.all()
        ],
    }


__all__ = ["AVERTISSEMENT", "MENTION_LORSQUE_REQUIS", "presenter_profil"]
