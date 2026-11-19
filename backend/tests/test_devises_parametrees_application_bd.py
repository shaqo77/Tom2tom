# ruff: noqa: F811, E501
"""Les réglages de devises s'appliquent là où une devise entre dans le système, et plus aucun « DJF »
n'est écrit dans le code : sans devise demandée, on prend la monnaie de base DU PROJET, en base.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from core.erreurs import ErreurMetier
from niveau1_socle.comptabilite.models import Ecriture
from niveau1_socle.comptabilite.services import saisir_ecriture
from niveau1_socle.exercices.services import creer_exercice
from niveau1_socle.financements.models import Bailleur
from niveau1_socle.financements.services import (
    creer_accord,
    creer_bailleur,
    creer_compte_bancaire,
)
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau1_socle.referentiels.parametres_devises import (
    exiger_devise_autorisee,
    monnaie_de_base,
    parametrer_devises,
)
from niveau1_socle.reprise.services import ouvrir_reprise
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
J = datetime.date
DEBUT = J(2026, 1, 1)
LIGNES = [{"compte": "6011", "debit": "100"}, {"compte": "5211", "credit": "100"}]


def _poser(organisation):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


@pytest.fixture
def cadre(decor):
    """P1 (base DJF) et P2 (base USD, exercice 2026) ; dora paramètre et saisit sur les deux."""
    organisation, p1, profils = decor
    p2 = _creer_projet(organisation, "P2", base_currency="USD")
    _poser(organisation)
    creer_exercice(p2, 2026, utilisateur=None)
    dora = Utilisateur.objects.create_user("dora", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id,
        code="ADM",
        label={"fr": "adm"},
        operations=["consulter", "saisir", "parametrer"],
    )
    for projet in (p1, p2):
        Habilitation.objects.create(
            org_id=organisation.id, user_id=dora.id, project_id=projet.id, role=role
        )
    profils["dora"] = dora
    return organisation, p1, p2, profils


def _saisir(cadre, projet, **champs):
    _, _, _, profils = cadre
    return saisir_ecriture(
        utilisateur=profils["dora"],
        project_id=projet.id,
        journal="OD",
        date_comptable=J(2026, 3, 15),
        libelle="Écriture",
        lignes=LIGNES,
        **champs,
    )


def _accord(cadre, projet, devise, **champs):
    _, _, _, profils = cadre
    code = f"B-{devise}-{projet.code}"
    bailleur = Bailleur.objects.filter(code=code).first() or creer_bailleur(
        utilisateur=profils["dora"], code=code, nom="B"
    )
    return creer_accord(
        utilisateur=profils["dora"],
        project_id=projet.id,
        bailleur=bailleur,
        numero=f"A-{devise}-{projet.code}",
        nature="don",
        devise=devise,
        montant_initial="1000",
        **champs,
    )


def _reglage(cadre, projet=None, **champs):
    _, _, _, profils = cadre
    champs.setdefault("date_effet", DEBUT)
    return parametrer_devises(
        utilisateur=profils["dora"], project_id=projet.id if projet else None, **champs
    )


# --- plus de « DJF » écrit dans le code -------------------------------------------------------


def test_la_monnaie_de_base_d_un_projet_vient_de_la_base(cadre):
    _, p1, p2, _ = cadre
    assert (monnaie_de_base(p1.id), monnaie_de_base(p2.id)) == ("DJF", "USD")


def test_une_ecriture_sans_devise_demandee_prend_la_monnaie_de_base_du_projet(cadre):
    _, p1, p2, _ = cadre
    assert _saisir(cadre, p1).currency_id == "DJF"
    assert _saisir(cadre, p2).currency_id == "USD"  # avant : « DJF » en dur, faux pour ce projet
    assert Ecriture.objects.filter(project_id=p2.id, currency_id="DJF").count() == 0


def test_une_reprise_sans_devise_demandee_prend_la_monnaie_de_base_du_projet(cadre):
    _, p1, p2, profils = cadre
    r = ouvrir_reprise(
        utilisateur=profils["dora"], project_id=p2.id, nom="Reprise", date_bascule=J(2026, 1, 1)
    )
    assert r.devise == "USD"


# --- les devises autorisées sont appliquées ---------------------------------------------------


def test_sans_liste_paramétrée_rien_n_est_restreint(cadre):
    _, p1, _, _ = cadre
    assert _accord(cadre, p1, "EUR").devise_id == "EUR"
    exiger_devise_autorisee(p1.id, "GBP", J(2026, 3, 1))  # ne lève pas


def test_un_accord_dans_une_devise_non_autorisee_est_refuse_puis_accepte_une_fois_autorisee(cadre):
    _, p1, _, _ = cadre
    _reglage(cadre, p1, devises_autorisees=["DJF", "USD"])
    with pytest.raises(ErreurMetier, match="EUR.*pas autorisée"):
        _accord(cadre, p1, "EUR")
    assert _accord(cadre, p1, "USD").devise_id == "USD"
    _reglage(cadre, p1, devises_autorisees=["DJF", "USD", "EUR"], date_effet=J(2026, 2, 1))
    assert _accord(cadre, p1, "EUR", date_effet=J(2026, 3, 1)).devise_id == "EUR"


def test_la_date_compte_une_devise_autorisee_plus_tard_ne_l_est_pas_avant(cadre):
    _, p1, _, _ = cadre
    _reglage(cadre, p1, devises_autorisees=["DJF", "USD"])
    _reglage(cadre, p1, devises_autorisees=["DJF", "USD", "EUR"], date_effet=J(2026, 7, 1))
    with pytest.raises(ErreurMetier, match="EUR"):
        _accord(cadre, p1, "EUR", date_effet=J(2026, 6, 30))
    assert _accord(cadre, p1, "EUR", date_effet=J(2026, 7, 1)).devise_id == "EUR"


def test_un_compte_bancaire_dans_une_devise_non_autorisee_est_refuse(cadre):
    _, p1, _, profils = cadre
    _reglage(cadre, p1, devises_autorisees=["DJF", "USD"])
    champs = {
        "utilisateur": profils["dora"],
        "project_id": p1.id,
        "type": "operationnel",
        "banque": "B",
    }
    with pytest.raises(ErreurMetier, match="EUR"):
        creer_compte_bancaire(code="CB-EUR", devise="EUR", numero="FR-1", **champs)
    assert (
        creer_compte_bancaire(code="CB-USD", devise="USD", numero="US-1", **champs).devise_id
        == "USD"
    )


def test_une_ecriture_dans_une_devise_non_autorisee_est_refusee(cadre):
    _, p1, _, _ = cadre
    _reglage(cadre, p1, devises_autorisees=["DJF", "USD"])
    with pytest.raises(ErreurMetier, match="EUR"):
        _saisir(cadre, p1, devise="EUR", taux=200)
    assert _saisir(cadre, p1, devise="USD", taux=177).currency_id == "USD"


def test_une_reprise_dans_une_devise_non_autorisee_est_refusee(cadre):
    _, p1, _, profils = cadre
    _reglage(cadre, p1, devises_autorisees=["DJF", "USD"])
    with pytest.raises(ErreurMetier, match="EUR"):
        ouvrir_reprise(
            utilisateur=profils["dora"], project_id=p1.id, nom="R", date_bascule=DEBUT, devise="EUR"
        )


def test_le_reglage_d_un_projet_ne_restreint_pas_les_autres(cadre):
    _, p1, p2, _ = cadre
    _reglage(cadre, p1, devises_autorisees=["DJF"])
    with pytest.raises(ErreurMetier):
        _accord(cadre, p1, "EUR")
    assert _accord(cadre, p2, "EUR").devise_id == "EUR"  # P2 n'a aucune restriction
