"""L'API HTTP des demandes de retrait : la liste d'un projet, de quoi choisir une demande dans
un écran (justification du compte spécial, par exemple). Lecture seule ; montants en chaînes."""

from core.api import VueMetier, projeter, reponse_liste
from core.metier import habilite

from .models import DemandeRetrait, StatutDemande


def _demande(d: DemandeRetrait) -> dict:
    return projeter(
        d,
        "id",
        "numero",
        "type",
        "periode_debut",
        "periode_fin",
        "montant_total",
        statut=d.status,
        accord=d.accord.numero,
    )


class DemandesRetrait(VueMetier):
    def get(self, requete, project_id):
        habilite(requete.user, "consulter", project_id)
        demandes = DemandeRetrait.objects.filter(project_id=project_id).select_related("accord")
        statut = requete.query_params.get("statut")
        if statut in StatutDemande.values:
            demandes = demandes.filter(status=statut)
        accord = requete.query_params.get("accord")
        if accord:
            demandes = demandes.filter(accord__numero=accord)
        return reponse_liste(requete, demandes.order_by("-periode_fin", "numero", "id"), _demande)
