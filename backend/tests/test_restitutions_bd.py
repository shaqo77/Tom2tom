"""Restitutions : balances, grand livre, journaux. Voir L3-T09.

Le contrôle de la tâche : balance générale = balance analytique = balance par accord, au centime,
sur le même périmètre. Trois chemins, un seul chiffre.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import PermissionDenied

from niveau4_reporting import restitutions
from niveau4_reporting.moteur.compilateur import generer
from niveau4_reporting.restitutions import (
    BalancesIncoherentes,
    RestitutionInvalide,
    balance,
    controler_balances,
    grand_livre,
    journal,
)
from tests.outils import _compte, creer_piece, id_objet
from tests.test_cycle_ecriture_bd import decor  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = Decimal


def _piece(org, projet, annee, periode, lignes, **champs):
    return creer_piece(org.id, annee, periode, lignes, project_id=projet.id, **champs)


@pytest.fixture
def jeu(decor):  # noqa: F811
    """Un exercice 2025 (ouverture) et 2026, avec tiers, axe et accord sur certaines lignes."""
    organisation, projet, profils = decor
    for code in ("4011", "7061", "101"):
        _compte(organisation.id, code)
    # 2025 : capital 10 000 en banque, une facture fournisseur sans tiers ni axe.
    _piece(
        organisation,
        projet,
        2025,
        12,
        [{"compte": "5211", "debit": "10000"}, {"compte": "101", "credit": "10000"}],
    )
    # 2026 P1 : achat 3 000 à crédit, avec tiers, axe et accord.
    _piece(
        organisation,
        projet,
        2026,
        1,
        [
            {"compte": "6011", "debit": "3000", "dim1": "COMP-A", "accord": "IDA-1"},
            {"compte": "4011", "credit": "3000", "tiers": "FRN-001", "accord": "IDA-1"},
        ],
    )
    # 2026 P2 : vente 5 000 sans aucune ventilation ; règlement partiel 1 000 du fournisseur.
    _piece(
        organisation,
        projet,
        2026,
        2,
        [{"compte": "5211", "debit": "5000"}, {"compte": "7061", "credit": "5000"}],
        journal="VT",
    )
    _piece(
        organisation,
        projet,
        2026,
        2,
        [
            {"compte": "4011", "debit": "1000", "tiers": "FRN-001", "accord": "IDA-1"},
            {"compte": "5211", "credit": "1000"},
        ],
    )
    # 2026 P3 : un brouillon, qui ne doit apparaître nulle part.
    _piece(
        organisation,
        projet,
        2026,
        3,
        [{"compte": "6011", "debit": "999"}, {"compte": "5211", "credit": "999"}],
        statut="draft",
    )
    return organisation, projet, profils


def _par_compte(b):
    return {ligne.compte: ligne for ligne in b.lignes if ligne.ventilation is None}


def test_la_balance_generale_donne_ouverture_mouvements_et_solde(jeu):
    _, projet, profils = jeu
    b = balance(profils["claire"], projet.id, 2026, 1, 2, nature="generale")
    lignes = {ligne.compte: ligne for ligne in b.lignes}
    banque = lignes["5211"]
    assert (banque.ouverture, banque.debit, banque.credit, banque.solde) == (
        D(10000),
        D(5000),
        D(1000),
        D(14000),
    )
    capital = lignes["101"]
    assert (capital.ouverture, capital.solde) == (D(-10000), D(-10000))
    fournisseur = lignes["4011"]
    assert (fournisseur.debit, fournisseur.credit, fournisseur.solde) == (
        D(1000),
        D(3000),
        D(-2000),
    )
    assert b.total_debit == b.total_credit and b.total_ouverture == 0 and b.total_solde == 0


def test_un_brouillon_n_apparait_pas_dans_les_restitutions(jeu):
    _, projet, profils = jeu
    b = balance(profils["claire"], projet.id, 2026, 1, 3, nature="generale")
    assert {ligne.compte: ligne.debit for ligne in b.lignes}["6011"] == D(3000)  # pas 3 999


def test_la_balance_auxiliaire_ventile_par_tiers_avec_une_ligne_non_ventile(jeu):
    _, projet, profils = jeu
    b = balance(profils["claire"], projet.id, 2026, 1, 3, nature="auxiliaire")
    fournisseur = {ligne.ventilation: ligne for ligne in b.lignes if ligne.compte == "4011"}
    assert set(fournisseur) == {"FRN-001"}
    assert fournisseur["FRN-001"].solde == D(-2000)
    assert {ligne.ventilation for ligne in b.lignes if ligne.compte == "5211"} == {None}


def test_la_balance_par_accord_et_l_analytique_ventilent_le_meme_ensemble(jeu):
    _, projet, profils = jeu
    accord = {
        (ligne.compte, ligne.ventilation): ligne.debit - ligne.credit
        for ligne in balance(profils["claire"], projet.id, 2026, 1, 3, nature="accord").lignes
    }
    assert accord[("6011", str(id_objet("IDA-1")))] == D(3000)
    assert accord[("4011", str(id_objet("IDA-1")))] == D(-2000)
    analytique = {
        (ligne.compte, ligne.ventilation): ligne.debit - ligne.credit
        for ligne in balance(profils["claire"], projet.id, 2026, 1, 3, nature="analytique_1").lignes
    }
    assert analytique[("6011", "COMP-A")] == D(3000)
    assert analytique[("5211", None)] == D(4000)  # le non ventilé existe


# --- le contrôle de la tâche --------------------------------------------------------------


def test_balance_generale_analytique_et_par_accord_donnent_le_meme_chiffre(jeu):
    """Contrôle de L3-T09 : trois chemins, un seul chiffre, au centime."""
    _, projet, profils = jeu
    for debut, fin in ((1, 1), (1, 3), (2, 2), (3, 3)):
        balances = controler_balances(profils["claire"], projet.id, 2026, debut, fin)
        generale = balances["generale"]
        for nature, b in balances.items():
            assert b.par_compte() == generale.par_compte(), nature
            assert (b.total_debit, b.total_credit) == (generale.total_debit, generale.total_credit)


def test_la_balance_s_accorde_avec_le_moteur_d_etats(jeu):
    """Les restitutions reposent sur le même socle que le moteur : mêmes chiffres, par rubrique."""
    _, projet, profils = jeu
    modele = {
        "code": "CTRL",
        "columns": [{"code": "cumul", "period": "inception_to_date"}],
        "rows": [
            {"code": comptes, "type": "aggregate", "select": {"accounts": [[comptes, comptes]]}}
            for comptes in ("5211", "4011", "6011")
        ],
    }
    etat = generer(modele, {}, {"project_id": projet.id, "fiscal_year": 2026, "current_period": 3})
    b = balance(profils["claire"], projet.id, 2026, 1, 3, nature="generale")
    for ligne in b.lignes:
        if ligne.compte in etat.valeurs:
            assert ligne.solde == etat[ligne.compte]["cumul"], ligne.compte


def test_des_balances_qui_divergent_sont_refusees_avec_tous_les_ecarts(jeu, monkeypatch):
    _, projet, profils = jeu
    vraie = restitutions.balance

    def truquee(utilisateur, project_id, annee, debut, fin, *, nature):
        b = vraie(utilisateur, project_id, annee, debut, fin, nature=nature)
        if nature == "accord":  # un centime perdu sur un compte
            premiere, *reste = b.lignes
            faux = restitutions.LigneBalance(
                premiere.compte,
                premiere.ventilation,
                premiere.ouverture,
                premiere.debit - D("0.01"),
                premiere.credit,
                premiere.solde - D("0.01"),
            )
            return restitutions.Balance(nature, (faux, *reste))
        return b

    monkeypatch.setattr(restitutions, "balance", truquee)
    with pytest.raises(BalancesIncoherentes, match="accord") as erreur:
        controler_balances(profils["claire"], projet.id, 2026, 1, 3)
    assert "déséquilibrée" in str(erreur.value) and "balance générale" in str(erreur.value)


# --- grand livre et journaux --------------------------------------------------------------


def test_le_grand_livre_donne_le_report_et_le_solde_cumule(jeu):
    _, projet, profils = jeu
    gl = grand_livre(profils["claire"], projet.id, "5211", 2026, 2, 3)
    assert gl.report == D(10000)
    # Même date : le journal, puis le numéro, ordonnent (OD avant VT).
    assert [(ligne.debit, ligne.credit, ligne.solde_cumule) for ligne in gl.lignes] == [
        (D(0), D(1000), D(9000)),
        (D(5000), D(0), D(14000)),
    ]
    assert gl.solde == D(14000) == gl.report + gl.total_debit - gl.total_credit
    assert all(ligne.numero for ligne in gl.lignes)


def test_le_grand_livre_se_restreint_a_un_tiers(jeu):
    _, projet, profils = jeu
    gl = grand_livre(profils["claire"], projet.id, "4011", 2026, 1, 3, tiers="FRN-001")
    assert [ligne.solde_cumule for ligne in gl.lignes] == [D(-3000), D(-2000)]
    assert grand_livre(profils["claire"], projet.id, "4011", 2026, 1, 3, tiers="AUCUN").lignes == ()


def test_un_journal_liste_ses_pieces_et_s_equilibre(jeu):
    _, projet, profils = jeu
    od = journal(profils["claire"], projet.id, "OD", 2026, 1, 3)
    assert od.total_debit == od.total_credit == D(4000)
    vt = journal(profils["claire"], projet.id, "VT", 2026, 1, 3)
    assert {ligne.compte for ligne in vt.lignes} >= {"5211", "7061"}
    assert [ligne.numero for ligne in vt.lignes] == sorted(ligne.numero for ligne in vt.lignes)


# --- droits et paramètres ------------------------------------------------------------------


def test_une_restitution_exige_l_habilitation_consulter(jeu):
    organisation, projet, _ = jeu
    inconnu = Utilisateur.objects.create_user("eve", password="x", org_id=organisation.id)
    with pytest.raises(PermissionDenied):
        balance(inconnu, projet.id, 2026, 1, 3, nature="generale")
    with pytest.raises(PermissionDenied):
        grand_livre(inconnu, projet.id, "5211", 2026, 1, 3)
    with pytest.raises(PermissionDenied):
        journal(inconnu, projet.id, "OD", 2026, 1, 3)


@pytest.mark.parametrize(
    "annee, debut, fin",
    [(2026, 0, 3), (2026, 4, 3), (2026, 1, 13), ("2026", 1, 3), (2026, 1, None)],
)
def test_des_bornes_invalides_sont_refusees(jeu, annee, debut, fin):
    _, projet, profils = jeu
    with pytest.raises(RestitutionInvalide):
        balance(profils["claire"], projet.id, annee, debut, fin, nature="generale")


def test_une_nature_inconnue_n_est_jamais_interpolee_dans_le_sql(jeu):
    _, projet, profils = jeu
    with pytest.raises(RestitutionInvalide, match="nature"):
        balance(profils["claire"], projet.id, 2026, 1, 3, nature="compte; DROP TABLE x")
