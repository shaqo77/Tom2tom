"""Séparation des tâches : le validateur d'une pièce n'en est pas l'auteur. Voir L1-T06.

La règle est paramétrable par organisation et ACTIVÉE PAR DÉFAUT. Les écritures
n'existent qu'au lot L3 : la ligne d'écriture du prototype tient lieu de pièce.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, override_settings
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView

from niveau1_socle.comptabilite.models import Ecriture
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau1_socle.habilitations.permissions import HabilitationRequise
from niveau1_socle.habilitations.separation import exiger_separation_des_taches
from niveau1_socle.organisations.models import Organisation
from tests.outils import creer_piece
from tests.test_organisations_bd import _creer_organisation, _creer_projet

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()


class ValiderPiece(APIView):
    permission_classes = [HabilitationRequise]
    operation = "valider"

    def post(self, requete, project_id, piece_id):
        piece = Ecriture.objects.get(pk=piece_id, project_id=project_id)
        exiger_separation_des_taches(requete.user, piece.created_by)
        return Response({"validee": str(piece.pk)})


urlpatterns = [path("pieces/<uuid:project_id>/<uuid:piece_id>/valider/", ValiderPiece.as_view())]


def _poser(org_id):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])


def _piece(organisation, projet, auteur):
    _poser(organisation.id)
    return creer_piece(
        organisation.id,
        2026,
        1,
        [{"compte": "6011", "debit": "10"}],
        project_id=projet.id,
        utilisateur_id=auteur.id if auteur else None,
    )


@pytest.fixture
def decor():
    organisation = _creer_organisation("ORG-A")
    projet = _creer_projet(organisation, "P1")
    amina = Utilisateur.objects.create_user("amina", password="x", org_id=organisation.id)
    bruno = Utilisateur.objects.create_user("bruno", password="x", org_id=organisation.id)
    _poser(organisation.id)
    role = Role.objects.create(
        org_id=organisation.id,
        code="VALIDEUR",
        label={"fr": "Validateur"},
        operations=["consulter", "saisir", "valider"],
    )
    for utilisateur in (amina, bruno):
        Habilitation.objects.create(
            org_id=organisation.id,
            user_id=utilisateur.id,
            project_id=projet.id,
            role=role,
        )
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")
    return organisation, projet, amina, bruno


def _valider(utilisateur, projet, piece):
    client = Client()
    client.force_login(utilisateur)
    return client.post(f"/pieces/{projet.id}/{piece.pk}/valider/")


def test_la_regle_est_activee_par_defaut_sur_une_nouvelle_organisation():
    organisation = _creer_organisation("ORG-NEUVE")
    assert Organisation.objects.get(pk=organisation.pk).separation_des_taches is True


@override_settings(ROOT_URLCONF=__name__)
def test_lauteur_dune_piece_recoit_403_en_tentant_de_la_valider(decor):
    """Contrôle de L1-T06, bien qu'il soit habilité à valider."""
    organisation, projet, amina, bruno = decor
    piece = _piece(organisation, projet, auteur=amina)

    assert _valider(amina, projet, piece).status_code == 403
    assert _valider(bruno, projet, piece).status_code == 200


@override_settings(ROOT_URLCONF=__name__)
def test_une_organisation_peut_desactiver_la_regle_pour_elle_seule(decor):
    organisation, projet, amina, _ = decor
    autre = _creer_organisation("ORG-B")
    piece = _piece(organisation, projet, auteur=amina)

    _poser(organisation.id)
    Organisation.objects.filter(pk=organisation.pk).update(separation_des_taches=False)
    assert _valider(amina, projet, piece).status_code == 200
    # L'autre organisation garde la règle par défaut.
    _poser(autre.id)
    assert Organisation.objects.get(pk=autre.pk).separation_des_taches is True


@override_settings(ROOT_URLCONF=__name__)
def test_une_piece_sans_auteur_connu_ne_declenche_pas_la_regle(decor):
    """Pièce importée : aucun auteur à comparer. Ce choix est explicite et testé."""
    organisation, projet, amina, _ = decor
    piece = _piece(organisation, projet, auteur=None)
    assert _valider(amina, projet, piece).status_code == 200


def test_la_regle_compare_des_identifiants_et_non_des_noms(decor):
    organisation, _, amina, bruno = decor
    _poser(organisation.id)
    from rest_framework.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        exiger_separation_des_taches(amina, amina.id)
    exiger_separation_des_taches(amina, bruno.id)
    exiger_separation_des_taches(amina, uuid.uuid4())
