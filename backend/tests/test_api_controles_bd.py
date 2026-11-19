# ruff: noqa: F811, E501
"""L'API HTTP des contrôles : installer la bibliothèque, écrire un contrôle, le valider et l'activer
sans développeur. Phase B de L11 (B5).

Avant : un contrôle ne se créait que par un appel de service Python. Rien n'est actif sans personne
habilitée (règle 9) : installer ne crée que des brouillons ; un contrôle actif refuse ensuite la
validation d'une dépense (A4), ce que le dernier test prouve de bout en bout.
"""

import datetime

import pytest
from django.db import connection

from niveau4_reporting.controles.models import Controle
from tests.test_api_marches_bd import api, appeler  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def _poser(organisation):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


def _nb(api, **filtres) -> int:
    """Les contrôles EN BASE : l'organisation se repose (la RLS cache tout sinon, et le compte
    vaudrait toujours zéro)."""
    _poser(api[0])
    return Controle.objects.filter(**filtres).count()


def _chemin(projet, fin=""):
    return f"/projets/{projet.id}/controles/{fin}"


def _corps(**changes):
    base = {
        "code": "DEPENSE-SANS-PIECE",
        "label": {"fr": "Dépense sans pièce", "en": "Expense without document"},
        "type_regle": "pieces",
        "severity": "bloquant",
        "valid_from": "2026-01-01",
        "expression": {
            "type_regle": "pieces",
            "conditions": [{"champ": "pieces", "op": "est_renseigne"}],
        },
        "action_corrective": {"fr": "Joindre la pièce", "en": "Attach the document"},
    }
    return base | changes


def _creer(api, **changes):
    _, projet, profils, _ = api
    r = appeler(profils["dora"], "post", _chemin(projet), _corps(**changes))
    assert r.status_code == 201, r.content
    return r.json()


# --- bibliothèque ------------------------------------------------------------------------------


def test_la_bibliotheque_liste_les_controles_livres_et_ceux_deja_installes(api):
    _, projet, profils, _ = api
    r = appeler(profils["amina"], "get", _chemin(projet, "bibliotheque/"))
    assert r.status_code == 200
    codes = {c["code"]: c for c in r.json()}
    assert {"COD-CATEGORIE", "ELIG-PERIODE-ACCORD", "PIE-ETAT-CERTIFIE"} <= set(codes)
    assert not any(c["installe"] for c in codes.values())
    assert set(codes["COD-CATEGORIE"]["label"]) == {"fr", "en"}
    appeler(
        profils["dora"],
        "post",
        _chemin(projet, "bibliotheque/installer/"),
        {"valid_from": "2026-01-01", "codes": ["COD-CATEGORIE"]},
    )
    apres = {
        c["code"]: c["installe"]
        for c in appeler(profils["amina"], "get", _chemin(projet, "bibliotheque/")).json()
    }
    assert apres["COD-CATEGORIE"] is True and apres["COD-SOURCE"] is False


def test_installer_cree_des_brouillons_jamais_actifs_et_ne_recree_rien(api):
    _, projet, profils, _ = api
    chemin = _chemin(projet, "bibliotheque/installer/")
    r = appeler(
        profils["dora"],
        "post",
        chemin,
        {"valid_from": "2026-01-01", "codes": ["COD-CATEGORIE", "COD-SOURCE"]},
    )
    assert r.status_code == 201 and r.json() == {
        "crees": ["COD-CATEGORIE", "COD-SOURCE"],
        "deja_presents": [],
    }
    assert _nb(api, status="draft") == 2 and _nb(api, status="active") == 0  # règle 9
    encore = appeler(
        profils["dora"], "post", chemin, {"valid_from": "2026-01-01", "codes": ["COD-CATEGORIE"]}
    )
    assert encore.status_code == 200 and encore.json() == {
        "crees": [],
        "deja_presents": ["COD-CATEGORIE"],
    }
    assert _nb(api) == 2


def test_installer_sans_codes_installe_toute_la_bibliotheque(api):
    _, projet, profils, _ = api
    r = appeler(
        profils["dora"],
        "post",
        _chemin(projet, "bibliotheque/installer/"),
        {"valid_from": "2026-01-01"},
    )
    livres = appeler(profils["amina"], "get", _chemin(projet, "bibliotheque/")).json()
    assert r.status_code == 201 and len(r.json()["crees"]) == len(livres) > 15
    assert _nb(api, status="draft") == len(livres) and _nb(api, status="active") == 0


@pytest.mark.parametrize(
    "corps",
    [
        {"valid_from": "2026-01-01", "codes": ["INCONNU"]},
        {"valid_from": "2026-01-01", "codes": []},
        {"valid_from": "2026-01-01", "codes": "COD-CATEGORIE"},
        {"valid_from": "2026-01-01", "codes": [1]},
        {"codes": ["COD-CATEGORIE"]},
        {"valid_from": "demain"},
    ],
)
def test_une_installation_invalide_est_refusee_au_format_stable_sans_rien_creer(api, corps):
    _, projet, profils, _ = api
    r = appeler(profils["dora"], "post", _chemin(projet, "bibliotheque/installer/"), corps)
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}, r.content
    assert _nb(api) == 0


# --- création et lecture -------------------------------------------------------------------------


def test_un_controle_se_cree_en_brouillon_et_se_relit_en_detail(api):
    _, projet, profils, _ = api
    c = _creer(api)
    assert (c["status"], c["version"], c["mode"], c["severity"]) == (
        "draft",
        1,
        "automatique",
        "bloquant",
    )
    assert c["expression"]["conditions"][0]["champ"] == "pieces"
    assert c["action_corrective"]["en"] == "Attach the document"
    r = appeler(profils["amina"], "get", _chemin(projet, f"{c['id']}/"))
    assert r.status_code == 200 and r.json() == c
    liste = appeler(profils["amina"], "get", _chemin(projet))
    assert [x["code"] for x in liste.json()] == ["DEPENSE-SANS-PIECE"]
    assert "expression" not in liste.json()[0]  # la liste est un résumé


def test_un_controle_a_verifier_a_la_main_n_a_pas_d_expression(api):
    c = _creer(api, code="REVUE-HUMAINE", manuel=True, expression=None)
    assert c["mode"] == "manuel" and c["expression"] is None


def test_les_versions_se_numerotent_et_la_liste_se_filtre(api):
    _, projet, profils, _ = api
    _creer(api)
    _creer(api, valid_from="2027-01-01")
    _creer(api, code="AUTRE")
    dora = profils["dora"]
    assert [
        c["version"]
        for c in appeler(dora, "get", _chemin(projet) + "?code=DEPENSE-SANS-PIECE").json()
    ] == [1, 2]
    assert [c["code"] for c in appeler(dora, "get", _chemin(projet) + "?status=draft").json()] == [
        "AUTRE",
        "DEPENSE-SANS-PIECE",
        "DEPENSE-SANS-PIECE",
    ]
    assert appeler(dora, "get", _chemin(projet) + "?status=zzz").status_code == 422


@pytest.mark.parametrize(
    "changes, attendu",
    [
        ({"type_regle": "inconnu"}, "Type de règle inconnu"),
        ({"severity": "grave"}, "Sévérité inconnue"),
        (
            {
                "expression": {
                    "type_regle": "pieces",
                    "conditions": [{"champ": "inconnu", "op": "est_renseigne"}],
                }
            },
            None,
        ),
        (
            {
                "expression": {
                    "type_regle": "pieces",
                    "conditions": [{"champ": "pieces", "op": "eval"}],
                }
            },
            None,
        ),
        (
            {
                "expression": {
                    "type_regle": "budget",
                    "conditions": [{"champ": "pieces", "op": "est_renseigne"}],
                }
            },
            None,
        ),
        ({"expression": None}, None),
        ({"manuel": True}, None),
        ({"manuel": "oui"}, None),
        ({"label": "texte"}, None),
        ({"label": None}, None),
        ({"valid_from": "demain"}, None),
        ({"code": ""}, None),
        ({"applicable_si": "x"}, None),
        ({"parametres": {"inconnu": 1}}, None),
    ],
)
def test_un_controle_invalide_est_refuse_au_format_stable(api, changes, attendu):
    _, projet, profils, _ = api
    r = appeler(profils["dora"], "post", _chemin(projet), _corps(**changes))
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}, (changes, r.content)
    if attendu:
        assert attendu in r.json()["message"]
    assert _nb(api) == 0


def test_la_creation_exige_parametrer_et_la_lecture_consulter(api):
    _, projet, profils, _ = api
    assert appeler(profils["amina"], "post", _chemin(projet), _corps()).status_code == 403
    assert appeler(profils["bruno"], "post", _chemin(projet), _corps()).status_code == 403
    assert _nb(api) == 0


def test_un_controle_inconnu_est_404(api):
    _, projet, profils, _ = api
    inconnu = "00000000-0000-0000-0000-000000000000"
    assert appeler(profils["dora"], "get", _chemin(projet, f"{inconnu}/")).status_code == 404
    assert (
        appeler(profils["bruno"], "post", _chemin(projet, f"{inconnu}/valider/"), {}).status_code
        == 404
    )


# --- cycle de vie --------------------------------------------------------------------------------


def test_valider_puis_activer_fait_passer_le_controle(api):
    _, projet, profils, _ = api
    c = _creer(api)
    v = appeler(profils["bruno"], "post", _chemin(projet, f"{c['id']}/valider/"), {})
    assert v.status_code == 200 and v.json()["status"] == "validated"
    a = appeler(profils["dora"], "post", _chemin(projet, f"{c['id']}/activer/"), {})
    assert a.status_code == 200 and a.json()["status"] == "active"


def test_valider_exige_valider_et_activer_parametrer(api):
    _, projet, profils, _ = api
    c = _creer(api)
    assert (
        appeler(profils["dora"], "post", _chemin(projet, f"{c['id']}/valider/"), {}).status_code
        == 403
    )
    appeler(profils["bruno"], "post", _chemin(projet, f"{c['id']}/valider/"), {})
    assert (
        appeler(profils["bruno"], "post", _chemin(projet, f"{c['id']}/activer/"), {}).status_code
        == 403
    )
    assert _nb(api, status="validated") == 1 and _nb(api, status="active") == 0


def test_on_ne_saute_pas_d_etape_activer_un_brouillon_est_un_conflit(api):
    _, projet, profils, _ = api
    c = _creer(api)
    r = appeler(profils["dora"], "post", _chemin(projet, f"{c['id']}/activer/"), {})
    assert r.status_code == 409 and r.json()["code"] == "TRANSITION_INTERDITE"
    assert _nb(api, status="draft") == 1


def test_rejeter_exige_un_motif(api):
    _, projet, profils, _ = api
    c = _creer(api)
    sans = appeler(profils["bruno"], "post", _chemin(projet, f"{c['id']}/rejeter/"), {})
    assert sans.status_code == 409 and _nb(api, status="rejected") == 0
    r = appeler(
        profils["bruno"],
        "post",
        _chemin(projet, f"{c['id']}/rejeter/"),
        {"motif": "règle trop large"},
    )
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    # un contrôle rejeté ne s'active plus
    assert (
        appeler(profils["dora"], "post", _chemin(projet, f"{c['id']}/activer/"), {}).status_code
        == 409
    )


def test_activer_une_nouvelle_version_ferme_la_precedente_a_sa_date_d_effet(api):
    _, projet, profils, _ = api
    v1 = _creer(api)
    v2 = _creer(api, valid_from="2027-01-01", severity="avertissement")
    for c in (v1, v2):
        appeler(profils["bruno"], "post", _chemin(projet, f"{c['id']}/valider/"), {})
        assert (
            appeler(profils["dora"], "post", _chemin(projet, f"{c['id']}/activer/"), {}).status_code
            == 200
        )
    _poser(api[0])
    ancien = Controle.objects.get(id=v1["id"])
    assert ancien.valid_to == datetime.date(2027, 1, 1) and ancien.status == "active"
    assert Controle.objects.get(id=v2["id"]).severity == "avertissement"


# --- bout en bout : un contrôle écrit et activé par l'API refuse une validation ---------------


def test_un_controle_installe_et_active_par_l_api_refuse_la_validation_d_une_depense(api, cadre):
    """Le contrôle « dépense sans catégorie » de la bibliothèque, installé puis activé par HTTP
    uniquement, refuse la validation d'une écriture dont la charge n'a pas de catégorie."""
    from core.erreurs import CodeErreur, ErreurMetier
    from niveau1_socle.comptabilite.models import Ecriture, LigneEcriture
    from niveau1_socle.comptabilite.services import valider_ecriture
    from niveau1_socle.financements.services import changer_statut_accord
    from tests.test_demandes_retrait_bd import _depense
    from tests.test_financements_bd import _accord

    organisation, projet, profils, _ = api
    _, _, _, bailleur = cadre
    _poser(organisation)
    accord = _accord(projet, profils, bailleur)
    changer_statut_accord(accord, "actif", utilisateur=profils["dora"])
    chemin = _chemin(projet, "bibliotheque/installer/")
    assert (
        appeler(
            profils["dora"],
            "post",
            chemin,
            {"valid_from": "2026-01-01", "codes": ["COD-CATEGORIE"]},
        ).status_code
        == 201
    )
    _poser(organisation)
    controle = Controle.objects.get(code="COD-CATEGORIE")
    assert (
        appeler(
            profils["bruno"], "post", _chemin(projet, f"{controle.id}/valider/"), {}
        ).status_code
        == 200
    )
    assert (
        appeler(profils["dora"], "post", _chemin(projet, f"{controle.id}/activer/"), {}).status_code
        == 200
    )
    _poser(organisation)
    ligne_id = _depense(organisation, projet, accord, None, 100, statut="draft")
    ligne = LigneEcriture.objects.select_related("entry").get(pk=ligne_id)
    with pytest.raises(ErreurMetier) as refus:
        valider_ecriture(Ecriture.objects.get(pk=ligne.entry_id), utilisateur=profils["bruno"])
    assert refus.value.code == CodeErreur.CONTROLE_BLOQUANT
