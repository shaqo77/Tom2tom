"""Réglages communs. Voir 03_GUIDE_DEMARRAGE.md, partie A.6."""

from decimal import ROUND_HALF_UP, DefaultContext, setcontext
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# --- Règle monétaire globale : arrondi explicite, jamais implicite ---
DefaultContext.prec = 28
DefaultContext.rounding = ROUND_HALF_UP
setcontext(DefaultContext)

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

AUTH_USER_MODEL = "organisations.Utilisateur"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "core",
    "niveau1_socle.organisations",
    "niveau3_config",
    "niveau4_reporting.mapping",
    "niveau4_reporting.moteur",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.OrganisationScopeMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

# Le schéma applicatif ne vit pas dans « public ». Voir infra/sql/00_bootstrap_roles.sql :
# sur une instance Supabase, « public » est servi au rôle anonyme par l'API REST.
DB_SCHEMA = env("DB_SCHEMA", default="")
DB_SSLMODE = env("DB_SSLMODE", default="")


def configurer_base(variable: str) -> dict:
    """Lit une URL de connexion et y applique les réglages communs."""
    reglages = env.db(variable)
    # Chaque requête HTTP est UNE transaction : « SET LOCAL » ne vit pas au-delà.
    reglages["ATOMIC_REQUESTS"] = True
    options = reglages.setdefault("OPTIONS", {})
    if DB_SSLMODE:
        options["sslmode"] = DB_SSLMODE
    if DB_SCHEMA:
        # Posé à la connexion, donc valable pour toute requête, y compris
        # celles que Django émet avant tout middleware.
        options["options"] = f"-c search_path={DB_SCHEMA},public"
    return reglages


DATABASES = {"default": configurer_base("DATABASE_URL")}

# Le rôle qui sert les requêtes doit SUBIR l'isolation, jamais la contourner.
# Contrôlé au démarrage par core/checks.py, parce qu'une erreur ici ouvre
# toutes les organisations les unes aux autres sans rien casser de visible.
ROLE_APPLICATIF = env("DB_ROLE_APPLICATIF", default="sigf_app")
VERIFIER_ROLE_APPLICATIF = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
LANGUAGE_CODE = "fr"
LANGUAGES = [("fr", "Français"), ("en", "English"), ("ar", "العربية")]
STATIC_URL = "static/"
