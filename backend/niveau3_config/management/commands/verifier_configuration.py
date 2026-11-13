"""Signale les objets de configuration actifs sans exigence source. Voir L5-T03.

Sort en erreur (code 1) s'il y en a : c'est ce code de sortie que l'ordonnanceur ou la chaîne
d'intégration transforme en alerte. Par organisation, car la RLS impose un périmètre.
"""

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from niveau3_config.services.rattachement import detecter_configuration_orpheline


class Command(BaseCommand):
    help = "Liste les objets de configuration actifs sans exigence source ; échoue s'il y en a."

    def add_arguments(self, parser):
        parser.add_argument("--organisation", required=True, help="UUID de l'organisation")
        parser.add_argument("--projet", required=True, help="UUID du projet")
        parser.add_argument("--date", help="AAAA-MM-JJ (par défaut aujourd'hui)")

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [options["organisation"]])
        date = datetime.date.fromisoformat(options["date"]) if options["date"] else None
        orphelins = detecter_configuration_orpheline(options["projet"], date)
        if orphelins:
            for o in orphelins:
                self.stderr.write(f"{o.target_type} {o.libelle} ({o.target_id}) : {o.raison}")
            raise CommandError(f"{len(orphelins)} objet(s) de configuration sans exigence source")
        self.stdout.write("Toute la configuration active a son exigence source.")
