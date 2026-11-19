# ruff: noqa: F811, E501
"""L'API HTTP des documents de référence : dépôt (base64), remplacement, intégrité. Phase B de L11.

Avant : un document ne s'enregistrait que par appel de service ; un avenant ou une exigence ne
pouvait donc citer un document que si un développeur l'avait déposé.
"""

import base64
import hashlib
import uuid

import pytest
from django.contrib.auth import get_user_model

from core.models import AuditLog
from niveau3_config import stockage
from niveau3_config.models import DocumentReference
from tests.test_api_marches_bd import RACINE, appeler  # noqa: F401
from tests.test_cycle_ecriture_bd import _creer_projet, _poser, decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
TEXTE = b"Accord de financement. Les depenses sont eligibles apres le 1er janvier."


@pytest.fixture
def docs(cadre, settings, tmp_path):
    settings.STOCKAGE_DOCUMENTS_ROOT = tmp_path
    return cadre


def _chemin(projet, fin=""):
    return f"/projets/{projet.id}/documents/{fin}"


def _b64(octets=TEXTE):
    return base64.b64encode(octets).decode()


def _corps(**champs):
    return {
        "kind": "financing_agreement",
        "title": "Accord de don IDA",
        "version": "1",
        "contenu_base64": _b64(),
    } | champs


def _deposer(profils, projet, **champs):
    r = appeler(profils["dora"], "post", _chemin(projet), _corps(**champs))
    assert r.status_code in (200, 201), r.content
    return r.json()


def test_un_document_se_depose_avec_son_empreinte_et_son_fichier_est_conserve(docs):
    organisation, projet, profils, _ = docs
    r = appeler(profils["dora"], "post", _chemin(projet), _corps(issued_on="2025-12-01"))
    assert r.status_code == 201, r.content
    doc = r.json()
    assert doc["sha256"] == hashlib.sha256(TEXTE).hexdigest()
    assert (doc["kind"], doc["title"], doc["version"], doc["issued_on"]) == (
        "financing_agreement", "Accord de don IDA", "1", "2025-12-01",
    )  # fmt: skip
    assert "file_ref" not in doc  # la référence de stockage est interne : on ne l'expose pas
    _poser(organisation)
    stocke = DocumentReference.objects.get(pk=doc["id"])
    assert stockage.lire(stocke.file_ref) == TEXTE


def test_deposer_deux_fois_le_meme_fichier_rend_le_meme_document(docs):
    _, projet, profils, _ = docs
    premier = appeler(profils["dora"], "post", _chemin(projet), _corps())
    second = appeler(profils["dora"], "post", _chemin(projet), _corps())
    assert (premier.status_code, second.status_code) == (201, 200)  # créé, puis retrouvé
    assert premier.json()["id"] == second.json()["id"]
    assert len(appeler(profils["dora"], "get", _chemin(projet)).json()) == 1


def test_un_fichier_different_sous_le_meme_titre_et_la_meme_version_est_refuse(docs):
    _, projet, profils, _ = docs
    _deposer(profils, projet)
    r = appeler(profils["dora"], "post", _chemin(projet), _corps(contenu_base64=_b64(TEXTE + b"!")))
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}
    assert "empreinte" in r.json()["message"]


@pytest.mark.parametrize(
    "champs",
    [
        {"kind": "magique"},
        {"title": "   "},
        {"contenu_base64": "ceci n'est pas du base64 !"},
        {"contenu_base64": ""},
        {"kind": ""},
        {"issued_on": "pas-une-date"},
    ],
)
def test_un_depot_invalide_est_refuse_au_format_stable(docs, champs):
    _, projet, profils, _ = docs
    r = appeler(profils["dora"], "post", _chemin(projet), _corps(**champs))
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}, r.content


def test_un_fichier_vide_est_refuse(docs):
    _, projet, profils, _ = docs
    r = appeler(profils["dora"], "post", _chemin(projet), _corps(contenu_base64=_b64(b"")))
    assert r.status_code == 422


def test_la_liste_donne_les_metadonnees_et_jamais_la_reference_de_stockage(docs):
    _, projet, profils, _ = docs
    _deposer(profils, projet, title="B")
    _deposer(profils, projet, title="A", contenu_base64=_b64(b"autre texte"))
    liste = appeler(profils["dora"], "get", _chemin(projet)).json()
    assert [d["title"] for d in liste] == ["A", "B"]
    assert all("file_ref" not in d and len(d["sha256"]) == 64 for d in liste)


def test_remplacer_un_document_chaine_l_ancien_sans_le_toucher(docs):
    organisation, projet, profils, _ = docs
    ancien = _deposer(profils, projet)
    r = appeler(
        profils["dora"], "post", _chemin(projet, f"{ancien['id']}/remplacement/"),
        {"version": "2", "contenu_base64": _b64(TEXTE + b" Avenant."), "issued_on": "2026-06-01"},
    )  # fmt: skip
    assert r.status_code == 201, r.content
    nouveau = r.json()
    assert (
        nouveau["id"] != ancien["id"]
        and nouveau["version"] == "2"
        and nouveau["title"] == ancien["title"]
    )
    liste = {d["id"]: d for d in appeler(profils["dora"], "get", _chemin(projet)).json()}
    assert liste[ancien["id"]]["remplace_par"] == nouveau["id"]
    assert liste[ancien["id"]]["sha256"] == ancien["sha256"]  # l'ancien ne change pas
    assert liste[nouveau["id"]]["remplace_par"] is None


@pytest.mark.parametrize(
    "champs",
    [{"version": ""}, {"contenu_base64": _b64()}, {"contenu_base64": "!!"}],
)
def test_un_remplacement_invalide_est_refuse(docs, champs):
    _, projet, profils, _ = docs
    ancien = _deposer(profils, projet)
    corps = {"version": "2", "contenu_base64": _b64(TEXTE + b"+")} | champs
    r = appeler(profils["dora"], "post", _chemin(projet, f"{ancien['id']}/remplacement/"), corps)
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}, r.content


def test_un_document_deja_remplace_ne_se_remplace_pas_deux_fois(docs):
    _, projet, profils, _ = docs
    ancien = _deposer(profils, projet)
    url = _chemin(projet, f"{ancien['id']}/remplacement/")
    assert (
        appeler(
            profils["dora"], "post", url, {"version": "2", "contenu_base64": _b64(b"v2")}
        ).status_code
        == 201
    )
    r = appeler(profils["dora"], "post", url, {"version": "3", "contenu_base64": _b64(b"v3")})
    assert r.status_code == 422


def test_l_integrite_d_un_fichier_intact_est_confirmee(docs):
    _, projet, profils, _ = docs
    doc = _deposer(profils, projet)
    r = appeler(profils["dora"], "get", _chemin(projet, f"{doc['id']}/integrite/"))
    assert r.status_code == 200 and r.json() == {"integre": True, "probleme": None}


def test_un_fichier_altere_est_signale_et_le_constat_reste_dans_le_journal(docs):
    """La constatation est journalisée ; elle ne doit pas être annulée avec la réponse."""
    organisation, projet, profils, _ = docs
    doc = _deposer(profils, projet)
    _poser(organisation)
    stocke = DocumentReference.objects.get(pk=doc["id"])
    stockage._chemin(stocke.file_ref).write_bytes(b"fichier modifie en douce")
    r = appeler(profils["dora"], "get", _chemin(projet, f"{doc['id']}/integrite/"))
    assert r.status_code == 200 and r.json()["integre"] is False
    assert "empreinte" in r.json()["probleme"]
    _poser(organisation)
    assert (
        AuditLog.objects.filter(action="document_integrity_failed", object_id=doc["id"]).count()
        == 1
    )


def test_un_fichier_disparu_est_signale(docs):
    organisation, projet, profils, _ = docs
    doc = _deposer(profils, projet)
    _poser(organisation)
    stockage._chemin(DocumentReference.objects.get(pk=doc["id"]).file_ref).unlink()
    r = appeler(profils["dora"], "get", _chemin(projet, f"{doc['id']}/integrite/"))
    assert (
        r.status_code == 200
        and r.json()["integre"] is False
        and "introuvable" in r.json()["probleme"]
    )


def test_deposer_exige_parametrer_lire_exige_consulter(docs):
    organisation, projet, profils, _ = docs
    assert appeler(profils["amina"], "post", _chemin(projet), _corps()).status_code == 403
    doc = _deposer(profils, projet)
    assert appeler(profils["amina"], "get", _chemin(projet)).status_code == 200
    inconnu = Utilisateur.objects.create_user("ivan", password="x", org_id=organisation.id)
    assert appeler(inconnu, "get", _chemin(projet)).status_code == 403
    assert appeler(inconnu, "get", _chemin(projet, f"{doc['id']}/integrite/")).status_code == 403
    r = appeler(
        profils["amina"],
        "post",
        _chemin(projet, f"{doc['id']}/remplacement/"),
        {"version": "2", "contenu_base64": _b64(b"x")},
    )
    assert r.status_code == 403


def test_un_document_s_adresse_par_son_projet_pas_par_un_autre(docs):
    from niveau1_socle.habilitations.models import Habilitation, Role

    organisation, projet, profils, _ = docs
    doc = _deposer(profils, projet)
    autre = _creer_projet(organisation, "AUTRE")
    role = Role.objects.create(
        org_id=organisation.id, code="D2", label={"fr": "d"}, operations=["consulter", "parametrer"]
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=profils["dora"].id, project_id=autre.id, role=role
    )
    assert (
        appeler(profils["dora"], "get", _chemin(autre, f"{doc['id']}/integrite/")).status_code
        == 404
    )
    r = appeler(
        profils["dora"],
        "post",
        _chemin(autre, f"{doc['id']}/remplacement/"),
        {"version": "2", "contenu_base64": _b64(b"x")},
    )
    assert r.status_code == 404
    assert (
        appeler(profils["dora"], "get", _chemin(projet, f"{uuid.uuid4()}/integrite/")).status_code
        == 404
    )


def test_de_bout_en_bout_un_document_depose_par_http_sert_a_un_avenant(docs):
    """Le document déposé par l'administrateur devient la pièce d'un avenant, sans développeur."""
    _, projet, profils, _ = docs
    dora = profils["dora"]
    doc = _deposer(profils, projet, title="Avenant 1 à l'accord")
    accord = appeler(
        dora, "post", f"/projets/{projet.id}/accords/",
        {"bailleur": "IDA", "numero": "IDA-DOC", "nature": "don", "devise": "USD", "montant_initial": "1000"},
    ).json()  # fmt: skip
    appeler(
        dora, "post", f"/projets/{projet.id}/accords/{accord['id']}/statut/", {"statut": "actif"}
    )
    r = appeler(
        dora, "post", f"/projets/{projet.id}/accords/{accord['id']}/avenants/",
        {"reference": "AV-1", "date_avenant": "2026-06-01", "document_id": doc["id"], "montant_revise": "1500"},
    )  # fmt: skip
    assert r.status_code == 201, r.content
    assert r.json()["variation"] == "500.0000"


def test_le_remplacement_liste_les_exigences_qui_citaient_l_ancien_texte(docs):
    """Une exigence cite un passage de l'ancien texte : après remplacement, il faut le revérifier."""
    import datetime

    from niveau3_config.services.exigences import proposer_exigence

    organisation, projet, profils, _ = docs
    phrase = b"Le rapport financier intermediaire est remis dans les 45 jours suivant le trimestre"
    ancien = _deposer(profils, projet, title="DFIL", kind="dfil", contenu_base64=_b64(phrase))
    _poser(organisation)
    proposer_exigence(
        utilisateur=profils["dora"], project_id=projet.id, code="IFR-DELAI",
        document=DocumentReference.objects.get(pk=ancien["id"]),
        citation={"paragraph": "4.2", "quote": "remis dans les 45 jours"},
        subject="IFR", rule={}, obligation="mandatory", valid_from=datetime.date(2026, 1, 1),
    )  # fmt: skip
    r = appeler(
        profils["dora"], "post", _chemin(projet, f"{ancien['id']}/remplacement/"),
        {"version": "2", "contenu_base64": _b64(phrase + b" (revise)")},
    )  # fmt: skip
    assert r.status_code == 201, r.content
    assert r.json()["exigences_a_reverifier"] == ["IFR-DELAI"]
