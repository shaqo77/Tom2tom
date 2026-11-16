# ruff: noqa: F811, E501
"""L'accès auditeur : jeton à portée et durée limitées, lecture seule. Voir L7-T02.

Contrôle du plan : un jeton auditeur sur le projet A reçoit 403 sur le projet B ; après expiration,
401 partout ; les accès figurent au journal d'audit de l'organisation.
"""

import datetime
import hashlib
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from core.audit import verifier_chaine
from core.erreurs import ErreurMetier
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau4_reporting.publication import auditeur
from niveau4_reporting.publication.auditeur import (
    creer_acces_auditeur,
    journal_des_acces,
    revoquer_acces_auditeur,
)
from niveau4_reporting.publication.exports import exporter_rapport
from niveau4_reporting.publication.models import AccesAuditeur
from tests.outils import connexion_proprietaire
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_exports_rapport_bd import rapport  # noqa: F401
from tests.test_regeneration_bd import pub  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = datetime.date
PLAGE = (D(2026, 1, 1), D(2026, 12, 31))


@pytest.fixture
def aud(rapport):
    publie, profils = rapport
    organisation_id, projet_id = publie.org_id, publie.project_id
    admin = Utilisateur.objects.create_user("admin", password="x", org_id=organisation_id)
    role = Role.objects.create(
        org_id=organisation_id,
        code="ADM",
        label={"fr": "adm"},
        operations=["consulter", "parametrer"],
    )
    Habilitation.objects.create(
        org_id=organisation_id, user_id=admin.id, project_id=projet_id, role=role
    )
    profils["admin"] = admin
    fichier = exporter_rapport(utilisateur=profils["pia"], rapport=publie, format="pdf")
    acces, jeton = creer_acces_auditeur(
        utilisateur=admin, nom="Cabinet Externe", project_ids=[projet_id],
        period_from=PLAGE[0], period_to=PLAGE[1], duree_jours=30,
    )  # fmt: skip
    return publie, profils, acces, jeton, fichier


def _get(url, jeton=None, methode="get", **kw):
    client = APIClient()
    if jeton:
        client.credentials(HTTP_AUTHORIZATION=f"Auditeur {jeton}")
    with connection.cursor() as cur:  # aucune organisation héritée de la connexion de test
        cur.execute("RESET app.org_id")
    return getattr(client, methode)(url, **kw)


def _urls(publie, fichier=None):
    base = f"/auditeur/projets/{publie.project_id}/rapports/"
    return {
        "liste": base,
        "detail": f"{base}{publie.id}/",
        "dossier": f"{base}{publie.id}/dossier/",
        "fichier": f"{base}{publie.id}/fichiers/{fichier.id}/" if fichier else None,
    }


# --- création de l'accès ---------------------------------------------------------------------


def test_le_jeton_n_est_jamais_stocke_et_l_acces_est_borne(aud):
    publie, profils, acces, jeton, _ = aud
    secret = jeton.split(".", 1)[1]
    assert bytes(acces.jeton_hash) == hashlib.sha256(secret.encode()).digest()
    with connection.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM publication_accesauditeur WHERE nom LIKE %s", [f"%{secret}%"]
        )
        assert cur.fetchone()[0] == 0
    assert acces.project_ids == [str(publie.project_id)]
    assert (acces.expire_le - acces.created_at).days in (29, 30)


@pytest.mark.parametrize(
    "champs",
    [
        {"nom": " "},
        {"project_ids": []},
        {"duree_jours": 0},
        {"duree_jours": 91},
        {"period_from": D(2027, 1, 1)},
        {"project_ids": [uuid.uuid4()]},
    ],
)
def test_un_acces_invalide_est_refuse(aud, champs):
    publie, profils, *_ = aud
    base = {
        "utilisateur": profils["admin"], "nom": "X", "project_ids": [publie.project_id],
        "period_from": PLAGE[0], "period_to": PLAGE[1], "duree_jours": 10,
    }  # fmt: skip
    with pytest.raises((ErreurMetier, PermissionDenied)):
        creer_acces_auditeur(**{**base, **champs})


def test_seul_un_parametreur_du_projet_cree_un_acces(aud):
    publie, profils, *_ = aud
    with pytest.raises(PermissionDenied):
        creer_acces_auditeur(
            utilisateur=profils["pia"], nom="X", project_ids=[publie.project_id],
            period_from=PLAGE[0], period_to=PLAGE[1], duree_jours=10,
        )  # fmt: skip


# --- 401 : pas de jeton valable --------------------------------------------------------------


@pytest.mark.parametrize(
    "variante",
    ["absent", "autre_schema", "sans_point", "secret_faux", "organisation_fausse", "illisible"],
)
def test_sans_jeton_valable_c_est_401(aud, variante):
    publie, _, _, jeton, _ = aud
    organisation, secret = jeton.split(".", 1)
    jetons = {
        "absent": None,
        "autre_schema": None,
        "sans_point": "pasdepoint",
        "secret_faux": f"{organisation}.{secret[:-2]}zz",
        "organisation_fausse": f"{uuid.uuid4()}.{secret}",
        "illisible": "pas-un-uuid.xxx",
    }
    reponse = _get(_urls(publie)["liste"], jetons[variante])
    assert reponse.status_code == 401


def test_un_jeton_valide_lit_les_rapports_de_son_projet(aud):
    publie, _, _, jeton, _ = aud
    reponse = _get(_urls(publie)["liste"], jeton)
    assert reponse.status_code == 200
    assert [r["id"] for r in reponse.json()] == [str(publie.id)]
    assert reponse.json()[0]["scelle"] == bytes(publie.seal).hex()


# --- 403 : un autre projet, ou une écriture --------------------------------------------------


def test_un_jeton_sur_le_projet_a_recoit_403_sur_le_projet_b(aud):
    publie, profils, _, jeton, _ = aud
    organisation = type("O", (), {"id": publie.org_id})
    projet_b = _creer_projet(organisation, "P-B")
    for chemin in (
        f"/auditeur/projets/{projet_b.id}/rapports/",
        f"/auditeur/projets/{uuid.uuid4()}/rapports/",
    ):
        assert _get(chemin, jeton).status_code == 403


@pytest.mark.parametrize("methode", ["post", "put", "patch", "delete"])
def test_un_auditeur_n_ecrit_rien(aud, methode):
    publie, _, _, jeton, _ = aud
    for url in _urls(publie).values():
        if url:
            assert _get(url, jeton, methode).status_code == 403


# --- expiration et révocation : 401 partout --------------------------------------------------


def test_apres_expiration_c_est_401_partout(aud, monkeypatch):
    publie, _, acces, jeton, fichier = aud
    urls = _urls(publie, fichier)
    assert all(_get(u, jeton).status_code == 200 for u in urls.values())
    futur = acces.expire_le + datetime.timedelta(seconds=1)
    monkeypatch.setattr(auditeur, "maintenant", lambda: futur)
    assert {name: _get(u, jeton).status_code for name, u in urls.items()} == dict.fromkeys(
        urls, 401
    )
    # y compris sur un projet qui n'est pas le sien : 401 d'abord.
    assert _get(f"/auditeur/projets/{uuid.uuid4()}/rapports/", jeton).status_code == 401


def test_un_acces_revoque_est_401(aud):
    publie, profils, acces, jeton, _ = aud
    assert _get(_urls(publie)["liste"], jeton).status_code == 200
    with connection.cursor() as cur:  # `_get` a retiré l'organisation de la connexion de test
        cur.execute("SET app.org_id = %s", [str(publie.org_id)])
    revoquer_acces_auditeur(utilisateur=profils["admin"], acces=acces)
    assert _get(_urls(publie)["liste"], jeton).status_code == 401


# --- la plage de périodes ---------------------------------------------------------------------


def test_un_rapport_hors_de_la_plage_n_existe_pas_pour_l_auditeur(aud):
    publie, profils, _, _, _ = aud
    _, jeton = creer_acces_auditeur(
        utilisateur=profils["admin"], nom="T2", project_ids=[publie.project_id],
        period_from=D(2026, 4, 1), period_to=D(2026, 6, 30), duree_jours=5,
    )  # fmt: skip
    urls = _urls(publie)
    assert _get(urls["liste"], jeton).json() == []  # le rapport finit le 31/03
    assert _get(urls["detail"], jeton).status_code == 404
    assert _get(urls["dossier"], jeton).status_code == 404


# --- le journal ---------------------------------------------------------------------------------


def test_chaque_consultation_et_chaque_export_figurent_au_journal_de_l_organisation(aud):
    publie, profils, acces, jeton, fichier = aud
    urls = _urls(publie, fichier)
    for nom in ("liste", "detail", "dossier", "fichier"):
        assert _get(urls[nom], jeton).status_code == 200
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(publie.org_id)])
    entrees = journal_des_acces(utilisateur=profils["admin"], project_id=publie.project_id)
    consultations = [e for e in entrees if e.action == "auditor_consulted"]
    assert [e.after["ressource"] for e in reversed(consultations)] == [
        "rapports",
        "rapport",
        "dossier",
        "export",
    ]
    assert all(
        e.actor_id == acces.id and e.after["nom"] == "Cabinet Externe" for e in consultations
    )
    export = consultations[0]
    assert export.after["sha256"] == fichier.sha256
    assert {"auditor_access_granted"} <= {e.action for e in entrees}
    verifier_chaine(publie.org_id)  # le journal reste intègre (lève sinon)


def test_un_refus_n_est_pas_une_consultation(aud):
    publie, profils, _, jeton, _ = aud
    _get(f"/auditeur/projets/{uuid.uuid4()}/rapports/", jeton)
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(publie.org_id)])
    avant = len(journal_des_acces(utilisateur=profils["admin"], project_id=publie.project_id))
    assert (
        all(
            e.action != "auditor_consulted"
            for e in journal_des_acces(utilisateur=profils["admin"], project_id=publie.project_id)
        )
        and avant >= 1
    )


def test_seul_un_parametreur_lit_le_journal_des_acces(aud):
    publie, profils, *_ = aud
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(publie.org_id)])
    with pytest.raises(PermissionDenied):
        journal_des_acces(utilisateur=profils["pia"], project_id=publie.project_id)


# --- exports et dossier -----------------------------------------------------------------------


def test_l_export_rend_les_octets_enregistres_avec_leur_empreinte(aud):
    publie, _, _, jeton, fichier = aud
    reponse = _get(_urls(publie, fichier)["fichier"], jeton)
    assert reponse.status_code == 200
    assert (
        hashlib.sha256(reponse.content).hexdigest()
        == fichier.sha256
        == reponse["X-Empreinte-SHA256"]
    )


def test_le_dossier_de_conformite_se_consulte(aud):
    publie, _, _, jeton, _ = aud
    donnees = _get(_urls(publie)["dossier"], jeton).json()
    assert [r["code"] for r in donnees["rubriques"]] == ["R110", "R120", "R190"]
    assert donnees["taux_couverture"] == "0"  # aucune exigence rattachée dans ce scénario


# --- aucune prolongation, aucune suppression, isolation ---------------------------------------


def test_la_base_refuse_toute_prolongation_et_toute_suppression(aud):
    _, _, acces, _, _ = aud
    with pytest.raises(IntegrityError), transaction.atomic():
        AccesAuditeur.objects.filter(pk=acces.pk).update(
            expire_le=acces.expire_le + datetime.timedelta(days=60)
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        AccesAuditeur.objects.filter(pk=acces.pk).update(period_to=D(2099, 1, 1))
    with pytest.raises(IntegrityError), transaction.atomic():
        AccesAuditeur.objects.filter(pk=acces.pk).delete()
    with connexion_proprietaire() as proprietaire:  # y compris le rôle propriétaire
        with pytest.raises(Exception, match="prolonge"):
            proprietaire.execute(
                "UPDATE publication_accesauditeur SET expire_le = expire_le + interval '1 day'"
            )


def test_un_jeton_d_une_autre_organisation_ne_donne_rien(aud):
    from tests.test_organisations_bd import _creer_organisation

    publie, profils, _, jeton, _ = aud
    autre = _creer_organisation("ORG-B")
    projet_b = _creer_projet(autre, "PB")
    admin_b = Utilisateur.objects.create_user("admin_b", password="x", org_id=autre.id)
    role = Role.objects.create(
        org_id=autre.id, code="ADM", label={"fr": "a"}, operations=["parametrer"]
    )
    Habilitation.objects.create(
        org_id=autre.id, user_id=admin_b.id, project_id=projet_b.id, role=role
    )
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(autre.id)])
    _, jeton_b = creer_acces_auditeur(
        utilisateur=admin_b, nom="B", project_ids=[projet_b.id],
        period_from=PLAGE[0], period_to=PLAGE[1], duree_jours=5,
    )  # fmt: skip
    # Le jeton B ne lit pas le projet A (403) ; le secret B derrière l'organisation A : 401.
    assert _get(_urls(publie)["liste"], jeton_b).status_code == 403
    secret_b = jeton_b.split(".", 1)[1]
    assert _get(_urls(publie)["liste"], f"{publie.org_id}.{secret_b}").status_code == 401
