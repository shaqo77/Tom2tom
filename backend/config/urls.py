from django.urls import include, path

urlpatterns = [
    # Téléchargement d'un export complet par lien signé à durée limitée (L8-T03).
    path("export/", include("niveau1_socle.reversibilite.urls")),
    # Accès auditeur : lecture seule, jeton à portée et durée limitées (L7-T02).
    path("auditeur/", include("niveau4_reporting.publication.urls")),
]
