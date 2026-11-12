"""Habilitations par projet et par site, vérifiées au serveur. Voir L1-T05."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import Client, override_settings
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView

from niveau1_socle.habilitations.models import Habilitation, Role
from niveau1_socle.habilitations.permissions import HabilitationRequise, est_habilite
from tests.test_organisations_bd import _creer_organisation, _creer_projet

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()


class VueConsulter(APIView):
    permission_classes = [HabilitationRequise]
    operation = "consulter"

    def get(self, requete, project_id, site=None):
        return Response({"projet": str(project_id)})


class VueSaisir(VueConsulter):
    operation = "saisir"


class VueSansOperation(APIView):
    """Une vue qui oublie de déclarer son opération doit être fermée, pas ouverte."""

    permission_classes = [HabilitationRequise]

    def get(self, requete, project_id):
        return Response({})


urlpatterns = [
    path("projets/<uuid:project_id>/", VueConsulter.as_view()),
    path("projets/<uuid:project_id>/sites/<str:site>/", VueConsulter.as_view()),
    path("projets/<uuid:project_id>/saisie/", VueSaisir.as_view()),
    path("projets/<uuid:project_id>/oubli/", VueSansOperation.as_view()),
]


def _sans_perimetre():
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")


def _role(organisation, code, operations):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])
    return Role.objects.create(
        org_id=organisation.id,
        code=code,
        label={"fr": code, "en": code},
        operations=operations,
    )


def _habiliter(organisation, utilisateur, projet, role, *, site=None):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])
    return Habilitation.objects.create(
        org_id=organisation.id,
        user_id=utilisateur.id,
        project_id=projet.id,
        site=site,
        role=role,
    )


@pytest.fixture
def decor():
    organisation = _creer_organisation("ORG-A")
    p1 = _creer_projet(organisation, "P1")
    p2 = _creer_projet(organisation, "P2")
    amina = Utilisateur.objects.create_user("amina", password="x", org_id=organisation.id)
    lecteur = _role(organisation, "LECTEUR", ["consulter"])
    _sans_perimetre()
    return organisation, p1, p2, amina, lecteur


def _client(utilisateur):
    client = Client()
    client.force_login(utilisateur)
    return client


@override_settings(ROOT_URLCONF=__name__)
def test_habilite_sur_le_projet_a_refuse_sur_le_projet_b_de_la_meme_organisation(decor):
    """Contrôle de L1-T05."""
    organisation, p1, p2, amina, lecteur = decor
    _habiliter(organisation, amina, p1, lecteur)
    _sans_perimetre()

    client = _client(amina)
    assert client.get(f"/projets/{p1.id}/").status_code == 200
    assert client.get(f"/projets/{p2.id}/").status_code == 403


@override_settings(ROOT_URLCONF=__name__)
def test_une_operation_non_accordee_est_refusee_meme_sur_le_bon_projet(decor):
    organisation, p1, _, amina, lecteur = decor
    _habiliter(organisation, amina, p1, lecteur)
    _sans_perimetre()

    client = _client(amina)
    assert client.get(f"/projets/{p1.id}/").status_code == 200
    assert client.get(f"/projets/{p1.id}/saisie/").status_code == 403


@override_settings(ROOT_URLCONF=__name__)
def test_une_habilitation_limitee_a_un_site_ne_vaut_que_pour_ce_site(decor):
    organisation, p1, _, amina, lecteur = decor
    _habiliter(organisation, amina, p1, lecteur, site="SIEGE")
    _sans_perimetre()

    client = _client(amina)
    assert client.get(f"/projets/{p1.id}/sites/SIEGE/").status_code == 200
    assert client.get(f"/projets/{p1.id}/sites/REG-N/").status_code == 403
    # Sans site demandé, une habilitation limitée à un site ne couvre pas le projet entier.
    assert client.get(f"/projets/{p1.id}/").status_code == 403


@override_settings(ROOT_URLCONF=__name__)
def test_une_habilitation_sans_site_couvre_tous_les_sites(decor):
    organisation, p1, _, amina, lecteur = decor
    _habiliter(organisation, amina, p1, lecteur, site=None)
    _sans_perimetre()

    client = _client(amina)
    assert client.get(f"/projets/{p1.id}/sites/REG-S/").status_code == 200
    assert client.get(f"/projets/{p1.id}/").status_code == 200


@override_settings(ROOT_URLCONF=__name__)
def test_le_defaut_est_la_fermeture(decor):
    organisation, p1, _, amina, lecteur = decor
    _habiliter(organisation, amina, p1, lecteur)
    root = Utilisateur.objects.create_superuser("root", password="x")
    _sans_perimetre()

    # Anonyme, compte de plateforme (même superutilisateur), vue sans opération : refus.
    assert Client().get(f"/projets/{p1.id}/").status_code in (401, 403)
    assert _client(root).get(f"/projets/{p1.id}/").status_code == 403
    assert _client(amina).get(f"/projets/{p1.id}/oubli/").status_code == 403


@override_settings(ROOT_URLCONF=__name__)
def test_une_habilitation_dune_autre_organisation_ne_donne_aucun_acces(decor):
    organisation, p1, _, _, lecteur = decor
    autre = _creer_organisation("ORG-B")
    intrus = Utilisateur.objects.create_user("intrus", password="x", org_id=autre.id)
    role_b = _role(autre, "LECTEUR", ["consulter"])
    # L'intrus est habilité chez lui, mais réclame un projet de l'organisation A.
    projet_b = _creer_projet(autre, "PB")
    _habiliter(autre, intrus, projet_b, role_b)
    _sans_perimetre()

    client = _client(intrus)
    assert client.get(f"/projets/{projet_b.id}/").status_code == 200
    assert client.get(f"/projets/{p1.id}/").status_code == 403


def test_est_habilite_lit_le_perimetre_de_lutilisateur(decor):
    organisation, p1, p2, amina, lecteur = decor
    _habiliter(organisation, amina, p1, lecteur)
    _habiliter(organisation, amina, p2, _role(organisation, "SAISIE", ["consulter", "saisir"]))

    assert est_habilite(amina, "consulter", p1.id)
    assert not est_habilite(amina, "saisir", p1.id)
    assert est_habilite(amina, "saisir", p2.id)
    assert not est_habilite(amina, "publier", p2.id)
    assert not est_habilite(amina, "consulter", uuid.uuid4())


def test_un_role_ne_peut_porter_quune_operation_connue(decor):
    organisation, *_ = decor
    with pytest.raises(IntegrityError), transaction.atomic():
        _role(organisation, "FANTAISISTE", ["consulter", "supprimer_tout"])
    with pytest.raises(IntegrityError), transaction.atomic():
        _role(organisation, "SCALAIRE", "consulter")  # doit être une liste


def test_la_meme_habilitation_nest_pas_enregistree_deux_fois(decor):
    organisation, p1, _, amina, lecteur = decor
    _habiliter(organisation, amina, p1, lecteur)
    with pytest.raises(IntegrityError), transaction.atomic():
        _habiliter(organisation, amina, p1, lecteur)  # site nul : doublon aussi
    _habiliter(organisation, amina, p1, lecteur, site="SIEGE")


def test_les_roles_et_habilitations_sont_isoles_par_organisation(decor):
    organisation, p1, _, amina, lecteur = decor
    _habiliter(organisation, amina, p1, lecteur)
    _creer_organisation("ORG-B")  # pose le périmètre de B
    assert Role.objects.count() == 0
    assert Habilitation.objects.count() == 0
