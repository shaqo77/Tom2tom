"""Pose app.org_id pour la transaction de la requête. Voir §B.4 du guide."""

from django.db import connection, transaction


class OrganisationScopeMiddleware:
    """Ouvre la transaction de la requête et y pose l'organisation courante.

    SET LOCAL ne survit pas à la transaction, ce qui est exactement voulu :
    un SET simple persisterait sur la connexion réutilisée et la requête
    suivante, servie à un AUTRE utilisateur, hériterait de l'organisation
    précédente.

    Mais encore faut-il qu'une transaction soit ouverte. ATOMIC_REQUESTS
    n'enveloppe QUE la vue — « make_view_atomic » ne wrappe rien d'autre —
    et les middlewares s'exécutent en dehors. Un SET LOCAL posé ici sans
    transaction explicite part donc en mode autocommit, où PostgreSQL le
    jette : la vue ne verrait aucune organisation, donc aucune ligne.

    On ouvre donc la transaction nous-mêmes, au-dessus de la vue. Celle
    d'ATOMIC_REQUESTS devient un point de sauvegarde imbriqué, et le
    périmètre posé ici vaut pour toute la requête.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        org_id = getattr(getattr(request, "user", None), "org_id", None)
        if not org_id:
            # Sans organisation, rien n'est posé : les politiques d'isolation
            # ne laissent alors rien passer. C'est le défaut sûr.
            return self.get_response(request)
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("SET LOCAL app.org_id = %s", [str(org_id)])
            return self.get_response(request)
