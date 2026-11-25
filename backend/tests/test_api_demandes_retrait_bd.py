# ruff: noqa: F811, E501
"""L'API HTTP de la liste des demandes de retrait : de quoi choisir une demande dans un écran."""

import uuid

import pytest

from tests.test_api_marches_bd import appeler
from tests.test_compte_special_bd import _demande_a_part, special  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def test_la_liste_donne_le_numero_l_accord_le_statut_et_un_montant_en_chaine(special):
    _, projet, profils, accord, _, demande = special
    r = appeler(profils["bruno"], "get", f"/projets/{projet.id}/demandes-retrait/")
    assert r.status_code == 200, r.content
    [d] = r.json()
    assert d["id"] == str(demande.id) and d["numero"] == demande.numero
    assert d["accord"] == accord.numero and d["statut"] == "acceptee"
    assert isinstance(d["montant_total"], str) and set(d) >= {
        "periode_debut",
        "periode_fin",
        "type",
    }


def test_on_filtre_par_statut_et_par_accord(special):
    _, projet, profils, accord, _, _ = special
    chemin = f"/projets/{projet.id}/demandes-retrait/"
    assert len(appeler(profils["bruno"], "get", chemin + "?statut=acceptee").json()) == 1
    assert appeler(profils["bruno"], "get", chemin + "?statut=rejetee").json() == []
    assert len(appeler(profils["bruno"], "get", chemin + f"?accord={accord.numero}").json()) == 1
    assert appeler(profils["bruno"], "get", chemin + "?accord=INCONNU").json() == []
    assert (
        len(appeler(profils["bruno"], "get", chemin + "?statut=nimporte").json()) == 1
    )  # filtre inconnu ignoré


def test_un_projet_sans_droit_de_lecture_est_refuse_au_format_code_message(special):
    _, _, profils, _, _, _ = special
    r = appeler(profils["bruno"], "get", f"/projets/{uuid.uuid4()}/demandes-retrait/")
    assert r.status_code == 403 and set(r.json()) == {"code", "message"}
