"""Le type de demande BAD, DÉDUIT de ce que l'application sait (plan 07 §7.0).

Dans l'application, `reapprovisionnement` veut dire « remboursement » et `retrait` veut dire
« avance » : on n'ajoute pas de vocabulaire BAD au modèle. Première avance d'un accord = « avance
initiale », les suivantes = « reconstitution ». Un cas qu'on ne peut pas trancher est REFUSÉ,
jamais deviné.
"""

from niveau1_socle.decaissements.models import DemandeRetrait, StatutDemande, TypeDemande

REMBOURSEMENT = "reimbursement"
AVANCE_INITIALE = "special_account_initial_advance"
RECONSTITUTION = "special_account_replenishment"
PAIEMENT_DIRECT = "direct_payment"
TYPES_BAD = (REMBOURSEMENT, AVANCE_INITIALE, RECONSTITUTION, PAIEMENT_DIRECT)

# Les demandes qui comptent comme « déjà adressées à la Banque ».
VIVANTES = (
    StatutDemande.SOUMISE,
    StatutDemande.ACCEPTEE,
    StatutDemande.CONTESTEE,
    StatutDemande.REMBOURSEE,
)


class TypeBadIndeterminable(ValueError):
    """Le type BAD de la demande ne se déduit pas : on refuse plutôt que de le deviner."""

    def __init__(self, cle: str, **params):
        self.cle = cle
        self.params = params
        super().__init__(cle)


def type_bad(demande: DemandeRetrait) -> str:
    if demande.type == TypeDemande.REAPPROVISIONNEMENT:
        return REMBOURSEMENT
    if demande.type == TypeDemande.PAIEMENT_DIRECT:
        return PAIEMENT_DIRECT
    if demande.type != TypeDemande.RETRAIT:
        raise TypeBadIndeterminable("formats_bailleur.type_sans_equivalent", type=demande.type)
    avant = DemandeRetrait.objects.filter(
        accord_id=demande.accord_id, type=TypeDemande.RETRAIT, created_at__lt=demande.created_at
    ).exclude(pk=demande.pk)
    if avant.filter(status=StatutDemande.PREPAREE).exists():
        # Une avance antérieure n'est pas soumise : laquelle est la première ? On ne devine pas.
        raise TypeBadIndeterminable("formats_bailleur.avance_anterieure_non_soumise")
    return RECONSTITUTION if avant.filter(status__in=VIVANTES).exists() else AVANCE_INITIALE
