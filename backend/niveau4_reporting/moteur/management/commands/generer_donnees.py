"""Génère un jeu d'écritures factice mais ÉQUILIBRÉ. Voir L0-T01 et L3-T01.

Depuis L3-T01, ce sont de vraies pièces comptabilisées (une charge au débit, la trésorerie
au crédit), créées dans le grand livre définitif avec leurs comptes, axes, exercices et
journal. Le moteur les lit par la vue `moteur_ligneecriture`.

Le référentiel des devises doit être présent (il est livré par migration).
"""

import datetime
import random
import uuid
from decimal import Decimal
from types import SimpleNamespace

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from core.i18n import msg
from niveau1_socle.comptabilite.models import Ecriture, Journal, LigneEcriture
from niveau1_socle.exercices.models import Exercice
from niveau1_socle.exercices.services import creer_exercice
from niveau1_socle.referentiels.models import Compte, Devise, PlanDimension, ValeurDimension

ORGS = [
    uuid.UUID("11111111-1111-1111-1111-111111111111"),
    uuid.UUID("22222222-2222-2222-2222-222222222222"),
]
PROJETS = {
    ORGS[0]: [uuid.UUID(f"aaaaaaaa-0000-0000-0000-00000000000{i}") for i in (1, 2)],
    ORGS[1]: [uuid.UUID(f"bbbbbbbb-0000-0000-0000-00000000000{i}") for i in (1,)],
}
COMPTES_CHARGE = ["6011", "6021", "6231", "6281", "6411", "6511"]
COMPTES_TRESO = ["5211", "5311"]
DIM1 = ["COMP-A", "COMP-B", "COMP-C", "COMP-D", "COMP-E"]
DIM2 = ["ACT-01", "ACT-02", "ACT-03"]
ACCORDS = ["IDA-6789", "FIDA-2201"]
CATEGORIES = ["CAT-1", "CAT-2", "CAT-3"]
SITES = ["SIEGE", "REG-N", "REG-S"]
DEVISES = ["DJF", "USD"]
EXERCICES = [2024, 2025, 2026]
_ESPACE = uuid.UUID("0b1ec7a5-0000-4000-8000-00000000f00d")  # même espace que tests/outils.py


def _id_objet(nom: str) -> uuid.UUID:
    """UUID stable d'un accord, d'une catégorie ou d'un site, en attendant leur référentiel (L4)."""
    return uuid.uuid5(_ESPACE, nom)


class Command(BaseCommand):
    help = "Génère des écritures comptabilisées de test, équilibrées par pièce."

    def add_arguments(self, parser):
        parser.add_argument("--lignes", type=int, default=200_000)
        parser.add_argument(
            "--organisation",
            choices=("A", "B"),
            help="Génère toutes les lignes dans une seule organisation (benchmark L0).",
        )
        parser.add_argument(
            "--projet",
            type=int,
            choices=(1, 2),
            help="Génère toutes les lignes dans le projet numéroté 1 ou 2.",
        )

    def handle(self, *args, **opts):
        random.seed(1789)
        cible = opts["lignes"]
        if cible < 2 or cible % 2:
            raise CommandError(msg("generer_donnees.lignes_doit_etre_nombre_pair"))
        if not Devise.objects.exists():
            raise CommandError(msg("generer_donnees.referentiel_devises_vide_appliquez_migrations"))
        organisations = ORGS
        if opts["organisation"]:
            organisations = [ORGS[0] if opts["organisation"] == "A" else ORGS[1]]
        projet = opts["projet"]
        if projet and any(projet > len(PROJETS[org]) for org in organisations):
            raise CommandError(msg("generer_donnees.projet_demande_existe_organisation_choisie"))

        # Les écritures comptabilisées sont immuables (L3-T03) : on ne les purge pas, même ici.
        # Pour repartir de zéro, le propriétaire de la base exécute :
        #   TRUNCATE comptabilite_ligneecriture, comptabilite_ecriture CASCADE;
        for org in organisations:
            with connection.cursor() as cur:
                cur.execute("SET app.org_id = %s", [str(org)])
            projets = [PROJETS[org][projet - 1]] if projet else PROJETS[org]
            if Ecriture.objects.filter(project_id__in=projets).exists():
                raise CommandError(
                    msg("generer_donnees.ecritures_existent_deja_immuables_repartir")
                )

        # L'isolation est ACTIVE : on insère organisation par organisation,
        # après avoir posé app.org_id. Une ligne portant un autre org_id
        # serait refusée par la politique WITH CHECK — c'est voulu.
        par_org = cible // len(organisations)
        total = 0
        for org in organisations:
            with connection.cursor() as cur:
                cur.execute("SET app.org_id = %s", [str(org)])
            total += self._generer_pour(org, par_org, projet)

        self._verifier(total, organisations)

    def _preparer(self, org, projets):
        """Comptes, axes, exercices et journal dont les pièces ont besoin."""
        comptes = {}
        for code in COMPTES_CHARGE + COMPTES_TRESO:
            comptes[code], _ = Compte.objects.get_or_create(
                org_id=org,
                code=code,
                defaults={
                    "label": {"fr": f"Compte {code}", "en": f"Account {code}"},
                    "classe": int(code[0]),
                    "sens_normal": "debit",
                },
            )
        axes = {}
        for emplacement, valeurs in ((1, DIM1), (2, DIM2), (3, SITES)):
            plan, _ = PlanDimension.objects.get_or_create(
                org_id=org,
                kind="gestion",
                slot=emplacement,
                defaults={"code": f"AXE{emplacement}", "label": {"fr": f"Axe {emplacement}"}},
            )
            for code in valeurs:
                axes[(emplacement, code)], _ = ValeurDimension.objects.get_or_create(
                    org_id=org, plan=plan, code=code, defaults={"label": {"fr": code}}
                )
        journal, _ = Journal.objects.get_or_create(
            org_id=org, code="OD", defaults={"label": {"fr": "Opérations diverses"}}
        )
        periodes = {}
        for projet_id in projets:
            for annee in EXERCICES:
                exercice = Exercice.objects.filter(project_id=projet_id, annee=annee).first()
                if exercice is None:
                    exercice = creer_exercice(
                        SimpleNamespace(org_id=org, id=projet_id), annee, utilisateur=None
                    )
                for periode in exercice.periodes.all():
                    periodes[(projet_id, annee, periode.numero)] = (exercice, periode)
        return comptes, axes, journal, periodes

    def _generer_pour(self, org, cible, projet=None) -> int:
        projets = [PROJETS[org][projet - 1]] if projet else PROJETS[org]
        comptes, axes, journal, periodes = self._preparer(org, projets)
        ecritures, lignes, n = [], [], 0
        while n < cible:
            projet_id = projets[0] if projet else random.choice(projets)
            annee = random.choice(EXERCICES)
            numero_periode = random.randint(1, 12)
            exercice, periode = periodes[(projet_id, annee, numero_periode)]
            devise = random.choice(DEVISES)
            taux = Decimal("1") if devise == "DJF" else Decimal("177.721")
            montant = Decimal(random.randint(100, 5_000_000)) / 100
            ecriture = Ecriture(
                id=uuid.uuid4(),
                org_id=org,
                project_id=projet_id,
                exercice=exercice,
                periode=periode,
                journal=journal,
                accounting_date=datetime.date(
                    annee, periode.date_debut.month, random.randint(1, 28)
                ),
                label="Pièce générée",
                status="draft",
                currency_id=devise,
                fx_rate=taux,
                origin="import",
            )
            ecritures.append(ecriture)
            commun = dict(
                org_id=org,
                project_id=projet_id,
                entry=ecriture,
                dim1=axes[(1, random.choice(DIM1))],
                dim2=axes[(2, random.choice(DIM2))],
                dim3=axes[(3, random.choice(SITES))],
                agreement_id=_id_objet(random.choice(ACCORDS)),
                category_id=_id_objet(random.choice(CATEGORIES)),
                site_id=_id_objet(random.choice(SITES)),
                currency_id=devise,
                fx_rate=taux,
            )
            # Une paire équilibrée : charge au débit, trésorerie au crédit.
            lignes.append(
                LigneEcriture(
                    line_no=1,
                    account=comptes[random.choice(COMPTES_CHARGE)],
                    debit=montant,
                    credit=Decimal(0),
                    **commun,
                )
            )
            lignes.append(
                LigneEcriture(
                    line_no=2,
                    account=comptes[random.choice(COMPTES_TRESO)],
                    debit=Decimal(0),
                    credit=montant,
                    **commun,
                )
            )
            n += 2
            if len(ecritures) >= 5_000:
                self._inserer(ecritures, lignes)
                ecritures, lignes = [], []
                self.stdout.write(f"  {org.hex[:4]}… {n:>7} lignes")
        if ecritures:
            self._inserer(ecritures, lignes)
        return n

    @staticmethod
    def _inserer(ecritures, lignes):
        """Brouillons, puis lignes, puis comptabilisation : une écriture comptabilisée n'accepte
        plus de ligne (L3-T03). Le numéro est attribué par la base à la comptabilisation (L3-T04).
        Le tout dans une transaction : l'équilibre est vérifié au COMMIT."""
        with transaction.atomic():
            Ecriture.objects.bulk_create(ecritures)
            LigneEcriture.objects.bulk_create(lignes)
            maintenant = timezone.now()
            for ecriture in ecritures:
                ecriture.status = "posted"
                ecriture.posted_at = maintenant
                ecriture.posted_by = uuid.UUID(int=0)
            Ecriture.objects.bulk_update(
                ecritures, ["status", "posted_at", "posted_by"], batch_size=1000
            )

    def _verifier(self, n, organisations=ORGS):
        resultats = []
        for org in organisations:
            with connection.cursor() as cur:
                cur.execute("SET app.org_id = %s", [str(org)])
                cur.execute(
                    "SELECT count(*), COALESCE(SUM(debit) - SUM(credit), 0) "
                    "FROM moteur_ligneecriture"
                )
                resultats.append(cur.fetchone())

        details = "\n".join(
            f"  Organisation {chr(65 + ORGS.index(org))} : {resultat[0]} lignes visibles, "
            f"écart débit-crédit = {resultat[1]}"
            for org, resultat in zip(organisations, resultats, strict=True)
        )
        self.stdout.write(self.style.SUCCESS(f"\n{n} lignes générées.\n{details}"))
        assert all(ecart == 0 for _, ecart in resultats), "JEU DE DONNÉES DÉSÉQUILIBRÉ"
