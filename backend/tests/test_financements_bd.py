"""Bailleurs, accords, catégories, avenants, comptes bancaires. Voir L4-T04.

Contrôle : deux accords du même bailleur sur le même projet coexistent sans partager ni catégories
ni paramètres ; un accord suspendu refuse une nouvelle demande ; un numéro de compte n'est lisible
que par l'habilitation dédiée.
"""

import datetime
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from niveau1_socle.comptabilite.models import Ecriture
from niveau1_socle.comptabilite.services import (
    comptabiliser_ecriture,
    contre_passer,
    saisir_ecriture,
    valider_ecriture,
)
from niveau1_socle.exercices.services import TransitionInterdite
from niveau1_socle.financements.models import (
    Accord,
    AvenantAccord,
    Bailleur,
    Categorie,
    CompteBancaire,
    masquer_numero,
)
from niveau1_socle.financements.services import (
    AccordNonActif,
    FinancementInvalide,
    changer_statut_accord,
    consulter_numero_compte,
    creer_accord,
    creer_avenant,
    creer_bailleur,
    creer_categorie,
    creer_compte_bancaire,
    exiger_accord_actif,
    montant_courant,
    situation_avant_apres,
)
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau3_config.models import DocumentReference
from tests.outils import connexion_proprietaire
from tests.test_cycle_ecriture_bd import _creer_projet, _poser, decor  # noqa: F401
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = Decimal


@pytest.fixture
def cadre(decor):  # noqa: F811
    """dora paramètre ; nadia paramètre ET voit les numéros de compte ; amina saisit."""
    organisation, projet, profils = decor
    for nom, operations in {
        "dora": ["consulter", "parametrer"],
        "nadia": ["consulter", "parametrer", "voir_numero_compte"],
    }.items():
        utilisateur = Utilisateur.objects.create_user(nom, password="x", org_id=organisation.id)
        role = Role.objects.create(
            org_id=organisation.id, code=nom.upper(), label={"fr": nom}, operations=operations
        )
        Habilitation.objects.create(
            org_id=organisation.id, user_id=utilisateur.id, project_id=projet.id, role=role
        )
        profils[nom] = utilisateur
    bailleur = creer_bailleur(utilisateur=profils["dora"], code="IDA", nom="Banque mondiale (IDA)")
    return organisation, projet, profils, bailleur


def _accord(projet, profils, bailleur, numero="IDA-6789", **champs):
    donnees = {
        "utilisateur": profils["dora"],
        "project_id": projet.id,
        "bailleur": bailleur,
        "numero": numero,
        "nature": "don",
        "devise": "USD",
        "montant_initial": "1000000",
    } | champs
    return creer_accord(**donnees)


def _activer(accord, profils):
    return changer_statut_accord(accord, "actif", utilisateur=profils["dora"])


def _document(organisation, projet, nom="Avenant 1", kind="financing_agreement"):
    return DocumentReference.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        kind=kind,
        title=nom,
        file_ref=f"s3://docs/{nom}.pdf",
        sha256=b"\x01" * 32,
    )


# --- accords : création, contraintes ------------------------------------------------------


def test_deux_accords_du_meme_bailleur_sur_le_meme_projet_ne_partagent_rien(cadre):
    organisation, projet, profils, bailleur = cadre
    a1 = _accord(projet, profils, bailleur, "IDA-1")
    a2 = _accord(projet, profils, bailleur, "IDA-2", montant_initial="500000")
    c1 = creer_categorie(
        utilisateur=profils["dora"],
        accord=a1,
        code="BIENS",
        label={"fr": "Biens"},
        plafond="400000",
    )
    creer_categorie(
        utilisateur=profils["dora"],
        accord=a2,
        code="BIENS",
        label={"fr": "Biens"},
        plafond="100000",
    )  # même code : l'identité d'une catégorie est (accord, code)
    assert Accord.objects.filter(project_id=projet.id, bailleur=bailleur).count() == 2
    assert list(a1.categories.all()) == [c1] and a2.categories.count() == 1
    assert a1.categories.get().plafond == D(400000) and a2.categories.get().plafond == D(100000)
    assert montant_courant(a1) == D(1000000) and montant_courant(a2) == D(500000)


def test_le_numero_d_accord_est_unique_par_organisation(cadre):
    _, projet, profils, bailleur = cadre
    _accord(projet, profils, bailleur, "IDA-1")
    with pytest.raises(IntegrityError, match="uq_accord_numero"), transaction.atomic():
        _accord(projet, profils, bailleur, "IDA-1")


@pytest.mark.parametrize(
    "champs, contrainte",
    [
        ({"montant_initial": "-1"}, "accord_montant_positif"),
        (
            {"date_effet": datetime.date(2026, 6, 1), "date_cloture": datetime.date(2026, 1, 1)},
            "accord_dates_1",
        ),
        (
            {
                "date_fin_eligibilite": datetime.date(2027, 1, 1),
                "date_limite_decaissement": datetime.date(2026, 12, 31),
            },
            "accord_dates_4",
        ),
        (
            {
                "date_effet": datetime.date(2026, 1, 1),
                "date_limite_decaissement": datetime.date(2025, 1, 1),
            },
            "accord_dates_2",
        ),
        ({"nature": "cadeau"}, "accord_nature_fermee"),
    ],
)
def test_la_base_refuse_un_accord_incoherent(cadre, champs, contrainte):
    _, projet, profils, bailleur = cadre
    with pytest.raises(IntegrityError, match=contrainte), transaction.atomic():
        _accord(projet, profils, bailleur, **champs)


def test_des_dates_coherentes_et_partielles_sont_acceptees(cadre):
    _, projet, profils, bailleur = cadre
    accord = _accord(
        projet,
        profils,
        bailleur,
        date_effet=datetime.date(2026, 1, 1),
        date_cloture=datetime.date(2028, 12, 31),  # fin d'éligibilité et limite non renseignées
    )
    assert accord.date_cloture.year == 2028


def test_un_accord_ne_peut_viser_ni_le_projet_ni_le_bailleur_d_une_autre_organisation(cadre):
    organisation, projet, profils, bailleur = cadre
    autre = _creer_organisation("ORG-B")
    projet_b = _creer_projet(autre, "PB")
    with connexion_proprietaire() as admin:
        admin.execute(
            "INSERT INTO financements_bailleur (id, created_at, updated_at, org_id, code, nom, "
            "pays, actif) VALUES (%s, now(), now(), %s, 'B', 'Bailleur B', '', true)",
            [uuid.uuid4(), autre.id],
        )
        (bailleur_b,) = admin.execute(
            "SELECT id FROM financements_bailleur WHERE org_id = %s", [autre.id]
        ).fetchone()
        base = """INSERT INTO financements_accord (id, created_at, updated_at, org_id, project_id,
            bailleur_id, numero, libelle, nature, status, devise_id, montant_initial)
            VALUES (gen_random_uuid(), now(), now(), %s, %s, %s, 'X', '', 'don', 'brouillon',
                    'USD', 1)"""
        with pytest.raises(Exception, match="fk_accord_bailleur_meme_org"):
            admin.execute(base, [organisation.id, projet.id, bailleur_b])
        with pytest.raises(Exception, match="fk_accord_projet_meme_org"):
            admin.execute(base, [organisation.id, projet_b.id, bailleur.id])


# --- statuts ------------------------------------------------------------------------------


def test_le_cycle_de_vie_d_un_accord_est_ferme(cadre):
    organisation, projet, profils, bailleur = cadre
    accord = _accord(projet, profils, bailleur)
    assert accord.status == "brouillon"
    with pytest.raises(TransitionInterdite):
        changer_statut_accord(accord, "suspendu", utilisateur=profils["dora"], motif="x")
    _activer(accord, profils)
    with pytest.raises(FinancementInvalide, match="motif"):
        changer_statut_accord(accord, "suspendu", utilisateur=profils["dora"])
    changer_statut_accord(accord, "suspendu", utilisateur=profils["dora"], motif="Audit en cours")
    _activer(accord, profils)  # réactivation
    changer_statut_accord(accord, "clos", utilisateur=profils["dora"], motif="Fin de projet")
    for suite in ("actif", "suspendu", "annule"):
        with pytest.raises(TransitionInterdite):
            changer_statut_accord(accord, suite, utilisateur=profils["dora"], motif="x")
    with pytest.raises(PermissionDenied):
        changer_statut_accord(
            _accord(projet, profils, bailleur, "Z"), "actif", utilisateur=profils["amina"]
        )
    assert verifier_chaine(organisation.id) is None


def test_la_base_refuse_une_transition_interdite_et_la_modification_d_un_accord_actif(cadre):
    _, projet, profils, bailleur = cadre
    accord = _activer(_accord(projet, profils, bailleur), profils)
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="ne change plus que de statut"):
            admin.execute(
                "UPDATE financements_accord SET montant_initial = 1 WHERE id = %s", [accord.pk]
            )
        with pytest.raises(Exception, match="Transition d'accord interdite"):
            admin.execute(
                "UPDATE financements_accord SET status = 'brouillon' WHERE id = %s", [accord.pk]
            )
        with pytest.raises(Exception, match="ne se supprime jamais"):
            admin.execute("DELETE FROM financements_accord WHERE id = %s", [accord.pk])


def test_la_base_refuse_toute_transition_hors_du_cycle_ferme(cadre):
    _, projet, profils, bailleur = cadre
    interdites = [
        ("brouillon", "suspendu"),
        ("brouillon", "clos"),
        ("actif", "brouillon"),
        ("suspendu", "brouillon"),
        ("suspendu", "annule"),
    ]
    with connexion_proprietaire() as admin:
        for depart, arrivee in interdites:
            accord = _accord(projet, profils, bailleur, f"T-{depart}-{arrivee}")
            if depart != "brouillon":
                _activer(accord, profils)
            if depart == "suspendu":
                changer_statut_accord(accord, "suspendu", utilisateur=profils["dora"], motif="x")
            with pytest.raises(Exception, match="Transition d'accord interdite"):
                admin.execute(
                    "UPDATE financements_accord SET status = %s WHERE id = %s", [arrivee, accord.pk]
                )


def test_un_brouillon_vierge_se_supprime_mais_pas_un_accord_qui_porte_deja_quelque_chose(cadre):
    organisation, projet, profils, bailleur = cadre
    brouillon = _accord(projet, profils, bailleur, "TMP")
    brouillon.delete()
    assert not Accord.objects.filter(numero="TMP").exists()

    accord = _accord(projet, profils, bailleur, "IDA-1")
    creer_categorie(utilisateur=profils["dora"], accord=accord, code="C", label={"fr": "C"})
    with pytest.raises(Exception, match="ne se supprime jamais"), connection.cursor() as cur:
        cur.execute("DELETE FROM financements_accord WHERE id = %s", [accord.pk])  # brouillon, mais
        # il porte déjà une catégorie : c'est la base qui refuse, pas l'ORM


def test_un_accord_porteur_d_operations_ne_s_annule_ni_ne_se_supprime(cadre):
    organisation, projet, profils, bailleur = cadre
    from niveau1_socle.budget.engagements import creer_engagement

    accord = _activer(_accord(projet, profils, bailleur), profils)
    amina = profils["amina"]
    creer_engagement(
        utilisateur=amina,
        project_id=projet.id,
        reference="E1",
        annee=2026,
        montant="10",
        agreement_id=accord.pk,
    )
    with pytest.raises(Exception, match="ne s'annule pas"):
        changer_statut_accord(accord, "annule", utilisateur=profils["dora"], motif="Erreur")
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="ne se supprime jamais"):
            admin.execute("DELETE FROM financements_accord WHERE id = %s", [accord.pk])
    changer_statut_accord(accord, "clos", utilisateur=profils["dora"], motif="Fin")  # se clôt


# --- accord suspendu ----------------------------------------------------------------------


def _lignes(accord_id, montant="100"):
    return [
        {"compte": "6011", "debit": montant, "agreement_id": accord_id},
        {"compte": "5211", "credit": montant},
    ]


def _saisir(projet, profils, accord_id):
    return saisir_ecriture(
        utilisateur=profils["amina"],
        project_id=projet.id,
        journal="OD",
        date_comptable=datetime.date(2026, 3, 10),
        libelle="Charge",
        lignes=_lignes(accord_id),
    )


def test_un_accord_suspendu_refuse_une_nouvelle_imputation_et_une_nouvelle_demande(cadre):
    organisation, projet, profils, bailleur = cadre
    accord = _activer(_accord(projet, profils, bailleur), profils)
    assert _saisir(projet, profils, accord.pk).status == "draft"  # actif : accepté

    changer_statut_accord(accord, "suspendu", utilisateur=profils["dora"], motif="Audit")
    with pytest.raises(AccordNonActif, match="suspendu"):
        _saisir(projet, profils, accord.pk)
    with pytest.raises(AccordNonActif, match="demande"):  # le point d'appui des demandes (L4-T06)
        exiger_accord_actif(accord.pk, pour="demande_decaissement")

    changer_statut_accord(accord, "actif", utilisateur=profils["dora"])
    assert _saisir(projet, profils, accord.pk).status == "draft"


def test_un_accord_inconnu_ou_en_brouillon_ne_recoit_pas_d_imputation(cadre):
    _, projet, profils, bailleur = cadre
    with pytest.raises(AccordNonActif, match="n'existe pas"):
        _saisir(projet, profils, uuid.uuid4())
    brouillon = _accord(projet, profils, bailleur)
    with pytest.raises(AccordNonActif, match="brouillon"):
        _saisir(projet, profils, brouillon.pk)


def test_une_pioce_saisie_avant_la_suspension_ne_se_valide_plus_mais_l_historique_se_corrige(cadre):
    organisation, projet, profils, bailleur = cadre
    accord = _activer(_accord(projet, profils, bailleur), profils)
    en_attente = _saisir(projet, profils, accord.pk)
    posee = _saisir(projet, profils, accord.pk)
    valider_ecriture(posee, utilisateur=profils["bruno"])
    comptabiliser_ecriture(posee, utilisateur=profils["claire"])

    changer_statut_accord(accord, "suspendu", utilisateur=profils["dora"], motif="Audit")
    with pytest.raises(Exception, match="l'accord est suspendu"):
        valider_ecriture(en_attente, utilisateur=profils["bruno"])
    # L'historique reste consultable ET corrigeable : la contre-passation passe.
    inverse = contre_passer(Ecriture.objects.get(pk=posee.pk), utilisateur=profils["amina"])
    valider_ecriture(inverse, utilisateur=profils["bruno"])
    assert comptabiliser_ecriture(inverse, utilisateur=profils["claire"]).status == "posted"


# --- avenants -----------------------------------------------------------------------------


def test_un_avenant_porte_la_nouvelle_valeur_sans_modifier_l_accord(cadre):
    organisation, projet, profils, bailleur = cadre
    accord = _activer(_accord(projet, profils, bailleur), profils)
    doc = _document(organisation, projet)
    v = uuid.uuid4()
    avenant = creer_avenant(
        utilisateur=profils["dora"],
        accord=accord,
        reference="AV-1",
        date_avenant=datetime.date(2026, 6, 1),
        document=doc,
        montant_revise="1200000",
        motif="Financement additionnel",
        profile_version_id=v,
    )
    assert Accord.objects.get(pk=accord.pk).montant_initial == D(1000000)  # inchangé
    assert montant_courant(accord) == D(1200000)
    assert montant_courant(accord, datetime.date(2026, 5, 31)) == D(1000000)
    s = situation_avant_apres(avenant)
    assert (s["montant_avant"], s["montant_apres"], s["variation"]) == (
        D(1000000),
        D(1200000),
        D(200000),
    )
    assert s["profile_version_id"] == v

    creer_avenant(
        utilisateur=profils["dora"],
        accord=accord,
        reference="AV-2",
        date_avenant=datetime.date(2026, 9, 1),
        document=_document(organisation, projet, "A2"),
        montant_revise="1100000",
    )  # un avenant peut aussi réduire
    assert montant_courant(accord) == D(1100000)
    assert situation_avant_apres(AvenantAccord.objects.get(reference="AV-2"))["variation"] == D(
        -100000
    )


def test_un_avenant_est_immuable_et_exige_un_accord_vivant_et_un_document_de_l_accord(cadre):
    organisation, projet, profils, bailleur = cadre
    brouillon = _accord(projet, profils, bailleur, "B")
    doc = _document(organisation, projet)
    with pytest.raises(Exception, match="actif ou suspendu"):
        creer_avenant(
            utilisateur=profils["dora"],
            accord=brouillon,
            reference="A",
            date_avenant=datetime.date(2026, 1, 1),
            document=doc,
            montant_revise="1",
        )
    accord = _activer(_accord(projet, profils, bailleur), profils)
    with pytest.raises(Exception, match="accord de financement du même projet"):
        creer_avenant(
            utilisateur=profils["dora"],
            accord=accord,
            reference="A",
            date_avenant=datetime.date(2026, 1, 1),
            document=_document(organisation, projet, "Manuel", "implementation_manual"),
            montant_revise="1",
        )
    av = creer_avenant(
        utilisateur=profils["dora"],
        accord=accord,
        reference="A",
        date_avenant=datetime.date(2026, 1, 1),
        document=doc,
        montant_revise="1",
    )
    with connexion_proprietaire() as admin:
        for requete in (
            "UPDATE financements_avenantaccord SET montant_revise = 5 WHERE id = %s",
            "DELETE FROM financements_avenantaccord WHERE id = %s",
        ):
            with pytest.raises(Exception, match="ne se modifie ni ne se supprime"):
                admin.execute(requete, [av.pk])
    with pytest.raises(IntegrityError, match="uq_avenant_reference"), transaction.atomic():
        creer_avenant(
            utilisateur=profils["dora"],
            accord=accord,
            reference="A",
            date_avenant=datetime.date(2026, 2, 1),
            document=doc,
            montant_revise="2",
        )
    with pytest.raises(PermissionDenied):
        creer_avenant(
            utilisateur=profils["amina"],
            accord=accord,
            reference="Z",
            date_avenant=datetime.date(2026, 2, 1),
            document=doc,
            montant_revise="2",
        )


# --- catégories ---------------------------------------------------------------------------


def test_les_sous_categories_restent_dans_l_accord_et_sous_le_plafond_du_parent(cadre):
    organisation, projet, profils, bailleur = cadre
    a1, a2 = _accord(projet, profils, bailleur, "A1"), _accord(projet, profils, bailleur, "A2")
    dora = profils["dora"]
    parent = creer_categorie(
        utilisateur=dora, accord=a1, code="TRAV", label={"fr": "Travaux"}, plafond="300000"
    )
    enfant = creer_categorie(
        utilisateur=dora,
        accord=a1,
        code="TRAV-1",
        label={"fr": "Lot 1"},
        plafond="300000",
        parent=parent,
    )
    assert list(parent.enfants.all()) == [enfant]
    with pytest.raises(Exception, match="plafond d'une sous-catégorie"):
        creer_categorie(
            utilisateur=dora,
            accord=a1,
            code="TRAV-2",
            label={"fr": "x"},
            plafond="300001",
            parent=parent,
        )
    with pytest.raises(Exception, match="même accord"):
        creer_categorie(
            utilisateur=dora, accord=a2, code="TRAV-3", label={"fr": "x"}, parent=parent
        )
    with pytest.raises(IntegrityError, match="uq_categorie_code"), transaction.atomic():
        creer_categorie(utilisateur=dora, accord=a1, code="TRAV", label={"fr": "x"})
    with pytest.raises(Exception, match="parente ne se supprime pas"), connection.cursor() as cur:
        cur.execute("DELETE FROM financements_categorie WHERE id = %s", [parent.pk])
    with pytest.raises(Exception, match="ni d'accord, ni de code, ni de parent"):
        Categorie.objects.filter(pk=enfant.pk).update(parent=None)


def test_une_categorie_utilisee_ne_change_plus_que_de_libelle(cadre):
    organisation, projet, profils, bailleur = cadre
    accord = _activer(_accord(projet, profils, bailleur), profils)
    cat = creer_categorie(
        utilisateur=profils["dora"],
        accord=accord,
        code="BIENS",
        label={"fr": "Biens"},
        plafond="1000",
    )
    Categorie.objects.filter(pk=cat.pk).update(plafond=2000)  # pas encore utilisée : libre
    from niveau1_socle.budget.engagements import creer_engagement

    creer_engagement(
        utilisateur=profils["amina"],
        project_id=projet.id,
        reference="E1",
        annee=2026,
        montant="10",
        category_id=cat.pk,
    )
    with pytest.raises(Exception, match="seul son libellé change"):
        Categorie.objects.filter(pk=cat.pk).update(plafond=5)
    Categorie.objects.filter(pk=cat.pk).update(label={"fr": "Fournitures"})
    with pytest.raises(Exception, match="utilisée"), connection.cursor() as cur:
        cur.execute("DELETE FROM financements_categorie WHERE id = %s", [cat.pk])


# --- comptes bancaires --------------------------------------------------------------------


def _compte_b(profils, projet, numero="DJ21 0001 0000 0012 3456 7890", code="CD-1", **champs):
    donnees = {
        "utilisateur": profils["dora"],
        "project_id": projet.id,
        "code": code,
        "type": "designe",
        "devise": "USD",
        "banque": "Banque de Djibouti",
        "numero": numero,
    } | champs
    return creer_compte_bancaire(**donnees)


def test_un_numero_de_compte_n_est_lisible_que_par_l_habilitation_dediee(cadre):
    organisation, projet, profils, bailleur = cadre
    compte = _compte_b(profils, projet)
    complet = "DJ21 0001 0000 0012 3456 7890"

    assert compte.numero_masque.endswith("7890") and complet[:-4] not in compte.numero_masque
    assert complet not in str(compte) and complet not in repr(compte)
    with connection.cursor() as cur:  # même le journal d'audit de la création est masqué
        cur.execute("SELECT after::text FROM core_auditlog WHERE action = 'bank_account_created'")
        assert complet not in cur.fetchone()[0]

    for sans_droit in ("dora", "amina", "claire"):  # parametrer ne suffit pas
        with pytest.raises(PermissionDenied):
            consulter_numero_compte(profils[sans_droit], compte)
    assert consulter_numero_compte(profils["nadia"], compte) == complet
    with connection.cursor() as cur:
        cur.execute(
            "SELECT actor_id, after::text FROM core_auditlog "
            "WHERE action = 'bank_account_number_read'"
        )
        lecture = cur.fetchall()
    assert lecture == [(profils["nadia"].id, '{"code": "CD-1"}')]  # tracé, sans le numéro
    assert verifier_chaine(organisation.id) is None


def test_masquer_un_numero():
    assert masquer_numero("1234567890") == "••••••7890"
    assert masquer_numero("12") == "12" and masquer_numero("") == ""


@pytest.mark.parametrize(
    "champs, contrainte",
    [
        ({"type": "autre"}, "comptebancaire_type_ferme"),
        ({"plafond": "-1"}, "comptebancaire_plafond_positif"),
        (
            {"plafond": "1000", "seuil_reapprovisionnement": "1001"},
            "comptebancaire_seuil_sous_plafond",
        ),
    ],
)
def test_la_base_refuse_un_compte_incoherent(cadre, champs, contrainte):
    _, projet, profils, _ = cadre
    with pytest.raises(IntegrityError, match=contrainte), transaction.atomic():
        _compte_b(profils, projet, **champs)


def test_les_cinq_types_de_compte_existent_et_le_numero_est_unique(cadre):
    _, projet, profils, _ = cadre
    for i, type_ in enumerate(("designe", "special", "operationnel", "contrepartie", "transit")):
        _compte_b(
            profils,
            projet,
            numero=f"N{i}-0000",
            code=f"C{i}",
            type=type_,
            plafond="1000",
            seuil_reapprovisionnement="200",
        )
    with pytest.raises(IntegrityError, match="uq_comptebancaire_numero"), transaction.atomic():
        _compte_b(profils, projet, numero="N0-0000", code="AUTRE")


def test_un_compte_est_du_meme_projet_que_son_accord(cadre):
    organisation, projet, profils, bailleur = cadre
    accord = _accord(projet, profils, bailleur)
    assert _compte_b(profils, projet, accord=accord).accord_id == accord.pk
    autre_projet = _creer_projet(organisation, "P2")
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="même projet"):
            admin.execute(
                """INSERT INTO financements_comptebancaire (id, created_at, updated_at, org_id,
                       project_id, accord_id, code, libelle, type, devise_id, banque, numero, actif)
                   VALUES (gen_random_uuid(), now(), now(), %s, %s, %s, 'X', '', 'designe', 'USD',
                           'B', 'NUM-X', true)""",
                [organisation.id, autre_projet.id, accord.pk],
            )


# --- isolation ----------------------------------------------------------------------------


def test_les_financements_sont_isoles_par_organisation(cadre):
    organisation, projet, profils, bailleur = cadre
    accord = _accord(projet, profils, bailleur)
    creer_categorie(utilisateur=profils["dora"], accord=accord, code="C", label={"fr": "C"})
    _compte_b(profils, projet)
    autre = _creer_organisation("ORG-B")
    _poser(autre)
    for modele in (Bailleur, Accord, Categorie, AvenantAccord, CompteBancaire):
        assert modele.objects.count() == 0, modele
