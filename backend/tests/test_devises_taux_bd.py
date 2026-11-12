"""Devises et taux de change. Voir L2-T01.

Règle : un taux n'est JAMAIS écrasé. Un nouveau taux est une nouvelle ligne, à
une nouvelle date. Recalculer un historique avec un taux courant est une faute
comptable.
"""

import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction

from niveau1_socle.referentiels.models import Devise, Taux
from niveau1_socle.referentiels.taux import TauxIntrouvable, taux_applicable
from tests.test_organisations_bd import _creer_organisation

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.usefixtures("devises_referentiel"),
]
JOUR = datetime.date(2026, 3, 31)


def _taux(organisation, devise="USD", jour=JOUR, valeur="177.721", type_taux="officiel"):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])
    return Taux.objects.create(
        org_id=organisation.id,
        devise_id=devise,
        date=jour,
        taux=Decimal(valeur),
        type_taux=type_taux,
    )


def test_le_referentiel_livre_les_devises_avec_leurs_decimales_iso():
    assert Devise.objects.get(pk="DJF").decimales == 0
    assert Devise.objects.get(pk="USD").decimales == 2
    assert Devise.objects.get(pk="EUR").label["fr"] == "Euro"
    assert Devise.objects.filter(pk__in=["XOF", "XAF", "ETB", "GBP"]).count() == 4


def test_l_application_ne_modifie_pas_le_referentiel_des_devises():
    """Référentiel général : il se modifie par migration, jamais par l'application."""
    with pytest.raises(IntegrityError, match="lecture seule"), transaction.atomic():
        Devise.objects.filter(pk="USD").update(decimales=5)
    with pytest.raises(IntegrityError, match="lecture seule"), transaction.atomic():
        Devise.objects.create(code="XXX", label={"fr": "Fausse"}, decimales=2)
    with pytest.raises(IntegrityError, match="lecture seule"), transaction.atomic():
        Devise.objects.filter(pk="EUR").delete()
    assert Devise.objects.get(pk="USD").decimales == 2


def test_deux_taux_du_meme_jour_de_types_differents_coexistent():
    """Contrôle de L2-T01."""
    organisation = _creer_organisation("ORG-A")
    for type_taux, valeur in [
        ("officiel", "177.721"),
        ("bailleur", "178.500"),
        ("cloture", "177.900"),
        ("budget", "175.000"),
    ]:
        _taux(organisation, valeur=valeur, type_taux=type_taux)

    jour = Taux.objects.filter(devise_id="USD", date=JOUR)
    assert jour.count() == 4
    assert {t.type_taux: t.taux for t in jour}["bailleur"] == Decimal("178.5000000000")


def test_un_second_taux_du_meme_type_le_meme_jour_est_refuse():
    organisation = _creer_organisation("ORG-A")
    _taux(organisation)
    with pytest.raises(IntegrityError), transaction.atomic():
        _taux(organisation, valeur="180")


def test_un_taux_nest_jamais_ecrase_ni_supprime_meme_en_sql_direct():
    organisation = _creer_organisation("ORG-A")
    taux = _taux(organisation)

    with pytest.raises(IntegrityError, match="jamais écrasé"), transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("UPDATE referentiels_taux SET taux = 1 WHERE id = %s", [taux.id])
    with pytest.raises(IntegrityError, match="jamais écrasé"), transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("DELETE FROM referentiels_taux WHERE id = %s", [taux.id])
    assert Taux.objects.get(pk=taux.pk).taux == Decimal("177.721")


@pytest.mark.parametrize(
    "champs",
    [
        {"valeur": "0"},
        {"valeur": "-1"},
        {"type_taux": "marche_noir"},
        {"devise": "ZZZ"},  # devise absente du référentiel
    ],
)
def test_un_taux_invalide_est_refuse_par_la_base(champs):
    organisation = _creer_organisation("ORG-A")
    with pytest.raises(IntegrityError), transaction.atomic():
        _taux(organisation, **champs)


def test_le_taux_applicable_est_celui_en_vigueur_a_la_date_jamais_un_taux_futur():
    organisation = _creer_organisation("ORG-A")
    _taux(organisation, jour=datetime.date(2026, 1, 1), valeur="170")
    _taux(organisation, jour=datetime.date(2026, 3, 1), valeur="175")
    _taux(organisation, jour=datetime.date(2026, 6, 1), valeur="180")

    assert taux_applicable("USD", datetime.date(2026, 2, 28), "officiel") == Decimal("170")
    assert taux_applicable("USD", datetime.date(2026, 3, 1), "officiel") == Decimal("175")
    assert taux_applicable("USD", datetime.date(2026, 5, 31), "officiel") == Decimal("175")
    with pytest.raises(TauxIntrouvable, match="2025-12-31"):
        taux_applicable("USD", datetime.date(2025, 12, 31), "officiel")
    with pytest.raises(TauxIntrouvable):
        taux_applicable("USD", datetime.date(2026, 3, 1), "budget")  # autre type : aucun


def test_les_taux_sont_isoles_par_organisation():
    a = _creer_organisation("ORG-A")
    _taux(a)
    b = _creer_organisation("ORG-B")  # pose le périmètre de B
    assert Taux.objects.count() == 0
    with pytest.raises(TauxIntrouvable):
        taux_applicable("USD", JOUR, "officiel")
    assert b.code == "ORG-B"
