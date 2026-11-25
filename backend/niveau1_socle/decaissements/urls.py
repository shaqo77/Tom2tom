from django.urls import path

from . import api

urlpatterns = [
    path("projets/<uuid:project_id>/demandes-retrait/", api.DemandesRetrait.as_view()),
]
