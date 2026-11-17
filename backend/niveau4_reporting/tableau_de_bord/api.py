"""L'API HTTP du tableau de bord multi-projets (lecture seule). Voir L10-T02.

Mêmes conventions que `niveau1_socle/marches/api.py` : montants en chaînes, erreurs
`{code, message}`, habilitation « consulter » contrôlée par les services. Le périmètre est celui
des projets que l'utilisateur peut consulter : un identifiant de projet demandé hors périmètre est
ignoré dans le tableau (jamais d'élargissement) et refusé (403) pour la descente.
"""

import uuid

from core.api import (
    VueMetier,
    parametre_date,
    reponse,
)
from core.metier import refuser as refuser_champ
from niveau4_reporting.tableau_de_bord import (
    Filtres,
    consolider,
    detail_indicateur,
    ecritures_du_detail,
    tableau_de_bord,
)
from niveau4_reporting.tableau_de_bord.conformite import CHAMPS
from niveau4_reporting.tableau_de_bord.detail import CODES
from niveau4_reporting.tableau_de_bord.financier import Indicateur


def _uuid(brut: str, nom: str) -> uuid.UUID:
    try:
        return uuid.UUID(brut)
    except ValueError:
        refuser_champ("api.champ_invalide", champ=nom, attendu="identifiant")


def _filtres(requete) -> Filtres:
    q = requete.query_params
    projets = q.get("projets")
    statut_projet = q.get("statut_projet") or Filtres.statut_projet
    return Filtres(
        projets=frozenset(_uuid(p, "projets") for p in projets.split(",") if p)
        if projets
        else None,
        bailleur_id=_uuid(q["bailleur"], "bailleur") if q.get("bailleur") else None,
        accord_id=_uuid(q["accord"], "accord") if q.get("accord") else None,
        devise=q.get("devise") or None,
        du=parametre_date(requete, "du", obligatoire=False),
        au=parametre_date(requete, "au", obligatoire=False),
        statut_accord=q.get("statut_accord") or None,
        statut_projet=None if statut_projet == "tous" else statut_projet,
        statut_configuration=q.get("statut_configuration") or None,
    )


def _indicateur(i: Indicateur) -> dict:
    return {
        "par_projet": {str(p): m for p, m in i.par_projet.items()},
        "total_par_devise": i.total,
    }


class TableauDeBordVue(VueMetier):
    def get(self, requete):
        jour = parametre_date(requete, "jour")
        tdb = tableau_de_bord(utilisateur=requete.user, jour=jour, filtres=_filtres(requete))
        conformite = tdb.conformite
        return reponse(
            {
                "jour": tdb.jour,
                "projets": [
                    {
                        "id": p.id,
                        "code": p.code,
                        "libelle": p.libelle,
                        "statut": p.statut,
                        "configuration": p.configuration,
                        "bailleurs": p.bailleurs,
                    }
                    for p in tdb.projets
                ],
                "indicateurs": {code: _indicateur(i) for code, i in tdb.indicateurs.items()},
                "taux_execution": tdb.taux_execution(),
                "par_composante": {
                    composante: {code: _indicateur(i) for code, i in ventilation.items()}
                    for composante, ventilation in tdb.par_composante.items()
                },
                "conformite": {
                    "par_projet": {str(p): vars(c) for p, c in conformite.par_projet.items()},
                    "totaux": {champ: conformite.total(champ) for champ in CHAMPS},
                    "taux_acceptation": conformite.taux_acceptation,
                },
                "avertissements": tdb.avertissements,
            }
        )


class Consolidation(VueMetier):
    def get(self, requete, code):
        if code not in CODES:
            refuser_champ("api.champ_invalide", champ="indicateur", attendu="indicateur connu")
        jour = parametre_date(requete, "jour")
        devise_reference = requete.query_params.get("devise_reference")
        if not devise_reference:
            refuser_champ("api.champ_obligatoire", champ="devise_reference")
        tdb = tableau_de_bord(utilisateur=requete.user, jour=jour, filtres=_filtres(requete))
        c = consolider(
            tdb.indicateurs[code],
            devise_reference=devise_reference,
            jour=jour,
            type_taux=requete.query_params.get("type_taux", "officiel"),
        )
        return reponse(
            {
                "indicateur": code,
                "devise_reference": c.devise_reference,
                "jour": c.jour,
                "consolide": c.montant is not None,
                "montant": c.montant,
                "par_projet": {str(p): m for p, m in c.par_projet.items()},
                "taux": {d: {"taux": t, "date": j} for d, (t, j) in c.taux.items()},
                "methode": c.methode if c.montant is not None else None,
                "raison": c.raison,
            }
        )


def _detail_a_dict(d) -> dict:
    return {
        "type": d.type,
        "id": d.id,
        "libelle": d.libelle,
        "devise": d.devise,
        "montant": d.montant,
        "a_une_ecriture": d.a_une_ecriture,
    }


class Detail(VueMetier):
    def get(self, requete, project_id, code):
        if code not in CODES:
            refuser_champ("api.champ_invalide", champ="indicateur", attendu="indicateur connu")
        lignes = detail_indicateur(
            utilisateur=requete.user,
            code=code,
            project_id=project_id,
            jour=parametre_date(requete, "jour"),
            filtres=_filtres(requete),
        )
        return reponse([_detail_a_dict(d) for d in lignes])


class DetailEcritures(VueMetier):
    def get(self, requete, project_id, code, detail_id):
        if code not in CODES:
            refuser_champ("api.champ_invalide", champ="indicateur", attendu="indicateur connu")
        jour = parametre_date(requete, "jour")
        filtres = _filtres(requete)
        lignes = detail_indicateur(
            utilisateur=requete.user, code=code, project_id=project_id, jour=jour, filtres=filtres
        )
        detail = next((d for d in lignes if d.id == detail_id), None)
        if detail is None:
            from rest_framework.exceptions import NotFound

            raise NotFound
        ecritures = ecritures_du_detail(
            utilisateur=requete.user, detail=detail, project_id=project_id, jour=jour
        )
        return reponse(
            {
                "detail": _detail_a_dict(detail),
                "ecritures": [
                    {
                        "ecriture_id": e.ecriture_id,
                        "numero": e.numero,
                        "date": e.date,
                        "libelle": e.libelle,
                        "montant": e.montant,
                    }
                    for e in ecritures
                ],
            }
        )
