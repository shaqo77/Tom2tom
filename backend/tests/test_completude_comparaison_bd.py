# ruff: noqa: F811
"""Complétude avant soumission et comparaison de versions. Voir L5-T04bis.

Contrôles du plan : un profil incomplet voit sa soumission refusée, chaque manque nommé ; la
comparaison V1/V2 détecte les quatre sortes de différences ; l'écart entre budget et financements
n'est jamais une erreur bloquante.
"""

import datetime
import json
from decimal import Decimal

import pytest

from niveau3_config.models import ProfilDecaissement
from niveau3_config.services.activation import ActivationRefusee, valider_profil
from niveau3_config.services.comparaison import comparer_versions
from niveau3_config.services.completude import verifier_completude
from niveau3_config.services.versions import nouvelle_version
from tests.outils_profil import creer_profil
from tests.test_activation_bd import _exigence, _profil, cfg  # noqa: F401
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
D = datetime.date
M = Decimal


def _complet(cfg, **champs):
    """Un profil sans aucune anomalie ni avertissement."""
    cat = cfg[4]
    requirement = _exigence(cfg, 1, D(2026, 1, 1), statut="active", code="DECAISSEMENT")
    return _profil(
        cfg,
        statut="draft",
        eligibility_date=D(2026, 1, 1),
        requirement=requirement,
        regles=[(cat["serv"], "0.8")],
        **champs,
    )


def test_un_profil_complet_na_ni_erreur_ni_avertissement_et_le_budget_nest_pas_en_cause(cfg):
    profil = _complet(cfg)
    resultat = verifier_completude(profil)
    # Seul manque non bloquant : aucun compte désigné (avertissement). Les allocations (100) sont
    # très inférieures au montant de l'accord : un budget non financé n'est pas une anomalie.
    assert resultat.complet and resultat.codes() == {"sans_compte_designe"}


@pytest.mark.parametrize(
    "champs, code",
    [
        ({"methodes": ()}, "aucune_methode"),
        ({"methodes": [{"method": "advance", "supporting_docs": []}]}, "methode_sans_pieces"),
        ({"regles": []}, "aucune_categorie"),
    ],
)
def test_chaque_manque_bloquant_est_nomme(cfg, champs, code):
    profil = _profil(cfg, statut="draft", **champs)
    resultat = verifier_completude(profil)
    assert not resultat.complet and code in {a.code for a in resultat.bloquantes}
    with pytest.raises(ActivationRefusee, match="Profil incomplet"):
        valider_profil(utilisateur=cfg[2]["vera"], profil=profil)
    profil.refresh_from_db()
    assert profil.status == "draft"


def test_des_allocations_au_dela_du_montant_de_laccord_bloquent(cfg):
    _, _, _, _, cat, _ = cfg
    profil = _profil(
        cfg,
        statut="draft",
        regles=[
            (cat["serv"], "0.8", {"allocation": M(600)}),
            (cat["biens"], "0.8", {"allocation": M(600)}),
        ],
    )
    manque = {a.code: str(a.message) for a in verifier_completude(profil).bloquantes}
    assert "1200" in manque["allocations_excessives"] and "1000" in manque["allocations_excessives"]


def test_une_exigence_source_non_validee_bloque(cfg):
    proposee = _exigence(cfg, 1, D(2026, 1, 1), code="SOURCE")
    profil = _profil(cfg, statut="draft", requirement=proposee)
    assert "exigence_non_validee" in {a.code for a in verifier_completude(profil).bloquantes}
    valide = _exigence(cfg, 2, D(2026, 1, 1), statut="validated", code="SOURCE")
    ok = _profil(cfg, version=2, statut="draft", requirement=valide)
    assert "exigence_non_validee" not in {a.code for a in verifier_completude(ok).bloquantes}


def test_une_version_qui_chevauche_une_version_active_bloque(cfg):
    _profil(cfg, version=1, valid_from=D(2026, 6, 1), statut="active")
    ancienne = _profil(cfg, version=2, valid_from=D(2026, 3, 1), statut="draft")
    assert "chevauchement" in {a.code for a in verifier_completude(ancienne).bloquantes}
    suivante = _profil(cfg, version=3, valid_from=D(2026, 9, 1), statut="draft")
    assert "chevauchement" not in {a.code for a in verifier_completude(suivante).bloquantes}


def test_des_dates_incoherentes_bloquent(cfg):
    profil = _profil(cfg, statut="draft")
    profil.valid_to = profil.valid_from  # en mémoire : la base ne laisserait pas l'enregistrer
    profil.eligibility_date, profil.closing_date = D(2027, 1, 1), D(2026, 6, 1)
    messages = [str(a.message) for a in verifier_completude(profil).bloquantes]
    assert any("fin de validité" in m for m in messages)
    assert any("eligibility_date" in m and "closing_date" in m for m in messages)


def test_les_avertissements_ne_bloquent_pas_et_sont_traces_avec_leur_justification(cfg):
    from core.models import AuditLog

    _, _, profils, _, cat, _ = cfg
    profil = _profil(cfg, statut="draft", regles=[(cat["serv"], "1")])
    codes = {a.code for a in verifier_completude(profil).avertissements}
    assert codes == {
        "taux_integral",
        "sans_exigence_source",
        "sans_date_eligibilite",
        "sans_compte_designe",
    }
    valider_profil(
        utilisateur=profils["vera"],
        profil=profil,
        justifications={"taux_integral": "Prévu par l'avenant 3"},
    )
    profil.refresh_from_db()
    assert profil.status == "validated"
    entree = AuditLog.objects.get(object_id=profil.id, action="disbursement_profile_validated")
    tracees = json.loads(entree.after["avertissements"])
    assert tracees["taux_integral"] == "Prévu par l'avenant 3"
    assert tracees["sans_date_eligibilite"] == ""  # non justifié : tracé tel quel


# --- comparaison ---------------------------------------------------------------------------


def test_la_comparaison_detecte_identiques_modifies_ajoutes_et_supprimes(cfg):
    _, _, _, _, cat, _ = cfg
    a = _profil(
        cfg,
        version=1,
        statut="draft",
        methodes=("advance", "reimbursement"),
        regles=[(cat["serv"], "0.8"), (cat["biens"], "0.9")],
    )
    b = _profil(
        cfg,
        version=2,
        valid_from=D(2026, 7, 1),
        statut="draft",
        closing_date=D(2028, 1, 1),
        methodes=("reimbursement", "direct_payment"),
        regles=[(cat["serv"], "0.7"), (cat["biens_a"], "0.9")],
    )
    c = comparer_versions(a, b)
    assert not c.identiques
    assert c.methodes.identiques == ["reimbursement"]
    assert c.methodes.supprimes == ["advance"] and c.methodes.ajoutes == ["direct_payment"]
    assert c.categories.supprimes == ["BIENS"] and c.categories.ajoutes == ["BIENS-A"]
    ((code, ecarts),) = c.categories.modifies
    assert code == "SERV" and ecarts == {"funding_rate": (M("0.8"), M("0.7"))}
    assert {"valid_from", "closing_date"} <= set(c.parametres.modifies[0][1])


def test_une_copie_est_identique_a_son_original_et_les_comptes_sont_compares(cfg):
    organisation, projet, profils, accord, cat, _ = cfg
    from niveau1_socle.financements.services import creer_compte_bancaire

    compte = creer_compte_bancaire(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code="CB",
        type="designe",
        devise="DJF",
        banque="BCD",
        numero="DJ-0000-1",
        accord=accord,
    )
    original = _profil(cfg, statut="draft", comptes=[{"compte": compte, "plafond": M(500)}])
    copie = nouvelle_version(
        ProfilDecaissement.objects.get(pk=original.pk),
        valid_from=D(2026, 7, 1),
        utilisateur=profils["vera"],
    )
    c = comparer_versions(original, copie)
    assert c.methodes.inchangee and c.categories.inchangee and c.comptes.inchangee
    assert [champ for champ in c.parametres.modifies[0][1]] == ["valid_from"]  # seule la date
    assert (copie.version, copie.status) == (2, "draft")
    assert copie.comptes.get().bank_account_id == compte.id  # le compte désigné est repris
    with pytest.raises(ValueError, match="sans règle"):
        nouvelle_version(
            original,
            valid_from=D(2026, 8, 1),
            utilisateur=profils["vera"],
            allocations={cat["biens"].pk: M(5)},
        )
    with pytest.raises(ValueError, match="jalons inconnus"):
        nouvelle_version(
            original, valid_from=D(2026, 8, 1), utilisateur=profils["vera"], dates={"valid_to": 1}
        )


def test_on_ne_compare_que_deux_versions_dun_meme_accord(cfg):
    from tests.test_financements_bd import _accord

    organisation, projet, profils, accord, cat, _ = cfg
    autre = _accord(projet, profils, accord.bailleur, "DON-2", devise="DJF", montant_initial="500")
    a = _profil(cfg, statut="draft")
    b = creer_profil(organisation, projet, autre, statut="draft", regles=[])
    with pytest.raises(ValueError, match="même accord"):
        comparer_versions(a, b)


def test_une_version_active_programmee_au_dela_du_debut_dune_nouvelle_version_la_chevauche(cfg):
    """V1 active du 01/01 au 01/09 : une version qui commence le 01/06 chevauche V1 par sa fin."""
    _profil(cfg, version=1, valid_from=D(2026, 1, 1), valid_to=D(2026, 9, 1), statut="active")
    courte = _profil(cfg, version=2, valid_from=D(2026, 6, 1), statut="draft")
    assert "chevauchement" in {a.code for a in verifier_completude(courte).bloquantes}
    apres = _profil(cfg, version=3, valid_from=D(2026, 9, 1), statut="draft")
    assert "chevauchement" not in {a.code for a in verifier_completude(apres).bloquantes}
