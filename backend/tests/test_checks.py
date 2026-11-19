"""Le contrôle de démarrage refuse-t-il un rôle qui contourne l'isolation ?

Le jugement est testé sur des faits fabriqués : un rôle BYPASSRLS ne peut pas
être créé depuis l'application, et c'est précisément ce qu'on lui demande.
La lecture, elle, est testée contre la vraie base.
"""

import pytest
from django.core.checks import Error, Warning
from django.core.checks.registry import registry
from django.db import connection
from django.test import override_settings

from core.checks import (
    ROLE_CONTOURNE,
    ROLE_INATTENDU,
    ROLE_INVERIFIABLE,
    juger,
    verifier_role_applicatif,
)


def test_un_role_bypassrls_est_une_erreur_bloquante():
    [anomalie] = juger("postgres", True, False, "sigf_app")
    assert isinstance(anomalie, Error)
    assert anomalie.id == ROLE_CONTOURNE
    assert "BYPASSRLS" in anomalie.msg
    assert "migrate" in anomalie.hint, "l'indice doit désigner la cause probable"


def test_un_superutilisateur_est_une_erreur_bloquante():
    """SUPERUSER contourne la RLS même sans BYPASSRLS explicite."""
    [anomalie] = juger("supabase_admin", False, True, "sigf_app")
    assert anomalie.id == ROLE_CONTOURNE
    assert "SUPERUSER" in anomalie.msg


def test_bypassrls_prime_sur_le_nom_attendu():
    """Un rôle qui porte le bon nom mais contourne l'isolation reste refusé."""
    [anomalie] = juger("sigf_app", True, False, "sigf_app")
    assert anomalie.id == ROLE_CONTOURNE


def test_le_role_attendu_sans_privilege_passe():
    assert juger("sigf_app", False, False, "sigf_app") == []


def test_un_role_inattendu_mais_soumis_a_la_rls_est_signale_sans_etre_une_faille():
    [anomalie] = juger("autre_role", False, False, "sigf_app")
    assert anomalie.id == ROLE_INATTENDU
    assert "BYPASSRLS" not in anomalie.msg


def test_le_controle_est_enregistre_au_demarrage():
    assert verifier_role_applicatif in registry.get_checks(include_deployment_checks=False)


@pytest.mark.django_db
def test_la_lecture_porte_sur_le_role_reellement_connecte():
    """Le contrôle lit current_user, pas la configuration."""
    with connection.cursor() as cur:
        cur.execute("SELECT current_user")
        reel = cur.fetchone()[0]
    # En se déclarant « attendu », le rôle réel ne doit pas être jugé inattendu.
    with override_settings(ROLE_APPLICATIF=reel):
        ids = {a.id for a in verifier_role_applicatif(None)}
    assert ROLE_INATTENDU not in ids
    # Et en déclarant un autre nom, il l'est : la lecture a bien eu lieu.
    with override_settings(ROLE_APPLICATIF="role_qui_n_existe_pas"):
        ids = {a.id for a in verifier_role_applicatif(None)}
    assert ids & {ROLE_INATTENDU, ROLE_CONTOURNE}


def test_le_controle_peut_etre_desactive_pour_les_migrations():
    with override_settings(VERIFIER_ROLE_APPLICATIF=False):
        assert verifier_role_applicatif(None) == []


def test_une_base_injoignable_est_un_avertissement_pas_une_erreur(monkeypatch):
    """Sinon « manage.py check » deviendrait impossible hors connexion."""
    from django.db import DatabaseError

    class _Curseur:
        def __enter__(self):
            raise DatabaseError("connexion refusée")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("core.checks.connection.cursor", lambda: _Curseur())
    [anomalie] = verifier_role_applicatif(None)
    assert isinstance(anomalie, Warning)
    assert anomalie.id == ROLE_INVERIFIABLE


def test_le_serveur_de_production_refuse_de_demarrer_avec_le_role_proprietaire():
    """Preuve de bout en bout, en vrai processus, par le point d'entrée ASGI.

    Sans cela, le contrôle ne tournerait que sous « manage.py » : uvicorn et
    gunicorn n'exécutent aucun contrôle système. Le sous-processus reçoit
    l'URL du propriétaire à la place de celle de l'application.
    """
    import os
    import subprocess
    import sys

    from django.conf import settings

    env = {**os.environ, "DATABASE_URL": os.environ["DATABASE_OWNER_URL"]}
    resultat = subprocess.run(
        [sys.executable, "-c", "import config.asgi"],
        cwd=settings.BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert resultat.returncode != 0, "le serveur a démarré avec un rôle qui contourne la RLS"
    assert ROLE_CONTOURNE in resultat.stderr
