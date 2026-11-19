"""Calcul des lignes d'un schéma d'écriture : logique pure, sans base. Voir L3-T06.

Une règle de calcul est un élément d'un ensemble FERMÉ (`base`, `taux`, `solde`), jamais une
formule libre : aucune évaluation de code sur une donnée utilisateur (règle 5).
"""

from decimal import ROUND_HALF_UP, Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from niveau1_socle.comptabilite.schemas import ModeleLigne, SchemaIncoherent, calculer_lignes

ACHAT = [
    ModeleLigne("6011", "debit", "base", None, {"dim1": "COMP-A"}),
    ModeleLigne("4452", "debit", "taux", Decimal("0.18"), {}),
    ModeleLigne("4011", None, "solde", None, {}),
]


def _total(lignes, sens):
    return sum((Decimal(ligne[sens]) for ligne in lignes), Decimal(0))


def test_un_achat_avec_tva_et_contrepartie_automatique():
    lignes = calculer_lignes(ACHAT, Decimal("1000"), decimales=2)

    assert [(ligne["compte"], ligne["debit"], ligne["credit"]) for ligne in lignes] == [
        ("6011", "1000.00", "0"),
        ("4452", "180.00", "0"),
        ("4011", "0", "1180.00"),
    ]
    assert lignes[0]["dim1"] == "COMP-A"  # l'axe par défaut du schéma est repris


def test_les_arrondis_sont_deterministes_au_nombre_de_decimales_de_la_devise():
    assert calculer_lignes(ACHAT, Decimal("100.05"), decimales=2)[1]["debit"] == "18.01"  # 18,009
    assert calculer_lignes(ACHAT, Decimal("333"), decimales=0)[1]["debit"] == "60"  # 59,94
    assert (
        calculer_lignes(ACHAT, Decimal("2.5"), decimales=0)[0]["debit"] == "3"
    )  # moitié vers le haut


def test_la_contrepartie_prend_le_sens_qui_equilibre():
    recette = [
        ModeleLigne("5211", "debit", "base", None, {}),
        ModeleLigne("7061", None, "solde", None, {}),
    ]
    lignes = calculer_lignes(recette, Decimal("500"), decimales=0)
    assert [(ligne["compte"], ligne["debit"], ligne["credit"]) for ligne in lignes] == [
        ("5211", "500", "0"),
        ("7061", "0", "500"),
    ]

    inverse = [
        ModeleLigne("5211", "credit", "base", None, {}),
        ModeleLigne("6011", None, "solde", None, {}),
    ]
    assert calculer_lignes(inverse, Decimal("500"), decimales=0)[1]["debit"] == "500"


def test_une_ligne_a_zero_nest_pas_generee():
    lignes = calculer_lignes(ACHAT, Decimal("2"), decimales=0)  # 2 x 0,18 = 0,36 -> 0
    assert [ligne["compte"] for ligne in lignes] == ["6011", "4011"]


def test_un_montant_qui_arrondit_a_zero_ne_genere_aucune_piece():
    """Trouvé par la propriété ci-dessous : 0,01 en devise sans décimale n'est rien."""
    with pytest.raises(SchemaIncoherent, match="nul après arrondi"):
        calculer_lignes(ACHAT, Decimal("0.01"), decimales=0)


def test_une_contrepartie_sans_rien_a_equilibrer_est_une_incoherence():
    deja_equilibre = [
        ModeleLigne("6011", "debit", "base", None, {}),
        ModeleLigne("5211", "credit", "base", None, {}),
        ModeleLigne("4011", None, "solde", None, {}),
    ]
    with pytest.raises(SchemaIncoherent, match="rien à équilibrer"):
        calculer_lignes(deja_equilibre, Decimal("10"), decimales=2)


@pytest.mark.parametrize(
    ("modeles", "message"),
    [
        ([ModeleLigne("6011", "debit", "formule", None, {})], "règle inconnue"),
        ([ModeleLigne("6011", "debit", "taux", None, {})], "taux"),
        ([ModeleLigne("6011", "debit", "taux", Decimal("0"), {})], "taux"),
        ([ModeleLigne("6011", "debit", "base", Decimal("0.1"), {})], "taux"),
        ([ModeleLigne("6011", "neutre", "base", None, {})], "sens"),
        ([ModeleLigne("6011", None, "base", None, {})], "sens"),
        ([ModeleLigne("6011", "debit", "solde", None, {})], "sens"),
        (
            [
                ModeleLigne("6011", "debit", "base", None, {}),
                ModeleLigne("4011", None, "solde", None, {}),
                ModeleLigne("4012", None, "solde", None, {}),
            ],
            "une seule contrepartie",
        ),
        ([ModeleLigne("6011", "debit", "base", None, {"dim9": "X"})], "axe"),
    ],
)
def test_un_schema_mal_forme_est_refuse_avec_la_raison(modeles, message):
    with pytest.raises(SchemaIncoherent, match=message):
        calculer_lignes(modeles, Decimal("10"), decimales=2)


@given(
    montant=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("1e9"), places=2),
    taux=st.decimals(min_value=Decimal("0.0001"), max_value=Decimal("0.9999"), places=4),
    decimales=st.sampled_from([0, 2, 3]),
)
def test_la_piece_generee_est_toujours_equilibree_arrondis_compris(montant, taux, decimales):
    """Propriété : la contrepartie absorbe les arrondis, donc débit == crédit, toujours."""
    modeles = [
        ModeleLigne("6011", "debit", "base", None, {}),
        ModeleLigne("4452", "debit", "taux", taux, {}),
        ModeleLigne("4011", None, "solde", None, {}),
    ]
    try:
        lignes = calculer_lignes(modeles, montant, decimales=decimales)
    except SchemaIncoherent as erreur:
        # Seul cas légitime : le montant arrondit à zéro (0,01 en devise sans décimale).
        assert "nul après arrondi" in str(erreur)
        return
    assert _total(lignes, "debit") == _total(lignes, "credit")
    pas = Decimal(1).scaleb(-decimales)
    assert all(
        Decimal(ligne[sens]) == Decimal(ligne[sens]).quantize(pas, rounding=ROUND_HALF_UP)
        for ligne in lignes
        for sens in ("debit", "credit")
    )
