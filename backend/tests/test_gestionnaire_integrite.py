"""Revue L11 (constat 1) : une contrainte de la base non traduite ne sort jamais en 500."""

import pytest
from django.db import DataError, IntegrityError

from core.api import gestionnaire_exceptions


@pytest.mark.parametrize("erreur", [IntegrityError("duplicate key"), DataError("trop long")])
def test_une_violation_de_la_base_non_traduite_devient_un_refus_json(erreur):
    reponse = gestionnaire_exceptions(erreur, {})
    assert reponse is not None, "sans gestionnaire, DRF répond 500"
    assert reponse.status_code == 422
    assert set(reponse.data) == {"code", "message"}
    # Aucun détail SQL ne fuit vers le client.
    assert "duplicate key" not in reponse.data["message"]
    assert "trop long" not in reponse.data["message"]
