"""Réglages pour les MIGRATIONS uniquement.

Les migrations tournent avec le rôle propriétaire (sigf_owner).
L'application, elle, tourne avec sigf_app, qui n'a aucun droit de
création et subit les politiques d'isolation.

    python manage.py migrate --settings=config.settings.migrate
"""

from .base import *  # noqa: F403
from .base import env

DATABASES = {"default": env.db("DATABASE_OWNER_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
