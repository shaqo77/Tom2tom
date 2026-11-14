"""Tiers : consultation journalisée et rétention. Voir L2-T04.

Un tiers est une donnée personnelle. Toute LECTURE est journalisée (qui, quand,
quel tiers) ; le journal ne contient JAMAIS la donnée lue. Un tiers inactif dont
la durée de rétention est échue est anonymisé : son code reste, pour que les
écritures qui le référencent restent lisibles.
"""

import datetime

from django.db import transaction
from django.utils import timezone

from core.audit import journaliser
from core.i18n import msg

from .models import Tiers

NOM_ANONYME = "ANONYMISÉ"


class TiersIntrouvable(LookupError):
    """Aucun tiers de ce code dans l'organisation courante."""


class AnonymisationImpossible(ValueError):
    """Le tiers est actif, ou sa durée de rétention n'est pas échue."""


def _lire(code: str) -> Tiers:
    tiers = Tiers.objects.filter(code=code).first()
    if tiers is None:
        raise TiersIntrouvable(msg("tiers.tiers_existe", code=code))
    return tiers


def _tracer(utilisateur, tiers: Tiers, action: str) -> None:
    journaliser(
        org_id=tiers.org_id,
        actor_id=getattr(utilisateur, "id", None),
        action=action,
        object_type="tiers",
        object_id=tiers.id,
    )


def consulter_tiers(utilisateur, code: str) -> Tiers:
    """Retourne le tiers et journalise la consultation."""
    with transaction.atomic():
        tiers = _lire(code)
        _tracer(utilisateur, tiers, "tiers_read")
    return tiers


def consulter_coordonnees_bancaires(utilisateur, code: str) -> dict | None:
    """Retourne les coordonnées bancaires, journalisées à part de la fiche."""
    with transaction.atomic():
        tiers = _lire(code)
        _tracer(utilisateur, tiers, "tiers_bank_details_read")
    return tiers.coordonnees_bancaires


def tiers_a_anonymiser(aujourdhui: datetime.date):
    """Tiers inactifs dont la durée de rétention est échue et non encore anonymisés."""
    return Tiers.objects.filter(
        actif=False, retention_until__lte=aujourdhui, anonymise_le__isnull=True
    )


def anonymiser_tiers(tiers: Tiers, *, utilisateur, aujourdhui: datetime.date) -> Tiers:
    """Efface les données personnelles d'un tiers dont la rétention est échue."""
    with transaction.atomic():
        courant = Tiers.objects.select_for_update().get(pk=tiers.pk)
        if (
            courant.actif
            or courant.retention_until is None
            or courant.retention_until > aujourdhui
            or courant.anonymise_le is not None
        ):
            raise AnonymisationImpossible(
                msg("tiers.tiers_peut_etre_anonymise_il", code=courant.code)
            )
        courant.nom = NOM_ANONYME
        courant.identification = {}
        courant.coordonnees_bancaires = None
        courant.anonymise_le = timezone.now()
        courant.save()
        _tracer(utilisateur, courant, "tiers_anonymized")
    return courant
