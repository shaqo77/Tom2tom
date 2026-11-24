# ruff: noqa: F811
"""La pagination optionnelle des listes de l'API (Lot 2-B), bout en bout par HTTP.

Le corps reste un tableau JSON ; la pagination se demande par `?limite=` et `?decalage=`, le total
et la suite passent par les en-têtes `X-Total-Count` et `X-Decalage-Suivant`.
"""

import pytest

from tests.test_api_marches_bd import RACINE, appeler  # noqa: F401
from tests.test_api_parametres_devises_bd import reglages  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_devises_parametrees_application_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def _taux(dora, jours):
    for jour in jours:
        r = appeler(
            dora,
            "post",
            "/taux/",
            {
                "devise": "USD",
                "date": f"2026-03-{jour:02d}",
                "taux": "177",
                "type_taux": "officiel",
            },
        )
        assert r.status_code == 201, r.content


def test_les_taux_se_paginent_et_gardent_leur_ordre(reglages):
    _, _, _, profils = reglages
    dora = profils["dora"]
    _taux(dora, range(1, 8))
    tout = appeler(dora, "get", "/taux/")
    assert tout.status_code == 200 and tout["X-Total-Count"] == "7"
    assert "X-Decalage-Suivant" not in tout
    dates = [t["date"] for t in tout.json()]
    assert dates == sorted(dates, reverse=True)

    premiere = appeler(dora, "get", "/taux/?limite=3")
    assert [t["date"] for t in premiere.json()] == dates[:3]
    assert premiere["X-Total-Count"] == "7" and premiere["X-Decalage-Suivant"] == "3"

    derniere = appeler(dora, "get", "/taux/?limite=3&decalage=6")
    assert [t["date"] for t in derniere.json()] == dates[6:]
    assert "X-Decalage-Suivant" not in derniere


def test_un_parametre_de_pagination_invalide_est_refuse_au_format_stable(reglages):
    _, _, _, profils = reglages
    for requete in ("limite=0", "limite=501", "limite=abc", "decalage=-1"):
        r = appeler(profils["dora"], "get", f"/taux/?{requete}")
        assert r.status_code == 422, requete
        assert set(r.json()) == {"code", "message"}, requete
