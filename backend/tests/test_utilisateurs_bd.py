"""Utilisateur rattaché à une organisation. Voir L1-T01.

La table des utilisateurs est la SEULE à porter `org_id` sans politique
d'isolation : il faut pouvoir la lire au login, avant que l'organisation de
la requête soit connue. Tout le reste de l'application la découvre ensuite par
`request.user.org_id`, que le middleware transforme en périmètre RLS.
"""

import uuid

import pytest
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import connection
from django.http import JsonResponse
from django.test import Client, override_settings
from django.urls import path

from niveau1_socle.organisations.models import Projet
from tests.test_organisations_bd import _creer_organisation, _creer_projet

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()


def vue_projets(requete):
    return JsonResponse(sorted(Projet.objects.values_list("code", flat=True)), safe=False)


urlpatterns = [path("projets/", vue_projets)]


def _sans_perimetre():
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")


def test_le_modele_utilisateur_est_celui_du_socle():
    assert settings.AUTH_USER_MODEL == "organisations.Utilisateur"
    assert isinstance(Utilisateur().id, uuid.UUID)


def test_un_utilisateur_porte_son_organisation_et_se_retrouve_au_login_sans_perimetre():
    org = _creer_organisation("ORG-A")
    Utilisateur.objects.create_user("amina", password="s3cret-Pass", org_id=org.id)

    _sans_perimetre()  # au login, aucune organisation n'est encore posée
    utilisateur = authenticate(username="amina", password="s3cret-Pass")

    assert utilisateur is not None
    assert utilisateur.org_id == org.id
    assert authenticate(username="amina", password="mauvais") is None


def test_un_compte_de_plateforme_nappartient_a_aucune_organisation():
    root = Utilisateur.objects.create_superuser("root", password="s3cret-Pass")
    assert root.org_id is None


@override_settings(ROOT_URLCONF=__name__)
def test_une_requete_authentifiee_ne_voit_que_les_projets_de_son_organisation():
    """Bout en bout : session, middleware, transaction, RLS."""
    a = _creer_organisation("ORG-A")
    b = _creer_organisation("ORG-B")
    _creer_projet(a, "A1")
    _creer_projet(a, "A2")
    _creer_projet(b, "B1")
    amina = Utilisateur.objects.create_user("amina", password="x", org_id=a.id)
    bruno = Utilisateur.objects.create_user("bruno", password="x", org_id=b.id)
    _sans_perimetre()

    client = Client()
    client.force_login(amina)
    assert client.get("/projets/").json() == ["A1", "A2"]
    client.force_login(bruno)
    assert client.get("/projets/").json() == ["B1"]


@override_settings(ROOT_URLCONF=__name__)
def test_un_compte_sans_organisation_ne_voit_aucune_donnee_metier():
    a = _creer_organisation("ORG-A")
    _creer_projet(a, "A1")
    Utilisateur.objects.create_superuser("root", password="x")
    _sans_perimetre()

    client = Client()
    client.force_login(Utilisateur.objects.get(username="root"))
    assert client.get("/projets/").json() == []
