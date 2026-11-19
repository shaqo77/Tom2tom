"""Fabrique de vrais documents pour les tests : un PDF paginé et un DOCX, sans dépendance."""

import io
import zipfile


def _echapper(texte: str) -> bytes:
    brut = texte.encode("cp1252")
    return brut.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def fabriquer_pdf(pages: list[str]) -> bytes:
    """Un PDF valide d'une ligne de texte par page (Helvetica, WinAnsi : accents français)."""
    n = len(pages)
    corps: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{' '.join(f'{4 + 2 * i} 0 R' for i in range(n))}] "
            f"/Count {n} >>"
        ).encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    for i, texte in enumerate(pages):
        flux = b"BT /F1 11 Tf 40 750 Td (" + _echapper(texte) + b") Tj ET" if texte else b""
        corps[4 + 2 * i] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {5 + 2 * i} 0 R /Resources << /Font << /F1 3 0 R >> >> >>"
        ).encode()
        corps[5 + 2 * i] = b"<< /Length %d >>\nstream\n" % len(flux) + flux + b"\nendstream"
    sortie = io.BytesIO()
    sortie.write(b"%PDF-1.4\n")
    positions = {}
    for numero in sorted(corps):
        positions[numero] = sortie.tell()
        sortie.write(b"%d 0 obj\n" % numero + corps[numero] + b"\nendobj\n")
    debut_xref = sortie.tell()
    sortie.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(corps) + 1))
    for numero in sorted(corps):
        sortie.write(b"%010d 00000 n \n" % positions[numero])
    sortie.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(corps) + 1, debut_xref)
    )
    return sortie.getvalue()


def fabriquer_docx(paragraphes: list[str]) -> bytes:
    """Un DOCX minimal : un paragraphe Word par entrée."""

    def echapper(texte: str) -> str:
        return texte.replace("&", "&amp;").replace("<", "&lt;")

    corps = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{echapper(p)}</w:t></w:r></w:p>' for p in paragraphes
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{corps}</w:body></w:document>"
    )
    sortie = io.BytesIO()
    with zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return sortie.getvalue()
