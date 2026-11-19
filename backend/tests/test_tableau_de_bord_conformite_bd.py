# ruff: noqa: F811
"""Le tableau de bord : échéances, rapports en attente, anomalies, acceptation. Voir L10-T02b.

Des comptes par projet ; le total est la somme exacte des détails, et le taux d'acceptation
consolidé est calculé sur les sommes (jamais une moyenne de taux).
"""

import datetime
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from niveau1_socle.habilitations.models import Habilitation
from niveau3_config.models import Echeance
from niveau3_config.services.documents import enregistrer_document
from niveau4_reporting.controles.models import Controle, EvaluationControle
from niveau4_reporting.controles.services import (
    activer_controle,
    installer_bibliotheque,
    valider_controle,
)
from niveau4_reporting.publication.revue import enregistrer_envoi, enregistrer_issue
from niveau4_reporting.tableau_de_bord import Filtres, tableau_de_bord
from tests.test_avances_bd import cadre as cadre_avances  # noqa: F401
from tests.test_calendrier_bd import _active
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_rattachement_bd import PHRASE
from tests.test_revue_bailleur_bd import revue  # noqa: F401
from tests.test_tableau_de_bord_bd import _droits, _poser

pytestmark = pytest.mark.django_db(transaction=True)
D = datetime.date
Utilisateur = get_user_model()
JOUR = D(2026, 6, 30)


@pytest.fixture
def parc(revue, settings, tmp_path):
    """P1 (le projet de la revue) et P2 (mêmes droits), chacun avec ses échéances et envois."""
    settings.STOCKAGE_DOCUMENTS_ROOT = tmp_path
    organisation, p1, profils, agents = revue
    p2 = _creer_projet(organisation, "P2")
    _droits(organisation, p2, profils, modele=p1)
    document = enregistrer_document(
        utilisateur=profils["dora"], project_id=p1.id, kind="dfil", title="DFIL",
        version="1", contenu=PHRASE.encode(),
    )  # fmt: skip
    cfg = (organisation, p1, profils, document)
    exigence = _active(cfg, "RFI")
    return organisation, p1, p2, profils, exigence


def _echeance(parc, projet, jour, statut="a_remettre"):
    organisation, _, _, _, exigence = parc
    _poser(organisation)
    remise = (
        {"rapport_id": uuid.uuid4(), "remise_le": timezone.now(), "remise_par": uuid.uuid4()}
        if statut == "remise"
        else {}
    )
    return Echeance.objects.create(
        **remise,
        org_id=organisation.id,
        project_id=projet.id,
        exigence=exigence,
        periode_debut=jour - datetime.timedelta(days=90),
        periode_fin=jour - datetime.timedelta(days=45),
        date_echeance=jour,
        statut=statut,
    )


def _vue(parc, **champs):
    organisation, _, _, profils, _ = parc
    _poser(organisation)
    return tableau_de_bord(utilisateur=profils["pia"], jour=JOUR, filtres=Filtres(**champs))


def _envoi(parc, projet, template, jour, accepte=None):
    organisation, _, _, profils, _ = parc
    _poser(organisation)
    envoi = enregistrer_envoi(
        utilisateur=profils["pia"], project_id=projet.id, template_code=template,
        period_to=D(2026, 3, 31), envoyee_le=jour,
    )  # fmt: skip
    if accepte is not None:
        enregistrer_issue(
            utilisateur=profils["pia"], soumission=envoi, accepte=accepte,
            decidee_le=jour + datetime.timedelta(days=5), motif_rejet="" if accepte else "rejeté",
        )  # fmt: skip
    return envoi


def test_les_echeances_se_classent_par_niveau_et_les_remises_ne_comptent_pas(parc):
    _, p1, p2, _, _ = parc
    _echeance(parc, p1, D(2026, 7, 5))  # dans 5 jours : imminente
    _echeance(parc, p1, D(2026, 6, 25))  # dépassée de 5 jours : en retard
    _echeance(parc, p1, D(2026, 6, 10))  # dépassée de 20 jours : escalade
    _echeance(parc, p1, D(2026, 12, 31))  # lointaine : à remettre, sans alerte
    _echeance(parc, p2, D(2026, 6, 26))  # P2 : en retard
    _echeance(parc, p2, D(2026, 6, 1), statut="remise")
    conformite = _vue(parc).conformite
    c1, c2 = conformite.par_projet[p1.id], conformite.par_projet[p2.id]
    assert (c1.echeances_a_remettre, c1.echeances_imminentes) == (4, 1)
    assert (c1.echeances_en_retard, c1.echeances_en_escalade) == (1, 1)
    assert (c2.echeances_a_remettre, c2.echeances_en_retard) == (
        1,
        1,
    )  # la remise n'est pas comptée
    assert conformite.total("echeances_a_remettre") == 5
    assert conformite.total("echeances_en_retard") == 2


def test_les_rapports_en_attente_sont_les_envois_sans_issue(parc):
    _, p1, p2, _, _ = parc
    _envoi(parc, p1, "A", D(2026, 4, 1))
    _envoi(parc, p1, "B", D(2026, 4, 2), accepte=True)
    _envoi(parc, p2, "A", D(2026, 4, 3))
    conformite = _vue(parc).conformite
    assert conformite.par_projet[p1.id].rapports_en_attente == 1
    assert conformite.par_projet[p2.id].rapports_en_attente == 1
    assert conformite.total("rapports_en_attente") == 2


def test_le_taux_d_acceptation_consolide_est_calcule_sur_les_sommes_pas_en_moyenne(parc):
    _, p1, p2, _, _ = parc
    for template in ("A", "B", "C"):  # P1 : 3 acceptés sur 3 (taux 1)
        _envoi(parc, p1, template, D(2026, 4, 1), accepte=True)
    _envoi(parc, p2, "A", D(2026, 4, 2), accepte=True)  # P2 : 1 accepté sur 3 (taux 1/3)
    _envoi(parc, p2, "B", D(2026, 4, 3), accepte=False)
    _envoi(parc, p2, "C", D(2026, 4, 4), accepte=False)
    conformite = _vue(parc).conformite
    assert conformite.taux_acceptation == Decimal(4) / Decimal(6)  # et non (1 + 1/3) / 2
    assert conformite.par_projet[p2.id].premiers_envois_decides == 3


def test_le_taux_suit_la_periode_et_reste_vide_sans_envoi_decide(parc):
    _, p1, _, _, _ = parc
    _envoi(parc, p1, "A", D(2026, 4, 1), accepte=True)
    assert _vue(parc, du=D(2026, 5, 1)).conformite.taux_acceptation is None  # hors période
    assert _vue(parc, au=D(2026, 3, 1)).conformite.taux_acceptation is None
    assert _vue(parc, du=D(2026, 4, 1), au=D(2026, 4, 30)).conformite.taux_acceptation == 1


def test_les_anomalies_ouvertes_comptent_les_controles_bloquants_non_leves(parc):
    organisation, p1, p2, profils, _ = parc
    _poser(organisation)
    controles = {p1.id: Controle.objects.filter(project_id=p1.id, code="AVA-DELAI").first()}
    installes = installer_bibliotheque(
        utilisateur=profils["dora"], project_id=p2.id, valid_from=D(2026, 1, 1), codes=["AVA-DELAI"]
    )
    valider_controle(utilisateur=profils["bruno_v"], controle=installes.crees[0])
    activer_controle(utilisateur=profils["dora"], controle=installes.crees[0])
    controles[p2.id] = installes.crees[0]

    def evaluer(projet, objet, resultat="bloquant"):
        controle = controles[projet.id]
        EvaluationControle.objects.create(
            org_id=organisation.id, controle=controle, controle_version=controle.version,
            project_id=projet.id, objet_type="avance", objet_id=objet, resultat=resultat,
            severity="bloquant", evaluee_le=D(2026, 6, 1), declencheur_type="service",
            declencheur_nom="test",
        )  # fmt: skip

    evaluer(p1, uuid.uuid4())
    evaluer(p1, uuid.uuid4())
    evaluer(p1, uuid.uuid4(), resultat="reussi")  # réussi : pas une anomalie
    evaluer(p2, uuid.uuid4())
    conformite = _vue(parc).conformite
    assert conformite.par_projet[p1.id].anomalies_ouvertes == 2
    assert conformite.par_projet[p2.id].anomalies_ouvertes == 1
    assert conformite.total("anomalies_ouvertes") == 3


def test_le_perimetre_limite_aussi_les_comptes_de_conformite(parc):
    organisation, p1, p2, profils, _ = parc
    _poser(organisation)
    Habilitation.objects.filter(project_id=p2.id).delete()
    _echeance(parc, p2, D(2026, 6, 20))
    conformite = _vue(parc).conformite
    assert set(conformite.par_projet) == {p1.id}
