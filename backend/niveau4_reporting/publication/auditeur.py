"""L'accès auditeur : un jeton à portée et à durée limitées, en lecture seule. Voir L7-T02.

Le jeton a la forme `<organisation>.<secret>`. L'organisation figure en clair parce que la
recherche de l'accès se fait SOUS l'isolation par organisation (aucune exception à la RLS) : on
pose cette organisation pour la transaction, puis on cherche le SHA-256 du secret. Une organisation
devinée ne trouve rien ; un secret faux ne trouve rien. Le jeton lui-même n'est jamais stocké.

401 : jeton absent, mal formé, inconnu, expiré ou révoqué (partout, sans exception).
403 : jeton valable, mais projet hors de ses projets nommés, ou méthode d'écriture.
"""

import datetime
import hashlib
import secrets
import uuid

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from core.models import AuditLog
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.organisations.models import Projet

from .models import AccesAuditeur

DUREE_MAX_JOURS = 90
MOT_CLE = "Auditeur"
ACTIONS_JOURNAL = ("auditor_access_granted", "auditor_access_revoked", "auditor_consulted")


def maintenant() -> datetime.datetime:
    return timezone.now()


def _hash(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


# --- créer et révoquer un accès (par l'organisation) -----------------------------------------


def creer_acces_auditeur(
    *,
    utilisateur,
    nom: str,
    project_ids: list,
    period_from: datetime.date,
    period_to: datetime.date,
    duree_jours: int,
) -> tuple[AccesAuditeur, str]:
    """Crée l'accès et rend `(accès, jeton en clair)`. Le jeton ne se relit plus jamais."""
    if not (nom or "").strip():
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("auditeur.nom_obligatoire"))
    projets = sorted({str(p) for p in project_ids})
    if not projets:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("auditeur.projets_obligatoires"))
    if not 1 <= duree_jours <= DUREE_MAX_JOURS:
        raise ErreurMetier(
            CodeErreur.REGLE_INVALIDE, msg("auditeur.duree_limitee", maximum=DUREE_MAX_JOURS)
        )
    if period_from > period_to:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("auditeur.plage_vide"))
    for projet in projets:
        if not est_habilite(utilisateur, "parametrer", projet):
            raise PermissionDenied(msg("auditeur.habilitation_requise"))
    if Projet.objects.filter(pk__in=projets).count() != len(projets):
        raise ErreurMetier(CodeErreur.ACCES_PROJET_REFUSE, msg("auditeur.projet_introuvable"))
    secret = secrets.token_urlsafe(32)
    with transaction.atomic():
        acces = AccesAuditeur.objects.create(
            org_id=utilisateur.org_id,
            nom=nom.strip(),
            project_ids=projets,
            period_from=period_from,
            period_to=period_to,
            jeton_hash=_hash(secret),
            expire_le=maintenant() + datetime.timedelta(days=duree_jours),
            cree_par=utilisateur.id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=acces.org_id,
            actor_id=utilisateur.id,
            action="auditor_access_granted",
            object_type="acces_auditeur",
            object_id=acces.id,
            after={
                "nom": acces.nom,
                "projets": projets,
                "du": period_from.isoformat(),
                "au": period_to.isoformat(),
                "expire_le": acces.expire_le.isoformat(),
            },
        )
    return acces, f"{utilisateur.org_id}.{secret}"


def revoquer_acces_auditeur(*, utilisateur, acces: AccesAuditeur) -> AccesAuditeur:
    for projet in acces.project_ids:
        if not est_habilite(utilisateur, "parametrer", projet):
            raise PermissionDenied(msg("auditeur.habilitation_requise"))
    with transaction.atomic():
        courant = AccesAuditeur.objects.select_for_update().get(pk=acces.pk)
        if courant.revoque_le is not None:
            return courant
        courant.revoque_le = maintenant()
        courant.revoque_par = utilisateur.id
        courant.save(update_fields=["revoque_le", "revoque_par", "updated_at"])
        journaliser(
            org_id=courant.org_id,
            actor_id=utilisateur.id,
            action="auditor_access_revoked",
            object_type="acces_auditeur",
            object_id=courant.id,
            after={"nom": courant.nom, "projets": courant.project_ids},
        )
    return courant


def journal_des_acces(*, utilisateur, project_id) -> list[AuditLog]:
    """Les accès et consultations des auditeurs sur ce projet, pour l'organisation. Plus récents
    d'abord."""
    if not est_habilite(utilisateur, "parametrer", project_id):
        raise PermissionDenied(msg("auditeur.habilitation_requise"))
    # Les consultations portent le projet ; l'octroi et la révocation, qui peuvent viser plusieurs
    # projets, le portent dans leur liste « projets ».
    return list(
        AuditLog.objects.filter(
            Q(project_id=project_id)
            | Q(
                action__in=("auditor_access_granted", "auditor_access_revoked"),
                after__projets__contains=[str(project_id)],
            ),
            action__in=ACTIONS_JOURNAL,
        ).order_by("-id")
    )


# --- l'authentification et les permissions DRF ------------------------------------------------


class Auditeur:
    """L'« utilisateur » d'une requête authentifiée par jeton : aucun compte, aucune écriture."""

    is_authenticated = True
    is_anonymous = False
    is_active = True
    langue = None

    def __init__(self, acces: AccesAuditeur):
        self.acces = acces
        self.pk = self.id = acces.id
        self.org_id = acces.org_id

    def get_username(self) -> str:
        return f"auditeur:{self.acces.nom}"


class AuthentificationAuditeur(BaseAuthentication):
    """`Authorization: Auditeur <organisation>.<secret>` → un `Auditeur`, ou 401."""

    def authenticate_header(self, request) -> str:
        return MOT_CLE

    def authenticate(self, request):
        valeur = request.META.get("HTTP_AUTHORIZATION", "")
        mot, _, jeton = valeur.partition(" ")
        if mot != MOT_CLE:
            return None  # pas notre schéma : DRF répondra 401 faute d'authentification
        organisation, point, secret = jeton.strip().partition(".")
        try:
            organisation = uuid.UUID(organisation)
        except ValueError:
            organisation = None
        if organisation is None or not point or not secret:
            raise AuthenticationFailed(msg("auditeur.jeton_invalide"))
        with connection.cursor() as cur:  # SET LOCAL : valable pour la transaction de la vue
            cur.execute("SELECT set_config('app.org_id', %s, true)", [str(organisation)])
        acces = AccesAuditeur.objects.filter(jeton_hash=_hash(secret)).first()
        if acces is None:
            raise AuthenticationFailed(msg("auditeur.jeton_invalide"))
        if acces.revoque_le is not None:
            raise AuthenticationFailed(msg("auditeur.jeton_revoque"))
        if acces.expire_le <= maintenant():
            raise AuthenticationFailed(msg("auditeur.jeton_expire"))
        return Auditeur(acces), acces


class LectureSeule(BasePermission):
    """Un auditeur lit : toute méthode qui pourrait écrire est refusée (403)."""

    def has_permission(self, request, view) -> bool:
        return isinstance(request.user, Auditeur) and request.method in SAFE_METHODS


def exiger_projet_et_plage(acces: AccesAuditeur, project_id, fin_de_periode=None) -> None:
    """403 hors des projets nommés ; hors de la plage de périodes, l'objet n'existe pas pour lui."""
    if str(project_id) not in acces.project_ids:
        raise PermissionDenied(msg("auditeur.projet_hors_perimetre"))


def dans_la_plage(acces: AccesAuditeur, fin_de_periode: datetime.date) -> bool:
    return acces.period_from <= fin_de_periode <= acces.period_to


def journaliser_consultation(
    request, acces: AccesAuditeur, project_id, ressource: str, detail=None
):
    """Chaque consultation et chaque export figurent au journal de l'organisation."""
    journaliser(
        org_id=acces.org_id,
        actor_id=acces.id,
        action="auditor_consulted",
        object_type="acces_auditeur",
        object_id=acces.id,
        project_id=project_id,
        after={"nom": acces.nom, "ressource": ressource, **(detail or {})},
        actor_ip=request.META.get("REMOTE_ADDR"),
    )
