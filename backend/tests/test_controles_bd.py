# ruff: noqa: F811, E501
"""Le moteur de contrôles : enregistrement, cycle de vie, évaluation et journal. Voir L6-T01b.

Contrôles du plan : condition hors schéma ou opérateur inconnu refusés à l'enregistrement ; contrôle
« à vérifier » non tranché : on n'avance pas ; chaque évaluation laisse une ligne de journal avec la
version du profil.
"""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from core.erreurs import CodeErreur, ErreurMetier
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau3_config.services.rattachement import detecter_configuration_orpheline, rattacher
from niveau4_reporting.controles.models import (
    Controle,
    DecisionControle,
    EvaluationControle,
)
from niveau4_reporting.controles.services import (
    activer_controle,
    controles_en_attente,
    creer_controle,
    evaluer_controle,
    evaluer_tous,
    exiger_controles_tranches,
    rejeter_controle,
    trancher,
    valider_controle,
)
from tests.outils_profil import creer_profil
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_financements_bd import _accord, _activer, cadre  # noqa: F401
from tests.test_rattachement_bd import _exigence, cadre_config  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = datetime.date
M = Decimal
DEBUT = D(2026, 1, 1)
JOUR = D(2026, 6, 15)
DEPASSEMENT = {
    "type_regle": "budget",
    "conditions": [{"champ": "depense_cumulee", "op": "lte", "valeur": "1000"}],
}


@pytest.fixture
def ctl(cadre_config):
    """vera valide et paramètre (le moteur lui est ouvert) ; dora paramètre seulement."""
    organisation, projet, profils, document = cadre_config
    vera = Utilisateur.objects.create_user("vera", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id,
        code="VERA",
        label={"fr": "vera"},
        operations=["consulter", "valider", "parametrer"],
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=vera.id, project_id=projet.id, role=role
    )
    profils["vera"] = vera
    return organisation, projet, profils, document


def _creer(ctl, code="DEPASSEMENT", **champs):
    _, projet, profils, _ = ctl
    donnees = {
        "utilisateur": profils["dora"],
        "project_id": projet.id,
        "code": code,
        "label": {"fr": "Dépassement du budget"},
        "type_regle": "budget",
        "severity": "bloquant",
        "valid_from": DEBUT,
        "expression": DEPASSEMENT,
        "action_corrective": "Demander une réallocation budgétaire",
    } | champs
    return creer_controle(**donnees)


def _actif(ctl, code="DEPASSEMENT", **champs):
    controle = _creer(ctl, code, **champs)
    valider_controle(utilisateur=ctl[2]["vera"], controle=controle)
    return activer_controle(utilisateur=ctl[2]["vera"], controle=controle)


def _evaluer(controle, contexte, ctl, date=JOUR, **champs):
    donnees = {
        "date_operation": date,
        "objet_type": "depense",
        "service": "comptabilite",
    } | champs
    return evaluer_controle(controle, contexte, **donnees)


# --- l'enregistrement : refusé ICI, pas à l'évaluation -------------------------------------


@pytest.mark.parametrize(
    "champs",
    [
        {"expression": {"type_regle": "budget", "conditions": [
            {"champ": "depense_cumulee", "op": "regex", "valeur": ".*"}]}},
        {"expression": {"type_regle": "budget", "conditions": [
            {"champ": "inexistant", "op": "gt", "valeur": "1"}]}},
        {"expression": {"type_regle": "budget", "conditions": [
            {"champ": "depense_cumulee", "op": "gt", "valeur": 1.5}]}},
        {"expression": "depense_cumulee > 1000"},
        {"expression": None},
        {"type_regle": "inconnu"},
        {"applicable_si": {"type_regle": "budget", "conditions": [
            {"champ": "inexistant", "op": "gt", "valeur": "1"}]}},
    ],
)  # fmt: skip
def test_une_condition_hors_schema_ou_un_operateur_inconnu_est_refuse_a_l_enregistrement(
    ctl, champs
):
    with pytest.raises(ErreurMetier) as erreur:
        _creer(ctl, **champs)
    assert erreur.value.code is CodeErreur.REGLE_INVALIDE
    assert Controle.objects.count() == 0  # rien n'est enregistré


def test_un_controle_a_verifier_n_a_pas_d_expression_et_inversement(ctl):
    with pytest.raises(ErreurMetier, match="pas d'expression"):
        _creer(ctl, manuel=True)  # l'expression de _creer n'est pas permise
    manuel = _creer(ctl, "REVUE", manuel=True, expression=None)
    assert (manuel.mode, manuel.expression) == ("manuel", None)


def test_les_champs_obligatoires_et_la_severite_sont_controles(ctl):
    for champs in ({"code": " "}, {"label": {}}, {"severity": "critique"}):
        with pytest.raises(ErreurMetier) as erreur:
            _creer(ctl, **champs)
        assert erreur.value.code is CodeErreur.REGLE_INVALIDE


def test_enregistrer_exige_parametrer_et_valider_exige_valider(ctl):
    _, _, profils, _ = ctl
    with pytest.raises(PermissionDenied):
        _creer(ctl, utilisateur=profils["bruno"])
    controle = _creer(ctl)
    with pytest.raises(PermissionDenied):
        valider_controle(utilisateur=profils["dora"], controle=controle)
    valider_controle(utilisateur=profils["vera"], controle=controle)
    with pytest.raises(PermissionDenied):
        activer_controle(utilisateur=profils["bruno"], controle=controle)


# --- le cycle de vie, tenu par la base -----------------------------------------------------


def test_un_controle_se_valide_s_active_et_une_version_ferme_la_precedente(ctl):
    _, projet, profils, _ = ctl
    v1 = _actif(ctl)
    v2 = _creer(ctl, valid_from=D(2027, 1, 1))
    assert v2.version == 2
    valider_controle(utilisateur=profils["vera"], controle=v2)
    activer_controle(utilisateur=profils["vera"], controle=v2)
    v1.refresh_from_db()
    assert (v1.status, v1.valid_to) == ("active", D(2027, 1, 1))


def test_on_ne_saute_pas_la_validation_et_un_rejet_est_definitif(ctl):
    _, _, profils, _ = ctl
    controle = _creer(ctl)
    with pytest.raises(ErreurMetier) as erreur:
        activer_controle(utilisateur=profils["vera"], controle=controle)
    assert erreur.value.code is CodeErreur.TRANSITION_INTERDITE
    with pytest.raises(ErreurMetier, match="motif"):
        rejeter_controle(utilisateur=profils["vera"], controle=controle, motif=" ")
    rejeter_controle(utilisateur=profils["vera"], controle=controle, motif="Doublon")
    controle.refresh_from_db()
    assert controle.status == "rejected"
    with pytest.raises(ErreurMetier):
        valider_controle(utilisateur=profils["vera"], controle=controle)


def test_la_base_refuse_deux_controles_actifs_qui_se_chevauchent(ctl):
    _actif(ctl)
    autre = _creer(ctl, valid_from=D(2026, 6, 1))
    valider_controle(utilisateur=ctl[2]["vera"], controle=autre)
    with pytest.raises(IntegrityError, match="controle_actif_sans_chevauchement"):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute("UPDATE controles_controle SET status='active' WHERE id=%s", [autre.id])


def test_un_controle_valide_ne_change_pas_et_ne_recule_pas_y_compris_en_sql_direct(ctl):
    controle = _actif(ctl)
    for sql, message in [
        ("UPDATE controles_controle SET severity='information' WHERE id=%s", "ne se modifie pas"),
        ("UPDATE controles_controle SET status='draft' WHERE id=%s", "ne recule pas"),
        ("DELETE FROM controles_controle WHERE id=%s", "ne se supprime pas"),
    ]:
        with pytest.raises(IntegrityError, match=message):
            with transaction.atomic(), connection.cursor() as cur:
                cur.execute(sql, [controle.id])
    brouillon = _creer(ctl, "AUTRE")
    brouillon.delete()  # un brouillon, lui, se supprime


def test_la_base_refuse_une_expression_incoherente_avec_le_mode(ctl):
    _, projet, profils, _ = ctl
    commun = {
        "org_id": ctl[0].id,
        "project_id": projet.id,
        "label": {"fr": "x"},
        "type_regle": "budget",
        "severity": "bloquant",
        "valid_from": DEBUT,
    }
    with pytest.raises(IntegrityError, match="controle_expression_selon_mode"):
        with transaction.atomic():
            Controle.objects.create(code="A", mode="automatique", expression=None, **commun)
    with pytest.raises(IntegrityError, match="controle_expression_selon_mode"):
        with transaction.atomic():
            Controle.objects.create(code="B", mode="manuel", expression=DEPASSEMENT, **commun)
    with pytest.raises(IntegrityError, match="controle_objets_json"):
        with transaction.atomic():
            Controle.objects.create(code="C", mode="automatique", expression=["x"], **commun)
    with pytest.raises(IntegrityError, match="controle_type_regle_ferme"):
        with transaction.atomic():
            Controle.objects.create(
                code="D", mode="automatique", expression=DEPASSEMENT,
                **{**commun, "type_regle": "magie"},
            )  # fmt: skip


# --- l'évaluation et son journal -----------------------------------------------------------


def test_chaque_evaluation_laisse_une_ligne_de_journal_complete(ctl):
    organisation, projet, profils, document = ctl
    controle = _actif(ctl)
    exigence = _exigence(ctl, "BUDGET-CTRL")
    rattacher(
        utilisateur=profils["dora"], exigence=exigence, target_type="control", target_id=controle.id
    )
    evaluation = _evaluer(controle, {"depense_cumulee": M("1250.50")}, ctl, utilisateur=None)

    assert EvaluationControle.objects.count() == 1
    assert (evaluation.resultat, evaluation.severity) == ("bloquant", "bloquant")
    assert evaluation.controle_id == controle.id and evaluation.controle_version == 1
    assert evaluation.valeur_constatee == "1250.50"
    assert evaluation.valeur_attendue == "lte 1000"
    assert "Dépassement du budget" in evaluation.message and "1250.50" in evaluation.message
    assert evaluation.action_corrective == "Demander une réallocation budgétaire"
    assert evaluation.evaluee_le == D(2026, 6, 15)
    assert (evaluation.exigence_code, evaluation.exigence_clause) == ("BUDGET-CTRL", "§ 4.2")
    assert evaluation.exigence_id == exigence.id
    assert (evaluation.declencheur_type, evaluation.declencheur_nom) == ("service", "comptabilite")
    assert evaluation.declencheur_id is None
    assert evaluation.project_id == projet.id and evaluation.objet_type == "depense"


def test_le_resultat_suit_la_severite_du_controle_et_un_succes_n_a_pas_d_action(ctl):
    _, _, profils, _ = ctl
    for severite in ("bloquant", "avertissement", "information"):
        controle = _actif(ctl, code=f"CTRL-{severite}", severity=severite)
        ko = _evaluer(controle, {"depense_cumulee": M("1001")}, ctl)
        ok = _evaluer(controle, {"depense_cumulee": M("1000")}, ctl)
        assert (ko.resultat, ok.resultat) == (severite, "reussi")
        assert ko.action_corrective and ok.action_corrective == ""
        assert ok.valeur_constatee == "" and ok.valeur_attendue == ""
    assert EvaluationControle.objects.count() == 6


def test_le_declencheur_est_un_utilisateur_ou_un_service_nomme_jamais_les_deux(ctl):
    _, _, profils, _ = ctl
    controle = _actif(ctl)
    contexte = {"depense_cumulee": M("1")}
    par_utilisateur = evaluer_controle(
        controle, contexte, date_operation=D(2026, 6, 15), objet_type="depense",
        utilisateur=profils["amina"],
    )  # fmt: skip
    assert (par_utilisateur.declencheur_type, par_utilisateur.declencheur_id) == (
        "utilisateur",
        profils["amina"].id,
    )
    for champs in ({}, {"utilisateur": profils["amina"], "service": "comptabilite"}):
        with pytest.raises(ValueError, match="déclencheur"):
            evaluer_controle(
                controle, contexte, date_operation=D(2026, 6, 15), objet_type="depense", **champs
            )
    assert EvaluationControle.objects.count() == 1


def test_un_controle_conditionnel_non_applicable_est_note_dans_le_journal(ctl):
    applicable_si = {
        "type_regle": "budget",
        "conditions": [{"champ": "montant", "op": "gte", "valeur": "5000"}],
    }
    controle = _actif(ctl, applicable_si=applicable_si)
    petit = _evaluer(controle, {"montant": M("100"), "depense_cumulee": M("9999")}, ctl)
    assert petit.resultat == "non_applicable" and "non applicable" in petit.message
    gros = _evaluer(controle, {"montant": M("6000"), "depense_cumulee": M("9999")}, ctl)
    assert gros.resultat == "bloquant"
    assert EvaluationControle.objects.count() == 2  # les deux évaluations sont au journal


def test_la_version_du_profil_de_decaissement_est_notee_dans_le_journal(cadre_config):
    organisation, projet, profils, document = cadre_config
    vera = Utilisateur.objects.create_user("vera", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id, code="VERA", label={"fr": "v"}, operations=["valider", "parametrer"]
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=vera.id, project_id=projet.id, role=role
    )
    profils["vera"] = vera
    from niveau1_socle.financements.models import Bailleur

    accord = _activer(
        _accord(projet, profils, Bailleur.objects.get(code="IDA"), "IDA-1", devise="USD"), profils
    )
    profil = creer_profil(organisation, projet, accord, valid_from=DEBUT, regles=[])
    ctx = (organisation, projet, profils, document)
    controle = _actif(ctx)
    avec = _evaluer(controle, {"depense_cumulee": M("1")}, ctx, accord=accord)
    sans = _evaluer(controle, {"depense_cumulee": M("1")}, ctx)
    assert avec.profile_version_id == profil.id and sans.profile_version_id is None


def test_un_controle_non_actif_a_la_date_n_est_pas_evalue(ctl):
    brouillon = _creer(ctl, "BROUILLON")
    actif = _actif(ctl, valid_from=D(2026, 3, 1))
    for controle, date in ((brouillon, D(2026, 6, 1)), (actif, D(2026, 2, 28))):
        with pytest.raises(ErreurMetier) as erreur:
            _evaluer(controle, {"depense_cumulee": M("1")}, ctl, date=date)
        assert erreur.value.code is CodeErreur.AUCUNE_CONFIGURATION_A_LA_DATE
    assert (
        _evaluer(actif, {"depense_cumulee": M("1")}, ctl, date=D(2026, 3, 1)).resultat == "reussi"
    )
    assert EvaluationControle.objects.count() == 1


def test_evaluer_tous_ne_prend_que_les_controles_actifs_du_type(ctl):
    _actif(ctl, "A-BUDGET")
    _actif(ctl, "B-BUDGET", severity="information")
    _creer(ctl, "C-BROUILLON")
    _actif(
        ctl, "D-AVANCES", type_regle="avances",
        expression={
            "type_regle": "avances",
            "conditions": [{"champ": "justifiee", "op": "est_vrai"}],
        },
    )  # fmt: skip
    evaluations = evaluer_tous(
        ctl[1].id, "budget", {"depense_cumulee": M("2000")}, date_operation=D(2026, 6, 1),
        objet_type="depense", service="comptabilite",
    )  # fmt: skip
    assert [e.controle.code for e in evaluations] == ["A-BUDGET", "B-BUDGET"]
    assert [e.resultat for e in evaluations] == ["bloquant", "information"]


def test_le_journal_est_en_ajout_seul_y_compris_en_sql_direct(ctl):
    controle = _actif(ctl)
    evaluation = _evaluer(controle, {"depense_cumulee": M("1")}, ctl)
    for sql in (
        "UPDATE controles_evaluationcontrole SET resultat='bloquant' WHERE id=%s",
        "DELETE FROM controles_evaluationcontrole WHERE id=%s",
    ):
        with pytest.raises(IntegrityError, match="ajout seul"):
            with transaction.atomic(), connection.cursor() as cur:
                cur.execute(sql, [evaluation.id])


def test_la_base_refuse_une_evaluation_incoherente(ctl):
    organisation, projet, _, _ = ctl
    controle = _actif(ctl)
    commun = {
        "org_id": organisation.id,
        "controle": controle,
        "project_id": projet.id,
        "objet_type": "depense",
        "resultat": "reussi",
        "severity": "bloquant",
        "evaluee_le": DEBUT,
        "controle_version": controle.version,
    }
    for champs, contrainte in [
        ({"controle_version": 7}, "décrit la version"),
        ({"declencheur_type": "service", "declencheur_nom": ""}, "evaluation_declencheur_coherent"),
        (
            {"declencheur_type": "service", "declencheur_nom": "x", "declencheur_id": ctl[2]["amina"].id},
            "evaluation_declencheur_coherent",
        ),
        ({"declencheur_type": "utilisateur", "declencheur_nom": "x"}, "evaluation_declencheur_coherent"),
        ({"declencheur_type": "robot", "declencheur_nom": "x"}, "evaluation_declencheur_(ferme|coherent)"),
        ({"declencheur_type": "service", "declencheur_nom": "x", "resultat": "magique"}, "evaluation_resultat_ferme"),
    ]:  # fmt: skip
        with pytest.raises(IntegrityError, match=contrainte), transaction.atomic():
            EvaluationControle.objects.create(**(commun | champs))


# --- contrôles « à vérifier » : on n'avance pas tant qu'ils ne sont pas tranchés -------------


def test_un_controle_a_verifier_non_tranche_interdit_d_avancer(ctl):
    _, projet, profils, _ = ctl
    manuel = _actif(ctl, "REVUE-PIECES", manuel=True, expression=None)
    objet = __import__("uuid").uuid4()
    evaluation = _evaluer(manuel, {}, ctl, objet_id=objet)
    assert evaluation.resultat == "a_verifier"

    with pytest.raises(ErreurMetier) as erreur:
        exiger_controles_tranches(projet.id, "depense", objet)
    assert erreur.value.code is CodeErreur.CONTROLE_BLOQUANT
    assert "REVUE-PIECES" in erreur.value.message and "non tranchée" in erreur.value.message

    trancher(
        utilisateur=profils["vera"], evaluation=evaluation, decision="conforme", motif="Pièces vues"
    )
    exiger_controles_tranches(projet.id, "depense", objet)  # l'étape devient accessible


def test_une_decision_non_conforme_bloque_toujours(ctl):
    _, projet, profils, _ = ctl
    manuel = _actif(ctl, "REVUE", manuel=True, expression=None)
    objet = __import__("uuid").uuid4()
    evaluation = _evaluer(manuel, {}, ctl, objet_id=objet)
    trancher(utilisateur=profils["vera"], evaluation=evaluation, decision="non_conforme", motif="x")
    (attente,) = controles_en_attente(projet.id, "depense", objet)
    assert attente[1] == "déclaré non conforme"
    with pytest.raises(ErreurMetier):
        exiger_controles_tranches(projet.id, "depense", objet)


def test_un_resultat_bloquant_interdit_d_avancer_et_la_derniere_evaluation_fait_foi(ctl):
    _, projet, profils, _ = ctl
    controle = _actif(ctl)
    objet = __import__("uuid").uuid4()
    _evaluer(controle, {"depense_cumulee": M("2000")}, ctl, objet_id=objet)
    with pytest.raises(ErreurMetier, match="contrôle bloquant"):
        exiger_controles_tranches(projet.id, "depense", objet)
    _evaluer(controle, {"depense_cumulee": M("900")}, ctl, objet_id=objet)  # corrigé, réévalué
    exiger_controles_tranches(projet.id, "depense", objet)
    assert controles_en_attente(projet.id, "depense", __import__("uuid").uuid4()) == []


def test_les_avertissements_et_informations_ne_bloquent_pas(ctl):
    _, projet, _, _ = ctl
    controle = _actif(ctl, severity="avertissement")
    objet = __import__("uuid").uuid4()
    assert _evaluer(controle, {"depense_cumulee": M("9999")}, ctl, objet_id=objet).resultat == (
        "avertissement"
    )
    exiger_controles_tranches(projet.id, "depense", objet)


def test_trancher_exige_valider_une_decision_motivee_et_un_controle_a_verifier(ctl):
    _, _, profils, _ = ctl
    manuel = _actif(ctl, "REVUE", manuel=True, expression=None)
    a_verifier = _evaluer(manuel, {}, ctl)
    with pytest.raises(PermissionDenied):
        trancher(utilisateur=profils["dora"], evaluation=a_verifier, decision="conforme", motif="x")
    for decision, motif in (("peut-etre", "x"), ("conforme", " ")):
        with pytest.raises(ErreurMetier) as erreur:
            trancher(
                utilisateur=profils["vera"], evaluation=a_verifier, decision=decision, motif=motif
            )
        assert erreur.value.code is CodeErreur.REGLE_INVALIDE
    reussi = _evaluer(_actif(ctl), {"depense_cumulee": M("1")}, ctl)
    with pytest.raises(ErreurMetier) as erreur:
        trancher(utilisateur=profils["vera"], evaluation=reussi, decision="conforme", motif="x")
    assert erreur.value.code is CodeErreur.TRANSITION_INTERDITE


def test_les_decisions_sont_en_ajout_seul_et_la_base_garde_leur_coherence(ctl):
    organisation, _, profils, _ = ctl
    manuel = _actif(ctl, "REVUE", manuel=True, expression=None)
    a_verifier = _evaluer(manuel, {}, ctl)
    decision = trancher(
        utilisateur=profils["vera"], evaluation=a_verifier, decision="conforme", motif="Vu"
    )
    for sql in (
        "UPDATE controles_decisioncontrole SET decision='non_conforme' WHERE id=%s",
        "DELETE FROM controles_decisioncontrole WHERE id=%s",
    ):
        with pytest.raises(IntegrityError, match="ajout seul"):
            with transaction.atomic(), connection.cursor() as cur:
                cur.execute(sql, [decision.id])
    reussi = _evaluer(_actif(ctl), {"depense_cumulee": M("1")}, ctl)
    with pytest.raises(IntegrityError, match="se tranche"), transaction.atomic():
        DecisionControle.objects.create(
            org_id=organisation.id, evaluation=reussi, decision="conforme", motif="x",
            decided_by=profils["vera"].id,
        )  # fmt: skip
    with pytest.raises(IntegrityError, match="decision_controle_motivee"), transaction.atomic():
        DecisionControle.objects.create(
            org_id=organisation.id, evaluation=a_verifier, decision="conforme", motif="",
            decided_by=profils["vera"].id,
        )  # fmt: skip


# --- rattachement à l'exigence et codes d'erreur -------------------------------------------


def test_un_controle_actif_sans_exigence_source_est_signale_comme_orphelin(ctl):
    _, projet, profils, _ = ctl
    controle = _actif(ctl, "SANS-SOURCE")
    (orphelin,) = detecter_configuration_orpheline(projet.id, D(2026, 6, 1))
    assert (orphelin.target_type, orphelin.libelle) == ("control", "SANS-SOURCE v1")
    rattacher(
        utilisateur=profils["dora"],
        exigence=_exigence(ctl, "SOURCE"),
        target_type="control",
        target_id=controle.id,
    )
    assert detecter_configuration_orpheline(projet.id, D(2026, 6, 1)) == []


def test_les_douze_codes_d_erreur_du_plan_sont_stables():
    assert {c.value for c in CodeErreur} == {
        "ACCES_ORGANISATION_REFUSE", "ACCES_PROJET_REFUSE", "ACCORD_INTROUVABLE",
        "AUCUNE_CONFIGURATION_A_LA_DATE", "CONFIGURATION_NON_APPROUVEE", "CONFLIT_DE_PERIODE",
        "REGLE_INVALIDE", "CONTROLE_BLOQUANT", "PIECE_OBLIGATOIRE", "SOLDE_CATEGORIE_INSUFFISANT",
        "APPROBATION_REQUISE", "TRANSITION_INTERDITE",
    }  # fmt: skip
    erreur = ErreurMetier(CodeErreur.CONTROLE_BLOQUANT, "Contrôles à traiter : X")
    assert erreur.vers_dict() == {"code": "CONTROLE_BLOQUANT", "message": "Contrôles à traiter : X"}
    with pytest.raises(ValueError):
        ErreurMetier("CODE_QUI_N_EXISTE_PAS", "x")


def test_les_actions_sont_tracees_dans_le_journal_chaine(ctl):
    organisation, _, profils, _ = ctl
    controle = _actif(ctl)
    _evaluer(controle, {"depense_cumulee": M("1")}, ctl)
    from core.models import AuditLog

    actions = list(AuditLog.objects.filter(object_id=controle.id).values_list("action", flat=True))
    assert actions == ["control_created", "control_validated", "control_activated"]
    assert verifier_chaine(organisation.id) is None


def test_seule_une_exigence_active_est_citee_comme_source_dans_le_journal(ctl):
    _, _, profils, _ = ctl
    controle = _actif(ctl)
    proposee = _exigence(ctl, "SOURCE-PROPOSEE", statut="proposed")
    rattacher(
        utilisateur=profils["dora"], exigence=proposee, target_type="control", target_id=controle.id
    )
    evaluation = _evaluer(controle, {"depense_cumulee": M("1")}, ctl)
    assert (evaluation.exigence_id, evaluation.exigence_code, evaluation.exigence_clause) == (
        None,
        "",
        "",
    )
    active = _exigence(ctl, "SOURCE-ACTIVE")
    rattacher(
        utilisateur=profils["dora"], exigence=active, target_type="control", target_id=controle.id
    )
    assert _evaluer(controle, {"depense_cumulee": M("1")}, ctl).exigence_code == "SOURCE-ACTIVE"


def test_un_controle_rejete_est_definitif_meme_vers_un_autre_statut_final(ctl):
    _, _, profils, _ = ctl
    controle = _creer(ctl)
    rejeter_controle(utilisateur=profils["vera"], controle=controle, motif="Hors périmètre")
    with pytest.raises(IntegrityError, match="est définitif"):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(
                "UPDATE controles_controle SET status='superseded' WHERE id=%s", [controle.id]
            )


def test_la_fin_de_validite_d_un_controle_ne_se_modifie_plus_une_fois_posee(ctl):
    _, _, profils, _ = ctl
    v1 = _actif(ctl)
    v2 = _creer(ctl, valid_from=D(2027, 1, 1))
    valider_controle(utilisateur=profils["vera"], controle=v2)
    activer_controle(utilisateur=profils["vera"], controle=v2)  # ferme v1 au 01/01/2027
    with pytest.raises(IntegrityError, match="fin de validité"):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute("UPDATE controles_controle SET valid_to='2028-01-01' WHERE id=%s", [v1.id])
