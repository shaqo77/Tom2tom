"""Résolution du taux applicable à une date (L2-T01) et enregistrement des taux (L11-A6).

Un taux est exprimé en unités de la monnaie de TENUE de l'organisation par unité de `devise`.
Un taux n'est jamais écrasé : en enregistrer un autre, c'est ajouter une ligne à une autre date.
"""

import datetime
import re
from decimal import Decimal

from django.db import IntegrityError, transaction

from core.audit import journaliser
from core.i18n import msg
from core.metier import decimal as decimal_exact
from core.metier import refuser
from niveau1_socle.organisations.models import Organisation

from .models import Devise, Taux, TypeTaux
from .parametres_devises import _habiliter, resoudre_parametres_devises

ECRITURE_DECIMALE = re.compile(
    r"^\d+(\.\d+)?$"
)  # ni exposant, ni signe : « 1e3 » n'est pas un taux


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
            msg("taux.aucun_taux_date", type_taux=type_taux, devise=devise, v1=date.isoformat())
        )
    return taux


def enregistrer_taux(
    *,
    utilisateur,
    devise: str,
    date: datetime.date,
    taux,
    type_taux: str,
    source: str = "",
) -> Taux:
    """Enregistre le taux de `devise` à `date` (habilitation `parametrer`).

    Refusés : un taux qui n'est pas un nombre exact strictement positif (jamais de `float`), un type
    de taux inconnu, une devise inconnue, la monnaie de tenue elle-même (son taux est 1 par
    définition), une devise que l'organisation n'autorise pas à cette date, et un taux déjà
    enregistré le même jour pour le même type (il ne s'écrase pas).
    """
    _habiliter(utilisateur, None)
    if isinstance(taux, float) or (isinstance(taux, str) and not ECRITURE_DECIMALE.match(taux)):
        refuser("taux.taux_invalide", champ="taux")
    valeur = decimal_exact(taux, "taux", cle="taux.taux_invalide")
    if type_taux not in TypeTaux.values:
        refuser("taux.type_inconnu", type_taux=type_taux)
    if not Devise.objects.filter(pk=devise).exists():
        refuser("taux.devise_inconnue", devise=devise)
    tenue = Organisation.objects.values_list("monnaie_tenue", flat=True).get()
    if devise == tenue:
        refuser("taux.monnaie_de_tenue", devise=devise)
    autorisees = resoudre_parametres_devises(None, date).devises_autorisees
    if autorisees is not None and devise not in autorisees:
        refuser("taux.devise_non_autorisee", devise=devise)
    try:
        with transaction.atomic():
            ligne = Taux.objects.create(
                org_id=utilisateur.org_id,
                devise_id=devise,
                date=date,
                taux=valeur,
                type_taux=type_taux,
                source=(source or "").strip(),
                created_by=utilisateur.id,
            )
            journaliser(
                org_id=ligne.org_id,
                actor_id=utilisateur.id,
                action="rate_recorded",
                object_type="taux",
                object_id=ligne.id,
                after={
                    "devise": devise,
                    "date": str(date),
                    "taux": format(valeur, "f"),
                    "type_taux": type_taux,
                    "source": ligne.source,
                },
            )
    except IntegrityError:
        refuser("taux.deja_enregistre", devise=devise, date=date.isoformat(), type_taux=type_taux)
    return ligne
