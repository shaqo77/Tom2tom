# ruff: noqa: F811, E501
"""Le circuit de validation borné. Voir L6-T02b.

Contrôles du plan : un contrôle bloquant non traité rend l'étape de validation inaccessible, vérifié
au serveur ; après dérogation le circuit avance ; deux approbations concurrentes : une seule prend
effet ; motif obligatoire au rejet ; 1 à 5 étapes.
"""

import datetime
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from rest_framework.exceptions import PermissionDenied

from core.erreurs import CodeErreur, ErreurMetier
from niveau4_reporting.controles.circuit import (
    circuit_en_vigueur,
    creer_circuit,
    decider_etape,
    ouvrir_demande,
)
from niveau4_reporting.controles.derogations import decider_derogation, demander_derogation
from niveau4_reporting.controles.models import (
    Circuit,
    DecisionEtape,
    DemandeValidation,
    EtapeCircuit,
)
from tests.test_controles_bd import _actif, _evaluer, ctl  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_derogations_bd import DEPASSEMENT_CTX, _utilisateur
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_rattachement_bd import cadre_config  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = datetime.date
JOUR = D(2026, 6, 15)

ETAPES = [
    {
        "nom": {"fr": "Validation du responsable financier", "en": "Finance manager validation"},
        "operation": "valider",
        "exige_controles_tranches": True,
    },
    {
        "nom": {"fr": "Approbation du coordonnateur", "en": "Coordinator approval"},
        "operation": "publier",
    },
]


@pytest.fixture
def cir(ctl):
    organisation, projet, profils, document = ctl
    profils["samir"] = _utilisateur(organisation, projet, "samir", ["consulter", "saisir"])
    profils["lea"] = _utilisateur(organisation, projet, "lea", ["consulter", "valider"])
    profils["coord"] = _utilisateur(organisation, projet, "coord", ["consulter", "publier"])
    circuit = creer_circuit(
        utilisateur=profils["dora"], project_id=projet.id, objet_type="depense",
        valid_from=D(2026, 1, 1), etapes=ETAPES,
    )  # fmt: skip
    return ctl, circuit


def _ouvrir(cir, objet=None, **champs):
    (organisation, projet, profils, _), _ = cir
    donnees = {
        "utilisateur": profils["samir"],
        "project_id": projet.id,
        "objet_type": "depense",
        "objet_id": objet or uuid.uuid4(),
        "date_effet": JOUR,
    } | champs
    return ouvrir_demande(**donnees)


# --- configuration du circuit ----------------------------------------------------------------


@pytest.mark.parametrize("n", [0, 6])
def test_un_circuit_a_de_une_a_cinq_etapes(cir, n):
    (_, projet, profils, _), _ = cir
    with pytest.raises(ErreurMetier):
        creer_circuit(
            utilisateur=profils["dora"], project_id=projet.id, objet_type="export",
            valid_from=JOUR, etapes=[ETAPES[0]] * n,
        )  # fmt: skip
    assert not Circuit.objects.filter(objet_type="export").exists()


def test_une_etape_exige_une_habilitation_connue_et_une_condition_valide(cir):
    (_, projet, profils, _), _ = cir
    base = dict(
        utilisateur=profils["dora"], project_id=projet.id, objet_type="export", valid_from=JOUR
    )
    for etape in (
        {**ETAPES[0], "operation": "inventee"},
        {**ETAPES[0], "condition": {"montant_min": "abc"}},
        {**ETAPES[0], "condition": {"inconnue": 1}},
        {**ETAPES[0], "nom": {"fr": "seulement"}},
    ):
        with pytest.raises((ErreurMetier, ValueError)):
            creer_circuit(**base, etapes=[etape])


def test_seul_un_parametreur_cree_un_circuit(cir):
    (_, projet, profils, _), _ = cir
    with pytest.raises(PermissionDenied):
        creer_circuit(
            utilisateur=profils["samir"], project_id=projet.id, objet_type="export",
            valid_from=JOUR, etapes=ETAPES,
        )  # fmt: skip


def test_un_nouveau_circuit_clot_le_precedent_et_l_ancien_ne_change_plus(cir):
    (_, projet, profils, _), v1 = cir
    v2 = creer_circuit(
        utilisateur=profils["dora"], project_id=projet.id, objet_type="depense",
        valid_from=D(2026, 9, 1), etapes=ETAPES[:1],
    )  # fmt: skip
    v1.refresh_from_db()
    assert (v2.version, v1.valid_to) == (2, D(2026, 9, 1))
    assert circuit_en_vigueur(projet.id, "depense", D(2026, 8, 31)).pk == v1.pk
    assert circuit_en_vigueur(projet.id, "depense", D(2026, 9, 1)).pk == v2.pk  # fin exclue
    with pytest.raises(IntegrityError), transaction.atomic():
        EtapeCircuit.objects.filter(circuit=v1).update(operation="consulter")
    with pytest.raises(IntegrityError), transaction.atomic():
        Circuit.objects.filter(pk=v1.pk).update(valid_from=D(2025, 1, 1))


# --- le parcours -----------------------------------------------------------------------------


def test_le_parcours_complet_valide_puis_approuve(cir):
    (_, _, profils, _), _ = cir
    demande = _ouvrir(cir)
    assert demande.rang_courant == 1
    decider_etape(utilisateur=profils["lea"], demande=demande, rang=1, approuver=True)
    assert (demande.statut, demande.rang_courant) == ("en_cours", 2)
    decider_etape(utilisateur=profils["coord"], demande=demande, rang=2, approuver=True)
    assert (demande.statut, demande.rang_courant) == ("approuvee", None)
    assert [(d.rang, d.decided_by_nom) for d in DecisionEtape.objects.order_by("rang")] == [
        (1, "lea"),
        (2, "coord"),
    ]


def test_chaque_etape_exige_son_habilitation_et_un_signataire_distinct_du_demandeur(cir):
    (_, _, profils, _), _ = cir
    demande = _ouvrir(cir)
    with pytest.raises(PermissionDenied):  # le coordonnateur ne saute pas l'étape 1
        decider_etape(utilisateur=profils["coord"], demande=demande, rang=1, approuver=True)
    with pytest.raises(PermissionDenied):
        decider_etape(utilisateur=profils["samir"], demande=demande, rang=1, approuver=True)
    double = _utilisateur(cir[0][0], cir[0][1], "double", ["consulter", "saisir", "valider"])
    propre = _ouvrir(cir, utilisateur=double)
    with pytest.raises(ErreurMetier) as e:
        decider_etape(utilisateur=double, demande=propre, rang=1, approuver=True)
    assert e.value.code == CodeErreur.APPROBATION_REQUISE


def test_on_ne_signe_pas_une_etape_qui_n_est_pas_la_courante(cir):
    (_, _, profils, _), _ = cir
    demande = _ouvrir(cir)
    with pytest.raises(ErreurMetier) as e:
        decider_etape(utilisateur=profils["coord"], demande=demande, rang=2, approuver=True)
    assert e.value.code == CodeErreur.TRANSITION_INTERDITE


def test_un_rejet_exige_un_motif_et_clot_la_demande(cir):
    (_, _, profils, _), _ = cir
    demande = _ouvrir(cir)
    with pytest.raises(ErreurMetier):
        decider_etape(
            utilisateur=profils["lea"], demande=demande, rang=1, approuver=False, motif=" "
        )
    decider_etape(
        utilisateur=profils["lea"],
        demande=demande,
        rang=1,
        approuver=False,
        motif="Pièces manquantes",
    )
    assert demande.statut == "rejetee"
    with pytest.raises(ErreurMetier):
        decider_etape(utilisateur=profils["lea"], demande=demande, rang=1, approuver=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        DemandeValidation.objects.filter(pk=demande.pk).update(statut="en_cours", rang_courant=1)


def test_une_seule_demande_en_cours_par_objet(cir):
    objet = uuid.uuid4()
    _ouvrir(cir, objet=objet)
    with pytest.raises(ErreurMetier, match="déjà"):
        _ouvrir(cir, objet=objet)


def test_sans_circuit_a_la_date_la_demande_est_refusee(cir):
    with pytest.raises(ErreurMetier) as e:
        _ouvrir(cir, date_effet=D(2025, 6, 1))
    assert e.value.code == CodeErreur.AUCUNE_CONFIGURATION_A_LA_DATE


def test_une_etape_dont_la_condition_n_est_pas_remplie_est_sautee(cir):
    (_, projet, profils, _), _ = cir
    creer_circuit(
        utilisateur=profils["dora"], project_id=projet.id, objet_type="avance",
        valid_from=D(2026, 1, 1),
        etapes=[
            ETAPES[0],
            {**ETAPES[1], "condition": {"montant_min": "5000"}},
        ],
    )  # fmt: skip
    petite = ouvrir_demande(
        utilisateur=profils["samir"], project_id=projet.id, objet_type="avance",
        objet_id=uuid.uuid4(), date_effet=JOUR, contexte={"montant": "100"},
    )  # fmt: skip
    decider_etape(utilisateur=profils["lea"], demande=petite, rang=1, approuver=True)
    assert petite.statut == "approuvee"  # l'étape 2 (≥ 5000) ne s'applique pas
    grosse = ouvrir_demande(
        utilisateur=profils["samir"], project_id=projet.id, objet_type="avance",
        objet_id=uuid.uuid4(), date_effet=JOUR, contexte={"montant": "9000"},
    )  # fmt: skip
    decider_etape(utilisateur=profils["lea"], demande=grosse, rang=1, approuver=True)
    assert (grosse.statut, grosse.rang_courant) == ("en_cours", 2)


# --- le blocage dur, au serveur --------------------------------------------------------------


def _avec_blocage(cir):
    ctl_ = cir[0]
    controle = _actif(ctl_)
    objet = uuid.uuid4()
    evaluation = _evaluer(controle, DEPASSEMENT_CTX, ctl_, objet_id=objet)
    return objet, evaluation


def test_un_controle_bloquant_non_traite_rend_l_etape_de_validation_inaccessible(cir):
    (_, _, profils, _), _ = cir
    objet, _ = _avec_blocage(cir)
    demande = _ouvrir(cir, objet=objet)
    with pytest.raises(ErreurMetier) as e:
        decider_etape(utilisateur=profils["lea"], demande=demande, rang=1, approuver=True)
    assert e.value.code == CodeErreur.CONTROLE_BLOQUANT
    assert not DecisionEtape.objects.exists()  # rien n'a été signé
    # Un rejet reste possible : refuser n'est pas passer outre.
    decider_etape(
        utilisateur=profils["lea"], demande=demande, rang=1, approuver=False, motif="Bloqué"
    )


def test_apres_derogation_approuvee_le_circuit_avance(cir):
    (_, _, profils, _), _ = cir
    objet, evaluation = _avec_blocage(cir)
    demande = _ouvrir(cir, objet=objet)
    derogation = demander_derogation(
        utilisateur=profils["samir"], evaluation=evaluation, motif="Urgent",
        justificatif="NO-1", valide_du=D(2026, 6, 1), valide_jusquau=D(2026, 7, 1),
    )  # fmt: skip
    decider_derogation(
        utilisateur=profils["lea"], derogation=derogation, approuver=True, motif="ok"
    )
    decider_etape(utilisateur=profils["lea"], demande=demande, rang=1, approuver=True)
    assert demande.rang_courant == 2


# --- concurrence -----------------------------------------------------------------------------


def _signer_en_concurrence(org_id, user_id, demande_id, barriere):
    try:
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [str(org_id)])
        barriere.wait()
        decider_etape(
            utilisateur=Utilisateur.objects.get(pk=user_id),
            demande=DemandeValidation.objects.get(pk=demande_id),
            rang=1,
            approuver=True,
        )
        return "ok"
    except ErreurMetier as erreur:
        return erreur.code.value
    finally:
        connections.close_all()


def test_deux_signatures_concurrentes_de_la_meme_etape_une_seule_prend_effet(cir):
    (organisation, projet, profils, _), _ = cir
    seconde = _utilisateur(organisation, projet, "ines", ["consulter", "valider"])
    demande = _ouvrir(cir)
    barriere = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futurs = [
            pool.submit(_signer_en_concurrence, organisation.id, u.id, demande.pk, barriere)
            for u in (profils["lea"], seconde)
        ]
        issues = sorted(f.result() for f in futurs)
    assert issues == ["TRANSITION_INTERDITE", "ok"]
    assert DecisionEtape.objects.filter(demande=demande, rang=1).count() == 1
    demande.refresh_from_db()
    assert demande.rang_courant == 2
