from django.urls import include, path

urlpatterns = [
    # Accès auditeur : lecture seule, jeton à portée et durée limitées (L7-T02).
    path("auditeur/", include("niveau4_reporting.publication.urls")),
]
