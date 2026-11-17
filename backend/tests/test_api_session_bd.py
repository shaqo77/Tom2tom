# ruff: noqa: F811
"""L'API de session du frontend : CSRF, connexion, « moi », langue, déconnexion. Voir F1.

Le frontend est une application monopage : il lui faut un point d'entrée pour se connecter, savoir
qui il est et ce qu'il peut faire, sans jamais deviner. Aucun mot de passe ni secret ne sort ;
l'identifiant inconnu et le mauvais mot de passe sont indiscernables.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client

from niveau1_socle.habilitations.models import Habilitation, Role
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
RACINE = "/api/v1/session"


def _poser(organisation):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


def _reset():
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")


def _client():
    """Un navigateur : cookies conservés, CSRF réellement contrôlé."""
    client = Client(enforce_csrf_checks=True)
    _reset()
    reponse = client.get(f"{RACINE}/csrf/")
    assert reponse.status_code == 200
    return client


def _envoyer(client, methode, chemin, donnees=None, *, jeton=True, **entetes):
    if jeton:
        entetes["HTTP_X_CSRFTOKEN"] = client.cookies["csrftoken"].value
    _reset()
    return getattr(client, methode)(
        f"{RACINE}{chemin}",
        data=json.dumps(donnees or {}),
        content_type="application/json",
        **entetes,
    )


def _connecter(client, nom="amina", mot_de_passe="x"):
    return _envoyer(
        client, "post", "/connexion/", {"identifiant": nom, "mot_de_passe": mot_de_passe}
    )


def test_le_jeton_csrf_se_demande_par_un_get_et_pose_son_cookie():
    client = Client(enforce_csrf_checks=True)
    _reset()
    reponse = client.get(f"{RACINE}/csrf/")
    assert reponse.status_code == 200
    assert client.cookies["csrftoken"].value
    assert set(reponse.json()) == {"csrf"}


def test_la_connexion_sans_jeton_csrf_est_refusee(decor):
    _reset()
    reponse = Client(enforce_csrf_checks=True).post(
        f"{RACINE}/connexion/",
        data=json.dumps({"identifiant": "amina", "mot_de_passe": "x"}),
        content_type="application/json",
    )
    assert reponse.status_code == 403


def test_une_connexion_reussie_rend_qui_je_suis_et_ce_que_je_peux_faire(decor):
    organisation, projet, profils = decor
    client = _client()
    reponse = _connecter(client)
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["identifiant"] == "amina" and corps["langue"] == "fr"
    assert corps["organisation"]["code"] == "ORG-A"
    assert set(corps["organisation"]) >= {
        "id",
        "code",
        "raison_sociale",
        "monnaie_tenue",
        "langues_actives",
    }
    (p,) = corps["projets"]
    assert (p["code"], p["operations"]) == ("P1", ["consulter", "saisir"])
    assert p["libelle"]["fr"] == "Projet P1"
    assert "password" not in json.dumps(corps) and "mot_de_passe" not in corps
    assert client.cookies["sessionid"]["httponly"]  # le cookie de session n'est pas lisible en JS


def test_apres_connexion_moi_rend_la_meme_chose_et_la_session_dure(decor):
    client = _client()
    connexion = _connecter(client).json()
    _reset()
    assert client.get(f"{RACINE}/moi/").json() == connexion


def test_un_mauvais_mot_de_passe_et_un_identifiant_inconnu_sont_indiscernables(decor):
    organisation, projet, profils = decor
    client = _client()
    mauvais = _connecter(client, "amina", "faux")
    inconnu = _connecter(client, "personne", "x")
    assert mauvais.status_code == inconnu.status_code == 401
    assert mauvais.json() == inconnu.json()
    assert mauvais.json()["code"] == "IDENTIFIANTS_INVALIDES"
    _reset()
    assert client.get(f"{RACINE}/moi/").status_code == 401  # aucune session n'a été ouverte


def test_un_compte_desactive_ne_se_connecte_pas(decor):
    organisation, projet, profils = decor
    _poser(organisation)
    Utilisateur.objects.filter(pk=profils["amina"].pk).update(is_active=False)
    reponse = _connecter(_client())
    assert (reponse.status_code, reponse.json()["code"]) == (401, "IDENTIFIANTS_INVALIDES")


def test_la_connexion_exige_les_deux_champs_et_du_json(decor):
    client = _client()
    assert _envoyer(client, "post", "/connexion/", {"identifiant": "amina"}).status_code == 422
    assert _envoyer(client, "post", "/connexion/", {"mot_de_passe": "x"}).status_code == 422
    assert (
        _envoyer(client, "post", "/connexion/", {"identifiant": 1, "mot_de_passe": "x"}).status_code
        == 422
    )


def test_le_message_d_erreur_suit_la_langue_du_navigateur(decor):
    client = _client()
    fr = _connecter(client, "amina", "faux").json()["message"]
    en = _envoyer(
        client, "post", "/connexion/", {"identifiant": "amina", "mot_de_passe": "faux"},
        HTTP_ACCEPT_LANGUAGE="en",
    ).json()["message"]  # fmt: skip
    assert fr != en and "incorrect" in fr.lower() + en.lower()


def test_moi_sans_session_est_un_401_lisible(decor):
    _reset()
    reponse = Client().get(f"{RACINE}/moi/")
    assert reponse.status_code == 401
    assert reponse.json()["code"] == "NON_AUTHENTIFIE" and reponse.json()["message"]


def test_on_ne_voit_que_ses_projets_et_ses_operations_sur_chacun(decor):
    organisation, p1, profils = decor
    p2 = _creer_projet(organisation, "P2")
    _poser(organisation)
    role = Role.objects.create(
        org_id=organisation.id, code="LECT", label={"fr": "l"}, operations=["consulter"]
    )
    autre = Role.objects.create(
        org_id=organisation.id, code="SITE", label={"fr": "s"}, operations=["consulter", "exporter"]
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=profils["amina"].id, project_id=p2.id, role=role
    )
    Habilitation.objects.create(
        org_id=organisation.id,
        user_id=profils["bruno"].id,
        project_id=p2.id,
        role=autre,
        site="DJI",
    )
    client = _client()
    amina = {p["code"]: p for p in _connecter(client).json()["projets"]}
    assert set(amina) == {"P1", "P2"} and amina["P2"]["operations"] == ["consulter"]
    client_b = _client()
    bruno = {p["code"]: p for p in _connecter(client_b, "bruno").json()["projets"]}
    assert bruno["P1"]["operations"] == ["consulter", "valider"]
    # Une habilitation limitée à un site n'est jamais présentée comme une habilitation du projet.
    assert bruno["P2"]["operations"] == []
    assert bruno["P2"]["operations_par_site"] == {"DJI": ["consulter", "exporter"]}


def test_une_autre_organisation_ne_voit_rien_de_celle_ci(decor):
    organisation, p1, profils = decor
    autre = _creer_organisation("ORG-B")
    _creer_projet(autre, "PB")
    _poser(autre)
    Utilisateur.objects.create_user("zoe", password="x", org_id=autre.id)
    corps = _connecter(_client(), "zoe").json()
    assert corps["organisation"]["code"] == "ORG-B" and corps["projets"] == []


def test_un_compte_de_plateforme_n_a_ni_organisation_ni_projet(decor):
    _reset()
    Utilisateur.objects.create_user("plateforme", password="x", org_id=None)
    corps = _connecter(_client(), "plateforme").json()
    assert corps["organisation"] is None and corps["projets"] == []


def test_changer_de_langue_se_garde_et_se_valide(decor):
    client = _client()
    _connecter(client)
    reponse = _envoyer(client, "patch", "/moi/", {"langue": "en"})
    assert (reponse.status_code, reponse.json()["langue"]) == (200, "en")
    _reset()
    assert client.get(f"{RACINE}/moi/").json()["langue"] == "en"
    refus = _envoyer(client, "patch", "/moi/", {"langue": "ar"})
    assert refus.status_code == 422
    assert _envoyer(client, "patch", "/moi/", {"langue": "en"}, jeton=False).status_code == 403


def test_se_deconnecter_ferme_la_session_et_exige_le_jeton_csrf(decor):
    client = _client()
    _connecter(client)
    assert _envoyer(client, "post", "/deconnexion/", jeton=False).status_code == 403
    assert _envoyer(client, "post", "/deconnexion/").status_code == 204
    _reset()
    assert client.get(f"{RACINE}/moi/").status_code == 401


def test_la_session_change_a_la_connexion(decor):
    """Contre la fixation de session : l'ancien identifiant de session ne survit pas."""
    client = _client()
    avant = client.cookies.get("sessionid")
    _connecter(client)
    assert client.cookies["sessionid"].value != (avant.value if avant else None)
