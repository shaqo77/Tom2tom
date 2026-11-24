# ruff: noqa: F811, E501
"""Lot 3-B : lier une dépense à un contrat, et « une seule devise par demande » (manuel BAD, p. 25).

Sans contrat sur les lignes, rien n'est contrôlé (état antérieur). Avec des contrats, ils sont tous
du projet de la demande et dans une même devise ; la base refuse un contrat d'un autre projet.
"""

import datetime
import uuid

import pytest
from django.db import IntegrityError, transaction

from niveau1_socle.decaissements.models import LigneDemande
from niveau1_socle.decaissements.services import DemandeInvalide
from tests.test_contrats_bd import _contrat
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import _depense, _preparer, drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_plan_passation_bd import _ligne, pas  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
J = datetime.date


def _methode(pas, code, devise):
    """Une méthode de passation dans `devise` (idempotent : une seule par code)."""
    from niveau1_socle.marches.models import MethodePassation
    from niveau1_socle.marches.plan import definir_methode

    organisation, projet, profils, _ = pas
    if not MethodePassation.objects.filter(code=code).exists():
        definir_methode(
            utilisateur=profils["dora"],
            project_id=projet.id,
            code=code,
            label={"fr": code, "en": code},
            devise=devise,
            seuil_min="0",
            seuil_max=None,
            exige_non_objection=False,
            valid_from=J(2026, 1, 1),
        )


def _contrat_en(pas, reference, devise="USD"):
    """Un contrat conclu sur un marché attribué, dans la devise du marché."""
    from niveau1_socle.marches.plan import avancer_ligne

    methode = "AON" if devise == "USD" else f"AON-{devise}"
    _methode(pas, methode, devise)
    amina = pas[2]["amina"]
    ligne = _ligne(pas, f"M-{reference}", "120000", methode, devise=devise)
    ligne = avancer_ligne(utilisateur=amina, ligne=ligne, statut="lance", date_effet=J(2026, 3, 2))
    ligne = avancer_ligne(
        utilisateur=amina, ligne=ligne, statut="attribue", date_effet=J(2026, 5, 2)
    )
    return _contrat(pas, ligne=ligne, reference=reference)


def _deux_depenses(drf):
    organisation, projet, profils, accord, cat = drf
    return (
        _depense(organisation, projet, accord, cat["serv"], 10),
        _depense(organisation, projet, accord, cat["serv"], 11),
    )


def test_une_demande_sans_contrat_se_prepare_comme_avant(drf, pas):
    _, _, profils, accord, _ = drf
    a, b = _deux_depenses(drf)
    demande = _preparer(profils, accord, [a, b])
    assert all(ligne.contrat_id is None for ligne in demande.lignes.all())


def test_les_contrats_de_meme_devise_sont_enregistres_sur_les_lignes(drf, pas):
    _, _, profils, accord, _ = drf
    c1, c2 = _contrat_en(pas, "C-1"), _contrat_en(pas, "C-2")
    a, b = _deux_depenses(drf)
    demande = _preparer(profils, accord, [a, b], contrats={a: c1.pk, b: c2})
    par_ligne = {ligne.ligne_ecriture_id: ligne.contrat_id for ligne in demande.lignes.all()}
    assert par_ligne == {a: c1.pk, b: c2.pk}


def test_un_seul_contrat_sur_une_ligne_n_en_impose_pas_a_l_autre(drf, pas):
    _, _, profils, accord, _ = drf
    c1 = _contrat_en(pas, "C-1")
    a, b = _deux_depenses(drf)
    demande = _preparer(profils, accord, [a, b], contrats={a: c1})
    par_ligne = {ligne.ligne_ecriture_id: ligne.contrat_id for ligne in demande.lignes.all()}
    assert par_ligne == {a: c1.pk, b: None}


def test_des_contrats_de_devises_differentes_dans_une_demande_sont_refuses(drf, pas):
    _, _, profils, accord, _ = drf
    usd, eur = _contrat_en(pas, "C-1"), _contrat_en(pas, "C-2", devise="EUR")
    a, b = _deux_depenses(drf)
    with pytest.raises(DemandeInvalide) as exc:
        _preparer(profils, accord, [a, b], contrats={a: usd, b: eur})
    message = str(exc.value.args[0].rendre("fr"))
    assert "EUR" in message and "USD" in message
    assert not LigneDemande.objects.exists()  # rien n'a été enregistré


def test_la_meme_devise_dans_deux_demandes_separees_reste_permise(drf, pas):
    _, _, profils, accord, _ = drf
    usd, eur = _contrat_en(pas, "C-1"), _contrat_en(pas, "C-2", devise="EUR")
    a, b = _deux_depenses(drf)
    assert _preparer(profils, accord, [a], contrats={a: usd}).numero
    assert _preparer(profils, accord, [b], contrats={b: eur}).numero


def test_un_contrat_inconnu_ou_une_ligne_etrangere_est_refuse(drf, pas):
    _, _, profils, accord, _ = drf
    a, b = _deux_depenses(drf)
    c1 = _contrat_en(pas, "C-1")
    with pytest.raises(DemandeInvalide):
        _preparer(profils, accord, [a], contrats={a: uuid.uuid4()})
    with pytest.raises(DemandeInvalide):  # b n'est pas dans la demande
        _preparer(profils, accord, [a], contrats={b: c1})


def _ligne_a_la_main(demande, ligne_id, categorie, contrat):
    """Insère une ligne SANS passer par le service : seule la base protège alors."""
    return LigneDemande.objects.create(
        org_id=demande.org_id,
        demande=demande,
        ligne_ecriture_id=ligne_id,
        categorie=categorie,
        montant=11,
        montant_a_retirer=11,
        date_piece=J(2026, 2, 10),
        contrat=contrat,
    )


def _contrat_d_un_autre_projet(pas):
    """Un contrat du projet P2 : sa propre méthode, son plan, son marché attribué."""
    from niveau1_socle.habilitations.models import Habilitation, Role
    from niveau1_socle.marches.plan import avancer_ligne, creer_plan, definir_methode
    from tests.test_cycle_ecriture_bd import _creer_projet

    organisation, projet, profils, _ = pas
    p2 = _creer_projet(organisation, "P2")
    role = Role.objects.create(
        org_id=organisation.id, code="TOUT2", label={"fr": "tout"},
        operations=["consulter", "saisir", "parametrer"],
    )  # fmt: skip
    for nom in ("amina", "dora"):
        Habilitation.objects.create(
            org_id=organisation.id, user_id=profils[nom].id, project_id=p2.id, role=role
        )
    definir_methode(
        utilisateur=profils["dora"], project_id=p2.id, code="AON", label={"fr": "AON", "en": "AON"},
        devise="USD", seuil_min="0", seuil_max=None, exige_non_objection=False,
        valid_from=J(2026, 1, 1),
    )  # fmt: skip
    plan = creer_plan(
        utilisateur=profils["amina"], project_id=p2.id, code="PPM-P2", nom="Plan P2",
        date_debut=J(2026, 1, 1), date_fin=J(2026, 12, 31),
    )  # fmt: skip
    ligne = _ligne((organisation, p2, profils, plan), "M-P2", "120000", "AON")
    ligne = avancer_ligne(
        utilisateur=profils["amina"], ligne=ligne, statut="lance", date_effet=J(2026, 3, 2)
    )
    ligne = avancer_ligne(
        utilisateur=profils["amina"], ligne=ligne, statut="attribue", date_effet=J(2026, 5, 2)
    )
    return _contrat((organisation, p2, profils, plan), ligne=ligne, reference="C-P2")


def test_un_contrat_d_un_autre_projet_est_refuse_par_le_service(drf, pas):
    _, _, profils, accord, _ = drf
    a, _ = _deux_depenses(drf)
    etranger = _contrat_d_un_autre_projet(pas)
    with pytest.raises(DemandeInvalide):
        _preparer(profils, accord, [a], contrats={a: etranger})


def test_la_base_refuse_un_contrat_d_un_autre_projet(drf, pas):
    organisation, projet, profils, accord, cat = drf
    a, b = _deux_depenses(drf)
    demande = _preparer(profils, accord, [a])
    bon, mauvais = _contrat_en(pas, "C-1"), _contrat_d_un_autre_projet(pas)
    with pytest.raises(IntegrityError, match="contrat du projet"), transaction.atomic():
        _ligne_a_la_main(demande, b, cat["serv"], mauvais)
    # Témoin : le même geste avec un contrat du bon projet passe, donc le refus vient du contrat.
    assert _ligne_a_la_main(demande, b, cat["serv"], bon).contrat_id == bon.pk
