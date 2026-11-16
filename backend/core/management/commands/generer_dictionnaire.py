"""Écrit le dictionnaire de données (Markdown) depuis les modèles. Voir L8-T04."""

from pathlib import Path

from django.core.management.base import BaseCommand

from core.dictionnaire import dictionnaire, rendre_markdown

PUBLIE = Path(__file__).resolve().parents[4] / "DICTIONNAIRE_DE_DONNEES.md"


class Command(BaseCommand):
    help = "Génère le dictionnaire de données publié (DICTIONNAIRE_DE_DONNEES.md)."

    def add_arguments(self, parser):
        parser.add_argument("--sortie", default=str(PUBLIE), help="Fichier à écrire")

    def handle(self, *args, **options):
        texte = rendre_markdown(dictionnaire())
        Path(options["sortie"]).write_text(texte, encoding="utf-8")
        self.stdout.write(f"Dictionnaire écrit : {options['sortie']} ({len(texte)} caractères)")
