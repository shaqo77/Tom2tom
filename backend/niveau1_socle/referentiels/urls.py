from django.urls import path

from . import api

urlpatterns = [
    path("devises/", api.Devises.as_view()),
    path("parametres-devises/", api.ParametresOrganisation.as_view()),
    path("parametres-devises/historique/", api.HistoriqueOrganisation.as_view()),
    path("projets/<uuid:project_id>/parametres-devises/", api.ParametresProjet.as_view()),
    path(
        "projets/<uuid:project_id>/parametres-devises/historique/", api.HistoriqueProjet.as_view()
    ),
]
