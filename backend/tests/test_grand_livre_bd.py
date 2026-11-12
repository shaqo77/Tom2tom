"""Grand livre définitif : schéma, contraintes et vue du moteur. Voir L3-T01."""

import uuid
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction

from niveau1_socle.comptabilite.models import Ecriture, LigneEcriture
from tests.outils import creer_ligne, creer_piece, id_objet

pytestmark = pytest.mark.django_db(transaction=True)


def _poser(org_id):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])


def _vue(requete="SELECT count(*) FROM moteur_ligneecriture", params=None):
    with connection.cursor() as cur:
        cur.execute(requete, params or [])
        return cur.fetchall()


def test_la_vue_du_moteur_expose_les_noms_de_colonnes_du_prototype(org_a):
    _poser(org_a)
    creer_ligne(
        org_a,
        "6011",
        2026,
        4,
        debit="50.10",
        accord="IDA-6789",
        categorie="CAT-1",
        site="SIEGE",
        dim1="COMP-A",
        tiers="FRN-001",
    )

    (ligne,) = _vue(
        "SELECT compte, tiers, dim1, fiscal_year, period, debit, credit, accord, categorie, "
        "site, devise, taux FROM moteur_ligneecriture"
    )

    assert ligne[:7] == ("6011", "FRN-001", "COMP-A", 2026, 4, Decimal("50.10"), Decimal("0"))
    assert ligne[7] == str(id_objet("IDA-6789"))  # accord : texte d'UUID jusqu'à L4
    assert ligne[10:] == ("DJF", Decimal("1"))


@pytest.mark.parametrize(
    ("statut", "visible"),
    [("draft", 0), ("validated", 0), ("posted", 1), ("locked", 1)],
)
def test_seules_les_ecritures_comptabilisees_alimentent_les_etats(org_a, statut, visible):
    _poser(org_a)
    creer_ligne(org_a, "6011", 2026, 4, debit="10", statut=statut)
    assert _vue()[0][0] == visible


def test_la_vue_du_moteur_subit_lisolation_par_organisation(org_a, org_b):
    """security_invoker : sans cette option, une vue contourne la RLS de son propriétaire."""
    _poser(org_a)
    creer_ligne(org_a, "6011", 2026, 4, debit="10")
    creer_ligne(org_a, "6011", 2026, 5, debit="20")
    _poser(org_b)
    creer_ligne(org_b, "6011", 2026, 4, debit="999")

    _poser(org_a)
    assert _vue()[0][0] == 2, "FUITE DE DONNÉES ENTRE ORGANISATIONS PAR LA VUE"
    _poser(org_b)
    assert _vue("SELECT debit FROM moteur_ligneecriture") == [(Decimal("999"),)]
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")
    assert _vue()[0][0] == 0


def test_la_vue_du_moteur_est_security_invoker():
    """Le test précédent ne suffit pas : il passerait même sans cette option.

    Dans la base de test, le rôle applicatif POSSÈDE la vue et subit la RLS forcée des
    tables sous-jacentes ; en production, le propriétaire a BYPASSRLS et une vue qui
    s'exécute avec ses droits ouvrirait toutes les organisations. On vérifie donc l'option.
    """
    with connection.cursor() as cur:
        cur.execute(
            "SELECT reloptions FROM pg_class WHERE oid = to_regclass('moteur_ligneecriture')"
        )
        options = cur.fetchone()[0]
    assert "security_invoker=true" in (options or [])


def test_une_ecriture_comptabilisee_est_numerotee_horodatee_et_attribuee(org_a):
    _poser(org_a)
    ecriture = creer_piece(org_a, 2026, 4, [{"compte": "6011", "debit": "10"}], statut="draft")
    for champs in (
        {"status": "posted"},  # ni numéro, ni horodatage, ni auteur
        {"status": "posted", "number": "OD-2026-000001"},  # numérotée mais non horodatée
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            Ecriture.objects.filter(pk=ecriture.pk).update(**champs)


def test_le_numero_est_unique_par_journal_et_exercice_et_libre_ailleurs(org_a):
    _poser(org_a)
    p1 = creer_piece(org_a, 2026, 1, [{"compte": "6011", "debit": "1"}])
    assert p1.number == "OD-2026-000001"
    with pytest.raises(IntegrityError), transaction.atomic():
        Ecriture.objects.filter(pk=creer_piece(org_a, 2026, 2, [{"compte": "6011"}]).pk).update(
            number=p1.number
        )
    assert creer_piece(org_a, 2027, 1, [{"compte": "6011"}]).number == "OD-2027-000001"
    assert creer_piece(org_a, 2026, 1, [{"compte": "6011"}], journal="BQ").number == (
        "BQ-2026-000001"
    )


def test_une_cle_dindempotence_ne_sert_quune_fois_par_organisation(org_a, org_b):
    _poser(org_a)
    a = creer_piece(org_a, 2026, 1, [{"compte": "6011"}], statut="draft")
    b = creer_piece(org_a, 2026, 2, [{"compte": "6011"}], statut="draft")
    Ecriture.objects.filter(pk=a.pk).update(idempotency_key="capture-0001")
    with pytest.raises(IntegrityError), transaction.atomic():
        Ecriture.objects.filter(pk=b.pk).update(idempotency_key="capture-0001")
    _poser(org_b)
    c = creer_piece(org_b, 2026, 1, [{"compte": "6011"}], statut="draft")
    Ecriture.objects.filter(pk=c.pk).update(idempotency_key="capture-0001")  # autre organisation


@pytest.mark.parametrize(
    "champs",
    [
        {"status": "annulee"},
        {"origin": "magique"},
    ],
)
def test_statut_et_origine_dune_ecriture_sont_des_ensembles_fermes(org_a, champs):
    _poser(org_a)
    ecriture = creer_piece(org_a, 2026, 1, [{"compte": "6011"}], statut="draft")
    with pytest.raises(IntegrityError), transaction.atomic():
        Ecriture.objects.filter(pk=ecriture.pk).update(**champs)


def test_une_ecriture_ne_se_contrepasse_pas_elle_meme(org_a):
    _poser(org_a)
    ecriture = creer_piece(org_a, 2026, 1, [{"compte": "6011"}], statut="draft")
    with pytest.raises(IntegrityError), transaction.atomic():
        Ecriture.objects.filter(pk=ecriture.pk).update(reverses=ecriture)


@pytest.mark.parametrize(
    "champs",
    [
        {"debit": Decimal("5"), "credit": Decimal("5")},  # un seul sens
        {"debit": Decimal("-1")},
        {"credit": Decimal("-1")},
    ],
)
def test_une_ligne_a_un_seul_sens_et_des_montants_positifs(org_a, champs):
    _poser(org_a)
    ligne = creer_ligne(org_a, "6011", 2026, 1, debit="1", statut="draft")
    with pytest.raises(IntegrityError), transaction.atomic():
        LigneEcriture.objects.filter(pk=ligne.pk).update(**champs)


def test_deux_lignes_dune_meme_ecriture_ne_partagent_pas_leur_numero(org_a):
    _poser(org_a)
    ecriture = creer_piece(
        org_a, 2026, 1, [{"compte": "6011", "debit": "1"}, {"compte": "5211", "credit": "1"}]
    )
    assert list(ecriture.lignes.order_by("line_no").values_list("line_no", flat=True)) == [1, 2]
    ligne = ecriture.lignes.get(line_no=2)
    with pytest.raises(IntegrityError), transaction.atomic():
        LigneEcriture.objects.filter(pk=ligne.pk).update(line_no=1)


def test_les_ecritures_et_leurs_lignes_sont_isolees_par_organisation(org_a, org_b):
    _poser(org_a)
    creer_piece(org_a, 2026, 1, [{"compte": "6011", "debit": "1"}])
    _poser(org_b)
    assert Ecriture.objects.count() == 0
    assert LigneEcriture.objects.count() == 0
    with pytest.raises(IntegrityError, match="org_id|violates"), transaction.atomic():
        LigneEcriture.objects.create(
            org_id=org_b,
            project_id=uuid.uuid4(),
            entry_id=uuid.uuid4(),  # écriture inexistante : clé étrangère
            line_no=1,
            account_id=uuid.uuid4(),
            currency_id="DJF",
        )
