# ruff: noqa: F811, E501
"""Le branchement des contrôles BAD : ce que le profil applique déjà, ce qu'il n'applique pas. L11-D2.

Chaque règle de contrôle du profil BAD dit COMMENT elle est appliquée : par le profil de
décaissement (jalons, règles, méthodes), par un contrôle de la bibliothèque, ou — honnêtement — par
rien. Les tests empêchent un branchement fantôme : un contrôle cité doit exister, un champ cité doit
exister, une règle non branchée doit dire pourquoi.
"""

import datetime
import json
from pathlib import Path

import pytest

from niveau2_profils.services.catalogue import lire_profil_livre
from niveau2_profils.services.gabarit import ajouter_mois, gabarit_decaissement
from niveau3_config.models import ProfilDecaissement
from niveau3_config.services.decaissement import ProfilViole, verifier_delai
from tests.test_api_marches_bd import api, appeler  # noqa: F401
from tests.test_api_profils_decaissement_bd import _chemin, _corps, _poser, monde  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

RACINE = Path(__file__).resolve().parents[1]
BIBLIOTHEQUE = {
    c["code"]
    for c in json.loads(
        (RACINE / "niveau4_reporting/controles/catalogue/bibliotheque.json").read_text(
            encoding="utf-8"
        )
    )["controles"]
}
BRANCHES = {
    "BAD-CTRL-ELIGIBILITE-DATES",
    "BAD-CTRL-ALLOCATIONS-CATEGORIES",
    "BAD-CTRL-DELAI-DEMANDES",
    "BAD-CTRL-PIECES-REMBOURSEMENT",
    "BAD-CTRL-MONODEVISE",
    "BAD-CTRL-NUMEROTATION",
}


def _controles():
    return {e["code"]: e for e in lire_profil_livre("bad")["elements"] if e["kind"] == "check"}


# --- le catalogue (logique pure) -----------------------------------------------------------------


def test_chaque_controle_du_profil_dit_comment_il_est_applique():
    controles = _controles()
    assert len(controles) == 12
    for code, e in controles.items():
        branchement = e["contenu"].get("branchement")
        assert branchement and all(
            b["type"]
            in {
                "controle_bibliotheque",
                "profil_decaissement",
                "service_decaissement",
                "non_branche",
            }
            for b in branchement
        ), code


def test_seuls_six_controles_sont_branches_et_les_six_autres_le_disent():
    controles = _controles()
    branches = {
        c
        for c, e in controles.items()
        if any(b["type"] != "non_branche" for b in e["contenu"]["branchement"])
    }
    assert branches == BRANCHES
    for code in set(controles) - BRANCHES:
        (b,) = controles[code]["contenu"]["branchement"]
        assert b["type"] == "non_branche" and set(b["raison"]) == {"fr", "en"}, code
        assert len(b["raison"]["fr"]) > 30 and len(b["raison"]["en"]) > 30, code


def test_un_controle_de_bibliotheque_cite_existe_vraiment():
    cites = {
        code
        for e in _controles().values()
        for b in e["contenu"]["branchement"]
        if b["type"] == "controle_bibliotheque"
        for code in b["codes"]
    }
    assert cites == {
        "ELIG-PERIODE-ACCORD",
        "BUD-ALLOCATION",
        "BUD-CATEGORIE",
        "COD-CATEGORIE",
        "PIE-ETAT-CERTIFIE",
    }
    assert cites <= BIBLIOTHEQUE, cites - BIBLIOTHEQUE


def test_un_champ_de_profil_de_decaissement_cite_existe_vraiment():
    champs = {f.name for f in ProfilDecaissement._meta.get_fields()}
    cites = {
        b["champ"]
        for e in _controles().values()
        for b in e["contenu"]["branchement"]
        if b["type"] == "profil_decaissement"
    }
    assert cites == {"eligibility_date", "regles", "disbursement_deadline", "methodes"}
    assert cites <= champs, cites - champs


def test_un_service_de_decaissement_cite_existe_vraiment():
    from niveau1_socle.decaissements import services

    cites = {
        b["fonction"]
        for e in _controles().values()
        for b in e["contenu"]["branchement"]
        if b["type"] == "service_decaissement"
    }
    assert cites == {"_contrats_des_lignes", "_numero_de_demande"}
    assert all(callable(getattr(services, nom, None)) for nom in cites), cites


# --- le calcul des mois ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "depart, mois, attendu",
    [
        ("2030-12-31", 4, "2031-04-30"),  # le dernier jour du mois d'arrivée
        ("2026-10-31", 4, "2027-02-28"),
        ("2027-10-31", 4, "2028-02-29"),  # année bissextile
        ("2026-09-15", 4, "2027-01-15"),  # changement d'année
        ("2026-01-31", 1, "2026-02-28"),
        ("2026-06-10", 0, "2026-06-10"),
        ("2026-11-30", 13, "2027-12-30"),
    ],
)
def test_ajouter_des_mois_garde_le_jour_ou_le_dernier_jour_du_mois(depart, mois, attendu):
    assert ajouter_mois(datetime.date.fromisoformat(depart), mois).isoformat() == attendu


# --- le gabarit -----------------------------------------------------------------------------------


def test_le_gabarit_bad_derive_le_delai_de_decaissement_de_la_cloture():
    g = gabarit_decaissement(
        "bad",
        date_cloture=datetime.date(2030, 12, 31),
        date_eligibilite=datetime.date(2026, 3, 15),
    )
    assert g["profil"] == "BAD" and g["version"] == 2
    assert g["jalons"] == {
        "closing_date": datetime.date(2030, 12, 31),
        "eligibility_date": datetime.date(2026, 3, 15),
        "disbursement_deadline": datetime.date(2031, 4, 30),  # clôture + 4 mois (DH p.26)
    }
    assert g["methodes_disponibles"] == [
        "advance",
        "direct_payment",
        "reimbursement",
        "special_commitment",
    ]
    assert g["controles_bibliotheque"] == [
        "ELIG-PERIODE-ACCORD",
        "BUD-ALLOCATION",
        "BUD-CATEGORIE",
        "COD-CATEGORIE",
        "PIE-ETAT-CERTIFIE",
    ]
    assert {n["code"] for n in g["non_branches"]} == set(_controles()) - BRANCHES
    assert g["a_decider"] == ["regime", "regles", "comptes", "methodes_pieces"]


def test_sans_date_d_eligibilite_aucune_n_est_inventee():
    g = gabarit_decaissement("bad", date_cloture=datetime.date(2030, 12, 31))
    assert "eligibility_date" not in g["jalons"]


def test_les_raisons_se_rendent_dans_la_langue_demandee_et_a_defaut_en_francais():
    cloture = datetime.date(2030, 12, 31)
    fr = gabarit_decaissement("bad", date_cloture=cloture)["non_branches"][0]
    en = gabarit_decaissement("bad", date_cloture=cloture, libelle_langue="en")["non_branches"][0]
    ar = gabarit_decaissement("bad", date_cloture=cloture, libelle_langue="ar")["non_branches"][0]
    assert fr["raison"] != en["raison"] and ar == fr
    assert "not" in en["raison"].lower() or "no " in en["raison"].lower()


def test_le_gabarit_n_est_pas_propre_au_bad_un_squelette_ne_derive_rien():
    g = gabarit_decaissement("fida", date_cloture=datetime.date(2030, 12, 31))
    assert g["jalons"] == {"closing_date": datetime.date(2030, 12, 31)}
    assert g["controles_bibliotheque"] == [] and g["non_branches"] == []


# --- l'API et le parcours de bout en bout -------------------------------------------------------

pytestmark_bd = pytest.mark.django_db(transaction=True)


def _gabarit_url(projet, nom="bad", requete="date_cloture=2030-12-31&date_eligibilite=2026-03-15"):
    return f"/projets/{projet.id}/profils-bailleurs/{nom}/gabarit-decaissement/?{requete}"


@pytestmark_bd
def test_l_api_rend_le_gabarit_en_chaines_dans_la_langue_de_la_requete(monde):
    _, projet, profils, _, _, _ = monde
    r = appeler(profils["amina"], "get", _gabarit_url(projet))
    assert r.status_code == 200, r.content
    g = r.json()
    assert g["jalons"] == {
        "closing_date": "2030-12-31",
        "eligibility_date": "2026-03-15",
        "disbursement_deadline": "2031-04-30",
    }
    profils["amina"].langue = "en"  # la langue du compte prime sur l'en-tête de la requête
    profils["amina"].save()
    en = appeler(profils["amina"], "get", _gabarit_url(projet)).json()
    assert en["non_branches"][0]["raison"] != g["non_branches"][0]["raison"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "requete, statut",
    [
        ("", 422),
        ("date_cloture=demain", 422),
        ("date_cloture=2030-12-31&date_eligibilite=hier", 422),
    ],
)
def test_une_date_absente_ou_illisible_est_refusee(monde, requete, statut):
    _, projet, profils, _, _, _ = monde
    r = appeler(profils["amina"], "get", _gabarit_url(projet, requete=requete))
    assert r.status_code == statut and set(r.json()) == {"code", "message"}


@pytestmark_bd
def test_un_nom_inconnu_ou_un_chemin_est_introuvable_et_sans_habilitation_refuse(monde):
    from django.contrib.auth import get_user_model

    organisation, projet, profils, _, _, _ = monde
    for nom in ("inconnu", "..%2F..%2Fsecret", "BAD"):
        assert appeler(profils["amina"], "get", _gabarit_url(projet, nom)).status_code == 404, nom
    inconnu = get_user_model().objects.create_user("zoe", password="x", org_id=organisation.id)
    _poser(organisation)
    assert appeler(inconnu, "get", _gabarit_url(projet)).status_code == 403


@pytestmark_bd
def test_du_gabarit_au_profil_actif_le_delai_de_la_bad_est_applique(monde):
    """Le jalon dérivé du profil BAD alimente un vrai profil de décaissement, qui refuse une demande
    déposée après « clôture + 4 mois » et l'accepte le dernier jour."""
    organisation, projet, profils, accord, _, _ = monde
    g = appeler(profils["amina"], "get", _gabarit_url(projet)).json()
    j = g["jalons"]
    r = appeler(
        profils["dora"],
        "post",
        _chemin(projet, accord),
        _corps(
            eligibility_date=j["eligibility_date"],
            closing_date=j["closing_date"],
            disbursement_deadline=j["disbursement_deadline"],
        ),
    )
    assert r.status_code == 201, r.content
    profil_id = r.json()["id"]
    assert (
        appeler(
            profils["bruno"], "post", _chemin(projet, accord, f"{profil_id}/valider/"), {}
        ).status_code
        == 200
    )
    assert (
        appeler(
            profils["dora"], "post", _chemin(projet, accord, f"{profil_id}/activer/"), {}
        ).status_code
        == 200
    )
    _poser(organisation)
    profil = ProfilDecaissement.objects.get(id=profil_id)
    verifier_delai(profil, datetime.date(2031, 4, 30))  # le dernier jour : accepté
    with pytest.raises(ProfilViole):
        verifier_delai(profil, datetime.date(2031, 5, 1))  # le lendemain : refusé


# --- l'exception d'audit : la règle suggérée par le gabarit (L11-D9) ----------------------------


def test_le_gabarit_bad_suggere_la_fin_propre_des_frais_d_audit_six_mois_apres_la_cloture():
    g = gabarit_decaissement("bad", date_cloture=datetime.date(2030, 12, 31))
    assert g["regles_suggerees"] == [
        {
            "role": "frais_d_audit",
            "eligibility_to": datetime.date(2031, 6, 30),  # clôture + 6 mois (DH p.23)
            "fin_propre_a_la_categorie": True,
        }
    ]
    # ce n'est qu'une SUGGESTION : le jalon de décaissement n'est pas touché par la règle d'audit
    assert g["jalons"]["disbursement_deadline"] == datetime.date(2031, 4, 30)
    assert "regles" not in g["jalons"]


def test_un_profil_sans_exception_ne_suggere_aucune_regle():
    assert (
        gabarit_decaissement("fida", date_cloture=datetime.date(2030, 12, 31))["regles_suggerees"]
        == []
    )
