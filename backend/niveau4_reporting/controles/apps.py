from django.apps import AppConfig


class ControlesConfig(AppConfig):
    name = "niveau4_reporting.controles"
    label = "controles"

    def ready(self) -> None:
        # Un contrôle actif doit avoir son exigence source : on le branche sur la règle de L5-T03.
        from .sources import brancher_les_controles

        brancher_les_controles()
        # Les contrôles actifs s'exécutent à la validation des écritures (L11-A4). Le grand livre ne
        # connaît pas ce module : il expose un point d'accroche, et c'est ici qu'on s'y branche.
        from niveau1_socle.comptabilite.services import enregistrer_controle_a_la_validation

        from .depenses import controler_ecriture

        enregistrer_controle_a_la_validation(controler_ecriture)
