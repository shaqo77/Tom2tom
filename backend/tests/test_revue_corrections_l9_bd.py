# ruff: noqa: F811, E501
"""Corrections de la revue de code du lot L9 : un test par constat, écrit pour échouer avant.

1. le journal d'`avancer_ligne` enregistrait le NOUVEAU statut comme ancien ;
2. un avenant pouvait fixer un montant sous les décomptes déjà certifiés ;
3. une ligne engagée ou sous contrat pouvait s'annuler ;
4. les prévisions « tous axes » et par axe se cumulaient dans la vue agrégée ;
5. le taux physique suivait le numéro du décompte, pas le maximum certifié ;
6. toute violation d'intégrité était lue comme « référence déjà existante » ;
7. les prévisions et le solde comptable se filtraient / s'additionnaient en Python ;
8. les alertes d'échéance : une requête par contrat, et alerte sur un contrat soldé ;
9. les mêmes helpers copiés dans cinq modules.
"""

import datetime
import re
from decimal import Decimal
from pathlib import Path

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext

from core.erreurs import CodeErreur, ErreurMetier
from core.models import AuditLog
from niveau1_socle.budget.engagements import annuler_engagement, creer_engagement
from niveau1_socle.marches.contrats import (
    ajouter_avenant,
    alertes_echeances,
)
from niveau1_socle.marches.decomptes import situation_contrat
from niveau1_socle.marches.models import AvenantContrat, LignePassation
from niveau1_socle.marches.plan import avancer_ligne
from niveau1_socle.tresorerie.services import (
    etablir_prevision,
    previsions,
    solde_comptable_a,
)
from tests.outils_paiement import ecriture_quelconque, payer  # noqa: F401
from tests.test_contrats_bd import _attribuer, _contrat
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_decomptes_bd import _certifier, _soumettre, marche  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_plan_passation_bd import _ligne, pas  # noqa: F401
from tests.test_rapprochement_bancaire_bd import _ligne as _ligne_banque  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
J = datetime.date
D = Decimal
DOSSIER = Path(__file__).parent.parent


def _cadre_plan(marche):
    organisation, projet, profils, contrat, _ = marche
    return organisation, projet, profils, contrat.ligne.plan


# --- 1. le journal d'avancer_ligne -------------------------------------------------------------


def test_le_journal_d_une_etape_garde_l_ancien_statut(pas):
    ligne = _ligne(pas, "M-001", "120000", "AON")
    amina = pas[2]["amina"]
    ligne = avancer_ligne(utilisateur=amina, ligne=ligne, statut="lance", date_effet=J(2026, 3, 2))
    avancer_ligne(utilisateur=amina, ligne=ligne, statut="attribue", date_effet=J(2026, 5, 2))
    transitions = [
        (e.before["statut"], e.after["statut"])
        for e in AuditLog.objects.filter(action="procurement_line_advanced").order_by("occurred_at")
    ]
    assert transitions == [("prevu", "lance"), ("lance", "attribue")]


# --- 2. un avenant ne passe pas sous le certifié ----------------------------------------------


def test_un_avenant_ne_fixe_pas_un_montant_sous_les_decomptes_deja_certifies(marche):
    amina = marche[2]["amina"]
    contrat = marche[3]
    _certifier(marche, _soumettre(marche, "100000", "80"), apure="500000")
    base = {
        "utilisateur": amina,
        "contrat": contrat,
        "date_effet": J(2026, 8, 1),
        "date_fin": J(2027, 1, 31),
    }
    with pytest.raises(ErreurMetier) as e:
        ajouter_avenant(**base, montant="99999.99", motif="Réduction")
    assert "100000" in str(e.value)
    assert ajouter_avenant(**base, montant="100000", motif="Réduction au certifié").numero == 1


def test_la_base_refuse_un_avenant_sous_le_certifie(marche):
    contrat = marche[3]
    _certifier(marche, _soumettre(marche, "100000", "80"), apure="500000")
    with pytest.raises(IntegrityError), transaction.atomic():
        AvenantContrat.objects.create(
            org_id=contrat.org_id, contrat=contrat, project_id=contrat.project_id, numero=1,
            date_effet=J(2026, 8, 1), montant=D("50000"), date_fin=J(2027, 1, 31), motif="x", cree_par=contrat.id,
        )  # fmt: skip


# --- 3. on n'annule pas une ligne engagée ou sous contrat -------------------------------------


def test_une_ligne_sous_contrat_ne_s_annule_pas(pas):
    ligne = _attribuer(pas, _ligne(pas, "M-001", "120000", "AON"))
    _contrat(pas, ligne=ligne)
    with pytest.raises(ErreurMetier) as e:
        avancer_ligne(
            utilisateur=pas[2]["amina"],
            ligne=ligne,
            statut="annule",
            date_effet=J(2026, 6, 1),
            note="x",
        )
    assert e.value.code == CodeErreur.TRANSITION_INTERDITE
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017  (la base aussi)
        LignePassation.objects.filter(pk=ligne.pk).update(statut="annule")


def test_une_ligne_avec_un_engagement_ouvert_ne_s_annule_qu_apres_l_annulation_de_l_engagement(pas):
    organisation, projet, profils, _ = pas
    amina = profils["amina"]
    ligne = _ligne(pas, "M-002", "20000", "COT")
    engagement = creer_engagement(
        utilisateur=amina,
        project_id=projet.id,
        reference="ENG-X",
        annee=2026,
        montant="100",
        ligne_passation=ligne,
    )
    with pytest.raises(ErreurMetier):
        avancer_ligne(
            utilisateur=amina,
            ligne=ligne,
            statut="annule",
            date_effet=J(2026, 6, 1),
            note="Abandon",
        )
    annuler_engagement(engagement, utilisateur=amina, motif="Marché abandonné")
    assert (
        avancer_ligne(
            utilisateur=amina,
            ligne=ligne,
            statut="annule",
            date_effet=J(2026, 6, 1),
            note="Abandon",
        ).statut
        == "annule"
    )


# --- 4. les prévisions tous axes et par axe ne se cumulent pas ---------------------------------


def test_la_vue_agregee_des_previsions_ne_compte_pas_deux_fois_tous_axes_et_axes(pas):
    from tests.outils import _valeur_axe

    organisation, projet, profils, _ = pas
    amina = profils["amina"]
    a, b = _valeur_axe(organisation.id, "COMP-A"), _valeur_axe(organisation.id, "COMP-B")
    base = {"utilisateur": amina, "project_id": projet.id, "devise": "DJF", "annee": 2026}
    etablir_prevision(**base, mois=4, encaissements="100")  # tous axes
    etablir_prevision(**base, mois=4, encaissements="60", axe=a)
    etablir_prevision(**base, mois=4, encaissements="40", axe=b)
    etablir_prevision(**base, mois=5, encaissements="30", axe=a)  # mai : seulement par axe
    etablir_prevision(**base, mois=5, encaissements="20", axe=b)
    agregees = previsions(
        utilisateur=amina, project_id=projet.id, annee=2026, mois=4, nombre_mois=2, par_axe=False
    )
    assert [(p.mois, p.encaissements) for p in agregees] == [(4, D("100")), (5, D("50"))]
    detail = previsions(
        utilisateur=amina, project_id=projet.id, annee=2026, mois=4, nombre_mois=1, par_axe=True
    )
    assert [(p.axe, p.encaissements) for p in detail] == [
        (None, D("100")),
        ("COMP-A", D("60")),
        ("COMP-B", D("40")),
    ]


# --- 5. le taux physique est le maximum certifié -----------------------------------------------


def test_le_taux_physique_est_le_maximum_certifie_pas_celui_du_dernier_numero(marche):
    amina = marche[2]["amina"]
    d1 = _soumettre(marche, "1000", "10", jour=J(2026, 7, 1))
    d2 = _soumettre(marche, "1000", "60", jour=J(2026, 7, 2))
    d3 = _soumettre(marche, "1000", "50", jour=J(2026, 7, 3))
    _certifier(marche, d3, apure="1000", jour=J(2026, 7, 10))
    _certifier(
        marche, d2, apure="1000", jour=J(2026, 7, 11)
    )  # 60 % ≥ max certifié (50 %) : accepté
    assert (d1.numero, d2.numero, d3.numero) == (1, 2, 3)
    assert situation_contrat(utilisateur=amina, contrat=marche[3]).taux_physique == D("60.00")


# --- 6. une violation d'intégrité n'est pas un doublon de référence ----------------------------


def test_un_second_contrat_sur_le_meme_marche_n_est_pas_presente_comme_un_doublon_de_reference(pas):
    ligne = _attribuer(pas, _ligne(pas, "M-001", "120000", "AON"))
    _contrat(pas, ligne=ligne, reference="C-001")
    with pytest.raises(ErreurMetier) as e:
        _contrat(pas, ligne=ligne, reference="C-NOUVEAU")
    assert "C-NOUVEAU" not in str(e.value) and "marché" in str(e.value)
    autre = _attribuer(pas, _ligne(pas, "M-003", "130000", "AON"))
    with pytest.raises(ErreurMetier) as e:
        _contrat(pas, ligne=autre, reference="C-001")
    assert "C-001" in str(e.value) and "référence" in str(e.value)


def test_une_violation_inconnue_garde_le_message_de_la_base():
    from core.metier import traduire_integrite

    erreur = traduire_integrite(
        IntegrityError("Les paiements dépasseraient le net\nCONTEXT: PL/pgSQL"), {}
    )
    assert "dépasseraient le net" in str(erreur) and "CONTEXT" not in str(erreur)
    connue = traduire_integrite(
        IntegrityError('duplicate key value violates unique constraint "uq_x"'),
        {"uq_x": ("metier.integrite_refusee", {"detail": "doublon connu"})},
    )
    assert "doublon connu" in str(connue)


# --- 7. agrégation en base ---------------------------------------------------------------------


def test_les_previsions_filtrent_la_fenetre_en_base_et_le_solde_comptable_s_agrege_en_base(
    marche, banque_compte
):
    organisation, projet, profils, _, _ = marche
    amina = profils["amina"]
    base = {"utilisateur": amina, "project_id": projet.id, "devise": "DJF", "annee": 2026}
    for mois in range(1, 13):
        etablir_prevision(**base, mois=mois, encaissements=str(mois))
    with CaptureQueriesContext(connection) as sql:
        lignes = previsions(
            utilisateur=amina, project_id=projet.id, annee=2026, mois=3, nombre_mois=2
        )
    assert [(p.mois, p.encaissements) for p in lignes] == [(3, D("3")), (4, D("4"))]
    requete = next(
        q["sql"] for q in sql.captured_queries if "tresorerie_previsiontresorerie" in q["sql"]
    )
    assert (
        "WHERE" in requete and '"mois"' in requete and "* 12" in requete
    )  # la fenêtre est dans la requête

    _ligne_banque(organisation, projet, banque_compte, 700, jour=10, mois=2)
    _ligne_banque(organisation, projet, banque_compte, -200, jour=12, mois=2)
    with CaptureQueriesContext(connection) as sql:
        assert solde_comptable_a(banque_compte, J(2026, 2, 28)) == D("500")
    assert any("SUM(" in q["sql"] for q in sql.captured_queries)


@pytest.fixture
def banque_compte(marche):
    from niveau1_socle.financements.services import creer_compte_bancaire

    _, projet, profils, _, _ = marche
    return creer_compte_bancaire(
        utilisateur=profils["dora"], project_id=projet.id, code="CB-DJF", type="operationnel",
        devise="DJF", banque="BCD", numero="DJ-777",
    )  # fmt: skip


# --- 8. alertes : peu de requêtes, pas de contrat soldé ---------------------------------------


def test_les_alertes_ne_font_pas_une_requete_par_contrat(marche):
    cadre = _cadre_plan(marche)
    amina = marche[2]["amina"]
    for i in range(5):
        ligne = _attribuer(cadre, _ligne(cadre, f"M-10{i}", "120000", "AON"))
        _contrat(cadre, ligne=ligne, reference=f"C-10{i}", montant="1000")
    with CaptureQueriesContext(connection) as sql:
        alertes = alertes_echeances(
            utilisateur=amina, project_id=marche[1].id, jour=J(2027, 1, 1), horizon_jours=0
        )
    assert len(alertes) == 6  # les cinq contrats, plus celui du marché de base
    assert len(sql.captured_queries) <= 8


def test_un_contrat_entierement_execute_et_paye_ne_donne_plus_d_alerte(marche):
    amina = marche[2]["amina"]
    contrat = marche[3]
    d1 = _certifier(marche, _soumettre(marche, "60000", "50"), apure="700000.11")
    d2 = _certifier(
        marche,
        _soumettre(marche, "58000.50", "100", jour=J(2026, 8, 1)),
        apure="534567.78",
        jour=J(2026, 8, 10),
    )
    jour = J(2027, 1, 5)  # la fin du contrat (15/12/2026) est dépassée
    assert [
        a.reference
        for a in alertes_echeances(
            utilisateur=amina, project_id=marche[1].id, jour=jour, horizon_jours=0
        )
    ] == ["C-001"]
    payer(marche, d1, "P1", J(2026, 7, 20), "60000")
    payer(marche, d2, "P2", J(2026, 8, 20), "57999")
    assert [
        a.reference
        for a in alertes_echeances(
            utilisateur=amina, project_id=marche[1].id, jour=jour, horizon_jours=0
        )
    ] == ["C-001"]  # reste 1,50 à payer
    payer(marche, d2, "P3", J(2026, 8, 21), "1.50")
    assert (
        alertes_echeances(utilisateur=amina, project_id=marche[1].id, jour=jour, horizon_jours=0)
        == []
    )
    assert contrat.reference == "C-001"


# --- 9. un seul jeu d'helpers ------------------------------------------------------------------


@pytest.mark.parametrize(
    "module",
    [
        "marches/plan",
        "marches/avis",
        "marches/contrats",
        "marches/decomptes",
        "tresorerie/services",
    ],
)
def test_les_helpers_metier_ne_sont_pas_recopies(module):
    source = (DOSSIER / "niveau1_socle" / f"{module}.py").read_text(encoding="utf-8")
    for nom in ("_habilite", "_refuser", "_montant", "_nombre", "_decimal"):
        assert not re.search(rf"^def {nom}\(", source, flags=re.MULTILINE), (
            f"{module} redéfinit {nom}"
        )
    assert "from core.metier import" in source


def test_la_base_refuse_d_annuler_une_ligne_qui_a_un_engagement_ouvert(pas):
    organisation, projet, profils, _ = pas
    ligne = _ligne(pas, "M-003", "20000", "COT")
    engagement = creer_engagement(
        utilisateur=profils["amina"], project_id=projet.id, reference="ENG-Y", annee=2026,
        montant="100", ligne_passation=ligne,
    )  # fmt: skip
    with pytest.raises(IntegrityError), transaction.atomic():
        LignePassation.objects.filter(pk=ligne.pk).update(statut="annule")
    annuler_engagement(engagement, utilisateur=profils["amina"], motif="Abandon")
    with transaction.atomic():  # l'engagement n'est plus ouvert : la base laisse passer
        LignePassation.objects.filter(pk=ligne.pk).update(statut="annule")
    assert LignePassation.objects.get(pk=ligne.pk).statut == "annule"
