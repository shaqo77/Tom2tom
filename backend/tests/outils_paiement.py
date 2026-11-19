"""Aides de test pour les paiements de décomptes : comptes, journal, taux et écriture quelconque."""

import datetime

from niveau1_socle.comptabilite.models import Journal
from niveau1_socle.comptabilite.services import saisir_ecriture
from niveau1_socle.financements.models import CompteBancaire
from niveau1_socle.financements.services import creer_compte_bancaire
from niveau1_socle.marches.decomptes import enregistrer_paiement
from tests.outils import _compte

TAUX = "177.5"  # 1 USD = 177,5 DJF ; le contrat est en USD, le projet tient ses comptes en DJF


def contexte_paiement(marche):
    """Journal, comptes et taux d'un paiement du contrat de `marche` (créés au besoin)."""
    organisation, projet, profils, contrat, _ = marche
    Journal.objects.get_or_create(
        org_id=organisation.id, code="BQ", defaults={"label": {"fr": "Banque", "en": "Bank"}}
    )
    for code in ("401", "5211"):
        _compte(organisation.id, code)
    compte = CompteBancaire.objects.filter(code="CB-PAIE").first() or creer_compte_bancaire(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code="CB-PAIE",
        type="operationnel",
        devise=contrat.devise,
        banque="Banque",
        numero="PAIE-0001",
    )
    return {
        "compte_bancaire": compte,
        "compte_fournisseur": "401",
        "compte_banque": "5211",
        "journal": "BQ",
        "taux": TAUX if contrat.devise != projet.base_currency else None,
    }


def payer(marche, decompte, reference, date_paiement, montant, utilisateur=None, **champs):
    """Enregistre un paiement avec le contexte par défaut des tests, surchargeable par `champs`."""
    return enregistrer_paiement(
        utilisateur=utilisateur or marche[2]["amina"],
        decompte=decompte,
        reference=reference,
        date_paiement=date_paiement,
        montant=montant,
        **(contexte_paiement(marche) | champs),
    )


def ecriture_quelconque(marche, reference="QQ"):
    """Un brouillon équilibré sans rapport avec un paiement, pour les insertions directes."""
    organisation, projet, profils, _, _ = marche
    contexte_paiement(marche)
    return saisir_ecriture(
        utilisateur=profils["amina"],
        project_id=projet.id,
        journal="BQ",
        date_comptable=datetime.date(2026, 7, 20),
        libelle="Quelconque",
        lignes=[
            {"compte": "401", "debit": "1"},
            {"compte": "5211", "credit": "1"},
        ],
        reference_piece=reference,
    )
