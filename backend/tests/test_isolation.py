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


def test_deplacer_une_ligne_vers_une_autre_organisation_est_refuse(org_a, org_b):
    """UPDATE ... SET org_id : la clause WITH CHECK doit refuser le transfert.

    Sans elle, un utilisateur de l'organisation A pourrait « donner » une ligne
    à B, ou y faire disparaître une ligne de son propre périmètre.
    """
    from django.db.utils import ProgrammingError

    _inserer(org_a, 1)
    _poser(org_a)
    with pytest.raises(ProgrammingError), connection.cursor() as cur:
        cur.execute("UPDATE moteur_ligneecriture SET org_id = %s", [str(org_b)])
    # La ligne n'a pas bougé : A la voit toujours, B ne la voit pas.
    assert _compter() == 1
    _poser(org_b)
    assert _compter() == 0


def test_toute_politique_a_une_clause_with_check():
    """Garde-fou méta : sans WITH CHECK, un UPDATE de org_id passerait.

    Même résolution du schéma effectif que le test précédent.
    """
    with connection.cursor() as cur:
        cur.execute(
            """SELECT p.tablename, p.policyname FROM pg_policies p
               WHERE p.schemaname = (SELECT n.nspname FROM pg_class c
                                      JOIN pg_namespace n ON n.oid = c.relnamespace
                                      WHERE c.oid = to_regclass('core_auditlog'))
                 AND p.cmd IN ('ALL', 'UPDATE', 'INSERT')
                 AND p.with_check IS NULL"""
        )
        sans_with_check = cur.fetchall()
    assert not sans_with_check, f"Politiques sans WITH CHECK : {sans_with_check}"


def test_sans_org_id_pose_rien_nest_visible(org_a):
    """Une requête hors contexte d'organisation ne voit rien. Défaut sûr."""
    _inserer(org_a, 4)
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")
        cur.execute("SELECT count(*) FROM moteur_ligneecriture")
        assert cur.fetchone()[0] == 0


def test_toute_table_avec_org_id_a_sa_politique():
    """Empêche qu'une nouvelle table soit créée sans isolation. Voir L1-T02.

    Le schéma inspecté est celui où Django a RÉELLEMENT posé ses tables,
    résolu par le chemin de recherche — « public » en intégration continue,
    « sigf » en exploitation (DB_SCHEMA). Le coder en dur rendrait ce
    garde-fou muet dans l'environnement même qu'il doit protéger.
    """
    with connection.cursor() as cur:
        cur.execute(
            """SELECT c.relname FROM pg_class c
               JOIN pg_attribute a ON a.attrelid = c.oid
                                  AND a.attname = 'org_id'
                                  AND NOT a.attisdropped
               WHERE c.relkind IN ('r', 'p')
                 AND c.relnamespace = (SELECT relnamespace FROM pg_class
                                        WHERE oid = to_regclass('core_auditlog'))
                 AND NOT (c.relrowsecurity AND c.relforcerowsecurity)"""
        )
        manquantes = [r[0] for r in cur.fetchall()]
    assert not manquantes, f"Tables sans isolation forcée : {manquantes}"
