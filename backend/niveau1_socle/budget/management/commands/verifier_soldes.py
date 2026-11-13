"""Tâche nocturne : compare les soldes budgétaires incrémentaux au calcul complet.

À planifier chaque nuit, une fois par organisation. Sort en erreur (code 1) et écrit au journal
d'audit en cas de divergence : c'est ce code de sortie que l'ordonnanceur transforme en alerte.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from niveau1_socle.budget.soldes import verifier_soldes


class Command(BaseCommand):
    help = "Compare les soldes budgétaires incrémentaux au recalcul complet ; échoue si écart."

    def add_arguments(self, parser):
        parser.add_argument("--organisation", required=True, help="UUID de l'organisation")
        parser.add_argument("--projet", help="UUID d'un projet (par défaut : tous)")

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [options["organisation"]])
        divergences = verifier_soldes(options["organisation"], options["projet"])
        if divergences:
            for d in divergences[:20]:
                self.stderr.write(
                    f"ligne {d.ligne_id} : consommé {d.consomme_incremental} ≠ "
                    f"{d.consomme_calcule}, engagé {d.engage_incremental} ≠ {d.engage_calcule}"
                )
            raise CommandError(f"{len(divergences)} solde(s) budgétaire(s) divergent(s)")
        self.stdout.write("Soldes budgétaires cohérents.")
