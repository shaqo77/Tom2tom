from django.urls import include, path

urlpatterns = [
    # API métier (L9) : plan de passation, avis, contrats, décomptes, trésorerie.
    path("api/v1/", include("niveau1_socle.organisations.urls")),
    path("api/v1/", include("niveau1_socle.marches.urls")),
    path("api/v1/", include("niveau1_socle.tresorerie.urls")),
    path("api/v1/", include("niveau1_socle.referentiels.urls")),
    path("api/v1/", include("niveau1_socle.financements.urls")),
    path("api/v1/", include("niveau3_config.urls")),
    path("api/v1/", include("niveau4_reporting.tableau_de_bord.urls")),
    # Téléchargement d'un export complet par lien signé à durée limitée (L8-T03).
    path("export/", include("niveau1_socle.reversibilite.urls")),
    # Accès auditeur : lecture seule, jeton à portée et durée limitées (L7-T02).
    path("auditeur/", include("niveau4_reporting.publication.urls")),
]
