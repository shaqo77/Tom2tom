"""Réglages pour les MIGRATIONS uniquement.

Les migrations tournent avec le rôle propriétaire (sigf_owner).
L'application, elle, tourne avec sigf_app, qui n'a aucun droit de
création et subit les politiques d'isolation.

    python manage.py migrate --settings=config.settings.migrate
"""

from .base import *  # noqa: F403
from .base import configurer_base

DATABASES = {"default": configurer_base("DATABASE_OWNER_URL")}

# Le propriétaire possède BYPASSRLS par construction : c'est ce qui lui
# permet de migrer. Le contrôle de démarrage viserait donc juste, mais à
# tort — il ne s'adresse qu'au rôle qui sert les requêtes.
VERIFIER_ROLE_APPLICATIF = False
