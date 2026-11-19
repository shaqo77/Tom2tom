# ruff: noqa: F811, E501
"""Les profils BAD, UE, FIDA, Fonds mondial, BID et Nations unies, livrés comme DONNÉES. L10-T01.

Rien n'est inventé : chaque élément cite sa source du registre (`ANNEXE_B`) ou le dossier d'apports
qui le justifie ; aucun délai ni aucune périodicité n'est livré tant qu'un document du bailleur ne
les donne pas. Le critère de recette : ajouter un profil et un modèle sans application nouvelle ni
ligne de code, et produire deux états de bailleurs différents sur les MÊMES données.
"""

import datetime
import json
import re
import shutil
import uuid
from pathlib import Path

import pytest
from django.utils import timezone

from niveau2_profils.models import TypeElement
from niveau2_profils.services import catalogue
from niveau2_profils.services.catalogue import charger_profil, lire_profil_livre, profils_livres
from niveau2_profils.services.presentation import presenter_profil
from niveau2_profils.services.profils import _valider_exigence_type, importer_profil
from niveau3_config.models import Exigence
from niveau4_reporting import modeles_etats
from niveau4_reporting.mapping.models import RegleMapping, TableMapping
from niveau4_reporting.modeles_etats import (
    lire_modele_livre,
    modele_rapprochement_compte_designe,
    modeles_livres,
)
from niveau4_reporting.moteur.compilateur import compiler
from niveau4_reporting.publication.rapports import publier_rapport, regenerer
from tests.outils_documents import fabriquer_pdf
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_regeneration_bd import _piece, pub  # noqa: F401
from tests.test_registre_exigences_bd import PAGES, _document, base  # noqa: F401

RACINE = Path(__file__).resolve().parents[2]
PROFILS = {
    "union_europeenne": "UNION_EUROPEENNE",
    "fida": "FIDA",
    "fonds_mondial": "FONDS_MONDIAL",
    "bid": "BID",
    "nations_unies": "NATIONS_UNIES",
}
FORMULAIRES = {
    "fida": {"FIDA-100", "FIDA-104", "FIDA-105"},
    "union_europeenne": {"UE-DEVIS-PROGRAMMES", "UE-MEMOIRES"},
    "fonds_mondial": set(),
    "bid": set(),
    "nations_unies": set(),
}


# --- les six profils comme données (logique pure) ----------------------------------------------


def test_le_catalogue_livre_les_sept_profils_de_la_specification():
    assert {"banque_mondiale", *PROFILS} <= set(profils_livres())
    for nom, code in PROFILS.items():
        assert lire_profil_livre(nom)["code"] == code


@pytest.mark.parametrize("nom", PROFILS)
def test_un_profil_livre_est_valide_bilingue_et_ne_se_dit_pas_universel(nom):
    d = lire_profil_livre(nom)
    assert set(d["label"]) == {"fr", "en"} and d["elements"]
    assert (
        "n'est pas un modèle universel" in d["description"]["fr"]
        and "lorsque requis" in d["description"]["fr"]
    )
    assert (
        "not a universal template" in d["description"]["en"]
        and "when required" in d["description"]["en"]
    )
    codes = [e["code"] for e in d["elements"]]
    assert len(codes) == len(set(codes))
    for e in d["elements"]:
        assert e["kind"] in TypeElement.values and set(e["label"]) == {"fr", "en"}, e["code"]
        if e.get("exigence") is not None:
            _valider_exigence_type(e["exigence"])
            assert e["exigence"]["obligation"] == "optional", e[
                "code"
            ]  # le profil met à disposition


@pytest.mark.parametrize("nom", PROFILS)
def test_aucun_delai_ni_periodicite_n_est_invente(nom):
    for e in lire_profil_livre(nom)["elements"]:
        exigence = e.get("exigence") or {}
        assert not exigence.get("periodicity") and not exigence.get("due_offset_days"), e["code"]
        assert "delai_type" not in (e.get("contenu") or {}), e["code"]


@pytest.mark.parametrize("nom", PROFILS)
def test_chaque_element_cite_sa_source_et_la_source_existe(nom):
    registre = (RACINE / "ANNEXE_B_REGISTRE_DES_SOURCES.md").read_text(encoding="utf-8")
    for e in lire_profil_livre(nom)["elements"]:
        source = (e.get("contenu") or {}).get("source")
        assert source, f"{nom}/{e['code']} sans source"
        for code in re.findall(r"SRC:[a-z]+:\d+", source):
            assert f"`{code}`" in registre, f"{code} absent du registre des sources"
        for fichier in re.findall(r"[\w.]+\.md", source):
            assert (RACINE / fichier).exists(), fichier


@pytest.mark.parametrize("nom", PROFILS)
def test_les_formulaires_connus_sont_nommes_sans_pretendre_a_leur_contenu(nom):
    familles = {
        e["code"] for e in lire_profil_livre(nom)["elements"] if e["kind"] == "report_family"
    }
    assert familles == FORMULAIRES[nom]
    for e in lire_profil_livre(nom)["elements"]:
        if e["kind"] == "report_family":
            assert "à préciser" in e["label"]["fr"] and "to be confirmed" in e["label"]["en"], e[
                "code"
            ]


# --- le chargement générique ---------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("nom", PROFILS)
def test_chaque_profil_se_charge_par_le_meme_mecanisme_que_la_banque_mondiale(base, nom):
    _, _, profils = base
    profil = charger_profil(utilisateur=profils["dora"], nom=nom, publier=True)
    assert (profil.status, profil.code) == ("published", PROFILS[nom])
    vue = presenter_profil(profil)
    assert {e["mention"] for e in vue["elements"]} == {"lorsque requis"}
    assert len(vue["elements"]) == len(lire_profil_livre(nom)["elements"])


@pytest.mark.django_db(transaction=True)
def test_importer_un_profil_livre_ne_produit_que_des_propositions(base):
    organisation, projet, profils = base
    profil = charger_profil(utilisateur=profils["dora"], nom="fida", publier=True)
    resultat = importer_profil(
        utilisateur=profils["dora"],
        profil=profil,
        project_id=projet.id,
        document=_document(profils, projet, fabriquer_pdf(PAGES)),
    )
    attendues = {e["code"] for e in lire_profil_livre("fida")["elements"] if e.get("exigence")}
    assert {e.code for e in resultat.creees} == attendues == {"FIDA-100", "FIDA-104", "FIDA-105"}
    # Rien n'est activé d'office (règle 9), et aucun délai ni aucune périodicité n'est posé.
    assert set(Exigence.objects.values_list("status", flat=True)) == {"proposed"}
    assert all(not e.periodicity and e.due_offset_days is None for e in Exigence.objects.all())


# --- le catalogue de modèles d'états -------------------------------------------------------------


def test_les_modeles_d_etats_se_livrent_comme_donnees():
    assert "rapprochement_compte_designe" in modeles_livres()
    json_brut = json.loads(
        (modeles_etats.DOSSIER / "rapprochement_compte_designe.json").read_text(encoding="utf-8")
    )
    assert lire_modele_livre("rapprochement_compte_designe") == json_brut
    assert modele_rapprochement_compte_designe()["code"] == "RCD"
    assert modele_rapprochement_compte_designe(version=3)["version"] == 3
    with pytest.raises(FileNotFoundError, match="rapprochement_compte_designe"):
        lire_modele_livre("../../etc/passwd")  # liste blanche : jamais un morceau de chemin


@pytest.mark.parametrize("nom", modeles_livres())
def test_chaque_modele_livre_se_compile(nom):
    modele = lire_modele_livre(nom)
    mappings = {
        ligne["select"]["mapping"]: []
        for ligne in modele["rows"]
        if ligne.get("type") == "aggregate" and ligne["select"].get("mapping")
    }
    compiler(
        modele,
        mappings,
        {
            "project_id": str(uuid.uuid4()),
            "fiscal_year": 2026,
            "current_period": 3,
            "compte_designe": "X",
            "date_debut": "2026-01-01",
            "date_fin": "2026-03-31",
        },
    )


# --- le critère de recette : un profil et un modèle SANS code ------------------------------------

PROFIL_ESSAI = {
    "code": "BAILLEUR_ESSAI", "version": 1,
    "label": {"fr": "Bailleur d'essai", "en": "Test donor"},
    "description": {
        "fr": "Profil d'essai : bibliothèque d'exigences possibles, ce n'est pas un modèle universel ; chaque élément se lit « lorsque requis ».",
        "en": "Test profile: library of possible requirements, not a universal template; each element reads “when required”.",
    },
    "elements": [
        {"kind": "report_family", "code": "ETAT-ESSAI",
         "label": {"fr": "État d'essai", "en": "Test statement"},
         "contenu": {"source": "essai"},
         "exigence": {"subject": {"fr": "État d'essai", "en": "Test statement"},
                      "rule": {"kind": "report", "template": "ESSAI"}, "obligation": "optional"}},
    ],
}  # fmt: skip


@pytest.mark.django_db(transaction=True)
def test_ajouter_un_profil_et_un_modele_ne_demande_aucun_code(base, tmp_path, monkeypatch):
    """Deux fichiers déposés dans les catalogues, et rien d'autre : ni application, ni module."""
    _, _, profils = base
    profils_dir, modeles_dir = tmp_path / "profils", tmp_path / "modeles"
    shutil.copytree(catalogue.DOSSIER, profils_dir)
    shutil.copytree(modeles_etats.DOSSIER, modeles_dir)
    (profils_dir / "bailleur_essai.json").write_text(json.dumps(PROFIL_ESSAI), encoding="utf-8")
    (modeles_dir / "etat_essai.json").write_text(
        json.dumps({"code": "ESSAI", "version": 1, "columns": [{"code": "YTD", "period": "year_to_date"}],
                    "rows": [{"code": "R1", "type": "aggregate", "select": {"mapping": "X", "target": "CHARGES"}}]}),
        encoding="utf-8",
    )  # fmt: skip
    monkeypatch.setattr(catalogue, "DOSSIER", profils_dir)
    monkeypatch.setattr(modeles_etats, "DOSSIER", modeles_dir)
    assert "bailleur_essai" in profils_livres() and "etat_essai" in modeles_livres()
    profil = charger_profil(utilisateur=profils["dora"], nom="bailleur_essai", publier=True)
    assert profil.code == "BAILLEUR_ESSAI" and profil.elements.count() == 1
    assert lire_modele_livre("etat_essai")["code"] == "ESSAI"


# --- deux bailleurs, les mêmes données -----------------------------------------------------------

MODELE_A = {
    "code": "ETAT-A", "version": 1, "columns": [{"code": "T", "period": "current_quarter"}],
    "rows": [
        {"code": "A10", "type": "aggregate", "select": {"mapping": "BAILLEUR-A", "target": "DEPENSES"}},
        {"code": "A20", "type": "aggregate", "select": {"mapping": "BAILLEUR-A", "target": "BANQUE"}},
        {"code": "A90", "type": "computed", "formula": "A10 + A20"},
    ],
}  # fmt: skip
MODELE_B = {
    "code": "ETAT-B", "version": 1, "columns": [{"code": "T", "period": "current_quarter"}, {"code": "CUM", "period": "year_to_date"}],
    "rows": [
        {"code": "B1", "type": "heading"},
        {"code": "B2", "type": "aggregate", "select": {"mapping": "BAILLEUR-B", "target": "CATEGORIE_1"}},
        {"code": "B3", "type": "aggregate", "select": {"mapping": "BAILLEUR-B", "target": "LIQUIDITES"}},
    ],
}  # fmt: skip


def _table(organisation, projet, code, regles):
    table = TableMapping.objects.create(
        org_id=organisation.id, project_id=projet.id, donor_profile_id=uuid.uuid4(), code=code, version=1,
        valid_from=datetime.date(2026, 1, 1), status="active", validated_by=uuid.uuid4(), validated_at=timezone.now(),
    )  # fmt: skip
    for priorite, comptes, cible in regles:
        RegleMapping.objects.create(
            org_id=organisation.id,
            table=table,
            priority=priorite,
            match={"accounts": comptes},
            target_code=cible,
        )
    return table


@pytest.mark.django_db(transaction=True)
def test_deux_bailleurs_differents_lisent_les_memes_donnees_dans_leur_propre_nomenclature(pub):
    organisation, projet, profils, _ = pub
    _piece(
        organisation, projet, "6011", "5211", "75.25", periode=3
    )  # une écriture de plus, en mars
    table_a = _table(
        organisation,
        projet,
        "BAILLEUR-A",
        [
            (10, [["6000", "6279"]], "DEPENSES"),
            (20, [["5200", "5299"]], "BANQUE"),
            (90, [["8999", "8999"]], "HORS_ETAT"),
        ],
    )
    table_b = _table(
        organisation,
        projet,
        "BAILLEUR-B",
        [
            (10, [["6000", "6279"]], "CATEGORIE_1"),
            (20, [["5200", "5299"]], "LIQUIDITES"),
            (90, [["8999", "8999"]], "HORS_ETAT"),
        ],
    )
    commun = {
        "utilisateur": profils["pia"], "project_id": projet.id, "params": {"fiscal_year": 2026, "current_period": 3},
        "period_from": datetime.date(2026, 1, 1), "period_to": datetime.date(2026, 3, 31),
    }  # fmt: skip
    a = publier_rapport(modele=MODELE_A, tables={"BAILLEUR-A": table_a}, **commun)
    b = publier_rapport(modele=MODELE_B, tables={"BAILLEUR-B": table_b}, **commun)
    # Les MÊMES données : même empreinte du jeu de données, même chiffre de charges.
    assert a.dataset_hash == b.dataset_hash
    assert a.values["A10/T"] == b.values["B2/T"] == "225.35"  # 100 + 50,10 + 75,25
    # Deux états DIFFÉRENTS : rubriques, colonnes et nomenclature propres à chaque bailleur.
    assert {k.split("/")[0] for k in a.values} == {"A10", "A20", "A90"}
    assert {k.split("/")[0] for k in b.values} == {"B1", "B2", "B3"}
    assert "B2/CUM" in b.values and "A10/CUM" not in a.values
    assert a.template_code != b.template_code and bytes(a.seal) != bytes(b.seal)
    assert a.mapping_versions.keys() == {"BAILLEUR-A"} and b.mapping_versions.keys() == {
        "BAILLEUR-B"
    }
    # Chacun se régénère à l'identique.
    assert regenerer(a).identique and regenerer(b).identique
