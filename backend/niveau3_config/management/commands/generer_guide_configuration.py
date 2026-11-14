"""Écrit le guide de configuration d'un projet (PDF) à une date. Voir L5-T07."""

import datetime
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from niveau3_config.services.guide import generer_guide


class Command(BaseCommand):
    help = "Génère le guide de configuration (PDF) d'un projet, à la date voulue."

    def add_arguments(self, parser):
        parser.add_argument("--organisation", required=True, help="UUID de l'organisation")
        parser.add_argument("--projet", required=True, help="UUID du projet")
        parser.add_argument("--utilisateur", required=True, help="Nom de l'utilisateur")
        parser.add_argument("--date", help="AAAA-MM-JJ (par défaut aujourd'hui)")
        parser.add_argument("--sortie", required=True, help="Chemin du fichier PDF à écrire")

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [options["organisation"]])
        User = get_user_model()
        try:
            utilisateur = User.objects.get(
                username=options["utilisateur"], org_id=options["organisation"]
            )
        except User.DoesNotExist as erreur:
            raise CommandError("Utilisateur introuvable dans cette organisation") from erreur
        date = (
            datetime.date.fromisoformat(options["date"])
            if options["date"]
            else datetime.date.today()
        )
        contenu = generer_guide(utilisateur=utilisateur, project_id=options["projet"], date=date)
        Path(options["sortie"]).write_bytes(contenu)
        self.stdout.write(f"Guide écrit : {options['sortie']} ({len(contenu)} octets)")
