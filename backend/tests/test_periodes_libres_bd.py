# ruff: noqa: F811, E501
"""Lot 4 : un état sur n'importe quelle plage de dates (colonne `{"period": "range"}`).

Les paramètres `plage_debut` et `plage_fin` (ISO, bornes INCLUSES) bornent la colonne ; ils sont des
paramètres SQL, jamais du texte collé. Un rapport sur plage se scelle et se régénère comme un autre.
"""

import datetime
from decimal import Decimal

import pytest

from core.erreurs import ErreurMetier
from niveau4_reporting.moteur.compilateur import ModeleEtatInvalide, compiler, generer
from niveau4_reporting.publication.rapports import publier_rapport, regenerer
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_regeneration_bd import _piece, pub  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
D = Decimal
J = datetime.date
MODELE_PLAGE = {
    "code": "PLG",
    "version": 1,
    "columns": [{"code": "PER", "period": "range"}],
    "rows": [
        {"code": "T100", "type": "heading"},
        {"code": "R110", "type": "aggregate", "select": {"mapping": "WB", "target": "CHARGES"}},
        {"code": "R120", "type": "aggregate", "select": {"mapping": "WB", "target": "TRESORERIE"}},
        {"code": "R190", "type": "computed", "formula": "R110 + R120"},
    ],
}


def _depense(pub, periode, jour, montant):
    organisation, projet, _, _ = pub
    return _piece(organisation, projet, "6011", "5211", montant, periode=periode, jour=jour)


def _charges(pub, debut, fin, modele=None):
    """La rubrique R110 de la plage [debut, fin] (chaînes ISO ou dates)."""
    _, _, _, table = pub
    produit = generer(
        modele or MODELE_PLAGE,
        {"WB": list(table.regles.all())},
        {"project_id": pub[1].id, "plage_debut": debut, "plage_fin": fin},
    )
    return produit.valeurs["R110"]["PER"]


@pytest.fixture
def pieces(pub):
    """Des charges de 10 (15 janv.), 20 (20 janv.), 30 (10 févr.), 40 (28 mars), 50 (27 avr.) ;
    `pub` apporte déjà 100 + 50,10 au 15 février."""
    for periode, jour, montant in (
        (1, 15, "10"),
        (1, 20, "20"),
        (2, 10, "30"),
        (3, 28, "40"),
        (4, 27, "50"),
    ):
        _depense(pub, periode, jour, montant)
    return pub


def test_la_somme_de_deux_plages_contigues_est_la_plage_totale(pieces):
    premiere = _charges(pieces, "2026-01-15", "2026-02-28")
    seconde = _charges(pieces, "2026-03-01", "2026-04-30")
    totale = _charges(pieces, "2026-01-15", "2026-04-30")
    assert (premiere, seconde, totale) == (D("210.10"), D("90"), D("300.10"))
    assert premiere + seconde == totale


def test_les_deux_bornes_sont_incluses_et_le_jour_d_avant_ou_d_apres_exclu(pieces):
    assert _charges(pieces, "2026-01-15", "2026-01-15") == D("10")  # le seul jour de début
    assert _charges(pieces, "2026-01-14", "2026-01-14") == D("0")  # la veille : rien
    assert _charges(pieces, "2026-04-27", "2026-04-27") == D("50")  # jour de fin inclus
    assert _charges(pieces, "2026-04-28", "2026-04-28") == D("0")  # le lendemain : rien
    assert _charges(pieces, "2026-01-16", "2026-04-26") == D("300.10") - D("10") - D("50")


def test_les_dates_peuvent_etre_des_objets_date_ou_des_chaines(pieces):
    assert _charges(pieces, J(2026, 1, 15), J(2026, 1, 20)) == _charges(
        pieces, "2026-01-15", "2026-01-20"
    )


@pytest.mark.parametrize(
    "debut, fin",
    [
        ("2026-04-30", "2026-04-29"),  # fin avant début
        ("2026-13-01", "2026-04-30"),  # mois impossible
        ("20260101", "2026-04-30"),
        ("2026-01-01", None),
        (None, "2026-04-30"),
        ("", ""),
        (20260101, 20260430),
        ("2026-01-01'; DROP TABLE comptabilite_ecriture; --", "2026-04-30"),
        ("2026-01-01T00:00:00", "2026-04-30"),
        (datetime.datetime(2026, 1, 1, 12, 30), "2026-04-30"),  # un horodatage n'est pas une date
    ],
)
def test_une_plage_invalide_est_refusee_net(pieces, debut, fin):
    with pytest.raises(ModeleEtatInvalide):
        _charges(pieces, debut, fin)


def test_une_colonne_de_plage_sans_parametres_de_plage_est_refusee(pieces):
    _, _, _, table = pieces
    with pytest.raises(ModeleEtatInvalide):
        compiler(
            MODELE_PLAGE,
            {"WB": list(table.regles.all())},
            {"project_id": pieces[1].id, "fiscal_year": 2026, "current_period": 3},
        )


def test_une_plage_ne_se_melange_pas_aux_autres_periodes_dans_un_meme_modele(pieces):
    _, _, _, table = pieces
    modele = {
        **MODELE_PLAGE,
        "columns": [{"code": "PER", "period": "range"}, {"code": "Y", "period": "year_to_date"}],
    }
    with pytest.raises(ModeleEtatInvalide):
        compiler(
            modele,
            {"WB": list(table.regles.all())},
            {"project_id": pieces[1].id, "plage_debut": "2026-01-01", "plage_fin": "2026-04-30"},
        )


def test_les_modeles_a_periode_fixe_ne_changent_pas(pieces):
    modele = {**MODELE_PLAGE, "columns": [{"code": "YTD", "period": "year_to_date"}]}
    _, _, _, table = pieces
    produit = generer(
        modele,
        {"WB": list(table.regles.all())},
        {"project_id": pieces[1].id, "fiscal_year": 2026, "current_period": 4},
    )
    assert produit.valeurs["R110"]["YTD"] == D("300.10")


# --- publication scellée et régénération ----------------------------------------------------


def _publier(pub, debut="2026-01-15", fin="2026-03-31", **champs):
    organisation, projet, profils, table = pub
    donnees = {
        "utilisateur": profils["pia"],
        "project_id": projet.id,
        "modele": MODELE_PLAGE,
        "params": {"plage_debut": debut, "plage_fin": fin},
        "tables": {"WB": table},
        "period_from": J.fromisoformat(debut),
        "period_to": J.fromisoformat(fin),
    } | champs
    return publier_rapport(**donnees)


def test_un_rapport_sur_plage_se_publie_et_se_rejoue_a_l_identique(pieces):
    rapport = _publier(pieces)
    assert rapport.values["R110/PER"] == "250.1"  # 10 + 20 + 30 + 40 + 150,10
    assert rapport.params == {
        "plage_debut": "2026-01-15",
        "plage_fin": "2026-03-31",
        "project_id": str(pieces[1].id),
    }
    resultat = regenerer(rapport)
    assert resultat.identique and not resultat.ecarts


def test_deux_plages_identiques_donnent_le_meme_scelle_et_une_autre_plage_un_autre(pieces):
    a, b = _publier(pieces), _publier(pieces)
    c = _publier(pieces, fin="2026-03-30")
    assert bytes(a.seal) == bytes(b.seal)
    assert bytes(a.seal) != bytes(c.seal)


def test_une_ecriture_posterieure_dans_la_plage_est_nommee_mais_pas_celle_hors_plage(pieces):
    organisation, projet, _, _ = pieces
    rapport = _publier(pieces)
    hors = _piece(
        organisation, projet, "6011", "5211", "7", periode=4, jour=10
    )  # avril : hors plage
    assert regenerer(rapport).identique
    dedans = _piece(organisation, projet, "6011", "5211", "75.25", periode=2, jour=20)
    resultat = regenerer(rapport)
    assert not resultat.identique
    assert {c.ecriture for c in resultat.causes} == {dedans.number}
    assert hors.number not in {c.ecriture for c in resultat.causes}


def test_la_periode_du_rapport_doit_etre_la_plage_demandee(pieces):
    with pytest.raises(ErreurMetier):
        _publier(
            pieces, period_to=J(2026, 4, 30)
        )  # le rapport dirait avril, la plage s'arrête en mars
    with pytest.raises(ErreurMetier):
        _publier(pieces, period_from=J(2026, 1, 1))
