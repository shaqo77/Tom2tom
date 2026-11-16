# ruff: noqa: F811, E501
"""Trésorerie : soldes de relevé, appariement, prévisions, disponibilités, reconstitution. L9-T05.

Contrôle du plan : l'état de reconstitution du compte désigné se rapproche du relevé bancaire, et
tout écart est explicitement justifié.
"""

import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied

from core.erreurs import ErreurMetier
from niveau1_socle.decaissements.services import accepter_demande
from niveau1_socle.financements.services import creer_compte_bancaire
from niveau1_socle.rapprochement.models import MouvementReleve
from niveau1_socle.rapprochement.services import importer_mouvements, rapprocher
from niveau1_socle.tresorerie.models import (
    AppariementDemande,
    JustificationEcart,
    PrevisionTresorerie,
    SoldeReleve,
)
from niveau1_socle.tresorerie.services import (
    annuler_appariement,
    apparier_demande,
    disponibilites,
    enregistrer_solde_releve,
    etablir_prevision,
    etat_reconstitution,
    justifier_ecart,
    previsions,
)
from tests.outils import _compte, _valeur_axe  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import _depense, _preparer, _soumettre, drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_rapprochement_bancaire_bd import GAIN, PERTE  # noqa: F401
from tests.test_rapprochement_bancaire_bd import _ligne as _ligne_banque

pytestmark = pytest.mark.django_db(transaction=True)
J = datetime.date
D = Decimal
DEBUT, FIN = J(2026, 2, 1), J(2026, 3, 31)


@pytest.fixture
def banque(drf):
    """Un compte désigné en DJF (plafond 5 000), une demande acceptée de 300, claire comptabilise."""
    organisation, projet, profils, accord, cat = drf
    designe = creer_compte_bancaire(
        utilisateur=profils["dora"], project_id=projet.id, code="CD-DJF", type="designe", devise="DJF",
        banque="BCD", numero="DJ21 0001 0000 0099 8877", plafond="5000",
    )  # fmt: skip
    ligne = _depense(organisation, projet, accord, cat["serv"], 300, jour=12, mois=2)
    demande = accepter_demande(
        _soumettre(_preparer(profils, accord, [ligne]), profils), utilisateur=profils["bruno"]
    )
    return organisation, projet, profils, designe, demande


def _drf_de(banque):
    """Accord et catégories de la demande de `banque` (l'accord DJF de la fixture `drf`)."""
    from niveau1_socle.financements.models import Accord, Categorie

    organisation, projet, profils, _, demande = banque
    accord = Accord.objects.get(pk=demande.accord_id)
    cat = {c.code.lower().replace("-", "_"): c for c in Categorie.objects.filter(accord=accord)}
    return organisation, projet, profils, accord, cat


def _importer(profils, compte, *mouvements):
    return importer_mouvements(
        utilisateur=profils["claire"], compte=compte,
        mouvements=[{"reference": r, "date": d, "montant": m} for r, d, m in mouvements],
    )[0]  # fmt: skip


def _scenario(banque):
    """Ouverture 1 000 ; +300 (avance de la demande), +50 (intérêts), −120, −30 ; clôture 1 200."""
    organisation, projet, profils, designe, demande = banque
    dora = profils["dora"]
    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=designe, date_solde=J(2026, 1, 31), solde="1000"
    )
    m0, m1, m2, m3, m4 = _importer(
        profils, designe,
        ("OUV", J(2026, 1, 15), "1000"), ("AV-1", J(2026, 2, 20), "300"), ("INT", J(2026, 3, 5), "50"),
        ("PAI-1", J(2026, 3, 10), "-120"), ("PAI-2", J(2026, 3, 15), "-30"),
    )  # fmt: skip
    mouvements = sorted(
        MouvementReleve.objects.filter(compte=designe), key=lambda m: m.date_operation
    )
    lignes = [
        _ligne_banque(
            organisation,
            projet,
            designe,
            m.montant,
            jour=m.date_operation.day,
            mois=m.date_operation.month,
        )
        for m in mouvements
    ]
    for ligne, mouvement in zip(lignes, mouvements, strict=True):
        rapprocher(
            utilisateur=profils["claire"], compte=designe, lignes=[ligne], mouvements=[mouvement]
        )
    avance = next(m for m in mouvements if m.reference == "AV-1")
    apparier_demande(utilisateur=profils["amina"], mouvement=avance, demande=demande)
    return dora, mouvements


def test_l_etat_de_reconstitution_se_rapproche_du_releve_et_chaque_ecart_est_justifie(banque):
    """Le contrôle du plan, de bout en bout."""
    _, _, profils, designe, demande = banque
    _scenario(banque)
    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=designe, date_solde=FIN, solde="1200"
    )
    etat = etat_reconstitution(
        utilisateur=profils["amina"], compte=designe, date_debut=DEBUT, date_fin=FIN
    )
    assert etat.complet and etat.ouverture == D("1000")
    assert etat.avances_recues == [(demande.numero, D("300"))]
    assert (etat.autres_encaissements, etat.decaissements) == (D("50"), D("150"))
    assert etat.cloture_calculee == etat.cloture_releve == D("1200")
    assert (etat.ecart_releve, etat.ecart_comptable) == (0, 0) and etat.justifie
    assert etat.solde_comptable == D("1200") and not etat.depasse_plafond

    # Le relevé de clôture diffère de 5 : l'écart apparaît, non justifié.
    autre = etat_reconstitution(
        utilisateur=profils["amina"], compte=designe, date_debut=DEBUT, date_fin=J(2026, 3, 30)
    )
    assert autre.manques == ["cloture"] and not autre.justifie and autre.ecart_releve is None


def test_un_ecart_de_releve_reste_non_justifie_tant_que_les_justifications_ne_le_couvrent_pas_au_centime(
    banque,
):
    _, _, profils, designe, _ = banque
    _scenario(banque)
    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=designe, date_solde=FIN, solde="1194.50"
    )

    def voir():
        return etat_reconstitution(
            utilisateur=profils["amina"], compte=designe, date_debut=DEBUT, date_fin=FIN
        )

    etat = voir()
    assert etat.ecart_releve == D("-5.50") and not etat.justifie
    assert etat.non_justifie_releve == D("-5.50")
    justifier_ecart(
        utilisateur=profils["bruno"],
        compte=designe,
        date_debut=DEBUT,
        date_fin=FIN,
        cible="releve",
        montant="-3",
        explication="Frais bancaires du 28/03",
    )
    etat = voir()
    assert etat.non_justifie_releve == D("-2.50") and not etat.justifie
    justifier_ecart(
        utilisateur=profils["bruno"],
        compte=designe,
        date_debut=DEBUT,
        date_fin=FIN,
        cible="releve",
        montant="-2.49",
        explication="Commission de change",
    )
    assert (
        voir().non_justifie_releve == D("-0.01") and not voir().justifie
    )  # un centime non expliqué suffit
    justifier_ecart(
        utilisateur=profils["bruno"],
        compte=designe,
        date_debut=DEBUT,
        date_fin=FIN,
        cible="releve",
        montant="-0.01",
        explication="Arrondi du relevé",
    )
    # L'écart du relevé est expliqué ; l'écart comptable (relevé 1194,50 contre grand livre 1200) ne l'est pas.
    etat = voir()
    assert (
        etat.non_justifie_releve == 0 and etat.ecart_comptable == D("-5.50") and not etat.justifie
    )
    justifier_ecart(
        utilisateur=profils["bruno"],
        compte=designe,
        date_debut=DEBUT,
        date_fin=FIN,
        cible="comptable",
        montant="-5.50",
        explication="Frais non encore comptabilisés",
    )
    assert voir().justifie


def test_la_justification_exige_une_explication_une_habilitation_et_ne_se_modifie_pas(banque):
    _, _, profils, designe, _ = banque
    base = {"compte": designe, "date_debut": DEBUT, "date_fin": FIN, "cible": "releve"}
    with pytest.raises(PermissionDenied):  # amina saisit mais ne valide pas
        justifier_ecart(utilisateur=profils["amina"], montant="-1", explication="x", **base)
    with pytest.raises(ErreurMetier):
        justifier_ecart(utilisateur=profils["bruno"], montant="-1", explication=" ", **base)
    with pytest.raises(ErreurMetier):
        justifier_ecart(utilisateur=profils["bruno"], montant="0", explication="x", **base)
    with pytest.raises(ErreurMetier):
        justifier_ecart(
            utilisateur=profils["bruno"],
            montant="-1",
            explication="x",
            **(base | {"cible": "autre"}),
        )
    j = justifier_ecart(utilisateur=profils["bruno"], montant="-1", explication="Frais", **base)
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        JustificationEcart.objects.filter(pk=j.pk).update(montant=D("-9"))
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        JustificationEcart.objects.filter(pk=j.pk).delete()


def test_l_etat_est_incomplet_sans_solde_d_ouverture_ni_de_cloture_et_reserve_au_compte_designe(
    banque,
):
    organisation, projet, profils, designe, _ = banque
    etat = etat_reconstitution(
        utilisateur=profils["amina"], compte=designe, date_debut=DEBUT, date_fin=FIN
    )
    assert etat.manques == ["ouverture", "cloture"] and not etat.complet and not etat.justifie
    assert etat.cloture_calculee is None and etat.ecart_releve is None
    operationnel = creer_compte_bancaire(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code="CO",
        type="operationnel",
        devise="DJF",
        banque="B",
        numero="X-1",
    )
    with pytest.raises(ErreurMetier):
        etat_reconstitution(
            utilisateur=profils["amina"], compte=operationnel, date_debut=DEBUT, date_fin=FIN
        )


def test_l_etat_n_expose_jamais_le_numero_complet_du_compte(banque):
    _, _, profils, designe, _ = banque
    etat = etat_reconstitution(
        utilisateur=profils["amina"], compte=designe, date_debut=DEBUT, date_fin=FIN
    )
    assert etat.compte_masque.endswith("8877") and "0099" not in etat.compte_masque
    assert "DJ21 0001 0000 0099 8877" not in repr(etat) and "DJ21 0001" not in repr(
        disponibilites(utilisateur=profils["amina"], project_id=designe.project_id, jour=FIN)
    )


def test_le_plafond_du_compte_designe_est_signale(banque):
    _, _, profils, designe, _ = banque
    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=designe, date_solde=J(2026, 1, 31), solde="4000"
    )
    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=designe, date_solde=FIN, solde="5000.01"
    )
    etat = etat_reconstitution(
        utilisateur=profils["amina"], compte=designe, date_debut=DEBUT, date_fin=FIN
    )
    assert etat.depasse_plafond and etat.plafond == D("5000")
    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=designe, date_solde=J(2026, 4, 30), solde="5000"
    )
    assert not etat_reconstitution(
        utilisateur=profils["amina"],
        compte=designe,
        date_debut=J(2026, 4, 1),
        date_fin=J(2026, 4, 30),
    ).depasse_plafond


def test_un_solde_de_releve_est_unique_par_jour_et_en_ajout_seul(banque):
    _, _, profils, designe, _ = banque
    s = enregistrer_solde_releve(
        utilisateur=profils["amina"],
        compte=designe,
        date_solde=J(2026, 1, 31),
        solde="10",
        reference="REL-01",
    )
    with pytest.raises(ErreurMetier):
        enregistrer_solde_releve(
            utilisateur=profils["amina"], compte=designe, date_solde=J(2026, 1, 31), solde="11"
        )
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        SoldeReleve.objects.filter(pk=s.pk).update(solde=D("99"))
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        SoldeReleve.objects.filter(pk=s.pk).delete()
    for solde in ("abc", 1.5):
        with pytest.raises(ErreurMetier):
            enregistrer_solde_releve(
                utilisateur=profils["amina"], compte=designe, date_solde=J(2026, 2, 28), solde=solde
            )


def test_un_mouvement_ne_s_apparie_qu_a_une_seule_demande(banque):
    organisation, projet, profils, designe, demande = banque
    [m] = _importer(profils, designe, ("AV-1", J(2026, 2, 20), "100"))
    premier = apparier_demande(utilisateur=profils["amina"], mouvement=m, demande=demande)
    with pytest.raises(ErreurMetier) as e:
        apparier_demande(utilisateur=profils["amina"], mouvement=m, demande=demande)
    assert "AV-1" in str(e.value)
    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
    ):  # contournement direct : l'index unique le refuse
        AppariementDemande.objects.create(
            org_id=m.org_id, mouvement=m, demande=demande, project_id=m.project_id, apparie_par=m.id
        )
    # Annuler (motivé) libère le mouvement ; l'historique garde l'appariement annulé.
    with pytest.raises(ErreurMetier):
        annuler_appariement(utilisateur=profils["amina"], appariement=premier, motif=" ")
    annuler_appariement(utilisateur=profils["amina"], appariement=premier, motif="Mauvaise demande")
    with pytest.raises(ErreurMetier):
        annuler_appariement(utilisateur=profils["amina"], appariement=premier, motif="encore")
    assert (
        apparier_demande(utilisateur=profils["amina"], mouvement=m, demande=demande).id
        != premier.id
    )
    assert AppariementDemande.objects.filter(mouvement=m).count() == 2


def test_les_appariements_d_une_demande_ne_depassent_pas_son_montant_et_exigent_un_encaissement(
    banque,
):
    _, _, profils, designe, demande = banque  # la demande retire 300
    a, b, sortie = _importer(
        profils,
        designe,
        ("E1", J(2026, 2, 20), "200"),
        ("E2", J(2026, 2, 21), "100.01"),
        ("S1", J(2026, 2, 22), "-50"),
    )
    apparier_demande(utilisateur=profils["amina"], mouvement=a, demande=demande)
    with pytest.raises(ErreurMetier) as e:  # 200 + 100,01 > 300
        apparier_demande(utilisateur=profils["amina"], mouvement=b, demande=demande)
    assert "300" in str(e.value)
    with pytest.raises(ErreurMetier):  # un décaissement ne s'apparie pas à une demande
        apparier_demande(utilisateur=profils["amina"], mouvement=sortie, demande=demande)


def test_la_base_refuse_un_appariement_sur_une_demande_non_payee_ou_d_une_autre_devise(banque):
    organisation, projet, profils, designe, demande = banque
    from niveau1_socle.decaissements.models import DemandeRetrait

    usd = creer_compte_bancaire(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code="CD-USD",
        type="designe",
        devise="USD",
        banque="B",
        numero="U-1",
    )
    [m_usd] = _importer(profils, usd, ("U1", J(2026, 2, 20), "10"))
    with pytest.raises(ErreurMetier):  # compte en USD, accord en DJF
        apparier_demande(utilisateur=profils["amina"], mouvement=m_usd, demande=demande)
    # Une demande seulement préparée ne reçoit pas d'encaissement.
    from tests.test_demandes_retrait_bd import _depense, _preparer

    _, _, _, accord, cat = _drf_de(banque)
    autre = _depense(organisation, projet, accord, cat["biens_a"], 100, jour=14, mois=2)
    preparee = _preparer(profils, accord, [autre])
    assert preparee.status == "preparee" and DemandeRetrait.objects.filter(pk=preparee.pk).exists()
    [m] = _importer(profils, designe, ("E9", J(2026, 2, 20), "10"))
    with pytest.raises(ErreurMetier):
        apparier_demande(utilisateur=profils["amina"], mouvement=m, demande=preparee)


def test_les_previsions_se_revisent_sans_ecraser_et_se_lisent_par_periode_et_par_axe(banque):
    organisation, projet, profils, designe, _ = banque
    amina = profils["amina"]
    comp_a = _valeur_axe(organisation.id, "COMP-A")
    comp_b = _valeur_axe(organisation.id, "COMP-B")
    base = {"utilisateur": amina, "project_id": projet.id, "devise": "DJF", "annee": 2026}
    etablir_prevision(**base, mois=4, encaissements="1000", decaissements="400", axe=comp_a)
    etablir_prevision(**base, mois=4, encaissements="500", decaissements="100", axe=comp_b)
    etablir_prevision(**base, mois=5, encaissements="0", decaissements="250.25", axe=comp_a)
    with pytest.raises(ErreurMetier):  # une révision se motive
        etablir_prevision(**base, mois=4, encaissements="1200", decaissements="400", axe=comp_a)
    rev2 = etablir_prevision(
        **base,
        mois=4,
        encaissements="1200",
        decaissements="450",
        axe=comp_a,
        motif="Nouvel accord de décaissement",
    )
    assert (
        rev2.revision == 2 and PrevisionTresorerie.objects.filter(axe=comp_a, mois=4).count() == 2
    )
    par_axe = previsions(utilisateur=amina, project_id=projet.id, annee=2026, mois=4, nombre_mois=2)
    assert [(p.mois, p.axe, p.encaissements, p.decaissements) for p in par_axe] == [
        (4, "COMP-A", D("1200"), D("450")),
        (4, "COMP-B", D("500"), D("100")),
        (5, "COMP-A", D("0"), D("250.25")),
    ]
    confondus = previsions(
        utilisateur=amina, project_id=projet.id, annee=2026, mois=4, nombre_mois=2, par_axe=False
    )
    assert [(p.mois, p.encaissements, p.decaissements, p.net) for p in confondus] == [
        (4, D("1700"), D("550"), D("1150")),
        (5, D("0"), D("250.25"), D("-250.25")),
    ]
    assert (
        previsions(utilisateur=amina, project_id=projet.id, annee=2026, mois=6, nombre_mois=1) == []
    )


def test_les_previsions_ne_melangent_jamais_les_devises_et_la_base_tient_la_numerotation(banque):
    organisation, projet, profils, _, _ = banque
    amina = profils["amina"]
    base = {"utilisateur": amina, "project_id": projet.id, "annee": 2026, "mois": 4}
    etablir_prevision(**base, devise="DJF", encaissements="1000")
    etablir_prevision(**base, devise="USD", encaissements="10")
    lignes = previsions(utilisateur=amina, project_id=projet.id, annee=2026, mois=4, nombre_mois=1)
    assert [(p.devise, p.encaissements) for p in lignes] == [("DJF", D("1000")), ("USD", D("10"))]
    with pytest.raises(IntegrityError), transaction.atomic():  # un trou de révision (3 sans 2)
        PrevisionTresorerie.objects.create(
            org_id=organisation.id, project_id=projet.id, devise="DJF", annee=2026, mois=4, revision=3,
            motif="x", etablie_par=amina.id,
        )  # fmt: skip
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        PrevisionTresorerie.objects.filter(devise="DJF").update(encaissements=D("1"))
    for mois in (0, 13):
        with pytest.raises(ErreurMetier):
            etablir_prevision(**(base | {"mois": mois}), devise="DJF")
    with pytest.raises(ErreurMetier):
        etablir_prevision(**base, devise="DJF", encaissements="-1")


def test_les_disponibilites_sont_ventilees_par_devise_avec_la_marge_du_plafond(banque):
    organisation, projet, profils, designe, _ = banque
    usd = creer_compte_bancaire(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code="CO-USD",
        type="operationnel",
        devise="USD",
        banque="B",
        numero="U-2",
    )
    _importer(profils, designe, ("A", J(2026, 2, 10), "700"), ("B", J(2026, 2, 12), "-100"))
    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=designe, date_solde=J(2026, 1, 31), solde="1000"
    )
    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=usd, date_solde=J(2026, 1, 31), solde="50"
    )
    _ligne_banque(organisation, projet, designe, 1000, jour=15, mois=1)
    d = disponibilites(utilisateur=profils["amina"], project_id=projet.id, jour=J(2026, 2, 28))
    positions = {c.code: c for c in d.comptes}
    assert positions["CD-DJF"].solde_releve == D("1600") and positions[
        "CD-DJF"
    ].solde_comptable == D("1000")
    assert positions["CD-DJF"].marge_plafond == D("3400") and positions["CO-USD"].solde_releve == D(
        "50"
    )
    assert positions["CO-USD"].marge_plafond is None
    assert d.totaux_par_devise() == {
        "DJF": {"comptable": D("1000"), "releve": D("1600")},
        "USD": {"comptable": D("0"), "releve": D("50")},
    }
    sans_releve = disponibilites(
        utilisateur=profils["amina"], project_id=projet.id, jour=J(2026, 1, 1)
    )
    assert {c.solde_releve for c in sans_releve.comptes} == {None}


def test_habilitations_de_la_tresorerie(banque):
    _, projet, profils, designe, demande = banque
    with pytest.raises(PermissionDenied):  # dora paramètre mais ne saisit pas
        enregistrer_solde_releve(
            utilisateur=profils["dora"], compte=designe, date_solde=J(2026, 2, 28), solde="1"
        )
    with pytest.raises(PermissionDenied):
        etablir_prevision(
            utilisateur=profils["dora"], project_id=projet.id, devise="DJF", annee=2026, mois=4
        )
    with pytest.raises(PermissionDenied):
        previsions(
            utilisateur=profils["nadia"] if False else _sans_droit(projet),
            project_id=projet.id,
            annee=2026,
            mois=4,
            nombre_mois=1,
        )


def _sans_droit(projet):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user("zoe", password="x", org_id=projet.org_id)


def test_un_mouvement_du_jour_du_dernier_solde_n_est_pas_compte_deux_fois(banque):
    """Le solde du relevé d'un jour INCLUT déjà les mouvements de ce jour."""
    _, _, profils, designe, _ = banque
    from niveau1_socle.tresorerie.services import solde_releve_a

    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=designe, date_solde=J(2026, 2, 10), solde="1000"
    )
    _importer(
        profils, designe, ("DU-JOUR", J(2026, 2, 10), "250"), ("LENDEMAIN", J(2026, 2, 11), "40")
    )
    assert solde_releve_a(designe, J(2026, 2, 10)) == (D("1000"), J(2026, 2, 10))
    assert solde_releve_a(designe, J(2026, 2, 11)) == (D("1040"), J(2026, 2, 10))
    assert solde_releve_a(designe, J(2026, 2, 9)) == (None, None)


def test_le_dernier_solde_enregistre_sert_de_base_et_la_prevision_courante_est_la_derniere_revision(
    banque,
):
    organisation, projet, profils, designe, _ = banque
    from niveau1_socle.tresorerie.services import solde_releve_a

    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=designe, date_solde=J(2026, 1, 10), solde="100"
    )
    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=designe, date_solde=J(2026, 2, 10), solde="900"
    )
    assert solde_releve_a(designe, J(2026, 3, 1)) == (D("900"), J(2026, 2, 10))
    assert solde_releve_a(designe, J(2026, 1, 20)) == (D("100"), J(2026, 1, 10))
    base = {
        "utilisateur": profils["amina"],
        "project_id": projet.id,
        "devise": "DJF",
        "annee": 2026,
        "mois": 7,
    }
    etablir_prevision(**base, encaissements="10")
    etablir_prevision(**base, encaissements="20", motif="r2")
    etablir_prevision(**base, encaissements="30", motif="r3")
    [courante] = previsions(
        utilisateur=profils["amina"], project_id=projet.id, annee=2026, mois=7, nombre_mois=1
    )
    assert courante.encaissements == D("30")
