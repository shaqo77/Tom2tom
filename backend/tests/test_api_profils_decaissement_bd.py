# ruff: noqa: F811, E501
"""L'API HTTP des profils de décaissement : un administrateur construit, valide, active et fait
évoluer le profil d'un accord sans développeur. Phase B de L11 (B4).

Avant : un profil ne se construisait que par l'ORM. Le profil naît en brouillon, se valide (complétude
nommant chaque manque), s'active à sa date d'effet, et un profil actif ne se modifie pas : on crée une
version. Chaque refus de la base sort en 422 `{code, message}`, jamais en erreur serveur brute.
"""

import datetime

import pytest
from django.db import connection

from niveau1_socle.financements.services import (
    changer_statut_accord,
    creer_categorie,
    creer_compte_bancaire,
)
from niveau3_config.models import MethodeDecaissement, ProfilDecaissement, RegleFinancementCategorie
from tests.test_api_marches_bd import RACINE, api, appeler  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import _accord, cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def _poser(organisation):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


def _nb(monde) -> int:
    """Le nombre de profils EN BASE : l'organisation se repose, sinon la RLS cache tout et le compte
    vaut toujours zéro (un test « rien n'est créé » passerait à vide)."""
    _poser(monde[0])
    return ProfilDecaissement.objects.count()


def _en_base(monde, profil_id) -> ProfilDecaissement:
    _poser(monde[0])
    return ProfilDecaissement.objects.get(id=profil_id)


@pytest.fixture
def monde(api, cadre):
    organisation, projet, profils, _ = api
    _, _, _, bailleur = cadre
    _poser(organisation)
    accord = _accord(projet, profils, bailleur)
    changer_statut_accord(accord, "actif", utilisateur=profils["dora"])
    travaux = creer_categorie(
        utilisateur=profils["dora"], accord=accord, code="TRAVAUX", label={"fr": "Travaux"}
    )
    services = creer_categorie(
        utilisateur=profils["dora"], accord=accord, code="SERVICES", label={"fr": "Services"}
    )
    compte = creer_compte_bancaire(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code="CD-USD",
        type="designe",
        devise="USD",
        banque="BCI",
        numero="DJ21 0001 0000 0012 3456 7890",
    )
    _poser(organisation)
    return organisation, projet, profils, accord, (travaux, services), compte


def _chemin(projet, accord, fin=""):
    return f"/projets/{projet.id}/accords/{accord.id}/profils-decaissement/{fin}"


def _corps(**changes):
    base = {
        "valid_from": "2026-01-01",
        "regime": "transaction_based",
        "eligibility_date": "2026-01-01",
        "closing_date": "2030-12-31",
        "disbursement_deadline": "2031-04-30",
        "methodes": [
            {
                "method": "reimbursement",
                "supporting_docs": ["soe"],
                "full_doc_threshold": "100000",
                "min_application_pct_of_ceiling": "0.1",
            },
            {"method": "direct_payment", "supporting_docs": ["records"]},
        ],
        "regles": [
            {
                "category": "TRAVAUX",
                "allocation": "600000",
                "funding_rate": "0.85",
                "tax_basis": "taxes_included",
            },
            {
                "category": "SERVICES",
                "allocation": "300000",
                "funding_rate": "1",
                "tax_basis": "net_of_taxes",
                "eligibility_from": "2026-03-01",
            },
        ],
        "comptes": [
            {
                "compte": "CD-USD",
                "devise": "USD",
                "ceiling_kind": "fixed",
                "ceiling_amount": "200000",
                "replenishment_threshold_pct": "0.4",
            }
        ],
    }
    return base | changes


def _creer(monde, **changes):
    _, projet, profils, accord, _, _ = monde
    r = appeler(profils["dora"], "post", _chemin(projet, accord), _corps(**changes))
    assert r.status_code == 201, r.content
    return r.json()


# --- création et lecture -------------------------------------------------------------------------


def test_un_profil_se_cree_en_brouillon_avec_ses_methodes_regles_et_comptes(monde):
    _, projet, profils, accord, _, _ = monde
    p = _creer(monde)
    assert (p["status"], p["version"], p["regime"], p["accord"]) == (
        "draft",
        1,
        "transaction_based",
        accord.numero,
    )
    assert p["valid_from"] == "2026-01-01" and p["disbursement_deadline"] == "2031-04-30"
    assert [m["method"] for m in p["methodes"]] == ["direct_payment", "reimbursement"]
    reimb = next(m for m in p["methodes"] if m["method"] == "reimbursement")
    assert reimb["full_doc_threshold"] == "100000.0000"
    assert reimb["min_application_pct_of_ceiling"] == "0.100000"
    assert [(r["category"], r["funding_rate"], r["tax_basis"]) for r in p["regles"]] == [
        ("SERVICES", "1.000000", "net_of_taxes"),
        ("TRAVAUX", "0.850000", "taxes_included"),
    ]
    assert p["comptes"] == [
        {
            "compte": "CD-USD",
            "devise": "USD",
            "ceiling_kind": "fixed",
            "ceiling_amount": "200000.0000",
            "replenishment_threshold_pct": "0.400000",
        }
    ]
    assert not isinstance(p["regles"][0]["allocation"], float)


def test_le_brouillon_expose_sa_completude_avec_chaque_manque_nomme(monde):
    p = _creer(monde)
    c = p["completude"]
    assert c["complet"] is True and c["bloquantes"] == []
    assert {a["code"] for a in c["avertissements"]} >= {"taux_integral", "sans_exigence_source"}
    assert all(a["message"] for a in c["avertissements"])


def test_les_versions_se_numerotent_et_la_liste_les_rend_dans_l_ordre(monde):
    _, projet, profils, accord, _, _ = monde
    _creer(monde)
    _creer(monde, valid_from="2027-01-01")
    r = appeler(profils["dora"], "get", _chemin(projet, accord))
    assert [p["version"] for p in r.json()] == [1, 2]
    assert "methodes" not in r.json()[0]  # la liste est un résumé, le détail se lit à part


def test_le_detail_d_un_profil_se_lit_et_un_profil_inconnu_est_404(monde):
    _, projet, profils, accord, _, _ = monde
    p = _creer(monde)
    r = appeler(profils["amina"], "get", _chemin(projet, accord, f"{p['id']}/"))
    assert r.status_code == 200 and r.json()["id"] == p["id"]
    inconnu = "00000000-0000-0000-0000-000000000000"
    assert (
        appeler(profils["dora"], "get", _chemin(projet, accord, f"{inconnu}/")).status_code == 404
    )


def test_la_creation_exige_parametrer_et_la_lecture_consulter(monde):
    _, projet, profils, accord, _, _ = monde
    assert appeler(profils["amina"], "post", _chemin(projet, accord), _corps()).status_code == 403
    assert appeler(profils["bruno"], "post", _chemin(projet, accord), _corps()).status_code == 403
    assert _nb(monde) == 0


# --- refus ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "changes, attendu",
    [
        ({"regime": "inconnu"}, "Régime de décaissement inconnu"),
        (
            {
                "regles": [
                    {
                        "category": "NOPE",
                        "allocation": "1",
                        "funding_rate": "0.5",
                        "tax_basis": "taxes_included",
                    }
                ]
            },
            "Catégorie inconnue dans cet accord",
        ),
        (
            {"comptes": [{"compte": "NOPE", "devise": "USD", "ceiling_kind": "variable"}]},
            "Compte bancaire inconnu",
        ),
        (
            {"methodes": [{"method": "troc", "supporting_docs": ["soe"]}]},
            "Méthode de décaissement inconnue",
        ),
        (
            {"methodes": [{"method": "advance", "supporting_docs": ["fax"]}]},
            "Pièce exigée inconnue",
        ),
        (
            {
                "regles": [
                    {
                        "category": "TRAVAUX",
                        "allocation": "1",
                        "funding_rate": "0.5",
                        "tax_basis": "x",
                    }
                ]
            },
            "Assiette de taxes inconnue",
        ),
        (
            {"comptes": [{"compte": "CD-USD", "devise": "XXX", "ceiling_kind": "variable"}]},
            "Devise inconnue",
        ),
        (
            {"comptes": [{"compte": "CD-USD", "devise": "USD", "ceiling_kind": "mobile"}]},
            "Type de plafond inconnu",
        ),
        ({"exigence": "REQ-INCONNUE"}, "Aucune exigence validée ou active"),
    ],
)
def test_une_donnee_inconnue_est_refusee_en_nommant_la_valeur(monde, changes, attendu):
    _, projet, profils, accord, _, _ = monde
    r = appeler(profils["dora"], "post", _chemin(projet, accord), _corps(**changes))
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}, r.content
    assert attendu in r.json()["message"]
    assert _nb(monde) == 0  # rien n'est créé à moitié


@pytest.mark.parametrize(
    "changes, attendu",
    [
        (
            {
                "regles": [
                    {
                        "category": "TRAVAUX",
                        "allocation": "1",
                        "funding_rate": "1.5",
                        "tax_basis": "taxes_included",
                    }
                ]
            },
            "supérieur à 0 et au plus égal à 1",
        ),
        (
            {
                "regles": [
                    {
                        "category": "TRAVAUX",
                        "allocation": "1",
                        "funding_rate": "0.5",
                        "tax_basis": "taxes_included",
                    },
                    {
                        "category": "TRAVAUX",
                        "allocation": "1",
                        "funding_rate": "0.5",
                        "tax_basis": "taxes_included",
                    },
                ]
            },
            "qu'une règle par profil",
        ),
        (
            {
                "methodes": [
                    {"method": "advance", "supporting_docs": ["soe"]},
                    {"method": "advance", "supporting_docs": ["soe"]},
                ]
            },
            "qu'une fois par profil",
        ),
        (
            {
                "methodes": [
                    {
                        "method": "advance",
                        "supporting_docs": ["soe"],
                        "min_application_amount": "10",
                        "min_application_pct_of_ceiling": "0.1",
                    }
                ]
            },
            "pas les deux",
        ),
        (
            {
                "methodes": [
                    {
                        "method": "advance",
                        "supporting_docs": ["soe"],
                        "min_application_pct_of_ceiling": "1.5",
                    }
                ]
            },
            "entre 0 et 1",
        ),
        (
            {"comptes": [{"compte": "CD-USD", "devise": "USD", "ceiling_kind": "fixed"}]},
            "plafond fixe porte un montant",
        ),
        ({"eligibility_date": "2031-01-01", "closing_date": "2030-12-31"}, "pas dans l'ordre"),
        (
            {
                "regles": [
                    {
                        "category": "TRAVAUX",
                        "allocation": "1",
                        "funding_rate": "0.5",
                        "tax_basis": "taxes_included",
                        "eligibility_from": "2027-01-01",
                        "eligibility_to": "2026-01-01",
                    }
                ]
            },
            "début d'éligibilité",
        ),
    ],
)
def test_une_contrainte_de_la_base_sort_en_refus_metier_precis(monde, changes, attendu):
    _, projet, profils, accord, _, _ = monde
    r = appeler(profils["dora"], "post", _chemin(projet, accord), _corps(**changes))
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}, r.content
    assert attendu in r.json()["message"]
    assert _nb(monde) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"valid_from": "demain"},
        {"methodes": []},
        {"methodes": "reimbursement"},
        {
            "regles": [
                {
                    "category": "TRAVAUX",
                    "allocation": 1.5,
                    "funding_rate": "0.5",
                    "tax_basis": "taxes_included",
                }
            ]
        },
        {
            "regles": [
                {
                    "category": "TRAVAUX",
                    "allocation": "1",
                    "funding_rate": 0.85,
                    "tax_basis": "taxes_included",
                }
            ]
        },
        {
            "regles": [
                {
                    "category": "TRAVAUX",
                    "allocation": "-1",
                    "funding_rate": "0.5",
                    "tax_basis": "taxes_included",
                }
            ]
        },
        {
            "regles": [
                {
                    "category": "TRAVAUX",
                    "allocation": "1",
                    "funding_rate": "NaN",
                    "tax_basis": "taxes_included",
                }
            ]
        },
        {"methodes": [{"method": "advance", "supporting_docs": "soe"}]},
        {"methodes": [{"method": "advance", "supporting_docs": ["soe"], "is_enabled": "oui"}]},
        {"closing_date": "pas une date"},
    ],
)
def test_un_corps_mal_forme_est_refuse_au_format_stable(monde, changes):
    _, projet, profils, accord, _, _ = monde
    r = appeler(profils["dora"], "post", _chemin(projet, accord), _corps(**changes))
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}, (changes, r.content)
    assert _nb(monde) == 0


def test_un_profil_ne_se_rattache_pas_a_l_accord_d_un_autre_projet(monde):
    organisation, projet, profils, accord, _, _ = monde
    from tests.test_cycle_ecriture_bd import _creer_projet

    autre = _creer_projet(organisation, "AUTRE")
    _poser(organisation)
    r = appeler(profils["dora"], "post", _chemin(autre, accord), _corps())
    assert r.status_code == 404


# --- cycle de vie --------------------------------------------------------------------------------


def test_valider_puis_activer_fait_passer_le_profil_et_le_fige(monde):
    _, projet, profils, accord, _, _ = monde
    p = _creer(monde)
    v = appeler(profils["bruno"], "post", _chemin(projet, accord, f"{p['id']}/valider/"), {})
    assert v.status_code == 200 and v.json()["status"] == "validated"
    assert "completude" not in v.json()  # la complétude ne concerne que le brouillon
    a = appeler(profils["dora"], "post", _chemin(projet, accord, f"{p['id']}/activer/"), {})
    assert a.status_code == 200 and a.json()["status"] == "active"


def test_valider_exige_l_habilitation_valider_et_activer_parametrer(monde):
    _, projet, profils, accord, _, _ = monde
    p = _creer(monde)
    assert (
        appeler(
            profils["dora"], "post", _chemin(projet, accord, f"{p['id']}/valider/"), {}
        ).status_code
        == 403
    )
    appeler(profils["bruno"], "post", _chemin(projet, accord, f"{p['id']}/valider/"), {})
    assert (
        appeler(
            profils["bruno"], "post", _chemin(projet, accord, f"{p['id']}/activer/"), {}
        ).status_code
        == 403
    )
    assert _en_base(monde, p["id"]).status == "validated"


def test_un_profil_incomplet_ne_se_valide_pas_et_le_refus_nomme_le_manque(monde):
    _, projet, profils, accord, (travaux, _), _ = monde
    p = _creer(
        monde,
        regles=[
            {
                "category": "TRAVAUX",
                "allocation": "5000000",
                "funding_rate": "0.5",
                "tax_basis": "taxes_included",
            }
        ],
    )
    r = appeler(profils["bruno"], "post", _chemin(projet, accord, f"{p['id']}/valider/"), {})
    assert r.status_code == 422 and "alloc" in r.json()["message"].lower()
    detail = appeler(profils["dora"], "get", _chemin(projet, accord, f"{p['id']}/")).json()
    assert detail["status"] == "draft"
    assert [a["code"] for a in detail["completude"]["bloquantes"]] == ["allocations_excessives"]
    assert detail["completude"]["complet"] is False


def test_on_ne_saute_pas_d_etape_activer_un_brouillon_est_refuse(monde):
    _, projet, profils, accord, _, _ = monde
    p = _creer(monde)
    r = appeler(profils["dora"], "post", _chemin(projet, accord, f"{p['id']}/activer/"), {})
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}
    assert _en_base(monde, p["id"]).status == "draft"


def test_rejeter_exige_un_motif_et_se_lit_ensuite(monde):
    _, projet, profils, accord, _, _ = monde
    p = _creer(monde)
    sans = appeler(profils["bruno"], "post", _chemin(projet, accord, f"{p['id']}/rejeter/"), {})
    assert sans.status_code == 422
    r = appeler(
        profils["bruno"],
        "post",
        _chemin(projet, accord, f"{p['id']}/rejeter/"),
        {"motif": "taux erroné"},
    )
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert r.json()["rejection_reason"] == "taux erroné"


def test_activer_une_nouvelle_version_ferme_la_precedente_a_sa_date_d_effet(monde):
    _, projet, profils, accord, _, _ = monde
    v1 = _creer(monde)
    for fin in ("valider", "activer"):
        who = profils["bruno"] if fin == "valider" else profils["dora"]
        assert (
            appeler(who, "post", _chemin(projet, accord, f"{v1['id']}/{fin}/"), {}).status_code
            == 200
        )
    r = appeler(
        profils["dora"],
        "post",
        _chemin(projet, accord, f"{v1['id']}/nouvelle-version/"),
        {
            "valid_from": "2027-01-01",
            "allocations": {"TRAVAUX": "650000"},
            "dates": {"closing_date": "2031-06-30", "disbursement_deadline": "2031-10-31"},
        },
    )
    assert r.status_code == 201, r.content
    v2 = r.json()
    assert (v2["version"], v2["status"], v2["valid_from"]) == (2, "draft", "2027-01-01")
    assert v2["closing_date"] == "2031-06-30"
    travaux = next(x for x in v2["regles"] if x["category"] == "TRAVAUX")
    assert travaux["allocation"] == "650000.0000"
    # le reste est repris à l'identique
    assert [m["method"] for m in v2["methodes"]] == ["direct_payment", "reimbursement"]
    assert len(v2["comptes"]) == 1
    for fin in ("valider", "activer"):
        who = profils["bruno"] if fin == "valider" else profils["dora"]
        assert (
            appeler(who, "post", _chemin(projet, accord, f"{v2['id']}/{fin}/"), {}).status_code
            == 200
        )
    ancien = _en_base(monde, v1["id"])
    assert ancien.valid_to == datetime.date(2027, 1, 1) and ancien.status == "active"


def test_une_nouvelle_version_refuse_une_categorie_ou_un_jalon_inconnu(monde):
    _, projet, profils, accord, _, _ = monde
    v1 = _creer(monde)
    chemin = _chemin(projet, accord, f"{v1['id']}/nouvelle-version/")
    for corps in (
        {"valid_from": "2027-01-01", "allocations": {"NOPE": "1"}},
        {"valid_from": "2027-01-01", "dates": {"inconnu": "2027-01-01"}},
        {"valid_from": "2027-01-01", "allocations": {"TRAVAUX": 1.5}},
        {"valid_from": "2027-01-01", "allocations": {"TRAVAUX": "-1"}},
        {"allocations": {}},
    ):
        r = appeler(profils["dora"], "post", chemin, corps)
        assert r.status_code == 422 and set(r.json()) == {"code", "message"}, corps
    assert _nb(monde) == 1
    assert (
        appeler(profils["amina"], "post", chemin, {"valid_from": "2027-01-01"}).status_code == 403
    )


def test_la_comparaison_montre_ce_qui_change_entre_deux_versions(monde):
    _, projet, profils, accord, _, _ = monde
    v1 = _creer(monde)
    v2 = appeler(
        profils["dora"],
        "post",
        _chemin(projet, accord, f"{v1['id']}/nouvelle-version/"),
        {"valid_from": "2027-01-01", "allocations": {"TRAVAUX": "650000"}},
    ).json()
    r = appeler(profils["dora"], "get", _chemin(projet, accord, f"{v1['id']}/comparaison/?avec=2"))
    assert r.status_code == 200
    c = r.json()
    assert (c["de"], c["vers"], c["identiques"]) == (1, 2, False)
    modifies = {m["cle"]: m["ecarts"] for m in c["categories"]["modifies"]}
    assert modifies["TRAVAUX"]["allocation"] == {"avant": "600000.0000", "apres": "650000.0000"}
    assert "SERVICES" in c["categories"]["identiques"]
    assert c["methodes"]["modifies"] == [] and c["comptes"]["modifies"] == []
    assert v2["version"] == 2
    assert (
        appeler(
            profils["dora"], "get", _chemin(projet, accord, f"{v1['id']}/comparaison/")
        ).status_code
        == 422
    )
    assert (
        appeler(
            profils["dora"], "get", _chemin(projet, accord, f"{v1['id']}/comparaison/?avec=9")
        ).status_code
        == 404
    )


def test_le_profil_cree_par_l_api_pilote_le_calcul_du_decaissement(monde):
    """Le profil API est le MÊME que celui des services : la règle de calcul le lit."""
    from decimal import Decimal

    from niveau3_config.services.decaissement import (
        montant_a_retirer,
        profil_en_vigueur,
        regle_pour,
    )

    organisation, projet, profils, accord, (travaux, _), _ = monde
    p = _creer(monde)
    appeler(profils["bruno"], "post", _chemin(projet, accord, f"{p['id']}/valider/"), {})
    appeler(profils["dora"], "post", _chemin(projet, accord, f"{p['id']}/activer/"), {})
    _poser(organisation)
    profil = profil_en_vigueur(accord, datetime.date(2026, 6, 1))
    assert profil is not None and str(profil.id) == p["id"]
    regle = regle_pour(profil, travaux)
    assert montant_a_retirer(Decimal("1000"), regle.funding_rate, regle.tax_basis) == Decimal("850")
    assert (
        RegleFinancementCategorie.objects.count() == 2 and MethodeDecaissement.objects.count() == 2
    )
