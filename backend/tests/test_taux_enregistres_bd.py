# ruff: noqa: F811, E501
"""L'enregistrement des taux de change, et le contrôle des devises autorisées sur le budget. L11-A6.

Avant : AUCUN service n'enregistrait un taux (ils n'entraient que par des tests ou du SQL direct),
alors que la consolidation du tableau de bord en dépend ; et une ligne de budget pouvait être saisie
dans une devise que les réglages n'autorisent pas.
"""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from core.erreurs import ErreurMetier
from niveau1_socle.budget.services import ajouter_ligne, creer_version
from niveau1_socle.referentiels.models import Taux
from niveau1_socle.referentiels.parametres_devises import parametrer_devises
from niveau1_socle.referentiels.taux import enregistrer_taux, taux_applicable
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_devises_parametrees_application_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = Decimal
J = datetime.date


def _enreg(profils, **champs):
    donnees = {
        "utilisateur": profils["dora"],
        "devise": "USD",
        "date": J(2026, 3, 1),
        "taux": "177.5",
        "type_taux": "officiel",
    } | champs
    return enregistrer_taux(**donnees)


def test_un_taux_enregistre_se_relit_par_taux_applicable(cadre):
    _, _, _, profils = cadre
    ligne = _enreg(profils)
    assert (ligne.devise_id, ligne.date, ligne.taux, ligne.type_taux) == (
        "USD",
        J(2026, 3, 1),
        D("177.5"),
        "officiel",
    )
    assert taux_applicable("USD", J(2026, 3, 15), "officiel") == D("177.5")


def test_un_nouveau_taux_a_une_autre_date_ne_remplace_pas_l_ancien(cadre):
    _, _, _, profils = cadre
    _enreg(profils, date=J(2026, 3, 1), taux="177")
    _enreg(profils, date=J(2026, 4, 1), taux="178")
    assert Taux.objects.filter(devise_id="USD").count() == 2
    assert taux_applicable("USD", J(2026, 3, 31), "officiel") == D("177")  # l'ancien reste lisible
    assert taux_applicable("USD", J(2026, 4, 1), "officiel") == D("178")


def test_un_taux_du_meme_jour_et_du_meme_type_n_est_pas_ecrase(cadre):
    _, _, _, profils = cadre
    _enreg(profils, taux="177")
    with pytest.raises(ErreurMetier, match="déjà|existe"):
        _enreg(profils, taux="180")
    assert taux_applicable("USD", J(2026, 3, 1), "officiel") == D("177")  # jamais écrasé
    _enreg(profils, type_taux="budget", taux="180")  # un autre type, le même jour : permis


@pytest.mark.parametrize("valeur", ["0", "-1", "abc", "", "1e3", "NaN", "Infinity"])
def test_un_taux_non_positif_ou_illisible_est_refuse(cadre, valeur):
    _, _, _, profils = cadre
    with pytest.raises(ErreurMetier):
        _enreg(profils, taux=valeur)
    assert Taux.objects.count() == 0


def test_un_float_n_est_jamais_accepte_comme_taux(cadre):
    _, _, _, profils = cadre
    with pytest.raises(ErreurMetier, match="float|chaîne|nombre"):
        _enreg(profils, taux=177.5)


def test_un_type_de_taux_inconnu_ou_une_devise_inconnue_est_refuse(cadre):
    _, _, _, profils = cadre
    # Le refus doit DIRE pourquoi (la base refuserait aussi, mais avec un message trompeur).
    with pytest.raises(ErreurMetier, match="Type de taux inconnu.*magique"):
        _enreg(profils, type_taux="magique")
    with pytest.raises(ErreurMetier, match="Devise inconnue.*XXX"):
        _enreg(profils, devise="XXX")


def test_le_taux_de_la_monnaie_de_tenue_n_existe_pas(cadre):
    organisation, _, _, profils = cadre
    with pytest.raises(ErreurMetier, match="tenue"):
        _enreg(profils, devise=organisation.monnaie_tenue)


def test_il_faut_l_habilitation_parametrer(cadre):
    organisation, projet, _, profils = cadre
    sans_droit = Utilisateur.objects.create_user("zoe", password="x", org_id=organisation.id)
    with pytest.raises(PermissionDenied):
        enregistrer_taux(
            utilisateur=sans_droit,
            devise="USD",
            date=J(2026, 3, 1),
            taux="177",
            type_taux="officiel",
        )
    assert Taux.objects.count() == 0


def test_une_devise_non_autorisee_par_l_organisation_n_a_pas_de_taux(cadre):
    organisation, _, _, profils = cadre
    parametrer_devises(
        utilisateur=profils["dora"], devises_autorisees=["DJF", "USD"], date_effet=J(2026, 1, 1)
    )
    with pytest.raises(ErreurMetier, match="EUR"):
        _enreg(profils, devise="EUR")
    assert _enreg(profils, devise="USD").devise_id == "USD"


def test_l_enregistrement_est_journalise_avec_sa_source(cadre):
    organisation, _, _, profils = cadre
    ligne = _enreg(profils, source="Banque centrale, circulaire 12")
    assert ligne.source == "Banque centrale, circulaire 12"
    from core.models import AuditLog

    entree = AuditLog.objects.filter(action="rate_recorded", object_id=ligne.id).get()
    assert entree.after["taux"] == "177.5" and entree.after["devise"] == "USD"
    assert verifier_chaine(organisation.id) is None  # la chaîne d'audit reste intègre


# --- le budget respecte les devises autorisées ------------------------------------------------


def test_une_ligne_de_budget_dans_une_devise_non_autorisee_est_refusee(cadre):
    _, p1, p2, profils = cadre
    dora = profils["dora"]
    parametrer_devises(
        utilisateur=dora, devises_autorisees=["DJF", "USD"], date_effet=J(2026, 1, 1)
    )
    version = creer_version(utilisateur=dora, project_id=p2.id, type="initial")
    with pytest.raises(ErreurMetier, match="EUR.*pas autorisée"):
        ajouter_ligne(version, utilisateur=dora, annee=2026, montant="100", devise="EUR")
    ligne = ajouter_ligne(
        version, utilisateur=dora, annee=2026, montant="100", devise="USD", taux=177
    )
    assert ligne.devise_id == "USD"


def test_la_date_de_la_ligne_decide_de_la_liste_applicable(cadre):
    _, _, p2, profils = cadre
    dora = profils["dora"]
    parametrer_devises(
        utilisateur=dora, devises_autorisees=["DJF", "USD"], date_effet=J(2026, 1, 1)
    )
    parametrer_devises(
        utilisateur=dora, devises_autorisees=["DJF", "USD", "EUR"], date_effet=J(2026, 7, 1)
    )
    version = creer_version(utilisateur=dora, project_id=p2.id, type="initial")
    with pytest.raises(ErreurMetier, match="EUR"):
        ajouter_ligne(version, utilisateur=dora, annee=2026, periode=3, montant="1", devise="EUR")
    assert (
        ajouter_ligne(
            version, utilisateur=dora, annee=2026, periode=8, montant="1", devise="EUR", taux=200
        ).devise_id
        == "EUR"
    )


def test_sans_liste_parametree_le_budget_n_est_pas_restreint(cadre):
    _, _, p2, profils = cadre
    version = creer_version(utilisateur=profils["dora"], project_id=p2.id, type="initial")
    assert (
        ajouter_ligne(
            version, utilisateur=profils["dora"], annee=2026, montant="1", devise="EUR", taux=200
        ).devise_id
        == "EUR"
    )


def test_une_periode_invalide_garde_son_propre_message_meme_avec_une_liste_de_devises(cadre):
    """Le contrôle de devise ne doit pas masquer la validation de la ligne par une erreur de date."""
    _, _, p2, profils = cadre
    dora = profils["dora"]
    parametrer_devises(
        utilisateur=dora, devises_autorisees=["DJF", "USD"], date_effet=J(2026, 1, 1)
    )
    version = creer_version(utilisateur=dora, project_id=p2.id, type="initial")
    from niveau1_socle.budget.services import BudgetInvalide

    with pytest.raises(BudgetInvalide, match="période"):
        ajouter_ligne(version, utilisateur=dora, annee=2026, periode=13, montant="1", devise="USD")
