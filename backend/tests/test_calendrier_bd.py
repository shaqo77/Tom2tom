"""Le calendrier des obligations. Voir L6-T06.

Contrôle du plan : activer une exigence trimestrielle à 45 jours génère les quatre échéances de
l'exercice, aux bonnes dates. Plus : idempotence, validité de l'exigence, annulation sans
suppression, feux, escalade, remise une seule fois.
"""

import datetime
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.erreurs import CodeErreur, ErreurMetier
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau3_config.models import Echeance, Exigence
from niveau3_config.services.calendrier import (
    alertes_du_jour,
    calendrier,
    date_echeance,
    feu,
    generer_calendrier,
    marquer_remise,
    periodes_de_l_annee,
)
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_rattachement_bd import _exigence, cadre_config  # noqa: F401

D = datetime.date
Utilisateur = get_user_model()


# --- la mécanique des dates (sans base) ------------------------------------------------------


def test_les_periodes_civiles_de_chaque_periodicite():
    assert periodes_de_l_annee("quarterly", 2026) == [
        (D(2026, 1, 1), D(2026, 3, 31)),
        (D(2026, 4, 1), D(2026, 6, 30)),
        (D(2026, 7, 1), D(2026, 9, 30)),
        (D(2026, 10, 1), D(2026, 12, 31)),
    ]
    assert len(periodes_de_l_annee("monthly", 2026)) == 12
    assert periodes_de_l_annee("semiannual", 2026)[0] == (D(2026, 1, 1), D(2026, 6, 30))
    assert periodes_de_l_annee("annual", 2026) == [(D(2026, 1, 1), D(2026, 12, 31))]
    assert periodes_de_l_annee("event", 2026) == []
    assert periodes_de_l_annee("monthly", 2028)[1][1] == D(2028, 2, 29)  # année bissextile


def test_le_delai_se_compte_apres_la_fin_de_la_periode():
    assert date_echeance(D(2026, 3, 31), 45) == D(2026, 5, 15)
    assert date_echeance(D(2026, 12, 31), 45) == D(2027, 2, 14)  # franchit l'année


# --- la génération depuis le registre ---------------------------------------------------------

pytestmark_bd = pytest.mark.django_db(transaction=True)


def _active(cfg, code="RFI", **champs):
    """Une exigence active : tout est posé en UNE mise à jour (une active ne se modifie plus)."""
    exigence = _exigence(cfg, code, statut="proposed")
    Exigence.objects.filter(pk=exigence.pk).update(
        status="active",
        validated_by=uuid.uuid4(),
        validated_at=timezone.now(),
        periodicity=champs.pop("periodicity", "quarterly"),
        due_offset_days=champs.pop("due_offset_days", 45),
        **champs,
    )
    exigence.refresh_from_db()
    return exigence


@pytest.fixture
def cal(cadre_config):  # noqa: F811
    organisation, projet, profils, document = cadre_config
    pia = Utilisateur.objects.create_user("pia", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id, code="PIA", label={"fr": "pia"}, operations=["consulter", "publier"]
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=pia.id, project_id=projet.id, role=role
    )
    profils["pia"] = pia
    return cadre_config


@pytestmark_bd
def test_une_exigence_trimestrielle_a_45_jours_genere_les_quatre_echeances_aux_bonnes_dates(cal):
    organisation, projet, profils, _ = cal
    _active(cal)
    resultat = generer_calendrier(utilisateur=profils["dora"], project_id=projet.id, annee=2026)
    assert len(resultat.creees) == 4
    assert [e.date_echeance for e in sorted(resultat.creees, key=lambda e: e.periode_fin)] == [
        D(2026, 5, 15),
        D(2026, 8, 14),
        D(2026, 11, 14),
        D(2027, 2, 14),
    ]
    assert {e.statut for e in resultat.creees} == {"a_remettre"}


@pytestmark_bd
def test_la_generation_est_idempotente(cal):
    _, projet, profils, _ = cal
    _active(cal)
    generer_calendrier(utilisateur=profils["dora"], project_id=projet.id, annee=2026)
    deuxieme = generer_calendrier(utilisateur=profils["dora"], project_id=projet.id, annee=2026)
    assert (len(deuxieme.creees), deuxieme.existantes) == (0, 4)
    assert Echeance.objects.count() == 4


@pytestmark_bd
def test_seule_une_exigence_active_en_vigueur_produit_des_echeances(cal):
    _, projet, profils, _ = cal
    _active(cal, "VIGUEUR", valid_to=D(2026, 7, 1))  # en vigueur jusqu'au 30 juin inclus
    _exigence(cal, "PROPOSEE", statut="proposed")
    Exigence.objects.filter(code="PROPOSEE").update(periodicity="monthly", due_offset_days=10)
    resultat = generer_calendrier(utilisateur=profils["dora"], project_id=projet.id, annee=2026)
    assert {e.periode_fin for e in resultat.creees} == {D(2026, 3, 31), D(2026, 6, 30)}
    assert {e.exigence.code for e in resultat.creees} == {"VIGUEUR"}


@pytestmark_bd
def test_aucun_delai_n_est_invente_et_l_evenement_n_a_pas_de_calendrier(cal):
    _, projet, profils, _ = cal
    _active(cal, "SANS-DELAI", due_offset_days=None)
    _active(cal, "EVENEMENT", periodicity="event", due_offset_days=None)
    resultat = generer_calendrier(utilisateur=profils["dora"], project_id=projet.id, annee=2026)
    assert resultat.creees == []
    assert [e.code for e in resultat.sans_delai] == ["SANS-DELAI"]  # listée, pas échéancée


@pytestmark_bd
def test_une_exigence_remplacee_annule_ses_echeances_a_remettre_sans_les_supprimer(cal):
    _, projet, profils, _ = cal
    exigence = _active(cal)
    resultat = generer_calendrier(utilisateur=profils["dora"], project_id=projet.id, annee=2026)
    premiere = min(resultat.creees, key=lambda e: e.periode_fin)
    marquer_remise(utilisateur=profils["pia"], echeance=premiere, rapport_id=uuid.uuid4())
    Exigence.objects.filter(pk=exigence.pk).update(status="superseded")
    apres = generer_calendrier(utilisateur=profils["dora"], project_id=projet.id, annee=2026)
    assert len(apres.annulees) == 3  # la remise de T1 ne bouge pas
    assert Echeance.objects.count() == 4
    assert sorted(Echeance.objects.values_list("statut", flat=True)) == [
        "annulee", "annulee", "annulee", "remise",
    ]  # fmt: skip


# --- feux, alertes, remise --------------------------------------------------------------------


def _echeance(date_ech, statut="a_remettre"):
    return Echeance(date_echeance=date_ech, statut=statut)


def test_le_feu_est_calcule_a_la_date_du_jour():
    ech = _echeance(D(2026, 5, 15))
    assert feu(ech, D(2026, 4, 1)) == "vert"
    assert feu(ech, D(2026, 4, 30)) == "orange"  # 15 jours avant : orange
    assert feu(ech, D(2026, 4, 29)) == "vert"  # 16 jours : encore vert
    assert feu(ech, D(2026, 5, 15)) == "orange"  # le jour même : pas encore en retard
    assert feu(ech, D(2026, 5, 16)) == "rouge"
    assert feu(_echeance(D(2026, 5, 15), "remise"), D(2026, 9, 1)) == "remise"


@pytestmark_bd
def test_les_alertes_du_jour_distinguent_imminente_retard_et_escalade(cal):
    _, projet, profils, _ = cal
    _active(cal)
    generer_calendrier(utilisateur=profils["dora"], project_id=projet.id, annee=2026)

    def niveaux(jour):
        return {
            (e.periode_fin.month, n) for e, n in alertes_du_jour(project_id=projet.id, jour=jour)
        }

    assert niveaux(D(2026, 4, 1)) == set()
    assert niveaux(D(2026, 5, 1)) == {(3, "imminente")}
    assert niveaux(D(2026, 5, 20)) == {(3, "en_retard")}
    assert niveaux(D(2026, 5, 23)) == {(3, "escalade")}


@pytestmark_bd
def test_le_calendrier_se_lit_trie_avec_ses_feux(cal):
    _, projet, profils, _ = cal
    _active(cal)
    generer_calendrier(utilisateur=profils["dora"], project_id=projet.id, annee=2026)
    lignes = calendrier(
        utilisateur=profils["dora"], project_id=projet.id, annee=2026, jour=D(2026, 5, 20)
    )
    assert [feu_ for _, feu_ in lignes] == ["rouge", "vert", "vert"]  # 2027-02-14 hors de 2026
    assert [e.date_echeance for e, _ in lignes] == sorted(e.date_echeance for e, _ in lignes)


@pytestmark_bd
def test_une_echeance_n_est_remise_qu_une_fois_et_ne_se_modifie_pas(cal):
    _, projet, profils, _ = cal
    _active(cal)
    ech = generer_calendrier(utilisateur=profils["dora"], project_id=projet.id, annee=2026).creees[
        0
    ]
    marquer_remise(utilisateur=profils["pia"], echeance=ech, rapport_id=uuid.uuid4())
    with pytest.raises(ErreurMetier) as e:
        marquer_remise(utilisateur=profils["pia"], echeance=ech, rapport_id=uuid.uuid4())
    assert e.value.code == CodeErreur.TRANSITION_INTERDITE
    with pytest.raises(IntegrityError), transaction.atomic():
        Echeance.objects.filter(pk=ech.pk).update(date_echeance=D(2030, 1, 1))
    with pytest.raises(IntegrityError), transaction.atomic():
        Echeance.objects.filter(pk=ech.pk).delete()
    with pytest.raises(IntegrityError), transaction.atomic():  # « remise » sans rapport
        Echeance.objects.filter(statut="a_remettre").update(statut="remise")


@pytestmark_bd
def test_les_habilitations_sont_exigees(cal):
    _, projet, profils, _ = cal
    _active(cal)
    with pytest.raises(PermissionDenied):
        generer_calendrier(utilisateur=profils["pia"], project_id=projet.id, annee=2026)
    ech = generer_calendrier(utilisateur=profils["dora"], project_id=projet.id, annee=2026).creees[
        0
    ]
    with pytest.raises(PermissionDenied):
        marquer_remise(utilisateur=profils["dora"], echeance=ech, rapport_id=uuid.uuid4())
    sans = Utilisateur.objects.create_user("sans", password="x", org_id=ech.org_id)
    with pytest.raises(PermissionDenied):
        calendrier(utilisateur=sans, project_id=projet.id, annee=2026, jour=D(2026, 1, 1))


@pytestmark_bd
def test_la_tache_quotidienne_signale_et_sort_en_erreur_en_cas_d_escalade(cal, capsys):
    from django.core.management import call_command

    organisation, projet, profils, _ = cal
    _active(cal)
    generer_calendrier(utilisateur=profils["dora"], project_id=projet.id, annee=2026)
    args = ["--organisation", str(organisation.id), "--projet", str(projet.id)]
    call_command("verifier_echeances", *args, "--date", "2026-05-01")
    assert "IMMINENTE RFI" in capsys.readouterr().out
    with pytest.raises(SystemExit) as sortie:
        call_command("verifier_echeances", *args, "--date", "2026-05-30")
    assert sortie.value.code == 2
    assert "ESCALADE RFI" in capsys.readouterr().out
