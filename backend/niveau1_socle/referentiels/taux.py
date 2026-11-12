"""Résolution du taux applicable à une date. Voir L2-T01."""

import datetime
from decimal import Decimal

from .models import Taux


class TauxIntrouvable(LookupError):
    """Aucun taux de ce type n'est en vigueur à la date demandée."""


def taux_applicable(devise: str, date: datetime.date, type_taux: str) -> Decimal:
    """Taux en vigueur à `date` : le plus récent à cette date ou avant, jamais un taux futur.

    Lu sous la RLS de l'organisation courante.
    """
    taux = (
        Taux.objects.filter(devise_id=devise, type_taux=type_taux, date__lte=date)
        .order_by("-date")
        .values_list("taux", flat=True)
        .first()
    )
    if taux is None:
        raise TauxIntrouvable(
            f"Aucun taux {type_taux!r} pour {devise} à la date du {date.isoformat()}"
        )
    return taux
