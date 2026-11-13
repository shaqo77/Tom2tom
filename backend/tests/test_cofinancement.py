"""L'arithmétique du cofinancement, sans base de données. Voir L4-T05.

Contrôle obligatoire : la ventilation conserve TOUJOURS le total.
"""

import random
from decimal import ROUND_DOWN, Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from niveau1_socle.financements.cofinancement import (
    CENTIME,
    VentilationImpossible,
    normaliser_parts,
    pas_de_devise,
    ventiler,
)

D = Decimal


def _cle(poids):
    """Une clé normalisée : `[(accord, part)]`, l'accord 0 portant l'arrondi."""
    return list(zip(range(len(poids)), normaliser_parts(poids), strict=True))


@given(
    montant=st.decimals(min_value=D("0.01"), max_value=D("1e9"), places=2),
    poids=st.lists(st.integers(1, 99), min_size=2, max_size=5),
)
@settings(max_examples=2000, deadline=None)
def test_la_ventilation_conserve_toujours_le_total(montant, poids):
    parts = _cle(poids)
    ventile = ventiler(montant, parts, porteur=0)
    assert sum(m for _, m in ventile) == montant
    assert all(m >= 0 for _, m in ventile)
    assert [a for a, _ in ventile] == [a for a, _ in parts]


@given(poids=st.lists(st.integers(1, 99), min_size=1, max_size=5))
@settings(max_examples=1000, deadline=None)
def test_les_parts_normalisees_somment_exactement_a_un(poids):
    parts = normaliser_parts(poids)
    assert sum(parts) == D(1)
    assert all(p > 0 for p in parts)


@given(
    montant=st.decimals(min_value=D("0.01"), max_value=D("1e9"), places=2),
    poids=st.lists(st.integers(1, 99), min_size=2, max_size=5),
)
@settings(max_examples=500, deadline=None)
def test_le_reliquat_n_est_jamais_negatif_et_reste_borne(montant, poids):
    """ROUND_DOWN : chaque part perd moins d'un centime, le reliquat est de 0 à (n - 1) centimes."""
    parts = _cle(poids)
    sans_reliquat = [(montant * p).quantize(CENTIME, rounding=ROUND_DOWN) for _, p in parts]
    reliquat = montant - sum(sans_reliquat)
    assert 0 <= reliquat < len(parts) * CENTIME
    porteur = ventiler(montant, parts, porteur=0)[0][1]
    assert porteur == sans_reliquat[0] + reliquat


@given(
    montant=st.decimals(min_value=D("0.01"), max_value=D("1e9"), places=2),
    poids=st.lists(st.integers(1, 99), min_size=2, max_size=5),
)
@settings(max_examples=500, deadline=None)
def test_un_remboursement_est_le_miroir_exact_de_la_depense(montant, poids):
    parts = _cle(poids)
    avant = ventiler(montant, parts, porteur=1)
    apres = ventiler(-montant, parts, porteur=1)
    assert apres == [(a, -m) for a, m in avant]
    assert sum(m for _, m in apres) == -montant


@given(
    montant=st.integers(1, 10**12),
    poids=st.lists(st.integers(1, 99), min_size=2, max_size=5),
    decimales=st.integers(0, 4),
)
@settings(max_examples=1000, deadline=None)
def test_le_pas_est_celui_de_la_devise(montant, poids, decimales):
    """En franc de Djibouti (0 décimale) les montants sont entiers ; en dinar (3), au millime."""
    pas = pas_de_devise(decimales)
    total = D(montant) * pas
    ventile = ventiler(total, _cle(poids), porteur=0, pas=pas)
    assert sum(m for _, m in ventile) == total
    assert all(m == m.quantize(pas) for _, m in ventile)


def test_cinquante_mille_ventilations_aleatoires_sont_toutes_conservatives():
    """Le jeu d'épreuve du plan : montants jusqu'à 10^9, de 2 à 5 accords."""
    hasard = random.Random(42)
    reliquat_max = D(0)
    for _ in range(50_000):
        montant = D(hasard.randint(1, 10**11)) / 100
        poids = [hasard.randint(1, 99) for _ in range(hasard.randint(2, 5))]
        parts = _cle(poids)
        ventile = ventiler(montant, parts, porteur=hasard.randrange(len(parts)))
        assert sum(m for _, m in ventile) == montant
        sans = sum((montant * p).quantize(CENTIME, rounding=ROUND_DOWN) for _, p in parts)
        reliquat_max = max(reliquat_max, montant - sans)
    assert reliquat_max < 5 * CENTIME


def test_exemple_a_la_main():
    parts = [("IDA", D("0.6")), ("GOV", D("0.4"))]
    assert ventiler(D("100.01"), parts, porteur="GOV") == [("IDA", D("60.00")), ("GOV", D("40.01"))]
    # un tiers chacun : 100 -> 33,33 + 33,33 + 33,33, et le centime restant va au porteur
    tiers = normaliser_parts([1, 1, 1])
    assert sum(tiers) == D(1) and tiers[0] == D("0.3333333333") and tiers[2] == D("0.3333333334")
    assert ventiler(D(100), list(zip("abc", tiers, strict=True)), porteur="c") == [
        ("a", D("33.33")),
        ("b", D("33.33")),
        ("c", D("33.34")),
    ]


@pytest.mark.parametrize(
    "parts, porteur, montant, message",
    [
        ([], "a", "1", "au moins une part"),
        ([("a", "0.5"), ("b", "0.4")], "a", "1", "sommer exactement à 1"),
        ([("a", "0.5"), ("b", "0.5000000001")], "a", "1", "sommer exactement à 1"),
        ([("a", "1.5"), ("b", "-0.5")], "a", "1", "positives"),
        ([("a", "0.5"), ("b", "0.5")], "z", "1", "porteur"),
        ([("a", "0.5"), ("b", "0.5")], "a", "1.005", "multiple du pas"),
    ],
)
def test_des_entrees_incoherentes_sont_refusees(parts, porteur, montant, message):
    with pytest.raises(VentilationImpossible, match=message):
        ventiler(D(montant), [(a, D(p)) for a, p in parts], porteur)


@pytest.mark.parametrize("poids", [[], [0, 1], [-1, 2]])
def test_normaliser_refuse_des_poids_invalides(poids):
    with pytest.raises(VentilationImpossible):
        normaliser_parts(poids)
