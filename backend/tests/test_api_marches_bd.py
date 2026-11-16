# ruff: noqa: F811, E501
"""L'API HTTP du plan de passation, des avis, des contrats et des décomptes. Voir L9.

Session authentifiée, JSON, montants en chaînes, refus métier au format `{code, message}`, isolation
par organisation, habilitations côté serveur. Le scénario déroule le parcours complet par HTTP.
"""

import base64
import json

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client

from niveau1_socle.budget.engagements import creer_engagement
from niveau1_socle.financements.services import creer_compte_bancaire
from niveau1_socle.referentiels.models import Tiers
from tests.outils import _compte
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_organisations_bd import _creer_organisation, _creer_projet

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
RACINE = "/api/v1"


def _connecte(utilisateur) -> Client:
    client = Client()
    client.force_login(utilisateur)
    return client


def _poser(organisation):
    """Pose l'organisation sur la session de test (les appels HTTP la remettent à zéro)."""
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


def appeler(utilisateur, methode, chemin, donnees=None, **entetes):
    """Un appel JSON ; la réponse porte `.json()` (les décimaux restent des chaînes)."""
    client = _connecte(utilisateur)
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")  # la requête pose sa propre organisation
    fonction = getattr(client, methode)
    if methode in ("get", "delete"):
        return fonction(f"{RACINE}{chemin}", **entetes)
    return fonction(
        f"{RACINE}{chemin}",
        data=json.dumps(donnees or {}),
        content_type="application/json",
        **entetes,
    )


@pytest.fixture
def api(cadre):
    """dora paramètre, amina saisit, bruno valide, claire comptabilise : un projet, un tiers."""
    organisation, projet, profils, _ = cadre
    from niveau1_socle.habilitations.models import Habilitation, Role

    for nom, operations in {
        "amina": ["consulter", "saisir"],
        "bruno": ["consulter", "valider"],
        "claire": ["consulter", "comptabiliser"],
        "pia": ["consulter", "publier"],
    }.items():
        utilisateur = profils.get(nom) or Utilisateur.objects.create_user(
            nom, password="x", org_id=organisation.id
        )
        role = Role.objects.create(
            org_id=organisation.id, code=nom.upper() + "X", label={"fr": nom}, operations=operations
        )
        Habilitation.objects.create(
            org_id=organisation.id, user_id=utilisateur.id, project_id=projet.id, role=role
        )
        profils[nom] = utilisateur
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])
    tiers = Tiers.objects.create(
        org_id=organisation.id, code="F1", nature="fournisseur", nom="Fournisseur 1"
    )
    return organisation, projet, profils, tiers


def _plan_et_ligne(api, montant="900000", methode="AOI"):
    organisation, projet, profils, _ = api
    dora, amina = profils["dora"], profils["amina"]
    for code, bas, haut, avis in (("AON", "50000", "500000", False), ("AOI", "500000", None, True)):
        r = appeler(
            dora,
            "post",
            f"/projets/{projet.id}/methodes/",
            {
                "code": code,
                "label": {"fr": code, "en": code},
                "devise": "USD",
                "seuil_min": bas,
                "seuil_max": haut,
                "exige_non_objection": avis,
                "valid_from": "2026-01-01",
            },
        )
        assert r.status_code == 201, r.content
    plan = appeler(
        amina,
        "post",
        f"/projets/{projet.id}/plans/",
        {
            "code": "PPM",
            "nom": "Plan 2026",
            "date_debut": "2026-01-01",
            "date_fin": "2026-12-31",
        },
    )
    assert plan.status_code == 201, plan.content
    ligne = appeler(
        amina,
        "post",
        f"/plans/{plan.json()['id']}/lignes/",
        {
            "reference": "M-900",
            "libelle": "Véhicules",
            "montant_prevu": montant,
            "devise": "USD",
            "methode_code": methode,
            "date_lancement_prevue": "2026-03-01",
            "date_attribution_prevue": "2026-05-01",
            "date_signature_prevue": "2026-06-01",
        },
    )
    assert ligne.status_code == 201, ligne.content
    return plan.json(), ligne.json()


def test_sans_session_l_api_est_fermee(api):
    assert Client().get(f"{RACINE}/projets/{api[1].id}/methodes/").status_code == 403


def test_le_parcours_complet_par_http(api):
    organisation, projet, profils, tiers = api
    amina, bruno, dora = profils["amina"], profils["bruno"], profils["dora"]
    plan, ligne = _plan_et_ligne(api)
    assert ligne["non_objection_requise"] is True and ligne["montant_prevu"] == "900000.0000"
    for statut, jour in (("lance", "2026-03-02"), ("attribue", "2026-05-02")):
        r = appeler(
            amina, "post", f"/lignes/{ligne['id']}/avancer/", {"statut": statut, "date_effet": jour}
        )
        assert r.status_code == 200 and r.json()["statut"] == statut

    # Sans avis, le contrat est refusé ; avec l'avis obtenu, il se conclut.
    contrat_corps = {
        "reference": "C-AOI",
        "tiers": str(tiers.id),
        "objet": "Véhicules",
        "montant": "900000",
        "date_signature": "2026-06-01",
        "date_debut": "2026-06-15",
        "date_fin": "2026-12-15",
    }
    refus = appeler(amina, "post", f"/lignes/{ligne['id']}/contrat/", contrat_corps)
    assert (
        refus.status_code == 422
        and refus.json()["code"] == "REGLE_INVALIDE"
        and "M-900" in refus.json()["message"]
    )
    avis = appeler(
        amina,
        "post",
        f"/lignes/{ligne['id']}/avis/",
        {"objet": "dossier", "date_demande": "2026-03-01"},
    ).json()
    piece = appeler(
        amina,
        "post",
        f"/avis/{avis['id']}/pieces/",
        {
            "nature": "demande",
            "nom": "lettre.pdf",
            "contenu_base64": base64.b64encode(b"%PDF lettre").decode(),
        },
    )
    assert piece.status_code == 201 and piece.json()["taille"] == 11
    attente = appeler(amina, "get", f"/projets/{projet.id}/avis-en-attente/?jour=2026-03-11").json()
    assert [(a["id"], a["jours_d_attente"]) for a in attente] == [(avis["id"], 10)]
    decide = appeler(
        amina,
        "post",
        f"/avis/{avis['id']}/decision/",
        {"statut": "obtenu", "date_decision": "2026-03-20", "reference_bailleur": "BM-117"},
    )
    assert decide.status_code == 200 and decide.json()["statut"] == "obtenu"
    contrat = appeler(amina, "post", f"/lignes/{ligne['id']}/contrat/", contrat_corps)
    assert contrat.status_code == 201, contrat.content
    contrat = contrat.json()
    assert (
        contrat["montant_courant"] == "900000.0000" and contrat["date_fin_courante"] == "2026-12-15"
    )

    # Un avenant s'appuie sur un avis « avenant » obtenu ; une garantie donne une alerte d'échéance.
    avis_av = appeler(
        amina,
        "post",
        f"/lignes/{ligne['id']}/avis/",
        {"objet": "avenant", "date_demande": "2026-07-01"},
    ).json()
    appeler(
        amina,
        "post",
        f"/avis/{avis_av['id']}/decision/",
        {"statut": "obtenu", "date_decision": "2026-07-06"},
    )
    av = appeler(
        amina,
        "post",
        f"/contrats/{contrat['id']}/avenants/",
        {
            "date_effet": "2026-08-01",
            "montant": "950000",
            "date_fin": "2027-01-31",
            "motif": "Extension",
            "avis": avis_av["id"],
        },
    )
    assert av.status_code == 201 and av.json()["montant_courant"] == "950000.0000"
    g = appeler(
        amina,
        "post",
        f"/contrats/{contrat['id']}/garanties/",
        {
            "type_garantie": "bonne_execution",
            "emetteur": "Banque X",
            "reference": "GBE-1",
            "montant": "90000",
            "date_emission": "2026-06-01",
            "date_echeance": "2026-09-15",
        },
    )
    assert g.status_code == 201
    alertes = appeler(
        amina, "get", f"/projets/{projet.id}/alertes/?jour=2026-09-01&horizon_jours=30"
    ).json()
    assert [(a["nature"], a["reference"], a["etat"]) for a in alertes] == [
        ("garantie", "GBE-1", "proche")
    ]
    cloture = appeler(
        amina,
        "post",
        f"/garanties/{g.json()['id']}/cloture/",
        {"statut": "liberee", "date_cloture": "2026-09-20"},
    )
    assert cloture.status_code == 200 and cloture.json()["statut"] == "liberee"

    # Décompte soumis par amina, certifié par bruno (apure l'engagement du marché), payé.
    from niveau1_socle.marches.models import LignePassation

    _poser(organisation)
    engagement = creer_engagement(
        utilisateur=amina,
        project_id=projet.id,
        reference="ENG-AOI",
        annee=2026,
        montant="5000",
        ligne_passation=LignePassation.objects.get(pk=ligne["id"]),
    )
    d = appeler(
        amina,
        "post",
        f"/contrats/{contrat['id']}/decomptes/",
        {
            "date_decompte": "2026-07-01",
            "montant_brut": "60000",
            "retenue": "3000",
            "avancement_physique": "40",
        },
    )
    assert d.status_code == 201 and d.json()["numero"] == 1 and d.json()["statut"] == "soumis"
    meme = appeler(
        amina,
        "post",
        f"/decomptes/{d.json()['id']}/certifier/",
        {
            "engagement": str(engagement.id),
            "date_certification": "2026-07-10",
            "montant_apure": "5000",
        },
    )
    assert meme.status_code == 403  # amina n'a pas « valider »
    cert = appeler(
        bruno,
        "post",
        f"/decomptes/{d.json()['id']}/certifier/",
        {
            "engagement": str(engagement.id),
            "date_certification": "2026-07-10",
            "montant_apure": "5000",
        },
    )
    assert cert.status_code == 200 and cert.json()["statut"] == "certifie"
    _poser(organisation)
    compte = creer_compte_bancaire(
        utilisateur=dora,
        project_id=projet.id,
        code="CB-USD",
        type="operationnel",
        devise="USD",
        banque="B",
        numero="USD-1",
    )
    _compte(organisation.id, "401"), _compte(organisation.id, "5211")
    from niveau1_socle.comptabilite.models import Journal

    Journal.objects.get_or_create(
        org_id=organisation.id, code="BQ", defaults={"label": {"fr": "B", "en": "B"}}
    )
    paie = appeler(
        amina,
        "post",
        f"/decomptes/{d.json()['id']}/paiements/",
        {
            "reference": "P1",
            "date_paiement": "2026-07-15",
            "montant": "57000",
            "compte_bancaire": str(compte.id),
            "compte_fournisseur": "401",
            "compte_banque": "5211",
            "journal": "BQ",
            "taux": "177.5",
        },
    )
    assert paie.status_code == 201 and paie.json()["ecriture_id"]
    situation = appeler(amina, "get", f"/contrats/{contrat['id']}/situation/").json()
    assert (situation["certifie"], situation["paye"], situation["reste_a_payer"]) == (
        "60000.0000",
        "57000.0000",
        "0.0000",
    )


def test_un_montant_en_nombre_decimal_json_est_refuse_et_le_champ_est_nomme(api):
    organisation, projet, profils, _ = api
    plan, _ = _plan_et_ligne(api, montant="120000", methode="AON")
    r = appeler(
        profils["amina"],
        "post",
        f"/plans/{plan['id']}/lignes/",
        {
            "reference": "M-2",
            "libelle": "x",
            "montant_prevu": 120000.5,
            "devise": "USD",
            "methode_code": "AON",
            "date_lancement_prevue": "2026-03-01",
            "date_attribution_prevue": "2026-05-01",
            "date_signature_prevue": "2026-06-01",
        },
    )
    assert (
        r.status_code == 422
        and r.json()["code"] == "REGLE_INVALIDE"
        and "montant_prevu" in r.json()["message"]
    )


def test_les_champs_sont_types_et_les_corps_non_objet_refuses(api):
    organisation, projet, profils, _ = api
    amina = profils["amina"]
    plan, ligne = _plan_et_ligne(api, montant="120000", methode="AON")
    for corps, champ in (
        ({"statut": "lance"}, "date_effet"),
        ({"statut": "lance", "date_effet": "hier"}, "date_effet"),
        ({"date_effet": "2026-03-02"}, "statut"),
        ({"statut": 5, "date_effet": "2026-03-02"}, "statut"),
    ):
        r = appeler(amina, "post", f"/lignes/{ligne['id']}/avancer/", corps)
        assert r.status_code == 422 and champ in r.json()["message"], (corps, r.content)
    liste = _connecte(amina).post(
        f"{RACINE}/lignes/{ligne['id']}/avancer/", data="[1]", content_type="application/json"
    )
    assert liste.status_code == 400


def test_un_refus_de_transition_est_un_409_dans_la_langue_de_la_requete(api):
    amina = api[2]["amina"]
    _, ligne = _plan_et_ligne(api, montant="120000", methode="AON")
    r = appeler(
        amina,
        "post",
        f"/lignes/{ligne['id']}/avancer/",
        {"statut": "attribue", "date_effet": "2026-04-01"},
    )
    assert (
        r.status_code == 409
        and r.json()["code"] == "TRANSITION_INTERDITE"
        and "saute" in r.json()["message"]
    )
    Utilisateur.objects.filter(pk=amina.pk).update(langue="en")  # la langue de l'utilisateur prime
    amina.refresh_from_db()
    en = appeler(
        amina,
        "post",
        f"/lignes/{ligne['id']}/avancer/",
        {"statut": "attribue", "date_effet": "2026-04-01"},
    )
    assert en.status_code == 409 and "skipped" in en.json()["message"]


def test_l_habilitation_est_verifiee_au_serveur(api):
    organisation, projet, profils, _ = api
    plan, ligne = _plan_et_ligne(api, montant="120000", methode="AON")
    assert (
        appeler(profils["bruno"], "post", f"/plans/{plan['id']}/lignes/", {}).status_code == 403
    )  # valide, ne saisit pas
    assert (
        appeler(profils["amina"], "post", f"/projets/{projet.id}/methodes/", {}).status_code == 403
    )  # ne paramètre pas
    assert (
        appeler(profils["claire"], "get", f"/lignes/{ligne['id']}/").status_code == 200
    )  # consulter suffit à lire
    sans_droit = Utilisateur.objects.create_user("zoe", password="x", org_id=organisation.id)
    assert appeler(sans_droit, "get", f"/lignes/{ligne['id']}/").status_code == 403


def test_un_objet_d_une_autre_organisation_est_introuvable(api):
    organisation, projet, profils, _ = api
    plan, ligne = _plan_et_ligne(api, montant="120000", methode="AON")
    autre = _creer_organisation("ORG-B")
    intrus = Utilisateur.objects.create_user("intrus", password="x", org_id=autre.id)
    for chemin in (
        f"/lignes/{ligne['id']}/",
        f"/plans/{plan['id']}/",
        f"/projets/{projet.id}/methodes/",
    ):
        assert appeler(intrus, "get", chemin).status_code in (403, 404)  # jamais 200
    assert (
        appeler(
            intrus,
            "post",
            f"/lignes/{ligne['id']}/avancer/",
            {"statut": "lance", "date_effet": "2026-03-02"},
        ).status_code
        == 404
    )
    assert _creer_projet(autre, "PB").id != projet.id


def test_aucune_reponse_ne_contient_de_nombre_decimal_json(api):
    amina = api[2]["amina"]
    plan, ligne = _plan_et_ligne(api)

    def refuse(valeur):
        raise AssertionError(f"float JSON {valeur} dans une réponse")

    for chemin in (
        f"/plans/{plan['id']}/",
        f"/plans/{plan['id']}/lignes/",
        f"/lignes/{ligne['id']}/",
        f"/projets/{api[1].id}/methodes/",
    ):
        reponse = appeler(amina, "get", chemin)
        assert reponse.status_code == 200
        json.loads(reponse.content, parse_float=refuse)
    synthese = appeler(amina, "get", f"/plans/{plan['id']}/").json()
    assert synthese["par_statut"] == [
        {"statut": "prevu", "devise": "USD", "montant": "900000.0000"}
    ]
    assert synthese["nombre"] == 1 and synthese["non_objection_requise"] == 1


def test_la_certification_exige_le_droit_avant_la_lecture_du_corps(api):
    organisation, projet, profils, tiers = api
    _, ligne = _plan_et_ligne(api, montant="120000", methode="AON")
    for statut, jour in (("lance", "2026-03-02"), ("attribue", "2026-05-02")):
        appeler(
            profils["amina"],
            "post",
            f"/lignes/{ligne['id']}/avancer/",
            {"statut": statut, "date_effet": jour},
        )
    contrat = appeler(
        profils["amina"],
        "post",
        f"/lignes/{ligne['id']}/contrat/",
        {
            "reference": "C-1",
            "tiers": str(tiers.id),
            "objet": "x",
            "montant": "118000",
            "date_signature": "2026-06-01",
            "date_debut": "2026-06-15",
            "date_fin": "2026-12-15",
        },
    ).json()
    d = appeler(
        profils["amina"],
        "post",
        f"/contrats/{contrat['id']}/decomptes/",
        {"date_decompte": "2026-07-01", "montant_brut": "1000", "avancement_physique": "10"},
    ).json()
    assert (
        appeler(profils["amina"], "post", f"/decomptes/{d['id']}/certifier/", {}).status_code == 403
    )
    assert (
        appeler(profils["amina"], "post", f"/decomptes/{d['id']}/rejeter/", {}).status_code == 403
    )
    assert (
        appeler(profils["bruno"], "post", f"/decomptes/{d['id']}/certifier/", {}).status_code == 422
    )
