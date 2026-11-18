from django.urls import path

from . import api

urlpatterns = [
    path("projets/<uuid:project_id>/cles-cofinancement/", api.Cles.as_view()),
    path("projets/<uuid:project_id>/cles-cofinancement/<uuid:cle_id>/", api.CleDetail.as_view()),
    path(
        "projets/<uuid:project_id>/cles-cofinancement/<uuid:cle_id>/versions/",
        api.CleVersions.as_view(),
    ),
]
