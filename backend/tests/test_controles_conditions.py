# ruff: noqa: E501  (tables de cas : une condition par ligne)
"""Le langage de conditions des contrôles : fermé, validé par schéma, sans eval. L6-T01a (pur)."""

import ast
import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from niveau4_reporting.controles import conditions
from niveau4_reporting.controles.conditions import (
    OPERATEURS,
    SCHEMAS,
    ConditionInvalide,
    evaluer,
    preparer_expression,
    reussit,
)

D = Decimal
J = datetime.date


def expr(type_regle, *conds):
    return {"type_regle": type_regle, "conditions": list(conds)}


def ok(type_regle, cond, contexte) -> bool:
    return reussit(evaluer(preparer_expression(expr(type_regle, cond)), contexte))


# --- le jeu d'opérateurs est exactement celui du plan --------------------------------------


def test_le_jeu_d_operateurs_est_ferme_et_conforme_au_plan():
    assert set(OPERATEURS) == {
        "eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "est_renseigne", "est_absent",
        "avant", "apres", "entre", "est_vrai", "est_faux", "somme_lte", "nombre_eq",
    }  # fmt: skip
    assert len(OPERATEURS) == 17


# --- chaque opérateur : vrai et faux -------------------------------------------------------

CAS = [
    # (type, condition, contexte, attendu)
    ("budget", {"champ": "montant", "op": "eq", "valeur": "100.00"}, {"montant": D("100")}, True),
    ("budget", {"champ": "montant", "op": "eq", "valeur": "100.00"}, {"montant": D("100.01")}, False),
    ("budget", {"champ": "montant", "op": "neq", "valeur": "100"}, {"montant": D("99")}, True),
    ("budget", {"champ": "montant", "op": "neq", "valeur": "100"}, {"montant": D("100")}, False),
    ("budget", {"champ": "montant", "op": "gt", "valeur": "100"}, {"montant": D("100.01")}, True),
    ("budget", {"champ": "montant", "op": "gt", "valeur": "100"}, {"montant": D("100")}, False),
    ("budget", {"champ": "montant", "op": "gte", "valeur": "100"}, {"montant": D("100")}, True),
    ("budget", {"champ": "montant", "op": "gte", "valeur": "100"}, {"montant": D("99.99")}, False),
    ("budget", {"champ": "montant", "op": "lt", "valeur": "100"}, {"montant": D("99.99")}, True),
    ("budget", {"champ": "montant", "op": "lt", "valeur": "100"}, {"montant": D("100")}, False),
    ("budget", {"champ": "montant", "op": "lte", "valeur": "100"}, {"montant": D("100")}, True),
    ("budget", {"champ": "montant", "op": "lte", "valeur": "100"}, {"montant": D("100.01")}, False),
    ("codification", {"champ": "categorie", "op": "in", "valeur": ["A", "B"]}, {"categorie": "B"}, True),
    ("codification", {"champ": "categorie", "op": "in", "valeur": ["A", "B"]}, {"categorie": "C"}, False),
    ("codification", {"champ": "categorie", "op": "not_in", "valeur": ["A"]}, {"categorie": "C"}, True),
    ("codification", {"champ": "categorie", "op": "not_in", "valeur": ["A"]}, {"categorie": "A"}, False),
    ("codification", {"champ": "categorie", "op": "est_renseigne"}, {"categorie": "A"}, True),
    ("codification", {"champ": "categorie", "op": "est_renseigne"}, {"categorie": ""}, False),
    ("codification", {"champ": "categorie", "op": "est_renseigne"}, {}, False),
    ("codification", {"champ": "source", "op": "est_absent"}, {}, True),
    ("codification", {"champ": "source", "op": "est_absent"}, {"source": "IDA"}, False),
    ("codification", {"champ": "date", "op": "avant", "valeur": "2026-07-01"}, {"date": J(2026, 6, 30)}, True),
    ("codification", {"champ": "date", "op": "avant", "valeur": "2026-07-01"}, {"date": J(2026, 7, 1)}, False),
    ("codification", {"champ": "date", "op": "apres", "valeur": "2026-07-01"}, {"date": J(2026, 7, 2)}, True),
    ("codification", {"champ": "date", "op": "apres", "valeur": "2026-07-01"}, {"date": J(2026, 7, 1)}, False),
    ("codification", {"champ": "date", "op": "entre", "valeur": ["2026-01-01", "2026-07-01"]}, {"date": J(2026, 1, 1)}, True),
    ("codification", {"champ": "date", "op": "entre", "valeur": ["2026-01-01", "2026-07-01"]}, {"date": J(2026, 7, 1)}, False),
    ("tresorerie", {"champ": "ecart_justifie", "op": "est_vrai"}, {"ecart_justifie": True}, True),
    ("tresorerie", {"champ": "ecart_justifie", "op": "est_vrai"}, {"ecart_justifie": False}, False),
    ("tresorerie", {"champ": "ecart_justifie", "op": "est_faux"}, {"ecart_justifie": False}, True),
    ("tresorerie", {"champ": "ecart_justifie", "op": "est_faux"}, {"ecart_justifie": True}, False),
    ("pieces", {"champ": "pieces", "op": "nombre_eq", "valeur": 2}, {"pieces": [{}, {}]}, True),
    ("pieces", {"champ": "pieces", "op": "nombre_eq", "valeur": 2}, {"pieces": [{}]}, False),
    ("pieces", {"champ": "pieces", "op": "nombre_eq", "valeur": 0}, {}, True),
    ("avances", {"champ": "jours_depuis_versement", "op": "lte", "valeur": 90}, {"jours_depuis_versement": 90}, True),
    ("avances", {"champ": "jours_depuis_versement", "op": "lte", "valeur": 90}, {"jours_depuis_versement": 91}, False),
]  # fmt: skip


@pytest.mark.parametrize("type_regle, cond, contexte, attendu", CAS)
def test_chaque_operateur_est_vrai_ou_faux_comme_attendu(type_regle, cond, contexte, attendu):
    assert ok(type_regle, cond, contexte) is attendu


def test_chaque_operateur_du_jeu_est_couvert_par_les_cas():
    couverts = {cas[1]["op"] for cas in CAS} | {"somme_lte"}
    assert couverts == set(OPERATEURS)


def test_somme_lte_additionne_exactement_sans_derive_de_flottant():
    cond = {"champ": "pieces", "op": "somme_lte", "somme_de": "montant", "valeur": "0.30"}
    # NB : le schéma de « pieces » n'a pas de montant ; somme_lte se teste sur un champ liste
    # numérique : voir le type de règle « rapport » pour la forme, ici un schéma ad hoc.
    with pytest.raises(ConditionInvalide, match="champ numérique"):
        preparer_expression(expr("pieces", cond))
    conditions.SCHEMAS["_essai"] = {
        "lignes": conditions.Champ(
            conditions.TypeChamp.LISTE, (("montant", conditions.TypeChamp.DECIMAL),)
        )
    }
    try:
        ligne = {"champ": "lignes", "op": "somme_lte", "somme_de": "montant", "valeur": "0.30"}
        prete = preparer_expression(expr("_essai", ligne))
        assert reussit(evaluer(prete, {"lignes": [{"montant": D("0.1")}, {"montant": D("0.2")}]}))
        assert not reussit(
            evaluer(prete, {"lignes": [{"montant": D("0.1")}, {"montant": D("0.2000001")}]})
        )
        assert reussit(evaluer(prete, {}))  # somme de rien : 0
    finally:
        del conditions.SCHEMAS["_essai"]


# --- validation : tout ce qui sort du schéma est refusé à l'enregistrement ------------------

REFUS = [
    (expr("budget", {"champ": "montant", "op": "regex", "valeur": ".*"}), "inconnu"),
    (expr("budget", {"champ": "montant", "op": "eval", "valeur": "1"}), "inconnu"),
    (expr("budget", {"champ": "inexistant", "op": "gt", "valeur": "1"}), "hors du schéma"),
    (expr("avances", {"champ": "plafond_accord", "op": "gt", "valeur": "1"}), "hors du schéma"),
    (expr("budget", {"champ": "montant", "op": "avant", "valeur": "2026-01-01"}), "ne s'applique pas"),
    (expr("budget", {"champ": "montant", "op": "est_vrai"}), "ne s'applique pas"),
    (expr("codification", {"champ": "date", "op": "gt", "valeur": "2026-01-01"}), "ne s'applique pas"),
    (expr("budget", {"champ": "montant", "op": "gt", "valeur": 1.5}), "flottante"),
    (expr("budget", {"champ": "montant", "op": "gt", "valeur": True}), "flottante"),
    (expr("budget", {"champ": "montant", "op": "gt", "valeur": "abc"}), "pas un décimal"),
    (expr("budget", {"champ": "montant", "op": "gt", "valeur": "NaN"}), "fini"),
    (expr("budget", {"champ": "montant", "op": "gt", "valeur": "Infinity"}), "fini"),
    (expr("budget", {"champ": "montant", "op": "gt", "valeur": None}), "décimal attendu"),
    (expr("budget", {"champ": "montant", "op": "gt"}), "exige une valeur"),
    (expr("budget", {"champ": "montant", "op": "est_renseigne", "valeur": "1"}), "ne prend pas"),
    (expr("budget", {"champ": "montant", "op": "gt", "valeur": "1", "sql": "DROP"}), "clés inconnues"),
    (expr("codification", {"champ": "date", "op": "avant", "valeur": "demain"}), "pas une date"),
    (expr("codification", {"champ": "date", "op": "avant", "valeur": "2026-13-45"}), "pas une date"),
    (expr("codification", {"champ": "date", "op": "entre", "valeur": ["2026-07-01", "2026-01-01"]}), "vide ou à l'envers"),
    (expr("codification", {"champ": "date", "op": "entre", "valeur": ["2026-01-01", "2026-01-01"]}), "vide ou à l'envers"),
    (expr("codification", {"champ": "date", "op": "entre", "valeur": ["2026-01-01"]}), "deux dates"),
    (expr("codification", {"champ": "categorie", "op": "in", "valeur": []}), "liste"),
    (expr("codification", {"champ": "categorie", "op": "in", "valeur": "A"}), "liste"),
    (expr("codification", {"champ": "categorie", "op": "eq", "valeur": 5}), "texte attendu"),
    (expr("pieces", {"champ": "pieces", "op": "nombre_eq", "valeur": "2"}), "entier attendu"),
    (expr("pieces", {"champ": "pieces", "op": "nombre_eq", "valeur": True}), "entier attendu"),
    (expr("pieces", {"champ": "pieces", "op": "somme_lte", "valeur": "1", "somme_de": "type"}), "champ numérique"),
    (expr("budget", {"champ": "montant", "op": "gt", "valeur": "1", "somme_de": "montant"}), "somme_lte"),
    (expr("inconnu", {"champ": "montant", "op": "gt", "valeur": "1"}), "inconnu"),
    ({"type_regle": "budget", "conditions": []}, "conditions"),
    ({"type_regle": "budget"}, "conditions"),
    ({"type_regle": "budget", "conditions": "x"}, "conditions"),
    ({"type_regle": "budget", "conditions": [["montant", "gt", "1"]]}, "objet"),
    ({"type_regle": "budget", "conditions": [{"champ": "montant", "op": "gt", "valeur": "1"}] * 21}, "conditions"),
    ({"type_regle": "budget", "conditions": [{"champ": "montant", "op": "gt", "valeur": "1"}], "x": 1}, "clés inconnues"),
    ("montant > 100", "objet JSON"),
    (["a"], "objet JSON"),
    (None, "objet JSON"),
]  # fmt: skip


@pytest.mark.parametrize("expression, message", REFUS)
def test_une_condition_hors_schema_ou_operateur_inconnu_est_refusee(expression, message):
    with pytest.raises(ConditionInvalide, match=message):
        preparer_expression(expression)


def test_le_type_de_regle_de_l_expression_doit_etre_celui_du_controle():
    valide = expr("budget", {"champ": "montant", "op": "gt", "valeur": "1"})
    assert preparer_expression(valide, "budget").type_regle == "budget"
    with pytest.raises(ConditionInvalide, match="diffère"):
        preparer_expression(valide, "avances")


def test_chaque_type_de_regle_du_plan_a_son_schema():
    assert set(SCHEMAS) >= {
        "codification", "pieces", "eligibilite", "budget", "tresorerie", "avances",
        "rapport", "coherence", "risque",
    }  # fmt: skip


# --- évaluation ----------------------------------------------------------------------------


def test_toutes_les_conditions_doivent_etre_vraies_et_le_constat_est_lisible():
    prete = preparer_expression(
        expr(
            "budget",
            {"champ": "montant", "op": "lte", "valeur": "1000"},
            {"champ": "disponible_categorie", "op": "gte", "valeur": "500"},
        )
    )
    constats = evaluer(prete, {"montant": D("900"), "disponible_categorie": D("400")})
    assert [c.satisfaite for c in constats] == [True, False]
    assert not reussit(constats)
    assert constats[1].lisible() == "disponible_categorie = 400 ; attendu : gte 500"


def test_une_valeur_absente_ne_satisfait_pas_une_comparaison():
    for op in ("eq", "gt", "gte", "lt", "lte"):
        assert not ok("budget", {"champ": "montant", "op": op, "valeur": "1"}, {})
    assert ok("budget", {"champ": "montant", "op": "neq", "valeur": "1"}, {})  # absent != 1
    assert not ok("codification", {"champ": "date", "op": "avant", "valeur": "2026-01-01"}, {})


@pytest.mark.parametrize(
    "contexte",
    [{"montant": 1.5}, {"montant": "100"}, {"montant": True}, {"montant": J(2026, 1, 1)}],
)
def test_le_contexte_ne_fournit_jamais_un_float_ni_un_mauvais_type_pour_un_montant(contexte):
    prete = preparer_expression(expr("budget", {"champ": "montant", "op": "gt", "valeur": "1"}))
    with pytest.raises(TypeError):
        evaluer(prete, contexte)


def test_une_date_est_une_date_et_pas_un_horodatage():
    prete = preparer_expression(
        expr("codification", {"champ": "date", "op": "avant", "valeur": "2027-01-01"})
    )
    with pytest.raises(TypeError, match="horodatage"):
        evaluer(prete, {"date": datetime.datetime(2026, 1, 1, 12, 0)})


# --- règle 5 : jamais d'eval, jamais de code dans les données ------------------------------


def test_le_module_n_appelle_ni_eval_ni_exec_ni_compile_ni_import_dynamique():
    arbre = ast.parse(Path(conditions.__file__).read_text(encoding="utf-8"))
    interdits = {"eval", "exec", "compile", "__import__", "getattr", "setattr", "open"}
    appels = {
        n.func.id
        for n in ast.walk(arbre)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert not appels & interdits
    modules = {a.name for n in ast.walk(arbre) if isinstance(n, ast.Import) for a in n.names}
    modules |= {n.module for n in ast.walk(arbre) if isinstance(n, ast.ImportFrom)}
    assert not modules & {"os", "subprocess", "sqlite3", "importlib", "pickle"}


@pytest.mark.parametrize(
    "charge",
    ["__import__('os').system('x')", "1; DROP TABLE a", "{{7*7}}", "${jndi:x}", "' OR 1=1 --"],
)
def test_un_code_dans_une_valeur_n_est_que_du_texte_compare(charge):
    cond = {"champ": "categorie", "op": "eq", "valeur": charge}
    assert ok("codification", cond, {"categorie": charge})
    assert not ok("codification", cond, {"categorie": "autre"})


# --- propriétés ----------------------------------------------------------------------------

decimaux = st.decimals(
    min_value=-(10**9), max_value=10**9, allow_nan=False, allow_infinity=False, places=4
)
dates = st.dates(min_value=J(2000, 1, 1), max_value=J(2100, 1, 1))


@given(a=decimaux, b=decimaux)
def test_les_comparaisons_de_decimaux_sont_coherentes(a, b):
    def verdict(op):
        return ok("budget", {"champ": "montant", "op": op, "valeur": str(b)}, {"montant": a})

    assert verdict("gte") == (not verdict("lt"))
    assert verdict("gt") == (not verdict("lte"))
    assert verdict("eq") == (not verdict("neq"))
    assert verdict("eq") == (a == b)
    assert verdict("gte") == (verdict("gt") or verdict("eq"))


@given(d=dates, du=dates, au=dates)
def test_entre_est_un_intervalle_semi_ouvert_qui_partitionne_les_dates(d, du, au):
    if du >= au:
        return

    def verdict(op, valeur):
        return ok("codification", {"champ": "date", "op": op, "valeur": valeur}, {"date": d})

    avant = verdict("avant", du.isoformat())
    dedans = verdict("entre", [du.isoformat(), au.isoformat()])
    apres_ou_egal = not avant and not dedans
    assert [avant, dedans, apres_ou_egal].count(True) == 1
    assert dedans == (du <= d < au)
    assert apres_ou_egal == (d >= au)


# --- cas qui verrouillent les derniers recoins ---------------------------------------------


def test_une_liste_vide_est_absente_et_une_liste_pleine_est_renseignee():
    absent = {"champ": "pieces", "op": "est_absent"}
    renseigne = {"champ": "pieces", "op": "est_renseigne"}
    assert ok("pieces", absent, {"pieces": []}) and ok("pieces", absent, {"pieces": ()})
    assert ok("pieces", absent, {})
    assert not ok("pieces", absent, {"pieces": [{"type": "facture"}]})
    assert ok("pieces", renseigne, {"pieces": [{"type": "facture"}]})
    assert not ok("pieces", renseigne, {"pieces": []})


def test_un_booleen_absent_n_est_ni_vrai_ni_faux():
    assert not ok("tresorerie", {"champ": "ecart_justifie", "op": "est_vrai"}, {})
    assert not ok("tresorerie", {"champ": "ecart_justifie", "op": "est_faux"}, {})


def test_nombre_eq_est_une_egalite_et_non_un_minimum():
    cond = {"champ": "pieces", "op": "nombre_eq", "valeur": 2}
    assert not ok("pieces", cond, {"pieces": [{}, {}, {}]})
    assert not ok("pieces", cond, {"pieces": [{}]})
    assert ok("pieces", cond, {"pieces": [{}, {}]})


def test_entre_prend_exactement_deux_dates():
    trois = {"champ": "date", "op": "entre", "valeur": ["2026-01-01", "2026-06-01", "2026-12-01"]}
    with pytest.raises(ConditionInvalide, match="deux dates"):
        preparer_expression(expr("codification", trois))


def test_une_liste_de_plus_de_deux_cents_valeurs_est_refusee():
    cond = {"champ": "categorie", "op": "in", "valeur": [f"C{i}" for i in range(201)]}
    with pytest.raises(ConditionInvalide, match="liste"):
        preparer_expression(expr("codification", cond))
    court = {"champ": "categorie", "op": "in", "valeur": [f"C{i}" for i in range(200)]}
    assert preparer_expression(expr("codification", court))


def test_le_contexte_refuse_un_float_en_le_nommant_et_un_booleen_pour_un_entier():
    montant = preparer_expression(expr("budget", {"champ": "montant", "op": "gt", "valeur": "1"}))
    with pytest.raises(TypeError, match="reçoit un float"):
        evaluer(montant, {"montant": 1.5})
    jours = preparer_expression(
        expr("avances", {"champ": "jours_depuis_versement", "op": "lte", "valeur": 90})
    )
    with pytest.raises(TypeError, match="bool"):
        evaluer(jours, {"jours_depuis_versement": True})  # True est un int en Python : refusé
