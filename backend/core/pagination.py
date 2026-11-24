"""Pagination optionnelle des listes de l'API (Lot 2-B).

Le corps de la réponse reste un tableau JSON : le frontend existant ne change pas. La pagination se
demande par `?limite=` et `?decalage=` ; son état passe par des en-têtes (`X-Total-Count`, et
`X-Decalage-Suivant` quand il y a une suite). Sans `limite`, la liste est rendue en entier jusqu'à
`PLAFOND` lignes ; au-delà, un refus demande de paginer plutôt que de rendre une réponse sans borne.
"""

from __future__ import annotations

from typing import Any

from .erreurs import CodeErreur, ErreurMetier
from .i18n import msg

PLAFOND = 500


def _entier(requete, nom: str, *, minimum: int, maximum: int | None = None) -> int | None:
    brut = requete.query_params.get(nom)
    if brut in (None, ""):
        return None
    try:
        valeur = int(brut)
    except ValueError:
        valeur = None
    if valeur is None or valeur < minimum or (maximum is not None and valeur > maximum):
        attendu = f"entier ≥ {minimum}" if maximum is None else f"entier de {minimum} à {maximum}"
        raise ErreurMetier(
            CodeErreur.REGLE_INVALIDE, msg("api.champ_invalide", champ=nom, attendu=attendu)
        )
    return valeur


def paginer(liste: Any, requete) -> tuple[list, dict[str, str]]:
    """`(tranche, en-têtes)` d'une liste ou d'un queryset DÉJÀ TRIÉ par une clé stable.

    Un queryset non trié est une erreur de programmation (`TypeError`) : deux pages pourraient alors
    se chevaucher ou omettre des lignes.
    """
    if getattr(liste, "ordered", True) is False:
        raise TypeError("paginer() exige une liste triée par une clé stable (order_by)")
    limite = _entier(requete, "limite", minimum=1, maximum=PLAFOND)
    decalage = _entier(requete, "decalage", minimum=0) or 0
    total = liste.count() if hasattr(liste, "count") and not isinstance(liste, list) else len(liste)
    if limite is None:
        if total > PLAFOND:
            raise ErreurMetier(
                CodeErreur.REGLE_INVALIDE,
                msg("api.liste_trop_longue", total=total, plafond=PLAFOND),
            )
        tranche = list(liste)
        entetes = {"X-Total-Count": str(total)}
        return tranche, entetes
    tranche = list(liste[decalage : decalage + limite])
    entetes = {"X-Total-Count": str(total)}
    if decalage + limite < total:
        entetes["X-Decalage-Suivant"] = str(decalage + limite)
    return tranche, entetes
