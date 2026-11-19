"""Présenter un profil : chaque élément se lit « lorsque requis ». Voir L5-T06.

Il n'existe pas de modèle Banque mondiale universel : le DFIL du projet décide. Toute présentation
d'un profil (écran, guide, export) passe par `presenter_profil`, qui ajoute la mention à CHAQUE
élément et l'avertissement en tête, dans la langue demandée. Présenter un profil comme universel
serait une erreur de conception.
"""

from core.i18n import LANGUE_PAR_DEFAUT, Localise, msg

from ..models import ProfilBailleur

AVERTISSEMENT = msg("presentation.avertissement")


def presenter_profil(profil: ProfilBailleur, langue: str = LANGUE_PAR_DEFAUT) -> dict:
    return {
        "code": profil.code,
        "version": profil.version,
        "libelle": Localise(profil.label).rendre(langue),
        "description": Localise(profil.description).rendre(langue),
        "avertissement": AVERTISSEMENT.rendre(langue),
        "elements": [
            {
                "type": element.kind,
                "code": element.code,
                "libelle": Localise(element.label).rendre(langue),
                "mention": element.mention.rendre(langue),
                "a_une_exigence": element.exigence is not None,
            }
            for element in profil.elements.all()
        ],
    }


__all__ = ["AVERTISSEMENT", "presenter_profil"]
