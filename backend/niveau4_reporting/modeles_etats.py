"""Modèles d'états livrés comme DONNÉES. Voir L9-T05 et L10-T01.

Un modèle d'état est un JSON lu par le moteur. Ajouter un modèle est un fichier du catalogue
(`catalogue_modeles/<nom>.json`), jamais du développement : aucune application, aucun module.
Les noms se lisent dans une LISTE BLANCHE (un nom reçu n'est jamais un morceau de chemin).

Le modèle `rapprochement_compte_designe` dépend d'une source externe (le relevé bancaire), déclarée
dans `moteur/sources_externes.py` ; ses deux assertions bloquent la publication tant qu'un écart
n'est pas justifié.
"""

import copy
import json
from pathlib import Path

from core.i18n import msg

DOSSIER = Path(__file__).resolve().parent / "catalogue_modeles"


def modeles_livres() -> list[str]:
    return sorted(p.stem for p in DOSSIER.glob("*.json"))


def lire_modele_livre(nom: str) -> dict:
    """Le modèle livré `nom` (copie : l'appelant peut le modifier sans toucher au catalogue)."""
    if nom not in modeles_livres():
        raise FileNotFoundError(
            msg("catalogue.aucun_modele_livre_disponibles", nom=str(nom)[:40], v1=modeles_livres())
        )
    return json.loads((DOSSIER / f"{nom}.json").read_text(encoding="utf-8"))


def modele_rapprochement_compte_designe(version: int = 1) -> dict:
    """Le rapprochement du compte désigné (code `RCD`), à la version demandée."""
    modele = copy.deepcopy(lire_modele_livre("rapprochement_compte_designe"))
    modele["version"] = version
    return modele
