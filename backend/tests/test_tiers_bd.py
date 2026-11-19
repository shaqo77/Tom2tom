"""Tiers : données personnelles, journalisation des lectures, rétention. Voir L2-T04."""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction

from core.audit import verifier_chaine
from niveau1_socle.referentiels.models import Tiers
from niveau1_socle.referentiels.tiers import (
    AnonymisationImpossible,
    TiersIntrouvable,
    anonymiser_tiers,
    consulter_coordonnees_bancaires,
    consulter_tiers,
    tiers_a_anonymiser,
)
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
IBAN = "DJ21 0001 0000 0123 4567 8901 234"


def _poser(organisation):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


def _tiers(organisation, code="FRN-001", **champs):
    _poser(organisation)
    donnees = {
        "org_id": organisation.id,
        "code": code,
        "nature": "fournisseur",
        "nom": "Société Tadjourah Équipements",
        "identification": {"nif": "123456789", "adresse": "Rue de Venise, Djibouti"},
        "coordonnees_bancaires": {"banque": "BCIMR", "iban": IBAN},
        "actif": True,
    }
    donnees.update(champs)
    return Tiers.objects.create(**donnees)


@pytest.fixture
def decor():
    organisation = _creer_organisation("ORG-A")
    amina = Utilisateur.objects.create_user("amina", password="x", org_id=organisation.id)
    _poser(organisation)
    return organisation, amina


def _journal(organisation):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT action, object_type, actor_id, before, after FROM core_auditlog "
            "WHERE org_id = %s ORDER BY id",
            [str(organisation.id)],
        )
        return cur.fetchall()


def test_chaque_consultation_dun_tiers_est_journalisee_sans_donnee_personnelle(decor):
    organisation, amina = decor
    tiers = _tiers(organisation)

    lu = consulter_tiers(amina, "FRN-001")

    assert lu.pk == tiers.pk
    action, objet, acteur, avant, apres = _journal(organisation)[-1]
    assert (action, objet, acteur) == ("tiers_read", "tiers", amina.id)
    assert avant is None and apres is None  # qui a lu quoi, jamais ce qu'il a vu
    assert verifier_chaine(organisation.id) is None


def test_la_lecture_des_coordonnees_bancaires_est_journalisee_a_part(decor):
    organisation, amina = decor
    _tiers(organisation)

    coordonnees = consulter_coordonnees_bancaires(amina, "FRN-001")

    assert coordonnees["iban"] == IBAN
    journal = _journal(organisation)
    assert journal[-1][0] == "tiers_bank_details_read"
    # Le journal lui-même ne contient jamais l'IBAN.
    assert IBAN not in repr(journal)


def test_consulter_un_tiers_inconnu_ne_journalise_rien_et_leve_une_erreur(decor):
    organisation, amina = decor
    with pytest.raises(TiersIntrouvable):
        consulter_tiers(amina, "INCONNU")
    assert _journal(organisation) == []


def test_le_code_est_unique_par_organisation_la_nature_est_un_ensemble_ferme(decor):
    organisation, _ = decor
    _tiers(organisation)
    with pytest.raises(IntegrityError), transaction.atomic():
        _tiers(organisation)
    with pytest.raises(IntegrityError), transaction.atomic():
        _tiers(organisation, code="X-1", nature="inconnue")
    autre = _creer_organisation("ORG-B")
    _tiers(autre)  # même code dans une autre organisation : autorisé


def test_un_tiers_dune_autre_organisation_reste_invisible(decor):
    organisation, amina = decor
    _tiers(organisation)
    autre = _creer_organisation("ORG-B")
    intrus = Utilisateur.objects.create_user("intrus", password="x", org_id=autre.id)
    _poser(autre)
    with pytest.raises(TiersIntrouvable):
        consulter_tiers(intrus, "FRN-001")
    assert Tiers.objects.count() == 0


def test_seuls_les_tiers_inactifs_dont_la_retention_est_echue_sont_a_anonymiser(decor):
    organisation, _ = decor
    _tiers(organisation, "ECHU", actif=False, retention_until=datetime.date(2026, 6, 30))
    _tiers(organisation, "PAS-ECHU", actif=False, retention_until=datetime.date(2027, 1, 1))
    _tiers(organisation, "ACTIF", actif=True, retention_until=datetime.date(2026, 1, 1))
    _tiers(organisation, "SANS-DELAI", actif=False)

    codes = {t.code for t in tiers_a_anonymiser(datetime.date(2026, 12, 31))}
    assert codes == {"ECHU"}


def test_lanonymisation_efface_les_donnees_personnelles_et_garde_le_code(decor):
    organisation, amina = decor
    tiers = _tiers(organisation, actif=False, retention_until=datetime.date(2026, 6, 30))

    anonymiser_tiers(tiers, utilisateur=amina, aujourdhui=datetime.date(2026, 12, 31))

    tiers = Tiers.objects.get(pk=tiers.pk)
    assert tiers.code == "FRN-001"  # les écritures qui le référencent restent lisibles
    assert tiers.nom == "ANONYMISÉ"
    assert tiers.identification == {} and tiers.coordonnees_bancaires is None
    assert tiers.anonymise_le is not None
    assert tiers.nom not in repr(_journal(organisation))
    assert _journal(organisation)[-1][0] == "tiers_anonymized"
    assert IBAN not in repr(_journal(organisation))


def test_on_nanonymise_ni_un_tiers_actif_ni_avant_la_fin_de_la_retention(decor):
    organisation, amina = decor
    actif = _tiers(organisation, "A", actif=True, retention_until=datetime.date(2026, 1, 1))
    futur = _tiers(organisation, "F", actif=False, retention_until=datetime.date(2027, 1, 1))
    sans = _tiers(organisation, "S", actif=False)
    for tiers in (actif, futur, sans):
        with pytest.raises(AnonymisationImpossible):
            anonymiser_tiers(tiers, utilisateur=amina, aujourdhui=datetime.date(2026, 12, 31))
        assert Tiers.objects.get(pk=tiers.pk).nom != "ANONYMISÉ"
