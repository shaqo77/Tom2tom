"""Documents de référence : enregistrement, remplacement, intégrité. Voir L5-T01.

Une exigence cite « DFIL §4.2 ». Si le fichier est remplacé en douce, la citation ne veut plus rien
dire. L'empreinte SHA-256 garantit que la citation renvoie EXACTEMENT au document analysé :
- le même fichier téléversé deux fois donne la même empreinte (et le même document) ;
- un fichier modifié d'un octet donne une autre empreinte, et le système le SIGNALE au lieu de
  l'accepter sous le même titre et la même version : un document modifié est une nouvelle version ;
- remplacer un document les chaîne (`superseded_by`) sans toucher à l'ancien, et liste les
  exigences qui le citent, à revérifier ;
- `verifier_integrite` relit le fichier stocké et le compare à l'empreinte enregistrée.

Habilitation : `parametrer` pour enregistrer et remplacer, `consulter` pour vérifier.
"""

import datetime

from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from niveau1_socle.habilitations.permissions import est_habilite

from .. import stockage
from ..models import DocumentReference, Exigence, TypeDocument

TAILLE_MAX = 50 * 1024 * 1024  # 50 Mio


class DocumentInvalide(ValueError):
    """Le document ou son fichier ne respecte pas les règles."""


class DocumentModifie(DocumentInvalide):
    """Un fichier différent est présenté sous le titre et la version d'un document connu."""


class IntegriteDocument(ValueError):
    """Le fichier stocké ne correspond plus à l'empreinte enregistrée."""


def _habilite(utilisateur, operation: str, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(f"Vous n'êtes pas habilité à « {operation} » sur ce projet.")


def _verifier_contenu(contenu: bytes) -> None:
    if not isinstance(contenu, bytes | bytearray) or len(contenu) == 0:
        raise DocumentInvalide("Le fichier est vide")
    if len(contenu) > TAILLE_MAX:
        raise DocumentInvalide(f"Le fichier dépasse {TAILLE_MAX // (1024 * 1024)} Mio")


def enregistrer_document(
    *,
    utilisateur,
    project_id,
    kind: str,
    title: str,
    contenu: bytes,
    version: str = "",
    issued_on: datetime.date | None = None,
) -> DocumentReference:
    """Enregistre un document avec l'empreinte de son contenu.

    Idempotent : les mêmes octets sous le même type, titre et version rendent le document existant.
    Des octets différents sous les mêmes type, titre et version sont REFUSÉS (`DocumentModifie`) :
    pour un texte modifié, on crée une nouvelle version ou on remplace.
    """
    _habilite(utilisateur, "parametrer", project_id)
    if kind not in TypeDocument.values:
        raise DocumentInvalide(f"type de document inconnu : {kind}")
    if not (title or "").strip():
        raise DocumentInvalide("Le titre du document est obligatoire")
    _verifier_contenu(contenu)
    contenu = bytes(contenu)
    digest = stockage.empreinte(contenu)
    with transaction.atomic():
        existant = DocumentReference.objects.filter(
            project_id=project_id, kind=kind, title=title.strip(), version=version
        ).first()
        if existant is not None:
            if bytes(existant.sha256) == digest:
                return existant
            raise DocumentModifie(
                f"Le document « {title.strip()} » (version {version or 'sans numéro'}) est déjà "
                f"enregistré avec l'empreinte {bytes(existant.sha256).hex()[:16]}… ; ce fichier "
                f"porte {digest.hex()[:16]}… : un document modifié est une nouvelle version"
            )
        ref = stockage.deposer(utilisateur.org_id, contenu)
        try:
            with transaction.atomic():
                document = DocumentReference.objects.create(
                    org_id=utilisateur.org_id,
                    project_id=project_id,
                    kind=kind,
                    title=title.strip(),
                    version=version,
                    issued_on=issued_on,
                    file_ref=ref,
                    sha256=digest,
                    created_by=utilisateur.id,
                )
        except IntegrityError:  # une session concurrente a enregistré le même document
            document = DocumentReference.objects.get(
                project_id=project_id, kind=kind, title=title.strip(), version=version
            )
            if bytes(document.sha256) != digest:
                raise DocumentModifie(
                    "Ce document vient d'être enregistré avec un autre contenu"
                ) from None
            return document
        journaliser(
            org_id=document.org_id,
            actor_id=utilisateur.id,
            action="document_registered",
            object_type="document_reference",
            object_id=document.id,
            project_id=project_id,
            after={
                "kind": kind,
                "title": document.title,
                "version": version,
                "sha256": digest.hex(),
            },
        )
    return document


def remplacer_document(
    *,
    utilisateur,
    ancien: DocumentReference,
    contenu: bytes,
    version: str,
    issued_on: datetime.date | None = None,
    title: str | None = None,
) -> DocumentReference:
    """Enregistre la nouvelle version d'un document et chaîne l'ancien (`superseded_by`).

    L'ancien document, son fichier et son empreinte ne sont jamais touchés : les exigences qui le
    citent continuent de renvoyer à ce qui a été analysé. Elles sont à revérifier
    (`exigences_a_reverifier`).
    """
    _habilite(utilisateur, "parametrer", ancien.project_id)
    if not (version or "").strip():
        raise DocumentInvalide("La nouvelle version doit être numérotée")
    with transaction.atomic():
        courant = DocumentReference.objects.select_for_update().get(pk=ancien.pk)
        if courant.superseded_by_id is not None:
            raise DocumentInvalide(f"Le document « {courant.title} » est déjà remplacé")
        nouveau = enregistrer_document(
            utilisateur=utilisateur,
            project_id=courant.project_id,
            kind=courant.kind,
            title=title or courant.title,
            contenu=contenu,
            version=version,
            issued_on=issued_on,
        )
        if nouveau.pk == courant.pk or bytes(nouveau.sha256) == bytes(courant.sha256):
            raise DocumentInvalide("Le nouveau fichier est identique à celui qu'il remplace")
        DocumentReference.objects.filter(pk=courant.pk).update(superseded_by=nouveau)
        journaliser(
            org_id=courant.org_id,
            actor_id=utilisateur.id,
            action="document_superseded",
            object_type="document_reference",
            object_id=courant.id,
            project_id=courant.project_id,
            before={"sha256": bytes(courant.sha256).hex()},
            after={"remplace_par": str(nouveau.id), "sha256": bytes(nouveau.sha256).hex()},
        )
    ancien.refresh_from_db()
    return nouveau


def exigences_a_reverifier(document: DocumentReference):
    """Les exigences qui citent un document remplacé : leur citation vise l'ancien texte, il faut
    s'assurer qu'elle tient toujours dans le nouveau."""
    if document.superseded_by_id is None:
        return Exigence.objects.none()
    return Exigence.objects.filter(document=document).exclude(status__in=["superseded", "rejected"])


def verifier_integrite(utilisateur, document: DocumentReference) -> bool:
    """Relit le fichier stocké et le compare à l'empreinte enregistrée. Lève `IntegriteDocument`
    si le fichier a changé ou disparu ; la constatation est journalisée."""
    _habilite(utilisateur, "consulter", document.project_id)
    try:
        contenu = stockage.lire(document.file_ref)
    except stockage.FichierIntrouvable as erreur:
        probleme = f"Le fichier de « {document.title} » est introuvable ({erreur})"
    else:
        if stockage.empreinte(contenu) == bytes(document.sha256):
            return True
        probleme = (
            f"Le fichier de « {document.title} » ne correspond plus à son empreinte : "
            f"enregistrée {bytes(document.sha256).hex()[:16]}…, "
            f"constatée {stockage.empreinte(contenu).hex()[:16]}…"
        )
    journaliser(
        org_id=document.org_id,
        actor_id=utilisateur.id,
        action="document_integrity_failed",
        object_type="document_reference",
        object_id=document.id,
        project_id=document.project_id,
        after={"probleme": probleme},
    )
    raise IntegriteDocument(probleme)


def verifier_integrite_du_projet(utilisateur, project_id) -> list[tuple[DocumentReference, str]]:
    """Vérifie tous les documents d'un projet ; retourne ceux qui échouent, avec la raison."""
    _habilite(utilisateur, "consulter", project_id)
    echecs = []
    for document in DocumentReference.objects.filter(project_id=project_id).order_by("created_at"):
        try:
            verifier_integrite(utilisateur, document)
        except IntegriteDocument as erreur:
            echecs.append((document, str(erreur)))
    return echecs
