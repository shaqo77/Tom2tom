"""Assertions bloquantes exécutées avec l'unique requête SQL. Voir L0-T06."""

import datetime
import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from niveau4_reporting.moteur.assertions import AssertionsViolees
from niveau4_reporting.moteur.compilateur import generer
from niveau4_reporting.moteur.models import LigneEcriture

pytestmark = pytest.mark.django_db(transaction=True)
PROJECT_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")


def _ligne(org_id, compte, *, debit="0", credit="0", annee=2026, periode=4):
    return LigneEcriture.objects.create(
        org_id=org_id,
        project_id=PROJECT_ID,
        fiscal_year=annee,
        period=periode,
        accounting_date=datetime.date(annee, periode, 15),
        compte=compte,
        debit=debit,
        credit=credit,
        dim1="COMP-A",
        accord="IDA-6789",
        categorie="CAT-1",
        site="SIEGE",
        devise="DJF",
        taux="1",
    )


@pytest.fixture
def jeu_assertion(org_a):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_a)])
    _ligne(org_a, "6011", debit="100")
    _ligne(org_a, "7011", credit="25")
    _ligne(org_a, "5011", debit="125")
    _ligne(org_a, "4011", credit="200")
    modele = {
        "code": "TER",
        "columns": [{"code": "YTD", "period": "year_to_date"}],
        "rows": [
            {
                "code": "R110",
                "type": "aggregate",
                "select": {"accounts": [["6011", "6011"]]},
            },
            {
                "code": "R120",
                "type": "aggregate",
                "select": {"accounts": [["7011", "7011"]]},
            },
            {
                "code": "R900",
                "type": "computed",
                "formula": "R110 - R120",
                "assert": "R900 == BALANCE('5')",
            },
        ],
    }
    params = {"project_id": PROJECT_ID, "fiscal_year": 2026, "current_period": 4}
    return org_a, modele, params


def test_une_assertion_vraie_produit_son_rapport_en_une_seule_requete(jeu_assertion):
    _, modele, params = jeu_assertion
    with CaptureQueriesContext(connection) as requetes:
        produit = generer(modele, {}, params)

    assert len(requetes) == 1
    assert produit.valeurs["R900"]["YTD"] == Decimal("125")
    assert produit.publiable is True
    assert len(produit.controles) == 1
    controle = produit.controles[0]
    assert controle.rubrique == "R900"
    assert controle.colonne == "YTD"
    assert controle.reussi is True
    assert controle.gauche == controle.droite == Decimal("125")


def test_une_ligne_falsifiee_bloque_la_generation_et_nomme_lassertion(jeu_assertion):
    org_a, modele, params = jeu_assertion
    _ligne(org_a, "5011", debit="0.01")

    with CaptureQueriesContext(connection) as requetes, pytest.raises(AssertionsViolees) as erreur:
        generer(modele, {}, params)

    assert len(requetes) == 1
    assert "R900" in str(erreur.value)
    assert "YTD" in str(erreur.value)
    assert "R900 == BALANCE('5')" in str(erreur.value)
    assert len(erreur.value.violations) == 1
    assert erreur.value.violations[0].ecart == Decimal("-0.01")


def test_lassertion_est_verifiee_separement_pour_chaque_colonne(jeu_assertion):
    org_a, modele, params = jeu_assertion
    _ligne(org_a, "5011", debit="1", annee=2025, periode=12)
    modele["columns"] = [
        {"code": "QTR", "period": "current_quarter"},
        {"code": "YTD", "period": "year_to_date"},
        {"code": "CUMUL", "period": "inception_to_date"},
    ]

    with CaptureQueriesContext(connection) as requetes, pytest.raises(AssertionsViolees) as erreur:
        generer(modele, {}, params)

    assert len(requetes) == 1
    assert len(erreur.value.controles) == 3
    assert len(erreur.value.violations) == 1
    assert erreur.value.violations[0].colonne == "CUMUL"
    assert erreur.value.violations[0].ecart == Decimal("-1")
