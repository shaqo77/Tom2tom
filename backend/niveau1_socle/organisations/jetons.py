"""Le jeton d'API : un programme appelle l'API sans mot de passe, avec les droits de son
propriétaire.

Le jeton a la forme `<organisation>.<secret>`, comme l'accès auditeur. L'organisation figure en
clair parce que la recherche se fait SOUS l'isolation par organisation (aucune exception à la RLS) :
on pose cette organisation pour la transaction, PUIS on cherche les jetons dont le préfixe
correspond et on compare l'empreinte SHA-256 du secret en temps constant. Le secret n'est jamais
stocké.

401 : jeton absent du schéma `Bearer`, mal formé, inconnu, expiré, révoqué, ou propriétaire inactif.
Un jeton n'élargit jamais les droits : l'utilisateur authentifié est son propriétaire, et
chaque service contrôle ses habilitations comme pour une session. Pas de CSRF : aucun cookie
n'intervient.
"""

import datetime
import hashlib
import hmac
import secrets
import uuid

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg

from .models import JetonApi

MOT_CLE = "Bearer"
DUREE_MAX_JOURS = 365
LIBELLE_MAX = 200
SECRET_MAX = 200
USAGE_AU_PLUS_TOUTES = datetime.timedelta(seconds=60)


def maintenant() -> datetime.datetime:
    return timezone.now()


def _empreinte(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


# --- créer, révoquer, lister (par le propriétaire, en session) -------------------------------


def creer_jeton(*, utilisateur, libelle, duree_jours) -> tuple[JetonApi, str]:
    """Crée un jeton pour `utilisateur` et rend `(jeton, jeton en clair)`. Il ne se relit plus."""
    if utilisateur.org_id is None:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("jetons.compte_sans_organisation"))
    libelle = (libelle or "").strip() if isinstance(libelle, str) else ""
    if not libelle or len(libelle) > LIBELLE_MAX:
        raise ErreurMetier(
            CodeErreur.REGLE_INVALIDE, msg("jetons.libelle_invalide", maximum=LIBELLE_MAX)
        )
    if (
        isinstance(duree_jours, bool)
        or not isinstance(duree_jours, int)
        or not 1 <= duree_jours <= DUREE_MAX_JOURS
    ):
        raise ErreurMetier(
            CodeErreur.REGLE_INVALIDE, msg("jetons.duree_limitee", maximum=DUREE_MAX_JOURS)
        )
    secret = secrets.token_urlsafe(32)
    with transaction.atomic():
        jeton = JetonApi.objects.create(
            org_id=utilisateur.org_id,
            utilisateur=utilisateur,
            libelle=libelle,
            prefixe=secret[:8],
            empreinte=_empreinte(secret),
            expire_le=maintenant() + datetime.timedelta(days=duree_jours),
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=jeton.org_id,
            actor_id=utilisateur.id,
            action="api_token_created",
            object_type="jeton_api",
            object_id=jeton.id,
            after={
                "libelle": jeton.libelle,
                "prefixe": jeton.prefixe,
                "expire_le": jeton.expire_le.isoformat(),
            },
        )
    return jeton, f"{utilisateur.org_id}.{secret}"


def revoquer_jeton(*, utilisateur, jeton: JetonApi) -> JetonApi:
    """Révoque un jeton ; sans effet s'il l'est déjà. Seul son propriétaire peut le faire."""
    with transaction.atomic():
        courant = JetonApi.objects.select_for_update().get(pk=jeton.pk)
        if courant.utilisateur_id != utilisateur.id:
            raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("jetons.jeton_d_un_autre"))
        if courant.revoque_le is not None:
            return courant
        courant.revoque_le = maintenant()
        courant.save(update_fields=["revoque_le", "updated_at"])
        journaliser(
            org_id=courant.org_id,
            actor_id=utilisateur.id,
            action="api_token_revoked",
            object_type="jeton_api",
            object_id=courant.id,
            after={"libelle": courant.libelle, "prefixe": courant.prefixe},
        )
    return courant


def jetons_de(utilisateur):
    """Les jetons de cette personne, les plus récents d'abord (ordre stable)."""
    return JetonApi.objects.filter(utilisateur_id=utilisateur.id).order_by("-created_at", "id")


# --- l'authentification DRF ----------------------------------------------------------------------


def _refuser(cle: str):
    raise AuthenticationFailed(msg(cle))


class AuthentificationJeton(BaseAuthentication):
    """`Authorization: Bearer <organisation>.<secret>` → le propriétaire du jeton, ou 401.

    Sans en-tête `Bearer`, cette classe n'a pas son mot à dire (`None`) : la session ou l'absence
    d'authentification se règlent comme avant.
    """

    def authenticate_header(self, request) -> str:
        return MOT_CLE

    def authenticate(self, request):
        valeur = request.META.get("HTTP_AUTHORIZATION", "")
        mot, _, jeton = valeur.partition(" ")
        if mot.lower() != MOT_CLE.lower():
            return None
        organisation, point, secret = jeton.strip().partition(".")
        try:
            organisation = uuid.UUID(organisation)
        except ValueError:
            organisation = None
        if (
            organisation is None
            or not point
            or not secret
            or len(secret) > SECRET_MAX
            or not secret.isascii()
        ):
            _refuser("jetons.jeton_invalide")
        with connection.cursor() as cur:  # valable pour la transaction de la vue
            cur.execute("SELECT set_config('app.org_id', %s, true)", [str(organisation)])
        empreinte = _empreinte(secret)
        trouve = None
        for candidat in JetonApi.objects.filter(prefixe=secret[:8]).select_related("utilisateur"):
            if hmac.compare_digest(bytes(candidat.empreinte), empreinte):
                trouve = candidat
        if trouve is None:
            _refuser("jetons.jeton_invalide")
        if trouve.revoque_le is not None:
            _refuser("jetons.jeton_revoque")
        maintenant_ = maintenant()
        if trouve.expire_le <= maintenant_:
            _refuser("jetons.jeton_expire")
        proprietaire = trouve.utilisateur
        if not proprietaire.is_active or proprietaire.org_id != trouve.org_id:
            _refuser("jetons.jeton_invalide")
        if (
            trouve.dernier_usage is None
            or maintenant_ - trouve.dernier_usage >= USAGE_AU_PLUS_TOUTES
        ):
            JetonApi.objects.filter(pk=trouve.pk).update(dernier_usage=maintenant_)
        return proprietaire, trouve
