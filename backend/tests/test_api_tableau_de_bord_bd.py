# ruff: noqa: F811
"""L'API HTTP du tableau de bord : lecture, filtres, consolidation, descente. Voir L10-T02."""

import datetime
from decimal import Decimal

import pytest
from django.test import Client

from niveau1_socle.referentiels.models import Taux
from niveau4_reporting.publication.models import SoumissionBailleur
from tests.test_api_marches_bd import RACINE, appeler
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_tableau_de_bord_bd import JOUR, _poser, parc  # noqa: F401
from tests.test_tresorerie_bd import banque  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Q = f"jour={JOUR.isoformat()}"
J = datetime.date


def _get(parc, chemin, nom="amina"):
    return appeler(parc[5][nom], "get", "/" + chemin)


def test_le_tableau_se_lit_par_projet_et_par_devise_avec_des_montants_en_chaines(parc):
    reponse = _get(parc, f"tableau-de-bord/?{Q}")
    assert reponse.status_code == 200
    corps = reponse.json()
    assert [p["code"] for p in corps["projets"]] == ["P1", "P2"]
    accordes = corps["indicateurs"]["financements_accordes"]["total_par_devise"]
    assert {d: Decimal(m) for d, m in accordes.items()} == {
        "DJF": Decimal("1000"),
        "EUR": Decimal("500000"),
    }
    assert all(isinstance(m, str) for m in accordes.values())  # jamais un nombre flottant
    assert corps["conformite"]["totaux"]["echeances_a_remettre"] == 0
    # Les avertissements arrivent avec leur texte dans la langue : le frontend n'a rien à deviner.
    avertissements = {a["code"]: a["message"] for a in corps["avertissements"]}
    assert "consommé" in avertissements["tableau_de_bord.execution_recouvrement"]
    assert all(m.strip() for m in avertissements.values())
    # Le nombre de décimales de chaque devise affichée : un montant en DJF ne s'écrit pas « ,00 ».
    assert corps["devises"] == {"DJF": 0, "EUR": 2, "USD": 2}
    # Le taux d'exécution par composante vient du serveur : une seule règle de calcul.
    sans_composante = corps["par_composante"][""]
    assert set(sans_composante) == {"budget", "engage", "consomme", "taux_execution"}
    assert Decimal(sans_composante["taux_execution"]["DJF"]) == Decimal("1200") / Decimal("20000")


def test_les_filtres_de_l_url_restreignent_le_tableau(parc):
    corps = _get(parc, f"tableau-de-bord/?{Q}&devise=EUR").json()
    accordes = corps["indicateurs"]["financements_accordes"]["total_par_devise"]
    assert list(accordes) == ["EUR"]
    corps = _get(parc, f"tableau-de-bord/?{Q}&projets={parc[2].id}").json()
    assert [p["code"] for p in corps["projets"]] == ["P2"]
    tous = _get(parc, f"tableau-de-bord/?{Q}&statut_projet=tous").json()
    assert [p["code"] for p in tous["projets"]] == ["P1", "P2", "P3"]


def test_un_projet_hors_perimetre_n_est_pas_ajoute_par_l_url(parc):
    p4 = parc[4]
    corps = _get(parc, f"tableau-de-bord/?{Q}&projets={p4.id}").json()
    assert corps["projets"] == []


def test_sans_jour_ou_avec_un_identifiant_invalide_la_requete_est_refusee(parc):
    sans_jour = _get(parc, "tableau-de-bord/")
    assert sans_jour.status_code == 422 and sans_jour.json()["code"]
    assert _get(parc, f"tableau-de-bord/?{Q}&projets=pas-un-uuid").status_code == 422


def test_un_visiteur_non_connecte_n_a_rien(parc):
    assert Client().get(f"{RACINE}/tableau-de-bord/?{Q}").status_code in (401, 403)


def test_la_consolidation_dit_qu_elle_est_impossible_sans_taux_puis_donne_methode_et_taux(parc):
    organisation = parc[0]
    base = f"tableau-de-bord/soldes_comptables/consolidation/?{Q}"
    chemin = f"{base}&devise_reference=DJF&type_taux=officiel"
    sans = _get(parc, chemin).json()
    assert sans["consolide"] is False and sans["montant"] is None and "USD" in sans["raison"]
    _poser(organisation)
    Taux.objects.create(
        org_id=organisation.id, devise_id="USD", date=J(2026, 6, 1), taux=Decimal("177.5555"),
        type_taux="officiel",
    )  # fmt: skip
    avec = _get(parc, chemin).json()
    assert avec["consolide"] is True and avec["methode"] and avec["raison"] is None
    assert avec["taux"]["USD"]["date"] == "2026-06-01"
    assert Decimal(avec["montant"]) == sum(Decimal(m) for m in avec["par_projet"].values())
    assert (
        _get(parc, f"tableau-de-bord/inconnu/consolidation/?{Q}&devise_reference=DJF").status_code
        == 422
    )
    # (sans devise_reference : voir plus bas, la valeur vient des réglages)


def test_la_descente_va_de_l_indicateur_au_detail_puis_a_l_ecriture(parc):
    p2 = parc[2]
    detail = _get(parc, f"projets/{p2.id}/tableau-de-bord/soldes_comptables/detail/?{Q}").json()
    assert [(d["type"], d["libelle"], d["devise"]) for d in detail] == [
        ("compte_bancaire", "CB-USD", "USD")
    ]
    chemin = (
        f"projets/{p2.id}/tableau-de-bord/soldes_comptables/detail/{detail[0]['id']}/ecritures/"
    )
    ecritures = _get(parc, f"{chemin}?{Q}").json()
    assert sum(Decimal(e["montant"]) for e in ecritures["ecritures"]) == Decimal(
        detail[0]["montant"]
    )
    assert ecritures["ecritures"][0]["ecriture_id"]


def test_la_descente_refuse_un_projet_non_consultable_un_code_et_un_detail_inconnus(parc):
    p2, p4 = parc[2], parc[4]
    assert (
        _get(parc, f"projets/{p4.id}/tableau-de-bord/budget_approuve/detail/?{Q}").status_code
        == 403
    )
    assert _get(parc, f"projets/{p2.id}/tableau-de-bord/inconnu/detail/?{Q}").status_code == 422
    inconnu = "00000000-0000-0000-0000-000000000001"
    chemin = f"projets/{p2.id}/tableau-de-bord/soldes_comptables/detail/{inconnu}/ecritures/?{Q}"
    assert _get(parc, chemin).status_code == 404


def test_le_taux_d_acceptation_est_vide_sans_issue_puis_donne_le_taux_des_sommes(parc):
    organisation, p1, _, _, _, profils, _ = parc
    assert _get(parc, f"tableau-de-bord/?{Q}").json()["conformite"]["taux_acceptation"] is None
    _poser(organisation)
    for numero, resultat in (("A", "accepte"), ("B", "accepte"), ("C", "rejete")):
        SoumissionBailleur.objects.create(
            org_id=organisation.id, project_id=p1.id, template_code=numero,
            period_to=J(2026, 3, 31), numero_envoi=1, envoyee_le=J(2026, 4, 1), resultat=resultat,
            decidee_le=J(2026, 4, 5), motif_rejet="x" if resultat == "rejete" else "",
            saisie_par=profils["amina"].id,
        )  # fmt: skip
    corps = _get(parc, f"tableau-de-bord/?{Q}").json()["conformite"]
    assert Decimal(corps["taux_acceptation"]) == Decimal(2) / Decimal(3)
    assert corps["totaux"]["premiers_envois_decides"] == 3


# --- la devise de référence et le type de taux viennent des RÉGLAGES (L11-A1) ---------------------


def _regler(organisation, *, projet=None, version=1, de=None, **champs):
    """Pose un réglage de devises directement en base (le service de pose est testé ailleurs)."""
    from niveau1_socle.referentiels.models import ParametreDevises

    _poser(organisation)
    return ParametreDevises.objects.create(
        org_id=organisation.id,
        project_id=projet.id if projet else None,
        version=version,
        valid_from=de or J(2026, 1, 1),
        **champs,
    )


def _taux(organisation, devise, valeur, type_taux="officiel"):
    _poser(organisation)
    Taux.objects.create(
        org_id=organisation.id, devise_id=devise, date=J(2026, 6, 1), taux=Decimal(valeur),
        type_taux=type_taux,
    )  # fmt: skip


CONSO = f"tableau-de-bord/financements_accordes/consolidation/?{Q}"


def test_sans_reglage_ni_parametre_la_consolidation_dit_non_parametre_au_lieu_de_deviner(parc):
    r = _get(parc, CONSO)
    assert r.status_code == 200  # avant : 422 « devise_reference obligatoire »
    corps = r.json()
    assert corps["consolide"] is False and corps["montant"] is None
    assert "paramétr" in corps["raison"]  # la raison dit POURQUOI, dans la langue de la requête


def test_la_devise_de_reference_et_le_type_de_taux_reglés_pilotent_la_consolidation(parc):
    organisation = parc[0]
    _taux(organisation, "EUR", "200")
    _regler(organisation, devise_reference_id="DJF", type_taux="officiel")
    corps = _get(parc, CONSO).json()
    assert corps["consolide"] is True and corps["devise_reference"] == "DJF"
    assert corps["origine"] == {"devise_reference": "organisation", "type_taux": "organisation"}
    # 1 000 DJF (P1) + 500 000 EUR × 200 (P2)
    assert Decimal(corps["montant"]) == Decimal("100001000")


def test_un_parametre_explicite_l_emporte_sur_le_reglage(parc):
    organisation = parc[0]
    _taux(organisation, "EUR", "200")
    _taux(organisation, "EUR", "300", type_taux="bailleur")
    _regler(organisation, devise_reference_id="DJF", type_taux="officiel")
    corps = _get(parc, CONSO + "&type_taux=bailleur").json()
    assert corps["origine"]["type_taux"] == "demande"
    assert Decimal(corps["montant"]) == Decimal("150001000")  # 1 000 + 500 000 × 300


def test_une_devise_de_reference_differente_de_la_monnaie_de_tenue_passe_par_la_monnaie_de_tenue(
    parc,
):
    """Les taux sont des unités de la monnaie de TENUE (DJF) par unité de devise : convertir vers
    USD se fait par croisement EUR → DJF → USD, jamais par le taux d'une autre devise.
    """
    organisation = parc[0]
    _taux(organisation, "EUR", "200")
    _taux(organisation, "USD", "177")
    _regler(organisation, devise_reference_id="USD", type_taux="officiel")
    corps = _get(parc, CONSO).json()
    assert corps["consolide"] is True and corps["devise_reference"] == "USD"
    # P1 : 1 000 DJF / 177 = 5,6497 → 5,65 ; P2 : 500 000 EUR × 200 / 177 = 564 971,75 (2 décimales)
    assert {Decimal(m) for m in corps["par_projet"].values()} == {
        Decimal("5.65"),
        Decimal("564971.75"),
    }
    assert Decimal(corps["montant"]) == Decimal("564977.40")


def test_sans_taux_de_la_devise_de_reference_la_consolidation_le_dit(parc):
    organisation = parc[0]
    _taux(organisation, "EUR", "200")  # pas de taux USD alors que USD est la référence
    _regler(organisation, devise_reference_id="USD", type_taux="officiel")
    corps = _get(parc, CONSO).json()
    assert corps["consolide"] is False and "USD" in corps["raison"]


def test_le_reglage_d_un_projet_pilote_la_consolidation_de_ce_projet(parc):
    organisation, p2 = parc[0], parc[2]
    _taux(organisation, "EUR", "200")
    _regler(organisation, devise_reference_id="DJF", type_taux="officiel")
    _regler(organisation, projet=p2, devise_reference_id="EUR", type_taux="officiel")
    seul = _get(parc, CONSO + f"&projets={p2.id}").json()
    assert seul["devise_reference"] == "EUR"
    assert seul["origine"]["devise_reference"] == "projet"
    assert Decimal(seul["montant"]) == Decimal("500000")


def test_des_references_differentes_entre_projets_empechent_un_total_unique_et_sont_nommees(parc):
    organisation, p2 = parc[0], parc[2]
    _taux(organisation, "EUR", "200")
    _regler(organisation, devise_reference_id="DJF", type_taux="officiel")
    _regler(organisation, projet=p2, devise_reference_id="EUR")
    corps = _get(parc, CONSO).json()  # P1 hérite de DJF, P2 règle EUR
    assert corps["consolide"] is False and corps["montant"] is None
    assert "DJF" in corps["raison"] and "EUR" in corps["raison"] and "P2" in corps["raison"]
    # Le choix explicite reste possible : c'est la personne qui tranche, pas le système.
    explicite = _get(parc, CONSO + "&devise_reference=DJF").json()
    assert explicite["consolide"] is True and explicite["origine"]["devise_reference"] == "demande"


def test_un_type_de_taux_inconnu_ou_une_devise_de_reference_inconnue_sont_refuses(parc):
    assert _get(parc, CONSO + "&type_taux=magique").status_code == 422
    corps = _get(parc, CONSO + "&devise_reference=XXX&type_taux=officiel").json()
    assert corps["consolide"] is False and "XXX" in corps["raison"]


def test_un_projet_sans_reglage_dans_le_perimetre_empeche_la_consolidation(parc):
    organisation, p2 = parc[0], parc[2]
    _taux(organisation, "EUR", "200")
    _regler(organisation, projet=p2, devise_reference_id="EUR", type_taux="officiel")  # P1 : rien
    sans = _get(parc, CONSO).json()
    assert sans["consolide"] is False and "aucune devise de référence" in sans["raison"]
    seul = _get(parc, CONSO + f"&projets={p2.id}").json()
    assert seul["consolide"] is True and seul["origine"]["devise_reference"] == "projet"


def test_une_reference_reglee_sans_type_de_taux_regle_le_dit(parc):
    organisation = parc[0]
    _regler(organisation, devise_reference_id="DJF")  # aucun type de taux
    corps = _get(parc, CONSO).json()
    assert corps["consolide"] is False and "type de taux" in corps["raison"]
    assert corps["devise_reference"] == "DJF" and corps["type_taux"] is None


# --- le dernier pas de la descente : l'écriture, ses lignes et ses pièces (L11-A1b) ---------------


def _une_ecriture_de_p2(parc):
    p2 = parc[2]
    detail = _get(parc, f"projets/{p2.id}/tableau-de-bord/soldes_comptables/detail/?{Q}").json()
    chemin = (
        f"projets/{p2.id}/tableau-de-bord/soldes_comptables/detail/{detail[0]['id']}/ecritures/"
    )
    return _get(parc, f"{chemin}?{Q}").json()["ecritures"][0]["ecriture_id"]


def test_une_ecriture_de_la_descente_se_lit_avec_ses_lignes_et_ses_pieces(parc):
    p2 = parc[2]
    ecriture_id = _une_ecriture_de_p2(parc)
    r = _get(parc, f"projets/{p2.id}/tableau-de-bord/ecritures/{ecriture_id}/")
    assert r.status_code == 200
    corps = r.json()
    assert corps["id"] == ecriture_id and corps["numero"] and corps["journal"]
    assert corps["lignes"] and all({"compte", "montant"} <= set(ligne) for ligne in corps["lignes"])
    assert sum(Decimal(ligne["montant"]) for ligne in corps["lignes"]) == Decimal(0)  # équilibrée
    assert all(isinstance(ligne["montant"], str) for ligne in corps["lignes"])
    assert corps["pieces"] == []  # ici aucune pièce : la liste est vide, pas absente


def test_une_ecriture_d_un_autre_projet_ou_inconnue_est_introuvable(parc):
    p1, p2 = parc[1], parc[2]
    ecriture_id = _une_ecriture_de_p2(parc)
    # Une écriture de P2 demandée « au nom » de P1 : introuvable (elle n'appartient pas à P1).
    assert (
        _get(parc, f"projets/{p1.id}/tableau-de-bord/ecritures/{ecriture_id}/").status_code == 404
    )
    inconnue = "00000000-0000-0000-0000-000000000001"
    assert _get(parc, f"projets/{p2.id}/tableau-de-bord/ecritures/{inconnue}/").status_code == 404


def test_une_ecriture_d_un_projet_non_consultable_est_refusee(parc):
    p2, p4 = parc[2], parc[4]
    ecriture_id = _une_ecriture_de_p2(parc)
    assert (
        _get(parc, f"projets/{p4.id}/tableau-de-bord/ecritures/{ecriture_id}/").status_code == 403
    )
    assert Client().get(
        f"{RACINE}/projets/{p2.id}/tableau-de-bord/ecritures/{ecriture_id}/"
    ).status_code in (401, 403)


def test_les_pieces_de_l_ecriture_sont_listees_sans_leurs_octets(parc):
    from niveau1_socle.comptabilite.models import Ecriture
    from niveau1_socle.comptabilite.pieces import joindre_piece

    organisation, p2, profils = parc[0], parc[2], parc[5]
    ecriture_id = _une_ecriture_de_p2(parc)
    _poser(organisation)
    joindre_piece(
        utilisateur=profils["amina"],
        ecriture=Ecriture.objects.get(pk=ecriture_id),
        type_piece="facture",
        nom="facture-001.pdf",
        contenu=b"%PDF-scan",
    )
    corps = _get(parc, f"projets/{p2.id}/tableau-de-bord/ecritures/{ecriture_id}/").json()
    assert len(corps["pieces"]) == 1
    piece = corps["pieces"][0]
    assert (piece["type"], piece["nom"], piece["taille"]) == ("facture", "facture-001.pdf", 9)
    assert set(piece) == {"id", "type", "nom", "taille"}  # ni octets ni empreinte
