"""Compilation SQL du mapping priorisé. Voir L0-T04."""

import pytest

from niveau4_reporting.mapping.models import RegleMapping
from niveau4_reporting.mapping.resolveur import MappingInvalide, construire_cas_sql


def test_les_regles_sont_compilees_par_priorite_et_parametrees():
    regles = [
        RegleMapping(
            priority=20,
            match={"accounts": [["7000", "7999"]], "dim1": ["COMP-B"]},
            target_code="R200",
        ),
        RegleMapping(
            priority=10,
            match={
                "accounts": [["6000", "6299"], ["6400", "6400"]],
                "agreement": "IDA-6789",
                "site": ["SIEGE"],
            },
            target_code="R100",
        ),
    ]

    sql, params = construire_cas_sql(regles)

    assert sql.count("WHEN") == 2
    assert sql.index("compte >= %s") < sql.index("dim1 = ANY(%s)")
    assert "accord = ANY(%s)" in sql
    assert "org_id" not in sql
    assert params == [
        "6000",
        "6299\uffff",
        "6400",
        "6400\uffff",
        ["IDA-6789"],
        ["SIEGE"],
        "R100",
        "7000",
        "7999\uffff",
        ["COMP-B"],
        "R200",
    ]


@pytest.mark.parametrize(
    ("match", "condition_expr", "message"),
    [
        ({"inconnu": ["X"]}, None, "clé de filtre inconnue"),
        ({"accounts": [["60"]]}, None, "fourchette de comptes"),
        ({"accounts": [["62", "60"]]}, None, "fourchette inversée"),
        ({"dim1": []}, None, "au moins une valeur"),
        ({"accounts": [["60", "62"]]}, "compte = '6281'", "condition_expr"),
    ],
)
def test_une_regle_ambigue_ou_non_compilable_est_refusee(match, condition_expr, message):
    regle = RegleMapping(
        priority=10,
        match=match,
        target_code="R100",
        condition_expr=condition_expr,
    )
    with pytest.raises(MappingInvalide, match=message):
        construire_cas_sql([regle])
