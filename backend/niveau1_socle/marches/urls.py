from django.urls import path

from . import api

urlpatterns = [
    path("projets/<uuid:project_id>/methodes/", api.Methodes.as_view()),
    path("projets/<uuid:project_id>/plans/", api.Plans.as_view()),
    path("projets/<uuid:project_id>/retards/", api.Retards.as_view()),
    path("projets/<uuid:project_id>/avis-en-attente/", api.AvisEnAttente.as_view()),
    path("projets/<uuid:project_id>/alertes/", api.Alertes.as_view()),
    path("plans/<uuid:plan_id>/", api.PlanDetail.as_view()),
    path("plans/<uuid:plan_id>/lignes/", api.LignesDuPlan.as_view()),
    path("lignes/<uuid:ligne_id>/", api.LigneDetail.as_view()),
    path("lignes/<uuid:ligne_id>/avancer/", api.LigneAvancer.as_view()),
    path("lignes/<uuid:ligne_id>/replanifier/", api.LigneReplanifier.as_view()),
    path("lignes/<uuid:ligne_id>/modifier/", api.LigneModifier.as_view()),
    path("lignes/<uuid:ligne_id>/avis/", api.AvisDeLaLigne.as_view()),
    path("lignes/<uuid:ligne_id>/contrat/", api.ContratDeLaLigne.as_view()),
    path("avis/<uuid:avis_id>/", api.AvisDetail.as_view()),
    path("avis/<uuid:avis_id>/decision/", api.AvisDecision.as_view()),
    path("avis/<uuid:avis_id>/pieces/", api.AvisPieces.as_view()),
    path("contrats/<uuid:contrat_id>/", api.ContratDetail.as_view()),
    path("contrats/<uuid:contrat_id>/avenants/", api.ContratAvenants.as_view()),
    path("contrats/<uuid:contrat_id>/garanties/", api.ContratGaranties.as_view()),
    path("contrats/<uuid:contrat_id>/decomptes/", api.ContratDecomptes.as_view()),
    path("contrats/<uuid:contrat_id>/situation/", api.ContratSituation.as_view()),
    path("garanties/<uuid:garantie_id>/cloture/", api.GarantieCloture.as_view()),
    path("decomptes/<uuid:decompte_id>/", api.DecompteDetail.as_view()),
    path("decomptes/<uuid:decompte_id>/certifier/", api.DecompteCertifier.as_view()),
    path("decomptes/<uuid:decompte_id>/rejeter/", api.DecompteRejeter.as_view()),
    path("decomptes/<uuid:decompte_id>/paiements/", api.DecomptePaiements.as_view()),
]
