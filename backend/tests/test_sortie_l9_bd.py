# ruff: noqa: F811, E501
"""Contrôle de sortie du lot L9 : un engagement bloqué faute d'avis de non-objection.

Correspondance entre le contrôle de chaque tâche du plan et le test qui le démontre (le premier
test vérifie que chaque test cité existe). Puis le scénario de bout en bout : un marché soumis à
avis refuse l'engagement, l'accepte dès réception, le contrat et son avenant s'appuient sur les
avis, deux décomptes apurent exactement l'engagement du marché, la trésorerie du compte désigné se
rapproche du relevé.
"""

import datetime
import re
from decimal import Decimal
from pathlib import Path

import pytest

from core.audit import verifier_chaine
from niveau1_socle.budget.engagements import creer_engagement
from niveau1_socle.budget.services import BudgetInvalide
from niveau1_socle.budget.soldes import comparer_soldes, situation
from niveau1_socle.marches.avis import demander_avis, enregistrer_decision
from niveau1_socle.marches.contrats import (
    ajouter_avenant,
    alertes_echeances,
    enregistrer_garantie,
    montant_courant,
)
from niveau1_socle.marches.decomptes import enregistrer_paiement, situation_contrat
from niveau1_socle.marches.plan import avancer_ligne
from niveau1_socle.tresorerie.services import enregistrer_solde_releve, etat_reconstitution
from tests.test_contrats_bd import _attribuer, _avis_avenant, _contrat
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_decomptes_bd import ENGAGEMENT, _certifier, _soumettre, marche  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_plan_passation_bd import _ligne, pas  # noqa: F401
from tests.test_tresorerie_bd import DEBUT, FIN, _scenario, banque  # noqa: F401

DOSSIER = Path(__file__).parent
CORRESPONDANCE = {
    "L9-T01 une méthode dont le seuil ne couvre pas le montant est refusée": [
        (
            "test_plan_passation_bd",
            "test_une_methode_dont_le_seuil_ne_couvre_pas_le_montant_est_refusee",
        ),
        ("test_plan_passation_bd", "test_le_seuil_maximal_est_exclu_et_le_minimal_inclus"),
    ],
    "L9-T01 l'avancement ne saute ni ne recule": [
        (
            "test_plan_passation_bd",
            "test_une_etape_ne_se_saute_pas_ni_ne_recule_dans_le_temps",
        ),
        ("test_plan_passation_bd", "test_la_base_refuse_un_retour_en_arriere_et_la_suppression"),
    ],
    "L9-T02 un marché soumis refuse l'engagement sans avis et l'accepte dès réception": [
        (
            "test_avis_non_objection_bd",
            "test_un_marche_soumis_a_avis_refuse_l_engagement_sans_avis_et_l_accepte_des_reception",
        ),
        (
            "test_avis_non_objection_bd",
            "test_la_base_refuse_l_engagement_sans_avis_meme_hors_du_service",
        ),
        ("test_avis_non_objection_bd", "test_un_refus_bloque_jusqu_a_une_nouvelle_demande_obtenue"),
    ],
    "L9-T03 avenants versionnés sans trou, alertes d'échéance": [
        (
            "test_contrats_bd",
            "test_les_avenants_portent_la_valeur_suivante_et_se_numerotent_sans_trou",
        ),
        (
            "test_contrats_bd",
            "test_la_base_tient_la_numerotation_et_l_ajout_seul_des_avenants",
        ),
        (
            "test_contrats_bd",
            "test_les_alertes_listent_garanties_et_contrats_du_plus_urgent_au_moins_urgent",
        ),
    ],
    "L9-T04 un engagement totalement apuré libère exactement le disponible, au centime": [
        (
            "test_decomptes_bd",
            "test_un_engagement_totalement_apure_libere_exactement_le_disponible_qu_il_reservait",
        ),
        (
            "test_decomptes_bd",
            "test_une_certification_refusee_n_apure_rien",
        ),
    ],
    "L9-T05 l'état de reconstitution se rapproche du relevé, tout écart est justifié": [
        (
            "test_tresorerie_bd",
            "test_l_etat_de_reconstitution_se_rapproche_du_releve_et_chaque_ecart_est_justifie",
        ),
        (
            "test_tresorerie_bd",
            "test_un_ecart_de_releve_reste_non_justifie_tant_que_les_justifications_ne_le_couvrent_pas_au_centime",
        ),
    ],
    "L9-T05 un mouvement ne s'apparie qu'à une demande ; numéros masqués": [
        ("test_tresorerie_bd", "test_un_mouvement_ne_s_apparie_qu_a_une_seule_demande"),
        ("test_tresorerie_bd", "test_l_etat_n_expose_jamais_le_numero_complet_du_compte"),
    ],
}


def test_chaque_controle_du_plan_renvoie_a_un_test_qui_existe():
    manquants = []
    for controle, tests in CORRESPONDANCE.items():
        for fichier, nom in tests:
            source = (DOSSIER / f"{fichier}.py").read_text(encoding="utf-8")
            if not re.search(rf"^def {re.escape(nom)}\(", source, flags=re.MULTILINE):
                manquants.append(f"{controle} -> {fichier}::{nom}")
    assert not manquants, manquants


# --- le scénario de bout en bout ---------------------------------------------------------------

J = datetime.date
D = Decimal


@pytest.mark.django_db(transaction=True)
def test_du_marche_soumis_a_la_tresorerie_un_engagement_bloque_puis_libere_au_centime(
    marche, banque
):
    organisation, projet, profils, contrat, engagement_aon = marche
    amina, bruno = profils["amina"], profils["bruno"]
    cadre_plan = (organisation, projet, profils, contrat.ligne.plan)

    # 1. Un marché soumis à non-objection (méthode AOI) : l'engagement est REFUSÉ sans avis.
    ligne = _ligne(cadre_plan, "M-900", "900000", "AOI")
    ligne = _attribuer(cadre_plan, ligne)
    with pytest.raises(BudgetInvalide):
        creer_engagement(
            utilisateur=amina, project_id=projet.id, reference="ENG-AOI", annee=2026,
            montant="5000", ligne_passation=ligne,
        )  # fmt: skip
    # ... et ACCEPTÉ dès la réception de l'avis.
    avis = demander_avis(
        utilisateur=amina, ligne=ligne, objet="dossier", date_demande=J(2026, 3, 1)
    )
    enregistrer_decision(
        utilisateur=amina,
        avis=avis,
        statut="obtenu",
        date_decision=J(2026, 3, 20),
        reference_bailleur="BM-117",
    )
    creer_engagement(
        utilisateur=amina, project_id=projet.id, reference="ENG-AOI", annee=2026,
        montant="5000", ligne_passation=ligne,
    )  # fmt: skip

    # 2. Le contrat de ce marché, puis un avenant qui s'appuie sur un avis « avenant » obtenu.
    contrat_aoi = _contrat(cadre_plan, ligne=ligne, reference="C-AOI", montant="900000")
    avis_avenant = _avis_avenant(cadre_plan, ligne)
    ajouter_avenant(
        utilisateur=amina, contrat=contrat_aoi, date_effet=J(2026, 8, 1), montant="950000",
        date_fin=J(2027, 1, 31), motif="Extension du périmètre", avis=avis_avenant,
    )  # fmt: skip
    assert montant_courant(contrat_aoi) == D("950000")

    # 3. Deux décomptes du marché ordinaire apurent EXACTEMENT son engagement : ce qu'il réservait
    #    est libéré au centime ; seul reste engagé celui du marché soumis.
    d1 = _certifier(marche, _soumettre(marche, "60000", "40"), apure="700000.11")
    d2 = _certifier(
        marche,
        _soumettre(marche, "58000.50", "100", jour=J(2026, 8, 1)),
        apure="534567.78",
        jour=J(2026, 8, 10),
    )
    engagement_aon.refresh_from_db()
    assert engagement_aon.status == "solde" and engagement_aon.apure == ENGAGEMENT
    [rangee] = situation(projet.id)
    assert rangee.engage == D("5000")
    assert comparer_soldes(projet.id) == []

    # 4. Paiements et soldes contractuels : le contrat est exécuté à 100 %.
    enregistrer_paiement(
        utilisateur=amina,
        decompte=d1,
        reference="P1",
        date_paiement=J(2026, 7, 15),
        montant="60000",
    )
    enregistrer_paiement(
        utilisateur=amina,
        decompte=d2,
        reference="P2",
        date_paiement=J(2026, 8, 15),
        montant="58000.50",
    )
    s = situation_contrat(utilisateur=amina, contrat=contrat)
    assert (s.solde_contractuel, s.taux_financier, s.taux_physique, s.reste_a_payer) == (
        0,
        D("100.00"),
        D("100.00"),
        0,
    )

    # 5. Une garantie à échéance proche déclenche une alerte.
    enregistrer_garantie(
        utilisateur=amina, contrat=contrat, type_garantie="bonne_execution", emetteur="Banque X",
        reference="GBE-1", montant="11800", date_emission=J(2026, 6, 1), date_echeance=J(2026, 9, 15),
    )  # fmt: skip
    alertes = alertes_echeances(
        utilisateur=amina, project_id=projet.id, jour=J(2026, 9, 1), horizon_jours=30
    )
    assert [(a.nature, a.reference, a.etat) for a in alertes][0] == ("garantie", "GBE-1", "proche")

    # 6. Trésorerie du compte désigné : l'état de reconstitution se rapproche du relevé, sans écart.
    _scenario(banque)
    designe = banque[3]
    enregistrer_solde_releve(utilisateur=amina, compte=designe, date_solde=FIN, solde="1200")
    etat = etat_reconstitution(utilisateur=amina, compte=designe, date_debut=DEBUT, date_fin=FIN)
    assert etat.justifie and etat.cloture_calculee == etat.cloture_releve == D("1200")
    assert "DJ21 0001" not in repr(etat)

    # 7. Le journal d'audit est intact de bout en bout.
    assert verifier_chaine(organisation.id) is None
    assert bruno.id and avancer_ligne
