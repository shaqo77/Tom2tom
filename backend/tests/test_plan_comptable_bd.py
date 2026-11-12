"""Plan comptable : comptes, hiérarchie, imputabilité. Voir L2-T02."""

import pytest
from django.db import IntegrityError, connection, transaction

from niveau1_socle.referentiels.comptes import (
    CompteInactif,
    CompteIntrouvable,
    CompteNonImputable,
    exiger_compte_imputable,
)
from niveau1_socle.referentiels.models import Compte
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)


def _compte(organisation, code, *, parent=None, imputable=True, actif=True, **champs):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])
    donnees = {
        "org_id": organisation.id,
        "code": code,
        "label": {"fr": f"Compte {code}", "en": f"Account {code}"},
        "classe": int(code[0]),
        "sens_normal": "debit",
        "imputable": imputable,
        "actif": actif,
        "parent": parent,
    }
    donnees.update(champs)
    return Compte.objects.create(**donnees)


def test_un_compte_non_imputable_refuse_limputation_directe():
    """Contrôle de L2-T02."""
    organisation = _creer_organisation("ORG-A")
    total = _compte(organisation, "60", imputable=False)
    detail = _compte(organisation, "601", parent=total)

    assert exiger_compte_imputable("601").pk == detail.pk
    with pytest.raises(CompteNonImputable, match="60"):
        exiger_compte_imputable("60")


def test_un_compte_inactif_ou_inconnu_refuse_limputation():
    organisation = _creer_organisation("ORG-A")
    _compte(organisation, "6011", actif=False)
    with pytest.raises(CompteInactif, match="6011"):
        exiger_compte_imputable("6011")
    with pytest.raises(CompteIntrouvable, match="9999"):
        exiger_compte_imputable("9999")


def test_un_compte_imputable_ne_peut_pas_avoir_denfant():
    """La base garantit la hiérarchie : seuls les comptes feuilles sont imputables."""
    organisation = _creer_organisation("ORG-A")
    feuille = _compte(organisation, "601")
    with pytest.raises(IntegrityError, match="imputable"), transaction.atomic():
        _compte(organisation, "6011", parent=feuille)


def test_un_compte_qui_a_des_enfants_ne_peut_pas_devenir_imputable():
    organisation = _creer_organisation("ORG-A")
    total = _compte(organisation, "60", imputable=False)
    _compte(organisation, "601", parent=total)
    with pytest.raises(IntegrityError, match="enfant"), transaction.atomic():
        Compte.objects.filter(pk=total.pk).update(imputable=True)


def test_un_compte_ne_peut_etre_son_propre_parent():
    organisation = _creer_organisation("ORG-A")
    compte = _compte(organisation, "60", imputable=False)
    with pytest.raises(IntegrityError), transaction.atomic():
        Compte.objects.filter(pk=compte.pk).update(parent=compte)


@pytest.mark.parametrize(
    "code, champs",
    [
        ("6A1", {"classe": 6}),  # code non numérique
        ("601", {"classe": 5}),  # classe différente du premier chiffre
        ("601", {"classe": 0}),
        ("601", {"sens_normal": "neutre"}),
        ("0601", {"classe": 0}),  # la classe 0 n'existe pas
    ],
)
def test_les_codes_classes_et_sens_sont_contraints_en_base(code, champs):
    organisation = _creer_organisation("ORG-A")
    with pytest.raises(IntegrityError), transaction.atomic():
        _compte(organisation, code, **champs)


def test_le_code_est_unique_par_organisation_et_libre_entre_organisations():
    a = _creer_organisation("ORG-A")
    b = _creer_organisation("ORG-B")
    _compte(a, "601")
    _compte(b, "601")
    with pytest.raises(IntegrityError), transaction.atomic():
        _compte(a, "601")


def test_les_libelles_sont_multilingues_et_le_plan_est_isole():
    a = _creer_organisation("ORG-A")
    _compte(a, "601", label={"fr": "Achats", "en": "Purchases", "ar": "مشتريات"})
    assert Compte.objects.get(code="601").label["ar"] == "مشتريات"

    _creer_organisation("ORG-B")  # pose le périmètre de B
    assert Compte.objects.count() == 0
    with pytest.raises(CompteIntrouvable):
        exiger_compte_imputable("601")
