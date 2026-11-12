"""Compilation pure d'un modèle d'état. Voir L0-T05."""

import uuid

import pytest

from niveau4_reporting.moteur.compilateur import ModeleEtatInvalide, compiler
from niveau4_reporting.moteur.formules import FormuleInvalide

PARAMS = {
    "project_id": uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"),
    "fiscal_year": 2026,
    "current_period": 5,
}


def _modele(**ligne):
    return {
        "code": "TER",
        "columns": [{"code": "YTD", "period": "year_to_date"}],
        "rows": [{"code": "R100", "type": "aggregate", **ligne}],
    }


def test_la_requete_est_unique_et_ne_contient_aucun_filtre_org_manuel():
    modele = _modele(select={"accounts": [["6000", "6299"]]})
    produit = compiler(modele, {}, PARAMS)

    assert "WITH source AS" in produit.sql
    assert "GROUP BY ()" in produit.sql
    assert "org_id" not in produit.sql
    assert ";" not in produit.sql
    assert produit.selections["R100"].params == ("6000", "6299\uffff")
    assert produit.source_params == (PARAMS["project_id"], 2026, 2026, 5)


def test_deux_rubriques_peuvent_utiliser_la_meme_fourchette():
    modele = _modele(select={"accounts": [["6000", "6299"]]})
    modele["rows"].append(
        {"code": "R101", "type": "aggregate", "select": {"accounts": [["6000", "6299"]]}}
    )
    produit = compiler(modele, {}, PARAMS)
    assert produit.sql.count("COALESCE(SUM") == 2


@pytest.mark.parametrize(
    "modele",
    [
        {"code": "TER", "columns": [], "rows": []},
        _modele(select={"mapping": "WB", "target": "X"}),
        _modele(select={"accounts": [["60"]]}),
        _modele(select={"accounts": [["60", "62"]], "mapping": "WB", "target": "X"}),
    ],
)
def test_un_modele_incomplet_est_refuse_avant_sql(modele):
    with pytest.raises((ModeleEtatInvalide, ValueError)):
        compiler(modele, {}, PARAMS)


def test_une_assertion_ne_est_jamais_silencieusement_ignoree():
    modele = _modele(select={"accounts": [["6000", "6299"]]})
    modele["rows"][0]["assert"] = "R100 == 0"
    with pytest.raises(FormuleInvalide, match="L0-T06"):
        compiler(modele, {}, PARAMS)
