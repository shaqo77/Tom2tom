"""Vérifier les citations d'un profil livré contre les documents du bailleur.

Un profil cite des passages (`contenu.citations` : source, page, extrait). La vérification ne
suppose rien : chaque document est reconnu par son empreinte SHA-256 (déclarée dans l'élément
`document_reference` qui porte le même code de source), puis chaque extrait est cherché, tel quel
(après normalisation typographique), à la page indiquée. Un document absent du dossier rend ses
citations « non vérifiables » : jamais « vraies par défaut ».
"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from niveau3_config.services.extraction import extraire_pages, normaliser


@dataclass
class ResultatCitations:
    verifiees: int = 0
    echecs: list = field(default_factory=list)  # (élément, page, extrait)
    non_verifiables: list = field(default_factory=list)  # (élément, source)

    @property
    def conforme(self) -> bool:
        return not self.echecs and not self.non_verifiables


def _documents_du_dossier(dossier: Path) -> dict[str, list[str]]:
    """Pages normalisées de chaque PDF du dossier, indexées par empreinte SHA-256."""
    pages = {}
    for chemin in sorted(dossier.glob("*.pdf")):
        contenu = chemin.read_bytes()
        pages[hashlib.sha256(contenu).hexdigest()] = [
            normaliser(p) for p in extraire_pages(contenu)
        ]
    return pages


def verifier_citations(donnees: dict, dossier: Path) -> ResultatCitations:
    empreintes = {
        e["contenu"]["source"]: e["contenu"]["sha256"]
        for e in donnees["elements"]
        if e["kind"] == "document_reference" and (e.get("contenu") or {}).get("sha256")
    }
    disponibles = _documents_du_dossier(Path(dossier))
    resultat = ResultatCitations()
    for element in donnees["elements"]:
        for citation in (element.get("contenu") or {}).get("citations", []):
            pages = disponibles.get(empreintes.get(citation["source"], ""))
            if pages is None:
                resultat.non_verifiables.append((element["code"], citation["source"]))
                continue
            page = citation["page"]
            if 1 <= page <= len(pages) and normaliser(citation["quote"]) in pages[page - 1]:
                resultat.verifiees += 1
            else:
                resultat.echecs.append((element["code"], page, citation["quote"]))
    return resultat
