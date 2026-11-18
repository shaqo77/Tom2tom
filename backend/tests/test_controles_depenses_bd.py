# ruff: noqa: F811, E501
"""Les contrôles actifs s'exécutent sur les dépenses d'une écriture, à sa validation. L11-A4.

Avant : la bibliothèque de contrôles n'était évaluée nulle part sur le grand livre ; un contrôle
« dépense sans catégorie » pouvait être actif sans rien arrêter.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model

from core.erreurs import CodeErreur, ErreurMetier
from niveau1_socle.comptabilite.models import Ecriture, LigneEcriture
from niveau1_socle.comptabilite.services import valider_ecriture
from niveau4_reporting.controles.models import Decision, EvaluationControle
from niveau4_reporting.controles.services import (
    activer_controle,
    installer_bibliotheque,
    trancher,
    valider_controle,
)
from tests.test_controles_bd import ctl  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import _depense, drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_rattachement_bd import cadre_config  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
DEBUT = datetime.date(2026, 1, 1)


@pytest.fixture
def pret(drf, ctl):
    """L'accord, ses catégories et les droits des contrôles (vera valide et paramètre)."""
    return drf


def _brouillon(pret, *, categorie="serv", montant=100):
    organisation, projet, profils, accord, cat = pret
    ligne_id = _depense(
        organisation, projet, accord, cat[categorie] if categorie else None, montant, statut="draft"
    )
    return LigneEcriture.objects.select_related("entry").get(pk=ligne_id)


def _actif(pret, code, *, debut=DEBUT):
    _, projet, profils, _, _ = pret
    installer_bibliotheque(
        utilisateur=profils["dora"], project_id=projet.id, valid_from=debut, codes=[code]
    )
    from niveau4_reporting.controles.models import Controle

    controle = Controle.objects.get(code=code)
    valider_controle(utilisateur=profils["vera"], controle=controle)
    return activer_controle(utilisateur=profils["vera"], controle=controle)


def _valider(pret, ligne):
    return valider_ecriture(Ecriture.objects.get(pk=ligne.entry_id), utilisateur=pret[2]["bruno"])


def _evaluations():
    return EvaluationControle.objects.filter(objet_type="ligne_ecriture")


def test_sans_controle_actif_la_validation_ne_change_pas(pret):
    ligne = _brouillon(pret, categorie=None)  # même sans catégorie : aucun contrôle n'est actif
    assert _valider(pret, ligne).status == "validated"
    assert _evaluations().count() == 0


def test_un_controle_bloquant_actif_refuse_la_validation_et_garde_son_evaluation(pret):
    _actif(pret, "COD-CATEGORIE")
    ligne = _brouillon(pret, categorie=None)
    with pytest.raises(ErreurMetier) as erreur:
        _valider(pret, ligne)
    assert (
        erreur.value.code is CodeErreur.CONTROLE_BLOQUANT
        and "COD-CATEGORIE" in erreur.value.message
    )
    assert Ecriture.objects.get(pk=ligne.entry_id).status == "draft"
    # Le refus n'efface pas l'évaluation : le journal est en ajout seul.
    assert [(e.controle.code, e.resultat) for e in _evaluations()] == [
        ("COD-CATEGORIE", "bloquant")
    ]


def test_une_fois_la_ligne_corrigee_la_validation_passe(pret):
    _, _, _, accord, cat = pret
    _actif(pret, "COD-CATEGORIE")
    ligne = _brouillon(pret, categorie=None)
    with pytest.raises(ErreurMetier):
        _valider(pret, ligne)
    LigneEcriture.objects.filter(pk=ligne.pk).update(category_id=cat["serv"].pk)
    assert _valider(pret, ligne).status == "validated"
    assert [e.resultat for e in _evaluations().order_by("created_at")] == ["bloquant", "reussi"]


def test_un_controle_a_verifier_attend_une_decision_puis_laisse_passer_sans_etre_reevalue(pret):
    organisation, projet, profils, _, _ = pret
    from niveau4_reporting.controles.models import Controle
    from niveau4_reporting.controles.services import creer_controle

    creer_controle(
        utilisateur=profils["dora"], project_id=projet.id, code="VERIF-MANUELLE",
        label={"fr": "Contrôle humain", "en": "Human check"}, type_regle="codification",
        severity="bloquant", valid_from=DEBUT, manuel=True,
    )  # fmt: skip
    controle = Controle.objects.get(code="VERIF-MANUELLE")
    valider_controle(utilisateur=profils["vera"], controle=controle)
    activer_controle(utilisateur=profils["vera"], controle=controle)
    ligne = _brouillon(pret, categorie="serv")
    with pytest.raises(ErreurMetier) as erreur:
        _valider(pret, ligne)
    assert erreur.value.code is CodeErreur.CONTROLE_BLOQUANT
    evaluation = _evaluations().get()
    assert evaluation.resultat == "a_verifier"
    trancher(
        utilisateur=profils["vera"], evaluation=evaluation, decision=Decision.CONFORME, motif="Vu"
    )
    assert _valider(pret, ligne).status == "validated"
    assert _evaluations().count() == 1  # pas réévalué : la décision humaine reste celle qui compte


def test_une_decision_non_conforme_continue_de_bloquer(pret):
    _, projet, profils, _, _ = pret
    from niveau4_reporting.controles.models import Controle
    from niveau4_reporting.controles.services import creer_controle

    creer_controle(
        utilisateur=profils["dora"], project_id=projet.id, code="VERIF-MANUELLE",
        label={"fr": "Contrôle humain", "en": "Human check"}, type_regle="codification",
        severity="bloquant", valid_from=DEBUT, manuel=True,
    )  # fmt: skip
    controle = Controle.objects.get(code="VERIF-MANUELLE")
    valider_controle(utilisateur=profils["vera"], controle=controle)
    activer_controle(utilisateur=profils["vera"], controle=controle)
    ligne = _brouillon(pret)
    with pytest.raises(ErreurMetier):
        _valider(pret, ligne)
    trancher(
        utilisateur=profils["vera"], evaluation=_evaluations().get(),
        decision=Decision.NON_CONFORME, motif="Non",
    )  # fmt: skip
    with pytest.raises(ErreurMetier):
        _valider(pret, ligne)


def test_un_avertissement_laisse_passer_et_se_lit_sur_l_ecriture(pret):
    _, projet, profils, _, _ = pret
    from niveau4_reporting.controles.models import Controle
    from niveau4_reporting.controles.services import creer_controle

    creer_controle(
        utilisateur=profils["dora"], project_id=projet.id, code="AVERT-CAT",
        label={"fr": "Catégorie conseillée", "en": "Category advised"}, type_regle="codification",
        severity="avertissement", valid_from=DEBUT,
        expression={"type_regle": "codification", "conditions": [{"champ": "categorie", "op": "est_renseigne"}]},
    )  # fmt: skip
    controle = Controle.objects.get(code="AVERT-CAT")
    valider_controle(utilisateur=profils["vera"], controle=controle)
    activer_controle(utilisateur=profils["vera"], controle=controle)
    ligne = _brouillon(pret, categorie=None)
    resultat = _valider(pret, ligne)
    assert resultat.status == "validated"
    assert len(resultat.avertissements_controles) == 1
    assert resultat.avertissements_controles[0].startswith("AVERT-CAT")


def test_un_controle_installe_mais_non_active_n_est_pas_evalue(pret):
    _, projet, profils, _, _ = pret
    installer_bibliotheque(
        utilisateur=profils["dora"], project_id=projet.id, valid_from=DEBUT, codes=["COD-CATEGORIE"]
    )  # brouillon : règle 9, jamais activé d'office
    ligne = _brouillon(pret, categorie=None)
    assert _valider(pret, ligne).status == "validated"
    assert _evaluations().count() == 0


def test_seules_les_charges_sont_controlees_pas_la_contrepartie(pret):
    _actif(pret, "COD-CATEGORIE")
    ligne = _brouillon(pret, categorie="serv")
    _valider(pret, ligne)
    # Deux lignes dans l'écriture (charge et banque), une seule évaluation : la charge.
    assert Ecriture.objects.get(pk=ligne.entry_id).lignes.count() == 2
    assert [e.objet_id for e in _evaluations()] == [ligne.pk]


def test_une_ecriture_deja_validee_ne_declenche_aucune_evaluation(pret):
    _actif(pret, "COD-CATEGORIE")
    ligne = _brouillon(pret, categorie="serv")
    _valider(pret, ligne)
    avant = _evaluations().count()
    with pytest.raises(Exception, match="validated|validée"):
        _valider(pret, ligne)  # plus un brouillon : la transition est refusée
    assert _evaluations().count() == avant


def test_sans_droit_de_valider_aucune_evaluation_n_est_ecrite(pret):
    organisation, _, profils, _, _ = pret
    _actif(pret, "COD-CATEGORIE")
    ligne = _brouillon(pret, categorie=None)
    with pytest.raises(Exception, match="habilit"):
        valider_ecriture(Ecriture.objects.get(pk=ligne.entry_id), utilisateur=profils["dora"])
    assert _evaluations().count() == 0


def test_l_auteur_de_la_piece_ne_declenche_aucune_evaluation_en_la_validant(pret):
    _, _, profils, _, _ = pret
    _actif(pret, "COD-CATEGORIE")
    ligne = _brouillon(pret, categorie=None)
    Ecriture.objects.filter(pk=ligne.entry_id).update(created_by=profils["bruno"].id)
    with pytest.raises(Exception, match="vous-même"):
        _valider(pret, ligne)
    assert _evaluations().count() == 0


def test_un_controle_pas_encore_en_vigueur_a_la_date_de_la_depense_n_est_pas_applique(pret):
    _actif(pret, "COD-CATEGORIE", debut=datetime.date(2026, 6, 1))
    ligne = _brouillon(pret, categorie=None)  # dépense de février
    assert _valider(pret, ligne).status == "validated"
    assert _evaluations().count() == 0


def test_un_controle_de_pieces_est_applique_aussi(pret):
    """Le doublon de facture (même référence, même tiers) est un contrôle de PIÈCES."""
    organisation, _, _, _, _ = pret
    from niveau1_socle.referentiels.models import Tiers

    _actif(pret, "PIE-DOUBLON")
    tiers = Tiers.objects.create(org_id=organisation.id, code="F-A", nature="fournisseur", nom="A")

    def avec_facture(jour):
        ligne = _brouillon(pret)
        Ecriture.objects.filter(pk=ligne.entry_id).update(document_ref="FAC-1")
        LigneEcriture.objects.filter(pk=ligne.pk).update(partner=tiers)
        return ligne

    premiere, _ = avec_facture(1), avec_facture(2)
    with pytest.raises(ErreurMetier) as erreur:
        _valider(pret, premiere)  # vue des deux côtés : le doublon bloque la première aussi
    assert (
        erreur.value.code is CodeErreur.CONTROLE_BLOQUANT and "PIE-DOUBLON" in erreur.value.message
    )
    assert {e.controle.code for e in _evaluations()} == {"PIE-DOUBLON"}
