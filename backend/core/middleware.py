"""Pose app.org_id pour la transaction de la requête. Voir §B.4 du guide."""

from django.db import connection


class OrganisationScopeMiddleware:
    """ATOMIC_REQUESTS=True garantit qu'une transaction est ouverte.

    SET LOCAL ne survit pas à la transaction, ce qui est exactement voulu :
    un SET simple persisterait sur la connexion réutilisée et la requête
    suivante, servie à un AUTRE utilisateur, hériterait de l'organisation
    précédente.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        org_id = getattr(getattr(request, "user", None), "org_id", None)
        if org_id:
            with connection.cursor() as cur:
                cur.execute("SET LOCAL app.org_id = %s", [str(org_id)])
        return self.get_response(request)
