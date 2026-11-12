"""Journal d'audit infalsifiable. Voir L1-T03 et règle n°2."""

import uuid

import pytest
from django.db import connection

from core.audit import journaliser, verifier_chaine

pytestmark = pytest.mark.django_db(transaction=True)


def _poser(org_id):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])


def test_la_chaine_est_intacte_apres_plusieurs_ecritures(org_a):
    _poser(org_a)
    acteur = uuid.uuid4()
    for i in range(50):
        journaliser(
            org_id=org_a,
            actor_id=acteur,
            action="post",
            object_type="Ecriture",
            object_id=uuid.uuid4(),
            after={"numero": i},
        )
    assert verifier_chaine(org_a) is None


def test_une_alteration_est_detectee(org_a):
    """Même un administrateur disposant des droits sur la base est détecté.

    C'est tout l'intérêt du chaînage par empreinte : il ne protège pas
    l'écriture (les droits s'en chargent), il rend l'altération VISIBLE.
    """
    _poser(org_a)
    acteur = uuid.uuid4()
    for i in range(10):
        journaliser(
            org_id=org_a,
            actor_id=acteur,
            action="post",
            object_type="Ecriture",
            object_id=uuid.uuid4(),
            after={"numero": i},
        )

    with connection.cursor() as cur:
        cur.execute(
            "SELECT id FROM core_auditlog WHERE org_id = %s ORDER BY id OFFSET 4 LIMIT 1",
            [str(org_a)],
        )
        cible = cur.fetchone()[0]
        # On se donne temporairement les droits : simulation d'un administrateur.
        cur.execute("SELECT current_user")
        utilisateur = cur.fetchone()[0]
        cur.execute(f'GRANT UPDATE ON core_auditlog TO "{utilisateur}"')
        try:
            cur.execute(
                "UPDATE core_auditlog SET after = %s WHERE id = %s",
                ['{"numero": 999}', cible],
            )
        finally:
            cur.execute(f'REVOKE UPDATE ON core_auditlog FROM "{utilisateur}"')

    assert verifier_chaine(org_a) == cible, "ALTÉRATION NON DÉTECTÉE"


def test_le_journal_est_en_ajout_seul(org_a):
    """Aucun rôle applicatif ne peut modifier une entrée déjà écrite."""
    from django.db.utils import ProgrammingError

    _poser(org_a)
    journaliser(org_id=org_a, actor_id=uuid.uuid4(), action="login", object_type="Utilisateur")
    with pytest.raises(ProgrammingError, match="permission denied"):
        with connection.cursor() as cur:
            cur.execute("UPDATE core_auditlog SET action = 'falsifie'")


def test_le_role_applicatif_ne_peut_pas_modifier_le_journal(org_a):
    """En production, sigf_app n'a ni UPDATE ni DELETE sur le journal."""
    _poser(org_a)
    journaliser(org_id=org_a, actor_id=uuid.uuid4(), action="login", object_type="Utilisateur")
    with connection.cursor() as cur:
        cur.execute("SELECT current_user")
        utilisateur = cur.fetchone()[0]
        cur.execute(
            "SELECT has_table_privilege(%s, 'core_auditlog', 'UPDATE'), "
            "       has_table_privilege(%s, 'core_auditlog', 'DELETE')",
            [utilisateur, utilisateur],
        )
        peut_modifier, peut_supprimer = cur.fetchone()
    if utilisateur == "sigf_app":
        assert not peut_modifier and not peut_supprimer, (
            "Le rôle applicatif peut modifier le journal d'audit"
        )
    else:
        pytest.skip(
            f"Tests exécutés comme « {utilisateur} », propriétaire des tables. "
            "Le retrait de droits vise sigf_app en exploitation."
        )
