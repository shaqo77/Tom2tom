# ruff: noqa: F811, E501
"""Le tableau de bord multi-projets : périmètre, filtres, devises, consolidation. Voir L10-T02.

Contrôles du plan : le total d'un indicateur consolidé égale exactement la somme de ses détails par
projet ; jamais deux devises dans un même chiffre sans le dire ; une consolidation sans taux le dit.
"""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from niveau1_socle.avances.services import justifier_avance, parametrer_delai, verser_avance
from niveau1_socle.budget.engagements import creer_engagement
from niveau1_socle.budget.services import ajouter_ligne, approuver_version, creer_version
from niveau1_socle.exercices.services import creer_exercice
from niveau1_socle.financements.services import creer_bailleur, creer_compte_bancaire
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau1_socle.referentiels.models import Taux, Tiers
from niveau4_reporting.tableau_de_bord import Filtres, consolider, perimetre, tableau_de_bord
from tests.outils import _compte, creer_piece
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import _accord, _activer, cadre  # noqa: F401
from tests.test_organisations_bd import _creer_projet
from tests.test_rapprochement_bancaire_bd import _ligne as _ligne_banque
from tests.test_tresorerie_bd import _scenario, banque  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
J = datetime.date
D = Decimal
JOUR = J(2026, 6, 30)
Utilisateur = get_user_model()


def _poser(organisation):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


def _droits(organisation, projet, profils, *, modele=None):
    """Donne sur `projet` les mêmes rôles que sur le projet du modèle (par défaut P1)."""
    for h in Habilitation.objects.filter(project_id=modele.id):
        Habilitation.objects.create(
            org_id=organisation.id, user_id=h.user_id, project_id=projet.id, role=h.role
        )


@pytest.fixture
def parc(banque):
    """P1 (accord DJF, scénario de trésorerie), P2 (accord EUR d'un autre bailleur, compte USD),
    P3 clos, P4 sans droit pour amina. Budgets, engagements et avances de P2 maîtrisés au centime."""
    organisation, p1, profils, designe, demande = banque
    _scenario(banque)
    dora, amina, bruno = profils["dora"], profils["amina"], profils["bruno"]
    bad = creer_bailleur(utilisateur=dora, code="BAD", nom="Banque africaine de développement")
    p2 = _creer_projet(organisation, "P2")
    p3 = _creer_projet(organisation, "P3", status="closed")
    p4 = _creer_projet(organisation, "P4")
    for projet in (p2, p3):
        _droits(organisation, projet, profils, modele=p1)
    creer_exercice(p2, 2026, utilisateur=None)
    # P2 : un accord EUR actif, un budget approuvé, un engagement, une charge, un compte USD, une avance.
    accord2 = _accord(p2, profils, bad, "A-EUR", devise="EUR", montant_initial="500000")
    _activer(accord2, profils)
    _poser(organisation)
    version = creer_version(utilisateur=amina, project_id=p2.id, type="initial")
    ajouter_ligne(version, utilisateur=amina, annee=2026, montant="20000", devise="DJF")
    approuver_version(version, utilisateur=bruno)
    creer_engagement(
        utilisateur=amina, project_id=p2.id, reference="ENG-P2", annee=2026, montant="3000"
    )
    creer_piece(
        organisation.id,
        2026,
        2,
        [{"compte": "6011", "debit": "1200"}, {"compte": "5211", "credit": "1200"}],
        project_id=p2.id,
    )
    _compte(organisation.id, "7061")
    usd = creer_compte_bancaire(
        utilisateur=dora,
        project_id=p2.id,
        code="CB-USD",
        type="operationnel",
        devise="USD",
        banque="B",
        numero="US-1",
    )
    _ligne_banque(organisation, p2, usd, 50, jour=10, mois=2)
    agent = Tiers.objects.create(org_id=organisation.id, code="AG", nature="personnel", nom="AG")
    parametrer_delai(utilisateur=dora, project_id=p2.id, jours=30, date_effet=J(2026, 1, 1))
    avance = verser_avance(
        utilisateur=amina,
        project_id=p2.id,
        tiers=agent,
        reference="AV-1",
        montant="100",
        date_versement=J(2026, 2, 1),
    )
    justifier_avance(
        avance,
        utilisateur=amina,
        type="depense",
        montant="40",
        date_justification=J(2026, 3, 1),
        reference="PJ",
    )
    return organisation, p1, p2, p3, p4, profils, bad


def _vue(parc, **champs):
    organisation, _, _, _, _, profils, _ = parc
    _poser(organisation)
    return tableau_de_bord(utilisateur=profils["amina"], jour=JOUR, filtres=Filtres(**champs))


def _codes(tdb):
    return [p.code for p in tdb.projets]


def test_le_perimetre_ne_contient_que_les_projets_consultables_et_actifs(parc):
    organisation, p1, p2, p3, p4, profils, _ = parc
    assert _codes(_vue(parc)) == ["P1", "P2"]  # P3 est clos ; P4 : amina n'a aucun droit
    assert _codes(_vue(parc, statut_projet=None)) == ["P1", "P2", "P3"]
    # Un filtre ne donne jamais un droit : P4 reste invisible même demandé par son identifiant.
    assert _codes(_vue(parc, projets=frozenset({p4.id, p2.id}), statut_projet=None)) == ["P2"]
    assert _codes(_vue(parc, projets=frozenset({p4.id}))) == []


def test_un_utilisateur_sans_habilitation_voit_un_tableau_vide(parc):
    organisation, _, _, _, _, _, _ = parc
    _poser(organisation)
    inconnu = Utilisateur.objects.create_user("zoe", password="x", org_id=organisation.id)
    tdb = tableau_de_bord(utilisateur=inconnu, jour=JOUR)
    assert tdb.projets == [] and all(not i.par_projet for i in tdb.indicateurs.values())


def test_un_utilisateur_n_a_que_les_projets_ou_il_a_consulter(parc):
    organisation, p1, p2, _, _, profils, _ = parc
    _poser(organisation)
    role = Role.objects.create(
        org_id=organisation.id, code="LECT", label={"fr": "l"}, operations=["consulter"]
    )
    lecteur = Utilisateur.objects.create_user("lea", password="x", org_id=organisation.id)
    Habilitation.objects.create(
        org_id=organisation.id, user_id=lecteur.id, project_id=p2.id, role=role
    )
    tdb = tableau_de_bord(utilisateur=lecteur, jour=JOUR)
    assert _codes(tdb) == ["P2"] and set(tdb.indicateurs["budget_approuve"].par_projet) == {p2.id}


def test_les_projets_actifs_portent_leurs_bailleurs_et_leur_statut_de_configuration(parc):
    tdb = _vue(parc)
    assert {p.code: p.bailleurs for p in tdb.projets} == {"P1": ["IDA"], "P2": ["BAD"]}
    assert {p.configuration for p in tdb.projets} == {"non_configure"}  # aucune exigence active
    assert _codes(_vue(parc, statut_configuration="configure")) == []
    assert _codes(_vue(parc, statut_configuration="non_configure")) == ["P1", "P2"]


def test_les_filtres_de_bailleur_d_accord_et_de_statut_d_accord(parc):
    organisation, p1, p2, _, _, profils, bad = parc
    assert _codes(_vue(parc, bailleur_id=bad.id)) == ["P2"]
    accord_p1 = p1.accords.first() if hasattr(p1, "accords") else None
    from niveau1_socle.financements.models import Accord

    a1 = Accord.objects.get(project_id=p1.id)
    assert _codes(_vue(parc, accord_id=a1.id)) == ["P1"]
    assert _codes(_vue(parc, statut_accord="suspendu")) == []
    assert _codes(_vue(parc, statut_accord="actif")) == ["P1", "P2"]
    assert accord_p1 is None or accord_p1


def test_les_financements_sont_ventiles_par_devise_et_jamais_additionnes(parc):
    tdb = _vue(parc)
    accordes = tdb.indicateurs["financements_accordes"]
    assert accordes.total == {"DJF": D("1000"), "EUR": D("500000")}  # deux devises, deux chiffres
    assert {p: m for p, m in accordes.par_projet.items() if m.get("EUR")} == {
        parc[2].id: {"EUR": D("500000")}
    }
    # Filtre de devise : on ne garde que cette devise.
    assert _vue(parc, devise="EUR").indicateurs["financements_accordes"].total == {
        "EUR": D("500000")
    }


def test_les_financements_recus_sont_les_encaissements_apparies_et_suivent_la_periode(parc):
    assert _vue(parc).indicateurs["financements_recus"].total == {
        "DJF": D("300")
    }  # l'avance AV-1 du scénario
    assert (
        _vue(parc, du=J(2026, 3, 1)).indicateurs["financements_recus"].total == {}
    )  # AV-1 date du 20/02
    assert _vue(parc, du=J(2026, 2, 1), au=J(2026, 2, 28)).indicateurs[
        "financements_recus"
    ].total == {"DJF": D("300")}


def test_budget_execution_et_taux_d_un_projet_au_centime(parc):
    organisation, p1, p2, _, _, _, _ = parc
    tdb = _vue(parc)
    p2_budget = tdb.indicateurs["budget_approuve"].par_projet[p2.id]
    assert p2_budget == {"DJF": D("20000")} == tdb.indicateurs["budget_initial"].par_projet[p2.id]
    assert tdb.indicateurs["execution_budget"].par_projet[p2.id] == {"DJF": D("20000")}
    assert tdb.indicateurs["execution_engage"].par_projet[p2.id] == {"DJF": D("3000")}
    assert tdb.indicateurs["execution_consomme"].par_projet[p2.id] == {"DJF": D("1200")}
    assert tdb.par_composante[""]["consomme"].par_projet[p2.id] == {
        "DJF": D("1200")
    }  # P2 n'a pas de composante
    assert tdb.taux_execution()["DJF"] is not None
    assert "tableau_de_bord.execution_recouvrement" in tdb.avertissements


def test_les_soldes_bancaires_sont_par_devise_comptable_et_releve(parc):
    tdb = _vue(parc)
    p2 = parc[2]
    assert tdb.indicateurs["soldes_comptables"].par_projet[p2.id] == {"USD": D("50")}
    assert (
        p2.id not in tdb.indicateurs["soldes_releves"].par_projet
    )  # pas de solde de relevé enregistré pour P2
    assert set(tdb.indicateurs["soldes_comptables"].total) == {"DJF", "USD"}


def test_engagements_ouverts_et_avances_non_justifiees(parc):
    tdb = _vue(parc)
    p2 = parc[2]
    assert tdb.indicateurs["engagements_ouverts"].par_projet[p2.id] == {"DJF": D("3000")}
    assert tdb.indicateurs["avances_non_justifiees"].par_projet[p2.id] == {
        "DJF": D("60")
    }  # 100 − 40 justifiés


def test_le_total_de_chaque_indicateur_est_la_somme_exacte_de_ses_details_par_projet(parc):
    """Le contrôle du plan, indicateur par indicateur ET recalculé indépendamment en SQL."""
    tdb = _vue(parc)
    for code, indicateur in tdb.indicateurs.items():
        for devise, total in indicateur.total.items():
            assert total == sum(
                (m[devise] for m in indicateur.par_projet.values() if devise in m), D(0)
            ), code
    with connection.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(montant - apure), 0) FROM budget_engagement WHERE status = 'ouvert' AND project_id = ANY(%s)",
            [[p.id for p in (parc[1], parc[2])]],
        )
        assert tdb.indicateurs["engagements_ouverts"].total == {"DJF": cur.fetchone()[0]}
        cur.execute(
            "SELECT COALESCE(SUM(montant_initial), 0) FROM financements_accord WHERE project_id = ANY(%s) AND status = 'actif' AND devise_id = 'EUR'",
            [[p.id for p in (parc[1], parc[2])]],
        )
        assert tdb.indicateurs["financements_accordes"].total["EUR"] == cur.fetchone()[0]


def test_la_consolidation_affiche_methode_date_et_taux_et_arrondit_par_projet(parc):
    organisation, p1, p2, _, _, _, _ = parc
    _poser(organisation)
    Taux.objects.create(
        org_id=organisation.id,
        devise_id="USD",
        date=J(2026, 6, 1),
        taux=D("177.5555"),
        type_taux="officiel",
    )
    Taux.objects.create(
        org_id=organisation.id,
        devise_id="USD",
        date=J(2026, 7, 1),
        taux=D("999"),
        type_taux="officiel",
    )  # futur : ignoré
    tdb = _vue(parc)
    indicateur = tdb.indicateurs["soldes_comptables"]
    c = consolider(indicateur, devise_reference="DJF", jour=JOUR)
    assert c.raison is None and c.taux == {"USD": (D("177.5555"), J(2026, 6, 1))}
    assert c.par_projet[p2.id] == D("8878")  # 8877,775 arrondi à la devise DJF (0 décimale)
    assert c.montant == sum(
        c.par_projet.values(), D(0)
    )  # exactement la somme des consolidations par projet
    assert "officiel" in c.methode and "2026-06-30" in c.methode and "DJF" in c.methode


def test_sans_taux_l_indicateur_n_est_pas_consolide_et_le_dit(parc):
    tdb = _vue(parc)
    c = consolider(tdb.indicateurs["financements_accordes"], devise_reference="DJF", jour=JOUR)
    assert c.montant is None and c.par_projet == {} and c.taux == {}
    assert "EUR" in c.raison and "2026-06-30" in c.raison
    inconnue = consolider(
        tdb.indicateurs["financements_accordes"], devise_reference="XXX", jour=JOUR
    )
    assert inconnue.montant is None and "XXX" in inconnue.raison


def test_une_devise_deja_en_reference_ne_demande_aucun_taux(parc):
    tdb = _vue(parc, devise="DJF")
    c = consolider(tdb.indicateurs["financements_accordes"], devise_reference="DJF", jour=JOUR)
    assert c.montant == D("1000") and c.taux == {}


def test_une_habilitation_sans_l_operation_consulter_ne_donne_aucun_projet(parc):
    organisation, _, p2, _, _, _, _ = parc
    _poser(organisation)
    role = Role.objects.create(
        org_id=organisation.id, code="SAISIE", label={"fr": "s"}, operations=["saisir"]
    )
    saisisseur = Utilisateur.objects.create_user("sam", password="x", org_id=organisation.id)
    Habilitation.objects.create(
        org_id=organisation.id, user_id=saisisseur.id, project_id=p2.id, role=role
    )
    assert perimetre(saisisseur, Filtres(), JOUR) == []
