# ruff: noqa: F811, E501
"""Le paiement d'un décompte écrit au grand livre. Voir L9-T04 (corrigé après la revue de L9).

Le paiement crée un BROUILLON équilibré (fournisseur au débit, banque au crédit) lié au paiement ;
il suit ensuite le cycle ordinaire : validé par une autre personne, puis comptabilisé. Aucun compte
ni taux n'est supposé : l'appelant les donne.
"""

import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from core.erreurs import ErreurMetier
from niveau1_socle.comptabilite.models import LigneEcriture
from niveau1_socle.comptabilite.services import (
    JournalIntrouvable,
    comptabiliser_ecriture,
    valider_ecriture,
)
from niveau1_socle.financements.services import creer_compte_bancaire
from niveau1_socle.marches.models import Paiement
from niveau1_socle.tresorerie.services import solde_comptable_a
from tests.outils_paiement import TAUX, contexte_paiement, payer
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_decomptes_bd import _certifier, _soumettre, marche  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_plan_passation_bd import pas  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
J = datetime.date
D = Decimal


def _decompte_certifie(marche, brut="60000"):
    return _certifier(marche, _soumettre(marche, brut, "40"), apure="700000.11")


def test_un_paiement_ecrit_un_brouillon_equilibre_lie_au_paiement(marche):
    decompte = _decompte_certifie(marche)
    paiement = payer(marche, decompte, "P1", J(2026, 7, 15), "60000")
    ecriture = paiement.ecriture
    assert ecriture is not None and ecriture.status == "draft" and ecriture.document_ref == "P1"
    assert ecriture.currency_id == "USD" and ecriture.fx_rate == D(TAUX)
    fournisseur, banque = ecriture.lignes.order_by("line_no")
    assert (fournisseur.account.code, fournisseur.debit, fournisseur.debit_cur) == (
        "401",
        D("10650000"),
        D("60000"),
    )
    assert fournisseur.partner.code == "F1" and fournisseur.contract_id == marche[3].id
    assert (banque.account.code, banque.credit, banque.credit_cur) == (
        "5211",
        D("10650000"),
        D("60000"),
    )
    assert banque.bank_account_id == contexte_paiement(marche)["compte_bancaire"].id
    assert ecriture.accounting_date == J(2026, 7, 15)


def test_une_fois_validee_puis_comptabilisee_l_ecriture_porte_le_solde_du_compte(marche):
    profils = marche[2]
    compte = contexte_paiement(marche)["compte_bancaire"]
    paiement = payer(marche, _decompte_certifie(marche), "P1", J(2026, 7, 15), "60000")
    assert solde_comptable_a(compte, J(2026, 7, 31)) == 0  # un brouillon ne compte pas
    valider_ecriture(paiement.ecriture, utilisateur=profils["bruno"])
    comptabiliser_ecriture(paiement.ecriture, utilisateur=profils["claire"])
    assert solde_comptable_a(compte, J(2026, 7, 31)) == D("-60000")  # devise du compte (USD)
    assert LigneEcriture.objects.filter(entry=paiement.ecriture).count() == 2


def test_le_montant_en_monnaie_de_tenue_est_arrondi_a_la_devise(marche):
    paiement = payer(
        marche, _decompte_certifie(marche, "58000.50"), "P2", J(2026, 7, 15), "58000.50"
    )
    debit = paiement.ecriture.lignes.get(line_no=1).debit
    assert debit == D(
        "10295089"
    )  # 58 000,50 × 177,5 = 10 295 088,75 → DJF sans décimale, arrondi supérieur


def test_la_devise_du_compte_bancaire_doit_etre_celle_du_contrat(marche):
    organisation, projet, profils, _, _ = marche
    djf = creer_compte_bancaire(
        utilisateur=profils["dora"], project_id=projet.id, code="CB-DJF", type="operationnel",
        devise="DJF", banque="B", numero="DJF-1",
    )  # fmt: skip
    with pytest.raises(ErreurMetier) as e:
        payer(marche, _decompte_certifie(marche), "P1", J(2026, 7, 15), "100", compte_bancaire=djf)
    assert "DJF" in str(e.value) and "USD" in str(e.value)
    assert not Paiement.objects.exists()


def test_sans_taux_hors_devise_de_tenue_le_message_dit_que_le_taux_est_obligatoire(marche):
    with pytest.raises(ErreurMetier) as e:
        payer(marche, _decompte_certifie(marche), "P1", J(2026, 7, 15), "100", taux=None)
    assert "obligatoire" in str(e.value) and "USD" in str(e.value)


@pytest.mark.parametrize("taux", ["0", "-1", "abc", 177.5])
def test_hors_devise_de_tenue_le_taux_est_decimal_et_positif(marche, taux):
    with pytest.raises(ErreurMetier):
        payer(marche, _decompte_certifie(marche), "P1", J(2026, 7, 15), "100", taux=taux)
    assert not Paiement.objects.exists()


def test_un_refus_de_l_ecriture_annule_aussi_le_paiement(marche):
    decompte = _decompte_certifie(marche)
    with pytest.raises(JournalIntrouvable):
        payer(marche, decompte, "P1", J(2026, 7, 15), "100", journal="INCONNU")
    assert not Paiement.objects.exists()
    from niveau1_socle.comptabilite.models import Ecriture

    assert not Ecriture.objects.filter(document_ref="P1").exists()
    assert payer(
        marche, decompte, "P1", J(2026, 7, 15), "100"
    ).id  # la même référence repart propre


def test_la_base_refuse_un_paiement_sans_ecriture(marche):
    decompte = _decompte_certifie(marche)
    contrat = marche[3]
    with pytest.raises(IntegrityError), transaction.atomic():
        Paiement.objects.create(
            org_id=contrat.org_id, decompte=decompte, project_id=contrat.project_id, reference="X",
            date_paiement=J(2026, 8, 1), montant=1, enregistre_par=contrat.id,
        )  # fmt: skip


def test_l_ecriture_du_paiement_porte_une_cle_d_idempotence_stable(marche):
    decompte = _decompte_certifie(marche)
    paiement = payer(marche, decompte, "P1", J(2026, 7, 15), "100")
    assert paiement.ecriture.idempotency_key == f"paiement-decompte:{decompte.id}:P1"


def test_la_base_refuse_une_ecriture_d_un_autre_projet(marche):
    from niveau1_socle.comptabilite.models import Ecriture, Journal
    from niveau1_socle.exercices.services import creer_exercice
    from tests.test_organisations_bd import _creer_projet

    organisation, projet, _, contrat, _ = marche
    decompte = _decompte_certifie(marche)
    contexte_paiement(marche)
    autre = _creer_projet(organisation, "P2")
    exercice = creer_exercice(autre, 2026, utilisateur=None)
    etrangere = Ecriture.objects.create(
        org_id=organisation.id, project_id=autre.id, exercice=exercice,
        periode=exercice.periodes.get(numero=7), journal=Journal.objects.get(code="BQ"),
        accounting_date=J(2026, 7, 20), label="Autre projet", status="draft", currency_id="DJF",
        fx_rate=D(1), origin="saisie",
    )  # fmt: skip
    with pytest.raises(IntegrityError), transaction.atomic():
        Paiement.objects.create(
            org_id=contrat.org_id, decompte=decompte, project_id=projet.id, reference="Z",
            date_paiement=J(2026, 8, 1), montant=1, enregistre_par=contrat.id, ecriture=etrangere,
        )  # fmt: skip
