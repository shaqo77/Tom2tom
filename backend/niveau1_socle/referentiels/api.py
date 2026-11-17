"""L'API HTTP des réglages de devises (organisation, projet) et du catalogue des devises. L10.

Lecture : les réglages RÉSOLUS un jour donné, avec la provenance de chaque champ (« projet »,
« organisation » ou rien : non paramétré). Pose : une NOUVELLE version à partir d'une date d'effet ;
l'habilitation `parametrer` est contrôlée par le service, jamais par la vue.
"""

import datetime

from core.api import (
    VueMetier,
    champ_date,
    champ_texte,
    corps,
    objet_ou_404,
    parametre_date,
    projeter,
    recharge,
    reponse,
)
from core.metier import habilite, refuser
from niveau1_socle.organisations.models import Projet

from .models import Devise, ParametreDevises
from .parametres_devises import parametrer_devises, resoudre_parametres_devises

VERSION = ("id", "version", "devise_reference_id", "type_taux", "valid_from", "valid_to", "motif")


def _version(reglage: ParametreDevises) -> dict:
    sortie = projeter(reglage, *VERSION)
    sortie["devise_reference"] = sortie.pop("devise_reference_id")
    sortie["devises_autorisees"] = reglage.devises_autorisees
    sortie["project_id"] = str(reglage.project_id) if reglage.project_id else None
    return sortie


def _resolu(project_id, jour: datetime.date) -> dict:
    r = resoudre_parametres_devises(project_id, jour)
    return {
        "jour": jour,
        "devise_reference": r.devise_reference,
        "devises_autorisees": list(r.devises_autorisees) if r.devises_autorisees else None,
        "type_taux": r.type_taux,
        "origine": r.origine,
        "versions": r.versions,
    }


def _poser(requete, project_id):
    d = corps(requete)
    liste = d.get("devises_autorisees")
    if liste is not None and (
        not isinstance(liste, list) or not all(isinstance(c, str) for c in liste)
    ):
        refuser("api.champ_invalide", champ="devises_autorisees", attendu="liste de codes")
    reglage = parametrer_devises(
        utilisateur=requete.user,
        project_id=project_id,
        devise_reference=champ_texte(d, "devise_reference", obligatoire=False),
        devises_autorisees=liste,
        type_taux=champ_texte(d, "type_taux", obligatoire=False),
        date_effet=champ_date(d, "date_effet"),
        motif=champ_texte(d, "motif", obligatoire=False, defaut=""),
    )
    return reponse(_version(recharge(reglage)), 201)


class ParametresOrganisation(VueMetier):
    def get(self, requete):
        jour = parametre_date(requete, "jour", obligatoire=False) or datetime.date.today()
        return reponse(_resolu(None, jour))

    def post(self, requete):
        return _poser(requete, None)


class HistoriqueOrganisation(VueMetier):
    def get(self, requete):
        versions = ParametreDevises.objects.filter(project_id__isnull=True).order_by("-version")
        return reponse([_version(v) for v in versions])


class ParametresProjet(VueMetier):
    def get(self, requete, project_id):
        objet_ou_404(Projet, pk=project_id)
        habilite(requete.user, "consulter", project_id)
        jour = parametre_date(requete, "jour", obligatoire=False) or datetime.date.today()
        return reponse(_resolu(project_id, jour))

    def post(self, requete, project_id):
        objet_ou_404(Projet, pk=project_id)
        return _poser(requete, project_id)


class HistoriqueProjet(VueMetier):
    def get(self, requete, project_id):
        objet_ou_404(Projet, pk=project_id)
        habilite(requete.user, "consulter", project_id)
        versions = ParametreDevises.objects.filter(project_id=project_id).order_by("-version")
        return reponse([_version(v) for v in versions])


class Devises(VueMetier):
    def get(self, requete):
        return reponse(
            [
                {"code": d.code, "label": d.label, "decimales": d.decimales}
                for d in Devise.objects.order_by("code")
            ]
        )
