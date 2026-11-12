import os

from django.core.asgi import get_asgi_application
from django.core.management import call_command

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
application = get_asgi_application()

# Seul « runserver » exécute les contrôles système avant de servir ; un
# serveur ASGI de production, lui, importe ce module et c'est tout. Sans cet
# appel, le contrôle du rôle de connexion (core/checks.py) ne protégerait
# que le poste de développement. Une anomalie lève SystemCheckError : le
# processus ne démarre pas, et c'est voulu.
call_command("check")
