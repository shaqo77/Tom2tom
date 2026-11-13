"""Reconstruit les soldes budgétaires depuis les écritures et les engagements. Voir L4-T02."""

from django.core.management.base import BaseCommand
from django.db import connection

from niveau1_socle.budget.soldes import recalculer_soldes


class Command(BaseCommand):
    help = "Reconstruit tous les soldes budgétaires ; liste ce qui avait dérivé."

    def add_arguments(self, parser):
        parser.add_argument("--organisation", required=True, help="UUID de l'organisation")
        parser.add_argument("--projet", help="UUID d'un projet (par défaut : tous)")

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [options["organisation"]])
        corriges = recalculer_soldes(options["organisation"], options["projet"])
        self.stdout.write(f"{len(corriges)} solde(s) corrigé(s).")
