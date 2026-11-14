from django.apps import AppConfig


class ControlesConfig(AppConfig):
    name = "niveau4_reporting.controles"
    label = "controles"

    def ready(self) -> None:
        # Un contrôle actif doit avoir son exigence source : on le branche sur la règle de L5-T03.
        from .sources import brancher_les_controles

        brancher_les_controles()
