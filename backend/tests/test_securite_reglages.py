"""Réglages de sécurité : le déploiement passe `check --deploy` sans avertissement."""

import importlib
import sys

import pytest
from django.conf import settings
from django.core.management import call_command


def test_les_protections_http_sont_actives():
    assert "django.middleware.csrf.CsrfViewMiddleware" in settings.MIDDLEWARE
    assert "django.middleware.clickjacking.XFrameOptionsMiddleware" in settings.MIDDLEWARE
    assert settings.X_FRAME_OPTIONS == "DENY"
    assert settings.SESSION_COOKIE_HTTPONLY is True


def test_un_point_d_acces_sans_authentification_explicite_est_refuse():
    cadre = settings.REST_FRAMEWORK
    assert cadre["DEFAULT_PERMISSION_CLASSES"] == ["rest_framework.permissions.IsAuthenticated"]


def test_les_mots_de_passe_courts_sont_refuses():
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        validate_password("court1")


def _charger_prod(monkeypatch, cle):
    monkeypatch.setenv("SECRET_KEY", cle)
    monkeypatch.setenv("ALLOWED_HOSTS", "sigf.exemple")
    for nom in ("config.settings.prod", "config.settings.base"):
        sys.modules.pop(nom, None)
    return importlib.import_module("config.settings.prod")


def test_la_production_refuse_une_cle_secrete_courte(monkeypatch):
    with pytest.raises(RuntimeError):
        _charger_prod(monkeypatch, "trop-courte")


def test_la_production_passe_check_deploy(monkeypatch, settings, capsys):
    prod = _charger_prod(monkeypatch, "k" * 20 + "Zx9!" * 10)
    for nom in dir(prod):
        if nom.isupper() and nom not in ("DATABASES", "SECRET_KEY_FALLBACKS"):
            setattr(settings, nom, getattr(prod, nom))
    call_command("check", "--deploy", "--tag", "security", "--fail-level", "WARNING")


@pytest.mark.parametrize(
    "nom", ["../../config/settings/base", "/etc/passwd", "banque_mondiale/../x"]
)
def test_un_nom_de_profil_ne_sort_jamais_du_catalogue(nom):
    from niveau2_profils.services.catalogue import lire_profil_livre

    with pytest.raises(FileNotFoundError):
        lire_profil_livre(nom)
