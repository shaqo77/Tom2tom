"""Justifications et dérogations. Voir L6-T02.

Deux actes distincts. Une JUSTIFICATION explique une anomalie : elle ne lève aucun blocage. Une
DÉROGATION autorise, pour un contrôle et un objet précis, pendant une durée bornée, à poursuivre
malgré un résultat bloquant ; elle est demandée par une personne et approuvée par une autre,
habilitée. Le résultat initial reste dans le journal d'évaluation, intact : la dérogation s'ajoute
à côté, et le dossier de conformité montre les deux.
"""

import datetime

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from niveau1_socle.habilitations.permissions import est_habilite

from .models import (
    Derogation,
    EvaluationControle,
    Justification,
    Resultat,
    StatutDerogation,
)


def _habilite(utilisateur, operation: str, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(msg("derogations.habilitation_requise", operation=operation))


def _est_la_derniere(evaluation: EvaluationControle) -> bool:
    derniere = (
        EvaluationControle.objects.filter(
            controle_id=evaluation.controle_id,
            project_id=evaluation.project_id,
            objet_type=evaluation.objet_type,
            objet_id=evaluation.objet_id,
        )
        .order_by("created_at", "id")
        .last()
    )
    return derniere is not None and derniere.pk == evaluation.pk


def justifier(*, utilisateur, evaluation: EvaluationControle, texte: str) -> Justification:
    """Explique une anomalie (résultat autre que réussi / non applicable). Texte obligatoire."""
    _habilite(utilisateur, "saisir", evaluation.project_id)
    if evaluation.resultat in (Resultat.REUSSI, Resultat.NON_APPLICABLE):
        raise ErreurMetier(
            CodeErreur.REGLE_INVALIDE,
            msg("derogations.rien_a_justifier", resultat=evaluation.resultat),
        )
    if not (texte or "").strip():
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("derogations.justification_textuelle"))
    with transaction.atomic():
        justification = Justification.objects.create(
            org_id=evaluation.org_id,
            evaluation=evaluation,
            texte=texte.strip(),
            auteur_id=utilisateur.id,
            auteur_nom=utilisateur.get_username(),
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=evaluation.org_id,
            actor_id=utilisateur.id,
            action="control_justified",
            object_type="evaluation_controle",
            object_id=evaluation.id,
            project_id=evaluation.project_id,
            after={"texte": texte.strip(), "auteur": utilisateur.get_username()},
        )
    return justification


def demander_derogation(
    *,
    utilisateur,
    evaluation: EvaluationControle,
    motif: str,
    justificatif: str,
    valide_du: datetime.date,
    valide_jusquau: datetime.date,
) -> Derogation:
    """Demande l'autorisation de poursuivre malgré ce résultat bloquant, sur CET objet."""
    _habilite(utilisateur, "saisir", evaluation.project_id)
    if evaluation.resultat != Resultat.BLOQUANT:
        raise ErreurMetier(
            CodeErreur.REGLE_INVALIDE,
            msg("derogations.seul_resultat_bloquant", resultat=evaluation.resultat),
        )
    if not _est_la_derniere(evaluation):
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("derogations.evaluation_depassee"))
    if not (motif or "").strip() or not (justificatif or "").strip():
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("derogations.motif_et_justificatif"))
    if valide_du >= valide_jusquau:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("derogations.periode_vide"))
    with transaction.atomic():
        derogation = Derogation.objects.create(
            org_id=evaluation.org_id,
            evaluation=evaluation,
            controle_id=evaluation.controle_id,
            project_id=evaluation.project_id,
            objet_type=evaluation.objet_type,
            objet_id=evaluation.objet_id,
            motif=motif.strip(),
            justificatif=justificatif.strip(),
            valide_du=valide_du,
            valide_jusquau=valide_jusquau,
            demandeur_id=utilisateur.id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=evaluation.org_id,
            actor_id=utilisateur.id,
            action="waiver_requested",
            object_type="derogation",
            object_id=derogation.id,
            project_id=evaluation.project_id,
            after={
                "evaluation": str(evaluation.id),
                "resultat_initial": evaluation.resultat,
                "motif": motif.strip(),
                "justificatif": justificatif.strip(),
                "valide_du": valide_du.isoformat(),
                "valide_jusquau": valide_jusquau.isoformat(),
            },
        )
    return derogation


def decider_derogation(
    *, utilisateur, derogation: Derogation, approuver: bool, motif: str
) -> Derogation:
    """Approuve ou refuse. L'approbateur est habilité (`valider`) et n'est pas le demandeur.

    La ligne est verrouillée : de deux décisions concurrentes, une seule prend effet.
    """
    _habilite(utilisateur, "valider", derogation.project_id)
    if not (motif or "").strip():
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("derogations.decision_motivee"))
    with transaction.atomic():
        courante = Derogation.objects.select_for_update().get(pk=derogation.pk)
        if utilisateur.id == courante.demandeur_id:
            raise ErreurMetier(
                CodeErreur.APPROBATION_REQUISE, msg("derogations.approbateur_distinct")
            )
        if courante.statut != StatutDerogation.DEMANDEE:
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("derogations.deja_decidee", statut=courante.statut),
            )
        statut = StatutDerogation.APPROUVEE if approuver else StatutDerogation.REFUSEE
        courante.statut = statut
        courante.approbateur_id = utilisateur.id
        courante.decidee_le = timezone.now()
        courante.motif_decision = motif.strip()
        courante.save(
            update_fields=["statut", "approbateur_id", "decidee_le", "motif_decision", "updated_at"]
        )
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action="waiver_approved" if approuver else "waiver_refused",
            object_type="derogation",
            object_id=courante.id,
            project_id=courante.project_id,
            before={"statut": StatutDerogation.DEMANDEE},
            after={"statut": statut, "motif": motif.strip()},
        )
    derogation.refresh_from_db()
    return derogation


def derogation_en_vigueur(
    *, controle_id, project_id, objet_type: str, objet_id, date: datetime.date
) -> Derogation | None:
    """La dérogation APPROUVÉE qui couvre ce contrôle sur cet objet à `date`, s'il y en a une.

    Périmètre exact (contrôle, projet, objet) ; validité `[valide_du, valide_jusquau[`.
    """
    return (
        Derogation.objects.filter(
            controle_id=controle_id,
            project_id=project_id,
            objet_type=objet_type,
            objet_id=objet_id,
            statut=StatutDerogation.APPROUVEE,
            valide_du__lte=date,
            valide_jusquau__gt=date,
        )
        .order_by("-decidee_le")
        .first()
    )


def dossier_de_conformite(project_id, objet_type: str, objet_id=None) -> list[dict]:
    """Le fil de conformité d'un objet : échecs, justifications, dérogations, dans l'ordre.

    Le résultat initial « bloquant » y figure toujours, suivi de la dérogation qui l'autorise :
    deux lignes, jamais une seule qui aurait remplacé l'autre.
    """
    evenements = []
    evaluations = EvaluationControle.objects.filter(
        project_id=project_id, objet_type=objet_type, objet_id=objet_id
    ).select_related("controle")
    for e in evaluations:
        if e.resultat in (Resultat.REUSSI, Resultat.NON_APPLICABLE):
            continue
        evenements.append((e.created_at, "evaluation", e.controle.code, e.resultat, e))
        for j in e.justifications.all():
            evenements.append((j.created_at, "justification", e.controle.code, j.texte, j))
    for d in Derogation.objects.filter(
        project_id=project_id, objet_type=objet_type, objet_id=objet_id
    ).select_related("controle"):
        evenements.append((d.created_at, "derogation", d.controle.code, d.statut, d))
    evenements.sort(key=lambda x: x[0])
    return [
        {"le": quand, "genre": genre, "controle": code, "detail": detail, "objet": objet}
        for quand, genre, code, detail, objet in evenements
    ]
