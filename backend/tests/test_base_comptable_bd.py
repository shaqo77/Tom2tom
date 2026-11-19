# ruff: noqa: F811, E501
"""La base comptable d'un projet a un EFFET : elle décide si le projet réserve du budget par engagement.
L11-A3.

Avant : `accounting_basis` était stocké (et verrouillé après la première écriture) mais aucun code ne
le lisait. Une promesse que rien ne tenait : un projet « en caisse » créait des engagements comme les
autres.

Ce que les trois valeurs veulent dire ICI (et rien de plus) :
- `cash` : comptabilité de caisse PURE : le projet ne réserve pas de budget (aucun engagement) ;
- `cash_with_commitments` : caisse, avec engagements suivis : un engagement réduit le disponible ;
- `accrual` : comptabilité d'engagement : idem.
La reconnaissance d'une charge reste celle de la date de l'écriture, saisie par les utilisateurs.
"""

import pytest
from django.contrib.auth import get_user_model

from niveau1_socle.budget.engagements import creer_engagement
from niveau1_socle.budget.services import BudgetInvalide
from niveau1_socle.habilitations.models import Habilitation, Role
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_organisations_bd import _creer_projet

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()


@pytest.fixture
def projets(decor):
    organisation, _, profils = decor
    eva = Utilisateur.objects.create_user("eva", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id, code="EVA", label={"fr": "eva"}, operations=["consulter", "saisir"]
    )
    par_base = {}
    for base in ("cash", "cash_with_commitments", "accrual"):
        projet = _creer_projet(organisation, f"P-{base}"[:12], accounting_basis=base)
        Habilitation.objects.create(
            org_id=organisation.id, user_id=eva.id, project_id=projet.id, role=role
        )
        par_base[base] = projet
    return eva, par_base


def _engager(eva, projet, reference="ENG-1"):
    return creer_engagement(
        utilisateur=eva, project_id=projet.id, reference=reference, annee=2026, montant="100"
    )


def test_un_projet_en_comptabilite_de_caisse_ne_reserve_pas_de_budget(projets):
    eva, par_base = projets
    with pytest.raises(BudgetInvalide, match="caisse") as erreur:
        _engager(eva, par_base["cash"])
    # Le refus dit quoi faire, et que le réglage est figé après la première écriture.
    assert "engagements" in str(erreur.value) and "première écriture" in str(erreur.value)


@pytest.mark.parametrize("base", ["cash_with_commitments", "accrual"])
def test_un_projet_avec_engagements_en_cree(projets, base):
    eva, par_base = projets
    assert _engager(eva, par_base[base]).reference == "ENG-1"


def test_le_refus_de_la_caisse_ne_laisse_aucun_engagement(projets):
    from niveau1_socle.budget.models import Engagement

    eva, par_base = projets
    with pytest.raises(BudgetInvalide):
        _engager(eva, par_base["cash"])
    assert Engagement.objects.filter(project_id=par_base["cash"].id).count() == 0


def test_la_base_d_un_projet_ne_change_pas_apres_la_premiere_ecriture(projets):
    """Garde-fou existant (déclencheur) : l'effet de la base ne peut donc pas être contourné en la
    changeant une fois le projet en service."""
    from django.db import IntegrityError, transaction

    from niveau1_socle.organisations.models import Projet
    from tests.outils import creer_piece

    eva, par_base = projets
    projet = par_base["cash"]
    from niveau1_socle.exercices.services import creer_exercice

    creer_exercice(projet, 2026, utilisateur=None)
    creer_piece(
        projet.org_id, 2026, 2,
        [{"compte": "6011", "debit": "10"}, {"compte": "5211", "credit": "10"}], project_id=projet.id,
    )  # fmt: skip
    with pytest.raises(IntegrityError), transaction.atomic():
        Projet.objects.filter(pk=projet.pk).update(accounting_basis="accrual")
