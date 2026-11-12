"""Mesure L0-T05 : TER sur 200 000 lignes, une seule requête.

Depuis la racine : backend/.venv/bin/python scripts/mesurer_ter.py
Préparer les données : generer_donnees --lignes 200000 --organisation A --projet 1 --purger
"""

import datetime
import os
import sys
import time
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django

django.setup()

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from niveau4_reporting.mapping.models import RegleMapping, TableMapping
from niveau4_reporting.moteur.compilateur import generer

ORG = uuid.UUID("11111111-1111-1111-1111-111111111111")
PROJET = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
BAILLEUR = uuid.UUID("33333333-3333-3333-3333-333333333333")
MODELE = {
    "code": "TER",
    "version": 1,
    "columns": [
        {"code": "QTR", "period": "current_quarter"},
        {"code": "YTD", "period": "year_to_date"},
        {"code": "CUMUL", "period": "inception_to_date"},
    ],
    "rows": [
        {
            "code": "R110",
            "type": "aggregate",
            "select": {"mapping": "BENCHMARK-TER", "target": "CHARGES"},
        },
        {
            "code": "R120",
            "type": "aggregate",
            "select": {"mapping": "BENCHMARK-TER", "target": "TRESORERIE"},
        },
        {"code": "R190", "type": "computed", "formula": "R110 + R120"},
    ],
}
PARAMS = {"project_id": PROJET, "fiscal_year": 2026, "current_period": 12}


def preparer_mapping():
    table, _ = TableMapping.objects.get_or_create(
        org_id=ORG,
        project_id=PROJET,
        donor_profile_id=BAILLEUR,
        code="BENCHMARK-TER",
        version=1,
        defaults={
            "valid_from": datetime.date(2024, 1, 1),
            "status": "active",
            "validated_by": uuid.UUID("44444444-4444-4444-4444-444444444444"),
            "validated_at": timezone.now(),
        },
    )
    RegleMapping.objects.get_or_create(
        table=table,
        priority=10,
        defaults={
            "org_id": ORG,
            "match": {"accounts": [["6000", "6599"]]},
            "target_code": "CHARGES",
        },
    )
    RegleMapping.objects.get_or_create(
        table=table,
        priority=20,
        defaults={
            "org_id": ORG,
            "match": {"accounts": [["5200", "5399"]]},
            "target_code": "TRESORERIE",
        },
    )
    return table


def main():
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(ORG)])
        cur.execute(
            "SELECT count(*) FROM moteur_ligneecriture WHERE project_id = %s",
            [PROJET],
        )
        lignes = cur.fetchone()[0]
    if lignes != 200_000:
        raise SystemExit(
            f"Jeu invalide : {lignes} lignes dans le projet, 200000 exigées"
        )

    table = preparer_mapping()
    regles = list(table.regles.all())
    durees = []
    for iteration in range(1, 4):
        debut = time.perf_counter()
        with CaptureQueriesContext(connection) as requetes:
            produit = generer(MODELE, {"BENCHMARK-TER": regles}, PARAMS)
        duree = time.perf_counter() - debut
        durees.append(duree)
        assert len(requetes) == 1, f"{len(requetes)} requêtes au lieu d'une"
        print(f"Itération {iteration} : {duree:.3f} s, {len(requetes)} requête")
    meilleure = min(durees)
    print(f"Meilleur TER sur {lignes} lignes : {meilleure:.3f} s")
    print(f"R190 CUMUL : {produit.valeurs['R190']['CUMUL']}")
    if meilleure >= 3:
        raise SystemExit("ÉCHEC L0-T05 : le TER dépasse 3 secondes")


if __name__ == "__main__":
    main()
