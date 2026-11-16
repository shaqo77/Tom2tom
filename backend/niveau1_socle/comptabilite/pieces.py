"""Les pièces justificatives d'une écriture : joindre un scan, le relire sans doute. L7-T03."""

from django.db import IntegrityError, transaction

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from niveau3_config import stockage

from .models import Ecriture, PieceJustificative, TypePiece
from .services import _exiger_habilitation

TAILLE_MAX = 25 * 1024 * 1024  # 25 Mio par scan


class PieceAlteree(ValueError):
    """Le scan stocké ne correspond plus à l'empreinte enregistrée."""


def joindre_piece(
    *, utilisateur, ecriture: Ecriture, type_piece: str, nom: str, contenu: bytes
) -> PieceJustificative:
    """Joint un scan à l'écriture. Idempotent : les mêmes octets ne se joignent qu'une fois."""
    _exiger_habilitation(utilisateur, "saisir", ecriture.project_id)
    if type_piece not in TypePiece.values:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("pieces.type_inconnu", type=type_piece))
    if not (nom or "").strip():
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("pieces.nom_obligatoire"))
    if not isinstance(contenu, bytes | bytearray) or not 0 < len(contenu) <= TAILLE_MAX:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("pieces.fichier_invalide"))
    contenu = bytes(contenu)
    digest = stockage.empreinte(contenu)
    existante = PieceJustificative.objects.filter(ecriture=ecriture, sha256=digest).first()
    if existante is not None:
        return existante
    ref = stockage.deposer(utilisateur.org_id, contenu)
    try:
        with transaction.atomic():
            piece = PieceJustificative.objects.create(
                org_id=ecriture.org_id,
                project_id=ecriture.project_id,
                ecriture=ecriture,
                type_piece=type_piece,
                nom=nom.strip(),
                file_ref=ref,
                sha256=digest,
                taille=len(contenu),
                ajoutee_par=utilisateur.id,
                created_by=utilisateur.id,
            )
            journaliser(
                org_id=piece.org_id,
                actor_id=utilisateur.id,
                action="supporting_document_attached",
                object_type="ecriture",
                object_id=ecriture.id,
                project_id=ecriture.project_id,
                after={"nom": piece.nom, "type": type_piece, "sha256": digest.hex()},
            )
    except IntegrityError:  # une jonction simultanée des mêmes octets
        return PieceJustificative.objects.get(ecriture=ecriture, sha256=digest)
    return piece


def lire_piece(piece: PieceJustificative) -> bytes:
    """Les octets du scan, après avoir recalculé et comparé son empreinte."""
    contenu = stockage.lire(piece.file_ref)
    if stockage.empreinte(contenu) != bytes(piece.sha256):
        raise PieceAlteree(msg("pieces.scan_altere", nom=piece.nom))
    return contenu
