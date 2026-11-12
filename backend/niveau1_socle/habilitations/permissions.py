"""Vérification des habilitations, au serveur, sur chaque requête.

L'interface masque, elle ne protège pas. Le défaut est la FERMETURE : une vue
qui oublie de déclarer son opération, un compte de plateforme (même
superutilisateur) ou un utilisateur sans habilitation sont refusés.
"""

from rest_framework.permissions import BasePermission

from .models import OPERATIONS, Habilitation


def est_habilite(utilisateur, operation: str, project_id, site: str | None = None) -> bool:
    """Vrai si une habilitation de l'utilisateur couvre l'opération sur ce projet et ce site.

    Sans site demandé, seule une habilitation « tous sites » couvre le projet
    entier. Les habilitations sont lues sous la RLS de l'organisation courante :
    une habilitation d'une autre organisation n'est jamais visible.
    """
    if operation not in OPERATIONS:
        raise ValueError(f"opération inconnue : {operation!r}")
    if not getattr(utilisateur, "is_authenticated", False) or not getattr(
        utilisateur, "org_id", None
    ):
        return False
    habilitations = Habilitation.objects.filter(
        user_id=utilisateur.id,
        project_id=project_id,
        role__operations__contains=[operation],
    )
    if site is None:
        habilitations = habilitations.filter(site__isnull=True)
    else:
        habilitations = habilitations.filter(site__isnull=True) | habilitations.filter(site=site)
    return habilitations.exists()


class HabilitationRequise(BasePermission):
    """Exige l'opération `view.operation` sur le projet de l'URL (`project_id`, `site`)."""

    message = "Vous n'êtes pas habilité pour cette opération sur ce projet."

    def has_permission(self, request, view) -> bool:
        operation = getattr(view, "operation", None)
        project_id = view.kwargs.get("project_id")
        if operation is None or project_id is None:
            return False
        return est_habilite(request.user, operation, project_id, view.kwargs.get("site"))
