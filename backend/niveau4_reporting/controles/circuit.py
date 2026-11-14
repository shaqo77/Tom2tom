"""Le circuit de validation borné : 1 à 5 étapes, un rôle chacune. Voir L6-T02b.

Pas de moteur de processus : des étapes ordonnées, chacune avec une habilitation requise, une
condition d'entrée facultative (seuil de montant, catégorie, bailleur) et un motif obligatoire au
rejet. Une étape peut exiger que les contrôles de l'objet soient tranchés (dérogations comprises) :
vérifié ICI, côté serveur, pas seulement masqué dans l'interface.
"""

import datetime
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import LANGUES, msg, normaliser_textes
from niveau1_socle.habilitations.models import OPERATIONS
from niveau1_socle.habilitations.permissions import est_habilite

from .models import (
    Circuit,
    DecisionEtape,
    DemandeValidation,
    EtapeCircuit,
    StatutDemande,
)
from .services import exiger_controles_tranches

MAX_ETAPES = 5
CLES_CONDITION = {"montant_min", "categories", "bailleurs"}


def _valider_condition(condition) -> dict | None:
    if condition is None:
        return None
    invalide = not isinstance(condition, dict) or not condition or set(condition) - CLES_CONDITION
    if not invalide and "montant_min" in condition:
        try:
            Decimal(str(condition["montant_min"]))
        except InvalidOperation:
            invalide = True
    for cle in ("categories", "bailleurs"):
        if cle in condition and not (
            isinstance(condition[cle], list) and all(isinstance(x, str) for x in condition[cle])
        ):
            invalide = True
    if invalide:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("circuit.condition_invalide"))
    return condition


def creer_circuit(
    *, utilisateur, project_id, objet_type: str, valid_from: datetime.date, etapes: list[dict]
) -> Circuit:
    """Crée une NOUVELLE version du circuit (la précédente est close la veille de `valid_from`).

    Chaque étape : `nom` {fr,en}, `operation`, `condition` facultative, `exige_controles_tranches`.
    """
    if not est_habilite(utilisateur, "parametrer", project_id):
        raise PermissionDenied(msg("circuit.habilitation_requise", operation="parametrer"))
    if not 1 <= len(etapes) <= MAX_ETAPES:
        raise ErreurMetier(
            CodeErreur.REGLE_INVALIDE, msg("circuit.de_une_a_cinq_etapes", n=len(etapes))
        )
    preparees = []
    for rang, etape in enumerate(etapes, start=1):
        if etape.get("operation") not in OPERATIONS:
            raise ErreurMetier(
                CodeErreur.REGLE_INVALIDE,
                msg("circuit.operation_inconnue", operation=etape.get("operation")),
            )
        nom = normaliser_textes(etape.get("nom"), obligatoire=True)
        if set(LANGUES) - set(nom):  # un nom d'étape existe dans CHAQUE langue gérée
            raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("circuit.nom_toutes_langues"))
        preparees.append(
            {
                "rang": rang,
                "nom": nom,
                "operation": etape["operation"],
                "condition": _valider_condition(etape.get("condition")),
                "exige_controles_tranches": bool(etape.get("exige_controles_tranches")),
            }
        )
    with transaction.atomic():
        precedent = (
            Circuit.objects.select_for_update()
            .filter(project_id=project_id, objet_type=objet_type)
            .order_by("-version")
            .first()
        )
        if precedent is not None:
            if precedent.valid_from >= valid_from:
                raise ErreurMetier(CodeErreur.CONFLIT_DE_PERIODE, msg("circuit.periode_anterieure"))
            if precedent.valid_to is None:
                Circuit.objects.filter(pk=precedent.pk).update(valid_to=valid_from)
        circuit = Circuit.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            objet_type=objet_type,
            version=(precedent.version + 1) if precedent else 1,
            valid_from=valid_from,
            created_by=utilisateur.id,
        )
        for e in preparees:
            EtapeCircuit.objects.create(org_id=circuit.org_id, circuit=circuit, **e)
        journaliser(
            org_id=circuit.org_id,
            actor_id=utilisateur.id,
            action="circuit_created",
            object_type="circuit",
            object_id=circuit.id,
            project_id=project_id,
            after={"objet_type": objet_type, "version": circuit.version, "etapes": len(preparees)},
        )
    return circuit


def circuit_en_vigueur(project_id, objet_type: str, date: datetime.date) -> Circuit | None:
    return (
        Circuit.objects.filter(project_id=project_id, objet_type=objet_type, valid_from__lte=date)
        .exclude(valid_to__lte=date)
        .first()
    )


def _applicable(etape: EtapeCircuit, contexte: dict) -> bool:
    c = etape.condition
    if not c:
        return True
    if "montant_min" in c and Decimal(str(contexte.get("montant", "0"))) < Decimal(
        str(c["montant_min"])
    ):
        return False
    if "categories" in c and contexte.get("categorie") not in c["categories"]:
        return False
    return not ("bailleurs" in c and contexte.get("bailleur") not in c["bailleurs"])


def _etapes_applicables(circuit: Circuit, contexte: dict) -> list[EtapeCircuit]:
    return [e for e in circuit.etapes.order_by("rang") if _applicable(e, contexte)]


def ouvrir_demande(
    *, utilisateur, project_id, objet_type: str, objet_id, date_effet: datetime.date, contexte=None
) -> DemandeValidation:
    """Ouvre la validation d'un objet selon le circuit EN VIGUEUR à la date d'effet."""
    if not est_habilite(utilisateur, "saisir", project_id):
        raise PermissionDenied(msg("circuit.habilitation_requise", operation="saisir"))
    circuit = circuit_en_vigueur(project_id, objet_type, date_effet)
    if circuit is None:
        raise ErreurMetier(
            CodeErreur.AUCUNE_CONFIGURATION_A_LA_DATE,
            msg("circuit.aucun_circuit", objet_type=objet_type, date=date_effet.isoformat()),
        )
    contexte = {k: str(v) for k, v in (contexte or {}).items()}
    applicables = _etapes_applicables(circuit, contexte)
    if not applicables:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("circuit.aucune_etape_applicable"))
    try:
        with transaction.atomic():
            demande = DemandeValidation.objects.create(
                org_id=circuit.org_id,
                circuit=circuit,
                project_id=project_id,
                objet_type=objet_type,
                objet_id=objet_id,
                contexte=contexte,
                date_effet=date_effet,
                demandeur_id=utilisateur.id,
                rang_courant=applicables[0].rang,
                created_by=utilisateur.id,
            )
            journaliser(
                org_id=circuit.org_id,
                actor_id=utilisateur.id,
                action="validation_opened",
                object_type="demande_validation",
                object_id=demande.id,
                project_id=project_id,
                after={"circuit": circuit.version, "objet": f"{objet_type}:{objet_id}"},
            )
    except IntegrityError as erreur:
        raise ErreurMetier(
            CodeErreur.TRANSITION_INTERDITE, msg("circuit.deja_en_cours")
        ) from erreur
    return demande


def decider_etape(
    *, utilisateur, demande: DemandeValidation, rang: int, approuver: bool, motif: str = ""
) -> DemandeValidation:
    """Signe (ou rejette) l'étape `rang`, qui doit être l'étape COURANTE.

    Le rang attendu est passé par l'appelant : deux signatures concurrentes de la même étape ne
    produisent qu'un effet, la seconde trouve l'étape déjà franchie.
    """
    if not approuver and not (motif or "").strip():
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("circuit.rejet_motive"))
    with transaction.atomic():
        courante = DemandeValidation.objects.select_for_update().get(pk=demande.pk)
        if courante.statut != StatutDemande.EN_COURS or courante.rang_courant != rang:
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("circuit.etape_non_courante", rang=rang, statut=courante.statut),
            )
        etape = courante.circuit.etapes.get(rang=rang)
        if not est_habilite(utilisateur, etape.operation, courante.project_id):
            raise PermissionDenied(msg("circuit.habilitation_requise", operation=etape.operation))
        if utilisateur.id == courante.demandeur_id:
            raise ErreurMetier(CodeErreur.APPROBATION_REQUISE, msg("circuit.signataire_distinct"))
        if approuver and etape.exige_controles_tranches:
            exiger_controles_tranches(
                courante.project_id, courante.objet_type, courante.objet_id, courante.date_effet
            )
        DecisionEtape.objects.create(
            org_id=courante.org_id,
            demande=courante,
            rang=rang,
            approuvee=approuver,
            motif=(motif or "").strip(),
            decided_by=utilisateur.id,
            decided_by_nom=utilisateur.get_username(),
            created_by=utilisateur.id,
        )
        if not approuver:
            courante.statut, courante.rang_courant = StatutDemande.REJETEE, None
        else:
            suivantes = [
                e for e in _etapes_applicables(courante.circuit, courante.contexte) if e.rang > rang
            ]
            if suivantes:
                courante.rang_courant = suivantes[0].rang
            else:
                courante.statut, courante.rang_courant = StatutDemande.APPROUVEE, None
        courante.save(update_fields=["statut", "rang_courant", "updated_at"])
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action="validation_step_approved" if approuver else "validation_rejected",
            object_type="demande_validation",
            object_id=courante.id,
            project_id=courante.project_id,
            after={"rang": rang, "statut": courante.statut, "motif": (motif or "").strip()},
        )
    demande.refresh_from_db()
    return demande
