"""Axes configurables : emplacements fixes, signification propre à l'organisation. Voir L2-T03.

Les emplacements (1 à 4) sont fixes dans le schéma ; ce qu'on y place est configuré
par organisation. On y gagne l'indexation et les contraintes d'intégrité qu'un
modèle clé-valeur interdirait.
"""

import pytest
from django.db import IntegrityError, connection, transaction

from niveau1_socle.referentiels.axes import (
    ValeurInactive,
    ValeurIntrouvable,
    ValeurNonImputable,
    exiger_valeur_imputable,
)
from niveau1_socle.referentiels.models import PlanDimension, ValeurDimension
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)


def _poser(organisation):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


def _plan(organisation, code, *, slot=1, kind="gestion", **champs):
    _poser(organisation)
    donnees = {
        "org_id": organisation.id,
        "kind": kind,
        "slot": slot,
        "code": code,
        "label": {"fr": code, "en": code},
    }
    donnees.update(champs)
    return PlanDimension.objects.create(**donnees)


def _valeur(organisation, plan, code, *, parent=None, is_postable=True, **champs):
    _poser(organisation)
    donnees = {
        "org_id": organisation.id,
        "plan": plan,
        "parent": parent,
        "code": code,
        "label": {"fr": code, "en": code},
        "is_postable": is_postable,
    }
    donnees.update(champs)
    return ValeurDimension.objects.create(**donnees)


def test_deux_organisations_placent_des_plans_differents_sur_lemplacement_1():
    """Contrôle de L2-T03."""
    a = _creer_organisation("ORG-A")
    b = _creer_organisation("ORG-B")
    _plan(a, "COMPOSANTES", slot=1)
    _plan(b, "ZONES", slot=1)

    _poser(a)
    assert PlanDimension.objects.get(slot=1).code == "COMPOSANTES"
    _poser(b)
    assert PlanDimension.objects.get(slot=1).code == "ZONES"


def test_un_seul_plan_par_organisation_type_et_emplacement():
    organisation = _creer_organisation("ORG-A")
    _plan(organisation, "COMPOSANTES", slot=1, kind="gestion")
    with pytest.raises(IntegrityError), transaction.atomic():
        _plan(organisation, "ZONES", slot=1, kind="gestion")
    # Même emplacement, autre type d'axe : autorisé.
    _plan(organisation, "BENEFICIAIRES", slot=1, kind="auxiliaire")


@pytest.mark.parametrize("champs", [{"slot": 0}, {"slot": 5}, {"kind": "analytique"}])
def test_emplacements_et_types_sont_des_ensembles_fermes(champs):
    organisation = _creer_organisation("ORG-A")
    with pytest.raises(IntegrityError), transaction.atomic():
        _plan(organisation, "X", **champs)


def test_une_valeur_nest_imputable_quen_feuille():
    organisation = _creer_organisation("ORG-A")
    plan = _plan(organisation, "COMPOSANTES")
    racine = _valeur(organisation, plan, "COMP-A", is_postable=False)
    activite = _valeur(organisation, plan, "ACT-01", parent=racine)

    assert exiger_valeur_imputable("COMPOSANTES", "ACT-01").pk == activite.pk
    with pytest.raises(ValeurNonImputable, match="COMP-A"):
        exiger_valeur_imputable("COMPOSANTES", "COMP-A")


def test_la_base_refuse_un_parent_imputable_et_une_feuille_devenue_parent():
    organisation = _creer_organisation("ORG-A")
    plan = _plan(organisation, "COMPOSANTES")
    feuille = _valeur(organisation, plan, "ACT-01")
    with pytest.raises(IntegrityError, match="imputable"), transaction.atomic():
        _valeur(organisation, plan, "TACHE-1", parent=feuille)

    racine = _valeur(organisation, plan, "COMP-A", is_postable=False)
    _valeur(organisation, plan, "ACT-02", parent=racine)
    with pytest.raises(IntegrityError, match="enfant"), transaction.atomic():
        ValeurDimension.objects.filter(pk=racine.pk).update(is_postable=True)


def test_une_valeur_ne_se_range_pas_sous_le_parent_dun_autre_plan():
    organisation = _creer_organisation("ORG-A")
    p1 = _plan(organisation, "COMPOSANTES", slot=1)
    p2 = _plan(organisation, "ZONES", slot=2)
    racine = _valeur(organisation, p1, "COMP-A", is_postable=False)
    with pytest.raises(IntegrityError, match="plan"), transaction.atomic():
        _valeur(organisation, p2, "Z-1", parent=racine)


def test_une_valeur_inactive_ou_inconnue_refuse_limputation():
    organisation = _creer_organisation("ORG-A")
    plan = _plan(organisation, "COMPOSANTES")
    _valeur(organisation, plan, "ACT-09", is_active=False)
    with pytest.raises(ValeurInactive, match="ACT-09"):
        exiger_valeur_imputable("COMPOSANTES", "ACT-09")
    with pytest.raises(ValeurIntrouvable, match="NUL"):
        exiger_valeur_imputable("COMPOSANTES", "NUL")
    with pytest.raises(ValeurIntrouvable):
        exiger_valeur_imputable("PLAN-INCONNU", "ACT-09")


def test_le_code_de_valeur_est_unique_par_plan():
    organisation = _creer_organisation("ORG-A")
    p1 = _plan(organisation, "COMPOSANTES", slot=1)
    p2 = _plan(organisation, "ZONES", slot=2)
    _valeur(organisation, p1, "X1")
    _valeur(organisation, p2, "X1")  # autre plan : autorisé
    with pytest.raises(IntegrityError), transaction.atomic():
        _valeur(organisation, p1, "X1")


def test_les_axes_sont_isoles_et_les_libelles_multilingues():
    a = _creer_organisation("ORG-A")
    plan = _plan(a, "COMPOSANTES", label={"fr": "Composantes", "en": "Components", "ar": "مكونات"})
    _valeur(a, plan, "COMP-A")
    assert PlanDimension.objects.get(code="COMPOSANTES").label["ar"] == "مكونات"

    _creer_organisation("ORG-B")  # pose le périmètre de B
    assert PlanDimension.objects.count() == 0
    assert ValeurDimension.objects.count() == 0
