"""Numérotation sans trou, attribuée par la base à la comptabilisation. Voir L3-T04.

Une séquence PostgreSQL n'est pas annulée par un ROLLBACK : elle produit des trous. Un
auditeur qui voit passer de la pièce 412 à la 414 présume une suppression. On utilise donc un
compteur par journal et par exercice, incrémenté dans la transaction de la comptabilisation :
annuler la transaction annule le numéro.

C'est la BASE qui attribue le numéro (déclencheur) : ni l'application ni un administrateur ne
le choisissent.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, connections, transaction
from django.utils import timezone

from niveau1_socle.comptabilite.models import Compteur, Ecriture, Journal, LigneEcriture
from niveau1_socle.comptabilite.numerotation import trous_de_numerotation
from niveau1_socle.exercices.models import Exercice
from tests.outils import _compte, connexion_proprietaire, creer_piece

pytestmark = pytest.mark.django_db(transaction=True)
PAIRE = [{"compte": "6011", "debit": "10"}, {"compte": "5211", "credit": "10"}]


@pytest.fixture(autouse=True)
def _perimetre(org_a):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_a)])


def _comptabiliser(ecriture_id):
    """Comptabilise un brouillon : un simple changement de statut. Le numéro vient de la base."""
    Ecriture.objects.filter(pk=ecriture_id).update(
        status="posted", posted_at=timezone.now(), posted_by=uuid.uuid4()
    )


def _brouillons_en_masse(org_a, nombre):
    """`nombre` brouillons équilibrés, créés d'un coup (la comptabilisation est testée à part)."""
    amorce = creer_piece(org_a, 2026, 1, PAIRE, statut="draft")  # exercice, journal, comptes
    compte_debit, compte_credit = _compte(org_a, "6011"), _compte(org_a, "5211")
    ecritures, lignes = [], []
    for _ in range(nombre - 1):
        ecriture = Ecriture(
            id=uuid.uuid4(),
            org_id=org_a,
            project_id=amorce.project_id,
            exercice=amorce.exercice,
            periode=amorce.periode,
            journal=amorce.journal,
            accounting_date=amorce.accounting_date,
            label="Brouillon de masse",
            status="draft",
            currency_id="DJF",
            origin="saisie",
        )
        ecritures.append(ecriture)
        for rang, (compte, debit, credit) in enumerate(
            [(compte_debit, "10", "0"), (compte_credit, "0", "10")], start=1
        ):
            lignes.append(
                LigneEcriture(
                    org_id=org_a,
                    project_id=amorce.project_id,
                    entry=ecriture,
                    line_no=rang,
                    account=compte,
                    debit=Decimal(debit),
                    credit=Decimal(credit),
                    currency_id="DJF",
                )
            )
    with transaction.atomic():
        Ecriture.objects.bulk_create(ecritures)
        LigneEcriture.objects.bulk_create(lignes)
    return [amorce.pk] + [e.pk for e in ecritures]


class _Annulation(Exception):
    """Fait échouer volontairement une transaction de comptabilisation."""


def _travailleur(org_a, ids, annuler):
    """Une session de base de données indépendante : comptabilise `ids` un par un."""
    try:
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [str(org_a)])
        for identifiant in ids:
            try:
                with transaction.atomic():
                    _comptabiliser(identifiant)
                    if identifiant in annuler:
                        raise _Annulation
            except _Annulation:
                pass
    finally:
        connections.close_all()  # ferme la connexion de CE fil, sinon la base de test reste occupée


# --- le contrôle de la tâche --------------------------------------------------------------


def test_mille_comptabilisations_depuis_dix_sessions_dont_cent_annulees_sans_trou_ni_doublon(
    org_a,
):
    """Contrôle de L3-T04 : la suite est 000001 à 000900."""
    ids = _brouillons_en_masse(org_a, 1000)
    annuler = set(ids[9::10])  # une sur dix : 100 transactions annulées
    assert len(annuler) == 100
    paquets = [ids[i::10] for i in range(10)]

    barriere = threading.Barrier(10)

    def lancer(paquet):
        barriere.wait()  # les dix sessions démarrent ensemble
        _travailleur(org_a, paquet, annuler)

    with ThreadPoolExecutor(max_workers=10) as pool:
        for resultat in [pool.submit(lancer, p) for p in paquets]:
            resultat.result()

    numeros = sorted(Ecriture.objects.filter(status="posted").values_list("number", flat=True))
    assert numeros == [f"OD-2026-{n:06d}" for n in range(1, 901)]
    assert Ecriture.objects.filter(status="draft", number__isnull=True).count() == 100
    assert Compteur.objects.get().dernier == 900
    journal, exercice = Journal.objects.get(), Exercice.objects.get()
    assert trous_de_numerotation(journal, exercice) == []


# --- le numéro est attribué à la comptabilisation, par la base ----------------------------


def test_un_brouillon_na_pas_de_numero_et_ne_consomme_aucun_compteur(org_a):
    piece = creer_piece(org_a, 2026, 1, PAIRE, statut="draft")
    assert piece.number is None
    assert Compteur.objects.count() == 0

    Ecriture.objects.filter(pk=piece.pk).update(status="validated")
    assert Ecriture.objects.get(pk=piece.pk).number is None
    assert Compteur.objects.count() == 0

    _comptabiliser(piece.pk)
    assert Ecriture.objects.get(pk=piece.pk).number == "OD-2026-000001"
    assert Compteur.objects.get().dernier == 1


def test_une_transaction_annulee_rend_son_numero(org_a):
    premiere = creer_piece(org_a, 2026, 1, PAIRE, statut="draft")
    seconde = creer_piece(org_a, 2026, 2, PAIRE, statut="draft")

    with pytest.raises(_Annulation), transaction.atomic():
        _comptabiliser(premiere.pk)
        raise _Annulation
    _comptabiliser(seconde.pk)

    assert Ecriture.objects.get(pk=seconde.pk).number == "OD-2026-000001"
    assert Ecriture.objects.get(pk=premiere.pk).number is None


def test_chaque_journal_et_chaque_exercice_ont_leur_propre_suite(org_a):
    assert creer_piece(org_a, 2026, 1, PAIRE).number == "OD-2026-000001"
    assert creer_piece(org_a, 2026, 2, PAIRE).number == "OD-2026-000002"
    assert creer_piece(org_a, 2026, 1, PAIRE, journal="BQ").number == "BQ-2026-000001"
    assert creer_piece(org_a, 2027, 1, PAIRE).number == "OD-2027-000001"
    assert creer_piece(org_a, 2026, 3, PAIRE).number == "OD-2026-000003"


def test_les_compteurs_sont_isoles_par_organisation(org_a, org_b):
    creer_piece(org_a, 2026, 1, PAIRE)
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_b)])
    assert Compteur.objects.count() == 0
    assert creer_piece(org_b, 2026, 1, PAIRE).number == "OD-2026-000001"


# --- on ne choisit pas son numéro ---------------------------------------------------------


@pytest.mark.parametrize(
    "creation",
    [
        {"number": "OD-2026-000042"},  # un brouillon n'a pas de numéro
        {"status": "posted", "posted_at": timezone.now(), "posted_by": uuid.uuid4()},
    ],
    ids=["brouillon_numerote", "naissance_comptabilisee"],
)
def test_une_ecriture_naît_en_brouillon_sans_numero(org_a, creation):
    modele = creer_piece(org_a, 2026, 1, PAIRE, statut="draft")
    champs = {
        "org_id": org_a,
        "project_id": modele.project_id,
        "exercice": modele.exercice,
        "periode": modele.periode,
        "journal": modele.journal,
        "accounting_date": modele.accounting_date,
        "label": "Tentative",
        "currency_id": "DJF",
        "origin": "saisie",
        "status": "draft",
    } | creation
    with pytest.raises(IntegrityError), transaction.atomic():
        Ecriture.objects.create(**champs)


def test_on_ne_choisit_pas_le_numero_en_comptabilisant(org_a):
    piece = creer_piece(org_a, 2026, 1, PAIRE, statut="draft")
    with pytest.raises(IntegrityError, match="attribué par la base"), transaction.atomic():
        Ecriture.objects.filter(pk=piece.pk).update(
            status="posted",
            number="OD-2026-000099",
            posted_at=timezone.now(),
            posted_by=uuid.uuid4(),
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        Ecriture.objects.filter(pk=piece.pk).update(number="OD-2026-000099")
    assert Ecriture.objects.get(pk=piece.pk).number is None


def test_le_compteur_ne_se_decremente_ni_ne_saute_ni_ne_se_supprime(org_a):
    creer_piece(org_a, 2026, 1, PAIRE)
    creer_piece(org_a, 2026, 2, PAIRE)
    compteur = Compteur.objects.get()
    assert compteur.dernier == 2

    for nouvelle_valeur in (1, 0, 4):  # reculer, remettre à zéro, sauter un numéro
        with pytest.raises(IntegrityError, match="compteur"), transaction.atomic():
            Compteur.objects.filter(pk=compteur.pk).update(dernier=nouvelle_valeur)
    with pytest.raises(IntegrityError, match="compteur"), transaction.atomic():
        Compteur.objects.filter(pk=compteur.pk).delete()
    assert Compteur.objects.get().dernier == 2


# --- le détecteur de trous ----------------------------------------------------------------


def test_le_detecteur_nomme_les_numeros_manquants(org_a):
    """Vérifie le vérificateur : un trou fabriqué hors des déclencheurs doit être vu."""
    for periode in (1, 2, 3):
        creer_piece(org_a, 2026, periode, PAIRE)
    journal, exercice = Journal.objects.get(), Exercice.objects.get()
    assert trous_de_numerotation(journal, exercice) == []

    # Un administrateur contourne les déclencheurs et efface le numéro 2.
    with connexion_proprietaire() as admin:
        admin.execute("SET session_replication_role = replica")
        admin.execute(
            "UPDATE comptabilite_ecriture SET number = 'OD-2026-000009' WHERE number = %s",
            ["OD-2026-000002"],
        )
    assert trous_de_numerotation(journal, exercice) == [2, 4, 5, 6, 7, 8]
