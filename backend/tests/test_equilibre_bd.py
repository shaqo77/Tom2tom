"""Équilibre des écritures, en contrainte différée. Voir L3-T02.

Pendant qu'on insère la première ligne, l'écriture est forcément déséquilibrée : la
contrainte est donc DIFFÉRÉE et ne se vérifie qu'au COMMIT, quand toutes les lignes sont là.
Elle vaut pour tous les statuts, brouillons compris.
"""

from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction

from niveau1_socle.comptabilite.models import Ecriture, LigneEcriture
from tests.outils import creer_piece

pytestmark = pytest.mark.django_db(transaction=True)


def _poser(org_id):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])


@pytest.fixture(autouse=True)
def _perimetre(org_a):
    _poser(org_a)


def _ecriture_vide(org_id, *, statut="draft", periode=1):
    """Une écriture sans ligne : rien à équilibrer, la contrainte ne se déclenche pas."""
    _poser(org_id)
    return creer_piece(org_id, 2026, periode, [], statut=statut)


def _ligne(ecriture, numero, compte, *, debit="0", credit="0"):
    from tests.outils import _compte

    return LigneEcriture.objects.create(
        org_id=ecriture.org_id,
        project_id=ecriture.project_id,
        entry=ecriture,
        line_no=numero,
        account=_compte(ecriture.org_id, compte),
        debit=Decimal(debit),
        credit=Decimal(credit),
        currency_id="DJF",
    )


def _nombre(modele):
    return modele.objects.count()


def test_une_ecriture_desequilibree_leve_lexception_au_commit_et_rien_nest_ecrit(org_a):
    """Contrôle de L3-T02."""
    ecriture = _ecriture_vide(org_a)

    with pytest.raises(IntegrityError, match="déséquilibrée"):
        with transaction.atomic():
            _ligne(ecriture, 1, "6011", debit="100")
            _ligne(ecriture, 2, "5211", credit="99.99")
            # Rien n'est refusé ici : la vérification attend la fin de la transaction.

    assert _nombre(LigneEcriture) == 0
    assert _nombre(Ecriture) == 1  # l'écriture vide, créée avant, est intacte


def test_une_ecriture_equilibree_est_acceptee_ligne_par_ligne_dans_une_transaction(org_a):
    ecriture = _ecriture_vide(org_a)
    with transaction.atomic():
        _ligne(ecriture, 1, "6011", debit="100.50")  # déséquilibre transitoire
        _ligne(ecriture, 2, "5211", credit="100.50")
    assert _nombre(LigneEcriture) == 2


def test_un_ecart_dun_dix_millieme_est_detecte(org_a):
    ecriture = _ecriture_vide(org_a)
    with pytest.raises(IntegrityError, match="0.0001"):
        with transaction.atomic():
            _ligne(ecriture, 1, "6011", debit="10.0001")
            _ligne(ecriture, 2, "5211", credit="10.0000")


def test_un_brouillon_doit_lui_aussi_etre_equilibre(org_a):
    ecriture = _ecriture_vide(org_a, statut="draft")
    with pytest.raises(IntegrityError, match="déséquilibrée"):
        with transaction.atomic():
            _ligne(ecriture, 1, "6011", debit="1")


def test_modifier_un_montant_qui_desequilibre_est_refuse_au_commit(org_a):
    piece = creer_piece(
        org_a,
        2026,
        1,
        [{"compte": "6011", "debit": "10"}, {"compte": "5211", "credit": "10"}],
        statut="draft",
    )
    with pytest.raises(IntegrityError, match="déséquilibrée"):
        with transaction.atomic():
            LigneEcriture.objects.filter(entry=piece, line_no=1).update(debit=Decimal("11"))
    assert LigneEcriture.objects.get(entry=piece, line_no=1).debit == Decimal("10")


def test_supprimer_une_ligne_qui_desequilibre_est_refuse_au_commit(org_a):
    piece = creer_piece(
        org_a,
        2026,
        1,
        [{"compte": "6011", "debit": "10"}, {"compte": "5211", "credit": "10"}],
        statut="draft",
    )
    with pytest.raises(IntegrityError, match="déséquilibrée"):
        with transaction.atomic():
            LigneEcriture.objects.filter(entry=piece, line_no=2).delete()
    assert _nombre(LigneEcriture) == 2


def test_supprimer_toute_lecriture_et_ses_lignes_reste_possible(org_a):
    """Zéro ligne : rien à équilibrer. (L3-T03 interdira de supprimer une écriture posée.)"""
    piece = creer_piece(
        org_a,
        2026,
        1,
        [{"compte": "6011", "debit": "10"}, {"compte": "5211", "credit": "10"}],
        statut="draft",
    )
    with transaction.atomic():
        piece.delete()
    assert _nombre(Ecriture) == 0 and _nombre(LigneEcriture) == 0


def test_deplacer_une_ligne_vers_une_autre_ecriture_desequilibre_les_deux(org_a):
    a = creer_piece(
        org_a,
        2026,
        1,
        [{"compte": "6011", "debit": "10"}, {"compte": "5211", "credit": "10"}],
        statut="draft",
    )
    b = creer_piece(
        org_a,
        2026,
        2,
        [{"compte": "6011", "debit": "5"}, {"compte": "5211", "credit": "5"}],
        statut="draft",
    )
    with pytest.raises(IntegrityError, match="déséquilibrée"):
        with transaction.atomic():
            LigneEcriture.objects.filter(entry=a, line_no=1).update(entry=b, line_no=3)
    assert LigneEcriture.objects.filter(entry=a).count() == 2


def test_une_ligne_deplacee_vers_une_ecriture_supprimee_ne_passe_pas_inapercue(org_a):
    """Le seul cas où le contrôle de l'ANCIENNE écriture est indispensable.

    On déplace une ligne vers une écriture temporaire, puis on supprime celle-ci avec ses
    lignes. Aucun événement ne cite plus l'écriture d'origine : sans contrôle de l'ancienne
    écriture à l'UPDATE, elle perdrait une ligne sans que rien ne se déclenche.
    """
    origine = creer_piece(
        org_a,
        2026,
        1,
        [{"compte": "6011", "debit": "10"}, {"compte": "5211", "credit": "10"}],
        statut="draft",
    )
    temporaire = creer_piece(org_a, 2026, 2, [], statut="draft")
    with pytest.raises(IntegrityError, match="déséquilibrée"):
        with transaction.atomic():
            LigneEcriture.objects.filter(entry=origine, line_no=1).update(entry=temporaire)
            temporaire.delete()  # emporte la ligne déplacée
    assert LigneEcriture.objects.filter(entry=origine).count() == 2


def test_deplacer_une_paire_complete_vers_une_autre_ecriture_est_equilibre(org_a):
    a = creer_piece(
        org_a,
        2026,
        1,
        [{"compte": "6011", "debit": "10"}, {"compte": "5211", "credit": "10"}],
        statut="draft",
    )
    b = creer_piece(org_a, 2026, 2, [], statut="draft")
    with transaction.atomic():
        LigneEcriture.objects.filter(entry=a, line_no=1).update(entry=b, line_no=1)
        LigneEcriture.objects.filter(entry=a, line_no=2).update(entry=b, line_no=2)
    assert LigneEcriture.objects.filter(entry=b).count() == 2


def test_plusieurs_ecritures_dans_une_meme_transaction_sont_chacune_controlees(org_a):
    bonne = _ecriture_vide(org_a, periode=1)
    mauvaise = _ecriture_vide(org_a, periode=2)
    with pytest.raises(IntegrityError, match="déséquilibrée"):
        with transaction.atomic():
            _ligne(bonne, 1, "6011", debit="10")
            _ligne(bonne, 2, "5211", credit="10")
            _ligne(mauvaise, 1, "6011", debit="10")
            _ligne(mauvaise, 2, "5211", credit="9")
    assert _nombre(LigneEcriture) == 0, "l'écriture équilibrée n'est pas écrite seule"
