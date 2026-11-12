"""Moteur de formules — sécurité et exactitude. Voir L0-T02."""

from decimal import Decimal

import pytest

from niveau4_reporting.moteur.formules import FormuleInvalide, evaluer, valider

CODES = ["R1", "R2", "R3"]


def test_soustraction():
    assert evaluer("R1 - R2", {"R1": Decimal(10), "R2": Decimal(3)}, CODES) == 7


def test_plage_sum():
    v = {"R1": Decimal(1), "R2": Decimal(2), "R3": Decimal(3)}
    assert evaluer("SUM(R1:R3)", v, CODES) == 6


def test_round_en_decimal():
    assert evaluer("ROUND(R1 / 3, 2)", {"R1": Decimal(10)}, CODES) == Decimal("3.33")


def test_abs():
    assert evaluer("ABS(R1 - R2)", {"R1": Decimal(3), "R2": Decimal(8)}, CODES) == 5


def test_rubrique_absente_vaut_zero():
    assert evaluer("R1 + R2", {"R1": Decimal(5)}, CODES) == 5


def test_division_par_zero_refusee():
    with pytest.raises(FormuleInvalide, match="division par zéro"):
        evaluer("R1 / R2", {"R1": Decimal(1), "R2": Decimal(0)}, CODES)


@pytest.mark.parametrize(
    "mechante",
    [
        "__import__('os').system('rm -rf /')",
        "().__class__.__bases__[0].__subclasses__()",
        "open('/etc/passwd').read()",
        "R1 if R2 else R3",
        "[x for x in R1]",
        "R1.__class__",
    ],
)
def test_code_arbitraire_refuse(mechante):
    """Aucune de ces formules ne doit jamais être évaluée."""
    with pytest.raises(FormuleInvalide):
        valider(mechante, CODES)


def test_rubrique_inconnue_refusee():
    with pytest.raises(FormuleInvalide, match="rubrique inconnue"):
        valider("R9 + 1", ["R1"])


def test_plage_inversee_refusee():
    with pytest.raises(FormuleInvalide, match="plage inversée"):
        valider("SUM(R3:R1)", CODES)


def test_syntaxe_invalide_refusee():
    with pytest.raises(FormuleInvalide, match="syntaxe invalide"):
        valider("R1 +", CODES)
