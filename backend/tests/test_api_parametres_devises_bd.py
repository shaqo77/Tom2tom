# ruff: noqa: F811, E501
"""L'API HTTP des réglages de devises : lecture résolue avec provenance, pose versionnée. L10."""

import pytest
from django.contrib.auth import get_user_model

from niveau1_socle.habilitations.models import Habilitation, Role
from tests.test_api_marches_bd import RACINE, _poser, appeler  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_devises_parametrees_application_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()


@pytest.fixture
def reglages(cadre):
    organisation, p1, p2, profils = cadre
    lecteur = Utilisateur.objects.create_user("lea", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id, code="LECX", label={"fr": "l"}, operations=["consulter"]
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=lecteur.id, project_id=p1.id, role=role
    )
    profils["lea"] = lecteur
    _poser(organisation)
    return organisation, p1, p2, profils


def test_sans_reglage_tout_est_non_parametre(reglages):
    _, p1, _, profils = reglages
    r = appeler(profils["dora"], "get", f"/projets/{p1.id}/parametres-devises/?jour=2026-03-01")
    assert r.status_code == 200
    d = r.json()
    assert d["devise_reference"] is None and d["devises_autorisees"] is None
    assert d["type_taux"] is None and d["origine"] == {
        "devise_reference": None,
        "devises_autorisees": None,
        "type_taux": None,
    }


def test_l_organisation_pose_puis_le_projet_surcharge_avec_provenance(reglages):
    _, p1, p2, profils = reglages
    dora = profils["dora"]
    r = appeler(
        dora,
        "post",
        "/parametres-devises/",
        {
            "devises_autorisees": ["usd", "DJF", "EUR"],
            "devise_reference": "USD",
            "date_effet": "2026-01-01",
        },
    )
    assert r.status_code == 201, r.content
    assert r.json()["devises_autorisees"] == ["DJF", "EUR", "USD"] and r.json()["version"] == 1
    r = appeler(
        dora,
        "post",
        f"/projets/{p2.id}/parametres-devises/",
        {"type_taux": "officiel", "date_effet": "2026-02-01"},
    )
    assert r.status_code == 201, r.content
    d = appeler(dora, "get", f"/projets/{p2.id}/parametres-devises/?jour=2026-03-01").json()
    assert d["devise_reference"] == "USD" and d["type_taux"] == "officiel"
    assert d["origine"] == {
        "devise_reference": "organisation",
        "devises_autorisees": "organisation",
        "type_taux": "projet",
    }
    autre = appeler(dora, "get", f"/projets/{p1.id}/parametres-devises/?jour=2026-03-01").json()
    assert autre["type_taux"] is None  # le réglage de P2 ne déborde pas sur P1


def test_l_historique_garde_toutes_les_versions(reglages):
    _, _, _, profils = reglages
    dora = profils["dora"]
    for date, liste in (("2026-01-01", ["DJF", "USD"]), ("2026-06-01", ["DJF", "USD", "EUR"])):
        appeler(
            dora, "post", "/parametres-devises/", {"devises_autorisees": liste, "date_effet": date}
        )
    h = appeler(dora, "get", "/parametres-devises/historique/").json()
    assert [v["version"] for v in h] == [2, 1]
    assert h[1]["valid_to"] == "2026-06-01" and h[0]["valid_to"] is None


def test_sans_habilitation_parametrer_la_pose_est_refusee(reglages):
    _, p1, _, profils = reglages
    lea = profils["lea"]
    corps = {"devises_autorisees": ["DJF"], "date_effet": "2026-01-01"}
    assert appeler(lea, "post", f"/projets/{p1.id}/parametres-devises/", corps).status_code == 403
    assert appeler(lea, "post", "/parametres-devises/", corps).status_code == 403
    assert (
        appeler(lea, "get", f"/projets/{p1.id}/parametres-devises/?jour=2026-03-01").status_code
        == 200
    )


def test_la_lecture_d_un_projet_sans_habilitation_est_refusee(reglages):
    _, _, p2, profils = reglages
    r = appeler(profils["lea"], "get", f"/projets/{p2.id}/parametres-devises/?jour=2026-03-01")
    assert r.status_code == 403


def test_les_refus_metier_ont_le_format_stable(reglages):
    _, _, _, profils = reglages
    dora = profils["dora"]
    r = appeler(
        dora,
        "post",
        "/parametres-devises/",
        {"devises_autorisees": ["XXX"], "date_effet": "2026-01-01"},
    )
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}
    assert (
        appeler(dora, "post", "/parametres-devises/", {"date_effet": "2026-01-01"}).status_code
        == 422
    )
    assert (
        appeler(dora, "post", "/parametres-devises/", {"devises_autorisees": ["DJF"]}).status_code
        == 422
    )
    r = appeler(
        dora,
        "post",
        "/parametres-devises/",
        {"devises_autorisees": "DJF", "date_effet": "2026-01-01"},
    )
    assert r.status_code == 422 and "devises_autorisees" in r.json()["message"]  # une liste


def test_le_catalogue_des_devises_est_lisible(reglages):
    _, _, _, profils = reglages
    r = appeler(profils["lea"], "get", "/devises/")
    assert r.status_code == 200
    assert {"DJF", "USD", "EUR"} <= {d["code"] for d in r.json()}
    assert all(set(d) == {"code", "label", "decimales"} for d in r.json())


def test_sans_session_l_acces_est_refuse(reglages):
    from django.test import Client

    assert Client().get(f"{RACINE}/parametres-devises/historique/").status_code in (401, 403)


# --- les taux de change par HTTP (L11-A6) --------------------------------------------------------


def test_un_taux_s_enregistre_et_se_liste_par_http(reglages):
    _, _, _, profils = reglages
    dora = profils["dora"]
    r = appeler(
        dora, "post", "/taux/",
        {"devise": "USD", "date": "2026-03-01", "taux": "177.5", "type_taux": "officiel", "source": "BCD"},
    )  # fmt: skip
    assert r.status_code == 201, r.content
    corps = r.json()
    assert (
        corps["devise"] == "USD" and corps["taux"] == "177.5000000000" and corps["source"] == "BCD"
    )
    appeler(
        dora,
        "post",
        "/taux/",
        {"devise": "USD", "date": "2026-04-01", "taux": "178", "type_taux": "officiel"},
    )
    liste = appeler(dora, "get", "/taux/?devise=USD&type_taux=officiel").json()
    assert [t["date"] for t in liste] == ["2026-04-01", "2026-03-01"]  # le plus récent d'abord
    assert all(isinstance(t["taux"], str) for t in liste)  # jamais un flottant


def test_les_refus_de_taux_ont_le_format_stable(reglages):
    _, _, _, profils = reglages
    dora = profils["dora"]
    base = {"devise": "USD", "date": "2026-03-01", "taux": "177", "type_taux": "officiel"}
    assert appeler(dora, "post", "/taux/", base).status_code == 201
    doublon = appeler(dora, "post", "/taux/", base | {"taux": "180"})
    assert doublon.status_code == 422 and set(doublon.json()) == {"code", "message"}
    assert (
        appeler(dora, "post", "/taux/", base | {"date": "2026-03-02", "taux": 177.5}).status_code
        == 422
    )
    assert appeler(dora, "post", "/taux/", base | {"date": "pas-une-date"}).status_code == 422
    assert appeler(dora, "post", "/taux/", {"devise": "USD"}).status_code == 422


def test_sans_habilitation_parametrer_l_enregistrement_d_un_taux_est_refuse(reglages):
    _, _, _, profils = reglages
    base = {"devise": "USD", "date": "2026-03-01", "taux": "177", "type_taux": "officiel"}
    assert appeler(profils["lea"], "post", "/taux/", base).status_code == 403
    assert appeler(profils["lea"], "get", "/taux/").status_code == 200  # la lecture reste ouverte


def test_la_liste_des_taux_se_filtre_par_devise_et_par_type(reglages):
    _, _, _, profils = reglages
    dora = profils["dora"]
    for devise, type_taux, valeur in (
        ("USD", "officiel", "177"),
        ("EUR", "officiel", "200"),
        ("USD", "budget", "170"),
    ):
        appeler(
            dora,
            "post",
            "/taux/",
            {"devise": devise, "date": "2026-03-01", "taux": valeur, "type_taux": type_taux},
        )
    tous = appeler(dora, "get", "/taux/").json()
    assert len(tous) == 3
    usd = appeler(dora, "get", "/taux/?devise=USD").json()
    assert {t["devise"] for t in usd} == {"USD"} and len(usd) == 2
    budget = appeler(dora, "get", "/taux/?type_taux=budget").json()
    assert [(t["devise"], t["type_taux"]) for t in budget] == [("USD", "budget")]
