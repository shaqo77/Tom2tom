from django.urls import path

from . import api

urlpatterns = [
    path("bailleurs/", api.Bailleurs.as_view()),
    path("projets/<uuid:project_id>/accords/", api.Accords.as_view()),
    path("projets/<uuid:project_id>/accords/<uuid:accord_id>/", api.AccordDetail.as_view()),
    path("projets/<uuid:project_id>/accords/<uuid:accord_id>/statut/", api.AccordStatut.as_view()),
    path(
        "projets/<uuid:project_id>/accords/<uuid:accord_id>/numerotation/",
        api.AccordNumerotation.as_view(),
    ),
    path(
        "projets/<uuid:project_id>/accords/<uuid:accord_id>/categories/",
        api.AccordCategories.as_view(),
    ),
    path(
        "projets/<uuid:project_id>/accords/<uuid:accord_id>/avenants/", api.AccordAvenants.as_view()
    ),
    path("projets/<uuid:project_id>/cles-cofinancement/", api.Cles.as_view()),
    path("projets/<uuid:project_id>/cles-cofinancement/<uuid:cle_id>/", api.CleDetail.as_view()),
    path(
        "projets/<uuid:project_id>/cles-cofinancement/<uuid:cle_id>/versions/",
        api.CleVersions.as_view(),
    ),
]
