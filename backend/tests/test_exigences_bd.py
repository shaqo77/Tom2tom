"""Registre des exigences, version minimale. Voir L0-T08 et architecture §4."""

import datetime
import hashlib
import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from niveau3_config.models import DocumentReference, Exigence, RattachementExigence

pytestmark = pytest.mark.django_db(transaction=True)
PROJECT_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
CITATION = {"annex": "2", "page": 37, "paragraph": "4.2", "quote": "dans les 45 jours"}


def _poser_org(org_id):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])


def _document(org_id, contenu=b"DFIL v1"):
    return DocumentReference.objects.create(
        org_id=org_id,
        project_id=PROJECT_ID,
        kind="dfil",
        title="DFIL du projet",
        version="1",
        issued_on=datetime.date(2026, 1, 10),
        file_ref="objets/dfil-v1.pdf",
        sha256=hashlib.sha256(contenu).digest(),
    )


def _exigence(org_id, document, **champs):
    donnees = {
        "org_id": org_id,
        "project_id": PROJECT_ID,
        "code": "IFR-TRIM",
        "document": document,
        "citation": CITATION,
        "subject": "Rapport financier intermédiaire",
        "rule": {"kind": "report", "template": "IFR"},
        "periodicity": "quarterly",
        "due_offset_days": 45,
        "obligation": "mandatory",
        "valid_from": datetime.date(2026, 1, 1),
        "version": 1,
        "status": "proposed",
        "source": "manual",
    }
    donnees.update(champs)
    if donnees["status"] in ("validated", "active"):  # la base exige une citation vérifiée (L5-T02)
        donnees.setdefault("citation_verifiee_sha256", document.sha256)
    return Exigence.objects.create(**donnees)


def test_une_exigence_active_sans_validateur_est_refusee_par_la_base(org_a):
    """Contrôle de L0-T08 : l'IntegrityError vient de PostgreSQL, pas de l'application."""
    _poser_org(org_a)
    document = _document(org_a)
    exigence = _exigence(org_a, document)

    with pytest.raises(IntegrityError, match="exigence_validation_obligatoire"):
        with transaction.atomic(), connection.cursor() as cur:
            # SQL direct : aucune validation Django ne peut intervenir.
            cur.execute(
                "UPDATE niveau3_config_exigence SET status = 'active', "
                "citation_verifiee_sha256 = %s WHERE id = %s",  # citation en règle : seul le
                [document.sha256, exigence.id],  # validateur manque, et c'est lui qui est refusé
            )


@pytest.mark.parametrize("statut", ["validated", "active"])
def test_une_exigence_validee_ou_active_exige_validateur_et_date(org_a, statut):
    _poser_org(org_a)
    document = _document(org_a)
    with pytest.raises(IntegrityError), transaction.atomic():
        _exigence(org_a, document, status=statut)
    with pytest.raises(IntegrityError), transaction.atomic():
        _exigence(org_a, document, status=statut, validated_by=uuid.uuid4())

    validee = _exigence(
        org_a,
        document,
        status=statut,
        validated_by=uuid.uuid4(),
        validated_at=timezone.now(),
    )
    assert validee.status == statut


def test_une_exigence_proposee_nexige_aucun_validateur(org_a):
    _poser_org(org_a)
    assert _exigence(org_a, _document(org_a), source="assisted", confidence="0.870")


def test_une_rubrique_se_rattache_a_un_paragraphe_de_document(org_a):
    """But de L0-T08 : de la rubrique au paragraphe, et retour."""
    _poser_org(org_a)
    exigence = _exigence(org_a, _document(org_a))
    rubrique = uuid.uuid4()
    RattachementExigence.objects.create(
        org_id=org_a, exigence=exigence, target_type="report_row", target_id=rubrique
    )

    source = Exigence.objects.get(
        rattachements__target_type="report_row", rattachements__target_id=rubrique
    )
    assert source.citation["paragraph"] == "4.2"
    assert source.citation["page"] == 37
    assert source.document.title == "DFIL du projet"
    assert source.document.sha256 == hashlib.sha256(b"DFIL v1").digest()


def test_un_meme_rattachement_nest_pas_enregistre_deux_fois(org_a):
    _poser_org(org_a)
    exigence = _exigence(org_a, _document(org_a))
    cible = uuid.uuid4()
    RattachementExigence.objects.create(
        org_id=org_a, exigence=exigence, target_type="mapping", target_id=cible
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        RattachementExigence.objects.create(
            org_id=org_a, exigence=exigence, target_type="mapping", target_id=cible
        )


def test_un_type_de_cible_hors_ensemble_ferme_est_refuse(org_a):
    _poser_org(org_a)
    exigence = _exigence(org_a, _document(org_a))
    with pytest.raises(IntegrityError), transaction.atomic():
        RattachementExigence.objects.create(
            org_id=org_a, exigence=exigence, target_type="script", target_id=uuid.uuid4()
        )


def test_une_exigence_est_versionnee_et_ses_dates_sont_semi_ouvertes(org_a):
    _poser_org(org_a)
    document = _document(org_a)
    _exigence(org_a, document, valid_to=datetime.date(2027, 1, 1), status="superseded")
    _exigence(org_a, document, version=2, valid_from=datetime.date(2027, 1, 1))
    with pytest.raises(IntegrityError), transaction.atomic():
        _exigence(org_a, document, version=2)  # même (code, version)
    with pytest.raises(IntegrityError), transaction.atomic():
        _exigence(  # intervalle vide
            org_a,
            document,
            version=3,
            valid_from=datetime.date(2027, 1, 1),
            valid_to=datetime.date(2027, 1, 1),
        )


def test_lobligation_la_periodicite_et_le_statut_sont_des_ensembles_fermes(org_a):
    _poser_org(org_a)
    document = _document(org_a)
    for champ, valeur in [
        ("obligation", "souhaitable"),
        ("periodicity", "hebdomadaire"),
        ("status", "brouillon"),
        ("source", "magie"),
    ]:
        with pytest.raises(IntegrityError), transaction.atomic():
            _exigence(org_a, document, **{champ: valeur})


def test_une_empreinte_de_document_invalide_est_refusee(org_a):
    _poser_org(org_a)
    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentReference.objects.create(
            org_id=org_a,
            project_id=PROJECT_ID,
            kind="dfil",
            title="Document tronqué",
            file_ref="objets/x.pdf",
            sha256=b"trop-court",
        )


def test_un_document_cite_ne_se_supprime_pas(org_a):
    from django.db.models import ProtectedError

    _poser_org(org_a)
    document = _document(org_a)
    _exigence(org_a, document)
    with pytest.raises(ProtectedError):
        document.delete()


def test_le_registre_ne_traverse_pas_les_organisations(org_a, org_b):
    _poser_org(org_a)
    _exigence(org_a, _document(org_a))
    _poser_org(org_b)
    assert Exigence.objects.count() == 0
    assert DocumentReference.objects.count() == 0
    assert RattachementExigence.objects.count() == 0
