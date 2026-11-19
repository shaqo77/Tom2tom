"""Le middleware pose-t-il vraiment l'organisation ? Voir §B.4 et règle n°4.

Ces tests tournent en « transaction=True », donc SANS transaction
enveloppante : c'est la condition de production. Sous le mode par défaut,
pytest-django ouvre une transaction autour de chaque test, qui ferait
survivre un SET LOCAL mal placé — et masquerait exactement le défaut que
ces tests surveillent.
"""

import uuid

import pytest
from django.db import connection, transaction
from django.http import HttpResponse
from django.test import RequestFactory

from core.middleware import OrganisationScopeMiddleware

pytestmark = pytest.mark.django_db(transaction=True)


class _Utilisateur:
    """Le strict minimum que le middleware lit sur request.user."""

    def __init__(self, org_id=None):
        self.org_id = org_id


def _requete(org_id):
    requete = RequestFactory().get("/")
    requete.user = _Utilisateur(org_id)
    return requete


def _vue_qui_observe(sql):
    """Une vue qui interroge la base dans SA propre transaction.

    ATOMIC_REQUESTS ouvre une transaction autour de la vue : on la reproduit
    ici, car c'est à travers cette imbrication que le périmètre doit rester
    visible.
    """
    vu = {}

    def vue(requete):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(sql)
            vu["valeur"] = cur.fetchone()[0]
        return HttpResponse()

    return vue, vu


def _inserer(org_id, nb):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])
        for rang in range(nb):
            cur.execute(
                """INSERT INTO comptabilite_journal
                   (id, org_id, code, label, actif, created_at, updated_at)
                   VALUES (%s,%s,%s,'{"fr": "Journal"}',true,now(),now())""",
                [uuid.uuid4(), org_id, f"J{rang}"],
            )
        # Sans cela, le périmètre posé pour l'insertion survivrait au test et
        # le middleware passerait pour efficace sans avoir rien fait.
        cur.execute("RESET app.org_id")


def test_lorganisation_atteint_la_transaction_de_la_vue(org_a):
    """ATOMIC_REQUESTS n'enveloppe que la vue : le périmètre doit l'atteindre."""
    vue, vu = _vue_qui_observe("SELECT current_setting('app.org_id', true)")
    OrganisationScopeMiddleware(vue)(_requete(org_a))
    assert vu["valeur"] == str(org_a), "app.org_id n'atteint pas la transaction de la vue"


def test_la_vue_ne_voit_que_les_lignes_de_son_organisation(org_a, org_b):
    _inserer(org_a, 3)
    _inserer(org_b, 5)
    vue, vu = _vue_qui_observe("SELECT count(*) FROM comptabilite_journal")
    OrganisationScopeMiddleware(vue)(_requete(org_a))
    assert vu["valeur"] == 3, "FUITE DE DONNÉES ENTRE ORGANISATIONS"


def test_le_perimetre_ne_survit_pas_a_la_requete(org_a):
    """Un SET simple contaminerait la requête suivante sur la même connexion."""
    OrganisationScopeMiddleware(lambda requete: HttpResponse())(_requete(org_a))
    with connection.cursor() as cur:
        cur.execute("SELECT current_setting('app.org_id', true)")
        reste = cur.fetchone()[0]
    assert not reste, "L'organisation survit à la requête : la suivante en hériterait"


def test_sans_organisation_la_vue_ne_voit_rien(org_a):
    """Utilisateur anonyme ou sans organisation : défaut sûr, pas défaut ouvert."""
    _inserer(org_a, 4)
    vue, vu = _vue_qui_observe("SELECT count(*) FROM comptabilite_journal")
    OrganisationScopeMiddleware(vue)(_requete(None))
    assert vu["valeur"] == 0
