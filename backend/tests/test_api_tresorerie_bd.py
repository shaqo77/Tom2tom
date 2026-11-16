# ruff: noqa: F811, E501
"""L'API HTTP de la trésorerie : disponibilités, prévisions, relevés, reconstitution, rapport. L9."""

import datetime
import json

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from niveau1_socle.habilitations.models import Habilitation, Role
from niveau1_socle.tresorerie.services import enregistrer_solde_releve
from tests.test_api_marches_bd import RACINE, _connecte, _poser, appeler
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_releves_bd import MT940
from tests.test_tresorerie_bd import DEBUT, FIN, _importer, _scenario, banque  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
J = datetime.date
Utilisateur = get_user_model()


@pytest.fixture
def tres(banque):
    """Le scénario de trésorerie, clôture enregistrée ; pia publie."""
    organisation, projet, profils, designe, demande = banque
    _scenario(banque)
    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=designe, date_solde=FIN, solde="1200"
    )
    pia = Utilisateur.objects.create_user("pia", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id, code="PIAX", label={"fr": "p"}, operations=["consulter", "publier"]
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=pia.id, project_id=projet.id, role=role
    )
    profils["pia"] = pia
    # amina consulte aussi (rôle « saisir » de decor) ; bruno valide et consulte.
    _poser(organisation)
    return banque


def test_les_disponibilites_se_lisent_par_compte_et_par_devise(tres):
    organisation, projet, profils, designe, _ = tres
    r = appeler(profils["amina"], "get", f"/projets/{projet.id}/disponibilites/?jour=2026-03-31")
    assert r.status_code == 200
    d = r.json()
    compte = d["comptes"][0]
    assert (
        compte["code"] == "CD-DJF"
        and compte["numero_masque"].endswith("8877")
        and "DJ21" not in r.content.decode()
    )
    assert d["totaux_par_devise"]["DJF"]["releve"].startswith("1200")
    assert (
        appeler(profils["amina"], "get", f"/projets/{projet.id}/disponibilites/").status_code == 422
    )  # jour obligatoire


def test_les_previsions_se_posent_se_revisent_et_se_lisent(tres):
    organisation, projet, profils, _, _ = tres
    amina = profils["amina"]
    base = {
        "devise": "DJF",
        "annee": 2026,
        "mois": 4,
        "encaissements": "1000",
        "decaissements": "400",
    }
    assert appeler(amina, "post", f"/projets/{projet.id}/previsions/", base).status_code == 201
    sans_motif = appeler(
        amina, "post", f"/projets/{projet.id}/previsions/", base | {"encaissements": "1200"}
    )
    assert sans_motif.status_code == 422 and "motif" in sans_motif.json()["message"]
    rev = appeler(
        amina,
        "post",
        f"/projets/{projet.id}/previsions/",
        base | {"encaissements": "1200", "motif": "Nouvel accord"},
    )
    assert rev.status_code == 201 and rev.json()["revision"] == 2
    lues = appeler(
        amina, "get", f"/projets/{projet.id}/previsions/?annee=2026&mois=4&nombre_mois=1"
    ).json()
    assert [(p["mois"], p["encaissements"], p["net"]) for p in lues] == [
        (4, "1200.0000", "800.0000")
    ]
    flottant = appeler(
        amina, "post", f"/projets/{projet.id}/previsions/", base | {"encaissements": 1200.5}
    )
    assert flottant.status_code == 422 and "encaissements" in flottant.json()["message"]
    assert (
        appeler(profils["bruno"], "post", f"/projets/{projet.id}/previsions/", base).status_code
        == 403
    )


def test_un_releve_mt940_s_importe_par_http_et_un_releve_incoherent_est_refuse(tres):
    organisation, projet, profils, designe, _ = tres
    # Le scénario a déjà importé des mouvements ; on repart d'un compte neuf pour l'import du relevé.
    from niveau1_socle.financements.services import creer_compte_bancaire

    neuf = creer_compte_bancaire(
        utilisateur=profils["dora"], project_id=projet.id, code="CD-NEUF", type="designe", devise="DJF",
        banque="BCD", numero="DJ21 0001 0000 0099 8877X",
    )  # fmt: skip
    fichier = MT940.replace("DJ21000100000099 8877", "DJ21 0001 0000 0099 8877X")
    _poser(organisation)
    ok = appeler(
        profils["claire"],
        "post",
        f"/comptes/{neuf.id}/releves/",
        {"contenu": fichier, "format": "mt940"},
    )
    assert ok.status_code == 201 and ok.json() == {
        "mouvements_importes": 3,
        "mouvements_ignores": 0,
        "soldes_poses": 2,
    }
    rejoue = appeler(
        profils["claire"], "post", f"/comptes/{neuf.id}/releves/", {"contenu": fichier}
    )
    assert rejoue.json()["mouvements_ignores"] == 3
    faux = appeler(
        profils["claire"],
        "post",
        f"/comptes/{neuf.id}/releves/",
        {"contenu": fichier.replace("C260228DJF1200,00", "C260228DJF9,00")},
    )
    assert faux.status_code == 422 and "incohérent" in faux.json()["message"]
    assert (
        appeler(
            profils["amina"], "post", f"/comptes/{neuf.id}/releves/", {"contenu": fichier}
        ).status_code
        == 403
    )
    assert "0099" not in ok.content.decode()


def test_la_reconstitution_se_lit_et_se_justifie_par_http(tres):
    organisation, projet, profils, designe, _ = tres
    url = f"/comptes/{designe.id}/reconstitution/?debut=2026-02-01&fin=2026-03-31"
    r = appeler(profils["amina"], "get", url)
    assert r.status_code == 200
    e = r.json()
    assert e["complet"] and e["justifie"] and e["cloture_calculee"] == e["cloture_releve"]
    assert e["avances_recues"][0]["montant"].startswith("300") and e["numero_masque"].endswith(
        "8877"
    )
    assert "DJ21 0001" not in r.content.decode()
    json.loads(
        r.content, parse_float=lambda v: (_ for _ in ()).throw(AssertionError(v))
    )  # aucun float
    _poser(organisation)
    _importer(profils, designe, ("EXTRA", J(2026, 3, 20), "5"))  # crée un écart de −5, à justifier
    assert appeler(profils["amina"], "get", url).json()["justifie"] is False
    corps = {
        "date_debut": "2026-02-01",
        "date_fin": "2026-03-31",
        "montant": "-5",
        "explication": "Virement tardif",
    }
    assert (
        appeler(
            profils["amina"],
            "post",
            f"/comptes/{designe.id}/justifications/",
            corps | {"cible": "releve"},
        ).status_code
        == 403
    )
    for cible in ("releve", "comptable"):
        assert (
            appeler(
                profils["bruno"],
                "post",
                f"/comptes/{designe.id}/justifications/",
                corps | {"cible": cible},
            ).status_code
            == 201
        )
    assert appeler(profils["amina"], "get", url).json()["justifie"] is True


def test_le_rapport_du_compte_designe_se_publie_par_http_et_se_bloque_sur_un_ecart_non_justifie(
    tres,
):
    organisation, projet, profils, designe, _ = tres
    corps = {"date_debut": "2026-02-01", "date_fin": "2026-03-31"}
    ok = appeler(profils["pia"], "post", f"/comptes/{designe.id}/rapport/", corps)
    assert ok.status_code == 201, ok.content
    assert (
        ok.json()["modele"] == "RCD"
        and len(ok.json()["scelle"]) == 64
        and ok.json()["valeurs"]["R150/PER"] == "1200"
    )
    assert (
        appeler(profils["amina"], "post", f"/comptes/{designe.id}/rapport/", corps).status_code
        == 403
    )
    _poser(organisation)
    _importer(profils, designe, ("EXTRA", J(2026, 3, 20), "5"))
    bloque = appeler(profils["pia"], "post", f"/comptes/{designe.id}/rapport/", corps)
    assert bloque.status_code == 422 and "R180" in bloque.json()["message"]


def test_un_encaissement_s_apparie_a_une_demande_par_http_une_seule_fois(tres):
    from niveau1_socle.tresorerie.models import AppariementDemande

    organisation, projet, profils, designe, demande = tres
    existant = AppariementDemande.objects.get()  # le scénario a apparié l'avance AV-1
    deux = appeler(
        profils["amina"],
        "post",
        f"/mouvements/{existant.mouvement_id}/appariement/",
        {"demande": str(demande.id)},
    )
    assert deux.status_code == 422 and "AV-1" in deux.json()["message"]
    sans_motif = appeler(
        profils["amina"], "post", f"/appariements/{existant.id}/annulation/", {"motif": ""}
    )
    assert sans_motif.status_code == 422
    annule = appeler(
        profils["amina"],
        "post",
        f"/appariements/{existant.id}/annulation/",
        {"motif": "Mauvaise demande"},
    )
    assert annule.status_code == 200 and annule.json()["annule_at"]
    de_nouveau = appeler(
        profils["amina"],
        "post",
        f"/mouvements/{existant.mouvement_id}/appariement/",
        {"demande": str(demande.id)},
    )
    assert de_nouveau.status_code == 201 and de_nouveau.json()["id"] != str(existant.id)


def test_un_solde_de_releve_se_pose_par_http_une_seule_fois_par_jour(tres):
    organisation, projet, profils, designe, _ = tres
    r = appeler(
        profils["amina"],
        "post",
        f"/comptes/{designe.id}/soldes/",
        {"date_solde": "2026-04-30", "solde": "5.50"},
    )
    assert r.status_code == 201 and r.json()["solde"] == "5.5000"
    deux = appeler(
        profils["amina"],
        "post",
        f"/comptes/{designe.id}/soldes/",
        {"date_solde": "2026-04-30", "solde": "6"},
    )
    assert deux.status_code == 422


def test_un_compte_d_une_autre_organisation_est_introuvable(tres):
    from tests.test_organisations_bd import _creer_organisation

    organisation, projet, profils, designe, _ = tres
    autre = _creer_organisation("ORG-Z")
    intrus = Utilisateur.objects.create_user("intrus", password="x", org_id=autre.id)
    r = appeler(
        intrus, "get", f"/comptes/{designe.id}/reconstitution/?debut=2026-02-01&fin=2026-03-31"
    )
    assert r.status_code == 404
    assert (
        _connecte(intrus)
        .get(f"{RACINE}/projets/{projet.id}/disponibilites/?jour=2026-03-31")
        .status_code
        == 403
    )
    assert connection.vendor == "postgresql"


def test_l_habilitation_est_verifiee_avant_la_lecture_du_corps(tres):
    """Sans le droit, la réponse est 403 même si le corps est invalide : rien n'est révélé."""
    organisation, projet, profils, designe, _ = tres
    amina = profils["amina"]  # consulte et saisit ; ne comptabilise, ne valide ni ne publie
    assert appeler(amina, "post", f"/comptes/{designe.id}/releves/", {}).status_code == 403
    assert appeler(amina, "post", f"/comptes/{designe.id}/justifications/", {}).status_code == 403
    assert appeler(amina, "post", f"/comptes/{designe.id}/rapport/", {}).status_code == 403
    assert (
        appeler(profils["bruno"], "post", f"/projets/{projet.id}/previsions/", {}).status_code
        == 403
    )
    # Avec le droit, le même corps vide est une erreur de validation nommant le champ.
    assert (
        appeler(profils["claire"], "post", f"/comptes/{designe.id}/releves/", {}).status_code == 422
    )


def test_un_booleen_n_est_pas_un_entier_et_par_axe_se_lit_dans_l_adresse(tres):
    organisation, projet, profils, _, _ = tres
    amina = profils["amina"]
    r = appeler(
        amina,
        "post",
        f"/projets/{projet.id}/previsions/",
        {"devise": "DJF", "annee": True, "mois": 4},
    )
    assert r.status_code == 422 and "annee" in r.json()["message"]
    from tests.outils import _valeur_axe

    _poser(organisation)
    axe = _valeur_axe(organisation.id, "COMP-A")
    base = {"devise": "DJF", "annee": 2026, "mois": 6}
    appeler(amina, "post", f"/projets/{projet.id}/previsions/", base | {"encaissements": "100"})
    appeler(
        amina,
        "post",
        f"/projets/{projet.id}/previsions/",
        base | {"encaissements": "60", "axe": str(axe.id)},
    )
    url = f"/projets/{projet.id}/previsions/?annee=2026&mois=6&nombre_mois=1"
    detail = appeler(amina, "get", url).json()
    assert [(p["axe"], p["encaissements"]) for p in detail] == [
        (None, "100.0000"),
        ("COMP-A", "60.0000"),
    ]
    agrege = appeler(amina, "get", url + "&par_axe=false").json()
    assert [(p["axe"], p["encaissements"]) for p in agrege] == [
        (None, "100.0000")
    ]  # « tous axes » l'emporte


def test_le_serialiseur_refuse_un_float():
    from core.api import serialiser

    with pytest.raises(TypeError):
        serialiser({"montant": 1.5})
    assert serialiser({"m": __import__("decimal").Decimal("1.50")}) == {"m": "1.50"}
