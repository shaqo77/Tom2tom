"""Saisie, validation, comptabilisation d'une écriture. Voir L3-T05 (partie a).

Le cycle : brouillon -> validée -> comptabilisée. Chaque transition vérifie, au serveur,
l'habilitation de l'utilisateur sur le projet, la séparation des tâches et le contenu de la
pièce, puis laisse une trace dans le journal d'audit. La contre-passation est la partie b.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from niveau1_socle.comptabilite.models import Ecriture
from niveau1_socle.comptabilite.services import (
    EcritureInvalide,
    PeriodeIntrouvable,
    PeriodeNonOuverte,
    TransitionInterdite,
    comptabiliser_ecriture,
    saisir_ecriture,
    valider_ecriture,
)
from niveau1_socle.exercices.models import Periode
from niveau1_socle.exercices.services import cloturer_periode, creer_exercice
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau1_socle.organisations.models import Organisation
from niveau1_socle.referentiels.axes import ValeurNonImputable
from niveau1_socle.referentiels.comptes import CompteNonImputable
from niveau1_socle.referentiels.models import Compte, ValeurDimension
from tests.outils import _compte, _valeur_axe, assurer_devises, fermer_sans_controle
from tests.test_organisations_bd import _creer_organisation, _creer_projet

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
JOUR = datetime.date(2026, 3, 15)
LIGNES = [
    {"compte": "6011", "debit": "100", "dim1": "COMP-A"},
    {"compte": "5211", "credit": "100"},
]


def _poser(organisation):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


@pytest.fixture
def decor():
    """Une organisation, un projet, un exercice 2026 et trois profils habilités."""
    organisation = _creer_organisation("ORG-A")
    projet = _creer_projet(organisation, "P1")
    _poser(organisation)
    assurer_devises()
    creer_exercice(projet, 2026, utilisateur=None)
    _compte(organisation.id, "6011")
    _compte(organisation.id, "5211")
    _valeur_axe(organisation.id, "COMP-A")
    from niveau1_socle.comptabilite.models import Journal

    Journal.objects.create(org_id=organisation.id, code="OD", label={"fr": "OD"})

    profils = {}
    for nom, operations in {
        "amina": ["consulter", "saisir"],
        "bruno": ["consulter", "valider"],
        "claire": ["consulter", "comptabiliser"],
    }.items():
        utilisateur = Utilisateur.objects.create_user(nom, password="x", org_id=organisation.id)
        role = Role.objects.create(
            org_id=organisation.id, code=nom.upper(), label={"fr": nom}, operations=operations
        )
        Habilitation.objects.create(
            org_id=organisation.id, user_id=utilisateur.id, project_id=projet.id, role=role
        )
        profils[nom] = utilisateur
    return organisation, projet, profils


def _saisir(projet, utilisateur, **champs):
    donnees = {
        "utilisateur": utilisateur,
        "project_id": projet.id,
        "journal": "OD",
        "date_comptable": JOUR,
        "libelle": "Achat de fournitures",
        "lignes": LIGNES,
    } | champs
    return saisir_ecriture(**donnees)


def _journal(organisation):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT action, actor_id, before, after FROM core_auditlog "
            "WHERE object_type = 'ecriture' ORDER BY id"
        )
        return cur.fetchall()


# --- le cycle complet ---------------------------------------------------------------------


def test_le_cycle_complet_brouillon_validee_comptabilisee_est_trace(decor):
    organisation, projet, profils = decor
    ecriture = _saisir(projet, profils["amina"])
    assert (ecriture.status, ecriture.number) == ("draft", None)

    valider_ecriture(ecriture, utilisateur=profils["bruno"])
    assert Ecriture.objects.get(pk=ecriture.pk).status == "validated"

    comptabiliser_ecriture(ecriture, utilisateur=profils["claire"])
    finale = Ecriture.objects.get(pk=ecriture.pk)
    assert (finale.status, finale.number) == ("posted", "OD-2026-000001")
    assert (finale.posted_by, finale.created_by) == (profils["claire"].id, profils["amina"].id)

    journal = _journal(organisation)
    assert [(a, acteur) for a, acteur, _, _ in journal] == [
        ("entry_created", profils["amina"].id),
        ("entry_validated", profils["bruno"].id),
        ("entry_posted", profils["claire"].id),
    ]
    assert '"number":"OD-2026-000001"' in journal[-1][3].replace(" ", "")
    assert verifier_chaine(organisation.id) is None


# --- la saisie ----------------------------------------------------------------------------


def test_la_saisie_enregistre_une_piece_equilibree_avec_ses_axes(decor):
    organisation, projet, profils = decor
    ecriture = _saisir(projet, profils["amina"], cle_idempotence="capture-001")

    assert ecriture.lignes.count() == 2
    ligne = ecriture.lignes.get(line_no=1)
    assert ligne.account.code == "6011" and ligne.dim1.code == "COMP-A"
    assert (ecriture.origin, ecriture.currency_id) == ("saisie", "DJF")
    assert ecriture.periode.numero == 3  # la période est déduite de la date comptable


def test_une_cle_dindempotence_ne_cree_pas_deux_ecritures(decor):
    _, projet, profils = decor
    premiere = _saisir(projet, profils["amina"], cle_idempotence="capture-001")
    seconde = _saisir(projet, profils["amina"], cle_idempotence="capture-001")
    assert premiere.pk == seconde.pk
    assert Ecriture.objects.count() == 1


def test_une_saisie_desequilibree_est_refusee_avant_toute_ecriture(decor):
    _, projet, profils = decor
    with pytest.raises(EcritureInvalide, match="déséquilibrée"):
        _saisir(
            projet,
            profils["amina"],
            lignes=[{"compte": "6011", "debit": "100"}, {"compte": "5211", "credit": "99"}],
        )
    assert Ecriture.objects.count() == 0


def test_la_saisie_refuse_un_total_une_date_hors_exercice_et_une_periode_close(decor):
    organisation, projet, profils = decor
    total = Compte.objects.get(code="6011")
    Compte.objects.filter(pk=total.pk).update(imputable=False)
    with pytest.raises(CompteNonImputable):
        _saisir(projet, profils["amina"])
    Compte.objects.filter(pk=total.pk).update(imputable=True)

    with pytest.raises(PeriodeIntrouvable, match="2031"):
        _saisir(projet, profils["amina"], date_comptable=datetime.date(2031, 1, 1))

    cloturer_periode(Periode.objects.get(exercice__annee=2026, numero=3), utilisateur=None)
    with pytest.raises(PeriodeNonOuverte, match="3"):
        _saisir(projet, profils["amina"])
    assert Ecriture.objects.count() == 0


def test_la_saisie_refuse_une_valeur_dagrement_non_imputable(decor):
    organisation, projet, profils = decor
    ValeurDimension.objects.filter(code="COMP-A").update(is_postable=False)
    with pytest.raises(ValeurNonImputable):
        _saisir(projet, profils["amina"])


# --- habilitation et séparation des tâches ------------------------------------------------


def test_chaque_operation_exige_son_habilitation(decor):
    _, projet, profils = decor
    with pytest.raises(PermissionDenied):
        _saisir(projet, profils["bruno"])  # bruno ne peut que valider
    ecriture = _saisir(projet, profils["amina"])
    with pytest.raises(PermissionDenied):
        valider_ecriture(
            ecriture, utilisateur=profils["claire"]
        )  # claire : comptabiliser seulement
    valider_ecriture(ecriture, utilisateur=profils["bruno"])
    with pytest.raises(PermissionDenied):
        comptabiliser_ecriture(ecriture, utilisateur=profils["bruno"])
    assert Ecriture.objects.get(pk=ecriture.pk).status == "validated"


def test_lauteur_ne_valide_pas_sa_propre_ecriture_sauf_si_lorganisation_le_permet(decor):
    organisation, projet, profils = decor
    valideur = Role.objects.get(code="AMINA")
    Role.objects.filter(pk=valideur.pk).update(operations=["consulter", "saisir", "valider"])

    ecriture = _saisir(projet, profils["amina"])
    with pytest.raises(PermissionDenied, match="vous-même saisie"):
        valider_ecriture(ecriture, utilisateur=profils["amina"])
    assert Ecriture.objects.get(pk=ecriture.pk).status == "draft"

    Organisation.objects.filter(pk=organisation.pk).update(separation_des_taches=False)
    valider_ecriture(ecriture, utilisateur=profils["amina"])
    assert Ecriture.objects.get(pk=ecriture.pk).status == "validated"


# --- validité de la pièce -----------------------------------------------------------------


def test_valider_refuse_une_ecriture_vide_ou_a_zero_et_liste_toutes_les_raisons(decor):
    _, projet, profils = decor
    vide = _saisir(projet, profils["amina"], lignes=[])
    with pytest.raises(EcritureInvalide) as erreur:
        valider_ecriture(vide, utilisateur=profils["bruno"])
    assert any("deux lignes" in str(raison) for raison in erreur.value.raisons)

    zero = _saisir(
        projet,
        profils["amina"],
        lignes=[{"compte": "6011", "debit": "0"}, {"compte": "5211", "credit": "0"}],
        cle_idempotence="zero",
    )
    with pytest.raises(EcritureInvalide, match="montant nul"):
        valider_ecriture(zero, utilisateur=profils["bruno"])


def test_valider_refuse_un_compte_ou_une_valeur_devenus_inutilisables(decor):
    organisation, projet, profils = decor
    ecriture = _saisir(projet, profils["amina"])
    Compte.objects.filter(code="5211").update(actif=False)
    ValeurDimension.objects.filter(code="COMP-A").update(is_active=False)

    with pytest.raises(EcritureInvalide) as erreur:
        valider_ecriture(ecriture, utilisateur=profils["bruno"])
    assert len(erreur.value.raisons) == 2  # le compte inactif ET la valeur d'axe inactive
    assert Ecriture.objects.get(pk=ecriture.pk).status == "draft"


# --- transitions --------------------------------------------------------------------------


def test_les_transitions_hors_cycle_sont_interdites(decor):
    _, projet, profils = decor
    ecriture = _saisir(projet, profils["amina"])
    with pytest.raises(TransitionInterdite):
        comptabiliser_ecriture(ecriture, utilisateur=profils["claire"])  # pas encore validée

    valider_ecriture(ecriture, utilisateur=profils["bruno"])
    with pytest.raises(TransitionInterdite):
        valider_ecriture(ecriture, utilisateur=profils["bruno"])  # déjà validée

    comptabiliser_ecriture(ecriture, utilisateur=profils["claire"])
    with pytest.raises(TransitionInterdite):
        comptabiliser_ecriture(ecriture, utilisateur=profils["claire"])  # déjà comptabilisée
    assert Ecriture.objects.get(pk=ecriture.pk).number == "OD-2026-000001"


def test_comptabiliser_refuse_une_periode_close_avec_un_message_clair(decor):
    _, projet, profils = decor
    ecriture = _saisir(projet, profils["amina"])
    valider_ecriture(ecriture, utilisateur=profils["bruno"])
    fermer_sans_controle(3)

    with pytest.raises(PeriodeNonOuverte, match="période 3"):
        comptabiliser_ecriture(ecriture, utilisateur=profils["claire"])
    assert Ecriture.objects.get(pk=ecriture.pk).status == "validated"


def test_comptabiliser_reverifie_le_contenu_devenu_invalide_depuis_la_validation(decor):
    _, projet, profils = decor
    ecriture = _saisir(projet, profils["amina"])
    valider_ecriture(ecriture, utilisateur=profils["bruno"])
    Compte.objects.filter(code="6011").update(actif=False)

    with pytest.raises(EcritureInvalide, match="inactif"):
        comptabiliser_ecriture(ecriture, utilisateur=profils["claire"])
    assert Ecriture.objects.get(pk=ecriture.pk).number is None


def test_un_utilisateur_dune_autre_organisation_na_aucune_prise(decor):
    organisation, projet, profils = decor
    autre = _creer_organisation("ORG-B")
    intrus = Utilisateur.objects.create_user("intrus", password="x", org_id=autre.id)
    _poser(organisation)  # _creer_organisation a déplacé le périmètre vers l'organisation B
    ecriture = _saisir(projet, profils["amina"])
    _poser(autre)
    with pytest.raises((PermissionDenied, Ecriture.DoesNotExist)):
        valider_ecriture(ecriture, utilisateur=intrus)
    _poser(organisation)
    assert Ecriture.objects.get(pk=ecriture.pk).status == "draft"
