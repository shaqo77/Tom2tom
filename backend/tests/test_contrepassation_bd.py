"""Contre-passation d'une écriture comptabilisée. Voir L3-T05 (partie b).

On ne corrige jamais une écriture comptabilisée : on en crée une inverse, liée à l'originale par
`reverses`. L'originale n'est jamais touchée. La contre-passation naît en brouillon et suit le
même circuit (validation, comptabilisation) que toute écriture.
"""

import datetime
import uuid
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from niveau1_socle.comptabilite.models import Ecriture, LigneEcriture
from niveau1_socle.comptabilite.services import (
    ContrepassationImpossible,
    DejaContrepassee,
    EcritureInvalide,
    PeriodeNonOuverte,
    TransitionInterdite,
    comptabiliser_ecriture,
    contre_passer,
    valider_ecriture,
)
from niveau1_socle.exercices.models import Periode
from niveau1_socle.exercices.services import cloturer_periode
from tests.outils import creer_piece
from tests.test_cycle_ecriture_bd import LIGNES, _journal, _poser, _saisir, decor  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def _comptabilisee(projet, profils, **champs):
    ecriture = _saisir(projet, profils["amina"], **champs)
    valider_ecriture(ecriture, utilisateur=profils["bruno"])
    return comptabiliser_ecriture(ecriture, utilisateur=profils["claire"])


def _instantane(ecriture):
    """Tout ce qui définit une écriture et ses lignes, pour prouver qu'on n'y a pas touché."""
    champs = Ecriture.objects.filter(pk=ecriture.pk).values().get()
    lignes = list(LigneEcriture.objects.filter(entry=ecriture).order_by("line_no").values())
    return champs, lignes


# --- le contrôle de la tâche --------------------------------------------------------------


def test_le_cycle_complet_laisse_deux_ecritures_toutes_deux_intactes(decor):  # noqa: F811
    """Contrôle de L3-T05 : brouillon, validée, comptabilisée, contre-passée."""
    organisation, projet, profils = decor
    originale = _comptabilisee(projet, profils)
    avant = _instantane(originale)

    inverse = contre_passer(originale, utilisateur=profils["amina"])
    assert (inverse.status, inverse.origin, inverse.reverses_id) == (
        "draft",
        "reversal",
        originale.pk,
    )
    valider_ecriture(inverse, utilisateur=profils["bruno"])
    comptabiliser_ecriture(inverse, utilisateur=profils["claire"])

    assert Ecriture.objects.count() == 2
    assert _instantane(originale) == avant, "L'ORIGINALE A ÉTÉ TOUCHÉE"
    inverse.refresh_from_db()
    assert inverse.number == "OD-2026-000002"
    assert originale.pk != inverse.pk and inverse.reverses_id == originale.pk

    # Les lignes se répondent en sens inverse, compte par compte.
    d = {x.account.code: (x.debit, x.credit) for x in originale.lignes.select_related("account")}
    i = {x.account.code: (x.debit, x.credit) for x in inverse.lignes.select_related("account")}
    assert d == {"6011": (Decimal("100"), 0), "5211": (0, Decimal("100"))}
    assert i == {"6011": (0, Decimal("100")), "5211": (Decimal("100"), 0)}

    # Effet net sur chaque compte : nul.
    with connection.cursor() as cur:
        cur.execute(
            "SELECT compte, SUM(debit) - SUM(credit) FROM moteur_ligneecriture GROUP BY compte"
        )
        assert {c: s for c, s in cur.fetchall()} == {"6011": 0, "5211": 0}
    assert verifier_chaine(organisation.id) is None


def test_la_contrepassation_est_journalisee_avec_loriginale(decor):  # noqa: F811
    organisation, projet, profils = decor
    originale = _comptabilisee(projet, profils)
    inverse = contre_passer(originale, utilisateur=profils["amina"])

    action, acteur, _, apres = [j for j in _journal(organisation) if j[0] == "entry_reversed"][0]
    assert acteur == profils["amina"].id
    assert str(originale.pk) in apres and "OD-2026-000001" in apres
    assert inverse.label.startswith("Contre-passation de OD-2026-000001")


def test_la_contrepassation_reprend_les_axes_et_inverse_les_devises(decor):  # noqa: F811
    _, projet, profils = decor
    originale = _comptabilisee(
        projet,
        profils,
        lignes=[
            {"compte": "6011", "debit": "100", "debit_cur": "100", "dim1": "COMP-A"},
            {"compte": "5211", "credit": "100", "credit_cur": "100"},
        ],
    )
    inverse = contre_passer(originale, utilisateur=profils["amina"])
    ligne = inverse.lignes.select_related("dim1").get(account__code="6011")
    assert ligne.dim1.code == "COMP-A"
    assert (ligne.credit, ligne.credit_cur, ligne.debit_cur) == (Decimal("100"), Decimal("100"), 0)


# --- ce qu'on ne contre-passe pas ---------------------------------------------------------


def test_on_ne_contrepasse_que_ce_qui_est_comptabilise(decor):  # noqa: F811
    _, projet, profils = decor
    brouillon = _saisir(projet, profils["amina"])
    with pytest.raises(TransitionInterdite):
        contre_passer(brouillon, utilisateur=profils["amina"])
    valider_ecriture(brouillon, utilisateur=profils["bruno"])
    with pytest.raises(TransitionInterdite):
        contre_passer(brouillon, utilisateur=profils["amina"])
    assert Ecriture.objects.count() == 1


def test_une_ecriture_ne_se_contrepasse_qu_une_fois(decor):  # noqa: F811
    _, projet, profils = decor
    originale = _comptabilisee(projet, profils)
    contre_passer(originale, utilisateur=profils["amina"])
    with pytest.raises(DejaContrepassee, match="OD-2026-000001"):
        contre_passer(originale, utilisateur=profils["amina"])
    assert Ecriture.objects.count() == 2


def test_la_base_garantit_une_seule_contrepassation_par_ecriture(org_a):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_a)])
    originale = creer_piece(
        org_a,
        2026,
        1,
        [{"compte": "6011", "debit": "5"}, {"compte": "5211", "credit": "5"}],
    )
    inverse = [{"compte": "6011", "credit": "5"}, {"compte": "5211", "debit": "5"}]
    creer_piece(org_a, 2026, 2, inverse, statut="draft", reverses=originale)
    with pytest.raises(IntegrityError, match="uq_ecriture_une_contrepassation"):
        creer_piece(org_a, 2026, 3, inverse, statut="draft", reverses=originale)


def test_une_contrepassation_ne_se_contrepasse_pas(decor):  # noqa: F811
    _, projet, profils = decor
    originale = _comptabilisee(projet, profils)
    inverse = contre_passer(originale, utilisateur=profils["amina"])
    valider_ecriture(inverse, utilisateur=profils["bruno"])
    comptabiliser_ecriture(inverse, utilisateur=profils["claire"])
    with pytest.raises(ContrepassationImpossible, match="saisissez une nouvelle écriture"):
        contre_passer(inverse, utilisateur=profils["amina"])


# --- habilitation, période ----------------------------------------------------------------


def test_contre_passer_exige_l_habilitation_de_saisie(decor):  # noqa: F811
    _, projet, profils = decor
    originale = _comptabilisee(projet, profils)
    with pytest.raises(PermissionDenied):
        contre_passer(originale, utilisateur=profils["bruno"])  # bruno ne peut que valider
    assert Ecriture.objects.count() == 1


def test_dans_une_periode_close_on_choisit_une_date_dans_une_periode_ouverte(decor):  # noqa: F811
    _, projet, profils = decor
    originale = _comptabilisee(projet, profils)  # 15 mars 2026
    cloturer_periode(Periode.objects.get(exercice__annee=2026, numero=3), utilisateur=None)

    with pytest.raises(PeriodeNonOuverte, match="date comptable"):
        contre_passer(originale, utilisateur=profils["amina"])

    inverse = contre_passer(
        originale, utilisateur=profils["amina"], date_comptable=datetime.date(2026, 4, 2)
    )
    assert (inverse.periode.numero, inverse.accounting_date) == (4, datetime.date(2026, 4, 2))


# --- la contre-passation reste fidèle -----------------------------------------------------


def test_une_contrepassation_retouchee_ne_se_valide_pas(decor):  # noqa: F811
    """Un brouillon se modifie ; une contre-passation qui ne reproduit plus l'originale, non."""
    _, projet, profils = decor
    originale = _comptabilisee(projet, profils)
    inverse = contre_passer(originale, utilisateur=profils["amina"])
    with transaction.atomic():
        LigneEcriture.objects.filter(entry=inverse, account__code="6011").update(
            credit=Decimal("90")
        )
        LigneEcriture.objects.filter(entry=inverse, account__code="5211").update(
            debit=Decimal("90")
        )

    with pytest.raises(EcritureInvalide, match="ne reproduit pas"):
        valider_ecriture(inverse, utilisateur=profils["bruno"])
    assert Ecriture.objects.get(pk=inverse.pk).status == "draft"


def test_la_base_refuse_une_contrepassation_incoherente(org_a):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_a)])
    paire = [{"compte": "6011", "debit": "5"}, {"compte": "5211", "credit": "5"}]
    inverse_lignes = [{"compte": "6011", "credit": "5"}, {"compte": "5211", "debit": "5"}]
    brouillon = creer_piece(org_a, 2026, 1, paire, statut="draft")
    posee = creer_piece(org_a, 2026, 2, paire)

    # On ne contre-passe qu'une écriture comptabilisée.
    with pytest.raises(IntegrityError, match="comptabilisée"):
        creer_piece(org_a, 2026, 3, inverse_lignes, statut="draft", reverses=brouillon)

    # Un autre projet n'a pas la même comptabilité.
    with pytest.raises(IntegrityError, match="même projet"):
        creer_piece(
            org_a,
            2026,
            3,
            inverse_lignes,
            statut="draft",
            reverses=posee,
            project_id=uuid.UUID("aaaaaaaa-0000-0000-0000-0000000000f2"),
        )

    # `origin = reversal` et `reverses` vont ensemble, dans les deux sens.
    modele = creer_piece(org_a, 2026, 4, paire, statut="draft")
    with pytest.raises(IntegrityError, match="ecriture_contrepassation_coherente"):
        Ecriture.objects.filter(pk=modele.pk).update(origin="reversal")
    with pytest.raises(IntegrityError, match="ecriture_contrepassation_coherente"):
        Ecriture.objects.filter(pk=modele.pk).update(reverses=posee)
