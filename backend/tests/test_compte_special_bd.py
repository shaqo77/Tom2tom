# ruff: noqa: F811, E501
"""Le compte spécial de la BAD : justifications soumises à la Banque et réconciliation. L11-D4.

Annexe 9 du manuel des décaissements : avances versées (cumul depuis l'ouverture), solde de clôture
du relevé, justification de la demande en cours, dépenses déjà justifiées, écart à expliquer. Ce qui
manquait : la trace « dépenses justifiées à la Banque sous la demande n° X », et le cumul depuis
l'ouverture (l'état du compte désigné ne lit qu'une période).
"""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from rest_framework.exceptions import PermissionDenied

from core.erreurs import CodeErreur, ErreurMetier
from niveau1_socle.decaissements.services import (
    accepter_demande,
    annuler_demande,
    rejeter_demande,
)
from niveau1_socle.financements.services import creer_compte_bancaire
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau1_socle.tresorerie.compte_special import (
    annuler_justification,
    calculer_situation,
    justifier_aupres_de_la_banque,
)
from niveau1_socle.tresorerie.models import AppariementDemande, JustificationCompteSpecial
from niveau1_socle.tresorerie.services import (
    annuler_appariement,
    apparier_demande,
    enregistrer_solde_releve,
)
from niveau4_reporting.modeles_etats import modele_reconciliation_compte_special
from niveau4_reporting.moteur.compilateur import ModeleEtatInvalide, generer
from niveau4_reporting.moteur.sources_externes import SourceIncomplete
from niveau4_reporting.publication.rapports import publier_rapport, regenerer
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import _depense, _preparer, _soumettre, drf  # noqa: F401
from tests.test_financements_bd import _accord, cadre  # noqa: F401
from tests.test_tresorerie_bd import _importer

pytestmark = pytest.mark.django_db(transaction=True)
J = datetime.date
D = Decimal
Utilisateur = get_user_model()
FIN = J(2026, 3, 31)


def _poser(organisation):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


@pytest.fixture
def special(drf):
    """Un compte SPÉCIAL en DJF lié à l'accord. Avance de 300 reçue le 20/02 (appariée à la demande
    acceptée de 300), 200 payés le 10/03 ; solde du relevé au 31/01 : 0, donc 100 au 31/03."""
    organisation, projet, profils, accord, cat = drf
    compte = creer_compte_bancaire(
        utilisateur=profils["dora"], project_id=projet.id, code="CS-DJF", type="special",
        devise="DJF", banque="BCD", numero="DJ21 0001 0000 0011 2233", accord=accord,
    )  # fmt: skip
    ligne = _depense(organisation, projet, accord, cat["serv"], 300, jour=12, mois=2)
    demande = accepter_demande(
        _soumettre(_preparer(profils, accord, [ligne]), profils), utilisateur=profils["bruno"]
    )
    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=compte, date_solde=J(2026, 1, 31), solde="0"
    )
    avance, _ = _importer(
        profils, compte, ("AV-1", J(2026, 2, 20), "300"), ("PAI-1", J(2026, 3, 10), "-200")
    )
    apparier_demande(utilisateur=profils["amina"], mouvement=avance, demande=demande)
    pia = Utilisateur.objects.create_user("pia", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id, code="PIA", label={"fr": "p"}, operations=["consulter", "publier"]
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=pia.id, project_id=projet.id, role=role
    )
    profils["pia"] = pia
    return organisation, projet, profils, accord, compte, demande


def _justifier(special, montant="200", **champs):
    _, _, profils, _, compte, demande = special
    return justifier_aupres_de_la_banque(
        utilisateur=profils["amina"], compte=compte, demande=demande, montant=montant,
        date_soumission=champs.pop("date_soumission", J(2026, 3, 20)), **champs,
    )  # fmt: skip


# --- la situation --------------------------------------------------------------------------------


def test_les_avances_sont_cumulees_depuis_l_ouverture_et_seuls_les_encaissements_apparies_comptent(
    special,
):
    _, _, profils, _, compte, demande = special
    _importer(profils, compte, ("INT", J(2026, 3, 5), "50"))  # un encaissement NON apparié
    s = calculer_situation(compte, FIN)
    assert s.avances == [(demande.numero, D("300"))] and s.total_avances == D("300")
    assert s.solde_cloture == D("150")  # 0 + 300 + 50 − 200
    assert calculer_situation(compte, J(2026, 2, 15)).avances == []  # avant l'avance
    # une date bien plus tardive garde l'avance : le cumul ne se limite pas à une période
    assert calculer_situation(compte, J(2027, 12, 31)).total_avances == D("300")


def test_un_appariement_annule_ne_compte_plus_comme_avance(special):
    _, _, profils, _, compte, demande = special
    appariement = AppariementDemande.objects.get(demande=demande, annule_at__isnull=True)
    annuler_appariement(
        utilisateur=profils["amina"], appariement=appariement, motif="mauvais encaissement"
    )
    assert calculer_situation(compte, FIN).avances == []
    assert calculer_situation(compte, FIN).total_avances == 0


def test_sans_justification_la_situation_n_a_que_des_zeros_pour_les_lignes_4_et_5(special):
    _, _, _, _, compte, _ = special
    s = calculer_situation(compte, FIN)
    assert s.complet and (s.justifie_cette_demande, s.justifie_precedemment) == (0, 0)
    assert s.solde_cloture == D("100") and s.total_justifie == D("100") and s.ecart == D("200")


def test_la_justification_de_la_demande_en_cours_et_celles_d_avant_se_separent(special):
    _, _, _, _, compte, demande = special
    _justifier(special, "200")
    en_cours = calculer_situation(compte, FIN, demande.numero)
    assert (en_cours.justifie_cette_demande, en_cours.justifie_precedemment) == (D("200"), 0)
    ailleurs = calculer_situation(
        compte, FIN
    )  # aucune demande désignée : tout est « déjà justifié »
    assert (ailleurs.justifie_cette_demande, ailleurs.justifie_precedemment) == (0, D("200"))
    assert en_cours.total_justifie == ailleurs.total_justifie == D("300") and en_cours.ecart == 0


def test_une_justification_posterieure_a_la_date_n_est_pas_comptee(special):
    _, _, _, _, compte, demande = special
    _justifier(special, "200", date_soumission=J(2026, 4, 15))
    assert calculer_situation(compte, FIN, demande.numero).justifie_cette_demande == 0
    assert calculer_situation(compte, J(2026, 4, 30), demande.numero).justifie_cette_demande == D(
        "200"
    )


def test_sans_solde_de_releve_la_situation_est_incomplete_et_n_invente_aucun_ecart(special):
    _, _, _, _, compte, _ = special
    s = calculer_situation(compte, J(2026, 1, 15))  # avant tout solde enregistré
    assert s.manques == ["cloture"] and not s.complet
    assert s.solde_cloture is None and s.total_justifie is None and s.ecart is None


def test_un_compte_non_special_est_refuse(special):
    organisation, projet, profils, accord, _, demande = special
    designe = creer_compte_bancaire(
        utilisateur=profils["dora"], project_id=projet.id, code="CD-DJF", type="designe",
        devise="DJF", banque="BCD", numero="DJ21 0001 0000 0099 8877",
    )  # fmt: skip
    with pytest.raises(ErreurMetier, match="n'est pas un compte spécial"):
        calculer_situation(designe, FIN)
    with pytest.raises(ErreurMetier, match="n'est pas un compte spécial"):
        justifier_aupres_de_la_banque(
            utilisateur=profils["amina"], compte=designe, demande=demande, montant="10"
        )


# --- justifier -----------------------------------------------------------------------------------


def test_une_justification_se_cree_et_se_journalise(special):
    j = _justifier(special, "200")
    assert (j.montant, j.date_soumission, j.annule_at) == (D("200"), J(2026, 3, 20), None)
    from core.models import AuditLog

    assert AuditLog.objects.filter(action="sa_justification_recorded").count() == 1


@pytest.mark.parametrize("montant", ["0", "-5", "abc", "NaN", 1.5])
def test_un_montant_invalide_est_refuse_sans_rien_creer(special, montant):
    with pytest.raises(ErreurMetier):
        _justifier(special, montant)
    assert JustificationCompteSpecial.objects.count() == 0


def test_la_justification_ne_depasse_pas_ce_que_la_demande_retire(special):
    with pytest.raises(ErreurMetier, match="dépasse le montant de la demande"):
        _justifier(special, "300.01")
    assert JustificationCompteSpecial.objects.count() == 0
    assert _justifier(special, "300").montant == D("300")  # le plafond lui-même est permis


def test_une_demande_ne_se_justifie_qu_une_fois_tant_que_la_premiere_n_est_pas_annulee(special):
    _justifier(special, "100")
    with pytest.raises(ErreurMetier, match="déjà justifiée"):
        _justifier(special, "100")
    assert JustificationCompteSpecial.objects.count() == 1


def special_cat(special):
    from niveau1_socle.financements.models import Categorie

    return Categorie.objects.get(accord=special[3], code="SERV")


def test_la_demande_doit_etre_celle_de_l_accord_du_compte(special):
    organisation, projet, profils, accord, compte, _ = special
    from niveau1_socle.financements.models import Bailleur

    autre = _accord(
        projet, profils, Bailleur.objects.first(), "DON-2", devise="DJF", montant_initial="500"
    )
    from niveau1_socle.financements.services import changer_statut_accord, creer_categorie

    changer_statut_accord(autre, "actif", utilisateur=profils["dora"])
    serv2 = creer_categorie(
        utilisateur=profils["dora"], accord=autre, code="SERV", label={"fr": "S"}, plafond="300"
    )
    ligne = _depense(organisation, projet, autre, serv2, 100, jour=15, mois=2)
    demande2 = accepter_demande(
        _soumettre(_preparer(profils, autre, [ligne]), profils), utilisateur=profils["bruno"]
    )
    with pytest.raises(ErreurMetier, match="n'est pas celle de l'accord du compte"):
        justifier_aupres_de_la_banque(
            utilisateur=profils["amina"], compte=compte, demande=demande2, montant="10"
        )


def test_justifier_exige_saisir_et_annuler_aussi(special):
    _, _, profils, _, compte, demande = special
    with pytest.raises(PermissionDenied):
        justifier_aupres_de_la_banque(
            utilisateur=profils["bruno"], compte=compte, demande=demande, montant="10"
        )
    j = _justifier(special, "100")
    with pytest.raises(PermissionDenied):
        annuler_justification(utilisateur=profils["bruno"], justification=j, motif="erreur")


# --- annuler -------------------------------------------------------------------------------------


def test_annuler_exige_un_motif_puis_la_justification_ne_compte_plus_et_on_peut_refaire(special):
    _, _, profils, _, compte, demande = special
    j = _justifier(special, "100")
    with pytest.raises(ErreurMetier, match="exige un motif"):
        annuler_justification(utilisateur=profils["amina"], justification=j, motif="  ")
    annuler_justification(utilisateur=profils["amina"], justification=j, motif="montant erroné")
    j.refresh_from_db()
    assert j.annule_at is not None and j.motif_annulation == "montant erroné"
    assert calculer_situation(compte, FIN, demande.numero).justifie_cette_demande == 0
    assert _justifier(special, "200").montant == D("200")  # la bonne justification


def test_une_justification_ne_s_annule_qu_une_fois(special):
    _, _, profils, _, _, _ = special
    j = _justifier(special, "100")
    annuler_justification(utilisateur=profils["amina"], justification=j, motif="erreur")
    with pytest.raises(ErreurMetier) as refus:
        annuler_justification(utilisateur=profils["amina"], justification=j, motif="encore")
    assert refus.value.code == CodeErreur.TRANSITION_INTERDITE


def test_la_base_refuse_de_corriger_ou_de_supprimer_une_justification(special):
    j = _justifier(special, "100")
    with pytest.raises(IntegrityError, match="ne change que par son annulation"):
        with transaction.atomic():
            JustificationCompteSpecial.objects.filter(pk=j.pk).update(montant=D("999"))
    with pytest.raises(IntegrityError, match="ne se supprime pas"):
        with transaction.atomic():
            JustificationCompteSpecial.objects.filter(pk=j.pk).delete()
    j.refresh_from_db()
    assert j.montant == D("100")


# --- le modèle d'état ----------------------------------------------------------------------------


def _params(projet, **champs):
    return {
        "fiscal_year": 2026, "current_period": 3, "compte_special": "CS-DJF",
        "date_fin": FIN.isoformat(), "project_id": str(projet.id),
    } | champs  # fmt: skip


def test_le_modele_produit_les_lignes_de_l_annexe_9(special):
    _, projet, _, _, _, demande = special
    _justifier(special, "200")
    modele = modele_reconciliation_compte_special()
    assert modele["code"] == "BAD_RECONCILIATION_CS"
    produit = generer(modele, {}, _params(projet, demande=demande.numero))
    v = {code: valeurs["PER"] for code, valeurs in produit.valeurs.items() if code != "H100"}
    assert v == {
        "R200": D("300"),  # (2) avances versées depuis l'ouverture
        "R300": D("100"),  # (3) solde de clôture du relevé
        "R400": D("200"),  # (4) justification avec la demande en cours
        "R500": D("0"),  # (5) dépenses déjà justifiées
        "R600": D("300"),  # (6) total justifié = (3) + (4) + (5)
        "R700": D("0"),  # (7) écart = (2) − (6)
    }


def test_sans_demande_designee_tout_ce_qui_est_justifie_forme_la_ligne_5(special):
    _, projet, _, _, _, _ = special
    _justifier(special, "200")
    v = generer(modele_reconciliation_compte_special(), {}, _params(projet)).valeurs
    assert (v["R400"]["PER"], v["R500"]["PER"], v["R700"]["PER"]) == (0, D("200"), 0)


def test_un_ecart_reste_affiche_et_ne_bloque_pas(special):
    """L'écart se justifie dans une NOTE (renvoi v du modèle) : le moteur l'affiche, sans assertion."""
    _, projet, _, _, _, demande = special
    _justifier(special, "150")
    v = generer(
        modele_reconciliation_compte_special(), {}, _params(projet, demande=demande.numero)
    ).valeurs
    assert v["R700"]["PER"] == D("50")


def test_sans_releve_a_la_date_l_etat_est_refuse(special):
    _, projet, _, _, _, _ = special
    with pytest.raises(SourceIncomplete, match="cloture"):
        generer(modele_reconciliation_compte_special(), {}, _params(projet, date_fin="2026-01-15"))


@pytest.mark.parametrize(
    "changes",
    [
        {"compte_special": "INCONNU"},
        {"compte_special": ""},
        {"compte_special": 5},
        {"date_fin": "hier"},
        {"demande": 5},
    ],
)
def test_des_parametres_invalides_sont_refuses(special, changes):
    _, projet, _, _, _, _ = special
    with pytest.raises(ModeleEtatInvalide):
        generer(modele_reconciliation_compte_special(), {}, _params(projet, **changes))


def test_un_compte_designe_n_alimente_pas_l_etat_special(special):
    organisation, projet, profils, _, _, _ = special
    creer_compte_bancaire(
        utilisateur=profils["dora"], project_id=projet.id, code="CD-DJF", type="designe",
        devise="DJF", banque="BCD", numero="DJ21 0001 0000 0099 8877",
    )  # fmt: skip
    with pytest.raises(ModeleEtatInvalide, match="n'est pas un compte spécial"):
        generer(
            modele_reconciliation_compte_special(), {}, _params(projet, compte_special="CD-DJF")
        )


def test_le_rapport_se_publie_se_scelle_et_se_regenere_a_l_identique(special):
    organisation, projet, profils, _, _, demande = special
    _justifier(special, "200")
    publie = publier_rapport(
        utilisateur=profils["pia"], project_id=projet.id, modele=modele_reconciliation_compte_special(),
        params=_params(projet, demande=demande.numero), tables={}, period_from=J(2026, 2, 1), period_to=FIN,
    )  # fmt: skip
    assert len(bytes(publie.seal)) == 32 and publie.values["R700/PER"] == "0"
    assert regenerer(publie).identique and publie.mapping_versions == {}


# --- la base, indépendamment du service ------------------------------------------------------


def _directement(special, **champs):
    organisation, projet, profils, accord, compte, demande = special
    return JustificationCompteSpecial.objects.create(
        org_id=organisation.id,
        compte=champs.pop("compte", compte),
        demande=champs.pop("demande", demande),
        project_id=champs.pop("project_id", projet.id),
        montant=champs.pop("montant", D("10")),
        date_soumission=J(2026, 3, 20),
        saisie_par=profils["amina"].id,
    )


def test_la_base_refuse_un_compte_non_special_meme_hors_du_service(special):
    _, projet, profils, _, _, _ = special
    designe = creer_compte_bancaire(
        utilisateur=profils["dora"], project_id=projet.id, code="CD-DJF", type="designe",
        devise="DJF", banque="BCD", numero="DJ21 0001 0000 0099 8877",
    )  # fmt: skip
    with pytest.raises(IntegrityError, match="Seul un compte spécial"):
        with transaction.atomic():
            _directement(special, compte=designe)


def test_la_base_refuse_une_justification_d_un_autre_projet(special):
    with pytest.raises(IntegrityError, match="même projet"):
        with transaction.atomic():
            _directement(special, project_id="00000000-0000-0000-0000-000000000001")


def test_la_base_refuse_un_montant_nul_ou_negatif_et_une_annulation_sans_motif(special):
    j = _justifier(special, "100")
    for montant in (D("0"), D("-1")):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _directement(special, montant=montant, demande=special[5])
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            JustificationCompteSpecial.objects.filter(pk=j.pk).update(
                annule_at=datetime.datetime.now(datetime.UTC)
            )


# --- les limites levées par D5 -----------------------------------------------------------------


def _demande_a_part(special, *, jour=14, soumise=True):
    """Une seconde demande de 100, préparée ou soumise (jamais acceptée)."""
    organisation, projet, profils, accord, _, _ = special
    from niveau1_socle.financements.models import Categorie

    biens = Categorie.objects.get(accord=accord, code="BIENS")  # SERV est déjà au plafond
    ligne = _depense(organisation, projet, accord, biens, 100, jour=jour, mois=2)
    preparee = _preparer(profils, accord, [ligne])
    return _soumettre(preparee, profils) if soumise else preparee


def test_sans_montant_la_justification_porte_sur_tout_ce_que_la_demande_retire(special):
    _, _, profils, _, compte, demande = special
    j = justifier_aupres_de_la_banque(
        utilisateur=profils["amina"], compte=compte, demande=demande, date_soumission=J(2026, 3, 20)
    )
    assert j.montant == D("300")  # la demande acceptée retire 300
    assert calculer_situation(compte, FIN, demande.numero).justifie_cette_demande == D("300")


def test_la_saisie_a_la_main_reste_possible_pour_une_justification_partielle(special):
    assert _justifier(special, "120").montant == D("120")


def test_une_demande_annulee_ne_retire_rien_et_le_defaut_est_refuse(special):
    _, _, profils, _, compte, _ = special
    annulee = _demande_a_part(special, soumise=False)
    annuler_demande(annulee, utilisateur=profils["amina"], motif="erreur de période")
    with pytest.raises(ErreurMetier, match="ne retire rien"):
        justifier_aupres_de_la_banque(utilisateur=profils["amina"], compte=compte, demande=annulee)


def test_une_demande_annulee_ne_se_justifie_pas_meme_avec_un_montant(special):
    _, _, profils, _, compte, _ = special
    annulee = _demande_a_part(special, soumise=False)
    annuler_demande(annulee, utilisateur=profils["amina"], motif="erreur de période")
    with pytest.raises(ErreurMetier, match="rejetée ou annulée ne se justifie pas"):
        justifier_aupres_de_la_banque(
            utilisateur=profils["amina"], compte=compte, demande=annulee, montant="10"
        )
    assert JustificationCompteSpecial.objects.count() == 0


def test_la_justification_de_la_demande_en_cours_peut_porter_sur_une_demande_preparee(special):
    _, _, profils, _, compte, _ = special
    preparee = _demande_a_part(special, soumise=False)
    assert preparee.status == "preparee"
    justifier_aupres_de_la_banque(
        utilisateur=profils["amina"], compte=compte, demande=preparee, montant="100",
        date_soumission=J(2026, 3, 20),
    )  # fmt: skip
    en_cours = calculer_situation(compte, FIN, preparee.numero)
    assert (en_cours.justifie_cette_demande, en_cours.justifie_precedemment) == (D("100"), 0)
    assert en_cours.justifications == [(preparee.numero, D("100"), J(2026, 3, 20), True, True)]


def test_une_demande_preparee_ne_compte_pas_parmi_les_depenses_deja_justifiees(special):
    """La ligne 5 ne compte que ce qui a été soumis à la Banque : une demande encore préparée, quand
    elle n'est pas désignée comme la demande en cours, ne justifie rien pour l'instant."""
    _, _, profils, _, compte, demande = special
    preparee = _demande_a_part(special, soumise=False)
    justifier_aupres_de_la_banque(
        utilisateur=profils["amina"], compte=compte, demande=preparee, montant="100",
        date_soumission=J(2026, 3, 20),
    )  # fmt: skip
    s = calculer_situation(compte, FIN, demande.numero)  # une AUTRE demande est en cours
    assert (s.justifie_cette_demande, s.justifie_precedemment) == (0, 0)
    assert s.justifications == [(preparee.numero, D("100"), J(2026, 3, 20), False, False)]


def test_une_demande_rejetee_apres_coup_ne_justifie_plus_rien(special):
    _, _, profils, _, compte, demande = special
    soumise = _demande_a_part(special)
    justifier_aupres_de_la_banque(
        utilisateur=profils["amina"], compte=compte, demande=soumise, montant="100",
        date_soumission=J(2026, 3, 20),
    )  # fmt: skip
    avant = calculer_situation(compte, FIN, demande.numero)
    assert avant.justifie_precedemment == D("100") and avant.justifications[0][4] is True
    rejeter_demande(soumise, utilisateur=profils["bruno"], motif="dépenses non éligibles")
    apres = calculer_situation(compte, FIN, demande.numero)
    assert apres.justifie_precedemment == 0  # la Banque l'a refusée : l'écart l'explique
    assert apres.ecart == avant.ecart + D("100")
    assert apres.justifications[0][4] is False  # toujours listée, marquée « non comptée »


def test_le_detail_est_trie_par_date_puis_par_numero(special):
    _, _, profils, _, compte, demande = special
    autre = _demande_a_part(special)
    justifier_aupres_de_la_banque(
        utilisateur=profils["amina"], compte=compte, demande=autre, montant="50",
        date_soumission=J(2026, 3, 5),
    )  # fmt: skip
    _justifier(special, "200", date_soumission=J(2026, 3, 20))
    detail = calculer_situation(compte, FIN).justifications
    assert [(d[0], d[2]) for d in detail] == [
        (autre.numero, J(2026, 3, 5)),
        (demande.numero, J(2026, 3, 20)),
    ]


def test_un_compte_et_un_accord_de_devises_differentes_sont_refuses_sans_conversion(special):
    from niveau1_socle.financements.models import CompteBancaire

    _, _, profils, _, compte, demande = special
    CompteBancaire.objects.filter(pk=compte.pk).update(devise_id="USD")
    compte.refresh_from_db()
    with pytest.raises(ErreurMetier, match=r"aucune conversion n'est faite"):  # le service, d'abord
        _justifier(special, "100")
    with pytest.raises(IntegrityError, match="même devise"):  # et la base, sans le service
        with transaction.atomic():
            _directement(special, compte=compte)
    assert JustificationCompteSpecial.objects.count() == 0
