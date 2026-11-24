from django.urls import path

from . import api

urlpatterns = [
    path("session/csrf/", api.Csrf.as_view()),
    path("session/connexion/", api.Connexion.as_view()),
    path("session/moi/", api.Moi.as_view()),
    path("session/mot-de-passe/", api.MotDePasse.as_view()),
    path("session/deconnexion/", api.Deconnexion.as_view()),
    path("jetons/", api.Jetons.as_view()),
    path("jetons/<uuid:jeton_id>/revocation/", api.RevocationJeton.as_view()),
]
