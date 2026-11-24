# ruff: noqa: F811
"""Lot 3-A : numérotation des demandes au format BAD (manuel des décaissements, p. 24-25).

Numérotation chronologique de 4 chiffres au plus, suffixe d'agence de 3 lettres, un numéro annulé
n'est JAMAIS réattribué, une suite distincte par accord (prêt et don). Le format `standard`
(`DRF-<accord>-<n>`) ne change pas.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import IntegrityError, connection, connections, transaction

from niveau1_socle.decaissements.services import DemandeInvalide, annuler_demande
from niveau1_socle.financements.models import CompteurDemande
from niveau1_socle.financements.services import (
    FinancementInvalide,
    creer_categorie,
    parametrer_numerotation_demandes,
)
from niveau1_socle.organisations.models import Utilisateur
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import _depense, _preparer, drf  # noqa: F401
from tests.test_financements_bd import _accord, _activer, cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def _bad(accord, profils, suffixe="ABC"):
    return parametrer_numerotation_demandes(
        accord, format="bad", suffixe_agence=suffixe, utilisateur=profils["dora"]
    )


def _nouvelle(drf, accord=None, montant=10, categorie=None):
    organisation, projet, profils, accord_drf, cat = drf
    accord = accord or accord_drf
    depense = _depense(organisation, projet, accord, categorie or cat["serv"], montant)
    return _preparer(profils, accord, [depense])


def test_le_format_standard_ne_change_pas(drf):
    assert _nouvelle(drf).numero == "DRF-DON-1-001"
    assert _nouvelle(drf).numero == "DRF-DON-1-002"


def test_le_format_bad_numerote_sur_quatre_chiffres_avec_le_suffixe_d_agence(drf):
    _, _, profils, accord, _ = drf
    _bad(accord, profils, "ADB")
    assert [_nouvelle(drf).numero for _ in range(3)] == ["0001ADB", "0002ADB", "0003ADB"]


def test_un_numero_annule_n_est_jamais_reattribue(drf):
    _, _, profils, accord, _ = drf
    _bad(accord, profils)
    premiere = _nouvelle(drf)
    annuler_demande(premiere, utilisateur=profils["amina"], motif="doublon")
    assert _nouvelle(drf).numero == "0002ABC"
    assert _nouvelle(drf).numero == "0003ABC"


def test_chaque_accord_a_sa_propre_suite(drf):
    organisation, projet, profils, accord, _ = drf
    second = _activer(
        _accord(projet, profils, accord.bailleur, "PRET-1", nature="pret", devise="DJF"), profils
    )
    cat2 = creer_categorie(
        utilisateur=profils["dora"],
        accord=second,
        code="SERV",
        label={"fr": "Services"},
        plafond="300",
    )
    _bad(accord, profils, "ABC")
    _bad(second, profils, "ABC")
    assert _nouvelle(drf).numero == "0001ABC"
    assert (
        _nouvelle(drf, second, categorie=cat2).numero == "0001ABC"
    )  # même suffixe, suite distincte
    assert _nouvelle(drf).numero == "0002ABC"
    assert _nouvelle(drf, second, categorie=cat2).numero == "0002ABC"


def test_la_dix_millieme_demande_est_refusee_nettement(drf):
    organisation, _, profils, accord, _ = drf
    _bad(accord, profils)
    CompteurDemande.objects.create(org_id=organisation.id, accord=accord, derniere_sequence=9999)
    with pytest.raises(DemandeInvalide) as exc:
        _nouvelle(drf)
    assert "9999" in str(exc.value.args[0].rendre("fr"))
    assert CompteurDemande.objects.get(accord=accord).derniere_sequence == 9999


@pytest.mark.parametrize("suffixe", ["", "AB", "ABCD", "abc", "A1C", "ÉÉÉ", "AB "])
def test_un_suffixe_d_agence_invalide_est_refuse(drf, suffixe):
    _, _, profils, accord, _ = drf
    with pytest.raises(FinancementInvalide):
        _bad(accord, profils, suffixe)


def test_le_format_standard_n_accepte_pas_de_suffixe(drf):
    _, _, profils, accord, _ = drf
    with pytest.raises(FinancementInvalide):
        parametrer_numerotation_demandes(
            accord, format="standard", suffixe_agence="ABC", utilisateur=profils["dora"]
        )


def test_le_format_ne_change_plus_des_qu_une_demande_existe(drf):
    _, _, profils, accord, _ = drf
    _nouvelle(drf)
    with pytest.raises(FinancementInvalide):
        _bad(accord, profils)


def test_seul_un_administrateur_change_le_format(drf):
    _, _, profils, accord, _ = drf
    from rest_framework.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        parametrer_numerotation_demandes(
            accord, format="bad", suffixe_agence="ABC", utilisateur=profils["amina"]
        )


def test_la_base_refuse_un_format_incoherent_et_un_compteur_qui_decroit(drf):
    organisation, _, profils, accord, _ = drf
    from niveau1_socle.financements.models import Accord

    with pytest.raises(IntegrityError), transaction.atomic():
        Accord.objects.filter(pk=accord.pk).update(format_numero_demande="bad", suffixe_agence="")
    compteur = CompteurDemande.objects.create(
        org_id=organisation.id, accord=accord, derniere_sequence=5
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CompteurDemande.objects.filter(pk=compteur.pk).update(derniere_sequence=4)
    with pytest.raises(IntegrityError), transaction.atomic():
        CompteurDemande.objects.filter(pk=compteur.pk).delete()


# --- concurrence -------------------------------------------------------------------------------


def _preparer_en_concurrence(org_id, user_id, accord_id, depense_id, barriere):
    try:
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [str(org_id)])
        from niveau1_socle.financements.models import Accord

        barriere.wait()
        demande = _preparer(
            {"amina": Utilisateur.objects.get(pk=user_id)},
            Accord.objects.get(pk=accord_id),
            [depense_id],
        )
        return demande.numero
    finally:
        connections.close_all()


def test_deux_preparations_simultanees_recoivent_deux_numeros_differents(drf):
    organisation, projet, profils, accord, cat = drf
    _bad(accord, profils)
    d1 = _depense(organisation, projet, accord, cat["serv"], 10)
    d2 = _depense(organisation, projet, accord, cat["serv"], 11)
    barriere = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futurs = [
            pool.submit(
                _preparer_en_concurrence,
                organisation.id,
                profils["amina"].id,
                accord.pk,
                depense,
                barriere,
            )
            for depense in (d1, d2)
        ]
        numeros = sorted(f.result() for f in futurs)
    assert numeros == ["0001ABC", "0002ABC"]
