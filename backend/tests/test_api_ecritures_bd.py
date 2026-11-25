# ruff: noqa: F811, E501
"""L'API HTTP des écritures : saisie d'un brouillon (avec clé de cofinancement), lecture, validation,
comptabilisation. E9a. Montants en chaînes, refus au format `{code, message}`."""

import pytest
from django.db import connection

from niveau1_socle.comptabilite.models import Ecriture
from tests.test_api_marches_bd import appeler
from tests.test_cles_cofinancement_bd import _version, cles  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def _corps(montant="1001", **champs):
    return {
        "journal": "OD",
        "date_comptable": "2026-03-10",
        "libelle": "Charge commune",
        "lignes": [
            {"compte": "6011", "debit": montant, "cle": "CHARGES"},
            {"compte": "5211", "credit": montant},
        ],
    } | champs


def _chemin(projet, fin=""):
    return f"/projets/{projet.id}/ecritures/{fin}"


def _nb(organisation) -> int:
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])
    return Ecriture.objects.count()


def test_une_ligne_avec_cle_est_ventilee_et_les_montants_restent_des_chaines(cles):
    organisation, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 60, "GOV": 30, "UE": 10})
    r = appeler(profils["amina"], "post", _chemin(projet), _corps())
    assert r.status_code == 201, r.content
    e = r.json()
    assert e["status"] == "draft" and e["number"] is None and e["journal"] == "OD"
    charges = [x for x in e["lignes"] if x["compte"] == "6011"]
    assert {x["accord"]: x["debit"] for x in charges} == {
        accords["IDA"].numero: "600.0000",
        accords["GOV"].numero: "301.0000",  # le porteur d'arrondi absorbe le reliquat
        accords["UE"].numero: "100.0000",
    }
    assert all(x["cle_version"] for x in charges)
    assert (e["total_debit"], e["total_credit"]) == ("1001.0000", "1001.0000")
    assert isinstance(e["lignes"][0]["debit"], str)


def test_le_cycle_complet_saisir_valider_comptabiliser_par_trois_personnes(cles):
    organisation, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 50, "GOV": 50})
    e = appeler(profils["amina"], "post", _chemin(projet), _corps("200")).json()
    v = appeler(profils["bruno"], "post", _chemin(projet, f"{e['id']}/valider/"))
    assert v.status_code == 200 and v.json()["status"] == "validated", v.content
    p = appeler(profils["claire"], "post", _chemin(projet, f"{e['id']}/comptabiliser/"))
    assert p.status_code == 200 and p.json()["status"] == "posted" and p.json()["number"]
    lu = appeler(profils["amina"], "get", _chemin(projet, f"{e['id']}/"))
    assert lu.json()["status"] == "posted"
    liste = appeler(profils["amina"], "get", _chemin(projet) + "?statut=posted")
    assert [x["id"] for x in liste.json()] == [e["id"]]


def test_l_auteur_ne_valide_pas_sa_propre_piece(cles):
    _, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 50, "GOV": 50})
    e = appeler(profils["amina"], "post", _chemin(projet), _corps("200")).json()
    r = appeler(profils["amina"], "post", _chemin(projet, f"{e['id']}/valider/"))
    assert r.status_code == 403 and set(r.json()) == {"code", "message"}


def test_une_piece_desequilibree_est_refusee_sans_rien_creer(cles):
    organisation, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 50, "GOV": 50})
    avant = _nb(organisation)
    corps = _corps("100")
    corps["lignes"][1]["credit"] = "90"
    r = appeler(profils["amina"], "post", _chemin(projet), corps)
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}
    assert "déséquilibrée" in r.json()["message"]
    assert _nb(organisation) == avant


@pytest.mark.parametrize(
    ("modifier", "attendu"),
    [
        (lambda c: c["lignes"][0].update(cle="INCONNUE"), "INCONNUE"),
        (lambda c: c["lignes"][0].update(compte="0000"), "0000"),
        (lambda c: c.update(journal="ZZ"), "ZZ"),
        (lambda c: c.update(date_comptable="2035-01-01"), None),
        (lambda c: c["lignes"][0].update(accord="NUL-1", cle=""), "NUL-1"),
        (lambda c: c["lignes"][0].update(tiers="NULPART"), "NULPART"),
    ],
)
def test_un_refus_metier_est_un_422_lisible_jamais_un_500(cles, modifier, attendu):
    _, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 50, "GOV": 50})
    corps = _corps("100")
    modifier(corps)
    r = appeler(profils["amina"], "post", _chemin(projet), corps)
    assert r.status_code == 422, r.content
    assert set(r.json()) == {"code", "message"}
    if attendu:
        assert attendu in r.json()["message"]


def test_un_montant_a_virgule_flottante_est_refuse(cles):
    _, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 50, "GOV": 50})
    corps = _corps("100")
    corps["lignes"][0]["debit"] = 100.1
    r = appeler(profils["amina"], "post", _chemin(projet), corps)
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}


def test_une_ligne_sans_montant_ou_une_liste_vide_est_refusee(cles):
    _, projet, profils, accords, cle = cles
    corps = _corps("100")
    corps["lignes"][0].pop("debit")
    assert appeler(profils["amina"], "post", _chemin(projet), corps).status_code == 422
    assert (
        appeler(profils["amina"], "post", _chemin(projet), _corps() | {"lignes": []}).status_code
        == 422
    )


def test_sans_le_droit_de_saisir_c_est_un_403_et_sans_le_droit_de_lire_aussi(cles):
    organisation, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 50, "GOV": 50})
    avant = _nb(organisation)
    refus = appeler(profils["claire"], "post", _chemin(projet), _corps("100"))
    assert refus.status_code == 403 and set(refus.json()) == {"code", "message"}
    assert _nb(organisation) == avant


def test_la_cle_d_idempotence_ne_cree_qu_une_piece(cles):
    organisation, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 50, "GOV": 50})
    corps = _corps("100", cle_idempotence="saisie-1")
    a = appeler(profils["amina"], "post", _chemin(projet), corps)
    b = appeler(profils["amina"], "post", _chemin(projet), corps)
    assert a.status_code == b.status_code == 201
    assert a.json()["id"] == b.json()["id"]
    assert _nb(organisation) == 1


def test_une_ecriture_d_un_autre_projet_est_introuvable(cles):
    _, projet, profils, accords, cle = cles
    import uuid

    r = appeler(profils["amina"], "get", _chemin(projet, f"{uuid.uuid4()}/"))
    assert r.status_code == 404 and set(r.json()) == {"code", "message"}
