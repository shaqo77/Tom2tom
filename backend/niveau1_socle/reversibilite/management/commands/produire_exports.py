"""Tâche de fond : produit les exports demandés d'une organisation. Voir L8-T03.

À planifier (cron, ordonnanceur) : une exécution traite les exports `demandé` de l'organisation.
"""

from django.core.management.base import BaseCommand
from django.db import connection

from niveau1_socle.reversibilite.models import ExportOrganisation, StatutExport
from niveau1_socle.reversibilite.services import produire_export, recuperer_exports_bloques


class Command(BaseCommand):
    help = "Produit les exports complets demandés d'une organisation."

    def add_arguments(self, parser):
        parser.add_argument("--organisation", required=True, help="UUID de l'organisation")

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [options["organisation"]])
        recuperes = recuperer_exports_bloques()
        if recuperes:
            self.stdout.write(f"{recuperes} export(s) interrompu(s) passé(s) en échec")
        produits = 0
        for export in ExportOrganisation.objects.filter(statut=StatutExport.DEMANDE).order_by(
            "created_at"
        ):
            produire_export(export)
            produits += 1
        self.stdout.write(f"{produits} export(s) produit(s)")
