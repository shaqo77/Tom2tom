"""Les tables du profil de décaissement : ensembles fermés et cohérence, tenus par la base.

« Ajouter une méthode est une migration, jamais un paramétrage client » : chaque ensemble fermé est
une contrainte CHECK, vérifiée ici en SQL direct, sans passer par l'application. Voir L5-T03bis.
"""

import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from niveau1_socle.financements.models import Accord
from niveau3_config.models import (
    MethodeDecaissement,
    ProfilDecaissement,
    RegleCompteDesigne,
    RegleFinancementCategorie,
)
from tests.outils import connexion_proprietaire
from tests.outils_profil import creer_profil
from tests.test_cycle_ecriture_bd import _creer_projet, _poser, decor  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
D = Decimal


@pytest.mark.parametrize(
    "champs, contrainte",
    [
        ({"regime": "mensuel"}, "profil_regime_ferme"),
        ({"valid_to": datetime.date(2025, 12, 31)}, "profil_dates_coherentes"),
        (
            {
                "eligibility_date": datetime.date(2026, 6, 1),
                "closing_date": datetime.date(2026, 5, 1),
            },
            "profil_jalons_1",
        ),
        (
            {
                "closing_date": datetime.date(2026, 5, 1),
                "disbursement_deadline": datetime.date(2026, 4, 1),
            },
            "profil_jalons_2",
        ),
        (
            {
                "effectiveness_date": datetime.date(2026, 6, 1),
                "eligibility_date": datetime.date(2026, 5, 1),
            },
            "profil_jalons_0",
        ),
        ({"statut": "validated"}, None),  # via creer_profil : validateur posé, donc accepté
    ],
)
def test_la_base_refuse_un_profil_incoherent(drf, champs, contrainte):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    if contrainte is None:
        assert creer_profil(organisation, projet, accord, **champs).status == "validated"
        return
    with pytest.raises(IntegrityError, match=contrainte), transaction.atomic():
        creer_profil(organisation, projet, accord, **champs)


def test_un_profil_valide_ou_actif_a_un_validateur_et_un_rejet_a_un_motif(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    base = {
        "org_id": organisation.id,
        "project_id": projet.id,
        "accord": accord,
        "valid_from": datetime.date(2026, 1, 1),
        "regime": "transaction_based",
    }
    for statut in ("validated", "active"):
        with (
            pytest.raises(IntegrityError, match="profil_validation_obligatoire"),
            transaction.atomic(),
        ):
            ProfilDecaissement.objects.create(version=10, status=statut, **base)
    with pytest.raises(IntegrityError, match="profil_rejet_motive"), transaction.atomic():
        ProfilDecaissement.objects.create(version=11, status="rejected", **base)
    rejete = ProfilDecaissement.objects.create(
        version=12, status="rejected", rejection_reason="Taux contraire à l'accord", **base
    )
    assert rejete.rejection_reason


def test_un_profil_et_son_accord_sont_du_meme_projet(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    autre = _creer_projet(organisation, "P2")
    with pytest.raises(IntegrityError, match="même projet"), transaction.atomic():
        ProfilDecaissement.objects.create(
            org_id=organisation.id,
            project_id=autre.id,
            accord=accord,
            version=1,
            valid_from=datetime.date(2026, 1, 1),
            regime="report_based",
        )


def test_le_numero_de_version_est_unique_par_accord(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    creer_profil(organisation, projet, accord, version=1)
    with pytest.raises(IntegrityError, match="uq_profil_version"), transaction.atomic():
        creer_profil(organisation, projet, accord, version=1)


# --- méthodes : ensembles fermés ------------------------------------------------------------


@pytest.mark.parametrize(
    "champs, contrainte",
    [
        ({"method": "cheque_en_blanc"}, "methode_ensemble_ferme"),
        (
            {"method": "advance", "supporting_docs": ["soe", "photo"]},
            "methode_pieces_ensemble_ferme",
        ),
        (
            {
                "method": "advance",
                "min_application_amount": D(10),
                "min_application_pct_of_ceiling": D("0.2"),
            },
            "methode_un_seul_minimum",
        ),
        ({"method": "advance", "min_application_amount": D(-1)}, "methode_minimum_positif"),
        (
            {"method": "advance", "min_application_pct_of_ceiling": D("1.1")},
            "methode_pourcentage_borne",
        ),
        ({"method": "advance", "full_doc_threshold": D(-5)}, "methode_seuil_documentation_positif"),
    ],
)
def test_la_base_refuse_une_methode_hors_des_ensembles_fermes(drf, champs, contrainte):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    profil = creer_profil(organisation, projet, accord, methodes=())
    donnees = {"supporting_docs": ["soe"]} | champs
    with pytest.raises(IntegrityError, match=contrainte), transaction.atomic():
        MethodeDecaissement.objects.create(org_id=organisation.id, profil=profil, **donnees)


def test_une_methode_n_apparait_qu_une_fois_par_profil_et_les_quatre_existent(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    profil = creer_profil(
        organisation,
        projet,
        accord,
        methodes=("advance", "reimbursement", "direct_payment", "special_commitment"),
    )
    assert profil.methodes.count() == 4
    with pytest.raises(IntegrityError, match="uq_methode_par_profil"), transaction.atomic():
        MethodeDecaissement.objects.create(
            org_id=organisation.id, profil=profil, method="advance", supporting_docs=["soe"]
        )


def test_les_quatre_pieces_exigees_sont_acceptees(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    profil = creer_profil(organisation, projet, accord, methodes=())
    methode = MethodeDecaissement.objects.create(
        org_id=organisation.id,
        profil=profil,
        method="advance",
        supporting_docs=["soe", "records", "ifr", "summary_sheet"],
    )
    assert len(methode.supporting_docs) == 4


# --- règles de financement et comptes désignés ----------------------------------------------


@pytest.mark.parametrize(
    "champs, contrainte",
    [
        ({"funding_rate": D(0)}, "regle_taux_dans_0_1"),
        ({"funding_rate": D("1.000001")}, "regle_taux_dans_0_1"),
        ({"tax_basis": "avec_la_tva"}, "regle_assiette_fermee"),
        ({"allocation": D(-1)}, "regle_allocation_positive"),
        (
            {
                "eligibility_from": datetime.date(2026, 6, 1),
                "eligibility_to": datetime.date(2026, 5, 1),
            },
            "regle_eligibilite_coherente",
        ),
        ({"max_per_contract": D(-1)}, "regle_plafond_contrat_positif"),
    ],
)
def test_la_base_refuse_une_regle_de_financement_incoherente(drf, champs, contrainte):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    profil = creer_profil(organisation, projet, accord)
    donnees = {"funding_rate": D(1), "allocation": D(100), "tax_basis": "taxes_included"} | champs
    with pytest.raises(IntegrityError, match=contrainte), transaction.atomic():
        RegleFinancementCategorie.objects.create(
            org_id=organisation.id, profil=profil, category=cat["serv"], **donnees
        )


def test_une_regle_vise_une_categorie_de_l_accord_du_profil(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    autre_accord = Accord.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        bailleur=accord.bailleur,
        numero="AUTRE",
        nature="don",
        devise_id="DJF",
        montant_initial=1,
    )
    from niveau1_socle.financements.models import Categorie

    categorie_etrangere = Categorie.objects.create(
        org_id=organisation.id, accord=autre_accord, code="X", label={"fr": "X"}, devise_id="DJF"
    )
    profil = creer_profil(organisation, projet, accord)
    with (
        pytest.raises(IntegrityError, match="catégorie d'une règle de financement appartient"),
        transaction.atomic(),
    ):
        RegleFinancementCategorie.objects.create(
            org_id=organisation.id,
            profil=profil,
            category=categorie_etrangere,
            allocation=D(1),
            funding_rate=D(1),
            tax_basis="taxes_included",
        )
    RegleFinancementCategorie.objects.create(  # une catégorie de l'accord : acceptée
        org_id=organisation.id,
        profil=profil,
        category=cat["serv"],
        allocation=D(1),
        funding_rate=D(1),
        tax_basis="taxes_included",
    )
    with pytest.raises(IntegrityError, match="uq_regle_categorie"), transaction.atomic():
        RegleFinancementCategorie.objects.create(
            org_id=organisation.id,
            profil=profil,
            category=cat["serv"],
            allocation=D(1),
            funding_rate=D(1),
            tax_basis="taxes_included",
        )


@pytest.mark.parametrize(
    "champs, contrainte",
    [
        (
            {"ceiling_kind": "illimite", "ceiling_amount": None},
            "regle_compte_plafond_ferme|regle_compte_plafond_coherent",
        ),  # deux contraintes la refusent
        ({"ceiling_kind": "fixed", "ceiling_amount": None}, "regle_compte_plafond_coherent"),
        ({"ceiling_kind": "variable", "ceiling_amount": D(10)}, "regle_compte_plafond_coherent"),
        ({"ceiling_kind": "fixed", "ceiling_amount": D(-1)}, "regle_compte_plafond_positif"),
        (
            {
                "ceiling_kind": "fixed",
                "ceiling_amount": D(10),
                "replenishment_threshold_pct": D("1.5"),
            },
            "regle_compte_seuil_borne",
        ),
    ],
)
def test_la_base_refuse_une_regle_de_compte_incoherente(drf, champs, contrainte):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    from niveau1_socle.financements.services import creer_compte_bancaire

    compte = creer_compte_bancaire(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code="CD",
        type="designe",
        devise="DJF",
        banque="B",
        numero="N-1",
        accord=accord,
    )
    profil = creer_profil(organisation, projet, accord)
    with pytest.raises(IntegrityError, match=contrainte), transaction.atomic():
        RegleCompteDesigne.objects.create(
            org_id=organisation.id, profil=profil, bank_account=compte, currency_id="DJF", **champs
        )


def test_un_compte_designe_est_du_meme_projet_et_sans_autre_accord(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    from niveau1_socle.financements.models import CompteBancaire

    autre_projet = _creer_projet(organisation, "P2")
    autre_accord = Accord.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        bailleur=accord.bailleur,
        numero="AUTRE",
        nature="don",
        devise_id="DJF",
        montant_initial=1,
    )
    profil = creer_profil(organisation, projet, accord)
    comptes = {
        "autre_projet": CompteBancaire.objects.create(
            org_id=organisation.id,
            project_id=autre_projet.id,
            code="C1",
            type="designe",
            devise_id="DJF",
            banque="B",
            numero="N-1",
        ),
        "autre_accord": CompteBancaire.objects.create(
            org_id=organisation.id,
            project_id=projet.id,
            accord=autre_accord,
            code="C2",
            type="designe",
            devise_id="DJF",
            banque="B",
            numero="N-2",
        ),
        "libre": CompteBancaire.objects.create(
            org_id=organisation.id,
            project_id=projet.id,
            code="C3",
            type="designe",
            devise_id="DJF",
            banque="B",
            numero="N-3",
        ),
    }
    for nom in ("autre_projet", "autre_accord"):
        with (
            pytest.raises(IntegrityError, match="compte désigné d'un profil est du même projet"),
            transaction.atomic(),
        ):
            RegleCompteDesigne.objects.create(
                org_id=organisation.id,
                profil=profil,
                bank_account=comptes[nom],
                currency_id="DJF",
                ceiling_kind="variable",
            )
    RegleCompteDesigne.objects.create(  # un compte du projet, sans accord propre : accepté
        org_id=organisation.id,
        profil=profil,
        bank_account=comptes["libre"],
        currency_id="DJF",
        ceiling_kind="variable",
    )


# --- isolation entre organisations ----------------------------------------------------------


def test_un_profil_ne_peut_viser_ni_l_accord_ni_le_projet_d_une_autre_organisation(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    autre = _creer_organisation("ORG-B")
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="fk_profil_accord_meme_org"):
            admin.execute(
                """INSERT INTO niveau3_config_profildecaissement (id, created_at, updated_at,
                       org_id, project_id, accord_id, version, valid_from, regime, status,
                       rejection_reason)
                   VALUES (gen_random_uuid(), now(), now(), %s, %s, %s, 1, '2026-01-01',
                           'report_based', 'draft', '')""",
                [autre.id, projet.id, accord.pk],
            )


def test_les_profils_sont_isoles_par_organisation(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    creer_profil(organisation, projet, accord, regles=[(cat["serv"], "1")])
    autre = _creer_organisation("ORG-B")
    _poser(autre)
    for modele in (
        ProfilDecaissement,
        MethodeDecaissement,
        RegleFinancementCategorie,
        RegleCompteDesigne,
    ):
        assert modele.objects.count() == 0, modele
