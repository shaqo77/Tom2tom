"""Le scellement : empreinte stable de tout ce qui détermine un rapport. Voir L6-T03.

Contrôle du plan : sceller, changer une ligne source, re-sceller : les empreintes diffèrent. Les
lignes comptabilisées étant immuables, « changer » s'entend comme ajouter une écriture (ou en
contre-passer une) dans le périmètre.
"""

import copy
import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import connection

from niveau4_reporting.mapping.resolveur import construire_predicat
from niveau4_reporting.publication.scellement import (
    VIDE,
    empreinte_jeu_de_donnees,
    montant_canonique,
    sceller,
)
from tests.outils import creer_ligne

D = Decimal


def _rapport(**champs):
    base = {
        "template": SimpleNamespace(code="RFI-TER"),
        "template_version": 3,
        "period_from": datetime.date(2026, 1, 1),
        "period_to": datetime.date(2026, 3, 31),
        "params": {"langue": "fr", "devise": "USD", "agreement": "IDA-6789"},
        "config_version": {"profil": 4, "exigences": [1, 2]},
        "mapping_versions": {"WB-TER": 2},
        "dataset_hash": bytes.fromhex("ab" * 32),
        "values": {"R110": D("1000.50"), "R120": D("0")},
    }
    return SimpleNamespace(**(base | champs))


def test_le_scellement_est_stable_et_de_32_octets():
    assert sceller(_rapport()) == sceller(_rapport())
    assert len(sceller(_rapport())) == 32


@pytest.mark.parametrize(
    "champs",
    [
        {"template": SimpleNamespace(code="RFI-SEM")},
        {"template_version": 4},
        {"period_to": datetime.date(2026, 4, 30)},
        {"params": {"langue": "en", "devise": "USD", "agreement": "IDA-6789"}},
        {"config_version": {"profil": 5, "exigences": [1, 2]}},
        {"mapping_versions": {"WB-TER": 3}},
        {"dataset_hash": bytes.fromhex("cd" * 32)},
        {"values": {"R110": D("1000.51"), "R120": D("0")}},
        {"values": {"R110": D("1000.50")}},  # une rubrique en moins
    ],
)
def test_tout_ce_qui_determine_le_resultat_change_l_empreinte(champs):
    assert sceller(_rapport(**champs)) != sceller(_rapport())


def test_l_ordre_des_cles_et_l_ecriture_d_un_montant_ne_changent_rien():
    a = _rapport(values={"R110": D("1000.50"), "R120": D("0")}, params={"a": 1, "b": 2})
    b = _rapport(values={"R120": D("0.00"), "R110": D("1000.5")}, params={"b": 2, "a": 1})
    assert sceller(a) == sceller(b)
    assert [montant_canonique(x) for x in ("10.50", "10", "1E+1", "-0.00", D("0.0"))] == [
        "10.5",
        "10",
        "10",
        "0",
        "0",
    ]


def test_un_float_ne_se_scelle_pas():
    with pytest.raises(TypeError):
        sceller(_rapport(values={"R110": 1000.5}))
    with pytest.raises(TypeError):
        sceller(_rapport(params={"taux": 0.1}))
    with pytest.raises(TypeError):
        sceller(_rapport(params={"ensemble": {1, 2}}))


def test_le_scellement_ne_modifie_pas_le_rapport():
    rapport = _rapport()
    avant = copy.deepcopy(rapport.__dict__)
    sceller(rapport)
    assert rapport.__dict__ == avant


# --- le jeu de données -----------------------------------------------------------------------

pytestmark_bd = pytest.mark.django_db(transaction=True)


def _poser(org_id):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])


@pytestmark_bd
def test_ajouter_une_ecriture_dans_le_perimetre_change_l_empreinte_du_jeu_et_le_scellement(org_a):
    _poser(org_a)
    predicat, params = construire_predicat({"accounts": [["6000", "6279"]]})
    assert empreinte_jeu_de_donnees(predicat, params) == VIDE  # aucun jeu : empreinte du vide
    creer_ligne(org_a, "6011", 2026, 2, debit="100.00", accord="IDA-6789")
    avant = empreinte_jeu_de_donnees(predicat, params)
    assert avant != VIDE and avant == empreinte_jeu_de_donnees(predicat, params)
    scelle_avant = sceller(_rapport(dataset_hash=avant))

    creer_ligne(org_a, "6011", 2026, 2, credit="100.00", accord="IDA-6789")  # contre-passation
    apres = empreinte_jeu_de_donnees(predicat, params)
    assert apres != avant
    assert sceller(_rapport(dataset_hash=apres)) != scelle_avant


@pytestmark_bd
def test_une_ecriture_hors_perimetre_ne_change_pas_l_empreinte(org_a):
    _poser(org_a)
    predicat, params = construire_predicat({"accounts": [["6000", "6279"]]})
    creer_ligne(org_a, "6011", 2026, 2, debit="100.00", accord="IDA-6789")
    avant = empreinte_jeu_de_donnees(predicat, params)
    creer_ligne(org_a, "5211", 2026, 2, debit="999.00", accord="IDA-6789")  # autre compte
    assert empreinte_jeu_de_donnees(predicat, params) == avant


@pytestmark_bd
def test_l_empreinte_du_jeu_ne_voit_pas_une_autre_organisation(org_a, org_b):
    _poser(org_b)
    creer_ligne(org_b, "6011", 2026, 2, debit="12345", accord="IDA-6789")
    _poser(org_a)
    predicat, params = construire_predicat({"accounts": [["6000", "6279"]]})
    assert empreinte_jeu_de_donnees(predicat, params) == VIDE


@pytestmark_bd
def test_un_jeu_plus_restreint_a_une_autre_empreinte(org_a):
    _poser(org_a)
    predicat, params = construire_predicat({"accounts": [["6000", "6279"]]})
    creer_ligne(org_a, "6011", 2026, 2, debit="100.00", accord="IDA-6789")
    creer_ligne(org_a, "6012", 2026, 2, debit="50.00", accord="IDA-6789")
    complet = empreinte_jeu_de_donnees(predicat, params)
    restreint, p2 = construire_predicat({"accounts": [["6000", "6011"]]})
    assert empreinte_jeu_de_donnees(restreint, p2) != complet


@pytestmark_bd
def test_une_alteration_directe_d_un_montant_est_detectee_par_l_empreinte(org_a):
    """Un administrateur qui contourne les déclencheurs ne change pas le chiffre sans que le jeu
    de données le trahisse : l'empreinte porte les montants, pas seulement les identifiants."""
    from tests.outils import connexion_proprietaire

    _poser(org_a)
    predicat, params = construire_predicat({"accounts": [["6000", "6279"]]})
    creer_ligne(org_a, "6011", 2026, 2, debit="100.00", accord="IDA-6789")
    creer_ligne(org_a, "6012", 2026, 2, credit="50.00", accord="IDA-6789")
    avant = empreinte_jeu_de_donnees(predicat, params)
    with connexion_proprietaire() as proprietaire:
        proprietaire.execute("SET session_replication_role = replica")  # hors déclencheurs
        cible = proprietaire.execute(
            "SELECT l.id FROM comptabilite_ligneecriture l "
            "JOIN referentiels_compte c ON c.id = l.account_id WHERE c.code = '6011'"
        ).fetchone()[0]
        for modification in ("debit = 250", "debit = 0, credit = 100"):
            proprietaire.execute(
                f"UPDATE comptabilite_ligneecriture SET {modification} WHERE id = %s",  # noqa: S608
                [cible],
            )
            assert empreinte_jeu_de_donnees(predicat, params) != avant, modification
            proprietaire.execute(
                "UPDATE comptabilite_ligneecriture SET debit = 100, credit = 0 WHERE id = %s",
                [cible],
            )
        credit = proprietaire.execute(
            "SELECT l.id FROM comptabilite_ligneecriture l "
            "JOIN referentiels_compte c ON c.id = l.account_id WHERE c.code = '6012'"
        ).fetchone()[0]
        proprietaire.execute(
            "UPDATE comptabilite_ligneecriture SET credit = 75 WHERE id = %s", [credit]
        )
        assert empreinte_jeu_de_donnees(predicat, params) != avant, "credit seul"
