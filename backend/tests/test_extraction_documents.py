"""Extraction du texte des documents de référence, sans base de données. Voir L5-T02."""

import io
import zipfile

import pytest

from niveau3_config.services.extraction import (
    ExtractionImpossible,
    extraire_pages,
    normaliser,
    type_du_contenu,
)
from tests.outils_documents import fabriquer_docx, fabriquer_pdf


def test_normaliser_rend_comparables_la_typographie_et_les_espaces():
    assert normaliser("L’agent  a  remis\n le « rapport » — dans les 45\tjours") == (
        'L\'agent a remis le " rapport " - dans les 45 jours'
    )
    assert normaliser("ﬁnancier") == "financier"  # ligature
    assert normaliser("rap­port") == "rapport"  # trait d'union conditionnel
    assert normaliser("  ") == ""


def test_normaliser_garde_la_casse_et_les_accents_significatifs():
    assert normaliser("Rapport") != normaliser("rapport")
    assert normaliser("résumé") != normaliser("resume")


def test_le_type_se_reconnait_a_son_contenu():
    assert type_du_contenu(fabriquer_pdf(["x"])) == "pdf"
    assert type_du_contenu(fabriquer_docx(["x"])) == "docx"
    assert type_du_contenu(b"du texte") == "texte"


def test_un_texte_brut_utf8_ou_cp1252_est_lu():
    assert extraire_pages("Dépenses éligibles".encode()) == ["Dépenses éligibles"]
    assert extraire_pages("Dépenses éligibles".encode("cp1252")) == ["Dépenses éligibles"]


def test_un_pdf_est_lu_page_par_page():
    pdf = fabriquer_pdf(["Article 1 Objet de l'accord", "Article 4.2 Rapport dans les 45 jours"])
    pages = extraire_pages(pdf)
    assert len(pages) == 2
    assert "Objet de l'accord" in pages[0] and "45 jours" in pages[1]


def test_un_pdf_avec_accents_est_lu():
    (page,) = extraire_pages(fabriquer_pdf(["Les dépenses éligibles à l'état certifié"]))
    assert "dépenses éligibles" in page and "certifié" in page


def test_un_docx_est_lu_paragraphe_par_paragraphe():
    (texte,) = extraire_pages(fabriquer_docx(["Premier paragraphe.", "Second & dernier."]))
    assert texte == "Premier paragraphe.\nSecond & dernier."


@pytest.mark.parametrize(
    "contenu, message",
    [
        (fabriquer_pdf([""]), "aucun texte extractible"),
        (b"%PDF-1.4 ceci n'est pas un pdf", "PDF illisible"),
        (b"\x00\x01\x02binaire", "non pris en charge"),
        (b"\xff\xfe\x81\x8d\x8f", "encodage inconnu"),
        (b"PK\x03\x04pas une archive", "illisible"),
    ],
)
def test_un_contenu_illisible_est_refuse_avec_sa_raison(contenu, message):
    with pytest.raises(ExtractionImpossible, match=message):
        extraire_pages(contenu)


def test_un_docx_sans_document_ou_avec_entites_est_refuse():
    sans = io.BytesIO()
    with zipfile.ZipFile(sans, "w") as archive:
        archive.writestr("autre.xml", "<a/>")
    with pytest.raises(ExtractionImpossible, match="sans document Word"):
        extraire_pages(sans.getvalue())
    piege = io.BytesIO()
    with zipfile.ZipFile(piege, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa">]><d>&a;</d>',
        )
    with pytest.raises(ExtractionImpossible, match="déclaration de type"):
        extraire_pages(piege.getvalue())
