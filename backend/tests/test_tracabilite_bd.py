"""Traçabilité descendante d'une cellule d'état vers ses écritures. Voir L0-T07."""

import datetime
import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from niveau4_reporting.mapping.models import RegleMapping, TableMapping
from niveau4_reporting.moteur.compilateur import compiler, generer
from niveau4_reporting.moteur.models import LigneEcriture
from niveau4_reporting.moteur.tracabilite import TracabiliteImpossible, tracer

pytestmark = pytest.mark.django_db(transaction=True)
PROJECT_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
DONOR_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _poser_org(org_id):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])


def _ligne(org_id, compte, annee, periode, *, debit="0", credit="0", accord="IDA-6789"):
    return LigneEcriture.objects.create(
        org_id=org_id,
        project_id=PROJECT_ID,
        fiscal_year=annee,
        period=periode,
        accounting_date=datetime.date(annee, periode, 15),
        compte=compte,
        debit=debit,
        credit=credit,
        dim1="COMP-A",
        accord=accord,
        categorie="CAT-1",
        site="SIEGE",
        devise="DJF",
        taux="1",
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
        priority=30,
        match={"accounts": [["7000", "7999"]]},
        target_code="PRODUITS",
    )
    _ligne(org_a, "6011", 2024, 12, debit="10")
    _ligne(org_a, "6011", 2026, 2, debit="100")
    _ligne(org_a, "6011", 2026, 4, debit="50.10")
    _ligne(org_a, "6011", 2026, 4, debit="40", accord="AUTRE")
    _ligne(org_a, "5211", 2026, 4, credit="30.05")
    _ligne(org_a, "7061", 2026, 3, credit="200.01")
    _ligne(org_a, "6011", 2026, 6, debit="999")
    modele = {
        "code": "TER",
        "columns": [
            {"code": "QTR", "period": "current_quarter"},
            {"code": "YTD", "period": "year_to_date"},
            {"code": "CUMUL", "period": "inception_to_date"},
            {"code": "MOIS", "period": "current_period"},
        ],
        "rows": [
            {"code": "T100", "type": "heading"},
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
            {
                "code": "R130",
                "type": "aggregate",
                "sign": "credit",
                "select": {"accounts": [["7000", "7999"]]},
            },
            {"code": "R190", "type": "computed", "formula": "R110 + R120"},
        ],
    }
    params = {
        "project_id": PROJECT_ID,
        "fiscal_year": 2026,
        "current_period": 4,
        "agreement": "IDA-6789",
    }
    regles = list(table.regles.all())
    return org_a, modele, {"WB-TER": regles}, params


def test_la_somme_des_lignes_tracees_egale_la_valeur_de_chaque_cellule(jeu):
    """Contrôle de L0-T07 : toutes les rubriques d'agrégat, toutes les colonnes, au centime."""
    _, modele, mappings, params = jeu
    produit = generer(modele, mappings, params)
    etat = compiler(modele, mappings, params)

    verifiees = 0
    for rubrique in etat.agregats:
        for colonne in etat.colonnes:
            trace = tracer(etat, rubrique, colonne)
            assert trace.total == produit.valeurs[rubrique][colonne], (rubrique, colonne)
            assert sum((ligne.montant for ligne in trace.lignes), Decimal(0)) == trace.total
            verifiees += 1
    assert verifiees == 12


def test_les_lignes_tracees_sont_exactement_celles_de_la_cellule(jeu):
    _, modele, mappings, params = jeu
    etat = compiler(modele, mappings, params)

    ytd = tracer(etat, "R110", "YTD")
    assert sorted(ligne.montant for ligne in ytd.lignes) == [Decimal("50.10"), Decimal("100")]
    assert {ligne.compte for ligne in ytd.lignes} == {"6011"}
    assert all(isinstance(ligne.id, uuid.UUID) for ligne in ytd.lignes)

    cumul = tracer(etat, "R110", "CUMUL")
    assert (
        len(cumul.lignes) == 3
    )  # l'exercice 2024, hors YTD, y figure ; l'accord AUTRE et juin non

    credit = tracer(etat, "R130", "YTD")
    assert [ligne.montant for ligne in credit.lignes] == [Decimal("200.01")]  # signe crédit


def test_la_tracabilite_est_une_seule_requete_et_ne_voit_pas_une_autre_organisation(jeu, org_b):
    org_a, modele, mappings, params = jeu
    _poser_org(org_b)
    _ligne(org_b, "6011", 2026, 2, debit="12345")
    _poser_org(org_a)
    etat = compiler(modele, mappings, params)

    with CaptureQueriesContext(connection) as requetes:
        trace = tracer(etat, "R110", "YTD")

    assert len(requetes) == 1
    assert Decimal("12345") not in [ligne.montant for ligne in trace.lignes]


def test_une_cellule_sans_ecriture_donne_une_trace_vide_a_zero(jeu):
    _, modele, mappings, params = jeu
    etat = compiler(modele, mappings, params)

    trace = tracer(etat, "R130", "MOIS")  # le produit est de mars, la période courante est avril
    assert trace.lignes == ()
    assert trace.total == Decimal(0)


@pytest.mark.parametrize(
    ("rubrique", "colonne"),
    [("R190", "YTD"), ("T100", "YTD"), ("R999", "YTD"), ("R110", "INCONNUE")],
)
def test_seule_une_cellule_dagregat_connue_est_tracable(jeu, rubrique, colonne):
    _, modele, mappings, params = jeu
    etat = compiler(modele, mappings, params)
    with pytest.raises(TracabiliteImpossible):
        tracer(etat, rubrique, colonne)
