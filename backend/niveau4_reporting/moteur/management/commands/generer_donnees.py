"""Génère un jeu de lignes d'écriture factice mais ÉQUILIBRÉ. Voir L0-T01."""

import datetime
import random
import uuid
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

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


class Command(BaseCommand):
    help = "Génère des lignes d'écriture de test, équilibrées par paire."

    def add_arguments(self, parser):
        parser.add_argument("--lignes", type=int, default=200_000)
        parser.add_argument("--purger", action="store_true")
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
            raise CommandError("--lignes doit être un nombre pair d'au moins 2")
        organisations = ORGS
        if opts["organisation"]:
            organisations = [ORGS[0] if opts["organisation"] == "A" else ORGS[1]]
        projet = opts["projet"]
        if projet and any(projet > len(PROJETS[org]) for org in organisations):
            raise CommandError("Le projet demandé n'existe pas pour l'organisation choisie.")

        if opts["purger"]:
            for org in organisations:
                with connection.cursor() as cur:
                    cur.execute("SET app.org_id = %s", [str(org)])
                    cur.execute("DELETE FROM moteur_ligneecriture")

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

    def _generer_pour(self, org, cible, projet=None) -> int:
        lignes, n = [], 0
        while n < cible:
            projet_id = PROJETS[org][projet - 1] if projet else random.choice(PROJETS[org])
            annee = random.choice(EXERCICES)
            periode = random.randint(1, 12)
            date = datetime.date(annee, periode, random.randint(1, 28))
            devise = random.choice(DEVISES)
            taux = Decimal("1") if devise == "DJF" else Decimal("177.721")
            montant = Decimal(random.randint(100, 5_000_000)) / 100
            commun = dict(
                org_id=org,
                project_id=projet_id,
                fiscal_year=annee,
                period=periode,
                accounting_date=date,
                dim1=random.choice(DIM1),
                dim2=random.choice(DIM2),
                dim3=random.choice(SITES),
                dim4=None,
                accord=random.choice(ACCORDS),
                categorie=random.choice(CATEGORIES),
                site=random.choice(SITES),
                devise=devise,
                taux=taux,
            )
            # Une paire équilibrée : charge au débit, trésorerie au crédit.
            lignes.append(
                dict(
                    commun,
                    compte=random.choice(COMPTES_CHARGE),
                    debit=montant,
                    credit=Decimal(0),
                    tiers=None,
                )
            )
            lignes.append(
                dict(
                    commun,
                    compte=random.choice(COMPTES_TRESO),
                    debit=Decimal(0),
                    credit=montant,
                    tiers=None,
                )
            )
            n += 2
            if len(lignes) >= 10_000:
                self._inserer(lignes)
                lignes = []
                self.stdout.write(f"  {org.hex[:4]}… {n:>7} lignes")
        if lignes:
            self._inserer(lignes)
        return n

    def _inserer(self, lignes):
        champs = list(lignes[0].keys())
        colonnes = ", ".join(champs)
        gabarit = "(" + ", ".join(["%s"] * (len(champs) + 3)) + ")"
        valeurs, params = [], []
        for ligne in lignes:
            valeurs.append(gabarit)
            params += (
                [uuid.uuid4()]
                + [ligne[c] for c in champs]
                + [
                    datetime.datetime.now(datetime.UTC),
                    datetime.datetime.now(datetime.UTC),
                ]
            )
        with connection.cursor() as cur:
            cur.execute(
                f"INSERT INTO moteur_ligneecriture "
                f"(id, {colonnes}, created_at, updated_at) VALUES " + ", ".join(valeurs),
                params,
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
