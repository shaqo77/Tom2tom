"""Ordonnancement des rubriques calculées. Voir L0-T03."""

import pytest

from niveau4_reporting.moteur.dependances import ReferenceCirculaire, ordonner

CODES = ["R1", "R2", "R3", "R4"]


def test_ordre_respecte_les_dependances():
    ordre = ordonner({"R3": "R1 + R2", "R4": "R3 * 2"}, CODES)
    assert ordre.index("R3") < ordre.index("R4")


def test_reference_circulaire_refusee():
    with pytest.raises(ReferenceCirculaire, match="référence circulaire"):
        ordonner({"R1": "R2 + 1", "R2": "R1 - 1"}, CODES)


def test_cycle_indirect_refuse():
    with pytest.raises(ReferenceCirculaire):
        ordonner({"R1": "R2", "R2": "R3", "R3": "R1"}, CODES)
