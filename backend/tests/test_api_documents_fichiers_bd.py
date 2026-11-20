# ruff: noqa: F811, E501
"""Documents de référence : dépôt multipart jusqu'à 50 Mio et téléchargement vérifié. L11-D6.

Avant : le dépôt passait par du base64 dans un corps JSON de 10 Mo au plus (environ 7 Mo de fichier),
et il n'existait aucun moyen de relire un document par l'API. Le dépôt multipart lève la limite des
7 Mo ; le téléchargement vérifie l'empreinte avant de servir, ne sert jamais un fichier altéré, et le
sert toujours en pièce jointe (un document déposé reste une donnée non fiable).
"""

import base64
import hashlib

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection

from core.models import AuditLog
from niveau3_config import stockage
from niveau3_config.models import DocumentReference
from tests.test_api_documents_bd import TEXTE, _chemin, _deposer, docs  # noqa: F401
from tests.test_api_marches_bd import _connecte, appeler  # noqa: F401
from tests.test_cycle_ecriture_bd import _poser, decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
PDF = b"%PDF-1.4\n% faux pdf de test\n"


def _multipart(profils, projet, octets=TEXTE, *, utilisateur="dora", fin="", **champs):
    """Un envoi multipart (le client de test encode le fichier et les champs)."""
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")
    donnees = {
        "kind": "financing_agreement",
        "title": "Accord de don IDA",
        "version": "1",
        "fichier": SimpleUploadedFile("peu-importe.bin", octets),
    } | champs
    return _connecte(profils[utilisateur]).post(_chemin_complet(projet, fin), donnees)


def _chemin_complet(projet, fin=""):
    return f"/api/v1{_chemin(projet, fin)}"


# --- dépôt multipart -----------------------------------------------------------------------------


def test_un_fichier_se_depose_en_multipart_avec_son_empreinte(docs):
    organisation, projet, profils, _ = docs
    r = _multipart(profils, projet, issued_on="2025-12-01")
    assert r.status_code == 201, r.content
    doc = r.json()
    assert doc["sha256"] == hashlib.sha256(TEXTE).hexdigest() and doc["issued_on"] == "2025-12-01"
    assert "file_ref" not in doc
    _poser(organisation)
    assert stockage.lire(DocumentReference.objects.get(pk=doc["id"]).file_ref) == TEXTE


def test_le_meme_fichier_par_json_ou_par_multipart_est_le_meme_document(docs):
    _, projet, profils, _ = docs
    json_doc = _deposer(profils, projet)
    r = _multipart(profils, projet)
    assert (
        r.status_code == 200 and r.json()["id"] == json_doc["id"]
    )  # idempotent d'un mode à l'autre


def test_un_gros_fichier_passe_en_multipart_la_ou_le_json_est_refuse(docs):
    """12 Mo : trop pour le corps JSON (base64 ≈ 16 Mo > 10 Mo), accepté en multipart."""
    _, projet, profils, _ = docs
    gros = b"x" * (12 * 1024 * 1024)
    refuse = appeler(
        profils["dora"],
        "post",
        _chemin(projet),
        {
            "kind": "financing_agreement",
            "title": "Gros",
            "version": "1",
            "contenu_base64": base64.b64encode(gros).decode(),
        },
    )
    assert refuse.status_code >= 400
    r = _multipart(profils, projet, gros, title="Gros")
    assert r.status_code == 201, r.content
    assert r.json()["sha256"] == hashlib.sha256(gros).hexdigest()


def test_au_dela_de_cinquante_mio_le_depot_est_refuse_nettement(docs):
    _, projet, profils, _ = docs
    r = _multipart(profils, projet, b"x" * (50 * 1024 * 1024 + 1), title="Trop gros")
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}
    assert "50" in r.json()["message"]
    _poser(docs[0])
    assert DocumentReference.objects.count() == 0  # rien n'a été enregistré


def test_un_depot_sans_fichier_ni_base64_est_refuse(docs):
    _, projet, profils, _ = docs
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")
    r = _connecte(profils["dora"]).post(
        _chemin_complet(projet), {"kind": "financing_agreement", "title": "Sans fichier"}
    )
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}


def test_un_fichier_vide_en_multipart_est_refuse(docs):
    _, projet, profils, _ = docs
    r = _multipart(profils, projet, b"")
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}


def test_le_depot_multipart_exige_parametrer(docs):
    organisation, projet, profils, _ = docs
    assert _multipart(profils, projet, utilisateur="amina").status_code == 403
    _poser(organisation)
    assert DocumentReference.objects.count() == 0


def test_un_remplacement_se_fait_aussi_en_multipart(docs):
    organisation, projet, profils, _ = docs
    ancien = _deposer(profils, projet)
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")
    r = _connecte(profils["dora"]).post(
        _chemin_complet(projet, f"{ancien['id']}/remplacement/"),
        {"version": "2", "fichier": SimpleUploadedFile("v2.bin", TEXTE + b" (avenant)")},
    )
    assert r.status_code == 201, r.content
    assert r.json()["version"] == "2" and r.json()["id"] != ancien["id"]
    _poser(organisation)
    assert DocumentReference.objects.get(pk=ancien["id"]).superseded_by_id is not None


# --- téléchargement ------------------------------------------------------------------------------


def _telecharger(profils, projet, doc, utilisateur="amina"):
    return appeler(profils[utilisateur], "get", _chemin(projet, f"{doc['id']}/contenu/"))


def test_le_telechargement_rend_les_octets_deposes_avec_leur_empreinte(docs):
    _, projet, profils, _ = docs
    doc = _deposer(profils, projet)
    r = _telecharger(profils, projet, doc)
    assert r.status_code == 200 and r.content == TEXTE
    assert r["Digest"] == f"sha-256={hashlib.sha256(TEXTE).hexdigest()}"


def test_le_fichier_est_toujours_une_piece_jointe_sans_interpretation(docs):
    _, projet, profils, _ = docs
    r = _telecharger(profils, projet, _deposer(profils, projet))
    assert r["Content-Disposition"].startswith("attachment;")
    assert r["X-Content-Type-Options"] == "nosniff" and r["Content-Security-Policy"] == "sandbox"
    assert r["Content-Type"] == "application/octet-stream"  # un texte quelconque


def test_un_pdf_est_reconnu_a_ses_octets_pas_a_ce_qu_il_pretend_etre(docs):
    _, projet, profils, _ = docs
    pdf = _deposer(profils, projet, title="Manuel", contenu_base64=base64.b64encode(PDF).decode())
    r = _telecharger(profils, projet, pdf)
    assert r["Content-Type"] == "application/pdf" and r["Content-Disposition"].endswith('.pdf"')
    html = _deposer(
        profils,
        projet,
        title="Piege",
        contenu_base64=base64.b64encode(b"<script>x</script>").decode(),
    )
    r2 = _telecharger(profils, projet, html)
    assert r2["Content-Type"] == "application/octet-stream" and r2["Content-Disposition"].endswith(
        '.bin"'
    )


def test_le_nom_du_fichier_telecharge_ne_peut_pas_sortir_du_dossier_ni_casser_l_en_tete(docs):
    _, projet, profils, _ = docs
    doc = _deposer(
        profils, projet, title='../../etc/passwd"; filename="x\r\nSet-Cookie: a=b é', version="v 1"
    )
    r = _telecharger(profils, projet, doc)
    entete = r["Content-Disposition"]
    assert "/" not in entete.split("filename=")[1] and "\r" not in entete and "\n" not in entete
    assert entete.count('"') == 2 and "Set-Cookie" not in r.headers


def test_un_telechargement_est_journalise(docs):
    organisation, projet, profils, _ = docs
    doc = _deposer(profils, projet)
    _telecharger(profils, projet, doc)
    _poser(organisation)
    entrees = AuditLog.objects.filter(action="document_downloaded", object_id=doc["id"])
    assert entrees.count() == 1 and entrees.get().actor_id == profils["amina"].id


def test_un_fichier_altere_n_est_jamais_servi_et_le_constat_reste_dans_le_journal(docs):
    organisation, projet, profils, _ = docs
    doc = _deposer(profils, projet)
    _poser(organisation)
    stockage._chemin(DocumentReference.objects.get(pk=doc["id"]).file_ref).write_bytes(b"modifie")
    r = _telecharger(profils, projet, doc)
    assert r.status_code == 409 and r.json()["code"] == "DOCUMENT_ALTERE"
    assert b"modifie" not in r.content and "empreinte" in r.json()["message"]
    _poser(organisation)
    assert (
        AuditLog.objects.filter(action="document_integrity_failed", object_id=doc["id"]).count()
        == 1
    )
    assert not AuditLog.objects.filter(action="document_downloaded", object_id=doc["id"]).exists()


def test_un_fichier_disparu_n_est_pas_servi(docs):
    organisation, projet, profils, _ = docs
    doc = _deposer(profils, projet)
    _poser(organisation)
    stockage._chemin(DocumentReference.objects.get(pk=doc["id"]).file_ref).unlink()
    r = _telecharger(profils, projet, doc)
    assert r.status_code == 409 and "introuvable" in r.json()["message"]


def test_le_telechargement_exige_consulter_et_le_projet_du_document(docs):
    from django.contrib.auth import get_user_model

    organisation, projet, profils, _ = docs
    doc = _deposer(profils, projet)
    inconnu = get_user_model().objects.create_user("ivan", password="x", org_id=organisation.id)
    _poser(organisation)
    assert appeler(inconnu, "get", _chemin(projet, f"{doc['id']}/contenu/")).status_code == 403
    sans_document = "00000000-0000-0000-0000-000000000000"
    assert (
        appeler(profils["amina"], "get", _chemin(projet, f"{sans_document}/contenu/")).status_code
        == 404
    )
