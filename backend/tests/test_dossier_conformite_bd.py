# ruff: noqa: F811, E501
"""Le dossier de conformité d'un rapport publié. Voir L7-T01.

Contrôle du plan : le dossier d'un rapport publié couvre 100 % de ses rubriques, avec la citation
exacte de l'exigence source. Plus : les rubriques sans source sont NOMMÉES, le dossier d'un rapport
ne change pas quand l'exigence est révisée plus tard, le PDF est enregistré avec son empreinte.
"""

import datetime
import io
import uuid
from decimal import Decimal

import pypdf
import pytest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from niveau3_config.models import Exigence, RattachementExigence
from niveau4_reporting.publication.dossier import (
    construire_dossier,
    exporter_dossier,
    rendre_pdf,
)
from niveau4_reporting.publication.exports import exporter_rapport, lire_fichier
from niveau4_reporting.publication.models import FichierRapport
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_exports_rapport_bd import rapport  # noqa: F401
from tests.test_financements_bd import _document
from tests.test_regeneration_bd import MODELE, _publier, pub  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
D = datetime.date
CITATION = {
    "annex": "2",
    "page": 37,
    "paragraph": "4.2",
    "quote": "Le rapport est remis dans les 45 jours suivant la fin du trimestre.",
}


DEBUT = D(2026, 1, 1)


def _exigence_sur_le_mapping(
    publie, *, code="RFI", valid_from=DEBUT, valid_to=None, status="active", validateur="victor"
):
    from django.contrib.auth import get_user_model

    u = get_user_model().objects.filter(username=validateur).first() or (
        get_user_model().objects.create_user(validateur, password="x", org_id=publie.org_id)
    )
    document = _document(
        type("O", (), {"id": publie.org_id}),
        type("P", (), {"id": publie.project_id}),
        "Accord" if code == "RFI" else f"Accord {code}",
    )
    exigence = Exigence.objects.create(
        org_id=publie.org_id, project_id=publie.project_id, code=code, document=document,
        citation=CITATION, citation_verifiee_sha256=document.sha256,
        subject="Rapport financier intermédiaire", rule={}, obligation="mandatory",
        valid_from=valid_from, valid_to=valid_to, version=1, source="manual", status=status,
        validated_by=u.id, validated_at=timezone.now(),
    )  # fmt: skip
    RattachementExigence.objects.create(
        org_id=publie.org_id, exigence=exigence, target_type="mapping",
        target_id=publie.mapping_versions["WB"]["id"],
    )  # fmt: skip
    return exigence


@pytest.fixture
def dossier_pret(rapport):
    publie, profils = rapport
    _exigence_sur_le_mapping(publie)
    return publie, profils


def _texte_pdf(octets):
    return " ".join(
        page.extract_text() for page in pypdf.PdfReader(io.BytesIO(octets)).pages
    ).replace("\n", " ")


def test_le_dossier_couvre_toutes_les_rubriques_avec_la_citation_exacte(dossier_pret):
    publie, _ = dossier_pret
    dossier = construire_dossier(publie)
    assert [ligne.code for ligne in dossier.lignes] == ["R110", "R120", "R190"]  # sans l'intitulé
    assert dossier.taux_couverture == Decimal(1) and dossier.non_couvertes == []
    source = dossier.lignes[0].sources[0]
    assert (source.code, source.version, source.document) == ("RFI", 1, "Accord")
    assert source.citation == CITATION and source.validateur == "victor"
    assert dossier.lignes[0].mapping == "WB v1"
    # La rubrique calculée hérite des sources de celles dont elle dépend, sans doublon.
    assert [s.code for s in dossier.lignes[2].sources] == ["RFI"]
    assert "R110 + R120" in dossier.lignes[2].regle


def test_le_pdf_porte_la_citation_exacte_le_mapping_le_validateur_et_le_scelle(dossier_pret):
    publie, _ = dossier_pret
    texte = _texte_pdf(rendre_pdf(construire_dossier(publie), "fr"))
    assert CITATION["quote"] in texte
    for attendu in ("annexe 2", "page 37", "§ 4.2", "mapping WB v1", "victor", "Accord"):
        assert attendu in texte, attendu
    assert "3 sur 3" in texte
    assert bytes(publie.seal).hex()[:32] in texte.replace(" ", "")
    english = _texte_pdf(rendre_pdf(construire_dossier(publie), "en"))
    assert "Quoted passage" in english and CITATION["quote"] in english


def test_une_rubrique_sans_exigence_source_est_nommee_pas_cachee(pub):
    organisation, projet, profils, table = pub
    rows = [dict(r) for r in MODELE["rows"]]
    rows.insert(
        3, {"code": "R150", "type": "aggregate", "select": {"accounts": [["7000", "7999"]]}}
    )
    publie = _publier(pub, modele={**MODELE, "rows": rows})  # R150 : comptes directs, aucun mapping
    _exigence_sur_le_mapping(publie)
    dossier = construire_dossier(publie)
    assert [ligne.code for ligne in dossier.non_couvertes] == ["R150"]
    assert dossier.taux_couverture == Decimal(3) / Decimal(4)
    texte = _texte_pdf(rendre_pdf(dossier, "fr"))
    assert "SANS exigence source (1)" in texte and "R150" in texte and "3 sur 4" in texte


def test_un_mapping_sans_exigence_laisse_ses_rubriques_non_couvertes(rapport):
    publie, _ = rapport  # aucune exigence rattachée
    dossier = construire_dossier(publie)
    assert dossier.taux_couverture == Decimal(0)
    assert [ligne.code for ligne in dossier.non_couvertes] == ["R110", "R120", "R190"]


def test_le_dossier_d_un_rapport_ne_change_pas_quand_l_exigence_est_revisee_apres(rapport):
    publie, _ = rapport
    ancienne = _exigence_sur_le_mapping(publie, code="RFI", valid_to=D(2027, 1, 1))
    # Une exigence qui n'entre en vigueur qu'APRÈS la publication ne figure pas au dossier.
    _exigence_sur_le_mapping(publie, code="RFI-2", valid_from=D(2999, 1, 1))
    avant = construire_dossier(publie)
    Exigence.objects.filter(pk=ancienne.pk).update(status="superseded")  # remplacée depuis
    apres = construire_dossier(publie)
    assert [s.code for s in avant.lignes[0].sources] == ["RFI"]
    assert avant.lignes == apres.lignes  # le rapport est resté justifié par ce qui l'était


def test_le_dossier_est_enregistre_avec_son_empreinte_a_cote_du_rapport(dossier_pret):
    publie, profils = dossier_pret
    rapport_pdf = exporter_rapport(utilisateur=profils["pia"], rapport=publie, format="pdf")
    dossier = exporter_dossier(utilisateur=profils["pia"], rapport=publie)
    assert dossier.pk != rapport_pdf.pk and dossier.nature == "dossier"
    assert FichierRapport.objects.filter(rapport=publie).count() == 2  # pas de collision
    contenu = lire_fichier(utilisateur=profils["pia"], fichier=dossier)
    import hashlib

    assert hashlib.sha256(contenu).hexdigest() == dossier.sha256
    assert exporter_dossier(utilisateur=profils["pia"], rapport=publie).pk == dossier.pk
    assert (
        exporter_rapport(utilisateur=profils["pia"], rapport=publie, format="pdf").pk
        == rapport_pdf.pk
    )


def test_exporter_le_dossier_exige_l_habilitation(dossier_pret):
    publie, profils = dossier_pret
    with pytest.raises(PermissionDenied):
        exporter_dossier(utilisateur=profils["amina"], rapport=publie)
    assert uuid.UUID(str(publie.id))
