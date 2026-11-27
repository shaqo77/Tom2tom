# ruff: noqa: F811, E501
"""Lot 8 : l'export d'une demande de retrait vers les formulaires BAD A1, A2, A3.

Sans le formulaire officiel éditable de la Banque, le fichier est TOUJOURS marqué « non officiel ». Chaque
cellule est un texte exact (aucun nombre à virgule flottante, aucune formule). Ce que l'application ne sait pas
est listé « à compléter », jamais inventé.
"""

import io
import uuid

import openpyxl
import pytest
from django.db import connection

from core.models import AuditLog
from niveau1_socle.decaissements.models import TypeDemande
from niveau1_socle.financements.models import Bailleur
from niveau4_reporting.formats_bailleur import (
    FormatInapplicable,
    FormatInconnu,
    export_demande,
    formats_disponibles,
)
from niveau4_reporting.formats_bailleur.export import AVERTISSEMENT, FormatInvalide, _verifier
from niveau4_reporting.formats_bailleur.types_bad import (
    AVANCE_INITIALE,
    PAIEMENT_DIRECT,
    RECONSTITUTION,
    REMBOURSEMENT,
    TypeBadIndeterminable,
    type_bad,
)
from tests.test_api_marches_bd import appeler
from tests.test_contrat_demande_bd import _contrat_en
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import _depense, _preparer, _soumettre
from tests.test_demandes_retrait_bd import drf as drf_de_base  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_plan_passation_bd import pas  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def drf(drf_de_base):
    """La fixture des demandes, dont le bailleur est la BAD : la correspondance se choisit sur son code."""
    organisation, accord = drf_de_base[0], drf_de_base[3]
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])
    Bailleur.objects.filter(pk=accord.bailleur_id).update(code="BAD")
    return drf_de_base


def _feuille(octets):
    return openpyxl.load_workbook(io.BytesIO(octets)).active


def _lignes(octets):
    return [[c.value for c in ligne] for ligne in _feuille(octets).iter_rows()]


def _demande(drf, type="reapprovisionnement", mois=2, **champs):
    organisation, projet, profils, accord, cat = drf
    serv = _depense(organisation, projet, accord, cat["serv"], 100, jour=10, mois=mois)
    biens = _depense(organisation, projet, accord, cat["biens"], 50, jour=11, mois=mois)
    return _preparer(profils, accord, [serv, biens], type=type, **champs)


# --- le fichier : non officiel, texte exact, ce qui manque est dit -------------------------------


def test_le_fichier_est_marque_non_officiel_et_ne_contient_que_du_texte_exact(drf):
    octets, nom = export_demande(_demande(drf), "bad_a2")
    assert nom.endswith(".xlsx") and nom.startswith("bad_a2-")
    feuille = _feuille(octets)
    assert (
        feuille["A1"].value
        == AVERTISSEMENT
        == "DOCUMENT NON OFFICIEL : à reporter sur le formulaire de la Banque"
    )
    for ligne in feuille.iter_rows():
        for cellule in ligne:
            if cellule.value is None:
                continue
            assert cellule.data_type == "s", cellule.coordinate  # texte : ni nombre, ni formule
            assert not str(cellule.value).startswith("="), cellule.coordinate


def test_a1_coche_le_type_de_demande_et_dit_ce_qui_est_a_verifier_et_a_completer(drf):
    lignes = _lignes(export_demande(_demande(drf), "bad_a1")[0])
    coches = [ligne[0].strip() for ligne in lignes if len(ligne) > 1 and ligne[1] == "X"]
    assert coches == ["Reimbursement"]  # une seule case, la bonne
    tout = " ".join(str(c) for ligne in lignes for c in ligne if c)
    assert (
        "À VÉRIFIER" in tout and "13 chiffres" in tout
    )  # « DON-1 » n'est pas un numéro de la Banque
    assert (
        "À COMPLÉTER" in tout
        and "Beneficiary Bank Details" in tout
        and "Authorised Signatories" in tout
    )
    par_etiquette = {ligne[0]: ligne[1] for ligne in lignes if len(ligne) > 1 and ligne[0]}
    assert par_etiquette["2. Loan/Grant Number"] == "DON-1"
    assert par_etiquette["5. Currency"] == "DJF"
    assert (
        par_etiquette["5. Amount of the disbursement request"] == "150"
    )  # DJF : 0 décimale, texte exact


def test_a2_regroupe_par_categorie_avec_des_totaux_exacts(drf):
    lignes = _lignes(export_demande(_demande(drf), "bad_a2")[0])
    groupes = {
        ligne[1].split()[0]: ligne for ligne in lignes if ligne[0] == "5. Category/Sub-Project"
    }
    assert set(groupes) == {"BIENS", "SERV"}
    totaux = {ligne[0]: ligne[1] for ligne in lignes if ligne[0] in ("Total", "Running Total")}
    assert totaux["Running Total"] == "150"
    montants = [
        ligne[-1] for ligne in lignes if ligne[0] in (1, "1") and ligne[-1] in ("100", "50")
    ]
    assert sorted(montants) == ["100", "50"]


def test_a3_n_existe_que_pour_une_avance_et_refuse_un_remboursement(drf):
    with pytest.raises(FormatInapplicable, match="bad_a3"):
        export_demande(_demande(drf), "bad_a3")


# --- le type de demande BAD, déduit ------------------------------------------------------------


def test_le_type_bad_se_deduit_et_un_cas_ambigu_est_refuse(drf):
    organisation, projet, profils, accord, cat = drf
    assert type_bad(_demande(drf, mois=2)) == REMBOURSEMENT
    assert type_bad(_demande(drf, type="paiement_direct", mois=3)) == PAIEMENT_DIRECT

    premiere = _demande(drf, type="retrait", mois=1)
    assert type_bad(premiere) == AVANCE_INITIALE  # la première avance de l'accord
    deuxieme = _preparer(
        profils, accord, [_depense(organisation, projet, accord, cat["serv"], 20, jour=12, mois=1)],
        type="retrait",
    )  # fmt: skip
    with pytest.raises(
        TypeBadIndeterminable
    ):  # la première n'est pas soumise : laquelle est l'initiale ?
        type_bad(deuxieme)
    _soumettre(premiere, profils)
    assert type_bad(deuxieme) == RECONSTITUTION  # maintenant la première est adressée à la Banque

    with pytest.raises(TypeBadIndeterminable):  # aucun équivalent BAD : on ne devine pas
        autre = _demande(drf, type=TypeDemande.ENGAGEMENT_SPECIAL, mois=3)
        type_bad(autre)


# --- « déjà payé par la Banque » : une requête, jamais une saisie ---------------------------------


def test_le_deja_paye_par_la_banque_vient_des_demandes_anterieures_du_contrat(drf, pas):
    organisation, projet, profils, accord, cat = drf
    contrat = _contrat_en(pas, "C-1")
    a = _depense(organisation, projet, accord, cat["serv"], 100, jour=10)
    b = _depense(organisation, projet, accord, cat["serv"], 40, jour=11)
    # Une demande restée « préparée » n'est PAS « payée » : elle ne compte pas, même si elle est antérieure.
    jamais_soumise = _depense(organisation, projet, accord, cat["serv"], 70, jour=9)
    _preparer(profils, accord, [jamais_soumise], contrats={jamais_soumise: contrat.pk})
    premiere = _preparer(profils, accord, [a], contrats={a: contrat.pk})
    _soumettre(premiere, profils)
    seconde = _preparer(profils, accord, [b], contrats={b: contrat.pk})

    lignes = _lignes(export_demande(seconde, "bad_a2")[0])
    entete = next(ligne for ligne in lignes if ligne[0] == "Item No")
    ligne = next(ligne for ligne in lignes if ligne[0] in (1, "1") and ligne[2] == "C-1")
    assert entete[4] == "14. Amount previously paid by the Bank"
    assert ligne[4] == "100"  # ce que la seule demande ADRESSÉE à la Banque a retiré (pas les 70)
    assert ligne[3] == f"{contrat.montant_initial:.2f}"  # la valeur du contrat, dans SA devise
    premiere_export = _lignes(export_demande(premiere, "bad_a2")[0])
    assert (
        next(ligne for ligne in premiere_export if ligne[0] in (1, "1") and ligne[2] == "C-1")[4]
        == "0"
    )  # rien avant elle


# --- le fichier de correspondance est une donnée VALIDÉE -----------------------------------------


def test_les_formats_livres_se_chargent_et_un_nom_n_est_jamais_un_chemin(drf):
    assert formats_disponibles("BAD") == ["bad_a1", "bad_a2", "bad_a3"]
    assert formats_disponibles("inconnu") == []
    demande = _demande(drf)
    for mauvais in ("../bad_a1", "bad_a1/../../x", "BAD_A1", "bad a1", "", "bad_a9"):
        with pytest.raises(FormatInconnu):
            export_demande(demande, mauvais)


@pytest.mark.parametrize(
    "bloc",
    [
        {"genre": "formule", "etiquette": "x"},
        {"genre": "champ", "etiquette": "x", "source": "os.system"},
        {"genre": "champ", "etiquette": "x", "source": "demande.date", "controle": "eval"},
        {"genre": "tableau", "groupe": "ligne.categorie", "total": "demande.date", "colonnes": []},
        {
            "genre": "tableau",
            "groupe": "ligne.categorie",
            "total": "ligne.montant_depense",
            "colonnes": [{"titre": "t", "source": "x"}],
        },
    ],
)
def test_un_fichier_de_correspondance_mal_forme_est_refuse_au_chargement(bloc):
    with pytest.raises(FormatInvalide):
        _verifier("test", bloc)


# --- l'API ----------------------------------------------------------------------------------------


def _url(projet, demande, format="bad_a2"):
    return f"/projets/{projet.id}/demandes-retrait/{demande.id}/export/{format}/"


def test_l_api_rend_une_piece_jointe_et_journalise_l_export(drf):
    _, projet, profils, _, _ = drf
    demande = _demande(drf)
    r = appeler(profils["amina"], "get", _url(projet, demande))
    assert r.status_code == 200, r.content
    assert r["Content-Type"].startswith("application/vnd.openxmlformats")
    assert r["Content-Disposition"].startswith('attachment; filename="bad_a2-')
    assert _feuille(r.content)["A1"].value == AVERTISSEMENT
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(demande.org_id)])
    entrees = AuditLog.objects.filter(action="demande_exportee", object_id=demande.id)
    assert entrees.count() == 1
    assert entrees.get().after["format"] == "bad_a2" and len(entrees.get().after["sha256"]) == 64


def test_l_api_refuse_dans_le_format_code_message(drf):
    _, projet, profils, _, _ = drf
    demande = _demande(drf)
    inconnu = appeler(profils["amina"], "get", _url(projet, demande, "bad_a9"))
    assert inconnu.status_code == 404 and set(inconnu.json()) == {"code", "message"}
    inapplicable = appeler(profils["amina"], "get", _url(projet, demande, "bad_a3"))
    assert inapplicable.status_code == 422 and set(inapplicable.json()) == {"code", "message"}
    assert "bad_a3" in inapplicable.json()["message"]
    absente = appeler(
        profils["amina"],
        "get",
        f"/projets/{projet.id}/demandes-retrait/{uuid.uuid4()}/export/bad_a2/",
    )
    assert absente.status_code == 404


def test_l_api_est_fermee_sans_droit_de_lecture_et_hors_du_projet(drf):
    organisation, projet, profils, accord, cat = drf
    demande = _demande(drf)
    ailleurs = appeler(profils["amina"], "get", _url(type("P", (), {"id": uuid.uuid4()}), demande))
    assert ailleurs.status_code == 403 and set(ailleurs.json()) == {"code", "message"}
