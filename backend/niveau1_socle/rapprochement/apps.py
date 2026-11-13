from django.apps import AppConfig


class RapprochementConfig(AppConfig):
    name = "niveau1_socle.rapprochement"
    label = "rapprochement"

    def ready(self) -> None:
        # Branche le contrôle « mouvements non rapprochés » sur la clôture des périodes (L3-T08).
        from niveau1_socle.exercices import services

        from .cloture import CONTROLES_DE_CLOTURE

        for controle in CONTROLES_DE_CLOTURE:
            if controle not in services.VERIFICATIONS_DE_CLOTURE:
                services.VERIFICATIONS_DE_CLOTURE.append(controle)
