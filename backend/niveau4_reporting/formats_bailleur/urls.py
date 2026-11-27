from django.urls import path

from . import api

urlpatterns = [
    path(
        "projets/<uuid:project_id>/demandes-retrait/<uuid:demande_id>/export/<str:nom_format>/",
        api.DemandeExport.as_view(),
    ),
]
