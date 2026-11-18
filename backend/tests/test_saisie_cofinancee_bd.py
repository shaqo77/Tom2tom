# ruff: noqa: F811, E501
"""La répartition entre bailleurs câblée à la SAISIE : une ligne qui porte une clé de cofinancement
est ventilée par `saisir_ecriture` elle-même, sans que l'appelant calcule les parts. L11-A2.

Avant : la ventilation n'existait que comme un service que seuls les tests appelaient ; la saisie
exigeait que l'appelant produise lui-même une ligne par accord (et se trompe sur les arrondis).
"""

import datetime
import random
from decimal import Decimal

import pytest

from niveau1_socle.comptabilite.services import (
    comptabiliser_ecriture,
    saisir_ecriture,
    valider_ecriture,
)
from niveau1_socle.financements.cles import CleInvalide, lignes_ventilees
from niveau1_socle.financements.services import changer_statut_accord
from tests.test_cles_cofinancement_bd import _version, cles  # noqa: F401
from tests.test_cycle_ecriture_bd import _creer_projet, _poser, decor  # noqa: F401
from tests.test_financements_bd import _accord, _activer, cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
D = Decimal
MARS = datetime.date(2026, 3, 10)


def _saisie(profils, projet, lignes, *, date=MARS, **champs):
    return saisir_ecriture(
        utilisateur=profils["amina"],
        project_id=projet.id,
        journal="OD",
        date_comptable=date,
        libelle="Charge commune",
        lignes=lignes,
        **champs,
    )


def _charge_avec_cle(montant, cle="CHARGES", sens="debit", **autres):
    contre = "credit" if sens == "debit" else "debit"
    return [
        {"compte": "6011", sens: str(montant), "cle": cle},
        {"compte": "5211", contre: str(montant)},
    ] + autres.get("supplement", [])


def test_une_ligne_portant_une_cle_est_ventilee_a_la_saisie(cles):
    _, projet, profils, accords, cle = cles
    version = _version(profils, cle, accords, {"IDA": 60, "GOV": 30, "UE": 10})
    ecriture = _saisie(profils, projet, _charge_avec_cle("1001"))
    charges = ecriture.lignes.filter(account__code="6011")
    assert {ligne.agreement_id: ligne.debit for ligne in charges} == {
        accords["IDA"].pk: D(600),
        accords["GOV"].pk: D(301),  # le porteur d'arrondi absorbe le reliquat
        accords["UE"].pk: D(100),
    }
    assert {ligne.cofunding_key_version_id for ligne in charges} == {version.pk}
    assert sum(ligne.debit for ligne in charges) == D(1001)
    contre = ecriture.lignes.get(account__code="5211")
    assert contre.credit == D(1001) and contre.agreement_id is None  # la contrepartie ne bouge pas
    valider_ecriture(ecriture, utilisateur=profils["bruno"])
    assert comptabiliser_ecriture(ecriture, utilisateur=profils["claire"]).status == "posted"


def test_le_resultat_est_celui_du_service_de_ventilation(cles):
    """Une seule règle de calcul : la saisie et `lignes_ventilees` donnent les mêmes lignes."""
    _, projet, profils, accords, cle = cles
    version = _version(profils, cle, accords, {"IDA": 1, "GOV": 1, "UE": 1})
    ecriture = _saisie(profils, projet, _charge_avec_cle("1000"))
    attendu = {
        ligne["agreement_id"]: D(ligne["debit"])
        for ligne in lignes_ventilees(version, montant="1000", devise="DJF", compte="6011")
    }
    obtenu = {
        ligne.agreement_id: ligne.debit for ligne in ecriture.lignes.filter(account__code="6011")
    }
    assert obtenu == attendu


def test_un_remboursement_au_credit_est_ventile_au_credit(cles):
    _, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 70, "GOV": 30})
    ecriture = _saisie(profils, projet, _charge_avec_cle("100", sens="credit"))
    credits = ecriture.lignes.filter(account__code="6011")
    assert sorted(ligne.credit for ligne in credits) == [D(30), D(70)]
    assert all(ligne.debit == 0 for ligne in credits)


def test_la_version_de_cle_applicable_est_celle_de_la_date_comptable(cles):
    _, projet, profils, accords, cle = cles
    v1 = _version(profils, cle, accords, {"IDA": 70, "GOV": 30}, debut=datetime.date(2026, 1, 1))
    v2 = _version(profils, cle, accords, {"IDA": 50, "GOV": 50}, debut=datetime.date(2026, 7, 1))
    mars = _saisie(profils, projet, _charge_avec_cle("1000"), date=MARS)
    aout = _saisie(profils, projet, _charge_avec_cle("1000"), date=datetime.date(2026, 8, 10))
    assert {ligne.cofunding_key_version_id for ligne in mars.lignes.all()} == {v1.pk, None}
    assert {ligne.cofunding_key_version_id for ligne in aout.lignes.all()} == {v2.pk, None}
    assert {ligne.agreement_id: ligne.debit for ligne in mars.lignes.filter(account__code="6011")}[
        accords["IDA"].pk
    ] == D(700)
    assert {ligne.agreement_id: ligne.debit for ligne in aout.lignes.filter(account__code="6011")}[
        accords["IDA"].pk
    ] == D(500)


def test_en_devise_les_montants_de_tenue_et_en_devise_sont_ventiles_chacun_a_son_pas(cles):
    _, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 60, "GOV": 30, "UE": 10})
    lignes = [
        {"compte": "6011", "debit": "17702", "debit_cur": "100.01", "cle": "CHARGES"},
        {"compte": "5211", "credit": "17702", "credit_cur": "100.01"},
    ]
    ecriture = _saisie(profils, projet, lignes, devise="USD", taux="177")
    charges = list(ecriture.lignes.filter(account__code="6011"))
    assert sum(ligne.debit for ligne in charges) == D("17702")  # tenue : le total est conservé
    assert sum(ligne.debit_cur for ligne in charges) == D("100.01")  # devise : idem
    assert all(
        ligne.debit == ligne.debit.to_integral_value() for ligne in charges
    )  # DJF : pas de 0,01
    assert all(ligne.currency_id == "USD" for ligne in charges)


def test_une_ligne_sans_cle_et_une_ecriture_sans_cle_ne_changent_pas(cles):
    _, projet, profils, accords, cle = cles
    lignes = [{"compte": "6011", "debit": "10"}, {"compte": "5211", "credit": "10"}]
    ecriture = _saisie(profils, projet, lignes)
    assert ecriture.lignes.count() == 2
    assert ecriture.lignes.filter(cofunding_key_version_id__isnull=False).count() == 0


def test_les_lignes_de_l_appelant_ne_sont_pas_modifiees(cles):
    _, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 60, "GOV": 40})
    lignes = _charge_avec_cle("100")
    avant = [dict(ligne) for ligne in lignes]
    _saisie(profils, projet, lignes)
    assert lignes == avant


def test_une_cle_inconnue_est_refusee_et_nommee(cles):
    _, projet, profils, accords, cle = cles
    with pytest.raises(CleInvalide, match="FANTOME.*n.existe pas"):
        _saisie(profils, projet, _charge_avec_cle("100", cle="FANTOME"))


def test_une_cle_d_un_autre_projet_est_introuvable(cles):
    from niveau1_socle.financements.cles import developper_cles

    organisation, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 60, "GOV": 40})
    autre = _creer_projet(organisation, "AUTRE")
    _poser(organisation)
    with pytest.raises(CleInvalide, match="CHARGES"):  # la clé existe, mais pour un autre projet
        developper_cles(
            _charge_avec_cle("100"), project_id=autre.id, date_comptable=MARS, devise="DJF"
        )


def test_sans_version_en_vigueur_a_la_date_la_saisie_est_refusee(cles):
    _, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 60, "GOV": 40}, debut=datetime.date(2026, 6, 1))
    with pytest.raises(CleInvalide, match="2026-03-10"):
        _saisie(profils, projet, _charge_avec_cle("100"), date=MARS)  # avant la 1re version


def test_une_ligne_ne_peut_pas_porter_a_la_fois_une_cle_et_un_accord(cles):
    _, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 60, "GOV": 40})
    lignes = [
        {"compte": "6011", "debit": "100", "cle": "CHARGES", "agreement_id": accords["IDA"].pk},
        {"compte": "5211", "credit": "100"},
    ]
    with pytest.raises(CleInvalide, match="accord"):
        _saisie(profils, projet, lignes)


def test_un_accord_de_la_cle_qui_n_est_plus_actif_ne_recoit_rien(cles):
    _, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 60, "GOV": 40})
    changer_statut_accord(accords["GOV"], "suspendu", utilisateur=profils["dora"], motif="test")
    with pytest.raises(Exception, match="GOV|suspendu|actif"):
        _saisie(profils, projet, _charge_avec_cle("100"))


def test_un_montant_non_exprimable_dans_la_monnaie_est_refuse_et_ne_laisse_rien(cles):
    _, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 60, "GOV": 40})
    from niveau1_socle.comptabilite.models import Ecriture

    avant = Ecriture.objects.count()
    with pytest.raises(ValueError, match="pas"):
        _saisie(profils, projet, _charge_avec_cle("100.5"))  # DJF : pas de décimale
    assert Ecriture.objects.count() == avant


def test_pour_tout_montant_le_total_ventile_est_celui_de_la_depense(cles):
    _, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 33, "GOV": 33, "UE": 34})
    hasard = random.Random(42)
    for _ in range(15):
        montant = hasard.randint(1, 10_000_000)
        ecriture = _saisie(profils, projet, _charge_avec_cle(montant))
        charges = ecriture.lignes.filter(account__code="6011")
        assert sum(ligne.debit for ligne in charges) == D(montant)


def test_une_part_nulle_apres_arrondi_ne_produit_pas_de_ligne_a_la_saisie(cles):
    _, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 99, "GOV": 1, "UE": 1}, porteur="IDA")
    ecriture = _saisie(profils, projet, _charge_avec_cle("1"))
    charges = ecriture.lignes.filter(account__code="6011")
    assert [(ligne.agreement_id, ligne.debit) for ligne in charges] == [(accords["IDA"].pk, D(1))]
