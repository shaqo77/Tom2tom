"""Le plan de passation : méthodes et seuils, lignes prévisionnelles, avancement. Voir L9-T01.

Aucun seuil n'est inventé : chaque projet pose les siens, par méthode et par devise. Une ligne ne
peut être prévue qu'avec une méthode APPLICABLE à son montant (plage `[seuil_min, seuil_max[` en
vigueur à la date de lancement prévue). Elle avance de prévu à lancé, attribué, puis signé, ou
s'annule avant la signature, et chaque étape laisse sa date et son auteur.
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import LANGUES, msg, normaliser_textes
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.referentiels.models import Devise

from .models import (
    EtapeAvancement,
    LignePassation,
    MethodePassation,
    PlanPassation,
    StatutLigne,
)

SUITE = {
    StatutLigne.PREVU: StatutLigne.LANCE,
    StatutLigne.LANCE: StatutLigne.ATTRIBUE,
    StatutLigne.ATTRIBUE: StatutLigne.SIGNE,
}
DATE_PREVUE = {
    StatutLigne.PREVU: "date_lancement_prevue",
    StatutLigne.LANCE: "date_attribution_prevue",
    StatutLigne.ATTRIBUE: "date_signature_prevue",
}


def _habilite(utilisateur, operation: str, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(msg("passation.habilitation_requise", operation=operation))


def _refuser(cle: str, **params):
    raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg(cle, **params))


def _montant(valeur, champ: str) -> Decimal:
    try:
        nombre = Decimal(str(valeur))
    except InvalidOperation:
        _refuser("passation.montant_invalide", champ=champ)
    if not nombre.is_finite() or isinstance(valeur, float):
        _refuser("passation.montant_invalide", champ=champ)
    return nombre


# --- les méthodes et leurs seuils --------------------------------------------------------------


def definir_methode(
    *,
    utilisateur,
    project_id,
    code: str,
    label: dict,
    devise: str,
    seuil_min,
    seuil_max=None,
    exige_non_objection: bool = False,
    valid_from: datetime.date,
) -> MethodePassation:
    """Pose une NOUVELLE version de la méthode ; la précédente se ferme à `valid_from`."""
    _habilite(utilisateur, "parametrer", project_id)
    if not (code or "").strip():
        _refuser("passation.code_obligatoire")
    textes = normaliser_textes(label, obligatoire=True)
    if set(LANGUES) - set(textes):
        _refuser("passation.libelle_toutes_langues")
    if not Devise.objects.filter(code=devise).exists():
        _refuser("passation.devise_inconnue", devise=devise)
    minimum = _montant(seuil_min, "seuil_min")
    maximum = None if seuil_max is None else _montant(seuil_max, "seuil_max")
    if minimum < 0 or (maximum is not None and maximum <= minimum):
        _refuser("passation.plage_invalide")
    with transaction.atomic():
        precedente = (
            MethodePassation.objects.select_for_update()
            .filter(project_id=project_id, code=code.strip())
            .order_by("-version")
            .first()
        )
        if precedente is not None:
            if precedente.valid_from >= valid_from:
                _refuser("passation.version_posterieure")
            if precedente.valid_to is None:
                MethodePassation.objects.filter(pk=precedente.pk).update(valid_to=valid_from)
        methode = MethodePassation.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            code=code.strip(),
            version=(precedente.version + 1) if precedente else 1,
            label=textes,
            devise=devise,
            seuil_min=minimum,
            seuil_max=maximum,
            exige_non_objection=bool(exige_non_objection),
            valid_from=valid_from,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=methode.org_id,
            actor_id=utilisateur.id,
            action="procurement_method_defined",
            object_type="methode_passation",
            object_id=methode.id,
            project_id=project_id,
            after={
                "code": methode.code,
                "version": methode.version,
                "seuil_min": str(minimum),
                "seuil_max": None if maximum is None else str(maximum),
                "devise": devise,
                "exige_non_objection": methode.exige_non_objection,
            },
        )
    return methode


def methode_en_vigueur(project_id, code: str, date: datetime.date) -> MethodePassation | None:
    return (
        MethodePassation.objects.filter(project_id=project_id, code=code, valid_from__lte=date)
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=date))
        .first()
    )


def methodes_applicables(
    project_id, montant, devise: str, date: datetime.date
) -> list[MethodePassation]:
    """Les méthodes en vigueur à `date` dont la plage contient `montant`, dans cette devise."""
    montant = _montant(montant, "montant")
    return [
        m
        for m in MethodePassation.objects.filter(project_id=project_id, devise=devise)
        .filter(valid_from__lte=date)
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=date))
        .order_by("code")
        if m.seuil_min <= montant and (m.seuil_max is None or montant < m.seuil_max)
    ]


# --- le plan et ses lignes ---------------------------------------------------------------------


def creer_plan(
    *,
    utilisateur,
    project_id,
    code: str,
    nom: str,
    date_debut: datetime.date,
    date_fin: datetime.date,
) -> PlanPassation:
    _habilite(utilisateur, "saisir", project_id)
    if not (code or "").strip() or not (nom or "").strip():
        _refuser("passation.code_obligatoire")
    if date_debut > date_fin:
        _refuser("passation.periode_vide")
    try:
        with transaction.atomic():
            plan = PlanPassation.objects.create(
                org_id=utilisateur.org_id,
                project_id=project_id,
                code=code.strip(),
                nom=nom.strip(),
                date_debut=date_debut,
                date_fin=date_fin,
                cree_par=utilisateur.id,
                created_by=utilisateur.id,
            )
            journaliser(
                org_id=plan.org_id,
                actor_id=utilisateur.id,
                action="procurement_plan_created",
                object_type="plan_passation",
                object_id=plan.id,
                project_id=project_id,
                after={"code": plan.code},
            )
    except IntegrityError:
        _refuser("passation.plan_existe", code=code.strip())
    return plan


def _verifier_ligne(plan, montant, devise, methode, dates):
    lancement, attribution, signature = dates
    if not lancement <= attribution <= signature:
        _refuser("passation.calendrier_desordonne")
    if not all(plan.date_debut <= d <= plan.date_fin for d in dates):
        _refuser(
            "passation.hors_du_plan",
            debut=plan.date_debut.isoformat(),
            fin=plan.date_fin.isoformat(),
        )
    if montant <= 0:
        _refuser("passation.montant_invalide", champ="montant_prevu")
    if methode.devise != devise:
        _refuser("passation.devise_differente", methode=methode.devise, ligne=devise)
    if montant < methode.seuil_min or (
        methode.seuil_max is not None and montant >= methode.seuil_max
    ):
        _refuser(
            "passation.methode_non_applicable",
            code=methode.code,
            plage=f"[{methode.seuil_min}, {methode.seuil_max or '∞'}[",
            montant=montant,
            devise=devise,
        )


def ajouter_ligne(
    *,
    utilisateur,
    plan: PlanPassation,
    reference: str,
    libelle: str,
    montant_prevu,
    devise: str,
    methode_code: str,
    date_lancement_prevue: datetime.date,
    date_attribution_prevue: datetime.date,
    date_signature_prevue: datetime.date,
    categorie_id=None,
) -> LignePassation:
    """Prévoit un marché : la méthode doit s'appliquer à son montant, à la date de lancement."""
    _habilite(utilisateur, "saisir", plan.project_id)
    if not (reference or "").strip() or not (libelle or "").strip():
        _refuser("passation.code_obligatoire")
    montant = _montant(montant_prevu, "montant_prevu")
    methode = methode_en_vigueur(plan.project_id, methode_code, date_lancement_prevue)
    if methode is None:
        _refuser(
            "passation.methode_inconnue", code=methode_code, date=date_lancement_prevue.isoformat()
        )
    dates = (date_lancement_prevue, date_attribution_prevue, date_signature_prevue)
    _verifier_ligne(plan, montant, devise, methode, dates)
    try:
        with transaction.atomic():
            ligne = LignePassation.objects.create(
                org_id=plan.org_id,
                plan=plan,
                project_id=plan.project_id,
                reference=reference.strip(),
                libelle=libelle.strip(),
                montant_prevu=montant,
                devise=devise,
                methode=methode,
                non_objection_requise=methode.exige_non_objection,
                categorie_id=categorie_id,
                date_lancement_prevue=date_lancement_prevue,
                date_attribution_prevue=date_attribution_prevue,
                date_signature_prevue=date_signature_prevue,
                created_by=utilisateur.id,
            )
            EtapeAvancement.objects.create(
                org_id=plan.org_id,
                ligne=ligne,
                statut=StatutLigne.PREVU,
                date_effet=timezone.localdate(),
                par=utilisateur.id,
                created_by=utilisateur.id,
            )
            journaliser(
                org_id=plan.org_id,
                actor_id=utilisateur.id,
                action="procurement_line_planned",
                object_type="ligne_passation",
                object_id=ligne.id,
                project_id=plan.project_id,
                after={
                    "reference": ligne.reference,
                    "montant": str(montant),
                    "devise": devise,
                    "methode": f"{methode.code} v{methode.version}",
                    "non_objection_requise": ligne.non_objection_requise,
                },
            )
    except IntegrityError:
        _refuser("passation.reference_existe", reference=reference.strip())
    return ligne


def replanifier(
    *,
    utilisateur,
    ligne: LignePassation,
    date_lancement_prevue: datetime.date,
    date_attribution_prevue: datetime.date,
    date_signature_prevue: datetime.date,
    motif: str,
) -> LignePassation:
    """Déplace le calendrier prévu d'une ligne encore en cours, avec un motif tracé au journal."""
    _habilite(utilisateur, "saisir", ligne.project_id)
    if not (motif or "").strip():
        _refuser("passation.motif_obligatoire")
    dates = (date_lancement_prevue, date_attribution_prevue, date_signature_prevue)
    with transaction.atomic():
        courante = LignePassation.objects.select_for_update().get(pk=ligne.pk)
        if courante.statut in (StatutLigne.SIGNE, StatutLigne.ANNULE):
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("passation.ligne_definitive", statut=courante.statut),
            )
        _verifier_ligne(
            courante.plan, courante.montant_prevu, courante.devise, courante.methode, dates
        )
        avant = {
            "lancement": courante.date_lancement_prevue.isoformat(),
            "attribution": courante.date_attribution_prevue.isoformat(),
            "signature": courante.date_signature_prevue.isoformat(),
        }
        courante.date_lancement_prevue = date_lancement_prevue
        courante.date_attribution_prevue = date_attribution_prevue
        courante.date_signature_prevue = date_signature_prevue
        courante.save(
            update_fields=[
                "date_lancement_prevue",
                "date_attribution_prevue",
                "date_signature_prevue",
                "updated_at",
            ]
        )
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action="procurement_line_rescheduled",
            object_type="ligne_passation",
            object_id=courante.id,
            project_id=courante.project_id,
            before=avant,
            after={
                "lancement": date_lancement_prevue.isoformat(),
                "attribution": date_attribution_prevue.isoformat(),
                "signature": date_signature_prevue.isoformat(),
                "motif": motif.strip(),
            },
        )
    ligne.refresh_from_db()
    return ligne


def modifier_ligne_prevue(
    *, utilisateur, ligne: LignePassation, montant_prevu, methode_code: str | None = None
) -> LignePassation:
    """Change le montant (et, au besoin, la méthode) d'une ligne ENCORE « prévue » seulement."""
    _habilite(utilisateur, "saisir", ligne.project_id)
    montant = _montant(montant_prevu, "montant_prevu")
    with transaction.atomic():
        courante = LignePassation.objects.select_for_update().get(pk=ligne.pk)
        if courante.statut != StatutLigne.PREVU:
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("passation.ligne_lancee", statut=courante.statut),
            )
        methode = courante.methode
        if methode_code is not None and methode_code != methode.code:
            methode = methode_en_vigueur(
                courante.project_id, methode_code, courante.date_lancement_prevue
            )
            if methode is None:
                _refuser(
                    "passation.methode_inconnue",
                    code=methode_code,
                    date=courante.date_lancement_prevue.isoformat(),
                )
        dates = (
            courante.date_lancement_prevue,
            courante.date_attribution_prevue,
            courante.date_signature_prevue,
        )
        _verifier_ligne(courante.plan, montant, courante.devise, methode, dates)
        avant = {"montant": str(courante.montant_prevu), "methode": courante.methode.code}
        courante.montant_prevu, courante.methode = montant, methode
        # L'exigence d'avis suit la méthode retenue : on la relit sur la nouvelle méthode.
        courante.non_objection_requise = methode.exige_non_objection
        courante.save(
            update_fields=["montant_prevu", "methode", "non_objection_requise", "updated_at"]
        )
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action="procurement_line_modified",
            object_type="ligne_passation",
            object_id=courante.id,
            project_id=courante.project_id,
            before=avant,
            after={"montant": str(montant), "methode": methode.code},
        )
    ligne.refresh_from_db()
    return ligne


def avancer_ligne(
    *, utilisateur, ligne: LignePassation, statut: str, date_effet: datetime.date, note: str = ""
) -> LignePassation:
    """Franchit l'étape suivante (prévu → lancé → attribué → signé), ou annule avant la signature.

    Une étape ne se saute pas ; sa date ne précède pas celle de l'étape d'avant ; une annulation
    est motivée. Chaque étape laisse sa trace (date, auteur, note) en ajout seul.
    """
    _habilite(utilisateur, "saisir", ligne.project_id)
    with transaction.atomic():
        courante = LignePassation.objects.select_for_update().get(pk=ligne.pk)
        if courante.statut in (StatutLigne.SIGNE, StatutLigne.ANNULE):
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("passation.ligne_definitive", statut=courante.statut),
            )
        if statut == StatutLigne.ANNULE:
            if not (note or "").strip():
                _refuser("passation.annulation_motivee")
        elif SUITE.get(courante.statut) != statut:
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("passation.etape_non_suivante", actuel=courante.statut, demande=statut),
            )
        # L'étape « prévu » date de la saisie : seules les étapes franchies ordonnent les dates.
        derniere = (
            courante.etapes.exclude(statut=StatutLigne.PREVU)
            .order_by("-date_effet", "-created_at")
            .first()
        )
        if derniere is not None and date_effet < derniere.date_effet:
            _refuser("passation.date_anterieure", date=derniere.date_effet.isoformat())
        EtapeAvancement.objects.create(
            org_id=courante.org_id,
            ligne=courante,
            statut=statut,
            date_effet=date_effet,
            note=(note or "").strip(),
            par=utilisateur.id,
            created_by=utilisateur.id,
        )
        courante.statut = statut
        courante.save(update_fields=["statut", "updated_at"])
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action="procurement_line_advanced",
            object_type="ligne_passation",
            object_id=courante.id,
            project_id=courante.project_id,
            before={"statut": courante.statut},
            after={
                "statut": statut,
                "date_effet": date_effet.isoformat(),
                "note": (note or "").strip(),
            },
        )
    ligne.refresh_from_db()
    return ligne


# --- le suivi ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Retard:
    ligne: LignePassation
    etape_attendue: str  # l'étape que le calendrier prévoyait déjà franchie
    date_prevue: datetime.date
    jours: int


def lignes_en_retard(*, utilisateur, project_id, jour: datetime.date) -> list[Retard]:
    """Lignes dont l'étape suivante devait être franchie avant `jour`, plus en retard d'abord."""
    _habilite(utilisateur, "consulter", project_id)
    retards = []
    for ligne in LignePassation.objects.filter(
        project_id=project_id, statut__in=list(DATE_PREVUE)
    ).select_related("plan", "methode"):
        prevue = getattr(ligne, DATE_PREVUE[ligne.statut])
        if prevue < jour:
            retards.append(Retard(ligne, SUITE[ligne.statut], prevue, (jour - prevue).days))
    return sorted(retards, key=lambda r: (-r.jours, r.ligne.reference))


def synthese(*, utilisateur, plan: PlanPassation) -> dict:
    """Le plan en chiffres : montants par statut et par méthode, sans mélanger les devises."""
    _habilite(utilisateur, "consulter", plan.project_id)
    lignes = LignePassation.objects.filter(plan=plan)
    par_statut = {
        (r["statut"], r["devise"]): r["total"]
        for r in lignes.values("statut", "devise").annotate(total=Sum("montant_prevu"))
    }
    par_methode = {
        (r["methode__code"], r["devise"]): r["total"]
        for r in lignes.values("methode__code", "devise").annotate(total=Sum("montant_prevu"))
    }
    return {
        "nombre": lignes.count(),
        "par_statut": par_statut,
        "par_methode": par_methode,
        "non_objection_requise": lignes.filter(non_objection_requise=True).count(),
    }
