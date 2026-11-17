"""Le refus CSRF de l'API, lisible par le frontend. Voir F3.

Django répond à un jeton CSRF absent ou périmé par une page HTML. Une interface qui appelle l'API
a besoin du même format que pour toute autre erreur : `{"code", "message"}`, avec un code stable
(`CSRF_INVALIDE`) d'après lequel elle peut redemander un jeton et rejouer la requête.
"""

from django.http import JsonResponse
from django.views.csrf import csrf_failure

from core.i18n import msg


def refus_csrf(requete, reason="", template_name=""):
    if requete.path.startswith("/api/"):
        return JsonResponse(
            {"code": "CSRF_INVALIDE", "message": str(msg("session.csrf_invalide"))}, status=403
        )
    return csrf_failure(requete, reason=reason)
