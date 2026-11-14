"""Le profil de décaissement dans les demandes de retrait. Voir L5-T03bis.

Contrôles du plan : trois projets du même bailleur coexistent avec des minimums différents ; un
changement de régime au 01/07 laisse inchangées les demandes du premier semestre ; une réallocation
qui change un taux ne recalcule aucune demande antérieure ; une dépense antérieure à la date
d'éligibilité est refusée en nommant la date ; une demande sous le minimum est bloquée en nommant le
seuil ; une dépense au-delà du seuil de documentation exige les copies de pièces.
"""

import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from niveau1_socle.decaissements.models import (
    DemandeRetrait,
    LigneDemande,
    SoldeAccord,
    SoldeCategorie,
)
from niveau1_socle.decaissements.services import (
    DemandeInvalide,
    DisponibleInsuffisant,
    soumettre_demande,
)
from niveau1_socle.exercices.services import creer_exercice
from niveau1_socle.financements.services import changer_statut_accord, creer_accord, creer_categorie
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau3_config.models import RegleFinancementCategorie
from niveau3_config.services.decaissement import ProfilViole
from tests.outils import connexion_proprietaire
from tests.outils_profil import creer_profil
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_demandes_retrait_bd import (  # noqa: F401
    DEBUT,
    FIN,
    _depense,
    _preparer,
    _soumettre,
    drf,
)
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
D = Decimal
JANV, JUIL = datetime.date(2026, 1, 1), datetime.date(2026, 7, 1)
JUIN = datetime.date(2026, 6, 15)


def _soumettre_avec(demande, profils, **champs):
    """Soumet en fournissant l'état certifié, que les profils de ces tests exigent par défaut."""
    champs.setdefault("pieces_fournies", ["soe"])
    return soumettre_demande(demande, utilisateur=profils["bruno"], **champs)


# --- calcul et persistance -----------------------------------------------------------------


def test_une_demande_sous_profil_demande_la_depense_fois_le_taux_et_persiste_la_regle(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    profil = creer_profil(
        organisation, projet, accord, regles=[(cat["serv"], "0.8"), (cat["biens"], "1")]
    )
    a = _depense(organisation, projet, accord, cat["serv"], 1001)
    demande = _preparer(profils, accord, [a], date_demande=JUIN)

    ligne = demande.lignes.get()
    assert (ligne.montant, ligne.montant_a_retirer, ligne.taux_applique) == (
        D(1001),
        D(800),
        D("0.8"),
    )  # 800,8 arrondi vers zéro
    assert ligne.regle_financement == profil.regles.get(category=cat["serv"])
    assert ligne.profil_version_id == profil.pk and demande.profil_version_id == profil.pk
    assert demande.montant_total == D(800)  # ce qui est demandé au bailleur


def test_les_soldes_et_les_plafonds_comptent_ce_qui_est_demande_au_bailleur(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    creer_profil(organisation, projet, accord, regles=[(cat["serv"], "0.5")])
    # Plafond de SERV : 300. Une dépense de 500 à 50 % demande 250 : elle passe.
    a = _depense(organisation, projet, accord, cat["serv"], 500)
    demande = _soumettre_avec(_preparer(profils, accord, [a], date_demande=JUIN), profils)
    assert SoldeCategorie.objects.get(categorie=cat["serv"]).utilise == D(250)
    assert SoldeAccord.objects.get().utilise == D(250)
    # Une seconde de 120 à 50 % : 60, soit 310 au total > 300 : refusée, avec ce qui est demandé.
    b = _depense(organisation, projet, accord, cat["serv"], 120, jour=11)
    with pytest.raises(DisponibleInsuffisant, match=r"plafond 300\.0000, déjà demandé 250\.0000"):
        _soumettre_avec(_preparer(profils, accord, [b], date_demande=JUIN), profils)
    assert demande.etat_certifie["total"] == "250.0000"
    assert demande.etat_certifie["total_depenses"] == "500.0000"
    ligne_certifiee = demande.etat_certifie["categories"][0]["lignes"][0]
    assert (ligne_certifiee["a_retirer"], ligne_certifiee["taux"]) == ("250.0000", "0.500000")


def test_une_sous_categorie_herite_du_taux_de_sa_categorie(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    creer_profil(organisation, projet, accord, regles=[(cat["biens"], "0.7")])
    a = _depense(organisation, projet, accord, cat["biens_a"], 1000)  # BIENS-A relève de BIENS
    ligne = _preparer(profils, accord, [a], date_demande=JUIN).lignes.get()
    assert ligne.montant_a_retirer == D(700) and ligne.taux_applique == D("0.7")


def test_la_regle_propre_a_la_sous_categorie_l_emporte(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    creer_profil(
        organisation, projet, accord, regles=[(cat["biens"], "0.7"), (cat["biens_a"], "0.9")]
    )
    a = _depense(organisation, projet, accord, cat["biens_a"], 1000)
    assert _preparer(profils, accord, [a], date_demande=JUIN).lignes.get().montant_a_retirer == D(
        900
    )


def test_une_categorie_sans_regle_est_refusee_quand_un_profil_est_en_vigueur(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    creer_profil(organisation, projet, accord, regles=[(cat["serv"], "0.8")])
    a = _depense(organisation, projet, accord, cat["biens"], 100)
    with pytest.raises(ProfilViole, match="La catégorie BIENS n'a pas de règle de financement"):
        _preparer(profils, accord, [a], date_demande=JUIN)
    assert DemandeRetrait.objects.count() == 0


# --- méthode, délai, profil en vigueur ------------------------------------------------------


def test_une_methode_non_autorisee_par_le_profil_est_refusee(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    creer_profil(
        organisation,
        projet,
        accord,
        methodes=[{"method": "reimbursement", "is_enabled": False}, "direct_payment"],
        regles=[(cat["serv"], "1")],
    )
    a = _depense(organisation, projet, accord, cat["serv"], 100)
    for type_ in ("reapprovisionnement", "retrait"):  # désactivée, puis absente du profil
        with pytest.raises(ProfilViole, match="n'est pas autorisée par le profil"):
            _preparer(profils, accord, [a], type=type_, date_demande=JUIN)
    assert _preparer(profils, accord, [a], type="paiement_direct", date_demande=JUIN).pk


def test_le_delai_de_decaissement_est_controle_a_la_preparation_et_a_la_soumission(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    creer_profil(
        organisation,
        projet,
        accord,
        regles=[(cat["serv"], "1")],
        disbursement_deadline=datetime.date(2026, 6, 30),
    )
    a = _depense(organisation, projet, accord, cat["serv"], 100)
    with pytest.raises(ProfilViole, match=r"date limite 2026-06-30, demande du 2026-07-01"):
        _preparer(profils, accord, [a], date_demande=JUIL)
    demande = _preparer(profils, accord, [a], date_demande=datetime.date(2026, 6, 30))
    with pytest.raises(ProfilViole, match="demande du 2026-07-02"):
        _soumettre_avec(demande, profils, date_soumission=datetime.date(2026, 7, 2))
    assert (
        _soumettre_avec(demande, profils, date_soumission=datetime.date(2026, 6, 30)).status
        == "soumise"
    )


def test_un_accord_dont_le_profil_a_expire_n_accepte_plus_de_demande(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    creer_profil(
        organisation,
        projet,
        accord,
        regles=[(cat["serv"], "1")],
        valid_to=datetime.date(2026, 6, 1),
    )
    a = _depense(organisation, projet, accord, cat["serv"], 100)
    with pytest.raises(ProfilViole, match="Aucun profil de décaissement n'est en vigueur"):
        _preparer(profils, accord, [a], date_demande=JUIN)
    assert _preparer(profils, accord, [a], date_demande=datetime.date(2026, 5, 31)).pk


def test_un_profil_brouillon_ou_rejete_n_est_pas_en_vigueur(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    creer_profil(organisation, projet, accord, statut="draft", regles=[(cat["serv"], "0.1")])
    a = _depense(organisation, projet, accord, cat["serv"], 1000)
    # Aucun profil n'a jamais été en vigueur : état antérieur à L5, la dépense est demandée entière.
    assert _preparer(profils, accord, [a], date_demande=JUIN).lignes.get().montant_a_retirer == D(
        1000
    )


# --- contrôles du plan ----------------------------------------------------------------------


def test_une_depense_anterieure_a_la_date_d_eligibilite_est_refusee_en_nommant_la_date(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    creer_profil(
        organisation,
        projet,
        accord,
        regles=[(cat["serv"], "1")],
        eligibility_date=datetime.date(2026, 2, 15),
    )
    avant = _depense(organisation, projet, accord, cat["serv"], 100, jour=14, mois=2)
    apres = _depense(organisation, projet, accord, cat["serv"], 100, jour=15, mois=2)
    with pytest.raises(
        ProfilViole,
        match=r"du 2026-02-14 est antérieure à la date d'éligibilité "
        r"du profil \(2026-02-15\)",
    ):
        _preparer(profils, accord, [avant], date_demande=JUIN)
    assert _preparer(profils, accord, [apres], date_demande=JUIN).pk


def test_une_demande_inferieure_au_minimum_est_bloquee_en_nommant_le_seuil(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    creer_profil(
        organisation,
        projet,
        accord,
        regles=[(cat["serv"], "0.5")],
        methodes=[{"method": "reimbursement", "min_application_amount": D(100)}],
    )
    petite = _depense(organisation, projet, accord, cat["serv"], 199)  # 99 à 50 %
    suffisante = _depense(organisation, projet, accord, cat["serv"], 200, jour=11)  # 100
    with pytest.raises(
        ProfilViole,
        match=r"La demande \(99\) est inférieure au minimum du profil : "
        r"montant minimum de 100",
    ):
        _preparer(profils, accord, [petite], date_demande=JUIN)
    assert _preparer(profils, accord, [suffisante], date_demande=JUIN).montant_total == D(100)


def test_le_minimum_en_pourcentage_du_plafond_du_compte_designe(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    from niveau1_socle.financements.services import creer_compte_bancaire

    compte = creer_compte_bancaire(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code="CD",
        type="designe",
        devise="DJF",
        banque="BCD",
        numero="N-1",
        accord=accord,
    )
    creer_profil(
        organisation,
        projet,
        accord,
        regles=[(cat["serv"], "1")],
        methodes=[{"method": "reimbursement", "min_application_pct_of_ceiling": D("0.2")}],
        comptes=[{"compte": compte, "plafond": D(1000)}],
    )
    petite = _depense(organisation, projet, accord, cat["serv"], 199)
    with pytest.raises(ProfilViole, match=r"20 % du plafond \(1000\.0000\), soit 200"):
        _preparer(profils, accord, [petite], date_demande=JUIN)
    assez = _depense(organisation, projet, accord, cat["serv"], 200, jour=11)
    assert _preparer(profils, accord, [assez], date_demande=JUIN).pk


def test_trois_projets_du_meme_bailleur_coexistent_avec_des_minimums_differents(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    bailleur = accord.bailleur
    resultats = {}
    for code, minimum in (
        ("P-20PCT", {"min_application_pct_of_ceiling": D("0.2")}),
        ("P-100K", {"min_application_amount": D(100_000)}),
        ("P-200K", {"min_application_amount": D(200_000)}),
    ):
        autre = _creer_projet(organisation, code)
        creer_exercice(autre, 2026, utilisateur=None)
        for nom in ("amina", "bruno", "dora"):
            Habilitation.objects.create(
                org_id=organisation.id,
                user_id=profils[nom].id,
                project_id=autre.id,
                role=Role.objects.get(code=nom.upper()),
            )
        acc = creer_accord(
            utilisateur=profils["dora"],
            project_id=autre.id,
            bailleur=bailleur,
            numero=f"IDA-{code}",
            nature="don",
            devise="DJF",
            montant_initial="5000000",
        )
        changer_statut_accord(acc, "actif", utilisateur=profils["dora"])
        categorie = creer_categorie(
            utilisateur=profils["dora"], accord=acc, code="BIENS", label={"fr": "Biens"}
        )
        from niveau1_socle.financements.services import creer_compte_bancaire

        compte = creer_compte_bancaire(
            utilisateur=profils["dora"],
            project_id=autre.id,
            code=f"CD-{code}",
            type="designe",
            devise="DJF",
            banque="BCD",
            numero=f"N-{code}",
            accord=acc,
        )
        creer_profil(
            organisation,
            autre,
            acc,
            regles=[(categorie, "1")],
            methodes=[{"method": "reimbursement", **minimum}],
            comptes=[{"compte": compte, "plafond": D(1_000_000)}],
        )  # 20 % = 200 000
        depense = _depense(organisation, autre, acc, categorie, 150_000)
        try:
            _preparer(profils, acc, [depense], date_demande=JUIN)
            resultats[code] = "acceptee"
        except ProfilViole as erreur:
            resultats[code] = str(erreur)
    # La même demande de 150 000 : acceptée là où le minimum est de 100 000, bloquée ailleurs, et
    # chaque refus nomme SON seuil. Les trois profils n'interfèrent pas.
    assert resultats["P-100K"] == "acceptee"
    assert "20 % du plafond (1000000.0000), soit 200000" in resultats["P-20PCT"]
    assert "montant minimum de 200000.0000" in resultats["P-200K"]


def test_une_depense_au_dela_du_seuil_exige_les_copies_de_pieces_et_non_l_etat_certifie(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    creer_profil(
        organisation,
        projet,
        accord,
        regles=[(cat["serv"], "1")],
        methodes=[
            {"method": "reimbursement", "supporting_docs": ["soe"], "full_doc_threshold": D(100)}
        ],
    )
    petite = _depense(organisation, projet, accord, cat["serv"], 100)
    grosse = _depense(organisation, projet, accord, cat["serv"], 101, jour=11)

    sous_le_seuil = _preparer(profils, accord, [petite], date_demande=JUIN)
    assert sous_le_seuil.pieces_exigees == ["soe"]
    assert _soumettre_avec(sous_le_seuil, profils, pieces_fournies=["soe"]).status == "soumise"

    au_dela = _preparer(profils, accord, [grosse], date_demande=JUIN)
    assert au_dela.pieces_exigees == ["records"]  # les copies, et non l'état certifié
    with pytest.raises(
        DemandeInvalide, match="Pièces exigées par le profil non fournies : copies des pièces"
    ):
        _soumettre_avec(au_dela, profils, pieces_fournies=["soe"])  # l'état certifié ne suffit pas
    assert _soumettre_avec(au_dela, profils, pieces_fournies=["records"]).pieces_fournies == [
        "records"
    ]


def test_la_base_refuse_une_soumission_sans_les_pieces_exigees(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    creer_profil(
        organisation,
        projet,
        accord,
        regles=[(cat["serv"], "1")],
        methodes=[{"method": "reimbursement", "supporting_docs": ["records", "ifr"]}],
    )
    a = _depense(organisation, projet, accord, cat["serv"], 100)
    demande = _preparer(profils, accord, [a], date_demande=JUIN)
    assert demande.pieces_exigees == ["ifr", "records"]
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="pièces exigées .* ne sont pas toutes fournies"):
            admin.execute(
                "UPDATE decaissements_demanderetrait SET status = 'soumise', "
                "etat_certifie = '{}'::jsonb, empreinte_etat = 'x' WHERE id = %s",
                [demande.pk],
            )


# --- versions : ce qui est figé -------------------------------------------------------------


def test_changer_de_regime_au_premier_juillet_laisse_inchangees_les_demandes_du_semestre(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    v1 = creer_profil(
        organisation,
        projet,
        accord,
        version=1,
        regime="transaction_based",
        valid_to=JUIL,
        regles=[(cat["serv"], "1")],
    )
    a = _depense(organisation, projet, accord, cat["serv"], 100, mois=3)
    d1 = _soumettre_avec(_preparer(profils, accord, [a], date_demande=JUIN), profils)
    assert d1.profil_version_id == v1.pk and d1.profil_version.regime == "transaction_based"

    v2 = creer_profil(
        organisation,
        projet,
        accord,
        version=2,
        regime="report_based",
        valid_from=JUIL,
        regles=[(cat["serv"], "1")],
    )
    b = _depense(organisation, projet, accord, cat["serv"], 100, mois=7, jour=20)
    d2 = _preparer(
        profils,
        accord,
        [b],
        date_demande=datetime.date(2026, 7, 21),
        periode_debut=JUIL,
        periode_fin=datetime.date(2026, 7, 31),
    )
    assert d2.profil_version_id == v2.pk and d2.profil_version.regime == "report_based"
    d1.refresh_from_db()
    assert d1.profil_version_id == v1.pk and d1.profil_version.regime == "transaction_based"


def test_une_reallocation_qui_change_un_taux_ne_recalcule_aucune_demande_anterieure(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    v1 = creer_profil(
        organisation, projet, accord, version=1, valid_to=JUIL, regles=[(cat["serv"], "1")]
    )
    a = _depense(organisation, projet, accord, cat["serv"], 100, mois=3)
    d1 = _soumettre_avec(_preparer(profils, accord, [a], date_demande=JUIN), profils)
    regle_v1 = d1.lignes.get().regle_financement
    assert d1.lignes.get().montant_a_retirer == D(100)

    v2 = creer_profil(
        organisation, projet, accord, version=2, valid_from=JUIL, regles=[(cat["serv"], "0.8")]
    )  # la réallocation passe le taux de 100 à 80 %
    b = _depense(organisation, projet, accord, cat["serv"], 100, mois=7, jour=20)
    d2 = _preparer(
        profils,
        accord,
        [b],
        date_demande=datetime.date(2026, 7, 21),
        periode_debut=JUIL,
        periode_fin=datetime.date(2026, 7, 31),
    )

    ligne1 = LigneDemande.objects.get(demande=d1)
    assert (ligne1.montant_a_retirer, ligne1.taux_applique) == (D(100), D(1))  # inchangée
    assert ligne1.regle_financement_id == regle_v1.pk == v1.regles.get().pk
    assert d1.montant_total == D(100) and d1.etat_certifie["total"] == "100.0000"
    assert d2.lignes.get().montant_a_retirer == D(80)
    assert d2.lignes.get().regle_financement_id == v2.regles.get().pk
    assert RegleFinancementCategorie.objects.get(pk=regle_v1.pk).funding_rate == D(1)


# --- la base garde les lignes ---------------------------------------------------------------


def test_la_base_refuse_une_ligne_incoherente_avec_la_regle_du_profil(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    v1 = creer_profil(
        organisation, projet, accord, version=1, valid_to=JUIL, regles=[(cat["serv"], "0.5")]
    )
    v2 = creer_profil(
        organisation, projet, accord, version=2, valid_from=JUIL, regles=[(cat["serv"], "0.9")]
    )
    a = _depense(organisation, projet, accord, cat["serv"], 1000)
    demande = DemandeRetrait.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        accord=accord,
        numero="DRF-T",
        type="retrait",
        periode_debut=DEBUT,
        periode_fin=FIN,
        profil_version=v1,
    )
    regle1, regle2 = v1.regles.get(), v2.regles.get()
    base = {
        "org_id": organisation.id,
        "demande": demande,
        "ligne_ecriture_id": a,
        "categorie": cat["serv"],
        "montant": D(1000),
        "date_piece": DEBUT,
    }
    cas = [
        ({"montant_a_retirer": D(500)}, "exige la règle de financement de chaque ligne"),
        (
            {
                "regle_financement": regle2,
                "profil_version": v1,
                "taux_applique": D("0.9"),
                "montant_a_retirer": D(500),
            },
            "règle de financement est celle du profil de la demande",
        ),
        (
            {
                "regle_financement": regle1,
                "profil_version": v1,
                "taux_applique": D("0.4"),
                "montant_a_retirer": D(400),
            },
            "Le taux appliqué est celui de la règle",
        ),
        (
            {
                "regle_financement": regle1,
                "profil_version": v1,
                "taux_applique": D("0.5"),
                "montant_a_retirer": D(501),
            },
            "dépasse dépense × taux",
        ),
        (
            {
                "regle_financement": regle1,
                "profil_version": v1,
                "taux_applique": D("0.5"),
                "montant_a_retirer": D(0),
            },
            "dépasse dépense × taux|lignedemande_retrait|<= 0",
        ),
    ]
    for champs, motif in cas:
        with pytest.raises(IntegrityError, match=motif), transaction.atomic():
            LigneDemande.objects.create(**base, **champs)
    LigneDemande.objects.create(  # la bonne ligne passe
        **base,
        regle_financement=regle1,
        profil_version=v1,
        taux_applique=D("0.5"),
        montant_a_retirer=D(500),
    )


def test_la_base_refuse_la_regle_d_une_autre_categorie(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    v1 = creer_profil(organisation, projet, accord, regles=[(cat["serv"], "0.5")])
    a = _depense(organisation, projet, accord, cat["biens"], 1000)
    demande = DemandeRetrait.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        accord=accord,
        numero="DRF-U",
        type="retrait",
        periode_debut=DEBUT,
        periode_fin=FIN,
        profil_version=v1,
    )
    with (
        pytest.raises(IntegrityError, match="catégorie de la ligne ou de son parent"),
        transaction.atomic(),
    ):
        LigneDemande.objects.create(
            org_id=organisation.id,
            demande=demande,
            ligne_ecriture_id=a,
            categorie=cat["biens"],
            montant=D(1000),
            montant_a_retirer=D(500),
            date_piece=DEBUT,
            regle_financement=v1.regles.get(),
            profil_version=v1,
            taux_applique=D("0.5"),
        )


def test_une_demande_ne_peut_viser_que_le_profil_de_son_accord(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    autre = _creer_projet(organisation, "P2")
    autre_accord = creer_accord.__globals__["Accord"].objects.create(
        org_id=organisation.id,
        project_id=autre.id,
        bailleur=accord.bailleur,
        numero="X",
        nature="don",
        devise_id="DJF",
        montant_initial=1,
    )
    profil_etranger = creer_profil(organisation, autre, autre_accord)
    with (
        pytest.raises(IntegrityError, match="profil d'une demande est celui de son accord"),
        transaction.atomic(),
    ):
        DemandeRetrait.objects.create(
            org_id=organisation.id,
            project_id=projet.id,
            accord=accord,
            numero="DRF-V",
            type="retrait",
            periode_debut=DEBUT,
            periode_fin=FIN,
            profil_version=profil_etranger,
        )


def test_sans_profil_la_base_fixe_le_montant_a_retirer_a_la_depense(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 123)
    ligne = _preparer(profils, accord, [a]).lignes.get()
    assert (ligne.montant_a_retirer, ligne.regle_financement_id, ligne.taux_applique) == (
        D(123),
        None,
        None,
    )
