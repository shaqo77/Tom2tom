from django.urls import path

from . import api

urlpatterns = [
    path("projets/<uuid:project_id>/controles/", api.Controles.as_view()),
    path("projets/<uuid:project_id>/controles/bibliotheque/", api.Bibliotheque.as_view()),
    path(
        "projets/<uuid:project_id>/controles/bibliotheque/installer/",
        api.BibliothequeInstaller.as_view(),
    ),
    path("projets/<uuid:project_id>/controles/<uuid:controle_id>/", api.ControleDetail.as_view()),
    *(
        path(
            f"projets/<uuid:project_id>/controles/<uuid:controle_id>/{fin}/",
            vue.as_view(),
        )
        for fin, vue in (
            ("valider", api.ControleValider),
            ("activer", api.ControleActiver),
            ("rejeter", api.ControleRejeter),
        )
    ),
]
