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
    assert "tableau_de_bord.execution_recouvrement" in corps["avertissements"]


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
    chemin = f"tableau-de-bord/soldes_comptables/consolidation/?{Q}&devise_reference=DJF"
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
    assert _get(parc, f"tableau-de-bord/soldes_comptables/consolidation/?{Q}").status_code == 422


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
