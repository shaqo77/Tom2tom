# ruff: noqa: F811
"""Pagination (Lot 2-B) des bailleurs et des accords, par HTTP."""

import pytest

from tests.test_api_marches_bd import RACINE, appeler  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def test_les_bailleurs_se_paginent(cadre):
    _, _, profils, _ = cadre
    dora = profils["dora"]
    for code in ("AAA", "BBB", "CCC"):
        r = appeler(dora, "post", "/bailleurs/", {"code": code, "nom": f"Bailleur {code}"})
        assert r.status_code == 201, r.content
    tout = [b["code"] for b in appeler(dora, "get", "/bailleurs/").json()]
    page = appeler(dora, "get", "/bailleurs/?limite=2&decalage=1")
    assert [b["code"] for b in page.json()] == tout[1:3]
    assert page["X-Total-Count"] == str(len(tout))


def test_les_accords_se_paginent(cadre):
    _, projet, profils, _ = cadre
    dora = profils["dora"]
    for numero in ("A-1", "A-2", "A-3"):
        r = appeler(
            dora,
            "post",
            f"/projets/{projet.id}/accords/",
            {
                "bailleur": "IDA",
                "numero": numero,
                "nature": "don",
                "devise": "USD",
                "montant_initial": "1000",
                "libelle": numero,
            },
        )
        assert r.status_code == 201, r.content
    chemin = f"/projets/{projet.id}/accords/"
    page = appeler(dora, "get", f"{chemin}?limite=2")
    assert [a["numero"] for a in page.json()] == ["A-1", "A-2"]
    assert page["X-Total-Count"] == "3" and page["X-Decalage-Suivant"] == "2"
