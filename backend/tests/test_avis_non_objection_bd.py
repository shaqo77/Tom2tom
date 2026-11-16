# ruff: noqa: F811, E501
"""L'avis de non-objection : demande, pièces, décision, blocage de l'engagement. Voir L9-T02.

Contrôle du plan : un marché soumis à non-objection refuse l'engagement sans avis, et l'accepte
dès réception ; la règle tient aussi en base, pour qui contournerait le service.
"""

import datetime

import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied

from core.erreurs import CodeErreur, ErreurMetier
from niveau1_socle.budget.engagements import creer_engagement
from niveau1_socle.budget.models import Engagement
from niveau1_socle.budget.services import BudgetInvalide
from niveau1_socle.marches.avis import (
    PieceAvisAlteree,
    avis_en_attente,
    avis_suffisant,
    demander_avis,
    enregistrer_decision,
    joindre_piece,
    lire_piece,
)
from niveau1_socle.marches.models import AvisNonObjection, PieceAvis, StatutLigne
from niveau1_socle.marches.plan import avancer_ligne
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_plan_passation_bd import _ligne, pas  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
J = datetime.date


def _engager(pas, ligne, reference="ENG-1", **champs):
    _, projet, profils, _ = pas
    return creer_engagement(
        utilisateur=profils["amina"],
        project_id=projet.id,
        reference=reference,
        annee=2026,
        montant="1000",
        ligne_passation=ligne,
        **champs,
    )


def _grosse(pas, reference="M-900"):
    return _ligne(pas, reference, "900000", "AOI")  # AOI : avis de non-objection exigé


def test_un_marche_soumis_a_avis_refuse_l_engagement_sans_avis_et_l_accepte_des_reception(pas):
    amina = pas[2]["amina"]
    ligne = _grosse(pas)
    with pytest.raises(BudgetInvalide) as e:
        _engager(pas, ligne)
    assert "M-900" in str(e.value)
    assert not Engagement.objects.exists()
    avis = demander_avis(
        utilisateur=amina, ligne=ligne, objet="dossier", date_demande=J(2026, 3, 1)
    )
    with pytest.raises(BudgetInvalide):  # demandé n'est pas obtenu
        _engager(pas, ligne)
    enregistrer_decision(
        utilisateur=amina,
        avis=avis,
        statut="obtenu",
        date_decision=J(2026, 3, 20),
        reference_bailleur="BM-2026-117",
    )
    engagement = _engager(pas, ligne)
    assert engagement.ligne_passation_id == ligne.id
    assert Engagement.objects.count() == 1


def test_un_engagement_sans_marche_ou_sur_un_marche_non_soumis_reste_possible(pas):
    petite = _ligne(pas, "M-001", "10000", "COT")
    assert avis_suffisant(petite)
    assert _engager(pas, petite, "ENG-A").id
    assert _engager(pas, None, "ENG-B").ligne_passation_id is None


def test_un_refus_bloque_jusqu_a_une_nouvelle_demande_obtenue(pas):
    amina = pas[2]["amina"]
    ligne = _grosse(pas)
    refuse = demander_avis(
        utilisateur=amina, ligne=ligne, objet="dossier", date_demande=J(2026, 3, 1)
    )
    enregistrer_decision(
        utilisateur=amina,
        avis=refuse,
        statut="refuse",
        date_decision=J(2026, 3, 9),
        motif="Critères flous",
    )
    with pytest.raises(BudgetInvalide):
        _engager(pas, ligne)
    nouveau = demander_avis(
        utilisateur=amina, ligne=ligne, objet="dossier", date_demande=J(2026, 3, 15)
    )
    enregistrer_decision(
        utilisateur=amina, avis=nouveau, statut="obtenu", date_decision=J(2026, 3, 25)
    )
    assert _engager(pas, ligne).id
    refuse.refresh_from_db()
    assert refuse.statut == "refuse"  # le refus reste dans l'historique


def test_chaque_objet_demande_doit_etre_obtenu(pas):
    amina = pas[2]["amina"]
    ligne = _grosse(pas)
    dossier = demander_avis(
        utilisateur=amina, ligne=ligne, objet="dossier", date_demande=J(2026, 3, 1)
    )
    enregistrer_decision(
        utilisateur=amina, avis=dossier, statut="obtenu", date_decision=J(2026, 3, 5)
    )
    evaluation = demander_avis(
        utilisateur=amina, ligne=ligne, objet="evaluation", date_demande=J(2026, 5, 1)
    )
    with pytest.raises(BudgetInvalide) as e:
        _engager(pas, ligne)
    assert "evaluation" in str(e.value)
    enregistrer_decision(
        utilisateur=amina, avis=evaluation, statut="obtenu", date_decision=J(2026, 5, 9)
    )
    assert _engager(pas, ligne).id


def test_la_base_refuse_l_engagement_sans_avis_meme_hors_du_service(pas):
    _, projet, _, _ = pas
    ligne = _grosse(pas)
    with pytest.raises(IntegrityError), transaction.atomic():
        Engagement.objects.create(
            org_id=ligne.org_id,
            project_id=projet.id,
            reference="CONTOURNE",
            annee=2026,
            montant=1000,
            ligne_passation=ligne,
        )
    assert not Engagement.objects.exists()


def test_un_engagement_ne_se_rattache_ni_a_un_marche_annule_ni_apres_coup(pas):
    amina = pas[2]["amina"]
    libre = _engager(pas, None, "ENG-LIBRE")
    petite = _ligne(pas, "M-001", "10000", "COT")
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        Engagement.objects.filter(pk=libre.pk).update(ligne_passation=petite)
    annulee = avancer_ligne(
        utilisateur=amina, ligne=_ligne(pas, "M-002", "20000", "COT"), statut="annule",
        date_effet=J(2026, 3, 2), note="Abandonné",
    )  # fmt: skip
    assert annulee.statut == StatutLigne.ANNULE
    with pytest.raises(BudgetInvalide):
        _engager(pas, annulee, "ENG-X")


def test_une_decision_est_motivee_datee_et_definitive(pas):
    amina = pas[2]["amina"]
    ligne = _grosse(pas)
    avis = demander_avis(
        utilisateur=amina, ligne=ligne, objet="contrat", date_demande=J(2026, 6, 1)
    )
    with pytest.raises(ErreurMetier):  # un refus sans motif
        enregistrer_decision(
            utilisateur=amina, avis=avis, statut="refuse", date_decision=J(2026, 6, 2)
        )
    with pytest.raises(ErreurMetier):  # une décision avant la demande
        enregistrer_decision(
            utilisateur=amina, avis=avis, statut="obtenu", date_decision=J(2026, 5, 31)
        )
    with pytest.raises(ErreurMetier):  # « demandé » n'est pas une décision
        enregistrer_decision(
            utilisateur=amina, avis=avis, statut="demande", date_decision=J(2026, 6, 2)
        )
    avis = enregistrer_decision(
        utilisateur=amina, avis=avis, statut="obtenu", date_decision=J(2026, 6, 2)
    )
    with pytest.raises(ErreurMetier) as e:
        enregistrer_decision(
            utilisateur=amina, avis=avis, statut="refuse", date_decision=J(2026, 6, 3), motif="x"
        )
    assert e.value.code == CodeErreur.TRANSITION_INTERDITE
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017  (base : un avis décidé est figé)
        AvisNonObjection.objects.filter(pk=avis.pk).update(statut="refuse", motif="x")
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        AvisNonObjection.objects.filter(pk=avis.pk).delete()


def test_la_base_refuse_de_modifier_la_demande_d_un_avis_en_attente(pas):
    amina = pas[2]["amina"]
    avis = demander_avis(
        utilisateur=amina, ligne=_grosse(pas), objet="dossier", date_demande=J(2026, 3, 1)
    )
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        AvisNonObjection.objects.filter(pk=avis.pk).update(objet="avenant")


def test_on_ne_demande_pas_d_avis_pour_un_marche_non_soumis_ou_clos(pas):
    amina = pas[2]["amina"]
    petite = _ligne(pas, "M-001", "10000", "COT")
    with pytest.raises(ErreurMetier):
        demander_avis(utilisateur=amina, ligne=petite, objet="dossier", date_demande=J(2026, 3, 1))
    with pytest.raises(ErreurMetier):
        demander_avis(
            utilisateur=amina, ligne=_grosse(pas), objet="inconnu", date_demande=J(2026, 3, 1)
        )
    close = avancer_ligne(
        utilisateur=amina,
        ligne=_grosse(pas, "M-901"),
        statut="annule",
        date_effet=J(2026, 3, 2),
        note="x",
    )
    with pytest.raises(ErreurMetier):
        demander_avis(utilisateur=amina, ligne=close, objet="dossier", date_demande=J(2026, 3, 3))


def test_les_pieces_se_joignent_une_fois_et_se_relisent_sans_alteration(pas):
    amina = pas[2]["amina"]
    avis = demander_avis(
        utilisateur=amina, ligne=_grosse(pas), objet="dossier", date_demande=J(2026, 3, 1)
    )
    p1 = joindre_piece(
        utilisateur=amina, avis=avis, nature="demande", nom="lettre.pdf", contenu=b"%PDF lettre"
    )
    p2 = joindre_piece(
        utilisateur=amina, avis=avis, nature="demande", nom="lettre.pdf", contenu=b"%PDF lettre"
    )
    assert p1.id == p2.id and PieceAvis.objects.count() == 1
    assert lire_piece(p1) == b"%PDF lettre"
    with pytest.raises(ErreurMetier):
        joindre_piece(utilisateur=amina, avis=avis, nature="reponse", nom="vide", contenu=b"")
    with pytest.raises(ErreurMetier):
        joindre_piece(utilisateur=amina, avis=avis, nature="autre", nom="x", contenu=b"x")
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017  (ajout seul)
        PieceAvis.objects.filter(pk=p1.pk).delete()
    from niveau3_config import stockage

    stockage._chemin(p1.file_ref).write_bytes(b"altere")
    with pytest.raises(PieceAvisAlteree):
        lire_piece(p1)


def test_les_avis_en_attente_listent_les_plus_anciens_d_abord(pas):
    amina = pas[2]["amina"]
    a = _grosse(pas, "M-900")
    b = _grosse(pas, "M-901")
    recent = demander_avis(utilisateur=amina, ligne=a, objet="dossier", date_demande=J(2026, 6, 1))
    ancien = demander_avis(utilisateur=amina, ligne=b, objet="dossier", date_demande=J(2026, 4, 1))
    traites = demander_avis(
        utilisateur=amina, ligne=b, objet="evaluation", date_demande=J(2026, 4, 2)
    )
    enregistrer_decision(
        utilisateur=amina, avis=traites, statut="obtenu", date_decision=J(2026, 4, 3)
    )
    attente = avis_en_attente(utilisateur=amina, project_id=pas[1].id, jour=J(2026, 6, 11))
    assert [(x.id, jours) for x, jours in attente] == [(ancien.id, 71), (recent.id, 10)]


def test_les_habilitations_sont_exigees(pas):
    profils = pas[2]
    ligne = _grosse(pas)
    with pytest.raises(PermissionDenied):  # dora paramètre mais ne saisit pas
        demander_avis(
            utilisateur=profils["dora"], ligne=ligne, objet="dossier", date_demande=J(2026, 3, 1)
        )
    avis = demander_avis(
        utilisateur=profils["amina"], ligne=ligne, objet="dossier", date_demande=J(2026, 3, 1)
    )
    with pytest.raises(PermissionDenied):
        enregistrer_decision(
            utilisateur=profils["dora"], avis=avis, statut="obtenu", date_decision=J(2026, 3, 2)
        )


def _directement(pas, ligne, reference):
    """Un engagement créé sans passer par le service : seule la base le garde."""
    return Engagement.objects.create(
        org_id=ligne.org_id,
        project_id=pas[1].id,
        reference=reference,
        annee=2026,
        montant=1000,
        ligne_passation=ligne,
    )


def test_la_base_refuse_aussi_l_engagement_sur_un_marche_annule(pas):
    annulee = avancer_ligne(
        utilisateur=pas[2]["amina"],
        ligne=_ligne(pas, "M-002", "20000", "COT"),
        statut="annule",
        date_effet=J(2026, 3, 2),
        note="Abandonné",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        _directement(pas, annulee, "ENG-X")


def test_la_base_tient_l_ordre_des_avis_comme_le_service(pas):
    amina = pas[2]["amina"]
    ligne = _grosse(pas)
    premier = demander_avis(
        utilisateur=amina, ligne=ligne, objet="dossier", date_demande=J(2026, 3, 1)
    )
    enregistrer_decision(
        utilisateur=amina, avis=premier, statut="obtenu", date_decision=J(2026, 3, 5)
    )
    assert _directement(pas, ligne, "ENG-OK").id  # un avis obtenu suffit
    # Une nouvelle demande du même objet, postérieure et sans réponse, bloque à nouveau.
    demander_avis(utilisateur=amina, ligne=ligne, objet="dossier", date_demande=J(2026, 4, 1))
    with pytest.raises(IntegrityError), transaction.atomic():
        _directement(pas, ligne, "ENG-KO")
    with pytest.raises(BudgetInvalide):
        _engager(pas, ligne, "ENG-KO2")


def test_un_refus_non_repris_bloque_aussi_en_base(pas):
    amina = pas[2]["amina"]
    ligne = _grosse(pas)
    refuse = demander_avis(
        utilisateur=amina, ligne=ligne, objet="dossier", date_demande=J(2026, 3, 1)
    )
    enregistrer_decision(
        utilisateur=amina,
        avis=refuse,
        statut="refuse",
        date_decision=J(2026, 3, 9),
        motif="Critères flous",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        _directement(pas, ligne, "ENG-KO")
