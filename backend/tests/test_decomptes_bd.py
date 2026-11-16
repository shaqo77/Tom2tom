# ruff: noqa: F811, E501
"""Décomptes, apurement des engagements, paiements, soldes contractuels. Voir L9-T04.

Contrôle du plan : un engagement totalement apuré libère EXACTEMENT le disponible budgétaire
qu'il réservait, au centime.
"""

import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction
from rest_framework.exceptions import PermissionDenied

from core.erreurs import CodeErreur, ErreurMetier
from niveau1_socle.budget.engagements import apurer_engagement, creer_engagement
from niveau1_socle.budget.models import Engagement
from niveau1_socle.budget.services import (
    BudgetInvalide,
    ajouter_ligne,
    approuver_version,
    creer_version,
)
from niveau1_socle.budget.soldes import comparer_soldes, situation
from niveau1_socle.marches.avis import demander_avis, enregistrer_decision  # noqa: F401
from niveau1_socle.marches.contrats import ajouter_avenant, conclure_contrat
from niveau1_socle.marches.decomptes import (
    certifier_decompte,
    enregistrer_paiement,
    rejeter_decompte,
    situation_contrat,
    soumettre_decompte,
)
from niveau1_socle.marches.models import Decompte, Paiement
from niveau1_socle.marches.plan import avancer_ligne
from niveau1_socle.referentiels.models import Tiers
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_plan_passation_bd import _ligne, pas  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
J = datetime.date
D = Decimal
BUDGET = D("50000000.00")
ENGAGEMENT = D("1234567.89")


def _disponible(projet) -> Decimal:
    rangees = situation(projet.id)
    assert len(rangees) == 1
    r = rangees[0]
    return r.budget - r.engage - r.consomme


@pytest.fixture
def marche(pas):
    """Un budget approuvé de 50 000 000 DJF, un marché AON attribué, son contrat (USD) et son engagement."""
    organisation, projet, profils, plan = pas
    amina, bruno = profils["amina"], profils["bruno"]
    version = creer_version(utilisateur=amina, project_id=projet.id, type="initial")
    ajouter_ligne(
        version, utilisateur=amina, annee=2026, montant=str(BUDGET), devise=projet.base_currency
    )
    approuver_version(version, utilisateur=bruno)
    ligne = _ligne(pas, "M-001", "120000", "AON")
    ligne = avancer_ligne(utilisateur=amina, ligne=ligne, statut="lance", date_effet=J(2026, 3, 2))
    ligne = avancer_ligne(
        utilisateur=amina, ligne=ligne, statut="attribue", date_effet=J(2026, 5, 2)
    )
    tiers = Tiers.objects.create(org_id=organisation.id, code="F1", nature="fournisseur", nom="F1")
    contrat = conclure_contrat(
        utilisateur=amina, ligne=ligne, reference="C-001", tiers=tiers, objet="Véhicules",
        montant="118000.50", date_signature=J(2026, 6, 1), date_debut=J(2026, 6, 15), date_fin=J(2026, 12, 15),
    )  # fmt: skip
    engagement = creer_engagement(
        utilisateur=amina, project_id=projet.id, reference="ENG-1", annee=2026,
        montant=str(ENGAGEMENT), ligne_passation=ligne,
    )  # fmt: skip
    return organisation, projet, profils, contrat, engagement


def _soumettre(marche, brut="60000", avancement="40", retenue="0", jour=None):
    jour = jour or J(2026, 7, 1)
    _, _, profils, contrat, _ = marche
    return soumettre_decompte(
        utilisateur=profils["amina"], contrat=contrat, date_decompte=jour, montant_brut=brut,
        avancement_physique=avancement, retenue=retenue, facture_reference="F-001",
    )  # fmt: skip


def _certifier(marche, decompte, apure="700000.11", jour=None, **champs):
    jour = jour or J(2026, 7, 10)
    _, _, profils, _, engagement = marche
    return certifier_decompte(
        utilisateur=champs.pop("utilisateur", profils["bruno"]), decompte=decompte,
        engagement=champs.pop("engagement", engagement), date_certification=jour, montant_apure=apure, **champs,
    )  # fmt: skip


def test_un_engagement_totalement_apure_libere_exactement_le_disponible_qu_il_reservait(marche):
    """Le contrôle décisif de L9-T04, au centime, sur des montants à deux décimales."""
    _, projet, _, _, engagement = marche
    assert _disponible(projet) == BUDGET - ENGAGEMENT
    d1 = _certifier(marche, _soumettre(marche, "60000", "40"), apure="700000.11")
    assert _disponible(projet) == BUDGET - (ENGAGEMENT - D("700000.11"))
    engagement.refresh_from_db()
    assert engagement.apure == D("700000.11") and engagement.status == "ouvert"
    d2 = _certifier(
        marche,
        _soumettre(marche, "58000.50", "100", jour=J(2026, 8, 1)),
        apure="534567.78",
        jour=J(2026, 8, 10),
    )
    engagement.refresh_from_db()
    assert engagement.status == "solde" and engagement.apure == ENGAGEMENT
    assert D("700000.11") + D("534567.78") == ENGAGEMENT
    assert (
        _disponible(projet) == BUDGET
    )  # exactement le budget d'origine : rien n'est resté réservé
    assert comparer_soldes(projet.id) == []  # l'incrémental égale le recalcul complet
    assert (d1.numero, d2.numero) == (1, 2)


def test_un_decompte_se_soumet_numerote_sans_trou_sans_rien_apurer(marche):
    projet, _ = marche[1], None
    d1, d2 = _soumettre(marche), _soumettre(marche, "1000", "45", jour=J(2026, 7, 5))
    assert (d1.numero, d2.numero) == (1, 2) and d1.statut == "soumis"
    marche[4].refresh_from_db()
    assert marche[4].apure == 0
    assert _disponible(marche[1]) == BUDGET - ENGAGEMENT
    assert projet


def test_la_personne_qui_soumet_ne_certifie_pas_et_la_certification_exige_l_habilitation(marche):
    profils = marche[2]
    decompte = _soumettre(marche)
    with pytest.raises(PermissionDenied):  # amina saisit mais ne valide pas
        _certifier(marche, decompte, utilisateur=profils["amina"])
    soumis_par_bruno = soumettre_decompte(  # bruno valide ; il ne saisit pas, donc amina soumet
        utilisateur=profils["amina"], contrat=marche[3], date_decompte=J(2026, 7, 2), montant_brut="1000",
        avancement_physique="41",
    )  # fmt: skip
    assert soumis_par_bruno.numero == 2


def test_la_base_refuse_qu_un_decompte_soit_certifie_par_son_auteur(marche):
    profils = marche[2]
    decompte = _soumettre(marche)
    with pytest.raises(IntegrityError), transaction.atomic():
        Decompte.objects.filter(pk=decompte.pk).update(
            statut="certifie", decide_par=decompte.soumis_par, date_decision=J(2026, 7, 10),
            engagement=marche[4], montant_apure=D("1"),
        )  # fmt: skip
    assert profils


def test_une_certification_refusee_n_apure_rien(marche):
    projet = marche[1]
    decompte = _soumettre(marche, "60000")
    with pytest.raises(BudgetInvalide):  # plus que le reste de l'engagement
        _certifier(marche, decompte, apure="1234567.90")
    decompte.refresh_from_db()
    marche[4].refresh_from_db()
    assert decompte.statut == "soumis" and marche[4].apure == 0
    assert _disponible(projet) == BUDGET - ENGAGEMENT


def test_l_engagement_doit_etre_celui_du_marche_du_contrat(marche):
    organisation, projet, profils, _, _ = marche
    libre = creer_engagement(
        utilisateur=profils["amina"],
        project_id=projet.id,
        reference="ENG-LIBRE",
        annee=2026,
        montant="1000",
    )
    with pytest.raises(ErreurMetier):
        _certifier(marche, _soumettre(marche), engagement=libre, apure="500")
    assert organisation


def test_un_engagement_rattache_a_un_marche_ne_s_apure_pas_a_la_main(marche):
    with pytest.raises(BudgetInvalide) as e:
        apurer_engagement(marche[4], utilisateur=marche[2]["amina"], montant="10")
    assert "ENG-1" in str(e.value)


def test_en_devise_differente_le_montant_apure_est_donne_en_monnaie_du_projet(marche):
    with pytest.raises(ErreurMetier) as e:
        _certifier(marche, _soumettre(marche), apure=None)
    assert "USD" in str(e.value) and marche[1].base_currency in str(e.value)


def test_les_decomptes_certifies_ne_depassent_pas_le_montant_courant_du_contrat(marche):
    amina = marche[2]["amina"]
    _certifier(marche, _soumettre(marche, "100000", "80"), apure="500000")
    trop = _soumettre(marche, "18000.51", "90", jour=J(2026, 8, 1))  # 118 000,51 > 118 000,50
    with pytest.raises(ErreurMetier) as e:
        _certifier(marche, trop, apure="100", jour=J(2026, 8, 5))
    assert "118000.50" in str(e.value)
    ajouter_avenant(
        utilisateur=amina, contrat=marche[3], date_effet=J(2026, 8, 2), montant="119000",
        date_fin=J(2027, 1, 31), motif="Extension",
    )  # fmt: skip
    assert (
        _certifier(marche, trop, apure="100", jour=J(2026, 8, 5)).statut == "certifie"
    )  # le plafond suit l'avenant


def test_l_avancement_physique_cumule_ne_recule_pas(marche):
    _certifier(marche, _soumettre(marche, "1000", "50"), apure="1000")
    recule = _soumettre(marche, "1000", "49.99", jour=J(2026, 8, 1))
    with pytest.raises(ErreurMetier):
        _certifier(marche, recule, apure="1000", jour=J(2026, 8, 5))
    egal = _soumettre(marche, "1000", "50", jour=J(2026, 8, 2))
    assert _certifier(marche, egal, apure="1000", jour=J(2026, 8, 5)).statut == "certifie"


def test_un_rejet_est_motive_et_definitif_et_n_apure_rien(marche):
    profils = marche[2]
    decompte = _soumettre(marche)
    with pytest.raises(ErreurMetier):
        rejeter_decompte(
            utilisateur=profils["bruno"], decompte=decompte, date_decision=J(2026, 7, 5), motif=" "
        )
    rejete = rejeter_decompte(
        utilisateur=profils["bruno"],
        decompte=decompte,
        date_decision=J(2026, 7, 5),
        motif="Quantités non vérifiées",
    )
    assert rejete.statut == "rejete"
    with pytest.raises(ErreurMetier) as e:
        _certifier(marche, rejete, apure="1000")
    assert e.value.code == CodeErreur.TRANSITION_INTERDITE
    marche[4].refresh_from_db()
    assert marche[4].apure == 0
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        Decompte.objects.filter(pk=decompte.pk).update(statut="soumis", motif_rejet="")


def test_la_base_tient_la_numerotation_l_ajout_seul_et_le_plafond_des_decomptes(marche):
    contrat = marche[3]

    def direct(numero, brut="1000"):
        return Decompte.objects.create(
            org_id=contrat.org_id, contrat=contrat, project_id=contrat.project_id, numero=numero,
            date_decompte=J(2026, 7, 1), montant_brut=brut, retenue=0, avancement_physique=10,
            soumis_par=contrat.id,
        )  # fmt: skip

    with pytest.raises(IntegrityError), transaction.atomic():  # un trou
        direct(2)
    decompte = direct(1)
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017  (contenu figé)
        Decompte.objects.filter(pk=decompte.pk).update(montant_brut=D("5"))
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        Decompte.objects.filter(pk=decompte.pk).delete()
    gros = direct(2, "999999")
    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
    ):  # dépasserait le contrat, même hors service
        Decompte.objects.filter(pk=gros.pk).update(
            statut="certifie", decide_par=marche[2]["bruno"].id, date_decision=J(2026, 7, 10),
            engagement=marche[4], montant_apure=D("1"),
        )  # fmt: skip


def test_les_paiements_ne_depassent_pas_le_net_et_ne_concernent_que_les_decomptes_certifies(marche):
    amina = marche[2]["amina"]
    decompte = _soumettre(marche, "60000", "40", retenue="3000")
    with pytest.raises(ErreurMetier):  # pas encore certifié
        enregistrer_paiement(
            utilisateur=amina,
            decompte=decompte,
            reference="P1",
            date_paiement=J(2026, 7, 11),
            montant="100",
        )
    decompte = _certifier(marche, decompte, apure="700000.11")
    with pytest.raises(ErreurMetier):  # avant la certification
        enregistrer_paiement(
            utilisateur=amina,
            decompte=decompte,
            reference="P1",
            date_paiement=J(2026, 7, 9),
            montant="100",
        )
    enregistrer_paiement(
        utilisateur=amina,
        decompte=decompte,
        reference="P1",
        date_paiement=J(2026, 7, 11),
        montant="40000",
    )
    with pytest.raises(ErreurMetier) as e:  # net = 57 000 ; reste 17 000
        enregistrer_paiement(
            utilisateur=amina,
            decompte=decompte,
            reference="P2",
            date_paiement=J(2026, 7, 12),
            montant="17000.01",
        )
    assert "17000" in str(e.value)
    enregistrer_paiement(
        utilisateur=amina,
        decompte=decompte,
        reference="P2",
        date_paiement=J(2026, 7, 12),
        montant="17000",
    )
    with pytest.raises(ErreurMetier):
        enregistrer_paiement(
            utilisateur=amina,
            decompte=decompte,
            reference="P2",
            date_paiement=J(2026, 7, 13),
            montant="0.01",
        )


def test_la_base_refuse_un_paiement_hors_net_ou_sur_un_decompte_non_certifie(marche):
    contrat = marche[3]
    soumis = _soumettre(marche)
    with pytest.raises(IntegrityError), transaction.atomic():
        Paiement.objects.create(
            org_id=contrat.org_id, decompte=soumis, project_id=contrat.project_id, reference="X",
            date_paiement=J(2026, 8, 1), montant=1, enregistre_par=contrat.id,
        )  # fmt: skip
    certifie = _certifier(marche, soumis, apure="1000")
    with pytest.raises(IntegrityError), transaction.atomic():
        Paiement.objects.create(
            org_id=contrat.org_id, decompte=certifie, project_id=contrat.project_id, reference="Y",
            date_paiement=J(2026, 8, 1), montant=D("60000.01"), enregistre_par=contrat.id,
        )  # fmt: skip
    ok = Paiement.objects.create(
        org_id=contrat.org_id, decompte=certifie, project_id=contrat.project_id, reference="Z",
        date_paiement=J(2026, 8, 1), montant=D("60000"), enregistre_par=contrat.id,
    )  # fmt: skip
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        Paiement.objects.filter(pk=ok.pk).delete()


def test_les_soldes_contractuels_et_les_taux_d_execution(marche):
    amina = marche[2]["amina"]
    contrat = marche[3]
    vide = situation_contrat(utilisateur=amina, contrat=contrat)
    assert (vide.certifie, vide.taux_financier, vide.taux_physique) == (0, 0, 0)
    d1 = _certifier(marche, _soumettre(marche, "59000.25", "50", retenue="2950.01"), apure="600000")
    enregistrer_paiement(
        utilisateur=amina,
        decompte=d1,
        reference="P1",
        date_paiement=J(2026, 7, 15),
        montant="30000",
    )
    s = situation_contrat(utilisateur=amina, contrat=contrat)
    assert s.montant_courant == D("118000.50") and s.certifie == D("59000.25")
    assert s.solde_contractuel == D("59000.25")
    assert (
        s.net_certifie == D("56050.24")
        and s.paye == D("30000")
        and s.reste_a_payer == D("26050.24")
    )
    assert s.taux_financier == D("50.00") and s.taux_physique == D("50.00")
    # Un soumis ou rejeté ne compte pas.
    _soumettre(marche, "1000", "60", jour=J(2026, 8, 1))
    assert situation_contrat(utilisateur=amina, contrat=contrat) == s


def test_un_decompte_ne_precede_pas_le_contrat_et_ses_montants_sont_decimaux(marche):
    profils = marche[2]
    contrat = marche[3]
    with pytest.raises(ErreurMetier):
        _soumettre(marche, jour=J(2026, 6, 1))  # avant le début du contrat (15/06)
    for brut, avancement in (
        ("0", "10"),
        ("-5", "10"),
        ("100", "100.01"),
        (60000.5, "10"),
        ("abc", "10"),
    ):
        with pytest.raises(ErreurMetier):
            soumettre_decompte(
                utilisateur=profils["amina"], contrat=contrat, date_decompte=J(2026, 7, 1),
                montant_brut=brut, avancement_physique=avancement,
            )  # fmt: skip
    with pytest.raises(ErreurMetier):  # retenue supérieure au brut
        _soumettre(marche, "100", "10", retenue="100.01")
    assert connection.vendor == "postgresql"
    assert not Engagement.objects.filter(apure__gt=0).exists()


def test_a_devise_egale_le_montant_apure_est_le_montant_brut(marche):
    organisation, projet, profils, _, _ = marche
    amina, dora, bruno = profils["amina"], profils["dora"], profils["bruno"]
    from niveau1_socle.marches.plan import definir_methode

    definir_methode(
        utilisateur=dora, project_id=projet.id, code="LOC", label={"fr": "Locale", "en": "Local"},
        devise=projet.base_currency, seuil_min="0", valid_from=J(2026, 1, 1),
    )  # fmt: skip
    ligne = _ligne(
        (organisation, projet, profils, marche[3].ligne.plan),
        "M-LOC",
        "900000",
        "LOC",
        devise=projet.base_currency,
    )
    ligne = avancer_ligne(utilisateur=amina, ligne=ligne, statut="lance", date_effet=J(2026, 3, 2))
    ligne = avancer_ligne(
        utilisateur=amina, ligne=ligne, statut="attribue", date_effet=J(2026, 5, 2)
    )
    contrat = conclure_contrat(
        utilisateur=amina, ligne=ligne, reference="C-LOC", tiers=marche[3].tiers, objet="Local",
        montant="900000", date_signature=J(2026, 6, 1), date_debut=J(2026, 6, 15), date_fin=J(2026, 12, 15),
    )  # fmt: skip
    engagement = creer_engagement(
        utilisateur=amina,
        project_id=projet.id,
        reference="ENG-LOC",
        annee=2026,
        montant="900000",
        ligne_passation=ligne,
    )
    decompte = soumettre_decompte(
        utilisateur=amina,
        contrat=contrat,
        date_decompte=J(2026, 7, 1),
        montant_brut="250000.25",
        avancement_physique="30",
    )
    with pytest.raises(ErreurMetier):  # un montant différent n'a pas de sens à devise égale
        certifier_decompte(
            utilisateur=bruno,
            decompte=decompte,
            engagement=engagement,
            date_certification=J(2026, 7, 5),
            montant_apure="1",
        )
    certifie = certifier_decompte(
        utilisateur=bruno,
        decompte=decompte,
        engagement=engagement,
        date_certification=J(2026, 7, 5),
    )
    engagement.refresh_from_db()
    assert certifie.montant_apure == D("250000.25") and engagement.apure == D("250000.25")


def test_meme_habilite_a_saisir_et_valider_on_ne_certifie_pas_son_propre_decompte(marche):
    from django.contrib.auth import get_user_model

    from niveau1_socle.habilitations.models import Habilitation, Role

    organisation, projet, _, contrat, engagement = marche
    eva = get_user_model().objects.create_user("eva", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id,
        code="EVA",
        label={"fr": "e"},
        operations=["consulter", "saisir", "valider"],
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=eva.id, project_id=projet.id, role=role
    )
    decompte = soumettre_decompte(
        utilisateur=eva,
        contrat=contrat,
        date_decompte=J(2026, 7, 1),
        montant_brut="1000",
        avancement_physique="10",
    )
    with pytest.raises(ErreurMetier) as e:
        certifier_decompte(
            utilisateur=eva,
            decompte=decompte,
            engagement=engagement,
            date_certification=J(2026, 7, 5),
            montant_apure="1000",
        )
    assert "soumis" in str(e.value)
    engagement.refresh_from_db()
    assert engagement.apure == 0


def test_la_base_fige_un_decompte_decide_et_tient_l_avancement_hors_du_service(marche):
    certifie = _certifier(marche, _soumettre(marche, "1000", "50"), apure="1000")
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017  (même un champ de décision d'un décompte décidé)
        Decompte.objects.filter(pk=certifie.pk).update(motif_rejet="modifié après coup")
    recule = _soumettre(marche, "1000", "49", jour=J(2026, 8, 1))
    with pytest.raises(IntegrityError), transaction.atomic():
        Decompte.objects.filter(pk=recule.pk).update(
            statut="certifie", decide_par=marche[2]["bruno"].id, date_decision=J(2026, 8, 5),
            engagement=marche[4], montant_apure=D("1"),
        )  # fmt: skip
