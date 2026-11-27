"""Écrit un fichier Excel NON OFFICIEL d'une demande de retrait (correspondance du bailleur).

Chaque cellule est un TEXTE exact (jamais un nombre à virgule flottante, aucune formule) : le
fichier sert à reporter les chiffres sur le formulaire officiel de la Banque. La première ligne le
dit. Ce que l'application ne sait pas (coordonnées bancaires, signataires…) est listé dans
« À compléter », jamais inventé.
"""

import io
import json
import re
from decimal import Decimal
from functools import cache
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font

from core.i18n import msg
from niveau1_socle.decaissements.models import DemandeRetrait

from .sources import SOURCES_DEMANDE, SOURCES_LIGNE, SOURCES_TOTAL, Contexte, contexte_de
from .types_bad import type_bad

DOSSIER = Path(__file__).resolve().parents[2] / "niveau2_profils" / "formats_export"
GENRES = ("champ", "choix", "a_completer", "tableau")
SOURCES_SPECIALES = {"numero_ligne"}
NOM_VALIDE = re.compile(r"^[a-z0-9_]+$")
NUMERO_ACCORD = re.compile(r"^\d{13}$")
NUMERO_DEMANDE = re.compile(r"^\d{4}([A-Z]{3})?$")
CONTROLES = {
    "numero_accord_13_chiffres": (NUMERO_ACCORD, "formats_bailleur.verifier_numero_accord"),
    "numero_demande_bad": (NUMERO_DEMANDE, "formats_bailleur.verifier_numero_demande"),
}
AVERTISSEMENT = "DOCUMENT NON OFFICIEL : à reporter sur le formulaire de la Banque"


class FormatInconnu(LookupError):
    """Le format demandé n'existe pas (ou pas pour ce bailleur)."""


class FormatInapplicable(ValueError):
    """Le format existe mais ne s'applique pas à cette demande."""


class FormatInvalide(ValueError):
    """Un fichier de correspondance est mal formé : refusé au chargement, jamais à l'export."""


def _verifier(nom: str, bloc: dict) -> None:
    def refuser(cle: str, valeur) -> FormatInvalide:
        return FormatInvalide(msg(cle, format=nom, valeur=repr(valeur)))

    if bloc.get("genre") not in GENRES:
        raise refuser("formats_bailleur.genre_inconnu", bloc.get("genre"))
    if "controle" in bloc and bloc["controle"] not in CONTROLES:
        raise refuser("formats_bailleur.controle_inconnu", bloc["controle"])
    if bloc["genre"] in ("champ", "choix") and bloc.get("source") not in SOURCES_DEMANDE:
        raise refuser("formats_bailleur.source_demande_inconnue", bloc.get("source"))
    if bloc["genre"] == "tableau":
        if bloc.get("groupe") not in SOURCES_LIGNE:
            raise refuser("formats_bailleur.groupe_inconnu", bloc.get("groupe"))
        if bloc.get("total") not in SOURCES_TOTAL:
            raise refuser("formats_bailleur.total_inconnu", bloc.get("total"))
        for colonne in bloc.get("colonnes", []):
            source = colonne.get("source")
            if source not in SOURCES_LIGNE and source not in SOURCES_SPECIALES:
                raise refuser("formats_bailleur.source_ligne_inconnue", source)


@cache
def _definition(bailleur: str) -> dict:
    if not NOM_VALIDE.match(bailleur):  # un nom reçu n'est jamais un morceau de chemin
        raise FormatInconnu(bailleur)
    chemin = DOSSIER / f"{bailleur}.json"
    if not chemin.is_file():
        raise FormatInconnu(bailleur)
    definition = json.loads(chemin.read_text(encoding="utf-8"))
    for nom, format_ in definition["formats"].items():
        for bloc in format_["blocs"]:
            _verifier(nom, bloc)
    return definition


def formats_disponibles(bailleur: str) -> list[str]:
    try:
        return sorted(_definition(bailleur.lower())["formats"])
    except FormatInconnu:
        return []


def _controler(bloc: dict, valeur: str, a_verifier: list[str]) -> None:
    controle = bloc.get("controle")
    if controle and valeur:
        motif, cle = CONTROLES[controle]
        if not motif.match(valeur):
            a_verifier.append(str(msg(cle, valeur=valeur)))


def export_demande(demande: DemandeRetrait, format_: str) -> tuple[bytes, str]:
    """`(octets du fichier .xlsx, nom du fichier)`.

    Lève `FormatInconnu`, `FormatInapplicable` ou `TypeBadIndeterminable`.
    """
    contexte = contexte_de(demande)
    bailleur = contexte.accord.bailleur.code.lower()
    definition = _definition(bailleur)
    if not NOM_VALIDE.match(format_) or format_ not in definition["formats"]:
        raise FormatInconnu(format_)
    modele = definition["formats"][format_]
    if not contexte.lignes:
        raise FormatInapplicable(msg("formats_bailleur.demande_sans_ligne", numero=demande.numero))
    genre_bad = type_bad(demande)
    if genre_bad not in modele["types_bad"]:
        raise FormatInapplicable(
            msg("formats_bailleur.format_non_applicable", format=format_, type=genre_bad)
        )

    classeur = openpyxl.Workbook()
    feuille = classeur.active
    feuille.title = format_.upper().replace("BAD_", "")
    gras = Font(bold=True)
    feuille.append([AVERTISSEMENT])
    feuille["A1"].font = Font(bold=True, color="FF0000")
    feuille.append([modele["titre"]])
    feuille["A2"].font = gras
    feuille.append([])
    a_completer: list[str] = []
    a_verifier: list[str] = []

    for bloc in modele["blocs"]:
        if bloc["genre"] == "champ":
            valeur = str(SOURCES_DEMANDE[bloc["source"]](contexte))
            _controler(bloc, valeur, a_verifier)
            feuille.append([bloc["etiquette"], valeur])
        elif bloc["genre"] == "choix":
            choisi = SOURCES_DEMANDE[bloc["source"]](contexte)
            feuille.append([bloc["etiquette"]])
            for code, libelle in bloc["options"]:
                feuille.append(["    " + libelle, "X" if code == choisi else ""])
        elif bloc["genre"] == "a_completer":
            feuille.append([bloc["etiquette"], ""])
            a_completer.append(bloc["etiquette"])
        else:
            _ecrire_tableau(feuille, bloc, contexte, gras)

    feuille.append([])
    if a_verifier:
        feuille.append(["À VÉRIFIER"])
        feuille[f"A{feuille.max_row}"].font = gras
        for ligne in a_verifier:
            feuille.append(["    " + ligne])
    if a_completer:
        feuille.append(
            ["À COMPLÉTER sur le formulaire de la Banque (informations absentes de l'application)"]
        )
        feuille[f"A{feuille.max_row}"].font = gras
        for ligne in a_completer:
            feuille.append(["    " + ligne])
    feuille.column_dimensions["A"].width = 60
    for colonne in "BCDEFGHIJK":
        feuille.column_dimensions[colonne].width = 24
    for ligne in feuille.iter_rows():
        for cellule in ligne:
            if cellule.value is not None:
                cellule.value = str(cellule.value)
                cellule.data_type = "s"  # TEXTE : aucun nombre, aucune formule
                cellule.alignment = Alignment(wrap_text=True, vertical="top")
    sortie = io.BytesIO()
    classeur.save(sortie)
    nom = re.sub(r"[^A-Za-z0-9_-]", "-", f"{format_}-{demande.numero}") + ".xlsx"
    return sortie.getvalue(), nom


def _ecrire_tableau(feuille, bloc: dict, contexte: Contexte, gras: Font) -> None:
    groupes: dict[str, list] = {}
    for ligne in contexte.lignes:
        groupes.setdefault(str(SOURCES_LIGNE[bloc["groupe"]](contexte, ligne)), []).append(ligne)
    total_general = Decimal(0)
    for code in sorted(groupes):
        lignes = groupes[code]
        libelle = SOURCES_LIGNE["ligne.categorie_libelle"](contexte, lignes[0])
        feuille.append([bloc["etiquette_groupe"], f"{code} {libelle}".strip()])
        feuille.append([c["titre"] for c in bloc["colonnes"]])
        for cellule in feuille[feuille.max_row]:
            cellule.font = gras
        for numero, ligne in enumerate(lignes, start=1):
            feuille.append(
                [
                    numero
                    if c["source"] == "numero_ligne"
                    else SOURCES_LIGNE[c["source"]](contexte, ligne)
                    for c in bloc["colonnes"]
                ]
            )
        sous_total = sum(
            (_montant(SOURCES_LIGNE[bloc["total"]](contexte, x)) for x in lignes), Decimal(0)
        )
        total_general += sous_total
        feuille.append(["Total", contexte.texte(sous_total)])
        feuille[f"A{feuille.max_row}"].font = gras
        feuille.append([])
    feuille.append(["Running Total", contexte.texte(total_general)])
    feuille[f"A{feuille.max_row}"].font = gras


def _montant(texte: str) -> Decimal:
    return Decimal(texte)
