from django.urls import path

from . import api

urlpatterns = [
    path("projets/<uuid:project_id>/disponibilites/", api.Disponibilites.as_view()),
    path("projets/<uuid:project_id>/previsions/", api.Previsions.as_view()),
    path("comptes/<uuid:compte_id>/soldes/", api.ComptesSoldes.as_view()),
    path("comptes/<uuid:compte_id>/releves/", api.ComptesReleves.as_view()),
    path("comptes/<uuid:compte_id>/reconstitution/", api.ComptesReconstitution.as_view()),
    path("comptes/<uuid:compte_id>/justifications/", api.ComptesJustifications.as_view()),
    path("comptes/<uuid:compte_id>/rapport/", api.ComptesRapport.as_view()),
    path("mouvements/<uuid:mouvement_id>/appariement/", api.MouvementAppariement.as_view()),
    path("appariements/<uuid:appariement_id>/annulation/", api.AppariementAnnulation.as_view()),
]
