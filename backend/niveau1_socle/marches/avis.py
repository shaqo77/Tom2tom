"""L'avis de non-objection du bailleur : demande, pièces, décision, blocage de l'engagement. L9-T02.

Une ligne du plan dont la méthode exige l'avis (`non_objection_requise`) ne peut être engagée
qu'une fois l'avis obtenu. Règle d'« avis suffisant » (aussi tenue par la base, voir
`marches_avis_suffisant`) : au moins un avis a été demandé, et chaque demande non obtenue — en
attente ou refusée — a été suivie d'un avis OBTENU sur le même objet.
"""

import datetime

from django.db import IntegrityError, transaction

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from core.metier import habilite, refuser, traduire_integrite
from niveau3_config import stockage

from .models import (
    AvisNonObjection,
    LignePassation,
    NaturePieceAvis,
    ObjetAvis,
    PieceAvis,
    StatutAvis,
    StatutLigne,
)

TAILLE_MAX = 25 * 1024 * 1024  # 25 Mio par pièce


class PieceAvisAlteree(ValueError):
    """La pièce stockée ne correspond plus à l'empreinte enregistrée."""


def demander_avis(
    *, utilisateur, ligne: LignePassation, objet: str, date_demande: datetime.date
) -> AvisNonObjection:
    """Enregistre une demande d'avis pour une ligne soumise à non-objection."""
    habilite(utilisateur, "saisir", ligne.project_id)
    if objet not in ObjetAvis.values:
        refuser("passation.avis_objet_inconnu", objet=objet)
    courante = LignePassation.objects.get(pk=ligne.pk)
    if not courante.non_objection_requise:
        refuser("passation.avis_ligne_non_soumise", reference=courante.reference)
    # Un marché signé ne reçoit plus que des demandes d'avis sur ses avenants.
    if courante.statut == StatutLigne.ANNULE or (
        courante.statut == StatutLigne.SIGNE and objet != ObjetAvis.AVENANT
    ):
        raise ErreurMetier(
            CodeErreur.TRANSITION_INTERDITE,
            msg("passation.ligne_definitive", statut=courante.statut),
        )
    with transaction.atomic():
        avis = AvisNonObjection.objects.create(
            org_id=courante.org_id,
            ligne=courante,
            project_id=courante.project_id,
            objet=objet,
            date_demande=date_demande,
            demande_par=utilisateur.id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=avis.org_id,
            actor_id=utilisateur.id,
            action="non_objection_requested",
            object_type="avis_non_objection",
            object_id=avis.id,
            project_id=avis.project_id,
            after={"ligne": courante.reference, "objet": objet, "date": date_demande.isoformat()},
        )
    return avis


def joindre_piece(
    *, utilisateur, avis: AvisNonObjection, nature: str, nom: str, contenu: bytes
) -> PieceAvis:
    """Joint un fichier à l'avis (demande envoyée ou réponse reçue). Idempotent par contenu."""
    habilite(utilisateur, "saisir", avis.project_id)
    if nature not in NaturePieceAvis.values:
        refuser("passation.avis_nature_inconnue", nature=nature)
    if not (nom or "").strip():
        refuser("passation.avis_nom_obligatoire")
    if not isinstance(contenu, bytes | bytearray) or not 0 < len(contenu) <= TAILLE_MAX:
        refuser("passation.avis_fichier_invalide")
    contenu = bytes(contenu)
    digest = stockage.empreinte(contenu)
    existante = PieceAvis.objects.filter(avis=avis, sha256=digest).first()
    if existante is not None:
        return existante
    ref = stockage.deposer(utilisateur.org_id, contenu)
    try:
        with transaction.atomic():
            piece = PieceAvis.objects.create(
                org_id=avis.org_id,
                avis=avis,
                nature=nature,
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
                action="non_objection_document_attached",
                object_type="avis_non_objection",
                object_id=avis.id,
                project_id=avis.project_id,
                after={"nom": piece.nom, "nature": nature, "sha256": digest.hex()},
            )
    except IntegrityError as erreur:
        if "uq_pieceavis_par_avis" not in str(erreur):
            raise traduire_integrite(erreur) from erreur
        return PieceAvis.objects.get(avis=avis, sha256=digest)
    return piece


def lire_piece(piece: PieceAvis) -> bytes:
    contenu = stockage.lire(piece.file_ref)
    if stockage.empreinte(contenu) != bytes(piece.sha256):
        raise PieceAvisAlteree(msg("passation.avis_piece_alteree", nom=piece.nom))
    return contenu


def enregistrer_decision(
    *,
    utilisateur,
    avis: AvisNonObjection,
    statut: str,
    date_decision: datetime.date,
    reference_bailleur: str = "",
    motif: str = "",
) -> AvisNonObjection:
    """Enregistre la réponse du bailleur : obtenu (dès réception) ou refusé (motivé)."""
    habilite(utilisateur, "saisir", avis.project_id)
    if statut not in (StatutAvis.OBTENU, StatutAvis.REFUSE):
        refuser("passation.avis_statut_invalide", statut=statut)
    if statut == StatutAvis.REFUSE and not (motif or "").strip():
        refuser("passation.avis_refus_motive")
    with transaction.atomic():
        courant = AvisNonObjection.objects.select_for_update().get(pk=avis.pk)
        if courant.statut != StatutAvis.DEMANDE:
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("passation.avis_deja_decide", statut=courant.statut),
            )
        if date_decision < courant.date_demande:
            refuser("passation.avis_date_anterieure", date=courant.date_demande.isoformat())
        courant.statut = statut
        courant.date_decision = date_decision
        courant.reference_bailleur = (reference_bailleur or "").strip()
        courant.motif = (motif or "").strip()
        courant.decide_par = utilisateur.id
        courant.save(
            update_fields=[
                "statut",
                "date_decision",
                "reference_bailleur",
                "motif",
                "decide_par",
                "updated_at",
            ]
        )
        journaliser(
            org_id=courant.org_id,
            actor_id=utilisateur.id,
            action="non_objection_decided",
            object_type="avis_non_objection",
            object_id=courant.id,
            project_id=courant.project_id,
            before={"statut": StatutAvis.DEMANDE},
            after={
                "statut": statut,
                "date": date_decision.isoformat(),
                "reference": courant.reference_bailleur,
                "motif": courant.motif,
            },
        )
    avis.refresh_from_db()
    return avis


def avis_manquants(ligne: LignePassation) -> list[str]:
    """Objets (hors avenant) dont l'avis fait défaut ; vide = permis, `[""]` si aucun avis."""
    if not ligne.non_objection_requise:
        return []
    # L'avis « avenant » vit avec le contrat : il ne conditionne pas l'engagement.
    tous = list(
        AvisNonObjection.objects.filter(ligne=ligne)
        .exclude(objet=ObjetAvis.AVENANT)
        .order_by("created_at")
    )
    if not tous:
        return [""]
    obtenus = {a.objet: a.created_at for a in tous if a.statut == StatutAvis.OBTENU}
    bloquants = {
        a.objet
        for a in tous
        if a.statut != StatutAvis.OBTENU
        and not (a.objet in obtenus and obtenus[a.objet] > a.created_at)
    }
    return sorted(bloquants)


def avis_suffisant(ligne: LignePassation) -> bool:
    return not avis_manquants(ligne)


def avis_en_attente(
    *, utilisateur, project_id, jour: datetime.date
) -> list[tuple[AvisNonObjection, int]]:
    """Les demandes sans réponse, les plus anciennes d'abord, avec leur ancienneté en jours."""
    habilite(utilisateur, "consulter", project_id)
    return [
        (a, (jour - a.date_demande).days)
        for a in AvisNonObjection.objects.filter(project_id=project_id, statut=StatutAvis.DEMANDE)
        .select_related("ligne")
        .order_by("date_demande", "created_at")
    ]
