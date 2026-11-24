# ruff: noqa: F811
"""Le jeton d'API (Lot 2-C) : un programme appelle l'API sans mot de passe ni navigateur.

Le jeton est `<organisation>.<secret>`, comme l'accès auditeur : l'organisation (en clair) pose
le périmètre de la transaction, PUIS on cherche l'empreinte du secret sous l'isolation.
Aucune exception à la RLS. Le jeton agit avec les droits de son propriétaire, jamais davantage.
"""

import datetime
import json
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import Client

from niveau1_socle.organisations import jetons
from tests.test_api_marches_bd import RACINE, appeler
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()


def _reset():
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")


def _poser(organisation):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


def _creer(utilisateur, libelle="Intégration comptable", duree_jours=30):
    r = appeler(utilisateur, "post", "/jetons/", {"libelle": libelle, "duree_jours": duree_jours})
    assert r.status_code == 201, r.content
    return r.json()


def _avec_jeton(jeton, methode, chemin, donnees=None, *, client=None):
    """Un programme : aucun cookie, aucun CSRF, seulement l'en-tête Authorization."""
    client = client or Client(enforce_csrf_checks=True)
    _reset()
    en_tetes = {"HTTP_AUTHORIZATION": f"Bearer {jeton}"} if jeton is not None else {}
    appel = getattr(client, methode)
    if methode in ("get", "delete"):
        return appel(f"{RACINE}{chemin}", **en_tetes)
    return appel(
        f"{RACINE}{chemin}",
        data=json.dumps(donnees or {}),
        content_type="application/json",
        **en_tetes,
    )


def _accords(projet):
    return f"/projets/{projet.id}/accords/"


# --- création, liste, révocation -------------------------------------------------------------


def test_un_jeton_se_cree_une_fois_et_ne_se_relit_plus(decor):
    organisation, projet, profils = decor
    cree = _creer(profils["amina"])
    assert cree["jeton"].startswith(f"{organisation.id}.")
    assert len(cree["jeton"].split(".", 1)[1]) >= 32
    assert cree["prefixe"] == cree["jeton"].split(".", 1)[1][:8]
    liste = appeler(profils["amina"], "get", "/jetons/").json()
    assert [j["id"] for j in liste] == [cree["id"]]
    assert "jeton" not in liste[0] and "empreinte" not in liste[0] and "secret" not in liste[0]
    assert liste[0]["prefixe"] == cree["prefixe"] and liste[0]["revoque_le"] is None


def test_le_secret_n_apparait_nulle_part_en_base(decor):
    organisation, _, profils = decor
    secret = _creer(profils["amina"])["jeton"].split(".", 1)[1]
    _poser(organisation)
    with connection.cursor() as cur:
        cur.execute("SELECT t::text FROM organisations_jetonapi t")
        assert secret not in "".join(ligne[0] for ligne in cur.fetchall())
        cur.execute("SELECT t::text FROM core_auditlog t")
        assert secret not in "".join(ligne[0] for ligne in cur.fetchall())
        cur.execute("SELECT count(*) FROM core_auditlog WHERE action = 'api_token_created'")
        assert cur.fetchone()[0] == 1


@pytest.mark.parametrize(
    "corps",
    [
        {"libelle": "", "duree_jours": 30},
        {"duree_jours": 30},
        {"libelle": "x", "duree_jours": 0},
        {"libelle": "x", "duree_jours": 366},
        {"libelle": "x", "duree_jours": "30"},
        {"libelle": "x" * 201, "duree_jours": 30},
    ],
)
def test_une_creation_invalide_est_refusee_au_format_stable(decor, corps):
    _, _, profils = decor
    r = appeler(profils["amina"], "post", "/jetons/", corps)
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}


def test_un_jeton_ne_sert_pas_a_creer_un_jeton(decor):
    _, _, profils = decor
    jeton = _creer(profils["amina"])["jeton"]
    r = _avec_jeton(jeton, "post", "/jetons/", {"libelle": "x", "duree_jours": 30})
    assert r.status_code in (401, 403)


def test_on_ne_voit_et_ne_revoque_que_ses_propres_jetons(decor):
    _, _, profils = decor
    de_bruno = _creer(profils["bruno"])
    assert appeler(profils["amina"], "get", "/jetons/").json() == []
    r = appeler(profils["amina"], "post", f"/jetons/{de_bruno['id']}/revocation/")
    assert r.status_code == 404
    assert _avec_jeton(de_bruno["jeton"], "get", "/session/moi/").status_code == 200


def test_la_revocation_coupe_le_jeton_et_se_journalise(decor):
    organisation, projet, profils = decor
    cree = _creer(profils["amina"])
    assert _avec_jeton(cree["jeton"], "get", _accords(projet)).status_code == 200
    r = appeler(profils["amina"], "post", f"/jetons/{cree['id']}/revocation/")
    assert r.status_code == 200 and r.json()["revoque_le"]
    assert _avec_jeton(cree["jeton"], "get", _accords(projet)).status_code == 401
    # Révoquer deux fois ne change rien.
    assert appeler(profils["amina"], "post", f"/jetons/{cree['id']}/revocation/").status_code == 200
    _poser(organisation)
    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM core_auditlog WHERE action = 'api_token_revoked'")
        assert cur.fetchone()[0] == 1


# --- l'authentification --------------------------------------------------------------------


def test_un_jeton_valide_authentifie_son_proprietaire(decor):
    _, projet, profils = decor
    jeton = _creer(profils["amina"])["jeton"]
    r = _avec_jeton(jeton, "get", "/session/moi/")
    assert r.status_code == 200 and r.json()["identifiant"] == "amina"
    assert _avec_jeton(jeton, "get", _accords(projet)).status_code == 200


def test_un_secret_faux_une_organisation_fausse_ou_un_jeton_mal_forme_donnent_401(decor):
    organisation, _, profils = decor
    organisation_id, secret = _creer(profils["amina"])["jeton"].split(".", 1)
    mauvais = [
        f"{organisation_id}.{secret}X",  # secret faux
        f"{organisation_id}.{'a' * len(secret)}",
        f"{uuid.uuid4()}.{secret}",  # organisation inconnue
        secret,  # sans organisation
        f"{organisation_id}.",  # sans secret
        f"{organisation_id}",
        f"pas-un-uuid.{secret}",
        "",
        ".",
        "é.é",
        "a" * 5000,
        f"{organisation_id}.{'é' * 50}",
    ]
    for jeton in mauvais:
        r = _avec_jeton(jeton, "get", "/session/moi/")
        assert r.status_code == 401, (jeton[:40], r.status_code)
        assert set(r.json()) == {"code", "message"}


def test_un_en_tete_authorization_d_un_autre_schema_n_authentifie_personne(decor):
    _, _, profils = decor
    jeton = _creer(profils["amina"])["jeton"]
    for valeur in (f"Basic {jeton}", f"Token {jeton}", jeton, "Bearer", "Bearer  "):
        _reset()
        r = Client().get(f"{RACINE}/session/moi/", HTTP_AUTHORIZATION=valeur)
        assert r.status_code in (401, 403), valeur


def test_un_jeton_expire_est_refuse(decor, monkeypatch):
    _, _, profils = decor
    jeton = _creer(profils["amina"], duree_jours=1)["jeton"]
    assert _avec_jeton(jeton, "get", "/session/moi/").status_code == 200
    futur = jetons.maintenant() + datetime.timedelta(days=2)
    monkeypatch.setattr(jetons, "maintenant", lambda: futur)
    r = _avec_jeton(jeton, "get", "/session/moi/")
    assert r.status_code == 401 and set(r.json()) == {"code", "message"}


def test_un_proprietaire_desactive_perd_ses_jetons(decor):
    organisation, _, profils = decor
    jeton = _creer(profils["amina"])["jeton"]
    _poser(organisation)
    Utilisateur.objects.filter(pk=profils["amina"].pk).update(is_active=False)
    assert _avec_jeton(jeton, "get", "/session/moi/").status_code == 401


def test_le_dernier_usage_se_met_a_jour(decor):
    organisation, _, profils = decor
    cree = _creer(profils["amina"])
    assert appeler(profils["amina"], "get", "/jetons/").json()[0]["dernier_usage"] is None
    assert _avec_jeton(cree["jeton"], "get", "/session/moi/").status_code == 200
    assert appeler(profils["amina"], "get", "/jetons/").json()[0]["dernier_usage"] is not None


# --- isolation et droits ---------------------------------------------------------------------


def test_le_jeton_d_une_autre_organisation_ne_lit_rien_de_la_notre(decor):
    organisation, projet, profils = decor
    autre = _creer_organisation("ORG-B")
    _creer_projet(autre, "PB")
    intrus = Utilisateur.objects.create_user("intrus", password="x", org_id=autre.id)
    jeton_intrus = _creer(intrus)["jeton"]
    # Son jeton fonctionne dans SON organisation…
    assert _avec_jeton(jeton_intrus, "get", "/session/moi/").json()["identifiant"] == "intrus"
    # …mais ne donne aucun accès au projet de la nôtre.
    r = _avec_jeton(jeton_intrus, "get", _accords(projet))
    assert r.status_code in (403, 404)
    # Remplacer l'organisation du jeton par la nôtre ne passe pas : le secret y est inconnu.
    secret = jeton_intrus.split(".", 1)[1]
    assert _avec_jeton(f"{organisation.id}.{secret}", "get", "/session/moi/").status_code == 401


def test_le_jeton_n_elargit_jamais_les_droits_de_son_proprietaire(decor):
    organisation, projet, profils = decor
    sans_droit = Utilisateur.objects.create_user("zoe", password="x", org_id=organisation.id)
    jeton_zoe = _creer(sans_droit)["jeton"]
    jeton_amina = _creer(profils["amina"])["jeton"]
    assert _avec_jeton(jeton_amina, "get", _accords(projet)).status_code == 200
    assert _avec_jeton(jeton_zoe, "get", _accords(projet)).status_code == 403


# --- CSRF ----------------------------------------------------------------------------------------


def test_le_jeton_n_exige_pas_de_csrf_mais_la_session_le_garde(decor):
    _, _, profils = decor
    jeton = _creer(profils["amina"])["jeton"]
    r = _avec_jeton(jeton, "patch", "/session/moi/", {"langue": "en"})
    assert r.status_code == 200 and r.json()["langue"] == "en"
    # Une session sans CSRF reste refusée.
    client = Client(enforce_csrf_checks=True)
    client.force_login(profils["amina"])
    _reset()
    r = client.patch(
        f"{RACINE}/session/moi/",
        data=json.dumps({"langue": "fr"}),
        content_type="application/json",
    )
    assert r.status_code == 403


# --- la table -----------------------------------------------------------------------------------


def test_un_jeton_ne_se_modifie_ni_ne_se_supprime_hors_revocation_et_dernier_usage(decor):
    organisation, _, profils = decor
    cree = _creer(profils["amina"])
    _poser(organisation)
    for sql in (
        "UPDATE organisations_jetonapi SET expire_le = expire_le + interval '400 days'",
        "UPDATE organisations_jetonapi SET empreinte = decode(repeat('00', 32), 'hex')",
        "UPDATE organisations_jetonapi SET utilisateur_id = gen_random_uuid()",
        "DELETE FROM organisations_jetonapi",
    ):
        with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cur:
            cur.execute(sql)
    assert cree["id"]
