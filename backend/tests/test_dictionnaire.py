"""Le dictionnaire de données publié. Voir L8-T04.

Il est généré depuis les modèles ; le fichier publié ne peut pas vieillir en silence.
"""

from pathlib import Path

from django.apps import apps

from core.dictionnaire import dictionnaire, rendre_markdown

PUBLIE = Path(__file__).resolve().parents[2] / "DICTIONNAIRE_DE_DONNEES.md"


def test_le_dictionnaire_publie_est_celui_que_les_modeles_produisent():
    attendu = rendre_markdown(dictionnaire())
    assert PUBLIE.read_text(encoding="utf-8") == attendu, (
        "DICTIONNAIRE_DE_DONNEES.md est périmé : python manage.py generer_dictionnaire"
    )


def test_chaque_table_des_modeles_figure_au_dictionnaire_avec_sa_cle_primaire():
    tables = {t["table"]: t for t in dictionnaire()["tables"]}
    attendues = {m._meta.db_table for m in apps.get_models() if not m._meta.proxy}
    assert attendues <= set(tables)
    for t in tables.values():
        assert sum(c["cle_primaire"] for c in t["colonnes"]) == 1, t["table"]


def test_le_dictionnaire_est_deterministe():
    assert dictionnaire() == dictionnaire()
    assert rendre_markdown(dictionnaire()) == rendre_markdown(dictionnaire())


def test_aucune_colonne_n_est_un_flottant():
    """Règle 1 : un montant n'est jamais un flottant, et aucune colonne ne l'est."""
    flottants = [
        f"{t['table']}.{c['nom']}"
        for t in dictionnaire()["tables"]
        for c in t["colonnes"]
        if c["type"] in ("double precision", "real") or c["type"].startswith("float")
    ]
    assert flottants == []


def test_les_relations_et_les_montants_sont_decrits():
    tables = {t["table"]: t for t in dictionnaire()["tables"]}
    colonnes = {c["nom"]: c for c in tables["comptabilite_ligneecriture"]["colonnes"]}
    assert colonnes["debit"]["type"] == "numeric(20, 4)"
    assert colonnes["entry_id"]["reference"] == "comptabilite_ecriture.id"
    assert colonnes["org_id"]["description"].startswith("Organisation propriétaire")
    assert tables["comptabilite_ligneecriture"]["isole_par_organisation"] is True
    assert any(
        c["nom"] == "ligne_un_seul_sens"
        for c in tables["comptabilite_ligneecriture"]["contraintes"]
    )


def test_les_tables_isolees_sont_exactement_celles_qui_portent_org_id():
    for t in dictionnaire()["tables"]:
        assert t["isole_par_organisation"] == any(c["nom"] == "org_id" for c in t["colonnes"])
