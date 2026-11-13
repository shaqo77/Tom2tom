"""Le calcul et les contrôles du profil de décaissement, sans base de données. Voir L5-T03bis."""

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from niveau3_config.services.decaissement import (
    ProfilViole,
    documents_exiges,
    minimum_de_demande,
    montant_a_retirer,
    plafond_des_comptes,
    verifier_delai,
    verifier_eligibilite,
)

D = Decimal
montants = st.decimals(min_value=D("0.01"), max_value=D("1e9"), places=2)
taux = st.decimals(min_value=D("0.000001"), max_value=D(1), places=6)


@given(depense=montants, rate=taux)
@settings(max_examples=2000, deadline=None)
def test_on_ne_reclame_jamais_plus_que_le_taux_ne_l_autorise(depense, rate):
    retrait = montant_a_retirer(depense, rate, "taxes_included", pas=D("0.01"))
    assert 0 <= retrait <= depense * rate  # arrondi vers zéro : jamais un centime de trop
    assert depense * rate - retrait < D("0.01")  # et jamais plus d'un pas de moins
    assert retrait == retrait.quantize(D("0.01"))


@given(depense=montants)
@settings(max_examples=500, deadline=None)
def test_a_taux_plein_et_taxes_comprises_la_depense_est_demandee_entiere(depense):
    assert montant_a_retirer(depense, D(1), "taxes_included", pas=D("0.01")) == depense


@given(depense=montants, rate=taux, taxes_pct=st.decimals(min_value=0, max_value=1, places=2))
@settings(max_examples=1000, deadline=None)
def test_l_assiette_hors_taxes_ne_depasse_jamais_l_assiette_taxes_comprises(
    depense, rate, taxes_pct
):
    taxes = (depense * taxes_pct).quantize(D("0.01"))
    hors = montant_a_retirer(depense, rate, "net_of_taxes", taxes=taxes, pas=D("0.01"))
    comprises = montant_a_retirer(depense, rate, "taxes_included", taxes=taxes, pas=D("0.01"))
    assert hors <= comprises


@given(a=montants, b=montants, rate=taux)
@settings(max_examples=1000, deadline=None)
def test_le_montant_a_retirer_croit_avec_la_depense(a, b, rate):
    petit, grand = sorted((a, b))
    assert montant_a_retirer(petit, rate, pas=D("0.01")) <= montant_a_retirer(
        grand, rate, pas=D("0.01")
    )


@given(depenses=st.lists(st.integers(1, 10**9), min_size=1, max_size=20), rate=taux)
@settings(max_examples=500, deadline=None)
def test_la_somme_des_retraits_ligne_a_ligne_ne_depasse_jamais_le_taux_sur_le_total(depenses, rate):
    """Une demande de plusieurs lignes ne réclame jamais plus que le taux sur son total."""
    ligne_a_ligne = sum(montant_a_retirer(D(d), rate, pas=D(1)) for d in depenses)
    assert ligne_a_ligne <= sum(D(d) for d in depenses) * rate


def test_exemples_a_la_main():
    assert montant_a_retirer(D("1000"), D("0.8")) == D(800)
    assert montant_a_retirer(D("1001"), D("0.8")) == D(800)  # 800,8 arrondi vers zéro, franc entier
    assert montant_a_retirer(D("100.01"), D("0.8"), pas=D("0.01")) == D("80.00")
    assert montant_a_retirer(D(1000), D("0.8"), "net_of_taxes", taxes=D(180)) == D(656)  # 820 × 0,8
    assert montant_a_retirer(D(1000), D("0.8"), "taxes_included", taxes=D(180)) == D(800)


@pytest.mark.parametrize(
    "depense, rate, taxes, message",
    [
        (-1, "0.5", 0, "positives"),
        (10, "0.5", 11, "ne dépassant pas"),
        (10, "0", 0, "]0 ; 1]"),
        (10, "1.01", 0, "]0 ; 1]"),
    ],
)
def test_des_entrees_incoherentes_sont_refusees(depense, rate, taxes, message):
    with pytest.raises(ProfilViole, match=message.replace("]", r"\]").replace("[", r"\[")):
        montant_a_retirer(D(depense), D(rate), taxes=D(taxes))


# --- éligibilité, délai ---------------------------------------------------------------------


def _profil(**champs):
    return SimpleNamespace(
        **({"eligibility_date": None, "disbursement_deadline": None, "version": 1} | champs)
    )


def _regle(**champs):
    return SimpleNamespace(**({"eligibility_from": None, "eligibility_to": None} | champs))


def test_une_depense_anterieure_a_la_date_d_eligibilite_est_refusee_en_nommant_la_date():
    profil = _profil(eligibility_date=datetime.date(2026, 3, 1))
    verifier_eligibilite(profil, _regle(), datetime.date(2026, 3, 1))  # le jour même : finançable
    with pytest.raises(
        ProfilViole,
        match="antérieure à la date d'éligibilité du profil "
        r"\(2026-03-01\)",
    ):
        verifier_eligibilite(profil, _regle(), datetime.date(2026, 2, 28))


def test_la_fenetre_d_eligibilite_de_la_categorie_est_bornee_et_nomme_ses_dates():
    regle = _regle(
        eligibility_from=datetime.date(2026, 2, 1), eligibility_to=datetime.date(2026, 8, 31)
    )
    profil = _profil()
    verifier_eligibilite(profil, regle, datetime.date(2026, 2, 1))
    verifier_eligibilite(profil, regle, datetime.date(2026, 8, 31))  # la fin est incluse
    with pytest.raises(ProfilViole, match=r"début d'éligibilité de la catégorie \(2026-02-01\)"):
        verifier_eligibilite(profil, regle, datetime.date(2026, 1, 31))
    with pytest.raises(ProfilViole, match=r"fin d'éligibilité de la catégorie \(2026-08-31\)"):
        verifier_eligibilite(profil, regle, datetime.date(2026, 9, 1))


def test_le_delai_de_decaissement_est_inclusif_et_nomme_sa_date():
    profil = _profil(disbursement_deadline=datetime.date(2027, 6, 30))
    verifier_delai(profil, datetime.date(2027, 6, 30))
    with pytest.raises(ProfilViole, match=r"date limite 2027-06-30, demande du 2027-07-01"):
        verifier_delai(profil, datetime.date(2027, 7, 1))
    verifier_delai(_profil(), datetime.date(2099, 1, 1))  # pas de date limite : rien à refuser


# --- minimum et pièces ----------------------------------------------------------------------


def _methode(**champs):
    return SimpleNamespace(
        **(
            {
                "min_application_amount": None,
                "min_application_pct_of_ceiling": None,
                "supporting_docs": ["soe"],
                "full_doc_threshold": None,
            }
            | champs
        )
    )


def _profil_avec_comptes(*plafonds):
    comptes = [
        SimpleNamespace(ceiling_kind="fixed" if p is not None else "variable", ceiling_amount=p)
        for p in plafonds
    ]
    return SimpleNamespace(comptes=SimpleNamespace(all=lambda: comptes))


def test_le_minimum_est_une_valeur_fixe_ou_un_pourcentage_du_plafond():
    profil = _profil_avec_comptes(D(1_000_000))
    fixe = minimum_de_demande(profil, _methode(min_application_amount=D(100_000)))
    assert fixe.montant == D(100_000) and "100000" in fixe.explication
    pct = minimum_de_demande(profil, _methode(min_application_pct_of_ceiling=D("0.2")))
    assert pct.montant == D(200_000) and "20 % du plafond (1000000)" in pct.explication
    assert minimum_de_demande(profil, _methode()) is None


def test_un_pourcentage_sans_plafond_fixe_est_une_erreur_de_parametrage():
    for profil in (_profil_avec_comptes(), _profil_avec_comptes(None)):
        with pytest.raises(ProfilViole, match="aucun plafond fixe"):
            minimum_de_demande(profil, _methode(min_application_pct_of_ceiling=D("0.2")))


def test_le_plafond_des_comptes_est_la_somme_des_plafonds_fixes():
    assert plafond_des_comptes(_profil_avec_comptes(D(300), D(700), None)) == D(1000)
    assert plafond_des_comptes(_profil_avec_comptes(None)) is None


def test_une_depense_au_dela_du_seuil_exige_les_copies_de_pieces_et_non_l_etat_certifie():
    methode = _methode(supporting_docs=["soe", "summary_sheet"], full_doc_threshold=D(500_000))
    assert documents_exiges(methode, [D(100), D(500_000)]) == [
        "soe",
        "summary_sheet",
    ]  # pas au-delà
    assert documents_exiges(methode, [D(100), D(500_001)]) == ["records", "summary_sheet"]
    assert documents_exiges(_methode(full_doc_threshold=None), [D(10**9)]) == ["soe"]
