# ruff: noqa: F811, E501
"""L'éligibilité s'applique à la validation d'une écriture : la dépense doit tomber dans la fenêtre
d'éligibilité de son accord, de son profil et de sa catégorie. L11-A5.

Avant : l'éligibilité n'était vérifiée que dans le flux de demande de retrait ; une dépense hors
période se comptabilisait sans un mot, et n'était repérée qu'au moment de la justifier au bailleur.
"""

import datetime
from types import SimpleNamespace

import pytest

from core.erreurs import CodeErreur, ErreurMetier
from niveau1_socle.comptabilite.models import Ecriture, LigneEcriture
from niveau1_socle.comptabilite.services import valider_ecriture
from niveau3_config.services.decaissement import fenetre_d_eligibilite
from niveau4_reporting.controles.models import Controle, EvaluationControle
from niveau4_reporting.controles.services import (
    activer_controle,
    installer_bibliotheque,
    valider_controle,
)
from tests.outils_profil import creer_profil
from tests.test_controles_bd import ctl  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import _depense, drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_rattachement_bd import cadre_config  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
J = datetime.date
DEBUT = J(2026, 1, 1)


# --- la fenêtre : une seule règle, bornes incluses, aucune date inventée -----------------------


def _p(**champs):
    return SimpleNamespace(**({"eligibility_date": None} | champs))


def _r(**champs):
    return SimpleNamespace(**({"eligibility_from": None, "eligibility_to": None} | champs))


def _a(**champs):
    return SimpleNamespace(**({"date_fin_eligibilite": None} | champs))


def test_sans_aucune_borne_connue_la_fenetre_est_ouverte():
    assert fenetre_d_eligibilite(None, None, _a()) == (None, None)
    assert fenetre_d_eligibilite(_p(), _r(), _a()) == (None, None)


def test_le_debut_est_le_plus_tardif_et_la_fin_la_plus_precoce():
    profil = _p(eligibility_date=J(2026, 1, 15))
    regle = _r(eligibility_from=J(2026, 2, 1), eligibility_to=J(2026, 9, 30))
    accord = _a(date_fin_eligibilite=J(2026, 6, 30))
    assert fenetre_d_eligibilite(profil, regle, accord) == (J(2026, 2, 1), J(2026, 6, 30))
    # Une catégorie qui finit avant l'accord resserre la fin ; un profil plus tardif, le début.
    assert fenetre_d_eligibilite(
        _p(eligibility_date=J(2026, 3, 1)),
        _r(eligibility_from=J(2026, 2, 1), eligibility_to=J(2026, 4, 1)),
        accord,
    ) == (J(2026, 3, 1), J(2026, 4, 1))


def test_un_profil_ou_une_regle_absents_n_ajoutent_aucune_borne():
    assert fenetre_d_eligibilite(None, None, _a(date_fin_eligibilite=J(2026, 6, 30))) == (
        None,
        J(2026, 6, 30),
    )


# --- la validation d'une écriture ----------------------------------------------------------------


@pytest.fixture
def pret(drf, ctl):
    return drf


def _controle_actif(pret):
    _, projet, profils, _, _ = pret
    installer_bibliotheque(
        utilisateur=profils["dora"],
        project_id=projet.id,
        valid_from=DEBUT,
        codes=["ELIG-PERIODE-ACCORD"],
    )
    c = Controle.objects.get(code="ELIG-PERIODE-ACCORD")
    valider_controle(utilisateur=profils["vera"], controle=c)
    return activer_controle(utilisateur=profils["vera"], controle=c)


def _depense_du(pret, jour, mois, *, categorie="serv", avec_accord=True):
    organisation, projet, _, accord, cat = pret
    ligne_id = _depense(
        organisation, projet, accord, cat[categorie], 100,
        jour=jour, mois=mois, statut="draft", agreement=avec_accord,
    )  # fmt: skip
    return LigneEcriture.objects.select_related("entry").get(pk=ligne_id)


def _valider(pret, ligne):
    return valider_ecriture(Ecriture.objects.get(pk=ligne.entry_id), utilisateur=pret[2]["bruno"])


def _profil(pret, **champs):
    organisation, projet, _, accord, cat = pret
    return creer_profil(
        organisation, projet, accord,
        regles=[(cat["serv"], "0.8", {"eligibility_from": J(2026, 2, 1), "eligibility_to": J(2026, 3, 31)})],
        eligibility_date=champs.pop("eligibility_date", J(2026, 1, 15)),
        **champs,
    )  # fmt: skip


def _evaluations():
    return EvaluationControle.objects.filter(
        objet_type="ligne_ecriture", controle__code="ELIG-PERIODE-ACCORD"
    )


def test_une_depense_dans_la_fenetre_passe(pret):
    _profil(pret)
    _controle_actif(pret)
    assert _valider(pret, _depense_du(pret, 10, 3)).status == "validated"
    assert [e.resultat for e in _evaluations()] == ["reussi"]


def test_une_depense_avant_le_debut_d_eligibilite_est_refusee(pret):
    _profil(pret)
    _controle_actif(pret)
    ligne = _depense_du(
        pret, 20, 1
    )  # 20 janvier : après le profil (15/01), avant la catégorie (01/02)
    with pytest.raises(ErreurMetier) as erreur:
        _valider(pret, ligne)
    assert (
        erreur.value.code is CodeErreur.CONTROLE_BLOQUANT
        and "ELIG-PERIODE-ACCORD" in erreur.value.message
    )
    assert Ecriture.objects.get(pk=ligne.entry_id).status == "draft"


def test_une_depense_apres_la_fin_de_la_categorie_est_refusee(pret):
    _profil(pret)
    _controle_actif(pret)
    with pytest.raises(ErreurMetier):
        _valider(pret, _depense_du(pret, 1, 4))  # 1er avril : après le 31 mars


def test_les_bornes_sont_incluses(pret):
    _profil(pret)
    _controle_actif(pret)
    assert _valider(pret, _depense_du(pret, 1, 2)).status == "validated"  # premier jour
    assert _valider(pret, _depense_du(pret, 31, 3)).status == "validated"  # dernier jour


def test_la_fin_d_eligibilite_de_l_accord_s_applique(pret):
    organisation, projet, profils, _, _ = pret
    from niveau1_socle.financements.models import Bailleur
    from tests.test_financements_bd import _accord, _activer

    accord2 = _activer(
        _accord(
            projet, profils, Bailleur.objects.first(), "DON-2", devise="DJF",
            montant_initial="1000", date_fin_eligibilite=J(2026, 2, 28),
        ),
        profils,
    )  # fmt: skip
    _controle_actif(pret)

    def depense(jour, mois):
        ligne_id = _depense(
            organisation, projet, accord2, None, 100, jour=jour, mois=mois, statut="draft"
        )
        return LigneEcriture.objects.select_related("entry").get(pk=ligne_id)

    assert _valider(pret, depense(28, 2)).status == "validated"  # dernier jour d'éligibilité
    with pytest.raises(ErreurMetier):
        _valider(pret, depense(1, 3))  # le lendemain : hors période


def test_une_sous_categorie_herite_de_la_fenetre_de_sa_categorie(pret):
    organisation, projet, _, accord, cat = pret
    creer_profil(
        organisation, projet, accord,
        regles=[(cat["biens"], "0.8", {"eligibility_from": J(2026, 2, 1), "eligibility_to": J(2026, 3, 31)})],
    )  # fmt: skip
    _controle_actif(pret)
    with pytest.raises(ErreurMetier):
        _valider(pret, _depense_du(pret, 10, 4, categorie="biens_a"))  # BIENS-A relève de BIENS


def test_sans_accord_le_controle_n_est_pas_applicable(pret):
    _profil(pret)
    _controle_actif(pret)
    ligne = _depense_du(pret, 1, 4, avec_accord=False)  # hors fenêtre, mais aucun accord
    assert _valider(pret, ligne).status == "validated"
    assert [e.resultat for e in _evaluations()] == ["non_applicable"]


def test_sans_aucune_borne_connue_rien_ne_restreint(pret):
    organisation, projet, _, accord, cat = pret
    creer_profil(organisation, projet, accord, regles=[(cat["serv"], "0.8")])
    _controle_actif(pret)
    assert _valider(pret, _depense_du(pret, 1, 12)).status == "validated"


def test_sans_controle_actif_l_eligibilite_n_est_pas_verifiee(pret):
    _profil(pret)  # le contrôle n'est pas activé : règle 9, jamais d'office
    assert _valider(pret, _depense_du(pret, 1, 4)).status == "validated"
    assert _evaluations().count() == 0
