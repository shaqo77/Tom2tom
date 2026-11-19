# ruff: noqa: F811
"""Le profil BAD, livré comme donnée d'après les cinq documents de la Banque. Voir L11-D1.

Rien n'est inventé : chaque citation renvoie à une page d'un document identifié par son SHA-256,
et seule la périodicité recommandée de l'IFR est livrée comme délai chiffré (45 jours, trimestriel).
"""

import io
import re
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from niveau2_profils.models import TypeElement
from niveau2_profils.services.catalogue import charger_profil, lire_profil_livre
from niveau2_profils.services.citations import verifier_citations
from niveau2_profils.services.presentation import presenter_profil
from niveau2_profils.services.profils import _valider_exigence_type, importer_profil
from niveau3_config.models import Exigence
from tests.outils_documents import fabriquer_pdf
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_registre_exigences_bd import PAGES, _document, base  # noqa: F401

RACINE = Path(__file__).resolve().parents[2]
REGISTRE = (RACINE / "ANNEXE_B_REGISTRE_DES_SOURCES.md").read_text(encoding="utf-8")
FAMILLES = {
    "BAD-A1",
    "BAD-A2",
    "BAD-A3",
    "BAD-RECONCILIATION-CS",
    "BAD-GARANTIE-REMBOURSEMENT",
    "BAD-IFR",
    "BAD-ETATS-ANNUELS-AUDITES",
    "BAD-ETATS-FMM",
    "BAD-PLAN-TRESORERIE",
    "BAD-PCR",
}


def _elements():
    return {e["code"]: e for e in lire_profil_livre("bad")["elements"]}


# --- le fichier de catalogue (logique pure) ------------------------------------------------


def test_le_profil_bad_est_valide_bilingue_et_ne_se_dit_pas_universel():
    d = lire_profil_livre("bad")
    assert d["code"] == "BAD" and d["version"] == 2
    assert "n'est pas un modèle universel" in d["description"]["fr"]
    assert "lorsque requis" in d["description"]["fr"]
    assert "not a universal template" in d["description"]["en"]
    assert "when required" in d["description"]["en"]
    codes = [e["code"] for e in d["elements"]]
    assert len(codes) == len(set(codes))
    for e in d["elements"]:
        assert e["kind"] in TypeElement.values and set(e["label"]) == {"fr", "en"}, e["code"]
        if e.get("exigence"):
            _valider_exigence_type(e["exigence"])
            assert e["exigence"]["obligation"] == "optional", e["code"]


def test_les_familles_d_etats_du_profil_sont_celles_des_documents():
    familles = {c for c, e in _elements().items() if e["kind"] == "report_family"}
    assert familles == FAMILLES


def test_les_seuls_delais_livres_sont_l_ifr_trimestriel_et_l_annuel_sans_jours():
    delais = {
        c: (e["exigence"].get("periodicity"), e["exigence"].get("due_offset_days"))
        for c, e in _elements().items()
        if e.get("exigence")
        and (e["exigence"].get("periodicity") or e["exigence"].get("due_offset_days"))
    }
    # « six mois » n'est pas converti en jours : l'annuel n'a aucun décalage.
    assert delais == {"BAD-IFR": ("quarterly", 45), "BAD-ETATS-ANNUELS-AUDITES": ("annual", None)}


def test_chaque_source_existe_au_registre_et_l_empreinte_du_registre_est_celle_du_profil():
    documents = {
        e["contenu"]["source"]: e["contenu"]["sha256"]
        for e in _elements().values()
        if e["kind"] == "document_reference" and e["contenu"].get("sha256")
    }
    assert set(documents) == {f"SRC:bailleur:42{n}" for n in range(5)}
    for source, sha in documents.items():
        ligne = next(ln for ln in REGISTRE.splitlines() if ln.startswith(f"| `{source}`"))
        assert sha in ligne, source
    for e in _elements().values():
        for code in re.findall(r"SRC:[a-z]+:\d+", e["contenu"]["source"]):
            assert f"`{code}`" in REGISTRE, code


def test_chaque_citation_a_une_source_connue_une_page_valide_et_un_extrait():
    elements = _elements()
    pages = {
        e["contenu"]["source"]: e["contenu"]["pages"]
        for e in elements.values()
        if e["kind"] == "document_reference" and e["contenu"].get("pages")
    }
    total = 0
    for code, e in elements.items():
        for c in e["contenu"].get("citations", []):
            total += 1
            assert c["source"] in pages and c["source"] in e["contenu"]["source"], code
            assert 1 <= c["page"] <= pages[c["source"]], (code, c)
            assert len(c["quote"].strip()) > 10, (code, c)
    assert total >= 70  # le profil repose sur des citations, pas sur des affirmations


def test_les_anciennes_lignes_directrices_ne_sont_jamais_citees_litteralement():
    # Leur couche texte est dégradée : on les a lues, on ne les cite pas.
    for e in _elements().values():
        assert all(c["source"] != "SRC:bailleur:421" for c in e["contenu"].get("citations", []))


def test_les_parametres_chiffres_viennent_des_documents():
    el = _elements()
    assert el["BAD-CTRL-NUMEROTATION"]["contenu"]["parametres"] == {
        "chiffres_max": 4,
        "suffixe_agence_caracteres": 3,
        "suffixe_justification_seule": "JUS",
        "numero_annule_non_reattribue": True,
        "numerotation_distincte_pret_et_don": True,
    }
    cs = el["BAD-CTRL-COMPTE-SPECIAL-REAPPROVISIONNEMENT"]["contenu"]["parametres"]
    assert cs["avance_precedente_justifiee_pct_min"] == 50
    assert cs["avances_plus_anciennes_justifiees_pct"] == 100
    assert cs["derniere_reconstitution_mois_avant_cloture"] == 6
    assert cs["remboursement_du_solde_mois_apres_cloture"] == 4
    assert el["BAD-CTRL-DELAI-DEMANDES"]["contenu"]["parametres"] == {
        "mois_apres_cloture": 4,
        "prolongation_demandee_mois_avant_cloture": 6,
    }
    m = el["BAD-METHODES-DECAISSEMENT"]["contenu"]["parametres"]
    assert m["approbation_prealable"] == ["special_account"]
    assert m["correspondance"]["reimbursement_guarantee"] == "special_commitment"


def test_aucun_montant_ni_taux_de_financement_n_est_livre():
    # Ces valeurs sont propres à l'accord de financement de chaque projet.
    texte = str(lire_profil_livre("bad")["elements"])
    assert "taux_de_financement" not in texte and "plafond" not in texte


# --- la vérification des citations (PDF fabriqués) ----------------------------------------------


def _donnees(sha, page=2, quote="La demande porte un numéro"):
    return {
        "elements": [
            {
                "kind": "document_reference",
                "code": "DOC",
                "contenu": {"source": "SRC:x:1", "sha256": sha},
            },
            {
                "kind": "check",
                "code": "C",
                "contenu": {"citations": [{"source": "SRC:x:1", "page": page, "quote": quote}]},
            },
        ]
    }


def _dossier(tmp_path):
    import hashlib

    pdf = fabriquer_pdf(["Premier texte", "La demande porte un numéro de série"])
    (tmp_path / "doc.pdf").write_bytes(pdf)
    return hashlib.sha256(pdf).hexdigest()


def test_une_citation_a_la_bonne_page_est_verifiee(tmp_path):
    r = verifier_citations(_donnees(_dossier(tmp_path)), tmp_path)
    assert (r.verifiees, r.echecs, r.non_verifiables, r.conforme) == (1, [], [], True)


def test_une_citation_a_la_mauvaise_page_ou_inventee_echoue(tmp_path):
    sha = _dossier(tmp_path)
    assert verifier_citations(_donnees(sha, page=1), tmp_path).echecs
    assert verifier_citations(_donnees(sha, page=9), tmp_path).echecs
    assert verifier_citations(_donnees(sha, quote="phrase inventée"), tmp_path).echecs


def test_un_document_absent_rend_ses_citations_non_verifiables_et_non_vraies(tmp_path):
    r = verifier_citations(_donnees("0" * 64), tmp_path)
    assert r.verifiees == 0 and r.non_verifiables == [("C", "SRC:x:1")] and not r.conforme


def test_la_commande_refuse_un_dossier_sans_les_documents_et_le_tolere_sur_demande(tmp_path):
    with pytest.raises(CommandError, match="non vérifiable"):
        call_command("verifier_citations_profil", "bad", dossier=str(tmp_path))
    sortie = io.StringIO()
    call_command(
        "verifier_citations_profil",
        "bad",
        dossier=str(tmp_path),
        tolerer_absents=True,
        stdout=sortie,
        stderr=io.StringIO(),
    )
    assert "0 citation(s) vérifiée(s)" in sortie.getvalue()
    with pytest.raises(CommandError, match="Dossier introuvable"):
        call_command("verifier_citations_profil", "bad", dossier=str(tmp_path / "absent"))


# --- le chargement générique ---------------------------------------------------------------------

pytestmark_bd = pytest.mark.django_db(transaction=True)


@pytestmark_bd
def test_le_profil_bad_se_charge_se_publie_et_se_lit_lorsque_requis(base):
    _, _, profils = base
    profil = charger_profil(utilisateur=profils["dora"], nom="bad", publier=True)
    assert (profil.status, profil.code, profil.version) == ("published", "BAD", 2)
    vue = presenter_profil(profil)
    assert {e["mention"] for e in vue["elements"]} == {"lorsque requis"}
    assert len(vue["elements"]) == len(lire_profil_livre("bad")["elements"])


@pytestmark_bd
def test_importer_le_profil_bad_ne_produit_que_des_propositions(base):
    _, projet, profils = base
    profil = charger_profil(utilisateur=profils["dora"], nom="bad", publier=True)
    resultat = importer_profil(
        utilisateur=profils["dora"],
        profil=profil,
        project_id=projet.id,
        document=_document(profils, projet, fabriquer_pdf(PAGES)),
    )
    assert {e.code for e in resultat.creees} == FAMILLES
    assert set(Exigence.objects.values_list("status", flat=True)) == {"proposed"}
    ifr = Exigence.objects.get(code="BAD-IFR")
    assert (ifr.periodicity, ifr.due_offset_days, ifr.obligation) == ("quarterly", 45, "optional")
    annuel = Exigence.objects.get(code="BAD-ETATS-ANNUELS-AUDITES")
    assert (annuel.periodicity, annuel.due_offset_days) == ("annual", None)
