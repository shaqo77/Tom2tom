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
    # Lisible par le frontend : le même format que toute erreur de l'API, pas une page HTML.
    assert reponse.json()["code"] == "CSRF_INVALIDE" and reponse.json()["message"]


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


# --- limitation des tentatives et changement de mot de passe -------------------------------------


@pytest.fixture(autouse=True)
def _cache_vide():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _echouer(client, identifiant, fois):
    return [_connecter(client, identifiant, "faux").status_code for _ in range(fois)]


def test_apres_cinq_echecs_meme_le_bon_mot_de_passe_est_refuse_temporairement(decor):
    client = _client()
    assert _echouer(client, "amina", 5) == [401] * 5
    bloque = _connecter(client, "amina", "x")  # le BON mot de passe
    assert bloque.status_code == 429
    assert bloque.json()["code"] == "TROP_DE_TENTATIVES" and bloque.json()["message"]
    assert int(bloque["Retry-After"]) > 0
    _reset()
    assert client.get(f"{RACINE}/moi/").status_code == 401  # rien ne s'est ouvert


def test_les_autres_comptes_ne_sont_pas_touches_par_le_blocage_d_un_compte(decor):
    client = _client()
    _echouer(client, "amina", 5)
    assert _connecter(_client(), "bruno").status_code == 200


def test_un_identifiant_inconnu_est_limite_comme_un_identifiant_connu(decor):
    """Sinon la limitation révélerait quels comptes existent."""
    client = _client()
    assert _echouer(client, "personne", 5) == [401] * 5
    assert _connecter(client, "personne", "x").status_code == 429


def test_une_connexion_reussie_remet_le_compteur_a_zero(decor):
    client = _client()
    _echouer(client, "amina", 4)
    assert _connecter(_client(), "amina").status_code == 200
    assert _echouer(_client(), "amina", 4) == [401] * 4  # repart de zéro, pas de blocage


def test_une_adresse_qui_essaie_trop_de_comptes_est_limitee(decor):
    client = _client()
    codes = [_connecter(client, f"inconnu{i}", "faux").status_code for i in range(31)]
    assert codes[:30] == [401] * 30 and codes[30] == 429


def _changer(client, actuel="x", nouveau="Un-mot-de-passe-solide-2026", **plus):
    return _envoyer(
        client, "post", "/mot-de-passe/", {"actuel": actuel, "nouveau": nouveau}, **plus
    )


def test_changer_son_mot_de_passe_garde_la_session_et_remplace_l_ancien(decor):
    client = _client()
    _connecter(client)
    assert _changer(client).status_code == 204
    _reset()
    assert client.get(f"{RACINE}/moi/").status_code == 200  # la session n'est pas coupée
    assert _connecter(_client(), "amina", "x").status_code == 401  # l'ancien ne marche plus
    assert _connecter(_client(), "amina", "Un-mot-de-passe-solide-2026").status_code == 200


def test_un_mauvais_mot_de_passe_actuel_ou_un_mot_de_passe_faible_est_refuse(decor):
    client = _client()
    _connecter(client)
    faux = _changer(client, actuel="faux")
    assert (faux.status_code, faux.json()["code"]) == (422, "REGLE_INVALIDE")
    faible = _changer(client, nouveau="court")
    assert faible.status_code == 422 and faible.json()["message"]
    assert _changer(client).status_code == 204  # un mot de passe solide est posé
    solide = "Un-mot-de-passe-solide-2026"
    identique = _changer(
        client, actuel=solide, nouveau=solide
    )  # solide, donc refusé pour autre chose
    assert identique.status_code == 422 and "différent" in identique.json()["message"]
    assert (
        _connecter(_client(), "amina", solide).status_code == 200
    )  # le dernier mot de passe reste


def test_changer_de_mot_de_passe_exige_une_session_et_le_jeton_csrf(decor):
    anonyme = _client()
    assert _changer(anonyme).status_code == 401
    client = _client()
    _connecter(client)
    assert _changer(client, jeton=False).status_code == 403


def test_deviner_le_mot_de_passe_actuel_est_limite_aussi(decor):
    client = _client()
    _connecter(client)
    codes = [_changer(client, actuel=f"faux{i}").status_code for i in range(5)]
    assert codes == [422] * 5
    assert _changer(client, actuel="x").status_code == 429  # même le bon est refusé un temps


def test_le_refus_csrf_hors_api_reste_la_page_de_django():
    from django.test import RequestFactory

    from core.csrf import refus_csrf

    reponse = refus_csrf(RequestFactory().post("/export/x/"), reason="absent")
    assert reponse.status_code == 403 and reponse["Content-Type"].startswith("text/html")


def test_le_serveur_de_developpement_du_frontend_est_reconnu_mais_jamais_en_production():
    from pathlib import Path

    from config.settings import dev

    assert "http://127.0.0.1:5173" in dev.CSRF_TRUSTED_ORIGINS
    # On lit le fichier : l'importer lèverait, la clé de test étant trop courte pour la production.
    prod = (Path(__file__).parent.parent / "config" / "settings" / "prod.py").read_text("utf-8")
    assert "5173" not in prod
