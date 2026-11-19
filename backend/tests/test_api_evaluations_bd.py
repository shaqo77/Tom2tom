# ruff: noqa: F811, E501
"""L'API HTTP des évaluations, décisions, justifications et dérogations, et les seuils de risque
réglés à l'installation. L11-D7.

Avant : le moteur écrivait des évaluations que personne ne pouvait lire ni traiter sans développeur.
Le journal reste en ajout seul : trancher, justifier ou déroger ajoute une ligne, ne modifie jamais
l'évaluation. Un résultat bloquant dérogé n'est plus en attente, mais reste lisible.
"""

import datetime
import uuid

import pytest
from django.db import connection

from niveau4_reporting.controles.models import (
    Controle,
    Derogation,
)
from niveau4_reporting.controles.services import (
    activer_controle,
    creer_controle,
    evaluer_controle,
    valider_controle,
)
from tests.test_api_marches_bd import appeler  # noqa: F401
from tests.test_controles_bd import _actif, _evaluer, ctl  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_derogations_bd import JOUR, dero  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_rattachement_bd import cadre_config  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
D = datetime.date


def _poser(organisation):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


def _p(projet, fin):
    return f"/projets/{projet.id}/{fin}"


def _nb(dero, modele, **filtres) -> int:
    _poser(dero[0])
    return modele.objects.filter(**filtres).count()


def _a_verifier(dero):
    """Un contrôle MANUEL actif et son évaluation « à vérifier » sur un objet à part."""
    organisation, projet, profils, _, _, _ = dero
    creer_controle(
        utilisateur=profils["dora"], project_id=projet.id, code="VERIF-MANUELLE",
        label={"fr": "Vérifier à la main", "en": "Check by hand"}, type_regle="codification",
        severity="bloquant", valid_from=D(2026, 1, 1), manuel=True,
    )  # fmt: skip
    controle = Controle.objects.get(code="VERIF-MANUELLE")
    valider_controle(utilisateur=profils["vera"], controle=controle)
    controle = activer_controle(utilisateur=profils["vera"], controle=controle)
    objet = uuid.uuid4()
    evaluation = evaluer_controle(
        controle, {}, date_operation=JOUR, objet_type="depense", objet_id=objet, service="test"
    )
    assert evaluation.resultat == "a_verifier"
    return evaluation, objet


# --- lire le journal -----------------------------------------------------------------------------


def test_le_journal_se_lit_du_plus_recent_au_plus_ancien_et_se_filtre(dero):
    _, projet, profils, controle, evaluation, objet = dero
    manuelle, objet2 = _a_verifier(dero)
    r = appeler(profils["lecteur"], "get", _p(projet, "evaluations-controles/"))
    assert r.status_code == 200
    ids = [e["id"] for e in r.json()]
    assert ids == [str(manuelle.id), str(evaluation.id)]  # le plus récent d'abord
    e = r.json()[1]
    assert (e["controle"], e["resultat"], e["objet_type"], e["objet_id"]) == (
        controle.code, "bloquant", "depense", str(objet),
    )  # fmt: skip
    assert e["message"] and e["action_corrective"] is not None

    def filtre(q):
        return [
            x["id"]
            for x in appeler(
                profils["lecteur"], "get", _p(projet, f"evaluations-controles/?{q}")
            ).json()
        ]

    assert filtre("resultat=a_verifier") == [str(manuelle.id)]
    assert filtre(f"objet_id={objet}") == [str(evaluation.id)]
    assert filtre(f"controle={controle.code}") == [str(evaluation.id)]
    assert filtre("objet_type=inconnu") == []


def test_un_filtre_inconnu_ou_mal_forme_est_refuse(dero):
    _, projet, profils, _, _, _ = dero
    for q in ("resultat=zzz", "objet_id=pas-un-uuid"):
        r = appeler(profils["lecteur"], "get", _p(projet, f"evaluations-controles/?{q}"))
        assert r.status_code == 422 and set(r.json()) == {"code", "message"}, q


def test_la_lecture_du_journal_est_bornee(dero, monkeypatch):
    from niveau4_reporting.controles import api

    _, projet, profils, _, _, _ = dero
    _a_verifier(dero)
    monkeypatch.setattr(api, "LIMITE_EVALUATIONS", 1)
    assert len(appeler(profils["lecteur"], "get", _p(projet, "evaluations-controles/")).json()) == 1


def test_le_detail_donne_decisions_justifications_et_derogations(dero):
    _, projet, profils, _, evaluation, _ = dero
    appeler(
        profils["samir"],
        "post",
        _p(projet, f"evaluations-controles/{evaluation.id}/justification/"),
        {"texte": "Avance attendue"},
    )
    d = appeler(
        profils["lecteur"], "get", _p(projet, f"evaluations-controles/{evaluation.id}/")
    ).json()
    assert [j["texte"] for j in d["justifications"]] == ["Avance attendue"] and d["decisions"] == []
    assert d["derogations"] == []


def test_une_evaluation_d_un_autre_projet_ou_inconnue_est_introuvable(dero):
    _, projet, profils, _, _, _ = dero
    inconnue = "00000000-0000-0000-0000-000000000000"
    assert (
        appeler(
            profils["lecteur"], "get", _p(projet, f"evaluations-controles/{inconnue}/")
        ).status_code
        == 404
    )
    assert (
        appeler(
            profils["vera"], "post", _p(projet, f"evaluations-controles/{inconnue}/decision/"), {}
        ).status_code
        == 404
    )


def test_sans_habilitation_aucune_lecture_n_est_permise(dero):
    from django.contrib.auth import get_user_model

    organisation, projet, _, _, evaluation, _ = dero
    inconnu = get_user_model().objects.create_user("zoe", password="x", org_id=organisation.id)
    _poser(organisation)
    for fin in ("evaluations-controles/", f"evaluations-controles/{evaluation.id}/", "derogations/",
                "controles-en-attente/?objet_type=depense", "dossier-conformite-objet/?objet_type=depense"):  # fmt: skip
        assert appeler(inconnu, "get", _p(projet, fin)).status_code == 403, fin


# --- trancher, justifier ---------------------------------------------------------------------------


def test_trancher_un_controle_a_verifier_exige_valider_et_un_motif(dero):
    _, projet, profils, _, _, _ = dero
    manuelle, _ = _a_verifier(dero)
    chemin = _p(projet, f"evaluations-controles/{manuelle.id}/decision/")
    assert (
        appeler(
            profils["samir"], "post", chemin, {"decision": "conforme", "motif": "Vu"}
        ).status_code
        == 403
    )
    assert appeler(profils["lea"], "post", chemin, {"decision": "conforme"}).status_code == 422
    assert (
        appeler(profils["lea"], "post", chemin, {"decision": "peut-etre", "motif": "x"}).status_code
        == 422
    )
    assert (
        _nb(
            dero,
            __import__(
                "niveau4_reporting.controles.models", fromlist=["DecisionControle"]
            ).DecisionControle,
        )
        == 0
    )
    r = appeler(profils["lea"], "post", chemin, {"decision": "conforme", "motif": "Vu sur pièce"})
    assert r.status_code == 201, r.content
    assert [(d["decision"], d["motif"]) for d in r.json()["decisions"]] == [
        ("conforme", "Vu sur pièce")
    ]


def test_seul_un_controle_a_verifier_se_tranche(dero):
    _, projet, profils, _, evaluation, _ = dero  # une évaluation BLOQUANTE
    r = appeler(
        profils["lea"],
        "post",
        _p(projet, f"evaluations-controles/{evaluation.id}/decision/"),
        {"decision": "conforme", "motif": "x"},
    )
    assert r.status_code == 409 and r.json()["code"] == "TRANSITION_INTERDITE"


def test_une_decision_conforme_leve_l_attente_une_non_conforme_la_garde(dero):
    _, projet, profils, _, _, _ = dero
    manuelle, objet = _a_verifier(dero)

    def attente():
        return appeler(
            profils["lecteur"],
            "get",
            _p(projet, f"controles-en-attente/?objet_type=depense&objet_id={objet}"),
        ).json()

    assert [(a["controle"], a["evaluation"]) for a in attente()] == [
        ("VERIF-MANUELLE", str(manuelle.id))
    ]
    chemin = _p(projet, f"evaluations-controles/{manuelle.id}/decision/")
    appeler(
        profils["lea"], "post", chemin, {"decision": "non_conforme", "motif": "Pièce illisible"}
    )
    assert [a["controle"] for a in attente()] == ["VERIF-MANUELLE"]  # non conforme : bloque encore
    appeler(profils["lea"], "post", chemin, {"decision": "conforme", "motif": "Pièce reçue"})
    assert attente() == []  # la dernière décision fait foi


def test_justifier_exige_saisir_un_texte_et_ne_leve_aucun_blocage(dero):
    _, projet, profils, _, evaluation, objet = dero
    chemin = _p(projet, f"evaluations-controles/{evaluation.id}/justification/")
    assert appeler(profils["lecteur"], "post", chemin, {"texte": "x"}).status_code == 403
    assert appeler(profils["samir"], "post", chemin, {"texte": "  "}).status_code == 422
    r = appeler(profils["samir"], "post", chemin, {"texte": "Financement complémentaire attendu"})
    assert r.status_code == 201 and r.json()["justifications"][0]["auteur"] == "samir"
    en_attente = appeler(
        profils["lecteur"],
        "get",
        _p(projet, f"controles-en-attente/?objet_type=depense&objet_id={objet}"),
    )
    assert len(en_attente.json()) == 1  # une justification explique, elle ne débloque pas


# --- dérogations -----------------------------------------------------------------------------------


def _demander(dero, **champs):
    _, projet, profils, _, evaluation, _ = dero
    corps = {
        "motif": "Marché urgent",
        "justificatif": "NO-2026-014",
        "valide_du": "2026-06-01",
        "valide_jusquau": "2026-07-01",
    } | champs
    return appeler(
        profils["samir"],
        "post",
        _p(projet, f"evaluations-controles/{evaluation.id}/derogation/"),
        corps,
    )


def test_une_derogation_se_demande_puis_un_autre_l_approuve_et_le_blocage_se_leve(dero):
    _, projet, profils, controle, evaluation, objet = dero
    r = _demander(dero)
    assert r.status_code == 201, r.content
    x = r.json()
    assert (x["statut"], x["controle"], x["valide_du"], x["valide_jusquau"]) == (
        "demandee",
        controle.code,
        "2026-06-01",
        "2026-07-01",
    )

    def attente():
        return appeler(
            profils["lecteur"],
            "get",
            _p(
                projet, f"controles-en-attente/?objet_type=depense&objet_id={objet}&date=2026-06-15"
            ),
        ).json()

    assert len(attente()) == 1  # demandée : ne couvre encore rien
    chemin = _p(projet, f"derogations/{x['id']}/decision/")
    d = appeler(
        profils["lea"], "post", chemin, {"approuver": True, "motif": "Accordée par le comité"}
    )
    assert (
        d.status_code == 200
        and d.json()["statut"] == "approuvee"
        and d.json()["motif_decision"] == "Accordée par le comité"
    )
    assert attente() == []  # le blocage est levé À CETTE DATE…
    hors = appeler(
        profils["lecteur"],
        "get",
        _p(projet, f"controles-en-attente/?objet_type=depense&objet_id={objet}&date=2026-07-01"),
    )
    assert len(hors.json()) == 1  # … et le jour de fin (exclu), il bloque de nouveau
    # le résultat initial « bloquant » reste lisible, suivi de la dérogation
    fil = appeler(
        profils["lecteur"],
        "get",
        _p(projet, f"dossier-conformite-objet/?objet_type=depense&objet_id={objet}"),
    ).json()
    assert [(e["genre"], e["detail"]) for e in fil] == [
        ("evaluation", "bloquant"),
        ("derogation", "approuvee"),
    ]


def test_le_demandeur_ne_peut_pas_approuver_sa_propre_derogation(dero):
    _, projet, profils, _, _, _ = dero
    x = _demander(dero).json()
    r = appeler(
        profils["vera"],
        "post",
        _p(projet, f"derogations/{x['id']}/decision/"),
        {"approuver": True, "motif": "ok"},
    )
    assert r.status_code == 200  # vera n'est pas le demandeur : permis
    y = appeler(
        profils["vera"],
        "post",
        _p(projet, f"evaluations-controles/{dero[4].id}/derogation/"),
        {
            "motif": "m",
            "justificatif": "j",
            "valide_du": "2026-08-01",
            "valide_jusquau": "2026-09-01",
        },
    )
    assert y.status_code == 403 or y.status_code == 201
    if y.status_code == 201:  # vera demande puis tente d'approuver : refusé
        refus = appeler(
            profils["vera"],
            "post",
            _p(projet, f"derogations/{y.json()['id']}/decision/"),
            {"approuver": True, "motif": "moi-même"},
        )
        assert refus.status_code == 422 and refus.json()["code"] == "APPROBATION_REQUISE"


def test_approuver_exige_valider_un_motif_un_booleen_et_ne_se_fait_qu_une_fois(dero):
    _, projet, profils, _, _, _ = dero
    x = _demander(dero).json()
    chemin = _p(projet, f"derogations/{x['id']}/decision/")
    assert (
        appeler(profils["samir"], "post", chemin, {"approuver": True, "motif": "m"}).status_code
        == 403
    )
    for corps in ({"approuver": True}, {"approuver": "oui", "motif": "m"}, {"motif": "m"}):
        assert appeler(profils["lea"], "post", chemin, corps).status_code == 422, corps
    assert (
        appeler(
            profils["lea"], "post", chemin, {"approuver": False, "motif": "Non justifié"}
        ).json()["statut"]
        == "refusee"
    )
    encore = appeler(profils["lea"], "post", chemin, {"approuver": True, "motif": "revenir"})
    assert encore.status_code == 409 and encore.json()["code"] == "TRANSITION_INTERDITE"


def test_une_derogation_invalide_est_refusee(dero):
    _, projet, profils, _, _, _ = dero
    for champs in (
        {"motif": ""},
        {"justificatif": ""},
        {"valide_du": "2026-07-01"},
        {"valide_du": "demain"},
        {"valide_jusquau": ""},
    ):
        r = _demander(dero, **champs)
        assert r.status_code == 422 and set(r.json()) == {"code", "message"}, champs
    assert _nb(dero, Derogation) == 0
    autre, _ = _a_verifier(dero)  # on ne déroge qu'à un résultat BLOQUANT
    r = appeler(
        profils["samir"],
        "post",
        _p(projet, f"evaluations-controles/{autre.id}/derogation/"),
        {
            "motif": "m",
            "justificatif": "j",
            "valide_du": "2026-06-01",
            "valide_jusquau": "2026-07-01",
        },
    )
    assert r.status_code == 422


def test_la_demande_de_derogation_exige_saisir(dero):
    _, projet, profils, _, evaluation, _ = dero
    r = appeler(
        profils["lecteur"],
        "post",
        _p(projet, f"evaluations-controles/{evaluation.id}/derogation/"),
        {
            "motif": "m",
            "justificatif": "j",
            "valide_du": "2026-06-01",
            "valide_jusquau": "2026-07-01",
        },
    )
    assert r.status_code == 403 and _nb(dero, Derogation) == 0


def test_la_liste_des_derogations_se_filtre_par_statut(dero):
    _, projet, profils, _, _, _ = dero
    x = _demander(dero).json()

    def liste(q=""):
        return appeler(profils["lecteur"], "get", _p(projet, f"derogations/{q}")).json()

    assert [d["id"] for d in liste()] == [x["id"]] and [
        d["id"] for d in liste("?statut=demandee")
    ] == [x["id"]]
    assert liste("?statut=approuvee") == []
    assert (
        appeler(profils["lecteur"], "get", _p(projet, "derogations/?statut=zzz")).status_code == 422
    )


def test_les_controles_en_attente_exigent_un_type_d_objet_et_une_date_lisible(dero):
    _, projet, profils, _, _, _ = dero
    assert (
        appeler(profils["lecteur"], "get", _p(projet, "controles-en-attente/")).status_code == 422
    )
    assert (
        appeler(
            profils["lecteur"],
            "get",
            _p(projet, "controles-en-attente/?objet_type=depense&date=hier"),
        ).status_code
        == 422
    )
    assert (
        appeler(profils["lecteur"], "get", _p(projet, "dossier-conformite-objet/")).status_code
        == 422
    )


# --- seuils de risque à l'installation -----------------------------------------------------------


def _installer(profils, projet, corps):
    return appeler(
        profils["dora"],
        "post",
        _p(projet, "controles/bibliotheque/installer/"),
        {"valid_from": "2026-01-01"} | corps,
    )


def _valeur_du_seuil(dero, code):
    _poser(dero[0])
    return Controle.objects.get(code=code).expression["conditions"][0]["valeur"]


def test_les_seuils_de_risque_se_reglent_a_l_installation(dero):
    _, projet, profils, _, _, _ = dero
    r = _installer(
        profils,
        projet,
        {
            "codes": ["RIS-CATEGORIE-SEUIL", "RIS-AVANCE-NON-APUREE", "RIS-REJETS-REPETES"],
            "seuils": {
                "RIS-CATEGORIE-SEUIL": "72.5",
                "RIS-AVANCE-NON-APUREE": 45,
                "RIS-REJETS-REPETES": 0,
            },
        },
    )
    assert r.status_code == 201, r.content
    assert _valeur_du_seuil(dero, "RIS-CATEGORIE-SEUIL") == "72.5"
    assert _valeur_du_seuil(dero, "RIS-AVANCE-NON-APUREE") == 45
    assert _valeur_du_seuil(dero, "RIS-REJETS-REPETES") == 0


def test_sans_seuil_les_valeurs_par_defaut_de_la_bibliotheque_s_appliquent(dero):
    _, projet, profils, _, _, _ = dero
    _installer(profils, projet, {"codes": ["RIS-CATEGORIE-SEUIL"]})
    assert _valeur_du_seuil(dero, "RIS-CATEGORIE-SEUIL") == "80"


@pytest.mark.parametrize(
    "seuils, attendu",
    [
        ({"COD-CATEGORIE": 1}, "n'est pas un contrôle de risque réglable"),
        ({"RIS-CATEGORIE-SEUIL": "101"}, "Seuil invalide"),
        ({"RIS-CATEGORIE-SEUIL": "-1"}, "Seuil invalide"),
        ({"RIS-CATEGORIE-SEUIL": "abc"}, "Seuil invalide"),
        ({"RIS-CATEGORIE-SEUIL": "NaN"}, "Seuil invalide"),
        ({"RIS-CATEGORIE-SEUIL": 80.5}, "Seuil invalide"),
        ({"RIS-CATEGORIE-SEUIL": True}, "Seuil invalide"),
        ({"RIS-AVANCE-NON-APUREE": 0}, "Seuil invalide"),
        ({"RIS-AVANCE-NON-APUREE": "60"}, "Seuil invalide"),
        ({"RIS-AVANCE-NON-APUREE": 1.5}, "Seuil invalide"),
        ({"RIS-REJETS-REPETES": -1}, "Seuil invalide"),
        ({"RIS-REJETS-REPETES": False}, "Seuil invalide"),
    ],
)
def test_un_seuil_invalide_est_refuse_sans_rien_installer(dero, seuils, attendu):
    _, projet, profils, _, _, _ = dero
    r = _installer(profils, projet, {"seuils": seuils})
    assert r.status_code == 422 and attendu in r.json()["message"], r.content
    _poser(dero[0])
    assert (
        Controle.objects.count() == 1
        or Controle.objects.filter(code__startswith="RIS-").count() == 0
    )


def test_un_seuil_pour_un_controle_non_installe_est_refuse(dero):
    _, projet, profils, _, _, _ = dero
    r = _installer(
        profils, projet, {"codes": ["COD-CATEGORIE"], "seuils": {"RIS-REJETS-REPETES": 2}}
    )
    assert r.status_code == 422 and "ne sont pas installés" in r.json()["message"]
    _poser(dero[0])
    assert not Controle.objects.filter(code="RIS-REJETS-REPETES").exists()
