"""L'API de session du frontend : jeton CSRF, connexion, « moi », langue, déconnexion. Voir F1.

Authentification par SESSION (cookie HttpOnly), jamais par jeton stocké dans le navigateur. Le CSRF
est contrôlé partout, la connexion comprise (contre la connexion forcée). Un identifiant inconnu,
un mauvais mot de passe et un compte désactivé donnent EXACTEMENT la même réponse.

« Moi » dit ce que l'interface doit MASQUER ou montrer ; le serveur revérifie chaque action
(l'interface masque, elle ne protège pas).
"""

from django.contrib.auth import authenticate, login, logout
from django.db import connection
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api import champ_texte, corps, reponse
from core.i18n import msg
from core.metier import refuser
from niveau1_socle.habilitations.models import OPERATIONS, Habilitation

from .models import Organisation, Projet

LANGUES = ("fr", "en")


def _ordonner(operations) -> list[str]:
    """Les opérations dans l'ordre canonique du produit, sans doublon."""
    return sorted(set(operations), key=OPERATIONS.index)


def _poser_perimetre(utilisateur) -> None:
    """Pose l'organisation de CE compte pour la transaction en cours.

    Nécessaire à la connexion : au moment où la requête arrive, le compte n'est pas encore connu
    du middleware d'isolation. Valable pour la seule transaction (`set_config(..., true)`).
    """
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.org_id', %s, true)", [str(utilisateur.org_id)])


def profil(utilisateur) -> dict:
    """Qui est connecté, dans quelle organisation, avec quelles opérations sur quels projets."""
    organisation = None
    projets = []
    if utilisateur.org_id:
        _poser_perimetre(utilisateur)
        o = Organisation.objects.get(pk=utilisateur.org_id)
        organisation = {
            "id": o.id,
            "code": o.code,
            "raison_sociale": o.raison_sociale,
            "monnaie_tenue": o.monnaie_tenue,
            "langues_actives": o.langues_actives,
        }
        tous: dict = {}
        par_site: dict = {}
        habilitations = Habilitation.objects.filter(user_id=utilisateur.id).select_related("role")
        for h in habilitations:
            tous.setdefault(h.project_id, [])
            par_site.setdefault(h.project_id, {})
            if h.site is None:
                tous[h.project_id] += h.role.operations
            else:
                par_site[h.project_id].setdefault(h.site, []).extend(h.role.operations)
        for projet in Projet.objects.filter(pk__in=list(tous)).order_by("code"):
            projets.append(
                {
                    "id": projet.id,
                    "code": projet.code,
                    "libelle": projet.label,
                    "statut": projet.status,
                    "operations": _ordonner(tous[projet.id]),
                    "operations_par_site": {
                        site: _ordonner(ops) for site, ops in par_site[projet.id].items()
                    },
                }
            )
    return {
        "id": utilisateur.id,
        "identifiant": utilisateur.username,
        "nom_complet": utilisateur.get_full_name() or utilisateur.username,
        "langue": utilisateur.langue,
        "organisation": organisation,
        "projets": projets,
    }


def _non_authentifie() -> Response:
    return Response(
        {"code": "NON_AUTHENTIFIE", "message": str(msg("session.non_authentifie"))}, status=401
    )


class Csrf(APIView):
    """Rend le jeton CSRF (`get_token` pose aussi le cookie) : à rejouer dans `X-CSRFToken`."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, requete):
        return reponse({"csrf": get_token(requete._request)})


@method_decorator(csrf_protect, name="dispatch")
class Connexion(APIView):
    authentication_classes: list = []  # le CSRF est contrôlé par `csrf_protect`, anonyme compris
    permission_classes = [AllowAny]

    def post(self, requete):
        donnees = corps(requete)
        identifiant = champ_texte(donnees, "identifiant")
        mot_de_passe = champ_texte(donnees, "mot_de_passe")
        utilisateur = authenticate(requete._request, username=identifiant, password=mot_de_passe)
        if utilisateur is None:
            return Response(
                {
                    "code": "IDENTIFIANTS_INVALIDES",
                    "message": str(msg("session.identifiants_invalides")),
                },
                status=401,
            )
        login(requete._request, utilisateur)  # change l'identifiant de session
        return reponse(profil(utilisateur))


class Moi(APIView):
    permission_classes = [AllowAny]  # un visiteur reçoit un 401 lisible, pas un 403 muet

    def get(self, requete):
        if not requete.user.is_authenticated:
            return _non_authentifie()
        return reponse(profil(requete.user))

    def patch(self, requete):
        if not requete.user.is_authenticated:
            return _non_authentifie()
        langue = champ_texte(corps(requete), "langue")
        if langue not in LANGUES:
            refuser("session.langue_non_geree", langue=langue)
        requete.user.langue = langue
        requete.user.save(update_fields=["langue"])
        return reponse(profil(requete.user))


class Deconnexion(APIView):
    permission_classes = [AllowAny]

    def post(self, requete):
        if requete.user.is_authenticated:
            logout(requete._request)
        return Response(status=204)
