"""Demandes de retrait de fonds et atelier DRF. Voir L4-T06.

Contrôles : une dépense déjà justifiée dans une demande antérieure ne peut pas être sélectionnée
une seconde fois ; dix soumissions simultanées sur un disponible qui n'en autorise que trois :
exactement trois acceptées, solde final exact au centime.
"""

import datetime
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from niveau1_socle.comptabilite.models import Ecriture, Journal, LigneEcriture
from niveau1_socle.decaissements.models import (
    DemandeRetrait,
    LigneDemande,
    MiseAEcart,
    SoldeAccord,
    SoldeCategorie,
)
from niveau1_socle.decaissements.services import (
    DemandeInvalide,
    DepenseNonSelectionnable,
    DeviseNonSupportee,
    DisponibleInsuffisant,
    accepter_demande,
    annuler_demande,
    contester_demande,
    depenses_eligibles,
    preparer_demande,
    rejeter_demande,
    rembourser_demande,
    soumettre_demande,
    verifier_disponible,
)
from niveau1_socle.exercices.models import Exercice
from niveau1_socle.exercices.services import TransitionInterdite
from niveau1_socle.financements.services import (
    AccordNonActif,
    changer_statut_accord,
    creer_avenant,
    creer_categorie,
)
from tests.outils import _compte, connexion_proprietaire
from tests.test_cycle_ecriture_bd import _poser, decor  # noqa: F401
from tests.test_financements_bd import _accord, _activer, _document, cadre  # noqa: F401
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = Decimal
DEBUT, FIN = datetime.date(2026, 1, 1), datetime.date(2026, 3, 31)


@pytest.fixture
def drf(cadre):  # noqa: F811
    """Un accord actif de 1 000 (DJF), des catégories (BIENS 600 > BIENS-A 400 ; SERV 300), et des
    dépenses comptabilisées. amina prépare, bruno soumet (valide), claire comptabilise."""
    organisation, projet, profils, bailleur = cadre
    accord = _activer(
        _accord(projet, profils, bailleur, "DON-1", devise="DJF", montant_initial="1000"), profils
    )
    dora = profils["dora"]
    biens = creer_categorie(
        utilisateur=dora, accord=accord, code="BIENS", label={"fr": "Biens"}, plafond="600"
    )
    biens_a = creer_categorie(
        utilisateur=dora,
        accord=accord,
        code="BIENS-A",
        label={"fr": "Biens A"},
        plafond="400",
        parent=biens,
    )
    serv = creer_categorie(
        utilisateur=dora, accord=accord, code="SERV", label={"fr": "Services"}, plafond="300"
    )
    _compte(organisation.id, "6021")
    _compte(organisation.id, "7061")
    return organisation, projet, profils, accord, {"biens": biens, "biens_a": biens_a, "serv": serv}


def _depense(
    organisation,
    projet,
    accord,
    categorie,
    montant,
    *,
    jour=10,
    mois=2,
    compte="6011",
    statut="posted",
    agreement=True,
):
    """Une charge comptabilisée imputée à l'accord et à la catégorie ; retourne l'id de sa ligne."""
    with transaction.atomic():
        exercice = Exercice.objects.get(project_id=projet.id, annee=2026)
        periode = exercice.periodes.get(numero=mois)
        journal, _ = Journal.objects.get_or_create(
            org_id=organisation.id, code="OD", defaults={"label": {"fr": "OD"}}
        )
        ecriture = Ecriture.objects.create(
            org_id=organisation.id,
            project_id=projet.id,
            exercice=exercice,
            periode=periode,
            journal=journal,
            accounting_date=datetime.date(2026, mois, jour),
            label="Dépense",
            status="draft",
            currency_id="DJF",
            fx_rate=D(1),
            origin="saisie",
        )
        commun = {
            "org_id": organisation.id,
            "project_id": projet.id,
            "entry": ecriture,
            "currency_id": "DJF",
            "fx_rate": D(1),
        }
        charge = LigneEcriture.objects.create(
            line_no=1,
            account=_compte(organisation.id, compte),
            debit=D(montant),
            credit=D(0),
            agreement_id=accord.pk if agreement else None,
            category_id=categorie.pk if categorie else None,
            **commun,
        )
        LigneEcriture.objects.create(
            line_no=2,
            account=_compte(organisation.id, "5211"),
            debit=D(0),
            credit=D(montant),
            **commun,
        )
        if statut != "draft":
            Ecriture.objects.filter(pk=ecriture.pk).update(
                status="posted", posted_at=timezone.now(), posted_by=uuid.uuid4()
            )
    return charge.pk


def _preparer(profils, accord, lignes, **champs):
    donnees = {
        "utilisateur": profils["amina"],
        "accord": accord,
        "type": "reapprovisionnement",
        "periode_debut": DEBUT,
        "periode_fin": FIN,
        "lignes": lignes,
    } | champs
    return preparer_demande(**donnees)


def _soumettre(demande, profils, **champs):
    return soumettre_demande(demande, utilisateur=profils["bruno"], **champs)


def _utilise(categorie):
    solde = SoldeCategorie.objects.filter(categorie=categorie).first()
    return solde.utilise if solde else D(0)


# --- l'atelier -----------------------------------------------------------------------------


def test_l_atelier_liste_les_depenses_eligibles_avec_leur_piece(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["biens_a"], 100, jour=5)
    b = _depense(organisation, projet, accord, cat["serv"], 50, jour=6)
    _depense(organisation, projet, accord, cat["serv"], 70, mois=6)  # hors période
    _depense(organisation, projet, accord, cat["serv"], 80, statut="draft")  # non comptabilisée
    _depense(organisation, projet, accord, cat["serv"], 90, agreement=False)  # autre imputation
    _depense(organisation, projet, accord, cat["serv"], 10, compte="7061")  # produit
    sans = _depense(organisation, projet, accord, None, 20)  # sans catégorie

    atelier = depenses_eligibles(accord, DEBUT, FIN)
    assert [d.ligne_id for d in atelier.selectionnables] == [a, b]
    assert all(d.piece.startswith("OD-2026-") for d in atelier.selectionnables)
    assert atelier.total_selectionnable == D(150)
    assert [(d.ligne_id, str(raison)) for d, raison in atelier.non_selectionnables] == [
        (sans, "sans catégorie de dépenses")
    ]


def test_preparer_une_demande_ecarte_avec_motif_et_verifie_le_disponible(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["biens_a"], 100)
    b = _depense(organisation, projet, accord, cat["serv"], 50)
    c = _depense(organisation, projet, accord, cat["serv"], 30)

    demande = _preparer(profils, accord, [a, b], ecarts={c: "Justificatif illisible"})
    assert (demande.status, demande.montant_total, demande.numero) == (
        "preparee",
        D(150),
        "DRF-DON-1-001",
    )
    assert {ligne.ligne_ecriture_id for ligne in demande.lignes.all()} == {a, b}
    ecart = MiseAEcart.objects.get()
    assert (ecart.ligne_ecriture_id, ecart.motif, ecart.created_by) == (
        c,
        "Justificatif illisible",
        profils["amina"].id,
    )
    # L'écart n'est pas une justification : la dépense reste libre pour une demande ultérieure.
    assert [d.ligne_id for d in depenses_eligibles(accord, DEBUT, FIN).selectionnables] == [c]

    rapport = {
        v.cible: v
        for v in verifier_disponible(accord, depenses_eligibles(accord, DEBUT, FIN).selectionnables)
    }
    assert rapport["accord"].disponible == D(1000) and rapport["accord"].conforme
    assert rapport["catégorie SERV"].demande == D(30)


@pytest.mark.parametrize("motif_vide, message", [({}, "motif"), ({"x": "  "}, "motif")])
def test_ecarter_une_depense_exige_un_motif(drf, motif_vide, message):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    b = _depense(organisation, projet, accord, cat["serv"], 30)
    with pytest.raises(DemandeInvalide, match="motif"):
        _preparer(profils, accord, [a], ecarts={b: "  "})
    assert DemandeRetrait.objects.count() == 0


def test_une_demande_est_refusee_si_ses_choix_sont_incoherents(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    with pytest.raises(DemandeInvalide, match="au moins une dépense"):
        _preparer(profils, accord, [])
    with pytest.raises(DemandeInvalide, match="à la fois choisie et écartée"):
        _preparer(profils, accord, [a], ecarts={a: "x"})
    with pytest.raises(DepenseNonSelectionnable, match="hors période"):
        _preparer(
            profils,
            accord,
            [a],
            periode_debut=datetime.date(2026, 5, 1),
            periode_fin=datetime.date(2026, 5, 31),
        )
    with pytest.raises(DemandeInvalide, match="type"):
        _preparer(profils, accord, [a], type="don")
    with pytest.raises(PermissionDenied):
        _preparer(profils, accord, [a], utilisateur=profils["claire"])
    assert DemandeRetrait.objects.count() == 0


def test_un_accord_dans_une_autre_devise_est_refuse_sans_conversion(drf):
    organisation, projet, profils, accord, cat = drf
    usd = _activer(_accord(projet, profils, accord.bailleur, "USD-1", devise="USD"), profils)
    with pytest.raises(DeviseNonSupportee, match="USD"):
        _preparer(profils, usd, [uuid.uuid4()])


# --- le contrôle de la tâche : une dépense, une seule demande -------------------------------


def test_une_depense_deja_justifiee_ne_peut_pas_etre_selectionnee_une_seconde_fois(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    b = _depense(organisation, projet, accord, cat["serv"], 60)
    premiere = _preparer(profils, accord, [a])

    # Préparée : la dépense est déjà retenue ; soumise puis acceptée : elle reste justifiée.
    for etape in ("preparee", "soumise", "acceptee"):
        if etape == "soumise":
            _soumettre(premiere, profils)
        if etape == "acceptee":
            accepter_demande(premiere, utilisateur=profils["bruno"])
        atelier = depenses_eligibles(accord, DEBUT, FIN)
        assert [d.ligne_id for d in atelier.selectionnables] == [b], etape
        assert [(d.ligne_id, str(r)) for d, r in atelier.non_selectionnables] == [
            (a, "déjà justifiée par une demande en cours")
        ]
        with pytest.raises(DepenseNonSelectionnable, match="déjà justifiée"):
            _preparer(profils, accord, [a, b])
    assert DemandeRetrait.objects.count() == 1


def test_la_base_refuse_la_meme_depense_dans_deux_demandes_en_cours(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    premiere = _preparer(profils, accord, [a])
    # Une seconde demande préparée « à la main » (contourne l'atelier) : la base refuse.
    seconde = DemandeRetrait.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        accord=accord,
        numero="DRF-X",
        type="retrait",
        periode_debut=DEBUT,
        periode_fin=FIN,
    )
    with (
        pytest.raises(IntegrityError, match="uq_lignedemande_une_demande_en_cours"),
        transaction.atomic(),
    ):
        LigneDemande.objects.create(
            org_id=organisation.id,
            demande=seconde,
            ligne_ecriture_id=a,
            categorie=cat["serv"],
            montant=D(50),
            date_piece=DEBUT,
        )
    assert premiere.lignes.count() == 1


def test_annuler_une_demande_preparee_libere_ses_depenses(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    demande = _preparer(profils, accord, [a])
    with pytest.raises(DemandeInvalide, match="motif"):
        annuler_demande(demande, utilisateur=profils["amina"], motif=" ")
    annuler_demande(demande, utilisateur=profils["amina"], motif="Préparée par erreur")
    assert demande.status == "annulee"
    assert [d.ligne_id for d in depenses_eligibles(accord, DEBUT, FIN).selectionnables] == [a]
    assert _preparer(profils, accord, [a]).numero == "DRF-DON-1-002"  # libre, sans reprise
    with pytest.raises(TransitionInterdite):
        annuler_demande(demande, utilisateur=profils["amina"], motif="Encore")


# --- rejets, reprise, litiges ---------------------------------------------------------------


def test_une_depense_rejetee_ne_revient_que_par_la_reprise_de_la_demande_rejetee(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    d1 = _soumettre(_preparer(profils, accord, [a]), profils)
    with pytest.raises(DemandeInvalide, match="motif"):
        rejeter_demande(d1, utilisateur=profils["bruno"], motif="")
    rejeter_demande(d1, utilisateur=profils["bruno"], motif="Pièce non conforme")
    assert (d1.status, d1.motif_rejet) == ("rejetee", "Pièce non conforme")
    assert LigneDemande.objects.get().etat == "rejete"

    # Sans lien de reprise : refusée, avec la raison exacte.
    atelier = depenses_eligibles(accord, DEBUT, FIN)
    assert atelier.selectionnables == [] and "rejetée" in str(atelier.non_selectionnables[0][1])
    with pytest.raises(DepenseNonSelectionnable, match="rejetée"):
        _preparer(profils, accord, [a])
    # Avec la reprise : acceptée. La régularisation est une opération NOUVELLE.
    d2 = _preparer(profils, accord, [a], reprise_de=d1)
    assert d2.reprise_de_id == d1.pk and d2.pk != d1.pk and d1.status == "rejetee"
    assert d2.montant_total == D(50)
    # La demande d'origine n'a pas été modifiée.
    d1.refresh_from_db()
    assert (d1.status, d1.montant_total) == ("rejetee", D(50))


def test_la_base_refuse_une_depense_rejetee_hors_reprise_meme_si_l_atelier_est_contourne(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    rejetee = rejeter_demande(
        _soumettre(_preparer(profils, accord, [a]), profils),
        utilisateur=profils["bruno"],
        motif="Non",
    )
    nouvelle = DemandeRetrait.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        accord=accord,
        numero="DRF-W",
        type="retrait",
        periode_debut=DEBUT,
        periode_fin=FIN,
    )
    base = {
        "org_id": organisation.id,
        "ligne_ecriture_id": a,
        "categorie": cat["serv"],
        "montant": D(50),
        "date_piece": DEBUT,
    }
    with (
        pytest.raises(IntegrityError, match="ne revient que par une demande qui reprend"),
        transaction.atomic(),
    ):
        LigneDemande.objects.create(demande=nouvelle, **base)  # sans lien de reprise : refusé
    reprise = DemandeRetrait.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        accord=accord,
        numero="DRF-V",
        type="retrait",
        periode_debut=DEBUT,
        periode_fin=FIN,
        reprise_de=rejetee,
    )
    LigneDemande.objects.create(demande=reprise, **base)  # avec le lien : accepté


def test_on_ne_represente_qu_une_demande_rejetee_du_meme_accord(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    b = _depense(organisation, projet, accord, cat["serv"], 60)
    soumise = _soumettre(_preparer(profils, accord, [a]), profils)
    with pytest.raises(DemandeInvalide, match="rejetée du même accord"):
        _preparer(profils, accord, [b], reprise_de=soumise)
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="rejetée du même accord"):
            admin.execute(
                """INSERT INTO decaissements_demanderetrait (id, created_at, updated_at, org_id,
                       project_id, accord_id, numero, type, status, periode_debut, periode_fin,
                       montant_total, reprise_de_id, motif_rejet, motif_contestation,
                       empreinte_etat)
                   VALUES (gen_random_uuid(), now(), now(), %s, %s, %s, 'X', 'retrait', 'preparee',
                           '2026-01-01', '2026-01-31', 0, %s, '', '', '')""",
                [organisation.id, projet.id, accord.pk, soumise.pk],
            )


def test_la_reprise_d_une_rejetee_ne_donne_pas_acces_aux_depenses_rejetees_d_une_autre(drf):
    """Chaîne : rejet, reprise rejetée à son tour, nouvelle reprise de CELLE-CI seulement."""
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    d1 = rejeter_demande(
        _soumettre(_preparer(profils, accord, [a]), profils),
        utilisateur=profils["bruno"],
        motif="Non",
    )
    d2 = rejeter_demande(
        _soumettre(_preparer(profils, accord, [a], reprise_de=d1), profils),
        utilisateur=profils["bruno"],
        motif="Encore non",
    )
    with pytest.raises(DepenseNonSelectionnable, match="rejetée"):
        _preparer(profils, accord, [a], reprise_de=d1)  # il faut reprendre la DERNIÈRE rejetée
    assert _preparer(profils, accord, [a], reprise_de=d2).reprise_de_id == d2.pk


def test_une_demande_contestee_se_motive_et_se_resout(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    demande = _soumettre(_preparer(profils, accord, [a]), profils)
    with pytest.raises(DemandeInvalide, match="motif"):
        contester_demande(demande, utilisateur=profils["bruno"], motif="")
    contester_demande(demande, utilisateur=profils["bruno"], motif="Écart de taux")
    assert (demande.status, demande.motif_contestation) == ("contestee", "Écart de taux")
    assert _utilise(cat["serv"]) == D(50)  # une demande contestée pèse encore
    accepter_demande(demande, utilisateur=profils["bruno"])
    rembourser_demande(demande, utilisateur=profils["bruno"])
    assert demande.status == "remboursee" and _utilise(cat["serv"]) == D(50)
    for suite in (accepter_demande, rembourser_demande):
        with pytest.raises(TransitionInterdite):
            suite(demande, utilisateur=profils["bruno"])


# --- plafonds, disponible, accord -----------------------------------------------------------


def test_la_soumission_refuse_le_depassement_du_plafond_d_une_categorie_et_de_ses_parents(drf):
    organisation, projet, profils, accord, cat = drf
    a1 = _depense(organisation, projet, accord, cat["biens_a"], 300)
    a2 = _depense(organisation, projet, accord, cat["biens_a"], 150)  # BIENS-A : 450 > 400
    d = _preparer(profils, accord, [a1, a2])
    with pytest.raises(DisponibleInsuffisant, match="catégorie BIENS-A : plafond 400"):
        _soumettre(d, profils)
    assert d.status == "preparee" and _utilise(cat["biens_a"]) == D(0)
    annuler_demande(d, utilisateur=profils["amina"], motif="Dépasse le plafond")  # libère a1 et a2

    # Dans le plafond de BIENS-A, mais le parent BIENS (600) compte aussi tout ce qui est dessous.
    d_ok = _preparer(profils, accord, [a1])
    _soumettre(d_ok, profils)
    assert (_utilise(cat["biens_a"]), _utilise(cat["biens"])) == (D(300), D(300))
    direct = _depense(organisation, projet, accord, cat["biens"], 350)  # BIENS : 650 > 600
    with pytest.raises(DisponibleInsuffisant, match="catégorie BIENS : plafond 600"):
        _soumettre(_preparer(profils, accord, [direct]), profils)


def test_la_soumission_refuse_le_depassement_du_montant_de_l_accord_et_un_avenant_l_eleve(drf):
    organisation, projet, profils, accord, cat = drf
    # Accord de 1 000 ; catégories sans plafond pour ne tester que l'accord.
    libre = creer_categorie(
        utilisateur=profils["dora"], accord=accord, code="LIBRE", label={"fr": "Libre"}
    )
    gros = _depense(organisation, projet, accord, libre, 900)
    reste = _depense(organisation, projet, accord, libre, 200)
    _soumettre(_preparer(profils, accord, [gros]), profils)
    d2 = _preparer(profils, accord, [reste])
    with pytest.raises(DisponibleInsuffisant, match="accord DON-1 : montant 1000"):
        _soumettre(d2, profils)
    creer_avenant(
        utilisateur=profils["dora"],
        accord=accord,
        reference="AV-1",
        date_avenant=datetime.date(2026, 3, 1),
        document=_document(organisation, projet),
        montant_revise="1500",
    )
    assert _soumettre(d2, profils).status == "soumise"
    assert SoldeAccord.objects.get().utilise == D(1100)


def test_un_rejet_restitue_le_disponible(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["biens_a"], 300)
    d = _soumettre(_preparer(profils, accord, [a]), profils)
    assert (
        _utilise(cat["biens_a"]),
        _utilise(cat["biens"]),
        SoldeAccord.objects.get().utilise,
    ) == (D(300), D(300), D(300))
    rejeter_demande(d, utilisateur=profils["bruno"], motif="Non éligible")
    assert (
        _utilise(cat["biens_a"]),
        _utilise(cat["biens"]),
        SoldeAccord.objects.get().utilise,
    ) == (D(0), D(0), D(0))


def test_la_base_refuse_un_depassement_meme_si_le_service_est_contourne(drf):
    organisation, projet, profils, accord, cat = drf
    SoldeCategorie.objects.create(org_id=organisation.id, categorie=cat["serv"], utilise=D(10))
    SoldeAccord.objects.create(org_id=organisation.id, accord=accord, utilise=D(10))
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="plafond de la catégorie serait dépassé"):
            admin.execute(
                "UPDATE decaissements_soldecategorie SET utilise = 301 WHERE categorie_id = %s",
                [cat["serv"].pk],
            )
        with pytest.raises(Exception, match="montant de l'accord serait dépassé"):
            admin.execute(
                "UPDATE decaissements_soldeaccord SET utilise = 1001 WHERE accord_id = %s",
                [accord.pk],
            )
        admin.execute(
            "UPDATE decaissements_soldecategorie SET utilise = 300 WHERE categorie_id = %s",
            [cat["serv"].pk],
        )  # pile le plafond : accepté


# --- accord suspendu ------------------------------------------------------------------------


def test_un_accord_suspendu_refuse_toute_nouvelle_demande(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    b = _depense(organisation, projet, accord, cat["serv"], 60)
    preparee = _preparer(profils, accord, [a])
    changer_statut_accord(accord, "suspendu", utilisateur=profils["dora"], motif="Audit")
    with pytest.raises(AccordNonActif, match="suspendu"):
        _preparer(profils, accord, [b])
    with pytest.raises(AccordNonActif, match="suspendu"):  # ni la soumission d'une préparée
        _soumettre(preparee, profils)
    with connexion_proprietaire() as admin:  # ni la base, pour tout rôle
        with pytest.raises(Exception, match="aucune nouvelle demande"):
            admin.execute(
                """INSERT INTO decaissements_demanderetrait (id, created_at, updated_at, org_id,
                       project_id, accord_id, numero, type, status, periode_debut, periode_fin,
                       montant_total, motif_rejet, motif_contestation, empreinte_etat)
                   VALUES (gen_random_uuid(), now(), now(), %s, %s, %s, 'Y', 'retrait', 'preparee',
                           '2026-01-01', '2026-01-31', 0, '', '', '')""",
                [organisation.id, projet.id, accord.pk],
            )
        with pytest.raises(Exception, match="aucune nouvelle demande"):
            admin.execute(
                "UPDATE decaissements_demanderetrait SET status = 'soumise', "
                "montant_total = 50 WHERE id = %s",
                [preparee.pk],
            )
    changer_statut_accord(accord, "actif", utilisateur=profils["dora"])
    assert _soumettre(preparee, profils).status == "soumise"


# --- soumission : état certifié, idempotence, droits ----------------------------------------


def test_la_soumission_fige_l_etat_certifie_de_depenses_et_son_empreinte(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["biens_a"], 100, jour=5)
    b = _depense(organisation, projet, accord, cat["serv"], 50, jour=6)
    d = _soumettre(_preparer(profils, accord, [a, b]), profils)
    etat = d.etat_certifie
    assert (etat["demande"], etat["accord"], etat["total"]) == (
        "DRF-DON-1-001",
        "DON-1",
        "150.0000",
    )
    assert [(c["categorie"], c["total"]) for c in etat["categories"]] == [
        ("BIENS-A", "100.0000"),
        ("SERV", "50.0000"),
    ]
    assert etat["categories"][0]["lignes"][0]["piece"].startswith("OD-2026-")
    assert len(d.empreinte_etat) == 64
    from niveau1_socle.decaissements.services import empreinte_de

    assert d.empreinte_etat == empreinte_de(etat)
    assert (d.soumise_par, d.status) == (profils["bruno"].id, "soumise")
    assert verifier_chaine(organisation.id) is None


def test_soumettre_exige_valider_une_autre_personne_et_une_demande_preparee(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    d = _preparer(profils, accord, [a])
    with pytest.raises(PermissionDenied):  # amina n'a pas « valider »
        soumettre_demande(d, utilisateur=profils["amina"])
    role_duo = profils["bruno"]  # bruno valide mais n'a pas préparé : accepté
    assert soumettre_demande(d, utilisateur=role_duo).status == "soumise"
    with pytest.raises(TransitionInterdite):
        soumettre_demande(d, utilisateur=role_duo)  # déjà soumise, sans clé : refusé


def test_l_auteur_de_la_demande_ne_la_soumet_pas_lui_meme(drf):
    organisation, projet, profils, accord, cat = drf
    from niveau1_socle.habilitations.models import Habilitation, Role

    role = Role.objects.create(
        org_id=organisation.id,
        code="DUO",
        label={"fr": "D"},
        operations=["consulter", "saisir", "valider"],
    )
    duo = Utilisateur.objects.create_user("duo", password="x", org_id=organisation.id)
    Habilitation.objects.create(
        org_id=organisation.id, user_id=duo.id, project_id=projet.id, role=role
    )
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    d = _preparer(profils, accord, [a], utilisateur=duo)
    with pytest.raises(PermissionDenied, match="même"):
        soumettre_demande(d, utilisateur=duo)


def test_rejouer_la_soumission_avec_la_meme_cle_ne_cree_qu_une_demande(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    d = _preparer(profils, accord, [a])
    cle = "soumission-2026-03-A"
    premiere = _soumettre(d, profils, cle_idempotence=cle)
    seconde = _soumettre(DemandeRetrait.objects.get(pk=d.pk), profils, cle_idempotence=cle)
    assert premiere.pk == seconde.pk and seconde.cle_idempotence == cle
    assert _utilise(cat["serv"]) == D(50)  # consommé une seule fois
    assert DemandeRetrait.objects.count() == 1
    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM core_auditlog WHERE action = 'drf_submitted'")
        assert cur.fetchone() == (1,)
    # Une autre clé sur une demande déjà soumise : refus, pas de second effet.
    with pytest.raises(TransitionInterdite):
        _soumettre(d, profils, cle_idempotence="autre-cle")


# --- le cycle est fermé et la demande soumise est figée --------------------------------------


def test_la_base_garde_le_cycle_et_fige_la_demande_soumise(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    d = _soumettre(_preparer(profils, accord, [a]), profils)
    ligne = d.lignes.get()
    with connexion_proprietaire() as admin:
        for requete, params, motif in [
            (
                "DELETE FROM decaissements_demanderetrait WHERE id = %s",
                [d.pk],
                "ne se supprime jamais",
            ),
            (
                "UPDATE decaissements_demanderetrait SET montant_total = 1 WHERE id = %s",
                [d.pk],
                "contenu d'une demande soumise",
            ),
            (
                "UPDATE decaissements_demanderetrait SET status = 'preparee' WHERE id = %s",
                [d.pk],
                "Transition de demande interdite",
            ),
            (
                "UPDATE decaissements_demanderetrait SET status = 'remboursee' WHERE id = %s",
                [d.pk],
                "Transition de demande interdite",
            ),
            (
                "UPDATE decaissements_lignedemande SET montant = 1 WHERE id = %s",
                [ligne.pk],
                "ne change que par le sort de sa demande",
            ),
            (
                "UPDATE decaissements_lignedemande SET etat = 'annule' WHERE id = %s",
                [ligne.pk],
                "ne change que par le sort de sa demande",
            ),
            (
                "DELETE FROM decaissements_lignedemande WHERE id = %s",
                [ligne.pk],
                "ne se retire pas",
            ),
        ]:
            with pytest.raises(Exception, match=motif):
                admin.execute(requete, params)
    rejeter_demande(d, utilisateur=profils["bruno"], motif="Non")
    for suite in (accepter_demande, rembourser_demande):
        with pytest.raises(TransitionInterdite):
            suite(d, utilisateur=profils["bruno"])
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="figée"):
            admin.execute(
                "UPDATE decaissements_demanderetrait SET type = 'retrait' WHERE id = %s", [d.pk]
            )


def test_la_base_valide_les_lignes_contre_le_grand_livre(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    brouillon = _depense(organisation, projet, accord, cat["serv"], 40, statut="draft")
    autre = _depense(organisation, projet, accord, cat["serv"], 30, agreement=False)
    demande = DemandeRetrait.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        accord=accord,
        numero="DRF-Z",
        type="retrait",
        periode_debut=DEBUT,
        periode_fin=FIN,
    )
    base = {"org_id": organisation.id, "demande": demande, "date_piece": DEBUT}
    for ligne_id, categorie, montant, message in [
        (brouillon, cat["serv"], 40, "comptabilisée"),
        (autre, cat["serv"], 30, "pas imputée à l'accord"),
        (a, cat["biens"], 50, "catégorie de la ligne est celle du grand livre"),
        (a, cat["serv"], 49, "montant de la ligne est celui du grand livre"),
    ]:
        with pytest.raises(IntegrityError, match=message), transaction.atomic():
            LigneDemande.objects.create(
                ligne_ecriture_id=ligne_id, categorie=categorie, montant=D(montant), **base
            )
    assert LigneDemande.objects.count() == 0


# --- la concurrence --------------------------------------------------------------------------


def _soumission_concurrente(org_id, user_id, demande_id, barriere, cle=None):
    try:
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [str(org_id)])
        barriere.wait()
        utilisateur = Utilisateur.objects.get(pk=user_id)
        demande = DemandeRetrait.objects.get(pk=demande_id)
        soumettre_demande(demande, utilisateur=utilisateur, cle_idempotence=cle)
        return "acceptee"
    except DisponibleInsuffisant:
        return "refusee"
    finally:
        connections.close_all()


def test_dix_soumissions_simultanees_sur_un_disponible_qui_en_autorise_trois(drf):
    """Contrôle de concurrence de L4-T06 : exactement trois acceptées, solde exact."""
    organisation, projet, profils, accord, cat = drf
    # Plafond de la catégorie : 300. Dix demandes de 100 chacune se disputent ce disponible.
    demandes = []
    for i in range(10):
        ligne = _depense(organisation, projet, accord, cat["serv"], 100, jour=1 + i)
        demandes.append(_preparer(profils, accord, [ligne]))
    barriere = threading.Barrier(10)
    with ThreadPoolExecutor(max_workers=10) as pool:
        futurs = [
            pool.submit(
                _soumission_concurrente, organisation.id, profils["bruno"].id, d.pk, barriere
            )
            for d in demandes
        ]
        issues = [f.result() for f in futurs]

    assert sorted(issues) == ["acceptee"] * 3 + ["refusee"] * 7
    assert DemandeRetrait.objects.filter(status="soumise").count() == 3
    assert DemandeRetrait.objects.filter(status="preparee").count() == 7
    assert _utilise(cat["serv"]) == D(300)  # exact : ni plus, ni moins
    assert SoldeAccord.objects.get().utilise == D(300)
    # Recalcul indépendant depuis les lignes des demandes soumises.
    assert sum(
        ligne.montant for ligne in LigneDemande.objects.filter(demande__status="soumise")
    ) == D(300)


def test_cinq_soumissions_simultanees_de_la_meme_demande_avec_la_meme_cle(drf):
    organisation, projet, profils, accord, cat = drf
    ligne = _depense(organisation, projet, accord, cat["serv"], 100)
    demande = _preparer(profils, accord, [ligne])
    barriere = threading.Barrier(5)
    with ThreadPoolExecutor(max_workers=5) as pool:
        futurs = [
            pool.submit(
                _soumission_concurrente,
                organisation.id,
                profils["bruno"].id,
                demande.pk,
                barriere,
                "cle-unique",
            )
            for _ in range(5)
        ]
        assert [f.result() for f in futurs] == ["acceptee"] * 5  # chacune obtient le même résultat
    assert _utilise(cat["serv"]) == D(100)  # consommé UNE fois
    assert DemandeRetrait.objects.get().status == "soumise"
    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM core_auditlog WHERE action = 'drf_submitted'")
        assert cur.fetchone() == (1,)


# --- isolation ------------------------------------------------------------------------------


def test_les_demandes_sont_isolees_par_organisation(drf):
    organisation, projet, profils, accord, cat = drf
    a = _depense(organisation, projet, accord, cat["serv"], 50)
    _soumettre(_preparer(profils, accord, [a], ecarts={}), profils)
    autre = _creer_organisation("ORG-B")
    _poser(autre)
    for modele in (DemandeRetrait, LigneDemande, MiseAEcart, SoldeCategorie, SoldeAccord):
        assert modele.objects.count() == 0, modele
