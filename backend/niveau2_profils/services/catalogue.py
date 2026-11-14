"""Charger un profil de bailleur livré sous forme de DONNÉES. Voir L5-T06.

Ajouter un profil est une opération de paramétrage, jamais de développement : un fichier JSON du
catalogue, chargé par `charger_profil`, crée le profil et ses éléments par les mêmes services que
la saisie manuelle (donc avec leurs contrôles et leur journal). Le profil se charge en BROUILLON ;
le publier est un acte distinct de `parametrer`.

Les exigences d'un profil livré sont `facultatives` : le profil met à disposition, il n'impose rien.
Aucun délai n'est inventé : seul celui que l'IDA fixe pour le rapport financier intermédiaire (45
jours après la fin de chaque trimestre civil) est renseigné ; le reste est laissé au DFIL.
"""

import json
from pathlib import Path

from core.i18n import msg

from ..models import ProfilBailleur
from .profils import ajouter_element, creer_profil_bailleur, publier_profil

DOSSIER = Path(__file__).resolve().parent.parent / "catalogue"


def profils_livres() -> list[str]:
    return sorted(p.stem for p in DOSSIER.glob("*.json"))


def lire_profil_livre(nom: str) -> dict:
    chemin = DOSSIER / f"{nom}.json"
    if not chemin.is_file():
        raise FileNotFoundError(
            msg("catalogue.aucun_profil_livre_disponibles", nom=nom, v1=profils_livres())
        )
    return json.loads(chemin.read_text(encoding="utf-8"))


def charger_profil(*, utilisateur, nom: str, publier: bool = False) -> ProfilBailleur:
    """Crée le profil livré `nom` (s'il n'existe pas déjà dans cette version) avec ses éléments."""
    donnees = lire_profil_livre(nom)
    existant = ProfilBailleur.objects.filter(
        code=donnees["code"], version=donnees.get("version", 1)
    ).first()
    if existant is not None:
        return existant
    profil = creer_profil_bailleur(
        utilisateur=utilisateur,
        code=donnees["code"],
        version=donnees.get("version", 1),
        label=donnees["label"],
        description=donnees.get("description", ""),
    )
    for position, element in enumerate(donnees["elements"]):
        ajouter_element(
            utilisateur=utilisateur,
            profil=profil,
            kind=element["kind"],
            code=element["code"],
            label=element["label"],
            contenu=element.get("contenu"),
            exigence=element.get("exigence"),
            position=position,
        )
    if publier:
        profil = publier_profil(utilisateur=utilisateur, profil=profil)
    return profil
