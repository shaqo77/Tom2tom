from django.urls import path

from . import api

urlpatterns = [
    path("projets/<uuid:project_id>/ecritures/", api.Ecritures.as_view()),
    path("projets/<uuid:project_id>/ecritures/<uuid:ecriture_id>/", api.EcritureDetail.as_view()),
    path(
        "projets/<uuid:project_id>/ecritures/<uuid:ecriture_id>/valider/",
        api.EcritureValider.as_view(),
    ),
    path(
        "projets/<uuid:project_id>/ecritures/<uuid:ecriture_id>/comptabiliser/",
        api.EcritureComptabiliser.as_view(),
    ),
]
