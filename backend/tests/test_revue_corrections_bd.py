# ruff: noqa: F811, E501
"""Corrections issues de la revue de code du lot L6 : un test par constat, écrit pour ÉCHOUER
avant la correction (voir le message de commit de chaque point).
"""

import datetime
import io
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pypdf
import pytest
from django.db import connection, connections

from core.erreurs import CodeErreur, ErreurMetier
from niveau1_socle.habilitations.models import OPERATIONS
from niveau4_reporting.controles import bibliotheque as lib
from niveau4_reporting.controles.circuit import creer_circuit, decider_etape, ouvrir_demande
from niveau4_reporting.controles.models import EvaluationControle
from niveau4_reporting.controles.services import (
    activer_controle,
    controles_en_attente,
    exiger_controles_tranches,
    valider_controle,
)
from niveau4_reporting.publication.exports import exporter_rapport, rendre_excel, rendre_pdf
from niveau4_reporting.publication.rapports import publier_rapport, regenerer
from niveau4_reporting.publication.revue import simuler_revue
from tests.test_avances_bd import _verser
from tests.test_avances_bd import cadre as cadre_avances  # noqa: F401
from tests.test_circuit_validation_bd import ETAPES, cir  # noqa: F401
from tests.test_controles_bd import _actif, _creer, _evaluer, ctl  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_exports_rapport_bd import rapport  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_rattachement_bd import cadre_config  # noqa: F401
from tests.test_regeneration_bd import MODELE, _piece, pub  # noqa: F401
from tests.test_revue_bailleur_bd import revue  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
D = datetime.date
M = Decimal


# --- 1. une nouvelle version d'un contrôle remplace l'ancienne dans le blocage ---------------


def test_une_nouvelle_version_reussie_leve_le_blocage_de_l_ancienne(ctl):
    _, projet, profils, _ = ctl
    v1 = _actif(ctl)
    objet = uuid.uuid4()
    _evaluer(v1, {"depense_cumulee": M("2000")}, ctl, objet_id=objet)  # bloquant sous la v1
    v2 = _creer(ctl, valid_from=D(2027, 1, 1))
    valider_controle(utilisateur=profils["vera"], controle=v2)
    v2 = activer_controle(utilisateur=profils["vera"], controle=v2)
    _evaluer(v2, {"depense_cumulee": M("900")}, ctl, date=D(2027, 2, 1), objet_id=objet)
    assert controles_en_attente(projet.id, "depense", objet, D(2027, 2, 1)) == []
    exiger_controles_tranches(projet.id, "depense", objet, D(2027, 2, 1))


# --- 2. la simulation ne modifie pas l'état réel ----------------------------------------------


def test_la_simulation_n_ecrit_aucune_evaluation_et_ne_bloque_rien(revue):
    organisation, projet, profils, agents = revue
    avance = _verser(projet, profils, agents, montant="1000", date=D(2026, 2, 1))
    simulation = simuler_revue(
        utilisateur=profils["pia"], project_id=projet.id, date_effet=D(2026, 3, 10)
    )
    assert simulation.avis == "no_go"  # elle a bien vu l'anomalie…
    assert EvaluationControle.objects.count() == 0  # …sans rien écrire dans le journal réel
    assert controles_en_attente(projet.id, "avance", avance.pk, D(2026, 3, 10)) == []


# --- 3. le contexte d'une demande est validé -------------------------------------------------


def _circuit_a_seuil(cir):
    (_, projet, profils, _), _ = cir
    creer_circuit(
        utilisateur=profils["dora"], project_id=projet.id, objet_type="marche",
        valid_from=D(2026, 1, 1),
        etapes=[ETAPES[0], {**ETAPES[1], "condition": {"montant_min": "100000"}}],
    )  # fmt: skip
    return projet, profils


def _ouvrir_marche(projet, profils, contexte):
    return ouvrir_demande(
        utilisateur=profils["samir"], project_id=projet.id, objet_type="marche",
        objet_id=uuid.uuid4(), date_effet=D(2026, 6, 15), contexte=contexte,
    )  # fmt: skip


@pytest.mark.parametrize(
    "contexte",
    [{}, {"categorie": "X"}, {"montant": "beaucoup"}, {"montant": "NaN"}, {"montant": "-5"}],
)
def test_un_contexte_incomplet_ou_invalide_est_refuse_a_l_ouverture(cir, contexte):
    projet, profils = _circuit_a_seuil(cir)
    with pytest.raises(ErreurMetier) as e:
        _ouvrir_marche(projet, profils, contexte)
    assert e.value.code == CodeErreur.REGLE_INVALIDE


def test_un_seuil_non_fini_est_refuse_a_la_creation_du_circuit(cir):
    (_, projet, profils, _), _ = cir
    for seuil in ("NaN", "Infinity", "-1"):
        with pytest.raises(ErreurMetier):
            creer_circuit(
                utilisateur=profils["dora"], project_id=projet.id, objet_type="x",
                valid_from=D(2026, 1, 1),
                etapes=[{**ETAPES[0], "condition": {"montant_min": seuil}}],
            )  # fmt: skip


def test_un_contexte_valide_applique_le_seuil(cir):
    projet, profils = _circuit_a_seuil(cir)
    assert _ouvrir_marche(projet, profils, {"montant": "100"}).rang_courant == 1
    petite = _ouvrir_marche(projet, profils, {"montant": "100"})
    decider_etape(utilisateur=profils["lea"], demande=petite, rang=1, approuver=True)
    assert petite.statut == "approuvee"  # l'étape à seuil ne s'applique pas à 100


# --- 4. une personne ne signe qu'une étape par demande ---------------------------------------


def test_une_meme_personne_ne_signe_pas_deux_etapes_d_une_demande(cir):
    (organisation, projet, profils, _), _ = cir
    from tests.test_derogations_bd import _utilisateur

    double = _utilisateur(organisation, projet, "double", ["consulter", "valider", "publier"])
    demande = ouvrir_demande(
        utilisateur=profils["samir"], project_id=projet.id, objet_type="depense",
        objet_id=uuid.uuid4(), date_effet=D(2026, 6, 15),
    )  # fmt: skip
    decider_etape(utilisateur=double, demande=demande, rang=1, approuver=True)
    with pytest.raises(ErreurMetier) as e:
        decider_etape(utilisateur=double, demande=demande, rang=2, approuver=True)
    assert e.value.code == CodeErreur.APPROBATION_REQUISE
    assert demande.statut == "en_cours"
    decider_etape(utilisateur=profils["coord"], demande=demande, rang=2, approuver=True)
    assert demande.statut == "approuvee"


# --- 5. la publication lit un état cohérent --------------------------------------------------


def test_une_ecriture_posee_pendant_la_generation_ne_cree_pas_de_fausse_alerte(pub, monkeypatch):
    organisation, projet, profils, table = pub
    from niveau4_reporting.publication import rapports

    reel, deja = rapports.generer, []

    def generer_puis_ecriture_concurrente(*args, **kwargs):
        produit = reel(*args, **kwargs)
        if not deja:  # une pièce est comptabilisée pendant la première génération
            deja.append(_piece(organisation, projet, "6011", "5211", "33"))
        return produit

    monkeypatch.setattr(rapports, "generer", generer_puis_ecriture_concurrente)
    publie = publier_rapport(
        utilisateur=profils["pia"], project_id=projet.id, modele=MODELE,
        params={"fiscal_year": 2026, "current_period": 3}, tables={"WB": table},
        period_from=D(2026, 1, 1), period_to=D(2026, 3, 31),
    )  # fmt: skip
    monkeypatch.setattr(rapports, "generer", reel)
    resultat = regenerer(publie)
    assert resultat.identique, (resultat.ecarts, resultat.inexpliquee)
    assert publie.values["R110/QTR"] == "183.1"  # 100 + 50,10 + 33 : la pièce est dans le rapport


@pytest.mark.parametrize(
    "champs",
    [{"period_to": D(2026, 6, 30)}, {"period_to": D(2025, 3, 31)}, {"period_from": D(2026, 4, 1)}],
)
def test_la_periode_du_rapport_doit_correspondre_aux_parametres(pub, champs):
    organisation, projet, profils, table = pub
    base = {
        "utilisateur": profils["pia"], "project_id": projet.id, "modele": MODELE,
        "params": {"fiscal_year": 2026, "current_period": 3}, "tables": {"WB": table},
        "period_from": D(2026, 1, 1), "period_to": D(2026, 3, 31),
    }  # fmt: skip
    with pytest.raises(ErreurMetier) as e:
        publier_rapport(**{**base, **champs})
    assert e.value.code == CodeErreur.REGLE_INVALIDE


# --- 6. la contrainte de base suit l'ensemble fermé des habilitations -----------------------


def test_la_contrainte_des_etapes_couvre_toutes_les_habilitations():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'etape_operation_fermee'"
        )
        definition = cur.fetchone()[0]
    dans_la_base = set(re.findall(r"'([a-z_]+)'", definition))
    assert dans_la_base == set(OPERATIONS)


def test_une_etape_voir_numero_compte_se_cree(cir):
    (_, projet, profils, _), _ = cir
    creer_circuit(
        utilisateur=profils["dora"], project_id=projet.id, objet_type="rib",
        valid_from=D(2026, 1, 1),
        etapes=[{**ETAPES[0], "operation": "voir_numero_compte"}],
    )  # fmt: skip


# --- 7. un seuil à zéro est un seuil, pas une absence ---------------------------------------


def test_un_seuil_de_risque_a_zero_est_conserve():
    assert lib.risque_rejets_repetes(maximum=0).expression["conditions"][0]["valeur"] == 0
    assert lib.risque_avance_non_apuree(delai_jours=0).expression["conditions"][0]["valeur"] == 0
    assert (
        lib.risque_categorie_consommee(seuil_pct="0").expression["conditions"][0]["valeur"] == "0"
    )
    assert lib.risque_rejets_repetes().expression["conditions"][0]["valeur"] != 0  # le défaut reste


# --- 8. ni français en dur dans le journal ni dans les refus de formule --------------------


def test_le_journal_d_evaluation_ne_porte_pas_de_texte_de_langue():
    from niveau4_reporting.controles import conditions

    conditions.SCHEMAS["_essai"] = {
        "lignes": conditions.Champ(
            conditions.TypeChamp.LISTE, (("montant", conditions.TypeChamp.DECIMAL),)
        )
    }
    try:
        brut = {
            "type_regle": "_essai",
            "conditions": [
                {"champ": "lignes", "op": "somme_lte", "somme_de": "montant", "valeur": "5"}
            ],
        }
        constat = conditions.evaluer(
            conditions.preparer_expression(brut), {"lignes": [{"montant": M("1")}]}
        )[0]
    finally:
        del conditions.SCHEMAS["_essai"]
    for texte in (str(constat.attendu), str(constat.constate)):
        assert not re.search(r"somme de|élément|[éèàù]", texte), texte  # aucun mot de langue
    assert str(constat.attendu) == "sum(montant) <= 5"


def test_les_refus_de_formule_et_d_assertion_passent_par_le_catalogue():
    from core.i18n import catalogue
    from niveau4_reporting.moteur.assertions import AssertionInvalide, analyser_assertion
    from niveau4_reporting.moteur.formules import FormuleInvalide, valider

    with pytest.raises(FormuleInvalide) as f:
        valider("[x for x in range(3)]", ["R1"])
    with pytest.raises(AssertionInvalide) as a:
        analyser_assertion("R1 is R2", ["R1", "R2"])
    for erreur in (f.value, a.value):
        assert hasattr(erreur.args[0], "rendre"), type(erreur.args[0])  # un Message catalogué
    assert "formules.construction_interdite" in catalogue()["en"]


# --- 9. le PDF formate comme la langue du lecteur -------------------------------------------


def test_le_pdf_francais_ecrit_les_montants_a_la_francaise(rapport):
    publie, profils = rapport
    publie.values = {**publie.values, "R110/QTR": "1234567.5"}
    texte = pypdf.PdfReader(io.BytesIO(rendre_pdf(publie, "fr"))).pages[0].extract_text()
    assert "1 234 567,50" in texte.replace("\xa0", " ").replace(" ", " ")
    assert "2026-01-01" not in texte  # la date suit la langue
    texte_en = pypdf.PdfReader(io.BytesIO(rendre_pdf(publie, "en"))).pages[0].extract_text()
    assert "1,234,567.50" in texte_en


def test_le_formatage_d_un_montant_suit_les_decimales_de_la_devise():
    from core.i18n import formater_montant

    assert formater_montant(M("1234.5"), "fr", decimales=0) == "1 235"
    assert formater_montant(M("1234.5"), "en", decimales=3) == "1,234.500"
    assert formater_montant(M("1234.5"), "fr") == "1 234,50"


# --- 10. l'export résiste aux titres de feuille invalides et à la concurrence ---------------


def test_un_code_de_modele_avec_des_caracteres_interdits_s_exporte(rapport):
    publie, profils = rapport
    publie.template_code = "WB/IFR:Q1?[*]"
    import openpyxl

    classeur = openpyxl.load_workbook(io.BytesIO(rendre_excel(publie, "fr")))
    assert re.fullmatch(r"[^/\\?*\[\]:]{1,31}", classeur.active.title)


def _exporter_en_concurrence(org_id, user_id, rapport_id, barriere):
    from django.contrib.auth import get_user_model

    from niveau4_reporting.publication.models import RapportPublie

    try:
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [str(org_id)])
        barriere.wait()
        fichier = exporter_rapport(
            utilisateur=get_user_model().objects.get(pk=user_id),
            rapport=RapportPublie.objects.get(pk=rapport_id),
            format="xlsx",
        )
        return str(fichier.pk)
    finally:
        connections.close_all()


def test_deux_exports_simultanes_du_meme_fichier_donnent_le_meme_fichier(rapport):
    publie, profils = rapport
    barriere = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futurs = [
            pool.submit(
                _exporter_en_concurrence, publie.org_id, profils["pia"].id, publie.pk, barriere
            )
            for _ in range(2)
        ]
        identifiants = {f.result() for f in futurs}
    assert len(identifiants) == 1
