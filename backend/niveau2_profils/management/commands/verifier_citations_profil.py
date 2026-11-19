"""Vérifie les citations d'un profil livré contre les PDF du bailleur (reconnus par SHA-256)."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.i18n import msg
from niveau2_profils.services.catalogue import lire_profil_livre, profils_livres
from niveau2_profils.services.citations import verifier_citations


class Command(BaseCommand):
    help = "Cherche chaque citation du profil, à sa page, dans le document du bailleur."

    def add_arguments(self, parser):
        parser.add_argument("profil", choices=profils_livres())
        parser.add_argument("--dossier", required=True, help="Dossier contenant les PDF")
        parser.add_argument(
            "--tolerer-absents",
            action="store_true",
            help="Ne pas échouer pour un document absent du dossier (citations non vérifiées).",
        )

    def handle(self, *args, **options):
        dossier = Path(options["dossier"])
        if not dossier.is_dir():
            raise CommandError(msg("citations_profil.dossier_introuvable", dossier=str(dossier)))
        resultat = verifier_citations(lire_profil_livre(options["profil"]), dossier)
        for code, page, extrait in resultat.echecs:
            self.stderr.write(f"ECHEC {code} p.{page} : {extrait[:80]}")
        for code, source in resultat.non_verifiables:
            self.stderr.write(f"NON VERIFIABLE {code} ({source})")
        self.stdout.write(f"{resultat.verifiees} citation(s) vérifiée(s)")
        if resultat.echecs or (resultat.non_verifiables and not options["tolerer_absents"]):
            raise CommandError(
                msg(
                    "citations_profil.verification_echouee",
                    echecs=len(resultat.echecs),
                    absentes=len(resultat.non_verifiables),
                )
            )
