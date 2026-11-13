"""Extraction du texte d'un document de référence. Voir L5-T02.

Sert à une seule chose : vérifier qu'une citation est RETROUVABLE dans le document. Formats pris en
charge : PDF (par page), DOCX et texte brut. Tout autre contenu est refusé avec une raison claire :
mieux vaut refuser un format que valider une citation sur un texte mal lu.

Le texte n'est extrait qu'après avoir revérifié que le fichier stocké a toujours l'empreinte
enregistrée : une citation ne se vérifie jamais sur un fichier modifié en douce.
"""

import io
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

from .. import stockage

LIMITE_XML = 50 * 1024 * 1024  # taille décompressée maximale d'un DOCX (contre les bombes zip)
ESPACE_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TYPOGRAPHIE = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "′": "'",
        "`": "'",
        "´": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "−": "-",
        "­": "",
        "​": "",
        "‌": "",
        "‍": "",
        "﻿": "",
    }
)


class ExtractionImpossible(ValueError):
    """Le contenu du document ne permet pas d'en extraire un texte fiable."""


def normaliser(texte: str) -> str:
    """Rend deux textes comparables : même Unicode (ligatures, espaces insécables), même
    typographie (guillemets, apostrophes, tirets), espaces et retours à la ligne ramenés à un seul
    espace. La CASSE et les ACCENTS restent significatifs : une citation est littérale."""
    texte = unicodedata.normalize("NFKC", texte).translate(TYPOGRAPHIE)
    return re.sub(r"\s+", " ", texte).strip()


def type_du_contenu(contenu: bytes) -> str:
    if contenu.startswith(b"%PDF"):
        return "pdf"
    if contenu.startswith(b"PK\x03\x04"):
        return "docx"
    return "texte"


def _pages_pdf(contenu: bytes) -> list[str]:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        lecteur = PdfReader(io.BytesIO(contenu))
        if lecteur.is_encrypted:
            raise ExtractionImpossible("Le PDF est chiffré : fournissez une version non protégée")
        pages = [page.extract_text() or "" for page in lecteur.pages]
    except ExtractionImpossible:
        raise
    except (PyPdfError, ValueError, KeyError, OSError) as erreur:
        raise ExtractionImpossible(f"PDF illisible : {erreur}") from erreur
    if not any(p.strip() for p in pages):
        raise ExtractionImpossible(
            "Le PDF ne contient aucun texte extractible (document scanné ?) : océrisez-le d'abord"
        )
    return pages


def _pages_docx(contenu: bytes) -> list[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(contenu)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > LIMITE_XML:
                raise ExtractionImpossible("Le document Word est trop volumineux")
            xml = archive.read("word/document.xml")
    except KeyError as erreur:
        raise ExtractionImpossible("Archive sans document Word (word/document.xml)") from erreur
    except zipfile.BadZipFile as erreur:
        raise ExtractionImpossible("Document Word illisible") from erreur
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:  # pas d'entités externes ni d'expansion
        raise ExtractionImpossible("Document Word refusé : déclaration de type non autorisée")
    try:
        racine = ET.fromstring(xml)
    except ET.ParseError as erreur:
        raise ExtractionImpossible(f"Document Word illisible : {erreur}") from erreur
    paragraphes = []
    for paragraphe in racine.iter(f"{ESPACE_W}p"):
        morceaux = []
        for element in paragraphe.iter():
            if element.tag == f"{ESPACE_W}t":
                morceaux.append(element.text or "")
            elif element.tag in (f"{ESPACE_W}tab", f"{ESPACE_W}br"):
                morceaux.append(" ")
        paragraphes.append("".join(morceaux))
    return ["\n".join(paragraphes)]


def _pages_texte(contenu: bytes) -> list[str]:
    if b"\x00" in contenu:
        raise ExtractionImpossible("Format de fichier non pris en charge (PDF, DOCX ou texte)")
    for encodage in ("utf-8-sig", "cp1252"):
        try:
            return [contenu.decode(encodage)]
        except UnicodeDecodeError:
            continue
    raise ExtractionImpossible("Texte illisible : encodage inconnu")


def extraire_pages(contenu: bytes) -> list[str]:
    """Le texte du document, une entrée par page (PDF) ou une seule entrée (DOCX, texte)."""
    return {"pdf": _pages_pdf, "docx": _pages_docx, "texte": _pages_texte}[
        type_du_contenu(contenu)
    ](contenu)


def document_lu(document) -> tuple[str, list[str]]:
    """`(type, pages)` d'un document enregistré, après revérification de son empreinte."""
    contenu = stockage.lire(document.file_ref)
    if stockage.empreinte(contenu) != bytes(document.sha256):
        raise ExtractionImpossible(
            f"Le fichier de « {document.title} » ne correspond plus à son empreinte enregistrée : "
            "on ne vérifie pas de citation sur un fichier modifié"
        )
    return type_du_contenu(contenu), extraire_pages(contenu)


def pages_du_document(document) -> list[str]:
    return document_lu(document)[1]


def extraire_texte(document) -> str:
    return "\n".join(pages_du_document(document))
