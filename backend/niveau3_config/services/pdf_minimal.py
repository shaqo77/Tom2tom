"""Un écrivain de PDF minimal, sans dépendance : texte, titres, pagination, numéros de page.

Polices standard du PDF (Helvetica, Helvetica-Bold), encodage WinAnsi : les accents français
s'impriment sans police embarquée. La sortie est DÉTERMINISTE (aucune date ni identifiant
aléatoire) : le même contenu donne les mêmes octets, donc la même empreinte.
"""

import io
import textwrap

from core.i18n import msg

LARGEUR, HAUTEUR = 595, 842  # A4 en points
MARGE_X, MARGE_HAUT, MARGE_BAS = 50, 60, 60
STYLES = {
    # nom: (police, corps, largeur en caractères, retrait, espace avant)
    "titre": ("F2", 17, 52, 0, 0),
    "section": ("F2", 12.5, 68, 0, 12),
    "sous_titre": ("F2", 10.5, 80, 0, 7),
    "normal": ("F1", 10, 88, 0, 2),
    "retrait": ("F1", 10, 82, 14, 1),
    "petit": ("F1", 8.5, 104, 0, 1),
}
REMPLACEMENTS = str.maketrans(
    {"→": "->", "≥": ">=", "≤": "<=", " ": " ", " ": " ", "≠": "!=", "✓": "oui"}
)


def _echapper(texte: str) -> bytes:
    brut = texte.translate(REMPLACEMENTS).encode("cp1252", errors="replace")
    return brut.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class DocumentPDF:
    def __init__(self, titre_court: str = ""):
        self.titre_court = titre_court
        self._lignes: list[tuple[str, str]] = []  # (style, texte) ; ("saut", "") = saut de page

    def ajouter(self, texte: str, style: str = "normal") -> None:
        if style not in STYLES:
            raise ValueError(msg("pdf_minimal.style_inconnu", style=style))
        _, _, largeur, _, _ = STYLES[style]
        for paragraphe in texte.split("\n"):
            morceaux = textwrap.wrap(paragraphe, width=largeur, break_long_words=True) or [""]
            self._lignes.extend((style, morceau) for morceau in morceaux)

    def espace(self) -> None:
        self._lignes.append(("normal", ""))

    def saut_de_page(self) -> None:
        self._lignes.append(("saut", ""))

    def _pages(self) -> list[list[tuple[str, float, float, str]]]:
        pages: list[list[tuple[str, float, float, str]]] = [[]]
        y = HAUTEUR - MARGE_HAUT
        precedent_vide = True
        for style, texte in self._lignes:
            if style == "saut":
                pages.append([])
                y = HAUTEUR - MARGE_HAUT
                precedent_vide = True
                continue
            police, corps, _, retrait, avant = STYLES[style]
            hauteur = corps * 1.35
            avant = 0 if precedent_vide else avant
            if y - avant - hauteur < MARGE_BAS:
                pages.append([])
                y = HAUTEUR - MARGE_HAUT
                avant = 0
            y -= avant + hauteur
            if texte:
                pages[-1].append((police, corps, MARGE_X + retrait, y, texte))
            precedent_vide = not texte
        return pages

    def octets(self) -> bytes:
        pages = self._pages()
        total = len(pages)
        corps: dict[int, bytes] = {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: (
                f"<< /Type /Pages /Kids [{' '.join(f'{5 + 2 * i} 0 R' for i in range(total))}] "
                f"/Count {total} >>"
            ).encode(),
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            4: (
                b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                b"/Encoding /WinAnsiEncoding >>"
            ),
        }
        for i, lignes in enumerate(pages):
            flux = io.BytesIO()
            for police, corps_texte, x, y, texte in lignes:
                flux.write(
                    b"BT /%s %s Tf 1 0 0 1 %s %s Tm ("
                    % (
                        police.encode(),
                        f"{corps_texte:g}".encode(),
                        f"{x:g}".encode(),
                        f"{y:.1f}".encode(),
                    )
                    + _echapper(texte)
                    + b") Tj ET\n"
                )
            pied = f"{self.titre_court}   Page {i + 1} / {total}".strip()
            flux.write(b"BT /F1 8 Tf 1 0 0 1 %d 30 Tm (" % MARGE_X + _echapper(pied) + b") Tj ET\n")
            donnees = flux.getvalue()
            corps[5 + 2 * i] = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {LARGEUR} {HAUTEUR}] "
                f"/Contents {6 + 2 * i} 0 R "
                "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>"
            ).encode()
            corps[6 + 2 * i] = b"<< /Length %d >>\nstream\n" % len(donnees) + donnees + b"endstream"
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
