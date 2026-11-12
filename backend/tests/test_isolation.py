"""Isolation des organisations par Row-Level Security. Voir §B.4 et règle n°4."""

import datetime
import uuid

import pytest
from django.db import connection

pytestmark = pytest.mark.django_db(transaction=True)


def _inserer(org_id, nb=3):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])
        for _ in range(nb):
            cur.execute(
                """INSERT INTO moteur_ligneecriture
                   (id, org_id, project_id, fiscal_year, period, accounting_date,
                    compte, debit, credit, devise, taux, created_at, updated_at)
                   VALUES (%s,%s,%s,2026,1,%s,'6011',100,0,'DJF',1,now(),now())""",
                [uuid.uuid4(), org_id, uuid.uuid4(), datetime.date(2026, 1, 15)],
            )


def _compter():
    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM moteur_ligneecriture")
        return cur.fetchone()[0]


def _poser(org_id):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])


def test_une_organisation_ne_voit_pas_les_donnees_dune_autre(org_a, org_b):
    _inserer(org_a, 3)
    _inserer(org_b, 5)

    _poser(org_a)
    assert _compter() == 3, "FUITE DE DONNÉES ENTRE ORGANISATIONS"
    _poser(org_b)
    assert _compter() == 5, "FUITE DE DONNÉES ENTRE ORGANISATIONS"


def test_un_filtre_explicite_sur_une_autre_organisation_ne_rend_rien(org_a, org_b):
    """Même en demandant explicitement l'autre organisation, rien ne sort."""
    _inserer(org_a, 2)
    _inserer(org_b, 2)
    _poser(org_a)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM moteur_ligneecriture WHERE org_id = %s",
            [str(org_b)],
        )
        assert cur.fetchone()[0] == 0, "FUITE DE DONNÉES ENTRE ORGANISATIONS"


def test_inserer_pour_une_autre_organisation_est_refuse(org_a, org_b):
    """La politique WITH CHECK interdit d'écrire chez quelqu'un d'autre."""
    from django.db.utils import ProgrammingError

    _poser(org_a)
    with pytest.raises(ProgrammingError), connection.cursor() as cur:
        cur.execute(
            """INSERT INTO moteur_ligneecriture
               (id, org_id, project_id, fiscal_year, period, accounting_date,
                compte, debit, credit, devise, taux, created_at, updated_at)
               VALUES (%s,%s,%s,2026,1,%s,'6011',100,0,'DJF',1,now(),now())""",
            [uuid.uuid4(), org_b, uuid.uuid4(), datetime.date(2026, 1, 15)],
        )


def test_sans_org_id_pose_rien_nest_visible(org_a):
    """Une requête hors contexte d'organisation ne voit rien. Défaut sûr."""
    _inserer(org_a, 4)
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")
        cur.execute("SELECT count(*) FROM moteur_ligneecriture")
        assert cur.fetchone()[0] == 0


def test_toute_table_avec_org_id_a_sa_politique():
    """Empêche qu'une nouvelle table soit créée sans isolation. Voir L1-T02."""
    with connection.cursor() as cur:
        cur.execute(
            """SELECT c.relname FROM pg_class c
               JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'org_id'
               JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE c.relkind = 'r' AND n.nspname = 'public'
                 AND NOT (c.relrowsecurity AND c.relforcerowsecurity)"""
        )
        manquantes = [r[0] for r in cur.fetchall()]
    assert not manquantes, f"Tables sans isolation forcée : {manquantes}"
