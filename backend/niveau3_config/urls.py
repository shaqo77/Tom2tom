from django.urls import path

from . import api

urlpatterns = [
    path("projets/<uuid:project_id>/documents/", api.Documents.as_view()),
    path(
        "projets/<uuid:project_id>/documents/<uuid:document_id>/remplacement/",
        api.DocumentRemplacement.as_view(),
    ),
    path(
        "projets/<uuid:project_id>/documents/<uuid:document_id>/contenu/",
        api.DocumentContenu.as_view(),
    ),
    path(
        "projets/<uuid:project_id>/documents/<uuid:document_id>/integrite/",
        api.DocumentIntegrite.as_view(),
    ),
    path(
        "projets/<uuid:project_id>/accords/<uuid:accord_id>/profils-decaissement/",
        api.ProfilsDecaissement.as_view(),
    ),
    path(
        "projets/<uuid:project_id>/accords/<uuid:accord_id>/profils-decaissement/<uuid:profil_id>/",
        api.ProfilDecaissementDetail.as_view(),
    ),
    *(
        path(
            f"projets/<uuid:project_id>/accords/<uuid:accord_id>/profils-decaissement/<uuid:profil_id>/{fin}/",
            vue.as_view(),
        )
        for fin, vue in (
            ("valider", api.ProfilValider),
            ("activer", api.ProfilActiver),
            ("rejeter", api.ProfilRejeter),
            ("nouvelle-version", api.ProfilNouvelleVersion),
            ("comparaison", api.ProfilComparaison),
        )
    ),
]
