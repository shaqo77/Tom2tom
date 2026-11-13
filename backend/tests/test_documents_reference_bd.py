"""Documents de référence : empreinte, remplacement, intégrité. Voir L5-T01.

Contrôle : téléverser deux fois le même fichier produit la même empreinte ; un fichier modifié d'un
octet en produit une différente et le système le signale.
"""

import datetime
import hashlib

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from niveau3_config import stockage
from niveau3_config.models import DocumentReference, Exigence
from niveau3_config.services.documents import (
    DocumentInvalide,
    DocumentModifie,
    IntegriteDocument,
    enregistrer_document,
    exigences_a_reverifier,
    remplacer_document,
    verifier_integrite,
    verifier_integrite_du_projet,
)
from tests.outils import connexion_proprietaire
from tests.test_cycle_ecriture_bd import _creer_projet, _poser, decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
TEXTE = "Article 4.2 — Le rapport financier intermédiaire est remis dans les 45 jours.".encode()


@pytest.fixture
def depot(settings, tmp_path):
    settings.STOCKAGE_DOCUMENTS_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def dossier(cadre, depot):  # noqa: F811
    organisation, projet, profils, _ = cadre
    return organisation, projet, profils


def _enregistrer(profils, projet, contenu=TEXTE, **champs):
    donnees = {
        "utilisateur": profils["dora"],
        "project_id": projet.id,
        "kind": "dfil",
        "title": "DFIL",
        "version": "1",
        "contenu": contenu,
    } | champs
    return enregistrer_document(**donnees)


# --- le contrôle de la tâche ----------------------------------------------------------------


def test_le_meme_fichier_deux_fois_donne_la_meme_empreinte_et_un_seul_document(dossier):
    organisation, projet, profils = dossier
    d1 = _enregistrer(profils, projet)
    d2 = _enregistrer(profils, projet)
    assert d1.pk == d2.pk
    assert bytes(d1.sha256) == hashlib.sha256(TEXTE).digest() == bytes(d2.sha256)
    assert DocumentReference.objects.count() == 1
    assert len(list(stockage.racine().rglob("*"))) == 3  # org / préfixe / fichier : un seul objet
    assert stockage.lire(d1.file_ref) == TEXTE


def test_un_fichier_modifie_d_un_octet_a_une_autre_empreinte_et_le_systeme_le_signale(dossier):
    organisation, projet, profils = dossier
    original = _enregistrer(profils, projet)
    modifie = TEXTE[:-1] + b"!"  # un seul octet de différence
    assert stockage.empreinte(modifie) != bytes(original.sha256)
    with pytest.raises(DocumentModifie, match="un document modifié est une nouvelle version") as e:
        _enregistrer(profils, projet, contenu=modifie)  # même titre, même version
    assert bytes(original.sha256).hex()[:16] in str(e.value)
    assert stockage.empreinte(modifie).hex()[:16] in str(e.value)
    assert DocumentReference.objects.count() == 1
    # Sous une nouvelle version, le fichier modifié est accepté, avec sa propre empreinte.
    v2 = _enregistrer(profils, projet, contenu=modifie, version="2")
    assert bytes(v2.sha256) != bytes(original.sha256)
    assert stockage.lire(original.file_ref) == TEXTE  # l'ancien objet est intact


def test_deux_organisations_ne_partagent_pas_les_objets_stockes(dossier):
    organisation, projet, profils = dossier
    doc = _enregistrer(profils, projet)
    assert doc.file_ref.startswith(f"fs://{organisation.id}/")
    autre = _creer_organisation("ORG-B")
    assert stockage.reference(autre.id, stockage.empreinte(TEXTE)) != doc.file_ref


# --- remplacer ------------------------------------------------------------------------------


def _exigence(organisation, projet, document, code="REQ-1"):
    return Exigence.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        code=code,
        document=document,
        citation={"paragraph": "4.2", "quote": "dans les 45 jours"},
        subject="RFI",
        rule={},
        obligation="mandatory",
        valid_from=datetime.date(2026, 1, 1),
        version=1,
        source="manual",
    )


def test_remplacer_un_document_chaine_l_ancien_sans_le_toucher(dossier):
    organisation, projet, profils = dossier
    ancien = _enregistrer(profils, projet)
    exigence = _exigence(organisation, projet, ancien)
    assert list(exigences_a_reverifier(ancien)) == []  # pas remplacé : rien à revérifier

    nouveau = remplacer_document(
        utilisateur=profils["dora"], ancien=ancien, contenu=TEXTE + b" Avenant.", version="2"
    )
    ancien.refresh_from_db()
    assert ancien.superseded_by_id == nouveau.pk and nouveau.superseded_by_id is None
    assert bytes(ancien.sha256) == hashlib.sha256(TEXTE).digest()  # intact
    assert stockage.lire(ancien.file_ref) == TEXTE
    assert list(exigences_a_reverifier(ancien)) == [exigence]  # elle cite toujours l'ancien texte
    exigence.refresh_from_db()
    assert exigence.document_id == ancien.pk  # la citation n'a pas bougé en douce
    with pytest.raises(DocumentInvalide, match="déjà remplacé"):
        remplacer_document(utilisateur=profils["dora"], ancien=ancien, contenu=b"x", version="3")
    assert verifier_chaine(organisation.id) is None


def test_remplacer_exige_un_contenu_different_et_une_version(dossier):
    organisation, projet, profils = dossier
    ancien = _enregistrer(profils, projet)
    with pytest.raises(DocumentInvalide, match="numérotée"):
        remplacer_document(
            utilisateur=profils["dora"], ancien=ancien, contenu=b"autre", version=" "
        )
    with pytest.raises(DocumentInvalide, match="identique"):
        remplacer_document(utilisateur=profils["dora"], ancien=ancien, contenu=TEXTE, version="2")


# --- intégrité ------------------------------------------------------------------------------


def test_verifier_l_integrite_detecte_un_fichier_altere_ou_disparu(dossier):
    organisation, projet, profils = dossier
    doc = _enregistrer(profils, projet)
    assert verifier_integrite(profils["lecteur"] if "lecteur" in profils else profils["dora"], doc)
    fichier = next(p for p in stockage.racine().rglob("*") if p.is_file())
    fichier.write_bytes(TEXTE + b"?")  # altération du fichier stocké, hors application
    with pytest.raises(IntegriteDocument, match="ne correspond plus à son empreinte"):
        verifier_integrite(profils["dora"], doc)
    fichier.unlink()
    with pytest.raises(IntegriteDocument, match="introuvable"):
        verifier_integrite(profils["dora"], doc)
    echecs = verifier_integrite_du_projet(profils["dora"], projet.id)
    assert [d.pk for d, _ in echecs] == [doc.pk]
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM core_auditlog WHERE action = 'document_integrity_failed'")
        assert cur.fetchone()[0] == 3  # chaque constatation est tracée


# --- règles et droits -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "champs, message",
    [({"contenu": b""}, "vide"), ({"title": " "}, "titre"), ({"kind": "memo"}, "type de document")],
)
def test_un_document_invalide_est_refuse(dossier, champs, message):
    organisation, projet, profils = dossier
    with pytest.raises(DocumentInvalide, match=message):
        _enregistrer(profils, projet, **champs)
    assert DocumentReference.objects.count() == 0


def test_enregistrer_exige_l_habilitation_parametrer(dossier):
    organisation, projet, profils = dossier
    with pytest.raises(PermissionDenied):
        _enregistrer(profils, projet, utilisateur=profils["amina"])
    doc = _enregistrer(profils, projet)
    with pytest.raises(PermissionDenied):
        remplacer_document(utilisateur=profils["amina"], ancien=doc, contenu=b"x", version="2")
    inconnu = Utilisateur.objects.create_user("eve", password="x", org_id=organisation.id)
    with pytest.raises(PermissionDenied):
        verifier_integrite(inconnu, doc)


def test_un_chemin_de_stockage_falsifie_est_refuse():
    for ref in ("fs://../../etc/passwd", "fs://a/b/../../x", "s3://bucket/x", "fs://a/zz"):
        with pytest.raises(stockage.FichierIntrouvable):
            stockage.lire(ref)


# --- la base --------------------------------------------------------------------------------


def test_la_base_garde_l_empreinte_et_le_chainage(dossier):
    organisation, projet, profils = dossier
    a = _enregistrer(profils, projet)
    b = _enregistrer(profils, projet, contenu=b"autre", version="2")
    c = _enregistrer(profils, projet, contenu=b"encore", version="3")
    autre_projet = _creer_projet(organisation, "P2")
    with connexion_proprietaire() as admin:
        for requete, params, motif in [
            (
                "DELETE FROM niveau3_config_documentreference WHERE id = %s",
                [a.pk],
                "ne se supprime jamais",
            ),
            (
                "UPDATE niveau3_config_documentreference SET sha256 = %s WHERE id = %s",
                [b"\x00" * 32, a.pk],
                "ne change pas",
            ),
            (
                "UPDATE niveau3_config_documentreference SET title = 'X' WHERE id = %s",
                [a.pk],
                "ne change pas",
            ),
            (
                "UPDATE niveau3_config_documentreference SET file_ref = 'fs://x' WHERE id = %s",
                [a.pk],
                "ne change pas",
            ),
            (
                "UPDATE niveau3_config_documentreference SET superseded_by_id = id WHERE id = %s",
                [a.pk],
                "non remplacé",
            ),
        ]:
            with pytest.raises(Exception, match=motif):
                admin.execute(requete, params)
        admin.execute(
            "UPDATE niveau3_config_documentreference SET superseded_by_id = %s WHERE id = %s",
            [b.pk, a.pk],
        )
        with pytest.raises(Exception, match="déjà remplacé"):
            admin.execute(
                "UPDATE niveau3_config_documentreference SET superseded_by_id = %s WHERE id = %s",
                [c.pk, a.pk],
            )
        with pytest.raises(Exception, match="non remplacé"):  # cible déjà remplacée : pas de cycle
            admin.execute(
                "UPDATE niveau3_config_documentreference SET superseded_by_id = %s WHERE id = %s",
                [a.pk, c.pk],
            )
    autre_doc = DocumentReference.objects.create(
        org_id=organisation.id,
        project_id=autre_projet.id,
        kind="dfil",
        title="Autre projet",
        version="1",
        file_ref="fs://z",
        sha256=b"\x01" * 32,
    )
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="même projet"):
            admin.execute(
                "UPDATE niveau3_config_documentreference SET superseded_by_id = %s WHERE id = %s",
                [autre_doc.pk, c.pk],
            )


def test_la_base_refuse_une_empreinte_qui_n_a_pas_32_octets_et_un_doublon(dossier):
    organisation, projet, profils = dossier
    _enregistrer(profils, projet)
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="sha256_32_octets"):
            admin.execute(
                """INSERT INTO niveau3_config_documentreference (id, created_at, updated_at,
                       org_id, project_id, kind, title, version, file_ref, sha256)
                   VALUES (gen_random_uuid(), now(), now(), %s, %s, 'dfil', 'Court', '1', 'fs://a',
                           %s)""",
                [organisation.id, projet.id, b"\x01" * 31],
            )
        with pytest.raises(Exception, match="uq_documentreference_version"):
            admin.execute(
                """INSERT INTO niveau3_config_documentreference (id, created_at, updated_at,
                       org_id, project_id, kind, title, version, file_ref, sha256)
                   VALUES (gen_random_uuid(), now(), now(), %s, %s, 'dfil', 'DFIL', '1', 'fs://a',
                           %s)""",
                [organisation.id, projet.id, b"\x02" * 32],
            )


def test_les_documents_sont_isoles_par_organisation(dossier):
    organisation, projet, profils = dossier
    _enregistrer(profils, projet)
    autre = _creer_organisation("ORG-B")
    _poser(autre)
    assert DocumentReference.objects.count() == 0
