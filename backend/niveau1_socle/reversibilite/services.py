"""Demander, produire et télécharger l'export complet. Voir L8-T03.

Demandé depuis l'interface, produit en TÂCHE DE FOND (la commande `produire_exports`, à planifier),
mis à disposition par un lien signé à durée limitée. Le lien porte l'organisation, l'export et son
expiration, signés par la clé secrète : il ne se devine ni ne se prolonge.
"""

import hashlib
import time

from django.core import signing
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.organisations.models import Projet
from niveau3_config import stockage

from .archive import construire_archive
from .models import ExportOrganisation, StatutExport

SEL = "sigf.export.lien"
DUREE_MIN, DUREE_MAX = 60, 24 * 3600


def _exiger_export_total(utilisateur) -> None:
    """Exporter toute l'organisation : « exporter » sur CHAQUE projet, pas sur un seul."""
    projets = list(Projet.objects.values_list("id", flat=True))
    if not projets or not all(est_habilite(utilisateur, "exporter", p) for p in projets):
        raise PermissionDenied(msg("export.habilitation_requise"))


def demander_export(*, utilisateur) -> ExportOrganisation:
    _exiger_export_total(utilisateur)
    with transaction.atomic():
        export = ExportOrganisation.objects.create(
            org_id=utilisateur.org_id, demandeur_id=utilisateur.id, created_by=utilisateur.id
        )
        journaliser(
            org_id=export.org_id,
            actor_id=utilisateur.id,
            action="export_requested",
            object_type="export_organisation",
            object_id=export.id,
        )
    return export


def produire_export(export: ExportOrganisation) -> ExportOrganisation:
    """Produit l'archive d'un export demandé (tâche de fond). Le périmètre de l'organisation doit
    être posé. Un échec est enregistré, jamais avalé."""
    with transaction.atomic():
        courant = ExportOrganisation.objects.select_for_update().get(pk=export.pk)
        if courant.statut != StatutExport.DEMANDE:
            return courant  # déjà pris par un autre processus
        courant.statut = StatutExport.EN_COURS
        courant.save(update_fields=["statut", "updated_at"])
    try:
        with transaction.atomic():
            archive, manifeste = construire_archive(export.org_id)
            ref = stockage.deposer(export.org_id, archive)
            ExportOrganisation.objects.filter(pk=export.pk).update(
                statut=StatutExport.PRET,
                produit_le=timezone.now(),
                file_ref=ref,
                sha256=hashlib.sha256(archive).hexdigest(),
                taille=len(archive),
                nombre_tables=len(manifeste["tables"]),
            )
            journaliser(
                org_id=export.org_id,
                actor_id=export.demandeur_id,
                action="export_produced",
                object_type="export_organisation",
                object_id=export.id,
                after={"tables": len(manifeste["tables"]), "taille": len(archive)},
            )
    except Exception as erreur:  # noqa: BLE001  (on l'enregistre, puis on le relève)
        ExportOrganisation.objects.filter(pk=export.pk).update(
            statut=StatutExport.ECHEC, erreur=f"{type(erreur).__name__}: {erreur}"[:2000]
        )
        raise
    export.refresh_from_db()
    return export


def lien_signe(*, utilisateur, export: ExportOrganisation, duree_secondes: int = 3600) -> str:
    """Le jeton d'un lien de téléchargement, valable `duree_secondes` (1 minute à 24 heures)."""
    _exiger_export_total(utilisateur)
    if export.statut != StatutExport.PRET:
        raise ErreurMetier(CodeErreur.TRANSITION_INTERDITE, msg("export.pas_pret"))
    if not DUREE_MIN <= duree_secondes <= DUREE_MAX:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("export.duree_limitee"))
    expire = int(time.time()) + duree_secondes
    jeton = signing.Signer(salt=SEL).sign(f"{export.org_id}:{export.id}:{expire}")
    journaliser(
        org_id=export.org_id,
        actor_id=utilisateur.id,
        action="export_link_issued",
        object_type="export_organisation",
        object_id=export.id,
        after={"expire": expire},
    )
    return jeton


def lire_jeton(jeton: str) -> tuple[str, str]:
    """`(organisation, export)` d'un jeton valable ; `ValueError` sinon (signature, expiration)."""
    try:
        valeur = signing.Signer(salt=SEL).unsign(jeton)
        org, export, expire = valeur.split(":")
        if int(expire) <= int(time.time()):
            raise signing.BadSignature("expired")
    except (signing.BadSignature, ValueError) as erreur:
        raise ValueError(msg("export.lien_invalide")) from erreur
    return org, export


def poser_organisation(org_id) -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.org_id', %s, true)", [str(org_id)])
