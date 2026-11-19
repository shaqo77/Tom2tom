"""Tâche quotidienne : les échéances imminentes, en retard ou à escalader. Voir L6-T06.

À lancer chaque jour (cron) ; sort une ligne par alerte et un code de sortie 2 s'il y a une
ESCALADE, pour que l'ordonnanceur la fasse remonter. Elle ne notifie personne par elle-même.
"""

import datetime

from django.core.management.base import BaseCommand
from django.db import connection

from niveau3_config.services.calendrier import alertes_du_jour


class Command(BaseCommand):
    help = "Liste les échéances imminentes, en retard et à escalader d'un projet."

    def add_arguments(self, parser):
        parser.add_argument("--organisation", required=True, help="UUID de l'organisation")
        parser.add_argument("--projet", required=True, help="UUID du projet")
        parser.add_argument("--date", help="AAAA-MM-JJ (par défaut aujourd'hui)")

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [options["organisation"]])
        jour = (
            datetime.date.fromisoformat(options["date"])
            if options["date"]
            else datetime.date.today()
        )
        alertes = alertes_du_jour(project_id=options["projet"], jour=jour)
        for echeance, niveau in alertes:
            self.stdout.write(
                f"{niveau.upper()} {echeance.exigence.code} "
                f"période {echeance.periode_fin.isoformat()} "
                f"échéance {echeance.date_echeance.isoformat()}"
            )
        self.stdout.write(f"{len(alertes)} alerte(s) au {jour.isoformat()}")
        if any(niveau == "escalade" for _, niveau in alertes):
            raise SystemExit(2)
