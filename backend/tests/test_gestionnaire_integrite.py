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


# --- refus de droit, objet introuvable, session absente : toujours {code, message} -------------


def test_un_refus_de_droit_rend_code_et_message_et_non_le_detail_de_drf():
    from rest_framework.exceptions import PermissionDenied

    reponse = gestionnaire_exceptions(PermissionDenied("Vous n'êtes pas habilité à consulter"), {})
    assert reponse.status_code == 403
    assert reponse.data == {
        "code": "ACCES_REFUSE",
        "message": "Vous n'êtes pas habilité à consulter",
    }


def test_un_refus_de_droit_sans_texte_a_un_message_du_catalogue_pas_l_anglais_de_drf():
    from rest_framework.exceptions import PermissionDenied

    reponse = gestionnaire_exceptions(PermissionDenied(), {})
    assert reponse.data["code"] == "ACCES_REFUSE"
    assert "permission" not in reponse.data["message"].lower()


def test_un_objet_introuvable_rend_code_et_message():
    from django.http import Http404

    reponse = gestionnaire_exceptions(Http404(), {})
    assert reponse.status_code == 404
    assert set(reponse.data) == {"code", "message"} and reponse.data["code"] == "INTROUVABLE"
    assert "Not found" not in reponse.data["message"]


def test_une_session_absente_rend_code_et_message():
    from rest_framework.exceptions import NotAuthenticated

    reponse = gestionnaire_exceptions(NotAuthenticated(), {})
    assert reponse.data["code"] == "NON_AUTHENTIFIE" and set(reponse.data) == {"code", "message"}
