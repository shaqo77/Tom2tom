# ruff: noqa: E501  (tables de cas : un contrôle par ligne)
"""La bibliothèque de contrôles livrée. Voir L6-T01c (logique pure, sans base).

Contrôle du plan : chaque contrôle livré a un test qui le déclenche ET un test qui prouve qu'il ne
se déclenche pas à tort. Un test de couverture refuse un contrôle livré sans ses deux cas.
"""

import datetime
from decimal import Decimal

import pytest

from niveau4_reporting.controles import bibliotheque as lib
from niveau4_reporting.controles import conditions
from niveau4_reporting.controles.contextes import contexte, reste_apres
from niveau4_reporting.controles.decision import (
    ParametresInvalides,
    decider,
    pieces_retenues,
    valider_parametres,
)

D = Decimal
J = datetime.date


def decision(definition, ctx):
    return decider(
        libelle=definition.label["fr"],
        mode="automatique",
        severity=definition.severity,
        type_regle=definition.type_regle,
        expression=definition.expression,
        applicable_si=definition.applicable_si,
        parametres=definition.parametres,
        contexte=ctx,
    )


# (contexte qui déclenche, contexte qui ne déclenche pas, contexte non applicable ou None)
CAS = {
    "COD-CATEGORIE": ({}, {"categorie": "BIENS"}, None),
    "COD-SOURCE": ({"source": ""}, {"source": "IDA"}, None),
    "COD-AXE-1": ({"axe_1": None}, {"axe_1": "COMP-A"}, None),
    "BUD-LIGNE": ({"disponible_ligne": D("-0.01")}, {"disponible_ligne": D("0")}, {}),
    "BUD-CATEGORIE": ({"disponible_categorie": D("-1")}, {"disponible_categorie": D("0.00")}, {}),
    "BUD-ALLOCATION": ({"disponible_allocation": D("-1")}, {"disponible_allocation": D("12")}, {}),
    "BUD-ACCORD": ({"disponible_accord": D("-100")}, {"disponible_accord": D("0")}, {}),
    "PIE-DOUBLON": ({"facture_en_double": True}, {"facture_en_double": False}, None),
    "PIE-ETAT-CERTIFIE": (
        {"destinee_etat_certifie": True, "pieces": []},
        {"destinee_etat_certifie": True, "pieces": [{"type": "facture"}]},
        {"destinee_etat_certifie": False, "pieces": []},
    ),
    "TRE-ECART": (
        {"ecart_justifie": False, "ecart_rapprochement": D("12.50")},
        {"ecart_justifie": False, "ecart_rapprochement": D("0")},
        {"ecart_justifie": True, "ecart_rapprochement": D("12.50")},
    ),
    "TRE-SOLDE-DESIGNE": ({"ecart_solde": D("5")}, {"ecart_solde": D("0.00")}, None),
    "AVA-NON-JUSTIFIEE": ({"justifiee": False}, {"justifiee": True}, None),
    "AVA-DELAI": ({"jours_de_retard": 1}, {"jours_de_retard": 0}, None),
    "RAP-RUBRIQUE-VIDE": (
        {"rubrique_obligatoire": True, "rubrique_vide": True},
        {"rubrique_obligatoire": True, "rubrique_vide": False},
        {"rubrique_obligatoire": False, "rubrique_vide": True},
    ),
    "RAP-COMPTE-NON-MAPPE": (
        {"comptes_non_mappes": [{"code": "6011"}]},
        {"comptes_non_mappes": []},
        None,
    ),
    "RAP-ASSERTION": ({"assertions_non_verifiees": [{"code": "A1"}]}, {}, None),
    "COH-ETATS": ({"ecart_entre_etats": D("0.01")}, {"ecart_entre_etats": D("0")}, None),
    "COH-PERIODES": ({"ecart_entre_periodes": D("-0.01")}, {"ecart_entre_periodes": D("0")}, None),
    "COH-CUMUL": ({"rupture_de_cumul": D("100")}, {"rupture_de_cumul": D("0")}, None),
    "RIS-CATEGORIE-SEUIL": (
        {"taux_consommation_categorie": D("80.01")},
        {"taux_consommation_categorie": D("80")},
        {},
    ),
    "RIS-AVANCE-NON-APUREE": ({"jours_avance_non_apuree": 91}, {"jours_avance_non_apuree": 90}, {}),
    "RIS-REJETS-REPETES": ({"rejets_categorie": 4}, {"rejets_categorie": 3}, {}),
}
LIVRES = {d.code: d for d in lib.livres_avec_risque()}


def test_chaque_controle_livre_a_ses_cas_et_chaque_cas_un_controle_livre():
    assert set(CAS) == set(LIVRES)  # ni contrôle sans test, ni test sans contrôle


@pytest.mark.parametrize("code", sorted(CAS))
def test_chaque_controle_livre_se_declenche_quand_il_le_doit(code):
    ko, _, _ = CAS[code]
    definition = LIVRES[code]
    resultat = decision(definition, ko)
    assert resultat.resultat == definition.severity, resultat.message
    assert resultat.premier_echec is not None and definition.label["fr"] in str(resultat.message)


@pytest.mark.parametrize("code", sorted(CAS))
def test_chaque_controle_livre_ne_se_declenche_pas_a_tort(code):
    _, ok, _ = CAS[code]
    assert decision(LIVRES[code], ok).resultat == "reussi"


@pytest.mark.parametrize("code", [c for c, cas in sorted(CAS.items()) if cas[2] is not None])
def test_un_controle_conditionnel_non_applicable_n_est_ni_reussi_ni_en_echec(code):
    _, _, hors_champ = CAS[code]
    assert decision(LIVRES[code], hors_champ).resultat == "non_applicable"


def test_les_huit_familles_du_plan_et_le_risque_sont_representes():
    """L'éligibilité n'a aucune valeur livrée en dur : ce sont des règles configurées par le projet,
    donc ses quatre fabriques."""
    par_fabrique = {
        lib.eligibilite_nature("N", ["x"]).famille,
        lib.eligibilite_zone("Z", ["x"]).famille,
        lib.eligibilite_periode("P", J(2026, 1, 1), J(2026, 2, 1)).famille,
        lib.eligibilite_beneficiaires_exclus("B", ["x"]).famille,
    }
    assert par_fabrique == {"eligibilite"}
    assert {d.famille for d in lib.livres_avec_risque()} | par_fabrique == set(lib.FAMILLES)
    assert set(lib.FAMILLES) >= {
        "codification", "budget", "pieces", "tresorerie", "avances", "rapport", "coherence", "eligibilite",
    }  # fmt: skip


def test_les_trois_controles_de_risque_sont_des_avertissements_ou_des_informations():
    risques = [d for d in lib.livres_avec_risque() if d.famille == "risque"]
    assert len(risques) == 3
    assert {d.severity for d in risques} <= {"avertissement", "information"}


def test_chaque_definition_livree_est_valide_pour_le_langage_ferme():
    for d in lib.livres_avec_risque():
        conditions.preparer_expression(d.expression, d.type_regle)
        if d.applicable_si is not None:
            conditions.preparer_expression(d.applicable_si, d.type_regle)
        assert d.severity in ("bloquant", "avertissement", "information")
        assert d.label["fr"] and d.label["en"]
        assert d.action_corrective["fr"] and d.action_corrective["en"]


def test_les_seuils_de_risque_sont_parametres():
    strict = lib.risque_categorie_consommee("50")
    assert decision(strict, {"taux_consommation_categorie": D("60")}).resultat == "avertissement"
    souple = lib.risque_categorie_consommee("95")
    assert decision(souple, {"taux_consommation_categorie": D("60")}).resultat == "reussi"
    court = lib.risque_avance_non_apuree(30)
    assert decision(court, {"jours_avance_non_apuree": 31}).resultat == "information"
    assert (
        decision(lib.risque_avance_non_apuree(30), {"jours_avance_non_apuree": 30}).resultat
        == "reussi"
    )
    assert decision(lib.risque_rejets_repetes(1), {"rejets_categorie": 2}).resultat == "information"
    assert "50 %" in strict.label["fr"] and "30 jours" in court.label["fr"]


# --- les règles de pièces : pas de liste universelle ---------------------------------------

FACTURE_VALIDEE = {"type": "facture", "rattachee": True, "valide": True}


def test_une_piece_du_mauvais_type_ou_non_rattachee_est_refusee_comme_absente():
    regle = lib.regle_de_piece("PIE-FACTURE", "facture")
    for pieces in (
        [],
        [{"type": "bon_de_commande", "rattachee": True, "valide": True}],  # mauvais type
        [{"type": "facture", "rattachee": False, "valide": True}],  # non rattachée
        [{"type": "facture", "valide": True}],  # rattachement inconnu : refusée aussi
    ):
        assert decision(regle, {"pieces": pieces}).resultat == "bloquant", pieces
    assert decision(regle, {"pieces": [FACTURE_VALIDEE]}).resultat == "reussi"
    mixte = [{"type": "bon_de_commande", "rattachee": True}, {"type": "facture", "rattachee": True}]
    assert decision(regle, {"pieces": mixte}).resultat == "reussi"


def test_une_piece_non_validee_est_refusee_quand_la_regle_exige_la_validation():
    exigeante = lib.regle_de_piece("PIE-FACTURE-V", "facture", validee=True)
    non_validee = {"type": "facture", "rattachee": True, "valide": False}
    assert decision(exigeante, {"pieces": [non_validee]}).resultat == "bloquant"
    assert (
        decision(exigeante, {"pieces": [{"type": "facture", "rattachee": True}]}).resultat
        == "bloquant"
    )
    assert decision(exigeante, {"pieces": [FACTURE_VALIDEE]}).resultat == "reussi"
    souple = lib.regle_de_piece("PIE-FACTURE", "facture")
    assert decision(souple, {"pieces": [non_validee]}).resultat == "reussi"  # non exigée


def test_la_portee_d_une_regle_de_piece_se_cumule_et_hors_portee_elle_est_non_applicable():
    regle = lib.regle_de_piece(
        "PIE-TRAVAUX", "pv_reception", categories=["TRAVAUX"], methodes=["reimbursement"],
        seuil_montant="1000", natures=["travaux"],
    )  # fmt: skip
    dans_la_portee = {
        "categorie": "TRAVAUX",
        "methode": "reimbursement",
        "montant": D("1000"),
        "nature": "travaux",
    }
    assert decision(regle, {**dans_la_portee, "pieces": []}).resultat == "bloquant"
    for ecart in (
        {"categorie": "BIENS"},
        {"methode": "advance"},
        {"montant": D("999.99")},
        {"nature": "fournitures"},
    ):
        assert (
            decision(regle, {**dans_la_portee, **ecart, "pieces": []}).resultat == "non_applicable"
        ), ecart
    sans_portee = lib.regle_de_piece("PIE-TOUT", "facture")
    assert sans_portee.applicable_si is None


def test_un_contrat_de_pieces_filtre_par_les_parametres_seulement():
    parametres = {"type_piece": "facture", "validee": True}
    pieces = [
        {"type": "facture", "rattachee": True, "valide": True},
        {"type": "facture", "rattachee": False, "valide": True},
        {"type": "facture", "rattachee": True, "valide": False},
        {"type": "devis", "rattachee": True, "valide": True},
    ]
    assert pieces_retenues(pieces, parametres) == [pieces[0]]
    assert pieces_retenues(None, parametres) == []
    assert pieces_retenues(pieces, {"type_piece": "facture"}) == [pieces[0], pieces[2]]


@pytest.mark.parametrize(
    "type_regle, parametres, message",
    [
        ("budget", {"type_piece": "x"}, "seule une règle de pièces"),
        ("pieces", {"type_piece": " "}, "type_piece"),
        ("pieces", {"validee": True}, "type_piece"),
        ("pieces", {"type_piece": 3}, "type_piece"),
        ("pieces", {"type_piece": "x", "validee": "oui"}, "booléen"),
        ("pieces", {"type_piece": "x", "couleur": "rouge"}, "inconnus"),
        ("pieces", ["x"], "objet"),
    ],
)
def test_des_parametres_hors_de_ce_que_le_type_de_regle_accepte_sont_refuses(
    type_regle, parametres, message
):
    with pytest.raises(ParametresInvalides, match=message):
        valider_parametres(type_regle, parametres)
    assert valider_parametres("pieces", None) == {} and valider_parametres("budget", {}) == {}
    assert valider_parametres("pieces", {"type_piece": " facture "}) == {
        "type_piece": "facture", "validee": False,
    }  # fmt: skip


# --- éligibilité : ce que le projet a configuré --------------------------------------------


def test_l_eligibilite_par_nature_et_par_zone():
    nature = lib.eligibilite_nature("ELI-NATURE", ["travaux", "biens"])
    assert decision(nature, {"nature": "voyages"}).resultat == "bloquant"
    assert decision(nature, {"nature": "travaux"}).resultat == "reussi"
    assert decision(nature, {}).resultat == "bloquant"  # nature absente : non éligible
    zone = lib.eligibilite_zone("ELI-ZONE", ["DJ-TADJOURA"])
    assert decision(zone, {"zone": "ER-ASSAB"}).resultat == "bloquant"
    assert decision(zone, {"zone": "DJ-TADJOURA"}).resultat == "reussi"


def test_la_periode_d_eligibilite_est_semi_ouverte():
    periode = lib.eligibilite_periode("ELI-DATE", J(2026, 1, 1), J(2026, 7, 1))
    assert decision(periode, {"date": J(2025, 12, 31)}).resultat == "bloquant"
    assert decision(periode, {"date": J(2026, 1, 1)}).resultat == "reussi"
    assert decision(periode, {"date": J(2026, 6, 30)}).resultat == "reussi"
    assert decision(periode, {"date": J(2026, 7, 1)}).resultat == "bloquant"  # fin exclue


def test_un_beneficiaire_exclu_est_bloque_et_sans_beneficiaire_c_est_non_applicable():
    exclus = lib.eligibilite_beneficiaires_exclus("ELI-BENEF", ["SOC-X", "SOC-Y"])
    assert decision(exclus, {"beneficiaire": "SOC-X"}).resultat == "bloquant"
    assert decision(exclus, {"beneficiaire": "SOC-Z"}).resultat == "reussi"
    assert decision(exclus, {}).resultat == "non_applicable"


# --- les contextes -------------------------------------------------------------------------


def test_un_contexte_refuse_un_champ_inconnu_ou_d_un_mauvais_type():
    assert contexte("budget", disponible_ligne=D("12")) == {"disponible_ligne": D("12")}
    with pytest.raises(KeyError, match="hors du schéma"):
        contexte("budget", disponible_lgne=D("12"))  # faute de frappe : refusée, pas ignorée
    with pytest.raises(TypeError):
        contexte("budget", disponible_ligne=12.5)
    with pytest.raises(KeyError, match="inconnu"):
        contexte("magie")


def test_le_reste_apres_une_depense_est_negatif_en_cas_de_depassement():
    assert reste_apres(D("1000"), D("900"), D("100")) == D("0")
    assert reste_apres(D("1000"), D("900"), D("100.01")) == D("-0.01")
    assert reste_apres(None, D("900"), D("100")) is None  # pas de plafond : rien à dépasser


# --- ce que la table de cas ne dit pas : sévérités, signes, mode manuel --------------------

# La sévérité attendue de chaque contrôle livré, écrite À PART de sa définition : sinon le test
# comparerait la définition à elle-même et ne verrait jamais une sévérité modifiée.
SEVERITES = {
    "COD-CATEGORIE": "bloquant", "COD-SOURCE": "bloquant", "COD-AXE-1": "bloquant",
    "BUD-LIGNE": "bloquant", "BUD-CATEGORIE": "bloquant", "BUD-ALLOCATION": "bloquant",
    "BUD-ACCORD": "bloquant", "PIE-DOUBLON": "bloquant", "PIE-ETAT-CERTIFIE": "bloquant",
    "TRE-ECART": "bloquant", "TRE-SOLDE-DESIGNE": "bloquant",
    "AVA-NON-JUSTIFIEE": "avertissement", "AVA-DELAI": "bloquant",
    "RAP-RUBRIQUE-VIDE": "bloquant", "RAP-COMPTE-NON-MAPPE": "bloquant", "RAP-ASSERTION": "bloquant",
    "COH-ETATS": "bloquant", "COH-PERIODES": "bloquant", "COH-CUMUL": "bloquant",
    "RIS-CATEGORIE-SEUIL": "avertissement", "RIS-AVANCE-NON-APUREE": "information",
    "RIS-REJETS-REPETES": "information",
}  # fmt: skip


def test_la_severite_de_chaque_controle_livre_est_celle_du_plan():
    assert {c: d.severity for c, d in LIVRES.items()} == SEVERITES
    for code, ko in ((c, CAS[c][0]) for c in CAS):
        assert decision(LIVRES[code], ko).resultat == SEVERITES[code], code


@pytest.mark.parametrize(
    "code, champ, valeur",
    [
        ("TRE-ECART", "ecart_rapprochement", D("-5")),
        ("TRE-SOLDE-DESIGNE", "ecart_solde", D("-5")),
        ("COH-ETATS", "ecart_entre_etats", D("-0.01")),
        ("COH-CUMUL", "rupture_de_cumul", D("-100")),
        ("COH-PERIODES", "ecart_entre_periodes", D("0.01")),
    ],
)
def test_un_ecart_est_une_anomalie_dans_les_deux_sens(code, champ, valeur):
    contexte_ko = {**CAS[code][0], champ: valeur}
    assert decision(LIVRES[code], contexte_ko).resultat == "bloquant"


def test_un_controle_manuel_est_a_verifier_sans_rien_evaluer():
    resultat = decider(
        libelle="Revue des pièces", mode="manuel", severity="bloquant", type_regle="pieces",
        expression=None, applicable_si=None, parametres={}, contexte={},
    )  # fmt: skip
    assert resultat.resultat == "a_verifier" and "vérification humaine" in str(resultat.message)
    assert resultat.constats == [] and resultat.premier_echec is None
