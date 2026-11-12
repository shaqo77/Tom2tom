"""Organisation et projet : cloisonnement et garde-fous. Voir L1-T01."""

import datetime
import uuid

import pytest
from django.db import IntegrityError, ProgrammingError, connection, transaction

from niveau1_socle.organisations.models import Organisation, Projet
from niveau4_reporting.moteur.models import LigneEcriture

pytestmark = pytest.mark.django_db(transaction=True)


def _poser(org_id):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])


def _creer_organisation(code, *, pays="DJ", monnaie="DJF"):
    """Sous RLS, une organisation se crée dans son propre périmètre."""
    identifiant = uuid.uuid4()
    _poser(identifiant)
    return Organisation.objects.create(
        id=identifiant,
        code=code,
        raison_sociale=f"Organisation {code}",
        pays=pays,
        monnaie_tenue=monnaie,
        langues_actives=["fr", "en"],
    )


def _creer_projet(organisation, code, **champs):
    _poser(organisation.id)
    donnees = {
        "org_id": organisation.id,
        "code": code,
        "label": {"fr": f"Projet {code}", "en": f"Project {code}"},
        "start_date": datetime.date(2026, 1, 1),
        "base_currency": "DJF",
        "accounting_basis": "accrual",
        "status": "active",
    }
    donnees.update(champs)
    return Projet.objects.create(**donnees)


def test_deux_organisations_et_deux_projets_chacune_se_creent_sans_erreur():
    """Contrôle de L1-T01."""
    orgs = [_creer_organisation("UGP-DJ"), _creer_organisation("ONG-ET", pays="ET", monnaie="ETB")]
    projets = {o.code: [_creer_projet(o, f"P{i}") for i in (1, 2)] for o in orgs}

    for organisation in orgs:
        _poser(organisation.id)
        assert Projet.objects.count() == 2
        assert {p.id for p in Projet.objects.all()} == {p.id for p in projets[organisation.code]}


def test_une_organisation_ne_voit_ni_les_projets_ni_la_fiche_dune_autre():
    a = _creer_organisation("ORG-A")
    b = _creer_organisation("ORG-B")
    _creer_projet(a, "P1")
    _creer_projet(b, "P1")

    _poser(a.id)
    assert list(Organisation.objects.values_list("code", flat=True)) == ["ORG-A"]
    assert Projet.objects.filter(org_id=b.id).count() == 0
    _poser(b.id)
    assert list(Organisation.objects.values_list("code", flat=True)) == ["ORG-B"]


def test_le_meme_code_de_projet_existe_dans_deux_organisations_mais_pas_deux_fois_dans_une():
    a = _creer_organisation("ORG-A")
    b = _creer_organisation("ORG-B")
    _creer_projet(a, "PADD")
    _creer_projet(b, "PADD")
    with pytest.raises(IntegrityError), transaction.atomic():
        _creer_projet(a, "PADD")


def test_un_code_dorganisation_est_unique():
    _creer_organisation("UNIQUE")
    with pytest.raises(IntegrityError), transaction.atomic():
        _creer_organisation("UNIQUE")


def test_une_organisation_ne_peut_pas_en_creer_une_autre_sous_un_perimetre_etranger():
    a = _creer_organisation("ORG-A")
    _poser(a.id)
    with pytest.raises(ProgrammingError), transaction.atomic():
        Organisation.objects.create(
            id=uuid.uuid4(),
            code="INTRUSE",
            raison_sociale="Intruse",
            pays="DJ",
            monnaie_tenue="DJF",
        )


def test_la_monnaie_et_la_base_comptable_ne_changent_plus_apres_la_premiere_ecriture():
    """Garde-fou posé tout de suite, par déclencheur : base_currency et accounting_basis."""
    organisation = _creer_organisation("ORG-A")
    projet = _creer_projet(organisation, "P1")

    # Avant toute écriture, ces deux champs se corrigent.
    Projet.objects.filter(pk=projet.pk).update(base_currency="USD", accounting_basis="cash")

    LigneEcriture.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        fiscal_year=2026,
        period=1,
        accounting_date=datetime.date(2026, 1, 15),
        compte="6011",
        debit="10",
        credit="0",
        devise="USD",
        taux="1",
    )

    for champ, valeur in [("base_currency", "DJF"), ("accounting_basis", "accrual")]:
        with pytest.raises(IntegrityError, match="première écriture"), transaction.atomic():
            Projet.objects.filter(pk=projet.pk).update(**{champ: valeur})

    # Les autres champs restent modifiables.
    Projet.objects.filter(pk=projet.pk).update(status="closing")
    assert Projet.objects.get(pk=projet.pk).status == "closing"


def test_une_ecriture_dun_autre_projet_ne_verrouille_pas_ce_projet():
    organisation = _creer_organisation("ORG-A")
    p1 = _creer_projet(organisation, "P1")
    p2 = _creer_projet(organisation, "P2")
    LigneEcriture.objects.create(
        org_id=organisation.id,
        project_id=p1.id,
        fiscal_year=2026,
        period=1,
        accounting_date=datetime.date(2026, 1, 15),
        compte="6011",
        debit="10",
        credit="0",
        devise="DJF",
        taux="1",
    )
    Projet.objects.filter(pk=p2.pk).update(base_currency="EUR")
    assert Projet.objects.get(pk=p2.pk).base_currency == "EUR"


@pytest.mark.parametrize(
    "champs",
    [
        {"accounting_basis": "mixte"},
        {"status": "suspendu"},
        {"closing_date": datetime.date(2025, 12, 31)},  # avant le démarrage
        {"base_currency": "DJ"},  # code de devise sur trois lettres
    ],
)
def test_les_ensembles_fermes_et_les_dates_du_projet_sont_contraints_en_base(champs):
    organisation = _creer_organisation("ORG-A")
    with pytest.raises(IntegrityError), transaction.atomic():
        _creer_projet(organisation, "PX", **champs)


def test_les_libelles_sont_multilingues_en_jsonb():
    organisation = _creer_organisation("ORG-A")
    projet = _creer_projet(
        organisation, "P1", label={"fr": "Projet", "en": "Project", "ar": "مشروع"}
    )
    assert Projet.objects.get(pk=projet.pk).label["ar"] == "مشروع"
