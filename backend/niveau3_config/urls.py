from django.urls import path

from . import api

urlpatterns = [
    path("projets/<uuid:project_id>/documents/", api.Documents.as_view()),
    path(
        "projets/<uuid:project_id>/documents/<uuid:document_id>/remplacement/",
        api.DocumentRemplacement.as_view(),
    ),
    path(
        "projets/<uuid:project_id>/documents/<uuid:document_id>/integrite/",
        api.DocumentIntegrite.as_view(),
    ),
]
