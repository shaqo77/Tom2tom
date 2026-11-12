"""Langage restreint et rapport des assertions. Voir L0-T06."""

from decimal import Decimal

import pytest

from niveau4_reporting.moteur.assertions import (
    AssertionInvalide,
    analyser_assertion,
    controler_assertion,
)

CODES = ["R110", "R120", "R900"]


def _controle(expression, valeurs, balances=None):
    return controler_assertion(
        expression,
        valeurs,
        CODES,
        balances or {},
        rubrique="R900",
        colonne="YTD",
    )


def test_balance_et_comparaison_sont_exactes_en_decimal():
    controle = _controle(
        "R900 == BALANCE('5')",
        {"R900": Decimal("125.00")},
        {"5": Decimal("125.00")},
    )
    assert controle.reussi is True
    assert controle.gauche == Decimal("125.00")
    assert controle.droite == Decimal("125.00")
    assert controle.ecart == Decimal("0.00")
    assert controle.comparateur == "=="


def test_une_assertion_peut_comparer_des_formules_de_rubriques():
    controle = _controle(
        "R110 - R120 == R900",
        {"R110": Decimal("100"), "R120": Decimal("-25"), "R900": Decimal("125")},
    )
    assert controle.reussi is True


@pytest.mark.parametrize(
    ("comparateur", "attendu"),
    [("==", True), ("!=", False), ("<", False), ("<=", True), (">", False), (">=", True)],
)
def test_les_six_comparateurs_declares_sont_supportes(comparateur, attendu):
    controle = _controle(
        f"R110 {comparateur} R900",
        {"R110": Decimal("125"), "R900": Decimal("125")},
    )
    assert controle.reussi is attendu


def test_une_assertion_fausse_conserve_ses_deux_valeurs_et_son_ecart():
    controle = _controle(
        "R900 == BALANCE('5')",
        {"R900": Decimal("125.00")},
        {"5": Decimal("125.01")},
    )
    assert controle.reussi is False
    assert controle.gauche == Decimal("125.00")
    assert controle.droite == Decimal("125.01")
    assert controle.ecart == Decimal("-0.01")


def test_les_prefixes_balance_sont_extraits_sans_doublon():
    assertion = analyser_assertion(
        "R900 == BALANCE('5') + BALANCE('521') - BALANCE('5')",
        CODES,
    )
    assert assertion.prefixes == ("5", "521")


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id') == 0",
        "R900.__class__ == 0",
        "R900 == open('/etc/passwd')",
        "R900 == R_INCONNUE",
        "R900 == BALANCE(R110)",
        "R900 == BALANCE('')",
        "R900 == BALANCE('5', '6')",
        "R900 == 0 == R110",
        "R900 != 0 and R110 == 0",
        "R900 == 'abc'",
        "R900 === 0",
    ],
)
def test_toute_construction_hors_du_langage_est_refusee(expression):
    with pytest.raises(AssertionInvalide):
        analyser_assertion(expression, CODES)
