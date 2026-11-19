from django.urls import path

from . import api

urlpatterns = [
    path("tableau-de-bord/", api.TableauDeBordVue.as_view()),
    path("tableau-de-bord/<str:code>/consolidation/", api.Consolidation.as_view()),
    path("projets/<uuid:project_id>/tableau-de-bord/<str:code>/detail/", api.Detail.as_view()),
    path(
        "projets/<uuid:project_id>/tableau-de-bord/<str:code>/detail/<uuid:detail_id>/ecritures/",
        api.DetailEcritures.as_view(),
    ),
    path(
        "projets/<uuid:project_id>/tableau-de-bord/ecritures/<uuid:ecriture_id>/",
        api.EcritureDuTableau.as_view(),
    ),
]
