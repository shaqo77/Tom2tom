"""Clôture mensuelle : une liste de contrôle bloquante. Voir L3-T08 (partie a).

`cloturer_periode` refuse tant qu'un contrôle de clôture signale un problème, et les liste tous :
- des écritures non comptabilisées (brouillon ou validée) dans la période ;
- des groupes de lignes de tiers qui se soldent mais ne sont pas lettrés.

Le troisième contrôle du plan, « rapprochements non soldés », attend les comptes bancaires de L4
(rapprochement bancaire, L3-T07b) : le mécanisme est prêt à l'accueillir.
"""

import pytest

from niveau1_socle.comptabilite.lettrage import lettrer
from niveau1_socle.exercices import services
from niveau1_socle.exercices.models import Periode
from niveau1_socle.exercices.services import ClotureImpossible, cloturer_periode
from tests.outils import creer_piece
from tests.test_cycle_ecriture_bd import _poser, decor  # noqa: F401
from tests.test_organisations_bd import _creer_organisation, _creer_projet

pytestmark = pytest.mark.django_db(transaction=True)


def _periode(numero, projet=None):
    filtre = {"exercice__project_id": projet.id} if projet else {}
    return Periode.objects.get(exercice__annee=2026, numero=numero, **filtre)


def _facture(org, projet, periode, montant="1000", tiers="FRN-001"):
    return creer_piece(
        org.id,
        2026,
        periode,
        [
            {"compte": "6011", "debit": montant},
            {"compte": "4011", "credit": montant, "tiers": tiers},
        ],
        project_id=projet.id,
    )


def _reglement(org, projet, periode, montant="1000", tiers="FRN-001"):
    return creer_piece(
        org.id,
        2026,
        periode,
        [
            {"compte": "4011", "debit": montant, "tiers": tiers},
            {"compte": "5211", "credit": montant},
        ],
        project_id=projet.id,
    )


def test_les_controles_de_la_comptabilite_sont_enregistres_au_demarrage():
    assert len(services.VERIFICATIONS_DE_CLOTURE) >= 2


# --- écritures non comptabilisées ---------------------------------------------------------


@pytest.mark.parametrize("statut", ["draft", "validated"])
def test_une_ecriture_non_comptabilisee_bloque_la_cloture_de_sa_periode(decor, statut):  # noqa: F811
    organisation, projet, _ = decor
    ecriture = _facture(organisation, projet, 3)
    brouillon = creer_piece(
        organisation.id,
        2026,
        3,
        [{"compte": "6011", "debit": "5"}, {"compte": "5211", "credit": "5"}],
        project_id=projet.id,
        statut=statut,
    )
    assert ecriture.status == "posted"

    with pytest.raises(ClotureImpossible, match="1 écriture non comptabilisée"):
        cloturer_periode(_periode(3), utilisateur=None)
    assert _periode(3).status == "ouverte"

    brouillon.delete()  # un brouillon se supprime
    cloturer_periode(_periode(3), utilisateur=None)
    assert _periode(3).status == "close"


def test_seules_les_ecritures_de_la_periode_et_du_projet_bloquent(decor):  # noqa: F811
    organisation, projet, _ = decor
    autre_projet = _creer_projet(organisation, "P2")
    _poser(organisation)
    # Brouillon d'une autre période du même projet : ne bloque pas la période 3.
    creer_piece(
        organisation.id,
        2026,
        4,
        [{"compte": "6011", "debit": "5"}, {"compte": "5211", "credit": "5"}],
        project_id=projet.id,
        statut="draft",
    )
    # Brouillon d'un autre projet, de la même période : ne bloque pas non plus.
    from niveau1_socle.exercices.services import creer_exercice

    creer_exercice(autre_projet, 2026, utilisateur=None)
    creer_piece(
        organisation.id,
        2026,
        3,
        [{"compte": "6011", "debit": "5"}, {"compte": "5211", "credit": "5"}],
        project_id=autre_projet.id,
        statut="draft",
    )
    _facture(organisation, projet, 3)

    cloturer_periode(_periode(3, projet), utilisateur=None)
    assert _periode(3, projet).status == "close"


def test_une_periode_sans_ecriture_se_cloture(decor):  # noqa: F811
    cloturer_periode(_periode(5), utilisateur=None)
    assert _periode(5).status == "close"


# --- groupes soldés non lettrés -----------------------------------------------------------


def test_un_groupe_de_tiers_qui_se_solde_doit_etre_lettre_avant_la_cloture(decor):  # noqa: F811
    organisation, projet, profils = decor
    facture = _facture(organisation, projet, 3)
    reglement = _reglement(organisation, projet, 4)

    # La facture seule ne se solde pas : la période 3 se clôture.
    cloturer_periode(_periode(3), utilisateur=None)

    # Avec le règlement, le groupe se solde : la période 4 attend le lettrage.
    with pytest.raises(ClotureImpossible, match=r"4011 / FRN-001 \(2 lignes\)"):
        cloturer_periode(_periode(4), utilisateur=None)

    lettrer(
        [
            facture.lignes.get(account__code="4011"),
            reglement.lignes.get(account__code="4011"),
        ],
        utilisateur=profils["claire"],
    )
    cloturer_periode(_periode(4), utilisateur=None)
    assert _periode(4).status == "close"


def test_une_facture_impayee_ne_bloque_jamais_la_cloture(decor):  # noqa: F811
    organisation, projet, _ = decor
    _facture(organisation, projet, 3, "1000")
    _reglement(organisation, projet, 3, "400")  # règlement partiel : le groupe ne se solde pas
    cloturer_periode(_periode(3), utilisateur=None)
    assert _periode(3).status == "close"


def test_un_groupe_soldé_dun_autre_tiers_ou_compte_ne_se_melange_pas(decor):  # noqa: F811
    organisation, projet, _ = decor
    _facture(organisation, projet, 3, "1000", tiers="FRN-001")
    _reglement(organisation, projet, 3, "1000", tiers="FRN-002")  # autre tiers : pas de solde
    cloturer_periode(_periode(3), utilisateur=None)
    assert _periode(3).status == "close"


# --- toutes les raisons d'un coup ---------------------------------------------------------


def test_la_cloture_liste_toutes_les_raisons_d_un_coup(decor):  # noqa: F811
    organisation, projet, _ = decor
    _facture(organisation, projet, 3)
    _reglement(organisation, projet, 3)  # groupe soldé non lettré
    creer_piece(
        organisation.id,
        2026,
        3,
        [{"compte": "6011", "debit": "5"}, {"compte": "5211", "credit": "5"}],
        project_id=projet.id,
        statut="draft",
    )

    with pytest.raises(ClotureImpossible) as erreur:
        cloturer_periode(_periode(3), utilisateur=None)

    assert len(erreur.value.raisons) == 2
    assert any("non comptabilisée" in str(raison) for raison in erreur.value.raisons)
    assert any("non lettrés" in str(raison) for raison in erreur.value.raisons)


def test_les_controles_ne_voient_que_l_organisation_courante(decor):  # noqa: F811
    organisation, projet, _ = decor
    _facture(organisation, projet, 3)
    _reglement(organisation, projet, 3)
    autre = _creer_organisation("ORG-B")
    _poser(autre)  # l'organisation B ne voit pas les lignes de A : rien à lettrer chez elle
    projet_b = _creer_projet(autre, "PB")
    from niveau1_socle.exercices.services import creer_exercice

    creer_exercice(projet_b, 2026, utilisateur=None)
    cloturer_periode(
        Periode.objects.get(exercice__project_id=projet_b.id, numero=3), utilisateur=None
    )
