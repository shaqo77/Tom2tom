"""L'API HTTP du gabarit de décaissement d'un profil de bailleur livré. Voir L11-D2.

Lecture seule (habilitation `consulter`) : le gabarit ne crée aucune donnée, il prépare le corps
d'un profil de décaissement que l'administrateur relit et soumet à l'API de B4.
"""

from django.http import Http404

from core.api import VueMetier, parametre_date, reponse
from core.i18n import langue_courante
from core.metier import habilite

from .services.catalogue import profils_livres
from .services.gabarit import gabarit_decaissement


class GabaritDecaissement(VueMetier):
    def get(self, requete, project_id, nom):
        habilite(requete.user, "consulter", project_id)
        if nom not in profils_livres():  # liste blanche : un nom reçu n'est jamais un chemin
            raise Http404
        return reponse(
            gabarit_decaissement(
                nom,
                date_cloture=parametre_date(requete, "date_cloture"),
                date_eligibilite=parametre_date(requete, "date_eligibilite", obligatoire=False),
                libelle_langue=langue_courante(),
            )
        )
