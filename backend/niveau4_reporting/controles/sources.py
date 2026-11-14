"""Branche les contrôles sur la règle « aucun objet actif sans exigence source » (L5-T03)."""

import datetime

from niveau3_config.models import TypeCible
from niveau3_config.services.rattachement import SourceCible, enregistrer_cible

from .models import Controle, StatutControle


def _controles_actifs(project_id, date: datetime.date):
    controles = Controle.objects.filter(
        project_id=project_id, status=StatutControle.ACTIF, valid_from__lte=date
    ).exclude(valid_to__lte=date)
    return [(c.pk, f"{c.code} v{c.version}") for c in controles.order_by("code", "version")]


def _controle_existe(project_id, target_id) -> bool:
    return Controle.objects.filter(pk=target_id, project_id=project_id).exists()


def brancher_les_controles() -> None:
    enregistrer_cible(TypeCible.CONTROLE, SourceCible(_controles_actifs, _controle_existe))
