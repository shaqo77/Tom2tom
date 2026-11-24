# ruff: noqa: F811, E501
"""L'API HTTP des bailleurs, des accords, de leurs catégories et avenants : un administrateur
configure un financement de bout en bout sans développeur. Phase B de L11.

Avant : toute cette configuration passait par des appels de service Python ; et plusieurs refus
(code déjà pris, montant négatif, dates incohérentes) sortaient en erreur serveur brute.
"""

import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from niveau1_socle.comptabilite.services import saisir_ecriture
from tests.test_api_marches_bd import RACINE, appeler  # noqa: F401
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_financements_bd import _document, cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
D = Decimal
Utilisateur = get_user_model()


def _accords(projet, fin=""):
    return f"/projets/{projet.id}/accords/{fin}"


def _nouvel_accord(**champs):
    return {
        "bailleur": "IDA",
        "numero": "IDA-6789",
        "nature": "don",
        "devise": "USD",
        "montant_initial": "1000000",
        "libelle": "Don IDA",
    } | champs


def _creer(profils, projet, **champs):
    r = appeler(profils["dora"], "post", _accords(projet), _nouvel_accord(**champs))
    assert r.status_code == 201, r.content
    return r.json()


def _poser_org(organisation):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


# --- bailleurs -----------------------------------------------------------------------------------


def test_un_bailleur_se_cree_et_se_liste(cadre):
    _, _, profils, _ = cadre
    dora = profils["dora"]
    r = appeler(
        dora,
        "post",
        "/bailleurs/",
        {"code": "BAD", "nom": "Banque africaine de développement", "pays": "CI"},
    )
    assert r.status_code == 201 and r.json()["code"] == "BAD" and r.json()["pays"] == "CI"
    assert [b["code"] for b in appeler(dora, "get", "/bailleurs/").json()] == ["BAD", "IDA"]


def test_un_bailleur_invalide_est_refuse_au_format_stable(cadre):
    _, _, profils, _ = cadre
    dora = profils["dora"]
    for champs in (
        {"code": "IDA", "nom": "Doublon"},
        {"code": "X", "nom": "x", "pays": "france"},
        {"nom": "x"},
        {"code": "X"},
    ):
        r = appeler(dora, "post", "/bailleurs/", champs)
        assert r.status_code == 422 and set(r.json()) == {"code", "message"}, champs


def test_sans_parametrer_on_ne_cree_pas_de_bailleur_mais_on_peut_les_lire(cadre):
    _, _, profils, _ = cadre
    assert (
        appeler(profils["amina"], "post", "/bailleurs/", {"code": "X", "nom": "x"}).status_code
        == 403
    )
    assert appeler(profils["amina"], "get", "/bailleurs/").status_code == 200


# --- accords -------------------------------------------------------------------------------------


def test_un_accord_se_cree_en_brouillon_et_se_liste_avec_ses_montants_en_chaines(cadre):
    _, projet, profils, _ = cadre
    accord = _creer(profils, projet, date_effet="2026-01-01", date_fin_eligibilite="2026-12-31")
    assert (
        accord["statut"] == "brouillon"
        and accord["bailleur"] == "IDA"
        and accord["devise"] == "USD"
    )
    assert accord["montant_initial"] == "1000000.0000" and isinstance(
        accord["montant_courant"], str
    )
    liste = appeler(profils["dora"], "get", _accords(projet)).json()
    assert [a["numero"] for a in liste] == ["IDA-6789"]


def test_plusieurs_accords_du_meme_bailleur_coexistent(cadre):
    _, projet, profils, _ = cadre
    _creer(profils, projet, numero="IDA-1")
    _creer(profils, projet, numero="IDA-2")
    assert len(appeler(profils["dora"], "get", _accords(projet)).json()) == 2


@pytest.mark.parametrize(
    "champs",
    [
        {"numero": ""},
        {"bailleur": "FANTOME"},
        {"nature": "magique"},
        {"devise": "XXX"},
        {"montant_initial": "-5"},
        {"montant_initial": 1000.5},  # jamais de nombre à virgule JSON
        {"montant_initial": "abc"},
        {"date_effet": "2026-06-01", "date_fin_eligibilite": "2026-01-01"},  # fin avant le début
        {"date_effet": "pas-une-date"},
    ],
)
def test_un_accord_invalide_est_refuse_au_format_stable_jamais_en_panne(cadre, champs):
    _, projet, profils, _ = cadre
    r = appeler(profils["dora"], "post", _accords(projet), _nouvel_accord(**champs))
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}, r.content
    # Le refus nomme la valeur fautive : pas un message générique de la base.
    for valeur, mot in (("FANTOME", "FANTOME"), ("magique", "magique"), ("XXX", "XXX")):
        if valeur in champs.values():
            assert mot in r.json()["message"], r.json()


def test_un_numero_d_accord_deja_pris_est_un_refus_lisible(cadre):
    _, projet, profils, _ = cadre
    _creer(profils, projet)
    r = appeler(profils["dora"], "post", _accords(projet), _nouvel_accord())
    assert r.status_code == 422 and "IDA-6789" in r.json()["message"]


def test_une_devise_non_autorisee_par_les_reglages_est_refusee(cadre):
    from niveau1_socle.referentiels.parametres_devises import parametrer_devises

    organisation, projet, profils, _ = cadre
    parametrer_devises(
        utilisateur=profils["dora"],
        devises_autorisees=["DJF", "USD"],
        date_effet=datetime.date(2026, 1, 1),
    )
    r = appeler(
        profils["dora"],
        "post",
        _accords(projet),
        _nouvel_accord(devise="EUR", date_effet="2026-02-01"),
    )
    assert r.status_code == 422 and "EUR" in r.json()["message"]


def test_creer_un_accord_exige_parametrer_et_le_lire_exige_consulter(cadre):
    organisation, projet, profils, _ = cadre
    assert appeler(profils["amina"], "post", _accords(projet), _nouvel_accord()).status_code == 403
    inconnu = Utilisateur.objects.create_user("ivan", password="x", org_id=organisation.id)
    assert appeler(inconnu, "get", _accords(projet)).status_code == 403


def test_le_detail_d_un_accord_rend_categories_avenants_et_montant_courant(cadre):
    _, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    detail = appeler(profils["dora"], "get", _accords(projet, f"{accord['id']}/")).json()
    assert (
        detail["numero"] == "IDA-6789" and detail["categories"] == [] and detail["avenants"] == []
    )


def test_un_accord_s_adresse_par_son_projet_pas_par_un_autre(cadre):
    organisation, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    autre = _creer_projet(organisation, "AUTRE")
    from niveau1_socle.habilitations.models import Habilitation, Role

    role = Role.objects.create(
        org_id=organisation.id, code="D2", label={"fr": "d"}, operations=["consulter", "parametrer"]
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=profils["dora"].id, project_id=autre.id, role=role
    )
    assert appeler(profils["dora"], "get", _accords(autre, f"{accord['id']}/")).status_code == 404


# --- statut --------------------------------------------------------------------------------------


def _statut(profils, projet, accord, statut, motif=""):
    return appeler(
        profils["dora"],
        "post",
        _accords(projet, f"{accord['id']}/statut/"),
        {"statut": statut, "motif": motif},
    )


def test_un_accord_s_active_puis_se_suspend_avec_un_motif(cadre):
    _, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    assert _statut(profils, projet, accord, "actif").json()["statut"] == "actif"
    sans_motif = _statut(profils, projet, accord, "suspendu")
    assert sans_motif.status_code == 422 and set(sans_motif.json()) == {"code", "message"}
    assert (
        _statut(profils, projet, accord, "suspendu", "Audit en cours").json()["statut"]
        == "suspendu"
    )


def test_une_transition_interdite_est_un_conflit_409(cadre):
    _, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    _statut(profils, projet, accord, "actif")
    _statut(profils, projet, accord, "clos", "Terminé")
    r = _statut(profils, projet, accord, "actif")
    assert r.status_code == 409 and r.json()["code"] == "TRANSITION_INTERDITE"


def test_un_statut_inconnu_est_refuse_et_sans_droit_c_est_403(cadre):
    _, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    assert _statut(profils, projet, accord, "magique").status_code == 422
    r = appeler(
        profils["amina"], "post", _accords(projet, f"{accord['id']}/statut/"), {"statut": "actif"}
    )
    assert r.status_code == 403


# --- catégories ----------------------------------------------------------------------------------


def _categorie(profils, projet, accord, **champs):
    corps = {"code": "BIENS", "label": {"fr": "Biens", "en": "Goods"}, "plafond": "600000"} | champs
    return appeler(profils["dora"], "post", _accords(projet, f"{accord['id']}/categories/"), corps)


def test_une_categorie_et_sa_sous_categorie_se_creent_par_code(cadre):
    _, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    r = _categorie(profils, projet, accord)
    assert (
        r.status_code == 201
        and r.json()["plafond"] == "600000.0000"
        and r.json()["devise"] == "USD"
    )
    sous = _categorie(profils, projet, accord, code="BIENS-A", plafond="400000", parent="BIENS")
    assert sous.status_code == 201 and sous.json()["parent"] == "BIENS"
    detail = appeler(profils["dora"], "get", _accords(projet, f"{accord['id']}/")).json()
    assert [(c["code"], c["parent"]) for c in detail["categories"]] == [
        ("BIENS", None),
        ("BIENS-A", "BIENS"),
    ]


@pytest.mark.parametrize(
    "champs",
    [
        {"code": "BIENS"},  # doublon
        {"code": ""},
        {"label": "texte"},
        {"label": {}},
        {"plafond": "-1"},
        {"plafond": 12.5},
        {"parent": "INCONNU"},
        {"devise": "XXX"},
    ],
)
def test_une_categorie_invalide_est_refusee_au_format_stable(cadre, champs):
    _, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    _categorie(profils, projet, accord)
    r = _categorie(profils, projet, accord, **({"code": "AUTRE"} | champs))
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}, r.content


# --- avenants ------------------------------------------------------------------------------------


def _avenant(profils, projet, accord, document, **champs):
    corps = {
        "reference": "AV-1",
        "date_avenant": "2026-06-01",
        "document_id": str(document.id),
        "montant_revise": "1200000",
        "motif": "Financement additionnel",
    } | champs
    return appeler(profils["dora"], "post", _accords(projet, f"{accord['id']}/avenants/"), corps)


def test_un_avenant_porte_la_nouvelle_valeur_sans_toucher_a_l_accord(cadre):
    organisation, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    _statut(profils, projet, accord, "actif")
    _poser_org(organisation)
    document = _document(organisation, projet)
    r = _avenant(profils, projet, accord, document)
    assert r.status_code == 201, r.content
    corps = r.json()
    assert (corps["montant_avant"], corps["montant_apres"], corps["variation"]) == (
        "1000000.0000",
        "1200000.0000",
        "200000.0000",
    )
    detail = appeler(profils["dora"], "get", _accords(projet, f"{accord['id']}/")).json()
    assert (
        detail["montant_initial"] == "1000000.0000" and detail["montant_courant"] == "1200000.0000"
    )
    assert [a["reference"] for a in detail["avenants"]] == ["AV-1"]


def test_un_avenant_invalide_est_refuse_au_format_stable(cadre):
    organisation, projet, profils, _ = cadre
    accord = _creer(profils, projet)  # encore en brouillon
    _poser_org(organisation)
    document = _document(organisation, projet)
    brouillon = _avenant(profils, projet, accord, document)
    assert brouillon.status_code in (422, 409) and set(brouillon.json()) == {"code", "message"}
    _statut(profils, projet, accord, "actif")
    for champs in (
        {"montant_revise": "-1"},
        {"montant_revise": 1.5},
        {"reference": ""},
        {"document_id": str(uuid.uuid4())},  # document inconnu
        {"date_avenant": "pas-une-date"},
    ):
        r = _avenant(profils, projet, accord, document, **champs)
        assert r.status_code == 422 and set(r.json()) == {"code", "message"}, (champs, r.content)
    assert _avenant(profils, projet, accord, document).status_code == 201
    doublon = _avenant(profils, projet, accord, document)  # même référence
    assert doublon.status_code == 422 and "AV-1" in doublon.json()["message"]


def test_sans_parametrer_pas_d_avenant(cadre):
    organisation, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    _poser_org(organisation)
    document = _document(organisation, projet)
    r = appeler(
        profils["amina"],
        "post",
        _accords(projet, f"{accord['id']}/avenants/"),
        {
            "reference": "A",
            "date_avenant": "2026-06-01",
            "document_id": str(document.id),
            "montant_revise": "1",
        },
    )
    assert r.status_code == 403


# --- de bout en bout -----------------------------------------------------------------------------


def test_de_bout_en_bout_un_accord_configure_par_http_recoit_une_imputation(cadre):
    """Configuré sans développeur, puis utilisé : refusé tant qu'il n'est pas actif, accepté ensuite."""
    organisation, projet, profils, _ = cadre
    accord = _creer(profils, projet, devise="DJF", numero="DON-HTTP", montant_initial="5000")
    assert _categorie(profils, projet, accord, code="SERV", plafond="3000").status_code == 201
    _poser_org(organisation)
    from niveau1_socle.financements.models import Accord

    pk = Accord.objects.get(numero="DON-HTTP").pk
    lignes = [
        {"compte": "6011", "debit": "100", "agreement_id": pk},
        {"compte": "5211", "credit": "100"},
    ]

    def saisir():
        return saisir_ecriture(
            utilisateur=profils["amina"], project_id=projet.id, journal="OD",
            date_comptable=datetime.date(2026, 3, 10), libelle="Dépense", lignes=lignes,
        )  # fmt: skip

    with pytest.raises(Exception, match="actif|brouillon"):
        saisir()
    _statut(profils, projet, accord, "actif")
    _poser_org(organisation)
    assert saisir().lignes.filter(agreement_id=pk).count() == 1


def test_le_detail_d_un_accord_exige_consulter(cadre):
    organisation, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    inconnu = Utilisateur.objects.create_user("ivan", password="x", org_id=organisation.id)
    assert appeler(inconnu, "get", _accords(projet, f"{accord['id']}/")).status_code == 403


def test_un_document_inconnu_est_nomme_dans_le_refus(cadre):
    organisation, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    _statut(profils, projet, accord, "actif")
    inconnu = _avenant(profils, projet, accord, SimpleNamespace(id=uuid.uuid4()))
    assert inconnu.status_code == 422 and "document" in inconnu.json()["message"].lower()


def test_les_categories_se_lisent_racines_d_abord_puis_sous_categories(cadre):
    _, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    for code, parent in (("Z-RACINE", None), ("A-ENFANT", "Z-RACINE"), ("B-RACINE", None)):
        _categorie(profils, projet, accord, code=code, **({"parent": parent} if parent else {}))
    detail = appeler(profils["dora"], "get", _accords(projet, f"{accord['id']}/")).json()
    assert [c["code"] for c in detail["categories"]] == ["B-RACINE", "Z-RACINE", "A-ENFANT"]


# --- numérotation des demandes (Lot 3-A) -----------------------------------------------------------


def _numerotation(projet, accord_id):
    return f"/projets/{projet.id}/accords/{accord_id}/numerotation/"


def test_un_accord_est_au_format_standard_par_defaut_et_passe_au_format_bad(cadre):
    _, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    assert accord["format_numero_demande"] == "standard" and accord["suffixe_agence"] == ""
    r = appeler(
        profils["dora"],
        "post",
        _numerotation(projet, accord["id"]),
        {"format": "bad", "suffixe_agence": "ADB"},
    )
    assert r.status_code == 200, r.content
    assert (r.json()["format_numero_demande"], r.json()["suffixe_agence"]) == ("bad", "ADB")


@pytest.mark.parametrize(
    "corps",
    [
        {"format": "bad"},
        {"format": "bad", "suffixe_agence": "ab"},
        {"format": "inconnu"},
        {"format": "standard", "suffixe_agence": "ABC"},
        {},
    ],
)
def test_une_numerotation_invalide_est_refusee_au_format_stable(cadre, corps):
    _, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    r = appeler(profils["dora"], "post", _numerotation(projet, accord["id"]), corps)
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}


def test_seul_un_administrateur_regle_la_numerotation(cadre):
    _, projet, profils, _ = cadre
    accord = _creer(profils, projet)
    r = appeler(
        profils["amina"],
        "post",
        _numerotation(projet, accord["id"]),
        {"format": "bad", "suffixe_agence": "ADB"},
    )
    assert r.status_code == 403
