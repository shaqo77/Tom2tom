# ruff: noqa: F811
"""Simulation de revue bailleur et indicateur « accepté au premier envoi ». Voir L6-T07.

Contrôle du plan : un rapport avec une avance non justifiée au-delà du délai reçoit un avis `no-go`
qui nomme l'avance et le nombre de jours de retard. Plus : go, réserves, motifs connus, journal,
envois successifs, issue posée une fois, taux calculé sur les premiers envois.
"""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied

from core.erreurs import CodeErreur, ErreurMetier
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau4_reporting.controles.models import EvaluationControle
from niveau4_reporting.controles.services import (
    activer_controle,
    installer_bibliotheque,
    valider_controle,
)
from niveau4_reporting.publication.models import (
    AvisRevue,
    MotifRejet,
    SimulationRevue,
    SoumissionBailleur,
)
from niveau4_reporting.publication.revue import (
    enregistrer_envoi,
    enregistrer_issue,
    enregistrer_motif,
    simuler_revue,
    taux_acceptation_premier_envoi,
)
from tests.test_avances_bd import _justifier, _verser
from tests.test_avances_bd import cadre as cadre_avances  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = datetime.date
JANVIER = D(2026, 1, 1)
COURS = D(2026, 3, 10)
FIN_T1 = D(2026, 3, 31)
ENVOI = D(2026, 5, 10)
ISSUE = D(2026, 6, 1)


@pytest.fixture
def revue(cadre_avances):
    organisation, projet, profils, agents = cadre_avances
    for nom, operations in {
        "pia": ["consulter", "publier"],
        "bruno_v": ["consulter", "valider"],
    }.items():
        u = Utilisateur.objects.create_user(nom, password="x", org_id=organisation.id)
        role = Role.objects.create(
            org_id=organisation.id, code=nom.upper(), label={"fr": nom}, operations=operations
        )
        Habilitation.objects.create(
            org_id=organisation.id, user_id=u.id, project_id=projet.id, role=role
        )
        profils[nom] = u
    resultat = installer_bibliotheque(
        utilisateur=profils["dora"],
        project_id=projet.id,
        valid_from=JANVIER,
        codes=["AVA-DELAI", "AVA-NON-JUSTIFIEE"],
    )
    assert len(resultat.crees) == 2
    for controle in resultat.crees:
        valider_controle(utilisateur=profils["bruno_v"], controle=controle)
        activer_controle(utilisateur=profils["dora"], controle=controle)
    return organisation, projet, profils, agents


def _simuler(revue, date=COURS, **champs):
    _, projet, profils, _ = revue
    return simuler_revue(
        utilisateur=profils["pia"], project_id=projet.id, date_effet=date, **champs
    )


# --- l'avis ----------------------------------------------------------------------------------


def test_une_avance_non_justifiee_au_dela_du_delai_donne_no_go_et_nomme_l_avance_et_le_retard(
    revue,
):
    organisation, projet, profils, agents = revue
    _verser(projet, profils, agents, reference="AV-7", montant="1000", date=D(2026, 2, 1))
    simulation = _simuler(revue)  # délai 30 jours : échue le 03/03, donc 7 jours de retard le 10/03
    assert simulation.avis == AvisRevue.NO_GO
    delai = next(c for c in simulation.constats if c["controle"] == "AVA-DELAI")
    assert delai["gravite"] == "bloquant"
    for langue in ("fr", "en"):
        assert "AV-7" in delai["message"][langue]
        assert "7" in delai["message"][langue]
    assert "7 jour(s) de retard" in delai["message"]["fr"]
    assert "7 day(s) late" in delai["message"]["en"]
    assert delai["action"]["fr"] and delai["action"]["en"]  # l'action à mener est donnée
    assert delai["objet"] == "avance:AV-7"


def test_sans_anomalie_l_avis_est_go(revue):
    organisation, projet, profils, agents = revue
    avance = _verser(projet, profils, agents, montant="1000", date=D(2026, 2, 1))
    _justifier(avance, profils, "1000", D(2026, 3, 1))
    simulation = _simuler(revue)
    assert (simulation.avis, simulation.constats) == (AvisRevue.GO, [])


def test_une_avance_pas_encore_echue_ne_bloque_pas(revue):
    organisation, projet, profils, agents = revue
    _verser(projet, profils, agents, montant="1000", date=D(2026, 2, 1))
    assert _simuler(revue, date=D(2026, 2, 20)).avis == AvisRevue.GO


def test_un_constat_qui_recoupe_un_motif_connu_est_marque_et_force_le_no_go(revue):
    organisation, projet, profils, agents = revue
    _, projet, profils, _ = revue
    # AVA-NON-JUSTIFIEE n'est qu'un avertissement ; mais le bailleur a déjà rejeté pour cela.
    from niveau4_reporting.controles.models import Controle

    Controle.objects.filter(code="AVA-DELAI").update(status="superseded")  # reste l'avertissement
    sans_motif = _verser(projet, profils, agents, montant="1000", date=D(2026, 2, 1))
    assert sans_motif
    assert _simuler(revue).avis == AvisRevue.GO_RESERVES
    enregistrer_motif(
        utilisateur=profils["dora"], project_id=projet.id, code="AVANCES-ANCIENNES",
        label={"fr": "Avances anciennes non apurées", "en": "Old unsettled advances"},
        controle_code="AVA-NON-JUSTIFIEE", source="Lettre de rejet du 12/03/2025",
    )  # fmt: skip
    simulation = _simuler(revue)
    assert simulation.avis == AvisRevue.NO_GO
    connu = simulation.constats[0]["motif_connu"]
    assert connu["code"] == "AVANCES-ANCIENNES" and "12/03/2025" in connu["source"]


def test_un_motif_inactif_ne_compte_plus(revue):
    organisation, projet, profils, agents = revue
    from niveau4_reporting.controles.models import Controle

    Controle.objects.filter(code="AVA-DELAI").update(status="superseded")
    _verser(projet, profils, agents, montant="1000", date=D(2026, 2, 1))
    motif = enregistrer_motif(
        utilisateur=profils["dora"], project_id=projet.id, code="M1",
        label={"fr": "m", "en": "m"}, controle_code="AVA-NON-JUSTIFIEE",
    )  # fmt: skip
    MotifRejet.objects.filter(pk=motif.pk).update(actif=False)
    assert _simuler(revue).avis == AvisRevue.GO_RESERVES


def test_la_simulation_est_gardee_telle_quelle_sans_toucher_au_journal_reel(revue):
    organisation, projet, profils, agents = revue
    _verser(projet, profils, agents, montant="1000", date=D(2026, 2, 1))
    simulation = _simuler(revue)
    assert SimulationRevue.objects.filter(pk=simulation.pk).exists()
    assert {c["controle"] for c in simulation.constats} == {"AVA-DELAI", "AVA-NON-JUSTIFIEE"}
    assert not EvaluationControle.objects.exists()  # « à blanc » : rien dans le journal réel
    with pytest.raises(IntegrityError), transaction.atomic():
        SimulationRevue.objects.filter(pk=simulation.pk).update(avis="go")
    with pytest.raises(IntegrityError), transaction.atomic():
        SimulationRevue.objects.filter(pk=simulation.pk).delete()


def test_simuler_exige_la_consultation(revue):
    organisation, projet, profils, agents = revue
    sans = Utilisateur.objects.create_user("sans", password="x", org_id=organisation.id)
    with pytest.raises(PermissionDenied):
        simuler_revue(utilisateur=sans, project_id=projet.id, date_effet=D(2026, 3, 10))


def test_l_indicateur_exige_la_consultation(revue):
    organisation, projet, profils, agents = revue
    sans = Utilisateur.objects.create_user("sans2", password="x", org_id=organisation.id)
    with pytest.raises(PermissionDenied):
        taux_acceptation_premier_envoi(
            utilisateur=sans, project_id=projet.id, du=JANVIER, au=FIN_T1
        )


def test_un_motif_pointe_un_controle_existant_et_un_libelle_complet(revue):
    organisation, projet, profils, agents = revue
    base = dict(utilisateur=profils["dora"], project_id=projet.id, code="X")
    with pytest.raises(ErreurMetier):
        enregistrer_motif(**base, label={"fr": "a", "en": "a"}, controle_code="INCONNU")
    with pytest.raises(ErreurMetier):
        enregistrer_motif(**base, label={"fr": "seulement"}, controle_code="AVA-DELAI")
    with pytest.raises(PermissionDenied):
        enregistrer_motif(
            **{**base, "utilisateur": profils["pia"]},
            label={"fr": "a", "en": "a"}, controle_code="AVA-DELAI",
        )  # fmt: skip
    motif = enregistrer_motif(**base, label={"fr": "a", "en": "a"}, controle_code="AVA-DELAI")
    with pytest.raises(IntegrityError), transaction.atomic():
        MotifRejet.objects.filter(pk=motif.pk).update(controle_code="AVA-NON-JUSTIFIEE")
    with pytest.raises(IntegrityError), transaction.atomic():
        MotifRejet.objects.filter(pk=motif.pk).delete()


# --- soumissions réelles et indicateur phare -------------------------------------------------


def _envoyer(revue, template="RFI", periode=FIN_T1, jour=ENVOI, **champs):
    _, projet, profils, _ = revue
    return enregistrer_envoi(
        utilisateur=profils["pia"], project_id=projet.id, template_code=template,
        period_to=periode, envoyee_le=jour, **champs,
    )  # fmt: skip


def test_les_envois_se_numerotent_et_un_nouvel_envoi_attend_l_issue_du_precedent(revue):
    _, projet, profils, _ = revue
    premier = _envoyer(revue)
    assert premier.numero_envoi == 1
    with pytest.raises(ErreurMetier) as e:
        _envoyer(revue)
    assert e.value.code == CodeErreur.TRANSITION_INTERDITE
    enregistrer_issue(
        utilisateur=profils["pia"], soumission=premier, accepte=False,
        decidee_le=D(2026, 5, 20), motif_rejet="Annexe 3 manquante",
    )  # fmt: skip
    assert _envoyer(revue, jour=D(2026, 5, 25)).numero_envoi == 2
    assert _envoyer(revue, template="ECD", jour=D(2026, 5, 25)).numero_envoi == 1  # autre rapport


def test_l_issue_se_pose_une_fois_un_rejet_est_motive(revue):
    _, projet, profils, _ = revue
    envoi = _envoyer(revue)
    with pytest.raises(ErreurMetier):
        enregistrer_issue(
            utilisateur=profils["pia"], soumission=envoi, accepte=False, decidee_le=D(2026, 5, 20)
        )
    enregistrer_issue(
        utilisateur=profils["pia"], soumission=envoi, accepte=True, decidee_le=D(2026, 5, 20)
    )
    with pytest.raises(ErreurMetier) as e:
        enregistrer_issue(
            utilisateur=profils["pia"], soumission=envoi, accepte=False,
            decidee_le=D(2026, 5, 21), motif_rejet="revirement",
        )  # fmt: skip
    assert e.value.code == CodeErreur.TRANSITION_INTERDITE
    with pytest.raises(IntegrityError), transaction.atomic():
        SoumissionBailleur.objects.filter(pk=envoi.pk).update(resultat="rejete", motif_rejet="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        SoumissionBailleur.objects.filter(pk=envoi.pk).delete()


def test_la_base_refuse_une_issue_incoherente(revue):
    _, projet, profils, _ = revue
    envoi = _envoyer(revue)
    with pytest.raises(IntegrityError), transaction.atomic():  # rejeté sans motif
        SoumissionBailleur.objects.filter(pk=envoi.pk).update(
            resultat="rejete", decidee_le=D(2026, 5, 20)
        )
    with pytest.raises(IntegrityError), transaction.atomic():  # accepté sans date
        SoumissionBailleur.objects.filter(pk=envoi.pk).update(resultat="accepte")


def test_le_taux_d_acceptation_ne_compte_que_les_premiers_envois_decides(revue):
    _, projet, profils, _ = revue

    def issue(envoi, accepte, jour=ISSUE):
        return enregistrer_issue(
            utilisateur=profils["pia"], soumission=envoi, accepte=accepte, decidee_le=jour,
            motif_rejet="" if accepte else "rejeté",
        )  # fmt: skip

    a = _envoyer(revue, template="A", jour=D(2026, 4, 1))
    b = _envoyer(revue, template="B", jour=D(2026, 4, 2))
    c = _envoyer(revue, template="C", jour=D(2026, 4, 3))
    d = _envoyer(revue, template="D", jour=D(2026, 4, 4))  # sans issue : n'entre pas dans le taux
    issue(a, True)
    issue(b, False)
    issue(c, True)
    # B renvoyé puis accepté : le SECOND envoi ne compte pas dans « accepté au premier envoi ».
    issue(_envoyer(revue, template="B", jour=D(2026, 4, 20)), True)
    ind = taux_acceptation_premier_envoi(
        utilisateur=profils["pia"], project_id=projet.id, du=D(2026, 4, 1), au=D(2026, 4, 30)
    )
    assert (ind.acceptes, ind.decides, ind.en_attente) == (2, 3, 1)
    assert ind.taux == Decimal(2) / Decimal(3)
    assert d.resultat == "en_attente"
    vide = taux_acceptation_premier_envoi(
        utilisateur=profils["pia"], project_id=projet.id, du=D(2027, 1, 1), au=D(2027, 12, 31)
    )
    assert (vide.decides, vide.taux) == (0, None)  # pas de division par zéro, pas de taux inventé


def test_envoyer_et_poser_l_issue_exigent_la_publication(revue):
    _, projet, profils, _ = revue
    with pytest.raises(PermissionDenied):
        enregistrer_envoi(
            utilisateur=profils["dora"], project_id=projet.id, template_code="RFI",
            period_to=D(2026, 3, 31), envoyee_le=D(2026, 5, 10),
        )  # fmt: skip
