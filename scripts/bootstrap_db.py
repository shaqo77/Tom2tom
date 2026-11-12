"""Amorce le cluster avant la première migration.

Exécute infra/sql/00_bootstrap_roles.sql avec le rôle PROPRIÉTAIRE, puis
aligne le mot de passe du rôle applicatif sur celui déclaré dans
DATABASE_URL. Le fichier .env reste ainsi la seule source de vérité : on ne
saisit pas un mot de passe à deux endroits, donc on ne les désaccorde pas.

    scripts/bootstrap_db.sh

Rejouable sans dommage.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psycopg
from psycopg import sql

RACINE = Path(__file__).resolve().parent.parent
SQL_AMORCAGE = RACINE / "infra" / "sql" / "00_bootstrap_roles.sql"


def lire_env(chemin: Path) -> dict[str, str]:
    """Lit backend/.env, puis laisse l'environnement avoir le dernier mot.

    C'est l'ordre de django-environ : en intégration continue comme en
    production, les secrets viennent de l'environnement et aucun fichier
    n'a besoin d'exister.
    """
    valeurs: dict[str, str] = {}
    if chemin.exists():
        for ligne in chemin.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, _, valeur = ligne.partition("=")
            valeurs[cle.strip()] = valeur.strip()
    for cle in ("DATABASE_URL", "DATABASE_OWNER_URL"):
        if os.environ.get(cle):
            valeurs[cle] = os.environ[cle]
    return valeurs


def identifiants(url: str) -> tuple[str, str]:
    """Retourne (rôle, mot de passe) d'une URL de connexion."""
    parties = urlsplit(url)
    return unquote(parties.username or ""), unquote(parties.password or "")


def main() -> int:
    env = lire_env(RACINE / "backend" / ".env")
    url_proprio = env.get("DATABASE_OWNER_URL")
    url_app = env.get("DATABASE_URL")
    if not url_proprio or not url_app:
        print(
            "DATABASE_URL et DATABASE_OWNER_URL doivent être définis dans backend/.env"
        )
        return 1

    role_app, mdp_app = identifiants(url_app)
    if not role_app or not mdp_app:
        print("DATABASE_URL doit porter un rôle et un mot de passe.")
        return 1
    # Sur un service mutualisé, le rôle est préfixé par la référence du projet
    # (« sigf_app.abcdef »). Le rôle PostgreSQL réel est la partie de gauche.
    role_app = role_app.split(".", 1)[0]

    with psycopg.connect(url_proprio, connect_timeout=15, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_user, current_database()")
            proprio, base = cur.fetchone()
            print(f"Amorçage de {base} avec le rôle {proprio}.")

        conn.execute(SQL_AMORCAGE.read_text(encoding="utf-8"))
        conn.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(role_app), sql.Literal(mdp_app)
            )
        )
        print(f"Schéma « sigf » et rôle « {role_app} » prêts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
