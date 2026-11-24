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
    "niveau1_socle.habilitations",
    "niveau1_socle.exercices",
    "niveau1_socle.referentiels",
    "niveau1_socle.comptabilite",
    "niveau1_socle.budget",
    "niveau1_socle.financements",
    "niveau1_socle.decaissements",
    "niveau1_socle.avances",
    "niveau1_socle.rapprochement",
    "niveau1_socle.reprise",
    "niveau1_socle.reversibilite",
    "niveau1_socle.marches",
    "niveau1_socle.tresorerie",
    "niveau2_profils",
    "niveau3_config",
    "niveau4_reporting.mapping",
    "niveau4_reporting.moteur",
    "niveau4_reporting.controles",
    "niveau4_reporting.publication",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.LangueMiddleware",
    "core.middleware.OrganisationScopeMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# --- Sécurité : valeurs par défaut sûres, que la production durcit encore (prod.py) ---
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "core.csrf.refus_csrf"  # JSON pour l'API, page Django ailleurs
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # un corps de requête ne dépasse pas 10 Mo

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Un point d'accès sans authentification explicite est refusé, pas ouvert.
REST_FRAMEWORK = {
    # La session d'abord (CSRF contrôlé), puis le jeton d'API (`Authorization: Bearer`, sans CSRF).
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "niveau1_socle.organisations.jetons.AuthentificationJeton",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "core.api.gestionnaire_exceptions",
}

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
# Le français et l'anglais pour l'instant ; l'arabe viendra (il exige aussi une police de PDF).
LANGUAGES = [("fr", "Français"), ("en", "English")]
USE_I18N = True
STATIC_URL = "static/"
