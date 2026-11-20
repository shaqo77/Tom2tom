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
    path("projets/<uuid:project_id>/evaluations-controles/", api.Evaluations.as_view()),
    path(
        "projets/<uuid:project_id>/evaluations-controles/<uuid:evaluation_id>/",
        api.EvaluationDetail.as_view(),
    ),
    *(
        path(
            f"projets/<uuid:project_id>/evaluations-controles/<uuid:evaluation_id>/{fin}/",
            vue.as_view(),
        )
        for fin, vue in (
            ("decision", api.EvaluationDecision),
            ("justification", api.EvaluationJustification),
            ("derogation", api.EvaluationDerogation),
        )
    ),
    path("projets/<uuid:project_id>/derogations/", api.Derogations.as_view()),
    path(
        "projets/<uuid:project_id>/derogations/<uuid:derogation_id>/decision/",
        api.DerogationDecision.as_view(),
    ),
    path("projets/<uuid:project_id>/controles-en-attente/", api.ControlesEnAttente.as_view()),
    path(
        "projets/<uuid:project_id>/dossier-conformite-objet/", api.DossierConformiteObjet.as_view()
    ),
]
