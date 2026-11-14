"""Charge un profil de bailleur livré (catalogue JSON) pour une organisation. Voir L5-T06."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from niveau2_profils.services.catalogue import charger_profil, profils_livres


class Command(BaseCommand):
    help = "Charge un profil de bailleur livré, en brouillon (ou publié avec --publier)."

    def add_arguments(self, parser):
        parser.add_argument("profil", choices=profils_livres())
        parser.add_argument("--organisation", required=True, help="UUID de l'organisation")
        parser.add_argument("--utilisateur", required=True, help="Nom de l'utilisateur habilité")
        parser.add_argument("--publier", action="store_true")

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [options["organisation"]])
        try:
            utilisateur = get_user_model().objects.get(
                username=options["utilisateur"], org_id=options["organisation"]
            )
        except get_user_model().DoesNotExist as erreur:
            raise CommandError("Utilisateur introuvable dans cette organisation") from erreur
        profil = charger_profil(
            utilisateur=utilisateur, nom=options["profil"], publier=options["publier"]
        )
        self.stdout.write(f"{profil} ({profil.status}) : {profil.elements.count()} éléments")
