# ruff: noqa: E501
# ruff: noqa: F811
"""Justifications et dérogations. Voir L6-T02a.

Contrôles du plan : dérogation par son propre demandeur refusée ; dérogation expirée ou hors
périmètre : le contrôle bloque de nouveau ; après dérogation, le résultat initial « bloquant » reste
lisible ; deux approbations concurrentes d'une même demande : une seule prend effet.
"""

import datetime
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from rest_framework.exceptions import PermissionDenied

from core.erreurs import CodeErreur, ErreurMetier
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau4_reporting.controles.derogations import (
    decider_derogation,
    demander_derogation,
    derogation_en_vigueur,
    dossier_de_conformite,
    justifier,
)
from niveau4_reporting.controles.models import (
    Derogation,
    EvaluationControle,
    Justification,
    StatutDerogation,
)
from niveau4_reporting.controles.services import (
    controles_en_attente,
    exiger_controles_tranches,
)
from tests.test_controles_bd import _actif, _evaluer, ctl  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_rattachement_bd import cadre_config  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = datetime.date
JOUR = D(2026, 6, 15)
DEPASSEMENT_CTX = {"montant": Decimal("10"), "depense_cumulee": Decimal("5000")}


def _utilisateur(organisation, projet, nom, operations):
    u = Utilisateur.objects.create_user(nom, password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id, code=nom.upper(), label={"fr": nom}, operations=operations
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=u.id, project_id=projet.id, role=role
    )
    return u


@pytest.fixture
def dero(ctl):
    organisation, projet, profils, document = ctl
    profils["samir"] = _utilisateur(organisation, projet, "samir", ["consulter", "saisir"])
    profils["lea"] = _utilisateur(organisation, projet, "lea", ["consulter", "valider"])
    profils["lecteur"] = _utilisateur(organisation, projet, "lecteur", ["consulter"])
    controle = _actif(ctl)
    objet = uuid.uuid4()
    evaluation = _evaluer(controle, DEPASSEMENT_CTX, ctl, objet_id=objet)
    assert evaluation.resultat == "bloquant"
    return organisation, projet, profils, controle, evaluation, objet


def _demander(dero, **champs):
    _, _, profils, _, evaluation, _ = dero
    donnees = {
        "utilisateur": profils["samir"],
        "evaluation": evaluation,
        "motif": "Marché urgent, financement complémentaire attendu",
        "justificatif": "NO-OBJECTION-2026-014",
        "valide_du": D(2026, 6, 1),
        "valide_jusquau": D(2026, 7, 1),
    } | champs
    return demander_derogation(**donnees)


# --- justification --------------------------------------------------------------------------


def test_une_justification_est_textuelle_nominative_et_ne_leve_aucun_blocage(dero):
    _, projet, profils, _, evaluation, objet = dero
    j = justifier(
        utilisateur=profils["samir"], evaluation=evaluation, texte="  Avance du bailleur  "
    )
    assert (j.texte, j.auteur_nom) == ("Avance du bailleur", "samir")
    assert len(controles_en_attente(projet.id, "depense", objet, JOUR)) == 1  # toujours bloqué
    with pytest.raises(ErreurMetier):
        justifier(utilisateur=profils["samir"], evaluation=evaluation, texte="  ")
    with pytest.raises(PermissionDenied):
        justifier(utilisateur=profils["lecteur"], evaluation=evaluation, texte="x")


def test_une_justification_ne_se_modifie_ni_ne_se_supprime(dero):
    _, _, profils, _, evaluation, _ = dero
    j = justifier(utilisateur=profils["samir"], evaluation=evaluation, texte="Raison")
    with pytest.raises(IntegrityError), transaction.atomic():
        Justification.objects.filter(pk=j.pk).update(texte="Autre")
    with pytest.raises(IntegrityError), transaction.atomic():
        Justification.objects.filter(pk=j.pk).delete()


# --- demande ---------------------------------------------------------------------------------


def test_une_derogation_ne_vise_qu_un_resultat_bloquant_et_le_dernier(dero, ctl):
    organisation, projet, profils, controle, evaluation, objet = dero
    reussi = _evaluer(controle, {"montant": Decimal("1"), "depense_cumulee": Decimal("1")}, ctl,
                      objet_id=uuid.uuid4())  # fmt: skip
    with pytest.raises(ErreurMetier) as e:
        _demander(dero, evaluation=reussi)
    assert e.value.code == CodeErreur.REGLE_INVALIDE
    # Une réévaluation (toujours bloquante) dépasse la première : on ne déroge pas à un état périmé.
    _evaluer(controle, DEPASSEMENT_CTX, ctl, objet_id=objet)
    with pytest.raises(ErreurMetier, match="dernier"):
        _demander(dero)


@pytest.mark.parametrize(
    "champs",
    [{"motif": " "}, {"justificatif": ""}, {"valide_jusquau": D(2026, 6, 1)}],
)
def test_une_demande_incomplete_ou_a_periode_vide_est_refusee(dero, champs):
    with pytest.raises(ErreurMetier):
        _demander(dero, **champs)
    assert Derogation.objects.count() == 0


def test_seul_un_saisisseur_demande(dero):
    with pytest.raises(PermissionDenied):
        _demander(dero, utilisateur=dero[2]["lecteur"])


# --- décision --------------------------------------------------------------------------------


def test_un_demandeur_ne_peut_pas_approuver_sa_propre_derogation(dero):
    _, _, profils, _, _, _ = dero
    # `vera` saisit ET valide : l'habilitation ne suffit pas, il faut une AUTRE personne.
    demandee = _demander(dero, utilisateur=_voir_saisie_et_validation(dero))
    with pytest.raises(ErreurMetier) as e:
        decider_derogation(
            utilisateur=Utilisateur.objects.get(pk=demandee.demandeur_id),
            derogation=demandee,
            approuver=True,
            motif="Moi, j'approuve",
        )
    assert e.value.code == CodeErreur.APPROBATION_REQUISE
    demandee.refresh_from_db()
    assert demandee.statut == StatutDerogation.DEMANDEE


def _voir_saisie_et_validation(dero):
    organisation, projet = dero[0], dero[1]
    return _utilisateur(organisation, projet, "double", ["consulter", "saisir", "valider"])


def test_la_base_refuse_un_approbateur_egal_au_demandeur(dero):
    demandee = _demander(dero)
    with pytest.raises(IntegrityError), transaction.atomic():
        Derogation.objects.filter(pk=demandee.pk).update(
            statut="approuvee",
            approbateur_id=demandee.demandeur_id,
            decidee_le=datetime.datetime.now(datetime.UTC),
            motif_decision="x",
        )


def test_seul_un_valideur_habilite_decide(dero):
    demandee = _demander(dero)
    with pytest.raises(PermissionDenied):
        decider_derogation(
            utilisateur=dero[2]["samir"], derogation=demandee, approuver=True, motif="ok"
        )
    with pytest.raises(ErreurMetier):  # motif obligatoire
        decider_derogation(
            utilisateur=dero[2]["lea"], derogation=demandee, approuver=True, motif=" "
        )


def test_une_derogation_decidee_ne_change_plus_et_ne_se_supprime_pas(dero):
    demandee = _demander(dero)
    decider_derogation(utilisateur=dero[2]["lea"], derogation=demandee, approuver=True, motif="ok")
    with pytest.raises(ErreurMetier) as e:
        decider_derogation(
            utilisateur=dero[2]["lea"], derogation=demandee, approuver=False, motif="finalement non"
        )
    assert e.value.code == CodeErreur.TRANSITION_INTERDITE
    with pytest.raises(IntegrityError), transaction.atomic():
        Derogation.objects.filter(pk=demandee.pk).update(motif="réécrit")
    with pytest.raises(IntegrityError), transaction.atomic():
        Derogation.objects.filter(pk=demandee.pk).delete()


# --- effet : périmètre, durée, historique -----------------------------------------------------


def test_une_derogation_approuvee_leve_le_blocage_sans_effacer_le_resultat_initial(dero):
    _, projet, profils, controle, evaluation, objet = dero
    demandee = _demander(dero)
    # Demandée seulement : rien n'est autorisé.
    with pytest.raises(ErreurMetier):
        exiger_controles_tranches(projet.id, "depense", objet, JOUR)
    decider_derogation(utilisateur=profils["lea"], derogation=demandee, approuver=True, motif="ok")
    exiger_controles_tranches(projet.id, "depense", objet, JOUR)  # passe
    # Le résultat initial est intact et lisible.
    evaluation.refresh_from_db()
    assert evaluation.resultat == "bloquant"
    assert EvaluationControle.objects.filter(objet_id=objet, resultat="bloquant").count() == 1
    fil = dossier_de_conformite(projet.id, "depense", objet)
    assert [(x["genre"], x["detail"]) for x in fil] == [
        ("evaluation", "bloquant"),
        ("derogation", "approuvee"),
    ]


def test_une_derogation_expiree_ou_pas_encore_valable_ne_couvre_pas(dero):
    _, projet, profils, controle, evaluation, objet = dero
    demandee = _demander(dero, valide_du=D(2026, 6, 10), valide_jusquau=D(2026, 6, 20))
    decider_derogation(utilisateur=profils["lea"], derogation=demandee, approuver=True, motif="ok")
    exiger_controles_tranches(projet.id, "depense", objet, D(2026, 6, 10))  # premier jour : couvert
    exiger_controles_tranches(projet.id, "depense", objet, D(2026, 6, 19))
    for jour in (D(2026, 6, 9), D(2026, 6, 20), D(2026, 8, 1)):  # fin EXCLUE
        with pytest.raises(ErreurMetier) as e:
            exiger_controles_tranches(projet.id, "depense", objet, jour)
        assert e.value.code == CodeErreur.CONTROLE_BLOQUANT


def test_une_derogation_ne_couvre_ni_un_autre_objet_ni_un_autre_controle(dero, ctl):
    _, projet, profils, controle, evaluation, objet = dero
    demandee = _demander(dero)
    decider_derogation(utilisateur=profils["lea"], derogation=demandee, approuver=True, motif="ok")
    autre_objet = uuid.uuid4()
    _evaluer(controle, DEPASSEMENT_CTX, ctl, objet_id=autre_objet)
    with pytest.raises(ErreurMetier):
        exiger_controles_tranches(projet.id, "depense", autre_objet, JOUR)
    assert derogation_en_vigueur(
        controle_id=uuid.uuid4(), project_id=projet.id, objet_type="depense", objet_id=objet, date=JOUR
    ) is None  # fmt: skip


def test_une_derogation_refusee_ne_couvre_rien(dero):
    _, projet, profils, _, _, objet = dero
    demandee = _demander(dero)
    decider_derogation(
        utilisateur=profils["lea"], derogation=demandee, approuver=False, motif="non"
    )
    with pytest.raises(ErreurMetier):
        exiger_controles_tranches(projet.id, "depense", objet, JOUR)


def test_la_base_refuse_une_derogation_a_un_perimetre_different_de_l_evaluation(dero):
    organisation, projet, profils, controle, evaluation, objet = dero
    with pytest.raises(IntegrityError), transaction.atomic():
        Derogation.objects.create(
            org_id=organisation.id, evaluation=evaluation, controle=controle,
            project_id=projet.id, objet_type="depense", objet_id=uuid.uuid4(),
            motif="m", justificatif="j", valide_du=D(2026, 6, 1), valide_jusquau=D(2026, 7, 1),
            demandeur_id=profils["samir"].id,
        )  # fmt: skip


# --- concurrence -----------------------------------------------------------------------------


def _decider_en_concurrence(org_id, user_id, derogation_id, barriere, approuver):
    try:
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [str(org_id)])
        barriere.wait()
        decider_derogation(
            utilisateur=Utilisateur.objects.get(pk=user_id),
            derogation=Derogation.objects.get(pk=derogation_id),
            approuver=approuver,
            motif="décision concurrente",
        )
        return "ok"
    except ErreurMetier as erreur:
        return erreur.code.value
    finally:
        connections.close_all()


def test_deux_approbations_concurrentes_une_seule_prend_effet(dero):
    organisation, projet, profils, _, _, _ = dero
    seconde = _utilisateur(organisation, projet, "ines", ["consulter", "valider"])
    demandee = _demander(dero)
    barriere = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futurs = [
            pool.submit(_decider_en_concurrence, organisation.id, u.id, demandee.pk, barriere, ok)
            for u, ok in ((profils["lea"], True), (seconde, False))
        ]
        issues = sorted(f.result() for f in futurs)
    assert issues == ["TRANSITION_INTERDITE", "ok"]
    demandee.refresh_from_db()
    assert demandee.statut in (StatutDerogation.APPROUVEE, StatutDerogation.REFUSEE)
    assert demandee.approbateur_id is not None
