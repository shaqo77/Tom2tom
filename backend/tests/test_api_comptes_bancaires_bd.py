# ruff: noqa: F811, E501
"""L'API qui liste les comptes bancaires d'un projet (Lot 5, écran du compte spécial).

Sans elle, aucun écran ne peut choisir un compte : toutes les routes de trésorerie s'adressent à
l'identifiant d'un compte. Le numéro COMPLET n'en sort jamais : seul le numéro masqué.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from niveau1_socle.habilitations.models import Habilitation, Role
from tests.test_api_marches_bd import appeler
from tests.test_compte_special_bd import special  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def _liste(special, utilisateur="amina", suite=""):
    _, projet, profils, _, _, _ = special
    return appeler(profils[utilisateur], "get", f"/projets/{projet.id}/comptes-bancaires/{suite}")


def test_les_comptes_du_projet_se_listent_avec_leur_identifiant_et_un_numero_masque(special):
    _, _, _, accord, compte, _ = special
    r = _liste(special)
    assert r.status_code == 200, r.content
    (c,) = [x for x in r.json() if x["id"] == str(compte.id)]
    assert (c["code"], c["type"], c["devise"], c["accord"]) == (
        compte.code,
        compte.type,
        compte.devise_id,
        accord.numero,
    )
    assert c["numero_masque"] == compte.numero_masque and c["numero_masque"] != compte.numero


def test_le_numero_complet_ne_sort_jamais(special):
    _, _, _, _, compte, _ = special
    r = _liste(special)
    assert compte.numero not in r.content.decode()
    assert all("numero" not in x for x in r.json())


def test_la_liste_est_triee_par_code_et_pagine_a_la_demande(special):
    r = _liste(special)
    codes = [x["code"] for x in r.json()]
    assert codes == sorted(codes)
    page = _liste(special, suite="?limite=1")
    assert len(page.json()) == 1 and page["X-Total-Count"] == str(len(codes))


def test_sans_le_droit_de_consulter_la_liste_est_refusee(special):
    organisation, projet, profils, _, _, _ = special
    zoe = get_user_model().objects.create_user("zoe", password="x", org_id=organisation.id)
    r = appeler(zoe, "get", f"/projets/{projet.id}/comptes-bancaires/")
    assert r.status_code == 403 and set(r.json()) == {"code", "message"}


def test_un_projet_inconnu_est_introuvable(special):
    import uuid

    _, _, profils, _, _, _ = special
    r = appeler(profils["amina"], "get", f"/projets/{uuid.uuid4()}/comptes-bancaires/")
    assert r.status_code in (403, 404)


def test_les_comptes_d_un_autre_projet_ne_sont_pas_listes(special):
    from niveau1_socle.financements.models import CompteBancaire
    from tests.test_cycle_ecriture_bd import _creer_projet

    organisation, projet, profils, _, compte, _ = special
    autre = _creer_projet(organisation, "P2")
    role = Role.objects.create(
        org_id=organisation.id, code="LECT2", label={"fr": "lecture"}, operations=["consulter"]
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=profils["amina"].id, project_id=autre.id, role=role
    )
    r = appeler(profils["amina"], "get", f"/projets/{autre.id}/comptes-bancaires/")
    assert r.status_code == 200 and r.json() == []
    with connection.cursor() as cur:  # l'appel HTTP a remis l'organisation à zéro : on la repose
        cur.execute("SET app.org_id = %s", [str(organisation.id)])
    assert CompteBancaire.objects.filter(pk=compte.pk).exists()  # le compte existe, mais ailleurs
