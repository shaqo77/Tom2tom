"""Immuabilité des écritures comptabilisées et périodes closes. Voir L3-T03.

Deux garanties posées EN BASE, sans exception administrateur : une écriture comptabilisée ne
se modifie plus (on contre-passe), et on n'écrit rien dans une période qui n'est pas ouverte.
Les déclencheurs valent pour tout rôle, propriétaire du schéma compris.
"""

import datetime

import psycopg
import pytest
from django.db import IntegrityError, connection, transaction

from niveau1_socle.comptabilite.models import Ecriture, LigneEcriture
from niveau1_socle.exercices.models import Periode
from niveau1_socle.exercices.services import cloturer_periode, verrouiller_periode
from tests.outils import connexion_proprietaire, creer_piece, fermer_sans_controle

pytestmark = pytest.mark.django_db(transaction=True)
PAIRE = [{"compte": "6011", "debit": "10"}, {"compte": "5211", "credit": "10"}]


@pytest.fixture(autouse=True)
def _perimetre(org_a):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_a)])


def _posee(org_a, periode=1, statut="posted"):
    return creer_piece(org_a, 2026, periode, PAIRE, statut=statut)


def _periode(numero):
    return Periode.objects.get(exercice__annee=2026, numero=numero)


# --- immuabilité de l'écriture ------------------------------------------------------------


@pytest.mark.parametrize("statut", ["posted", "locked"])
def test_une_ecriture_comptabilisee_ne_se_modifie_ni_ne_se_supprime(org_a, statut):
    """Contrôle de L3-T03."""
    piece = _posee(org_a, statut=statut)

    with pytest.raises(IntegrityError, match="comptabilisée"), transaction.atomic():
        Ecriture.objects.filter(pk=piece.pk).update(label="Falsifiée")
    with pytest.raises(IntegrityError, match="comptabilisée"), transaction.atomic():
        Ecriture.objects.filter(pk=piece.pk).delete()
    assert Ecriture.objects.get(pk=piece.pk).label == "Pièce de test"


def test_aucune_exception_administrateur_le_proprietaire_est_refuse_lui_aussi(org_a):
    piece = _posee(org_a)
    with connexion_proprietaire() as admin:
        with pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="comptabilisée"):
            admin.execute(
                "UPDATE comptabilite_ecriture SET label = 'Falsifiée' WHERE id = %s", [piece.pk]
            )
        with pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="comptabilisée"):
            admin.execute("DELETE FROM comptabilite_ligneecriture WHERE entry_id = %s", [piece.pk])
        with pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="comptabilisée"):
            admin.execute("DELETE FROM comptabilite_ecriture WHERE id = %s", [piece.pk])


def test_un_brouillon_et_une_ecriture_validee_se_modifient_et_se_comptabilisent(org_a):
    brouillon = _posee(org_a, statut="draft")
    Ecriture.objects.filter(pk=brouillon.pk).update(label="Corrigée")
    Ecriture.objects.filter(pk=brouillon.pk).update(status="validated")
    assert Ecriture.objects.get(pk=brouillon.pk).label == "Corrigée"

    inutile = _posee(org_a, periode=2, statut="validated")
    with transaction.atomic():
        inutile.delete()
    assert not Ecriture.objects.filter(pk=inutile.pk).exists()


def test_le_verrouillage_est_un_changement_de_statut_pur_et_irreversible(org_a):
    piece = _posee(org_a)

    with pytest.raises(IntegrityError, match="comptabilisée"), transaction.atomic():
        Ecriture.objects.filter(pk=piece.pk).update(status="locked", label="Falsifiée")
    Ecriture.objects.filter(pk=piece.pk).update(status="locked")
    assert Ecriture.objects.get(pk=piece.pk).status == "locked"

    with pytest.raises(IntegrityError, match="comptabilisée"), transaction.atomic():
        Ecriture.objects.filter(pk=piece.pk).update(status="posted")


def test_les_lignes_dune_ecriture_comptabilisee_sont_immuables(org_a):
    piece = _posee(org_a)
    ligne = piece.lignes.get(line_no=1)

    with pytest.raises(IntegrityError, match="comptabilisée"), transaction.atomic():
        LigneEcriture.objects.filter(pk=ligne.pk).update(label="Falsifiée")
    with pytest.raises(IntegrityError, match="comptabilisée"), transaction.atomic():
        LigneEcriture.objects.filter(pk=ligne.pk).delete()
    with pytest.raises(IntegrityError, match="comptabilisée"), transaction.atomic():
        LigneEcriture.objects.create(
            org_id=org_a,
            project_id=piece.project_id,
            entry=piece,
            line_no=3,
            account=ligne.account,
            currency_id="DJF",
        )
    assert piece.lignes.count() == 2


def test_on_ne_supprime_pas_une_ecriture_comptabilisee_en_cascade(org_a):
    piece = _posee(org_a)
    with pytest.raises(IntegrityError, match="comptabilisée"), transaction.atomic():
        piece.delete()  # Django supprime les lignes d'abord, puis l'écriture
    assert Ecriture.objects.filter(pk=piece.pk).exists() and piece.lignes.count() == 2


def test_on_corrige_par_contre_passation_sans_toucher_a_loriginale(org_a):
    """Le cycle de correction : une nouvelle écriture inverse, l'originale reste intacte."""
    originale = _posee(org_a)
    inverse = creer_piece(
        org_a,
        2026,
        2,
        [{"compte": "6011", "credit": "10"}, {"compte": "5211", "debit": "10"}],
        reverses=originale,
    )

    assert inverse.reverses_id == originale.pk
    assert Ecriture.objects.count() == 2
    assert Ecriture.objects.get(pk=originale.pk).status == "posted"
    assert originale.lignes.count() == 2


# --- périodes closes ----------------------------------------------------------------------


def test_on_ne_cree_aucune_ecriture_dans_une_periode_close(org_a):
    """Contrôle de L3-T03."""
    _posee(org_a, periode=2)  # crée l'exercice
    cloturer_periode(_periode(1), utilisateur=None)

    with pytest.raises(IntegrityError, match="période"):
        creer_piece(org_a, 2026, 1, PAIRE, statut="draft")
    assert Ecriture.objects.count() == 1


def test_une_periode_verrouillee_refuse_aussi_les_ecritures(org_a):
    _posee(org_a, periode=2)
    cloturer_periode(_periode(1), utilisateur=None)
    verrouiller_periode(_periode(1), utilisateur=None)
    with pytest.raises(IntegrityError, match="période"):
        creer_piece(org_a, 2026, 1, PAIRE, statut="draft")


def test_un_brouillon_laisse_dans_une_periode_devenue_close_est_fige(org_a):
    brouillon = _posee(org_a, statut="draft")
    fermer_sans_controle(1)
    ligne = brouillon.lignes.get(line_no=1)

    for action in (
        lambda: Ecriture.objects.filter(pk=brouillon.pk).update(label="Retouche"),
        lambda: Ecriture.objects.filter(pk=brouillon.pk).update(
            status="posted",
            posted_at=datetime.datetime(2026, 1, 31, tzinfo=datetime.UTC),
            posted_by=org_a,
        ),
        lambda: Ecriture.objects.filter(pk=brouillon.pk).delete(),
        lambda: LigneEcriture.objects.filter(pk=ligne.pk).update(label="Retouche"),
        lambda: LigneEcriture.objects.create(
            org_id=org_a,
            project_id=brouillon.project_id,
            entry=brouillon,
            line_no=3,
            account=ligne.account,
            currency_id="DJF",
        ),
    ):
        with pytest.raises(IntegrityError, match="période"), transaction.atomic():
            action()
    assert Ecriture.objects.get(pk=brouillon.pk).status == "draft"


def test_on_ne_deplace_pas_une_ecriture_vers_une_periode_close(org_a):
    brouillon = _posee(org_a, periode=2, statut="draft")
    cloturer_periode(_periode(1), utilisateur=None)
    with pytest.raises(IntegrityError, match="période"), transaction.atomic():
        Ecriture.objects.filter(pk=brouillon.pk).update(
            periode=_periode(1), accounting_date=datetime.date(2026, 1, 15)
        )


def test_le_verrouillage_dune_ecriture_reste_possible_dans_une_periode_close(org_a):
    """Verrouiller ne modifie rien : le changement de statut pur n'est pas une écriture."""
    piece = _posee(org_a)
    cloturer_periode(_periode(1), utilisateur=None)
    Ecriture.objects.filter(pk=piece.pk).update(status="locked")
    assert Ecriture.objects.get(pk=piece.pk).status == "locked"


def test_une_periode_ouverte_continue_daccepter_des_ecritures(org_a):
    _posee(org_a, periode=1)
    cloturer_periode(_periode(1), utilisateur=None)
    assert _posee(org_a, periode=2).status == "posted"


def test_la_date_comptable_reste_dans_la_periode_et_lexercice_de_lecriture(org_a):
    brouillon = _posee(org_a, periode=1, statut="draft")
    with pytest.raises(IntegrityError, match="date comptable"), transaction.atomic():
        Ecriture.objects.filter(pk=brouillon.pk).update(accounting_date=datetime.date(2026, 3, 1))

    autre_exercice = creer_piece(org_a, 2027, 1, PAIRE, statut="draft").exercice
    with pytest.raises(IntegrityError, match="exercice"), transaction.atomic():
        Ecriture.objects.filter(pk=brouillon.pk).update(exercice=autre_exercice)
