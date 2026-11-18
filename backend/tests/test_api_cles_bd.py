# ruff: noqa: F811, E501
"""L'API HTTP des clés de cofinancement : un administrateur règle la répartition entre bailleurs sans
développeur, puis la saisie l'utilise. Phase B de L11.

Avant : créer une clé et ses versions n'était possible que par appel de service Python.
"""

import datetime
from decimal import Decimal

import pytest
from django.db import connection

from niveau1_socle.comptabilite.services import saisir_ecriture
from tests.test_api_marches_bd import RACINE, appeler  # noqa: F401
from tests.test_cles_cofinancement_bd import cles  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
D = Decimal


def _chemin(projet, fin=""):
    return f"/projets/{projet.id}/cles-cofinancement/{fin}"


def _corps_version(**champs):
    return {
        "parts": {"IDA": 60, "GOV": 30, "UE": 10},
        "porteur": "GOV",
        "valid_from": "2026-01-01",
        "motif": "Clé initiale",
    } | champs


def test_une_cle_se_cree_par_http_puis_se_liste(cles):
    _, projet, profils, _, _ = cles
    dora = profils["dora"]
    r = appeler(
        dora,
        "post",
        _chemin(projet),
        {"code": "VEHICULES", "label": {"fr": "Véhicules", "en": "Vehicles"}},
    )
    assert r.status_code == 201, r.content
    assert r.json()["code"] == "VEHICULES" and r.json()["label"]["fr"] == "Véhicules"
    codes = [c["code"] for c in appeler(dora, "get", _chemin(projet)).json()]
    assert codes == ["CHARGES", "VEHICULES"]


def test_un_code_de_cle_deja_pris_est_un_refus_lisible_pas_une_panne(cles):
    _, projet, profils, _, _ = cles
    r = appeler(
        profils["dora"], "post", _chemin(projet), {"code": "CHARGES", "label": {"fr": "Doublon"}}
    )
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}
    assert "CHARGES" in r.json()["message"]


def test_code_et_libelle_sont_obligatoires_et_le_libelle_est_un_dictionnaire(cles):
    _, projet, profils, _, _ = cles
    dora = profils["dora"]
    assert appeler(dora, "post", _chemin(projet), {"label": {"fr": "x"}}).status_code == 422
    assert appeler(dora, "post", _chemin(projet), {"code": "X"}).status_code == 422
    assert (
        appeler(dora, "post", _chemin(projet), {"code": "X", "label": "texte"}).status_code == 422
    )


def test_une_version_se_pose_avec_des_parts_exactes_et_close_la_precedente(cles):
    _, projet, profils, accords, cle = cles
    dora = profils["dora"]
    r = appeler(dora, "post", _chemin(projet, f"{cle.id}/versions/"), _corps_version())
    assert r.status_code == 201, r.content
    v1 = r.json()
    assert v1["version"] == 1 and v1["porteur"] == "GOV" and v1["valid_to"] is None
    parts = {p["accord"]: D(p["part"]) for p in v1["parts"]}
    assert parts == {"IDA": D("0.6"), "GOV": D("0.3"), "UE": D("0.1")}
    assert sum(parts.values()) == D(1)  # exactes
    assert all(isinstance(p["part"], str) for p in v1["parts"])
    r2 = appeler(
        dora,
        "post",
        _chemin(projet, f"{cle.id}/versions/"),
        _corps_version(parts={"IDA": 1, "GOV": 1}, valid_from="2026-07-01"),
    )
    assert r2.status_code == 201 and r2.json()["version"] == 2
    detail = appeler(dora, "get", _chemin(projet, f"{cle.id}/")).json()
    assert [(v["version"], v["valid_from"], v["valid_to"]) for v in detail["versions"]] == [
        (2, "2026-07-01", None),
        (1, "2026-01-01", "2026-07-01"),  # l'ancienne reste, close à la date d'effet
    ]


def test_la_liste_donne_la_version_en_vigueur_a_la_date_demandee(cles):
    _, projet, profils, _, cle = cles
    dora = profils["dora"]
    appeler(dora, "post", _chemin(projet, f"{cle.id}/versions/"), _corps_version())
    appeler(
        dora,
        "post",
        _chemin(projet, f"{cle.id}/versions/"),
        _corps_version(parts={"IDA": 1, "GOV": 1}, valid_from="2026-07-01"),
    )

    def en(jour):
        corps = appeler(dora, "get", _chemin(projet) + f"?jour={jour}").json()
        return corps[0]["version_en_vigueur"]

    assert en("2025-12-31") is None  # avant la première version
    assert en("2026-03-01")["version"] == 1
    assert en("2026-07-01")["version"] == 2  # la fin est exclue, le début inclus


@pytest.mark.parametrize(
    "champs",
    [
        {"parts": {"IDA": 0, "GOV": 1}},  # poids nul
        {"parts": {"IDA": -5, "GOV": 1}},  # poids négatif
        {"parts": {"IDA": 1.5, "GOV": 1}},  # jamais de nombre à virgule JSON
        {"parts": {"IDA": "abc", "GOV": 1}},
        {"parts": {}},
        {"parts": {"INCONNU": 1, "GOV": 1}},  # accord qui n'existe pas dans ce projet
        {"porteur": "UE", "parts": {"IDA": 1, "GOV": 1}},  # porteur hors de la clé
        {"valid_from": "pas-une-date"},
        {"parts": "texte"},
    ],
)
def test_une_version_invalide_est_refusee_au_format_stable(cles, champs):
    _, projet, profils, _, cle = cles
    r = appeler(
        profils["dora"], "post", _chemin(projet, f"{cle.id}/versions/"), _corps_version(**champs)
    )
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}, r.content


def test_une_version_ne_peut_pas_prendre_effet_avant_la_precedente(cles):
    _, projet, profils, _, cle = cles
    dora = profils["dora"]
    appeler(
        dora,
        "post",
        _chemin(projet, f"{cle.id}/versions/"),
        _corps_version(valid_from="2026-06-01"),
    )
    r = appeler(
        dora,
        "post",
        _chemin(projet, f"{cle.id}/versions/"),
        _corps_version(valid_from="2026-03-01"),
    )
    assert r.status_code == 422 and "2026-06-01" in r.json()["message"]


def test_sans_habilitation_parametrer_on_ne_cree_rien_mais_on_peut_lire(cles):
    _, projet, profils, _, cle = cles
    amina = profils["amina"]  # consulter + saisir, pas parametrer
    assert (
        appeler(amina, "post", _chemin(projet), {"code": "X", "label": {"fr": "x"}}).status_code
        == 403
    )
    assert (
        appeler(amina, "post", _chemin(projet, f"{cle.id}/versions/"), _corps_version()).status_code
        == 403
    )
    assert appeler(amina, "get", _chemin(projet)).status_code == 200


def test_une_cle_d_un_autre_projet_est_introuvable(cles):
    organisation, projet, profils, _, cle = cles
    from tests.test_cycle_ecriture_bd import _creer_projet

    autre = _creer_projet(organisation, "AUTRE")
    # dora n'a aucun droit sur l'autre projet : refus ; et même avec le droit, la clé n'y existe pas.
    assert appeler(profils["dora"], "get", _chemin(autre, f"{cle.id}/")).status_code in (403, 404)


def test_de_bout_en_bout_une_cle_reglee_par_http_ventile_la_saisie(cles):
    """L'administrateur règle la clé par l'API ; la saisie s'en sert sans qu'on calcule une part."""
    organisation, projet, profils, accords, cle = cles
    dora, amina = profils["dora"], profils["amina"]
    assert (
        appeler(dora, "post", _chemin(projet, f"{cle.id}/versions/"), _corps_version()).status_code
        == 201
    )
    with connection.cursor() as cur:  # les appels HTTP remettent le périmètre à zéro
        cur.execute("SET app.org_id = %s", [str(organisation.id)])
    ecriture = saisir_ecriture(
        utilisateur=amina, project_id=projet.id, journal="OD", date_comptable=datetime.date(2026, 3, 10),
        libelle="Charge commune",
        lignes=[{"compte": "6011", "debit": "1001", "cle": "CHARGES"}, {"compte": "5211", "credit": "1001"}],
    )  # fmt: skip
    charges = ecriture.lignes.filter(account__code="6011")
    assert {ligne.agreement_id: ligne.debit for ligne in charges} == {
        accords["IDA"].pk: D(600),
        accords["GOV"].pk: D(301),
        accords["UE"].pk: D(100),
    }


def test_sans_aucun_droit_sur_le_projet_on_ne_lit_rien(cles):
    from django.contrib.auth import get_user_model

    organisation, projet, profils, _, cle = cles
    inconnu = get_user_model().objects.create_user("ivan", password="x", org_id=organisation.id)
    assert appeler(inconnu, "get", _chemin(projet)).status_code == 403
    assert appeler(inconnu, "get", _chemin(projet, f"{cle.id}/")).status_code == 403


def test_un_libelle_vide_ou_non_textuel_est_refuse(cles):
    _, projet, profils, _, _ = cles
    dora = profils["dora"]
    for label in ({"fr": ""}, {"fr": "   "}, {"fr": 5}, {}):
        r = appeler(dora, "post", _chemin(projet), {"code": "X", "label": label})
        assert r.status_code == 422, label


def test_une_cle_s_adresse_par_son_projet_pas_par_un_autre(cles):
    """Même avec des droits sur les deux projets, la clé de l'un ne se lit ni ne se modifie via l'autre."""
    from niveau1_socle.financements.cles import creer_cle
    from niveau1_socle.habilitations.models import Habilitation, Role
    from tests.test_cycle_ecriture_bd import _creer_projet, _poser

    organisation, projet, profils, _, cle = cles
    autre = _creer_projet(organisation, "AUTRE")
    role = Role.objects.create(
        org_id=organisation.id,
        code="DORA2",
        label={"fr": "d"},
        operations=["consulter", "parametrer"],
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=profils["dora"].id, project_id=autre.id, role=role
    )
    _poser(organisation)
    cle_autre = creer_cle(
        utilisateur=profils["dora"], project_id=autre.id, code="AUTRE-CLE", label={"fr": "autre"}
    )
    dora = profils["dora"]
    assert appeler(dora, "get", _chemin(projet, f"{cle_autre.id}/")).status_code == 404
    r = appeler(dora, "post", _chemin(projet, f"{cle_autre.id}/versions/"), _corps_version())
    assert r.status_code == 404
    assert appeler(dora, "get", _chemin(autre, f"{cle_autre.id}/")).status_code == 200
