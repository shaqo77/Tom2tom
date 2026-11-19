from django.apps import AppConfig


class MoteurConfig(AppConfig):
    name = "niveau4_reporting.moteur"
    label = "moteur"

    def ready(self) -> None:
        # Déclare les sources externes livrées (registre fermé : voir `sources_externes`).
        from . import source_compte_designe  # noqa: F401
