from django.apps import AppConfig
from django.core.checks import register


class CoreConfig(AppConfig):
    name = "core"
    label = "core"

    def ready(self):
        # Volontairement SANS le tag « database » : Django n'exécute alors
        # un contrôle ainsi tagué que sur demande (« check --database »).
        # Celui-ci doit tourner à CHAQUE démarrage et à chaque « check ».
        from .checks import verifier_role_applicatif

        register(verifier_role_applicatif)
