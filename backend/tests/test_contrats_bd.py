# ruff: noqa: F811, E501
"""Contrats, avenants versionnés, garanties et assurances, échéances et alertes. Voir L9-T03.

Le contrat porte sa valeur initiale, chaque avenant la suivante ; la base tient la numérotation
sans trou, l'ajout seul et la règle de non-objection même pour qui contournerait le service.
"""

import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied

from core.erreurs import CodeErreur, ErreurMetier
from niveau1_socle.marches.avis import demander_avis, enregistrer_decision
from niveau1_socle.marches.contrats import (
    ajouter_avenant,
    alertes_echeances,
    cloturer_garantie,
    conclure_contrat,
    date_fin_courante,
    enregistrer_garantie,
    montant_courant,
)
from niveau1_socle.marches.models import AvenantContrat, Contrat, Garantie
from niveau1_socle.marches.plan import avancer_ligne
from niveau1_socle.referentiels.models import Tiers
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_plan_passation_bd import _ligne, pas  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
J = datetime.date
D = Decimal


def _attribuer(pas, ligne):
    amina = pas[2]["amina"]
    ligne = avancer_ligne(utilisateur=amina, ligne=ligne, statut="lance", date_effet=J(2026, 3, 2))
    return avancer_ligne(
        utilisateur=amina, ligne=ligne, statut="attribue", date_effet=J(2026, 5, 2)
    )


def _tiers(pas):
    return Tiers.objects.create(
        org_id=pas[0].id, code="F1", nature="fournisseur", nom="Fournisseur 1"
    )


def _contrat(pas, ligne=None, reference="C-001", **champs):
    ligne = ligne or _attribuer(pas, _ligne(pas, "M-001", "120000", "AON"))
    donnees = {
        "utilisateur": pas[2]["amina"],
        "ligne": ligne,
        "reference": reference,
        "tiers": Tiers.objects.filter(code="F1").first() or _tiers(pas),
        "objet": "Fourniture de véhicules",
        "montant": "118000.50",
        "date_signature": J(2026, 6, 1),
        "date_debut": J(2026, 6, 15),
        "date_fin": J(2026, 12, 15),
    } | champs
    return conclure_contrat(**donnees)


def _soumis(pas):
    """Un marché AOI (non-objection exigée), attribué, dont l'avis du dossier est obtenu."""
    amina = pas[2]["amina"]
    ligne = _ligne(pas, "M-900", "900000", "AOI")
    avis = demander_avis(
        utilisateur=amina, ligne=ligne, objet="dossier", date_demande=J(2026, 3, 1)
    )
    enregistrer_decision(utilisateur=amina, avis=avis, statut="obtenu", date_decision=J(2026, 3, 9))
    return _attribuer(pas, ligne)


def _avis_avenant(pas, ligne, obtenu=True, jour=None):
    jour = jour or J(2026, 7, 1)
    amina = pas[2]["amina"]
    avis = demander_avis(utilisateur=amina, ligne=ligne, objet="avenant", date_demande=jour)
    if obtenu:
        avis = enregistrer_decision(
            utilisateur=amina,
            avis=avis,
            statut="obtenu",
            date_decision=jour + datetime.timedelta(days=5),
        )
    return avis


def test_un_contrat_se_conclut_sur_un_marche_attribue_dans_sa_devise(pas):
    amina = pas[2]["amina"]
    with pytest.raises(ErreurMetier) as e:  # la ligne est encore « prévue »
        _contrat(pas, ligne=_ligne(pas, "M-050", "120000", "AON"))
    assert e.value.code == CodeErreur.TRANSITION_INTERDITE
    contrat = _contrat(pas)
    assert contrat.devise == "USD" and contrat.montant_initial == D("118000.50")
    assert montant_courant(contrat) == D("118000.50")
    assert date_fin_courante(contrat) == J(2026, 12, 15)
    with pytest.raises(ErreurMetier):  # un seul contrat par marché
        _contrat(pas, ligne=contrat.ligne, reference="C-002")
    assert amina.id


def test_un_marche_soumis_a_avis_refuse_le_contrat_sans_avis_et_l_accepte_une_fois_obtenu(pas):
    amina = pas[2]["amina"]
    ligne = _attribuer(pas, _ligne(pas, "M-900", "900000", "AOI"))
    with pytest.raises(ErreurMetier) as e:
        _contrat(pas, ligne=ligne, montant="900000")
    assert "M-900" in str(e.value)
    avis = demander_avis(
        utilisateur=amina, ligne=ligne, objet="dossier", date_demande=J(2026, 3, 1)
    )
    with pytest.raises(ErreurMetier):
        _contrat(pas, ligne=ligne, montant="900000")
    enregistrer_decision(utilisateur=amina, avis=avis, statut="obtenu", date_decision=J(2026, 3, 9))
    assert _contrat(pas, ligne=ligne, montant="900000").id


def test_la_base_refuse_un_contrat_sans_avis_ou_sur_un_marche_non_attribue(pas):
    tiers = _tiers(pas)

    def direct(ligne, ref):
        return Contrat.objects.create(
            org_id=ligne.org_id, ligne=ligne, project_id=ligne.project_id, reference=ref, tiers=tiers,
            objet="x", montant_initial=1000, devise="USD", date_signature=J(2026, 6, 1),
            date_debut=J(2026, 6, 1), date_fin_initiale=J(2026, 7, 1),
        )  # fmt: skip

    with pytest.raises(IntegrityError), transaction.atomic():  # non attribué
        direct(_ligne(pas, "M-001", "120000", "AON"), "C-X")
    with pytest.raises(IntegrityError), transaction.atomic():  # soumis, sans avis
        direct(_attribuer(pas, _ligne(pas, "M-900", "900000", "AOI")), "C-Y")


def test_un_contrat_ne_se_modifie_ni_ne_se_supprime(pas):
    contrat = _contrat(pas)
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        Contrat.objects.filter(pk=contrat.pk).update(montant_initial=D("1"))
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        Contrat.objects.filter(pk=contrat.pk).delete()


def test_les_avenants_portent_la_valeur_suivante_et_se_numerotent_sans_trou(pas):
    amina = pas[2]["amina"]
    contrat = _contrat(pas)
    a1 = ajouter_avenant(
        utilisateur=amina, contrat=contrat, date_effet=J(2026, 8, 1), montant="130000",
        date_fin=J(2027, 1, 31), motif="Travaux supplémentaires",
    )  # fmt: skip
    a2 = ajouter_avenant(
        utilisateur=amina, contrat=contrat, date_effet=J(2026, 9, 1), montant="125000",
        date_fin=J(2027, 3, 31), motif="Réduction du périmètre",
    )  # fmt: skip
    assert (a1.numero, a2.numero) == (1, 2)
    contrat.refresh_from_db()
    assert montant_courant(contrat) == D("125000") and date_fin_courante(contrat) == J(2027, 3, 31)
    assert contrat.montant_initial == D("118000.50")  # le contrat lui-même ne bouge jamais
    assert [a.numero for a in contrat.avenants.order_by("numero")] == [1, 2]


def test_un_avenant_exige_un_motif_ne_remonte_pas_le_temps_et_garde_des_dates_coherentes(pas):
    amina = pas[2]["amina"]
    contrat = _contrat(pas)
    base = {
        "utilisateur": amina,
        "contrat": contrat,
        "montant": "130000",
        "date_fin": J(2027, 1, 31),
    }
    with pytest.raises(ErreurMetier):
        ajouter_avenant(**base, date_effet=J(2026, 8, 1), motif=" ")
    with pytest.raises(ErreurMetier):  # avant la signature
        ajouter_avenant(**base, date_effet=J(2026, 5, 31), motif="x")
    with pytest.raises(ErreurMetier):  # fin avant le début
        ajouter_avenant(**(base | {"date_fin": J(2026, 6, 1)}), date_effet=J(2026, 8, 1), motif="x")
    ajouter_avenant(**base, date_effet=J(2026, 8, 1), motif="x")
    with pytest.raises(ErreurMetier):  # avant l'avenant précédent
        ajouter_avenant(**base, date_effet=J(2026, 7, 1), motif="y")


def test_la_base_tient_la_numerotation_et_l_ajout_seul_des_avenants(pas):
    contrat = _contrat(pas)

    def direct(numero):
        return AvenantContrat.objects.create(
            org_id=contrat.org_id, contrat=contrat, project_id=contrat.project_id, numero=numero,
            date_effet=J(2026, 8, 1), montant=1000, date_fin=J(2027, 1, 1), motif="x", cree_par=contrat.id,
        )  # fmt: skip

    with pytest.raises(IntegrityError), transaction.atomic():  # un trou : 2 sans 1
        direct(2)
    avenant = direct(1)
    with pytest.raises(IntegrityError), transaction.atomic():  # un doublon
        direct(1)
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        AvenantContrat.objects.filter(pk=avenant.pk).update(montant=D("5"))
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        AvenantContrat.objects.filter(pk=avenant.pk).delete()


def test_un_avenant_sur_un_marche_soumis_s_appuie_sur_un_avis_avenant_obtenu_et_inutilise(pas):
    amina = pas[2]["amina"]
    ligne = _soumis(pas)
    contrat = _contrat(pas, ligne=ligne, montant="900000")
    base = {
        "utilisateur": amina, "contrat": contrat, "montant": "950000", "date_fin": J(2027, 1, 31),
        "motif": "Extension",
    }  # fmt: skip
    with pytest.raises(ErreurMetier):  # sans avis
        ajouter_avenant(**base, date_effet=J(2026, 8, 1))
    attente = _avis_avenant(pas, ligne, obtenu=False)
    with pytest.raises(ErreurMetier):  # avis seulement demandé
        ajouter_avenant(**base, date_effet=J(2026, 8, 1), avis=attente)
    obtenu = _avis_avenant(pas, ligne, obtenu=True, jour=J(2026, 7, 2))
    with pytest.raises(ErreurMetier):  # mauvais objet : l'avis du dossier ne couvre pas un avenant
        dossier = ligne.avis.exclude(objet="avenant").first()
        ajouter_avenant(**base, date_effet=J(2026, 8, 1), avis=dossier)
    premier = ajouter_avenant(**base, date_effet=J(2026, 8, 1), avis=obtenu)
    assert premier.avis_id == obtenu.id
    with pytest.raises(ErreurMetier):  # un avis ne sert qu'une fois
        ajouter_avenant(**(base | {"montant": "960000"}), date_effet=J(2026, 9, 1), avis=obtenu)


def test_la_base_refuse_un_avenant_sans_avis_sur_un_marche_soumis(pas):
    ligne = _soumis(pas)
    contrat = _contrat(pas, ligne=ligne, montant="900000")
    with pytest.raises(IntegrityError), transaction.atomic():
        AvenantContrat.objects.create(
            org_id=contrat.org_id, contrat=contrat, project_id=contrat.project_id, numero=1,
            date_effet=J(2026, 8, 1), montant=1000, date_fin=J(2027, 1, 1), motif="x", cree_par=contrat.id,
        )  # fmt: skip


def test_un_avis_avenant_ne_bloque_ni_l_engagement_ni_le_contrat(pas):
    """Un avis « avenant » en attente concerne la vie du contrat, pas l'engagement du marché."""
    from niveau1_socle.marches.avis import avis_suffisant

    ligne = _soumis(pas)
    _avis_avenant(pas, ligne, obtenu=False)
    assert avis_suffisant(ligne)
    assert _contrat(pas, ligne=ligne, montant="900000").id


def test_un_marche_signe_ne_recoit_plus_de_demande_que_pour_un_avenant(pas):
    amina = pas[2]["amina"]
    ligne = avancer_ligne(
        utilisateur=amina, ligne=_soumis(pas), statut="signe", date_effet=J(2026, 6, 1)
    )
    with pytest.raises(ErreurMetier):
        demander_avis(utilisateur=amina, ligne=ligne, objet="contrat", date_demande=J(2026, 6, 2))
    assert demander_avis(
        utilisateur=amina, ligne=ligne, objet="avenant", date_demande=J(2026, 6, 2)
    ).id


def test_une_garantie_suit_la_devise_du_contrat_et_se_cloture_une_seule_fois(pas):
    amina = pas[2]["amina"]
    contrat = _contrat(pas)
    g = enregistrer_garantie(
        utilisateur=amina, contrat=contrat, type_garantie="bonne_execution", emetteur="Banque X",
        reference="GBE-1", montant="11800", date_emission=J(2026, 6, 1), date_echeance=J(2026, 12, 31),
    )  # fmt: skip
    assert g.devise == "USD" and g.statut == "active"
    with pytest.raises(ErreurMetier):  # un appel se motive
        cloturer_garantie(
            utilisateur=amina, garantie=g, statut="appelee", date_cloture=J(2026, 7, 1)
        )
    g = cloturer_garantie(
        utilisateur=amina, garantie=g, statut="liberee", date_cloture=J(2027, 1, 5)
    )
    assert g.statut == "liberee" and g.date_cloture == J(2027, 1, 5)
    with pytest.raises(ErreurMetier) as e:
        cloturer_garantie(
            utilisateur=amina, garantie=g, statut="appelee", date_cloture=J(2027, 1, 6), note="x"
        )
    assert e.value.code == CodeErreur.TRANSITION_INTERDITE
    with pytest.raises(ErreurMetier):  # type et dates
        enregistrer_garantie(
            utilisateur=amina, contrat=contrat, type_garantie="caution", emetteur="B", reference="G2",
            montant="1", date_emission=J(2026, 6, 1), date_echeance=J(2026, 7, 1),
        )  # fmt: skip
    with pytest.raises(ErreurMetier):
        enregistrer_garantie(
            utilisateur=amina, contrat=contrat, type_garantie="avance", emetteur="B", reference="G3",
            montant="1", date_emission=J(2026, 7, 1), date_echeance=J(2026, 6, 1),
        )  # fmt: skip
    with pytest.raises(ErreurMetier):  # même référence sur le même contrat
        enregistrer_garantie(
            utilisateur=amina, contrat=contrat, type_garantie="avance", emetteur="B", reference="GBE-1",
            montant="1", date_emission=J(2026, 6, 1), date_echeance=J(2026, 7, 1),
        )  # fmt: skip


def test_la_base_fige_une_garantie_hors_de_sa_cloture(pas):
    amina = pas[2]["amina"]
    contrat = _contrat(pas)
    g = enregistrer_garantie(
        utilisateur=amina, contrat=contrat, type_garantie="assurance", emetteur="Assureur", reference="AS-1",
        montant="5000", date_emission=J(2026, 6, 1), date_echeance=J(2026, 12, 31),
    )  # fmt: skip
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        Garantie.objects.filter(pk=g.pk).update(date_echeance=J(2030, 1, 1))
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        Garantie.objects.filter(pk=g.pk).delete()
    cloturer_garantie(utilisateur=amina, garantie=g, statut="liberee", date_cloture=J(2026, 9, 1))
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        Garantie.objects.filter(pk=g.pk).update(statut="active", date_cloture=None)


def test_les_alertes_listent_garanties_et_contrats_du_plus_urgent_au_moins_urgent(pas):
    amina = pas[2]["amina"]
    contrat = _contrat(pas)  # fin initiale 2026-12-15
    for ref, echeance in (("G-A", J(2026, 7, 10)), ("G-B", J(2026, 8, 30)), ("G-C", J(2027, 6, 1))):
        enregistrer_garantie(
            utilisateur=amina, contrat=contrat, type_garantie="bonne_execution", emetteur="B",
            reference=ref, montant="100", date_emission=J(2026, 6, 1), date_echeance=echeance,
        )  # fmt: skip
    liberee = enregistrer_garantie(
        utilisateur=amina, contrat=contrat, type_garantie="avance", emetteur="B", reference="G-L",
        montant="100", date_emission=J(2026, 6, 1), date_echeance=J(2026, 7, 1),
    )  # fmt: skip
    cloturer_garantie(
        utilisateur=amina, garantie=liberee, statut="liberee", date_cloture=J(2026, 6, 20)
    )
    alertes = alertes_echeances(
        utilisateur=amina, project_id=pas[1].id, jour=J(2026, 8, 1), horizon_jours=30
    )
    assert [(a.reference, a.etat, a.jours_restants) for a in alertes] == [
        ("G-A", "depassee", -22),
        ("G-B", "proche", 29),
    ]
    large = alertes_echeances(
        utilisateur=amina, project_id=pas[1].id, jour=J(2026, 8, 1), horizon_jours=200
    )
    assert [a.reference for a in large] == ["G-A", "G-B", "C-001"]  # le contrat finit le 15/12
    assert (
        alertes_echeances(
            utilisateur=amina, project_id=pas[1].id, jour=J(2026, 8, 1), horizon_jours=0
        )[0].reference
        == "G-A"
    )


def test_une_alerte_de_contrat_suit_la_date_de_fin_de_son_dernier_avenant(pas):
    amina = pas[2]["amina"]
    contrat = _contrat(pas)  # fin 2026-12-15
    jour = J(2026, 12, 1)
    assert [
        a.reference
        for a in alertes_echeances(
            utilisateur=amina, project_id=pas[1].id, jour=jour, horizon_jours=30
        )
    ] == ["C-001"]
    ajouter_avenant(
        utilisateur=amina, contrat=contrat, date_effet=J(2026, 8, 1), montant="130000",
        date_fin=J(2027, 6, 30), motif="Prolongation",
    )  # fmt: skip
    assert (
        alertes_echeances(utilisateur=amina, project_id=pas[1].id, jour=jour, horizon_jours=30)
        == []
    )


def test_l_horizon_est_valide_et_les_habilitations_exigees(pas):
    profils = pas[2]
    contrat = _contrat(pas)
    for horizon in (-1, 1.5, None):
        with pytest.raises(ErreurMetier):
            alertes_echeances(
                utilisateur=profils["amina"],
                project_id=pas[1].id,
                jour=J(2026, 8, 1),
                horizon_jours=horizon,
            )
    with pytest.raises(PermissionDenied):  # dora paramètre mais ne saisit pas
        ajouter_avenant(
            utilisateur=profils["dora"], contrat=contrat, date_effet=J(2026, 8, 1), montant="1",
            date_fin=J(2027, 1, 1), motif="x",
        )  # fmt: skip
    with pytest.raises(PermissionDenied):
        enregistrer_garantie(
            utilisateur=profils["dora"], contrat=contrat, type_garantie="avance", emetteur="B", reference="G",
            montant="1", date_emission=J(2026, 6, 1), date_echeance=J(2026, 7, 1),
        )  # fmt: skip


def test_un_avis_ne_se_joint_pas_a_un_avenant_d_un_marche_non_soumis(pas):
    soumis = _soumis(pas)  # fournit un avis « avenant » d'un autre marché
    autre_avis = _avis_avenant(pas, soumis)
    contrat = _contrat(pas)  # marché AON : non soumis à non-objection
    with pytest.raises(ErreurMetier) as e:
        ajouter_avenant(
            utilisateur=pas[2]["amina"], contrat=contrat, date_effet=J(2026, 8, 1), montant="130000",
            date_fin=J(2027, 1, 31), motif="x", avis=autre_avis,
        )  # fmt: skip
    assert "C-001" in str(e.value)


def test_l_horizon_inclut_l_echeance_exactement_a_la_limite(pas):
    amina = pas[2]["amina"]
    contrat = _contrat(pas)  # fin 2026-12-15
    enregistrer_garantie(
        utilisateur=amina, contrat=contrat, type_garantie="avance", emetteur="B", reference="G-1",
        montant="100", date_emission=J(2026, 6, 1), date_echeance=J(2026, 9, 1),
    )  # fmt: skip
    jour = J(2026, 8, 1)  # 31 jours avant le 1er septembre
    assert [
        a.reference
        for a in alertes_echeances(
            utilisateur=amina, project_id=pas[1].id, jour=jour, horizon_jours=31
        )
    ] == ["G-1"]
    assert (
        alertes_echeances(utilisateur=amina, project_id=pas[1].id, jour=jour, horizon_jours=30)
        == []
    )
    fin = J(2026, 12, 15)  # le contrat : à la limite exacte aussi
    limite = alertes_echeances(
        utilisateur=amina,
        project_id=pas[1].id,
        jour=fin - datetime.timedelta(days=10),
        horizon_jours=10,
    )
    assert [a.reference for a in limite] == ["G-1", "C-001"]  # G-1 est dépassée depuis le 1er sept.
