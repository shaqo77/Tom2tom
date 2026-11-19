"""L'écrivain de PDF minimal : lisible, paginé, déterministe. Voir L5-T07 (logique pure)."""

import io

import pytest
from pypdf import PdfReader

from niveau3_config.services.pdf_minimal import DocumentPDF


def _pages(octets: bytes) -> list[str]:
    return [page.extract_text() for page in PdfReader(io.BytesIO(octets)).pages]


def test_les_accents_francais_les_parentheses_et_les_barres_sont_conserves():
    doc = DocumentPDF("Pied")
    doc.ajouter(
        "Rapport financier intermédiaire (RFI) — délai de 45 jours « à l'échéance »", "titre"
    )
    doc.ajouter("Chemin C:\\dossier\\fichier ; noté (a) et (b)", "normal")
    texte = "\n".join(_pages(doc.octets()))
    assert "intermédiaire (RFI)" in texte
    assert "« à l'échéance »" in texte
    assert "C:\\dossier\\fichier" in texte and "(a) et (b)" in texte


def test_un_texte_long_est_replie_et_chaque_style_est_accepte():
    doc = DocumentPDF()
    mot = "x" * 300  # un mot sans espace ne déborde pas de la page : il est coupé
    for style in ("titre", "section", "sous_titre", "normal", "retrait", "petit"):
        doc.ajouter(f"{style} " + "mot " * 80 + mot, style)
    texte = "".join(_pages(doc.octets())).replace("\n", "")
    assert "x" * 300 in texte  # rien n'est perdu


def test_aucune_ligne_ne_depasse_la_largeur_de_la_page():
    doc = DocumentPDF()
    doc.ajouter("mot " * 400, "normal")
    doc.ajouter("y" * 500, "retrait")
    lignes = [x for texte in _pages(doc.octets()) for x in texte.split("\n")]
    assert max(len(ligne) for ligne in lignes) <= 110  # sinon le texte sortirait de la page


def test_un_style_inconnu_est_refuse():
    with pytest.raises(ValueError, match="style inconnu"):
        DocumentPDF().ajouter("x", "gras_italique")


def test_la_pagination_numerote_les_pages_et_ne_coupe_aucune_ligne():
    doc = DocumentPDF("Mon guide")
    for i in range(400):
        doc.ajouter(f"Ligne numéro {i:03d}", "normal")
    pages = _pages(doc.octets())
    assert len(pages) > 3
    for numero, texte in enumerate(pages, start=1):
        assert f"Page {numero} / {len(pages)}" in texte and "Mon guide" in texte
    toutes = "\n".join(pages)
    assert all(f"Ligne numéro {i:03d}" in toutes for i in range(400))


def test_un_saut_de_page_force_une_nouvelle_page_et_un_document_vide_est_valide():
    doc = DocumentPDF()
    doc.ajouter("Avant", "normal")
    doc.saut_de_page()
    doc.ajouter("Après", "normal")
    avant, apres = _pages(doc.octets())
    assert "Avant" in avant and "Après" not in avant and "Après" in apres
    assert len(_pages(DocumentPDF().octets())) == 1


def test_la_sortie_est_deterministe_et_les_caracteres_hors_cp1252_ne_cassent_rien():
    def fabriquer():
        doc = DocumentPDF("p")
        doc.ajouter("a → b ≥ c ✓ \u202f fin", "normal")
        return doc.octets()

    assert fabriquer() == fabriquer()
    assert "a -> b >= c" in _pages(fabriquer())[0]
