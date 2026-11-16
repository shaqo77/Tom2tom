from django.urls import path

from . import vues_auditeur as v

urlpatterns = [
    path("projets/<uuid:project_id>/rapports/", v.RapportsPublies.as_view()),
    path("projets/<uuid:project_id>/rapports/<uuid:rapport_id>/", v.RapportPublie_.as_view()),
    path(
        "projets/<uuid:project_id>/rapports/<uuid:rapport_id>/dossier/",
        v.DossierDeConformite.as_view(),
    ),
    path(
        "projets/<uuid:project_id>/rapports/<uuid:rapport_id>/fichiers/<uuid:fichier_id>/",
        v.FichierExporte.as_view(),
    ),
    path(
        "projets/<uuid:project_id>/rapports/<uuid:rapport_id>/cellules/<str:rubrique>/<str:colonne>/",
        v.CelluleDescente.as_view(),
    ),
    path("projets/<uuid:project_id>/ecritures/<uuid:ecriture_id>/", v.EcritureDescente.as_view()),
    path(
        "projets/<uuid:project_id>/ecritures/<uuid:ecriture_id>/pieces/<uuid:piece_id>/",
        v.PieceScan.as_view(),
    ),
]
