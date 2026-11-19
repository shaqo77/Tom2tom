from django.apps import AppConfig


class ComptabiliteConfig(AppConfig):
    name = "niveau1_socle.comptabilite"
    label = "comptabilite"

    def ready(self) -> None:
        # Branche les contrôles de la comptabilité sur la clôture des périodes (L3-T08).
        from niveau1_socle.exercices import services

        from .cloture import CONTROLES_DE_CLOTURE

        for controle in CONTROLES_DE_CLOTURE:
            if controle not in services.VERIFICATIONS_DE_CLOTURE:
                services.VERIFICATIONS_DE_CLOTURE.append(controle)
