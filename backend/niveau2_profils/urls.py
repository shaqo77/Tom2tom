from django.urls import path

from . import api

urlpatterns = [
    path(
        "projets/<uuid:project_id>/profils-bailleurs/<str:nom>/gabarit-decaissement/",
        api.GabaritDecaissement.as_view(),
    ),
]
