"""Le gabarit d'un profil de décaissement dérivé d'un profil de bailleur livré. Voir L11-D2.

Un profil de bailleur décrit des règles ; le profil de décaissement d'un accord les met en
paramètres. Le gabarit fait le pont SANS rien inventer : il ne calcule que ce que le profil de
bailleur énonce (par ex. BAD : demandes acceptées 4 mois après la clôture → délai de décaissement),
liste les contrôles de la bibliothèque qui appliquent déjà une règle, et nomme celles que rien ne
contrôle encore. Ce qui dépend du projet (régime, catégories, taux, comptes, pièces) reste à
décider.

Le gabarit ne crée rien : il rend un corps que l'administrateur relit puis soumet à l'API des
profils de décaissement (le profil naît en brouillon, rien ne s'applique avant validation).
"""

import calendar
import datetime

from .catalogue import lire_profil_livre

A_DECIDER = ("regime", "regles", "comptes", "methodes_pieces")


def ajouter_mois(date: datetime.date, mois: int) -> datetime.date:
    """`date` + `mois` mois civils ; sans ce jour dans le mois d'arrivée, son dernier jour."""
    indice = date.year * 12 + (date.month - 1) + mois
    annee, mois_arrivee = divmod(indice, 12)
    jour = min(date.day, calendar.monthrange(annee, mois_arrivee + 1)[1])
    return datetime.date(annee, mois_arrivee + 1, jour)


def gabarit_decaissement(
    nom: str,
    *,
    date_cloture: datetime.date,
    date_eligibilite: datetime.date | None = None,
    libelle_langue: str = "fr",
) -> dict:
    """Jalons dérivés, contrôles à envisager et règles non branchées d'un profil de bailleur."""
    donnees = lire_profil_livre(nom)
    jalons = {"closing_date": date_cloture}
    if date_eligibilite is not None:
        jalons["eligibility_date"] = date_eligibilite
    controles: list[str] = []
    non_branches = []
    for element in donnees["elements"]:
        if element["kind"] != "check":
            continue
        contenu = element.get("contenu") or {}
        for branchement in contenu.get("branchement", []):
            genre = branchement["type"]
            if genre == "controle_bibliotheque":
                controles.extend(c for c in branchement["codes"] if c not in controles)
            elif genre == "profil_decaissement" and "derive" in branchement:
                derive = branchement["derive"]
                parametre = contenu["parametres"][derive["parametre"]]
                if derive["depuis"] == "closing_date":
                    jalons[branchement["champ"]] = ajouter_mois(date_cloture, parametre)
            elif genre == "non_branche":
                non_branches.append(
                    {
                        "code": element["code"],
                        "label": element["label"].get(libelle_langue, element["label"]["fr"]),
                        "raison": branchement["raison"].get(
                            libelle_langue, branchement["raison"]["fr"]
                        ),
                    }
                )
    methodes = []
    for element in donnees["elements"]:
        correspondance = (element.get("contenu") or {}).get("parametres", {}).get("correspondance")
        if correspondance:
            methodes = sorted(set(correspondance.values()))
    return {
        "profil": donnees["code"],
        "version": donnees.get("version", 1),
        "jalons": jalons,
        "methodes_disponibles": methodes,
        "controles_bibliotheque": controles,
        "non_branches": non_branches,
        "a_decider": list(A_DECIDER),
    }
