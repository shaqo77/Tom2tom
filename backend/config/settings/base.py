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

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "core",
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

DATABASES = {"default": env.db("DATABASE_URL")}
# Chaque requête HTTP est UNE transaction : « SET LOCAL » ne vit pas au-delà.
DATABASES["default"]["ATOMIC_REQUESTS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
LANGUAGE_CODE = "fr"
LANGUAGES = [("fr", "Français"), ("en", "English"), ("ar", "العربية")]
STATIC_URL = "static/"
