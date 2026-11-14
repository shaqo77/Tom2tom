"""Enregistrer, activer et ÉVALUER un contrôle ; trancher un contrôle à vérifier. Voir L6-T01.

Le moteur est APPELÉ par les autres modules (comptabilité, dépenses, demandes) : aucun module ne
réimplémente ses règles. Chaque évaluation laisse une ligne du journal : règle et version, profil
de décaissement résolu à la date de l'opération, valeur constatée et attendue, résultat, message,
action corrective, exigence et clause sources, date, déclencheur.
"""

import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from niveau1_socle.habilitations.permissions import est_habilite
from niveau3_config.models import Exigence, RattachementExigence, StatutExigence, TypeCible
from niveau3_config.services.activation import _fermer_les_precedentes, _transition
from niveau3_config.services.decaissement import profil_en_vigueur

from . import conditions
from .models import (
    Controle,
    Decision,
    DecisionControle,
    EvaluationControle,
    ModeControle,
    Resultat,
    Severite,
    StatutControle,
    TypeDeclencheur,
)


def _habilite(utilisateur, operation: str, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(f"Vous n'êtes pas habilité à « {operation} » sur ce projet.")


def _libelle(controle: Controle) -> str:
    return controle.label.get("fr") or next(iter(controle.label.values()))


# --- enregistrement et cycle de vie --------------------------------------------------------


def creer_controle(
    *,
    utilisateur,
    project_id,
    code: str,
    label: dict,
    type_regle: str,
    severity: str,
    valid_from: datetime.date,
    expression: dict | None = None,
    applicable_si: dict | None = None,
    action_corrective: str = "",
    manuel: bool = False,
) -> Controle:
    """Enregistre un contrôle en brouillon ; une condition hors schéma est refusée ICI."""
    _habilite(utilisateur, "parametrer", project_id)
    if not (code or "").strip() or not isinstance(label, dict) or not label:
        raise ErreurMetier(
            CodeErreur.REGLE_INVALIDE, "Le code et le libellé du contrôle sont requis"
        )
    if severity not in Severite.values:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, f"Sévérité inconnue : {severity}")
    try:
        if manuel:
            if expression is not None:
                raise conditions.ConditionInvalide(
                    "Un contrôle à vérifier à la main n'a pas d'expression"
                )
            if type_regle not in conditions.TYPES_DE_REGLE:
                raise conditions.ConditionInvalide(f"type de règle « {type_regle} » inconnu")
        else:
            if expression is None:
                raise conditions.ConditionInvalide("Un contrôle automatique a une expression")
            conditions.preparer_expression(expression, type_regle)
        if applicable_si is not None:
            conditions.preparer_expression(applicable_si, type_regle)
    except conditions.ConditionInvalide as erreur:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, f"Règle invalide : {erreur}") from erreur
    with transaction.atomic():
        derniere = (
            Controle.objects.filter(project_id=project_id, code=code.strip())
            .order_by("-version")
            .values_list("version", flat=True)
            .first()
        )
        controle = Controle.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            code=code.strip(),
            version=(derniere or 0) + 1,
            label=label,
            type_regle=type_regle,
            severity=severity,
            mode=ModeControle.MANUEL if manuel else ModeControle.AUTOMATIQUE,
            expression=expression,
            applicable_si=applicable_si,
            action_corrective=action_corrective,
            valid_from=valid_from,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=controle.org_id,
            actor_id=utilisateur.id,
            action="control_created",
            object_type="controle",
            object_id=controle.id,
            project_id=project_id,
            after={"code": controle.code, "version": controle.version, "severite": severity},
        )
    return controle


def _transition_controle(utilisateur, controle, depuis, vers, action, operation, apres=None):
    _habilite(utilisateur, operation, controle.project_id)
    try:
        with transaction.atomic():
            controle = Controle.objects.select_for_update().get(pk=controle.pk)
            if vers == StatutControle.ACTIF:
                list(
                    Controle.objects.select_for_update()
                    .filter(project_id=controle.project_id, code=controle.code)
                    .order_by("version")
                )
                _fermer_les_precedentes(
                    Controle.objects.filter(
                        project_id=controle.project_id,
                        code=controle.code,
                        status=StatutControle.ACTIF,
                    ).exclude(pk=controle.pk),
                    controle.valid_from,
                    f"Contrôle {controle.code}",
                )
            _transition(
                utilisateur=utilisateur,
                objet=controle,
                type_objet="controle",
                depuis=depuis,
                vers=vers,
                action=action,
                avant=controle.status,
                apres=apres,
            )
    except IntegrityError as erreur:
        raise ErreurMetier(
            CodeErreur.CONFLIT_DE_PERIODE,
            f"Contrôle {controle.code} : une version active couvre déjà cette période",
        ) from erreur
    except ValueError as erreur:
        raise ErreurMetier(CodeErreur.TRANSITION_INTERDITE, str(erreur)) from erreur
    return controle


def valider_controle(*, utilisateur, controle: Controle) -> Controle:
    return _transition_controle(
        utilisateur,
        controle,
        [StatutControle.BROUILLON],
        StatutControle.VALIDE,
        "control_validated",
        "valider",
        {"validated_by": utilisateur.id, "validated_at": timezone.now()},
    )


def activer_controle(*, utilisateur, controle: Controle) -> Controle:
    return _transition_controle(
        utilisateur,
        controle,
        [StatutControle.VALIDE],
        StatutControle.ACTIF,
        "control_activated",
        "parametrer",
    )


def rejeter_controle(*, utilisateur, controle: Controle, motif: str) -> Controle:
    if not (motif or "").strip():
        raise ErreurMetier(CodeErreur.TRANSITION_INTERDITE, "Un rejet exige un motif")
    return _transition_controle(
        utilisateur,
        controle,
        [StatutControle.BROUILLON, StatutControle.VALIDE],
        StatutControle.REJETE,
        "control_rejected",
        "valider",
        {"motif": motif.strip()},
    )


# --- évaluation ----------------------------------------------------------------------------


def _source(controle: Controle, date: datetime.date):
    """L'exigence ACTIVE à `date` qui justifie ce contrôle, et la clause citée."""
    ids = RattachementExigence.objects.filter(
        target_type=TypeCible.CONTROLE, target_id=controle.id
    ).values_list("exigence_id", flat=True)
    exigence = (
        Exigence.objects.filter(pk__in=ids, status=StatutExigence.ACTIVE, valid_from__lte=date)
        .exclude(valid_to__lte=date)
        .order_by("code", "-version")
        .first()
    )
    if exigence is None:
        return None, "", ""
    c = exigence.citation
    clause = ", ".join(
        f"{nom} {c[cle]}"
        for cle, nom in (("annex", "annexe"), ("page", "page"), ("paragraph", "§"))
        if c.get(cle) not in (None, "")
    )
    return exigence.id, exigence.code, clause


def _chaine(valeur) -> str:
    return "" if valeur is None else str(valeur)


def evaluer_controle(
    controle: Controle,
    contexte: dict,
    *,
    date_operation: datetime.date,
    objet_type: str,
    objet_id=None,
    utilisateur=None,
    service: str | None = None,
    accord=None,
) -> EvaluationControle:
    """Évalue `controle` sur `contexte`, ÉCRIT le journal et le retourne.

    Un déclencheur est exigé : un utilisateur OU un service nommé. Le contrôle doit être actif à
    `date_operation`. `accord` (facultatif) sert à noter la version du profil de décaissement
    résolue à cette date.
    """
    if (utilisateur is None) == (service is None):
        raise ValueError("Un déclencheur est exigé : un utilisateur ou un service, pas les deux")
    if not (
        controle.status == StatutControle.ACTIF
        and controle.valid_from <= date_operation
        and (controle.valid_to is None or controle.valid_to > date_operation)
    ):
        raise ErreurMetier(
            CodeErreur.AUCUNE_CONFIGURATION_A_LA_DATE,
            f"Le contrôle {controle.code} n'est pas actif le {date_operation}",
        )
    constats: list[conditions.Constat] = []
    if controle.mode == ModeControle.MANUEL:
        resultat, message = (
            Resultat.A_VERIFIER,
            f"{_libelle(controle)} : vérification humaine requise",
        )
    else:
        applicable = (
            True
            if controle.applicable_si is None
            else conditions.reussit(
                conditions.evaluer(
                    conditions.preparer_expression(controle.applicable_si, controle.type_regle),
                    contexte,
                )
            )
        )
        if not applicable:
            resultat, message = Resultat.NON_APPLICABLE, f"{_libelle(controle)} : non applicable"
        else:
            constats = conditions.evaluer(
                conditions.preparer_expression(controle.expression, controle.type_regle), contexte
            )
            if conditions.reussit(constats):
                resultat, message = Resultat.REUSSI, f"{_libelle(controle)} : réussi"
            else:
                resultat = Resultat(controle.severity)
                echecs = "; ".join(c.lisible() for c in constats if not c.satisfaite)
                message = f"{_libelle(controle)} : {echecs}"
    premier_echec = next((c for c in constats if not c.satisfaite), None)
    profil = profil_en_vigueur(accord, date_operation) if accord is not None else None
    exigence_id, exigence_code, clause = _source(controle, date_operation)
    with transaction.atomic():
        return EvaluationControle.objects.create(
            org_id=controle.org_id,
            controle=controle,
            controle_version=controle.version,
            project_id=controle.project_id,
            objet_type=objet_type,
            objet_id=objet_id,
            resultat=resultat,
            severity=controle.severity,
            valeur_constatee=_chaine(premier_echec.constate) if premier_echec else "",
            valeur_attendue=(
                f"{premier_echec.operateur} {_chaine(premier_echec.attendu)}".strip()
                if premier_echec
                else ""
            ),
            message=message,
            action_corrective=(
                controle.action_corrective if resultat not in (Resultat.REUSSI,) else ""
            ),
            profile_version_id=profil.id if profil else None,
            exigence_id=exigence_id,
            exigence_code=exigence_code,
            exigence_clause=clause,
            evaluee_le=date_operation,
            declencheur_type=(
                TypeDeclencheur.UTILISATEUR if utilisateur is not None else TypeDeclencheur.SERVICE
            ),
            declencheur_id=utilisateur.id if utilisateur is not None else None,
            declencheur_nom=service or "",
        )


def evaluer_tous(
    project_id,
    type_regle: str,
    contexte: dict,
    *,
    date_operation: datetime.date,
    objet_type: str,
    objet_id=None,
    utilisateur=None,
    service: str | None = None,
    accord=None,
) -> list[EvaluationControle]:
    """Évalue tous les contrôles ACTIFS de ce type : le point d'entrée des autres modules."""
    controles = (
        Controle.objects.filter(
            project_id=project_id,
            type_regle=type_regle,
            status=StatutControle.ACTIF,
            valid_from__lte=date_operation,
        )
        .exclude(valid_to__lte=date_operation)
        .order_by("code")
    )
    return [
        evaluer_controle(
            c,
            contexte,
            date_operation=date_operation,
            objet_type=objet_type,
            objet_id=objet_id,
            utilisateur=utilisateur,
            service=service,
            accord=accord,
        )
        for c in controles
    ]


# --- contrôles à vérifier ------------------------------------------------------------------


def trancher(*, utilisateur, evaluation: EvaluationControle, decision: str, motif: str):
    """Une personne habilitée (`valider`) tranche un contrôle « à vérifier ». Ajout seul."""
    _habilite(utilisateur, "valider", evaluation.project_id)
    if decision not in Decision.values:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, f"Décision inconnue : {decision}")
    if not (motif or "").strip():
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, "Une décision est motivée")
    if evaluation.resultat != Resultat.A_VERIFIER:
        raise ErreurMetier(
            CodeErreur.TRANSITION_INTERDITE,
            f"Seul un contrôle « à vérifier » se tranche (celui-ci est « {evaluation.resultat} »)",
        )
    with transaction.atomic():
        decision_enregistree = DecisionControle.objects.create(
            org_id=evaluation.org_id,
            evaluation=evaluation,
            decision=decision,
            motif=motif.strip(),
            decided_by=utilisateur.id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=evaluation.org_id,
            actor_id=utilisateur.id,
            action="control_decided",
            object_type="evaluation_controle",
            object_id=evaluation.id,
            project_id=evaluation.project_id,
            after={"decision": decision, "motif": motif.strip()},
        )
    return decision_enregistree


def controles_en_attente(project_id, objet_type: str, objet_id=None) -> list[tuple]:
    """Ce qui empêche d'avancer pour cet objet : `[(évaluation, raison), …]`.

    On ne regarde que la DERNIÈRE évaluation de chaque contrôle sur l'objet. Bloquent : un résultat
    `bloquant`, un contrôle `à vérifier` pas encore tranché, une décision « non conforme ».
    """
    evaluations = EvaluationControle.objects.filter(
        project_id=project_id, objet_type=objet_type, objet_id=objet_id
    ).order_by("created_at", "id")
    dernieres: dict = {}
    for evaluation in evaluations:
        dernieres[evaluation.controle_id] = evaluation
    en_attente = []
    for evaluation in dernieres.values():
        if evaluation.resultat == Resultat.BLOQUANT:
            en_attente.append((evaluation, "contrôle bloquant"))
        elif evaluation.resultat == Resultat.A_VERIFIER:
            derniere = evaluation.decisions.order_by("-decided_at", "-id").first()
            if derniere is None:
                en_attente.append((evaluation, "vérification humaine non tranchée"))
            elif derniere.decision == Decision.NON_CONFORME:
                en_attente.append((evaluation, "déclaré non conforme"))
    return sorted(en_attente, key=lambda x: x[0].controle.code)


def exiger_controles_tranches(project_id, objet_type: str, objet_id=None) -> None:
    """Refuse d'avancer tant qu'un contrôle bloque : vérifié au serveur (`CONTROLE_BLOQUANT`)."""
    en_attente = controles_en_attente(project_id, objet_type, objet_id)
    if en_attente:
        detail = "; ".join(f"{e.controle.code} ({raison})" for e, raison in en_attente)
        raise ErreurMetier(CodeErreur.CONTROLE_BLOQUANT, f"Contrôles à traiter : {detail}")
