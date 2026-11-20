# ruff: noqa: F811, E501
"""L'API HTTP du compte spécial : justifications soumises à la Banque, situation, rapport. L11-D4.

Montants en chaînes, refus au format `{code, message}`, habilitations côté serveur : consulter pour
lire, saisir pour justifier et annuler, publier pour le rapport.
"""

import datetime
from decimal import Decimal

import pytest
from django.db import connection

from niveau1_socle.tresorerie.models import JustificationCompteSpecial
from tests.test_api_marches_bd import appeler
from tests.test_compte_special_bd import FIN, _demande_a_part, special  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def _nb(special) -> int:
    """Les justifications EN BASE : l'organisation se repose (la RLS cache tout après un appel HTTP,
    et le compte vaudrait toujours zéro)."""
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(special[0].id)])
    return JustificationCompteSpecial.objects.count()


def _chemin(compte, fin):
    return f"/comptes/{compte.id}/{fin}"


def _poster(special, montant="200", **champs):
    _, _, profils, _, compte, demande = special
    corps = {
        "demande": str(demande.id),
        "montant": montant,
        "date_soumission": "2026-03-20",
    } | champs
    return appeler(profils["amina"], "post", _chemin(compte, "justifications-banque/"), corps)


def test_une_justification_se_cree_se_liste_et_les_montants_sont_des_chaines(special):
    _, _, profils, _, compte, demande = special
    r = _poster(special)
    assert r.status_code == 201, r.content
    j = r.json()
    assert (j["demande"], j["montant"], j["date_soumission"], j["annulee"]) == (
        demande.numero,
        "200.0000",
        "2026-03-20",
        False,
    )
    liste = appeler(profils["bruno"], "get", _chemin(compte, "justifications-banque/"))
    assert liste.status_code == 200 and [x["id"] for x in liste.json()] == [j["id"]]


@pytest.mark.parametrize(
    "champs",
    [
        {"montant": "0"},
        {"montant": "-5"},
        {"montant": 1.5},
        {"montant": "abc"},
        {"montant": "300.01"},
        {"demande": "pas-un-uuid"},
        {"date_soumission": "demain"},
    ],
)
def test_une_justification_invalide_est_refusee_au_format_stable_sans_rien_creer(special, champs):
    r = _poster(special, **champs)
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}, (champs, r.content)
    assert _nb(special) == 0


def test_une_justification_en_double_est_refusee(special):
    assert _poster(special, "100").status_code == 201
    r = _poster(special, "100")
    assert r.status_code == 422 and "déjà justifiée" in r.json()["message"]
    assert _nb(special) == 1


def test_justifier_et_annuler_exigent_saisir_et_lire_exige_consulter(special):
    _, _, profils, _, compte, demande = special
    refus = appeler(
        profils["bruno"],
        "post",
        _chemin(compte, "justifications-banque/"),
        {"demande": str(demande.id), "montant": "10"},
    )
    assert refus.status_code == 403 and _nb(special) == 0
    j = _poster(special).json()
    sans_droit = appeler(
        profils["bruno"], "post", f"/justifications-banque/{j['id']}/annulation/", {"motif": "x"}
    )
    assert sans_droit.status_code == 403
    inconnu = "00000000-0000-0000-0000-000000000000"
    assert (
        appeler(profils["amina"], "get", _chemin(compte, "justifications-banque/")).status_code
        == 200
    )
    assert (
        appeler(
            profils["amina"],
            "post",
            f"/justifications-banque/{inconnu}/annulation/",
            {"motif": "x"},
        ).status_code
        == 404
    )


def test_annuler_exige_un_motif_et_ne_se_fait_qu_une_fois(special):
    _, _, profils, _, _, _ = special
    j = _poster(special).json()
    chemin = f"/justifications-banque/{j['id']}/annulation/"
    assert appeler(profils["amina"], "post", chemin, {}).status_code == 422
    r = appeler(profils["amina"], "post", chemin, {"motif": "montant erroné"})
    assert (
        r.status_code == 200
        and r.json()["annulee"] is True
        and r.json()["motif_annulation"] == "montant erroné"
    )
    encore = appeler(profils["amina"], "post", chemin, {"motif": "encore"})
    assert encore.status_code == 409 and encore.json()["code"] == "TRANSITION_INTERDITE"
    assert _poster(special, "250").status_code == 201  # la bonne justification, après annulation


def test_la_situation_rend_les_lignes_de_l_annexe_9_en_chaines(special):
    _, _, profils, _, compte, demande = special
    _poster(special, "200")
    r = appeler(
        profils["amina"],
        "get",
        _chemin(
            compte, f"situation-compte-special/?date={FIN.isoformat()}&demande={demande.numero}"
        ),
    )
    assert r.status_code == 200, r.content
    s = r.json()
    assert s["complet"] is True and s["manques"] == [] and s["devise"] == "DJF"
    assert s["avances"] == [{"demande": demande.numero, "montant": "300.0000"}]
    assert (s["total_avances"], s["solde_cloture"]) == ("300.0000", "100.0000")
    # chaînes décimales EXACTES (« 0 » ou « 0.0000 » : même valeur, jamais un flottant)
    assert all(
        isinstance(s[k], str)
        for k in ("justifie_cette_demande", "justifie_precedemment", "total_justifie", "ecart")
    )
    assert (Decimal(s["justifie_cette_demande"]), Decimal(s["justifie_precedemment"])) == (
        Decimal("200"),
        0,
    )
    assert (Decimal(s["total_justifie"]), Decimal(s["ecart"])) == (Decimal("300"), 0)


def test_la_situation_est_incomplete_sans_releve_et_exige_une_date(special):
    _, _, profils, _, compte, _ = special
    r = appeler(
        profils["amina"], "get", _chemin(compte, "situation-compte-special/?date=2026-01-15")
    )
    s = r.json()
    assert r.status_code == 200 and s["complet"] is False and s["manques"] == ["cloture"]
    assert s["solde_cloture"] is None and s["ecart"] is None
    assert (
        appeler(profils["amina"], "get", _chemin(compte, "situation-compte-special/")).status_code
        == 422
    )
    assert (
        appeler(
            profils["amina"], "get", _chemin(compte, "situation-compte-special/?date=hier")
        ).status_code
        == 422
    )


def test_la_situation_refuse_un_compte_non_special(special):
    from niveau1_socle.financements.services import creer_compte_bancaire

    organisation, projet, profils, _, _, _ = special
    designe = creer_compte_bancaire(
        utilisateur=profils["dora"], project_id=projet.id, code="CD-DJF", type="designe",
        devise="DJF", banque="BCD", numero="DJ21 0001 0000 0099 8877",
    )  # fmt: skip
    r = appeler(
        profils["amina"], "get", _chemin(designe, "situation-compte-special/?date=2026-03-31")
    )
    assert r.status_code == 422 and "n'est pas un compte spécial" in r.json()["message"]


def test_le_rapport_se_publie_se_scelle_et_exige_publier(special):
    _, _, profils, _, compte, demande = special
    _poster(special, "200")
    corps = {"date_fin": FIN.isoformat(), "demande": demande.numero}
    assert (
        appeler(
            profils["amina"], "post", _chemin(compte, "rapport-compte-special/"), corps
        ).status_code
        == 403
    )
    r = appeler(profils["pia"], "post", _chemin(compte, "rapport-compte-special/"), corps)
    assert r.status_code == 201, r.content
    p = r.json()
    assert p["modele"] == "BAD_RECONCILIATION_CS" and len(p["scelle"]) == 64
    assert p["valeurs"]["R700/PER"] == "0" and p["valeurs"]["R400/PER"] == "200"
    assert datetime.date.fromisoformat(FIN.isoformat()) == FIN


def test_le_rapport_est_refuse_sans_releve_a_la_date(special):
    _, _, profils, _, compte, _ = special
    r = appeler(
        profils["pia"],
        "post",
        _chemin(compte, "rapport-compte-special/"),
        {"date_fin": "2026-01-15"},
    )
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}


def test_sans_habilitation_aucune_lecture_n_est_permise(special):
    """La situation se calcule SANS contrôle d'habilitation (états du moteur) : l'API est la seule
    barrière, elle doit refuser un utilisateur du même organisme qui n'a aucun droit sur le projet."""
    from django.contrib.auth import get_user_model

    organisation, _, _, _, compte, _ = special
    inconnu = get_user_model().objects.create_user("zoe", password="x", org_id=organisation.id)
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])
    for fin in ("justifications-banque/", "situation-compte-special/?date=2026-03-31"):
        assert appeler(inconnu, "get", _chemin(compte, fin)).status_code == 403, fin


def test_le_montant_est_facultatif_et_vaut_alors_tout_ce_que_la_demande_retire(special):
    _, _, profils, _, compte, demande = special
    r = appeler(
        profils["amina"],
        "post",
        _chemin(compte, "justifications-banque/"),
        {"demande": str(demande.id), "date_soumission": "2026-03-20"},
    )
    assert r.status_code == 201, r.content
    assert Decimal(r.json()["montant"]) == Decimal("300")


def test_la_situation_detaille_les_justifications_demande_par_demande(special):
    _, _, profils, _, compte, demande = special
    _poster(special, "200")
    r = appeler(
        profils["amina"],
        "get",
        _chemin(
            compte, f"situation-compte-special/?date={FIN.isoformat()}&demande={demande.numero}"
        ),
    )
    detail = r.json()["justifications"]
    assert len(detail) == 1
    assert (detail[0]["demande"], detail[0]["date_soumission"]) == (demande.numero, "2026-03-20")
    assert (Decimal(detail[0]["montant"]), detail[0]["en_cours"], detail[0]["comptee"]) == (
        Decimal("200"),
        True,
        True,
    )


def test_la_note_d_ecart_est_gardee_et_scellee_avec_le_rapport(special):
    _, _, profils, _, compte, demande = special
    _poster(special, "150")
    chemin = _chemin(compte, "rapport-compte-special/")
    base = {"date_fin": FIN.isoformat(), "demande": demande.numero}
    sans = appeler(profils["pia"], "post", chemin, base).json()
    avec = appeler(
        profils["pia"], "post", chemin, base | {"note_ecart": "Intérêts créditeurs du mois"}
    )
    assert avec.status_code == 201, avec.content
    from niveau4_reporting.publication.models import RapportPublie

    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(special[0].id)])
    rapport = RapportPublie.objects.get(pk=avec.json()["id"])
    assert rapport.params["note_ecart"] == "Intérêts créditeurs du mois"
    assert "note_ecart" not in RapportPublie.objects.get(pk=sans["id"]).params
    assert avec.json()["scelle"] != sans["scelle"]  # la note fait partie de ce qui est scellé
    assert avec.json()["valeurs"]["R700/PER"] == "50"  # la note n'entre dans aucun calcul


def test_une_note_trop_longue_est_refusee(special):
    _, _, profils, _, compte, _ = special
    r = appeler(
        profils["pia"], "post", _chemin(compte, "rapport-compte-special/"),
        {"date_fin": FIN.isoformat(), "note_ecart": "x" * 4001},
    )  # fmt: skip
    assert r.status_code == 422 and "dépasse 4000" in r.json()["message"]


def test_le_detail_marque_non_comptee_une_justification_qui_ne_compte_pas_encore(special):
    """Une demande encore préparée, qui n'est pas la demande en cours, ne justifie rien : elle reste
    listée, marquée « non comptée », pour que l'écart s'explique."""
    _, _, profils, _, compte, demande = special
    preparee = _demande_a_part(special, soumise=False)
    r = appeler(
        profils["amina"],
        "post",
        _chemin(compte, "justifications-banque/"),
        {"demande": str(preparee.id), "montant": "100", "date_soumission": "2026-03-20"},
    )
    assert r.status_code == 201, r.content
    situation = appeler(
        profils["amina"],
        "get",
        _chemin(
            compte, f"situation-compte-special/?date={FIN.isoformat()}&demande={demande.numero}"
        ),
    ).json()
    (ligne,) = situation["justifications"]
    assert (ligne["demande"], ligne["en_cours"], ligne["comptee"]) == (
        preparee.numero,
        False,
        False,
    )
    assert Decimal(situation["justifie_precedemment"]) == 0
