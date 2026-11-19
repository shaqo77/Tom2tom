"""Exécution du compilateur sur PostgreSQL. Voir L0-T05."""

import datetime
import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from niveau4_reporting.mapping.models import RegleMapping, TableMapping
from niveau4_reporting.mapping.resolveur import MappingIncomplet
from niveau4_reporting.moteur.compilateur import generer
from tests.outils import creer_ligne, id_objet

pytestmark = pytest.mark.django_db(transaction=True)
PROJECT_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
DONOR_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _poser_org(org_id):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])


def _ligne(org_id, compte, annee, periode, *, debit="0", credit="0", accord="IDA-6789"):
    return creer_ligne(
        org_id,
        compte,
        annee,
        periode,
        debit=debit,
        credit=credit,
        accord=accord,
        categorie="CAT-1",
        site="SIEGE",
        dim1="COMP-A",
    )


@pytest.fixture
def jeu(org_a):
    _poser_org(org_a)
    table = TableMapping.objects.create(
        org_id=org_a,
        project_id=PROJECT_ID,
        donor_profile_id=DONOR_ID,
        code="WB-TER",
        version=1,
        valid_from=datetime.date(2024, 1, 1),
        status="active",
        validated_by=uuid.uuid4(),
        validated_at=timezone.now(),
    )
    RegleMapping.objects.create(
        org_id=org_a,
        table=table,
        priority=10,
        match={"accounts": [["6000", "6279"]]},
        target_code="CHARGES",
    )
    RegleMapping.objects.create(
        org_id=org_a,
        table=table,
        priority=20,
        match={"accounts": [["5200", "5299"]]},
        target_code="TRESORERIE",
    )
    RegleMapping.objects.create(
        org_id=org_a,
        table=table,
        priority=90,
        match={"accounts": [["8999", "8999"]]},  # contrepartie technique des pièces de test
        target_code="CONTREPARTIE",
    )
    _ligne(org_a, "6011", 2024, 12, debit="10")
    _ligne(org_a, "6011", 2026, 2, debit="100")
    _ligne(org_a, "6011", 2026, 4, debit="50")
    _ligne(org_a, "6011", 2026, 4, debit="40", accord="AUTRE")
    _ligne(org_a, "5211", 2026, 4, credit="30")
    _ligne(org_a, "6011", 2026, 6, debit="999")
    modele = {
        "code": "TER",
        "columns": [
            {"code": "QTR", "period": "current_quarter"},
            {"code": "YTD", "period": "year_to_date"},
            {"code": "CUMUL", "period": "inception_to_date"},
        ],
        "rows": [
            {
                "code": "R110",
                "type": "aggregate",
                "select": {
                    "mapping": "WB-TER",
                    "target": "CHARGES",
                    "filters": {"agreement": "$param.agreement"},
                },
            },
            {
                "code": "R120",
                "type": "aggregate",
                "select": {"mapping": "WB-TER", "target": "TRESORERIE"},
            },
            {"code": "R190", "type": "computed", "formula": "R110 + R120"},
            {"code": "R200", "type": "computed", "formula": "R190 * 2"},
        ],
    }
    params = {
        "project_id": PROJECT_ID,
        "fiscal_year": 2026,
        "current_period": 5,
        "agreement": str(id_objet("IDA-6789")),
    }
    return org_a, table, modele, params


def test_un_etat_est_produit_en_une_requete_avec_formules_en_decimal(jeu):
    _, table, modele, params = jeu
    regles = list(table.regles.all())

    with CaptureQueriesContext(connection) as requetes:
        produit = generer(modele, {"WB-TER": regles}, params)

    assert len(requetes) == 1
    assert produit.valeurs["R110"] == {
        "QTR": Decimal("50"),
        "YTD": Decimal("150"),
        "CUMUL": Decimal("160"),
    }
    assert produit.valeurs["R120"] == {
        "QTR": Decimal("-30"),
        "YTD": Decimal("-30"),
        "CUMUL": Decimal("-30"),
    }
    assert produit.valeurs["R190"]["CUMUL"] == Decimal("130")
    assert produit.valeurs["R200"] == {
        "QTR": Decimal("40"),
        "YTD": Decimal("240"),
        "CUMUL": Decimal("260"),
    }
    assert all(
        isinstance(valeur, Decimal)
        for ligne in produit.valeurs.values()
        for valeur in ligne.values()
    )


def test_un_compte_non_mappe_bloque_apres_la_meme_requete_unique(jeu):
    org_a, table, modele, params = jeu
    _ligne(org_a, "6281", 2026, 4, debit="7")
    regles = list(table.regles.all())

    with CaptureQueriesContext(connection) as requetes, pytest.raises(MappingIncomplet) as erreur:
        generer(modele, {"WB-TER": regles}, params)

    assert len(requetes) == 1
    assert "6281" in str(erreur.value)


def test_une_fourchette_directe_est_compilee_dans_la_requete_unique(jeu):
    _, _, _, params = jeu
    modele = {
        "code": "BALANCE",
        "columns": [{"code": "CUMUL", "period": "inception_to_date"}],
        "rows": [
            {
                "code": "R100",
                "type": "aggregate",
                "select": {"accounts": [["6011", "6011"]], "filters": {"dim1": ["COMP-A"]}},
            }
        ],
    }
    with CaptureQueriesContext(connection) as requetes:
        produit = generer(modele, {}, params)
    assert len(requetes) == 1
    assert produit.valeurs["R100"]["CUMUL"] == Decimal("200")


def test_la_generation_ne_voit_pas_les_comptes_dune_autre_organisation(jeu, org_b):
    org_a, table, modele, params = jeu
    _poser_org(org_b)
    _ligne(org_b, "9999", 2026, 4, debit="123456")
    _poser_org(org_a)
    regles = list(table.regles.all())

    produit = generer(modele, {"WB-TER": regles}, params)
    assert produit.valeurs["R110"]["YTD"] == Decimal("150")


def test_un_etat_sans_ligne_produit_des_zero_decimaux(jeu):
    _, table, modele, params = jeu
    params = {**params, "project_id": uuid.uuid4()}
    regles = list(table.regles.all())

    with CaptureQueriesContext(connection) as requetes:
        produit = generer(modele, {"WB-TER": regles}, params)

    assert len(requetes) == 1
    assert produit.valeurs["R200"] == {
        "QTR": Decimal(0),
        "YTD": Decimal(0),
        "CUMUL": Decimal(0),
    }


def test_le_signe_credit_inverse_la_selection(jeu):
    _, _, _, params = jeu
    modele = {
        "code": "TER",
        "columns": [{"code": "YTD", "period": "year_to_date"}],
        "rows": [
            {
                "code": "R120",
                "type": "aggregate",
                "sign": "credit",
                "select": {"accounts": [["5211", "5211"]]},
            }
        ],
    }
    produit = generer(modele, {}, params)
    assert produit.valeurs["R120"]["YTD"] == Decimal("30")


def test_deux_mappings_sont_agreges_et_controles_dans_une_seule_requete(jeu):
    org_a, table, modele, params = jeu
    autre = TableMapping.objects.create(
        org_id=org_a,
        project_id=PROJECT_ID,
        donor_profile_id=DONOR_ID,
        code="WB-IFR",
        version=1,
        valid_from=datetime.date(2024, 1, 1),
        status="active",
        validated_by=uuid.uuid4(),
        validated_at=timezone.now(),
    )
    RegleMapping.objects.create(
        org_id=org_a,
        table=autre,
        priority=10,
        match={"accounts": [["5000", "6999"]]},
        target_code="EMPLOIS",
    )
    RegleMapping.objects.create(
        org_id=org_a,
        table=autre,
        priority=90,
        match={"accounts": [["8999", "8999"]]},  # contrepartie technique des pièces de test
        target_code="CONTREPARTIE",
    )
    modele["rows"].insert(
        2,
        {
            "code": "R130",
            "type": "aggregate",
            "select": {"mapping": "WB-IFR", "target": "EMPLOIS"},
        },
    )
    mappings = {
        "WB-TER": list(table.regles.all()),
        "WB-IFR": list(autre.regles.all()),
    }

    with CaptureQueriesContext(connection) as requetes:
        produit = generer(modele, mappings, params)

    assert len(requetes) == 1
    assert produit.valeurs["R130"]["YTD"] == Decimal("160")
