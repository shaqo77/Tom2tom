"""La simulation de revue bailleur et l'indicateur « accepté au premier envoi ». Voir L6-T07.

Avant d'envoyer un rapport, on REJOUE ce que le bailleur a l'habitude de rejeter : les contrôles
actifs sur les avances échues et sur l'objet en préparation, et les constats qui recoupent un
motif de rejet connu sont marqués comme tels. L'avis est :
- `no_go` : un constat bloquant, OU un constat qui recoupe un motif déjà rejeté par le bailleur ;
- `go_reserves` : des constats, aucun bloquant ni connu ;
- `go` : rien à signaler.
Chaque constat porte son message dans chaque langue et l'action corrective du contrôle.

La simulation est « à blanc » : elle calcule les évaluations sans les écrire au journal réel (une
évaluation journalisée est définitive et ferait bloquer l'étape de validation de l'objet). Ce
qu'elle a vu reste traçable dans la `SimulationRevue`, qui garde ses constats.
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.db import connection, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import LANGUES, msg, normaliser_textes
from niveau1_socle.avances.services import avances_non_justifiees_au_dela_du_delai
from niveau1_socle.habilitations.permissions import est_habilite
from niveau4_reporting.controles.contextes import contexte_avance
from niveau4_reporting.controles.models import (
    Controle,
    EvaluationControle,
    Resultat,
    Severite,
)
from niveau4_reporting.controles.services import controles_en_attente, evaluer_tous

from .models import (
    AvisRevue,
    MotifRejet,
    ResultatSoumission,
    SimulationRevue,
    SoumissionBailleur,
)

SERVICE = "simulation_revue"


def _habilite(utilisateur, operation: str, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(msg("revue.habilitation_requise", operation=operation))


# --- les motifs de rejet connus --------------------------------------------------------------


def enregistrer_motif(
    *, utilisateur, project_id, code: str, label: dict, controle_code: str, source: str = ""
) -> MotifRejet:
    """Enregistre un motif de rejet appris, relié au contrôle qui le détecte."""
    _habilite(utilisateur, "parametrer", project_id)
    if not (code or "").strip():
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("revue.motif_code_obligatoire"))
    textes = normaliser_textes(label, obligatoire=True)
    if set(LANGUES) - set(textes):
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("revue.motif_toutes_langues"))
    if not Controle.objects.filter(project_id=project_id, code=controle_code).exists():
        raise ErreurMetier(
            CodeErreur.REGLE_INVALIDE, msg("revue.controle_inconnu", code=controle_code)
        )
    with transaction.atomic():
        motif = MotifRejet.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            code=code.strip(),
            label=textes,
            controle_code=controle_code,
            source=(source or "").strip(),
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=motif.org_id,
            actor_id=utilisateur.id,
            action="rejection_motive_recorded",
            object_type="motif_rejet",
            object_id=motif.id,
            project_id=project_id,
            after={"code": motif.code, "controle": controle_code},
        )
    return motif


# --- la simulation ---------------------------------------------------------------------------


@dataclass
class _Constat:
    code: str  # le code du contrôle
    gravite: str
    message: dict  # {langue: texte}
    action: dict
    objet: str
    exigence: str = ""


def _constats_des_avances(utilisateur, project_id, date) -> list[_Constat]:
    constats = []
    for situation in avances_non_justifiees_au_dela_du_delai(utilisateur, project_id, date):
        evaluations = evaluer_tous(
            project_id,
            "avances",
            contexte_avance(situation, date),
            date_operation=date,
            objet_type="avance",
            objet_id=situation.avance.pk,
            service=SERVICE,
            ecrire=False,  # « à blanc » : le journal réel n'en garde rien et rien ne bloque
        )
        precis = msg(
            "revue.avance_en_retard",
            reference=situation.avance.reference,
            tiers=situation.avance.tiers.code,
            reste=situation.reste,
            jours_de_retard=situation.jours_de_retard,
        ).toutes()
        for e in evaluations:
            if e.resultat in (Resultat.REUSSI, Resultat.NON_APPLICABLE):
                continue
            constats.append(
                _Constat(
                    code=e.controle.code,
                    gravite=e.severity,
                    message=precis,
                    action=e.action_corrective,
                    objet=f"avance:{situation.avance.reference}",
                    exigence=e.exigence_code,
                )
            )
    return constats


def _constats_de_l_objet(project_id, objet_type, objet_id, date) -> list[_Constat]:
    constats, vus = [], set()
    for evaluation, raison in controles_en_attente(project_id, objet_type, objet_id, date):
        vus.add(evaluation.controle.code)
        constats.append(
            _Constat(
                code=evaluation.controle.code,
                gravite=Severite.BLOQUANT,
                message={
                    lg: f"{evaluation.message.get(lg, '')} — {raison.rendre(lg)}".strip(" —")
                    for lg in LANGUES
                },
                action=evaluation.action_corrective,
                objet=f"{objet_type}:{objet_id}",
                exigence=evaluation.exigence_code,
            )
        )
    dernieres: dict = {}
    for e in (
        EvaluationControle.objects.filter(
            project_id=project_id, objet_type=objet_type, objet_id=objet_id
        )
        .select_related("controle")
        .order_by("created_at", "id")
    ):
        dernieres[e.controle.code] = e
    for e in dernieres.values():
        if e.resultat == Resultat.AVERTISSEMENT and e.controle.code not in vus:
            constats.append(
                _Constat(
                    code=e.controle.code,
                    gravite=Severite.AVERTISSEMENT,
                    message=e.message,
                    action=e.action_corrective,
                    objet=f"{objet_type}:{objet_id}",
                    exigence=e.exigence_code,
                )
            )
    return constats


def simuler_revue(
    *,
    utilisateur,
    project_id,
    date_effet: datetime.date,
    objet_type: str = "rapport",
    objet_id=None,
) -> SimulationRevue:
    """Rejoue les motifs de rejet sur le rapport en préparation et rend un avis go / no-go."""
    _habilite(utilisateur, "consulter", project_id)
    with transaction.atomic():
        constats = _constats_des_avances(utilisateur, project_id, date_effet)
        constats += _constats_de_l_objet(project_id, objet_type, objet_id, date_effet)
        motifs = {
            m.controle_code: m for m in MotifRejet.objects.filter(project_id=project_id, actif=True)
        }
        sortie, connu = [], False
        for c in constats:
            motif = motifs.get(c.code)
            connu = connu or motif is not None
            sortie.append(
                {
                    "controle": c.code,
                    "gravite": c.gravite,
                    "message": c.message,
                    "action": c.action,
                    "objet": c.objet,
                    "exigence": c.exigence,
                    "motif_connu": (
                        {"code": motif.code, "label": motif.label, "source": motif.source}
                        if motif
                        else None
                    ),
                }
            )
        if any(c["gravite"] == Severite.BLOQUANT for c in sortie) or connu:
            avis = AvisRevue.NO_GO
        elif sortie:
            avis = AvisRevue.GO_RESERVES
        else:
            avis = AvisRevue.GO
        simulation = SimulationRevue.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            objet_type=objet_type,
            objet_id=objet_id,
            date_effet=date_effet,
            avis=avis,
            constats=sortie,
            lancee_par=utilisateur.id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=simulation.org_id,
            actor_id=utilisateur.id,
            action="review_simulated",
            object_type="simulation_revue",
            object_id=simulation.id,
            project_id=project_id,
            after={"avis": avis, "constats": len(sortie)},
        )
    return simulation


# --- les soumissions réelles et l'indicateur phare -------------------------------------------


def enregistrer_envoi(
    *,
    utilisateur,
    project_id,
    template_code: str,
    period_to: datetime.date,
    envoyee_le: datetime.date,
    rapport_id=None,
    simulation: SimulationRevue | None = None,
) -> SoumissionBailleur:
    """Note l'envoi réel d'un rapport au bailleur. Le numéro d'envoi se déduit : 1, 2, 3…"""
    _habilite(utilisateur, "publier", project_id)
    with transaction.atomic():
        with connection.cursor() as cur:  # le numéro se déduit d'un décompte : on sérialise
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                [f"soumission:{utilisateur.org_id}:{project_id}:{template_code}:{period_to}"],
            )
        precedents = SoumissionBailleur.objects.filter(
            project_id=project_id, template_code=template_code, period_to=period_to
        )
        # Un nouvel envoi n'a de sens qu'après l'issue du précédent.
        if precedents.filter(resultat=ResultatSoumission.EN_ATTENTE).exists():
            raise ErreurMetier(CodeErreur.TRANSITION_INTERDITE, msg("revue.envoi_en_attente"))
        soumission = SoumissionBailleur.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            template_code=template_code,
            period_to=period_to,
            numero_envoi=precedents.count() + 1,
            rapport_id=rapport_id,
            simulation=simulation,
            envoyee_le=envoyee_le,
            saisie_par=utilisateur.id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=soumission.org_id,
            actor_id=utilisateur.id,
            action="submission_recorded",
            object_type="soumission_bailleur",
            object_id=soumission.id,
            project_id=project_id,
            after={"envoi": soumission.numero_envoi, "template": template_code},
        )
    return soumission


def enregistrer_issue(
    *,
    utilisateur,
    soumission: SoumissionBailleur,
    accepte: bool,
    decidee_le: datetime.date,
    motif_rejet: str = "",
) -> SoumissionBailleur:
    """Pose l'issue d'un envoi, une fois. Un rejet exige le motif donné par le bailleur."""
    _habilite(utilisateur, "publier", soumission.project_id)
    if not accepte and not (motif_rejet or "").strip():
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("revue.rejet_motive"))
    with transaction.atomic():
        courante = SoumissionBailleur.objects.select_for_update().get(pk=soumission.pk)
        if courante.resultat != ResultatSoumission.EN_ATTENTE:
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("revue.issue_deja_posee", resultat=courante.resultat),
            )
        courante.resultat = ResultatSoumission.ACCEPTE if accepte else ResultatSoumission.REJETE
        courante.decidee_le = decidee_le
        courante.motif_rejet = "" if accepte else motif_rejet.strip()
        courante.save(update_fields=["resultat", "decidee_le", "motif_rejet", "updated_at"])
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action="submission_accepted" if accepte else "submission_rejected",
            object_type="soumission_bailleur",
            object_id=courante.id,
            project_id=courante.project_id,
            after={"envoi": courante.numero_envoi, "motif": courante.motif_rejet},
        )
    soumission.refresh_from_db()
    return soumission


@dataclass(frozen=True)
class Indicateur:
    acceptes: int
    decides: int  # premiers envois dont l'issue est connue
    en_attente: int
    taux: Decimal | None  # acceptés / décidés, sur les PREMIERS envois ; None sans issue connue


def taux_acceptation_premier_envoi(
    *, utilisateur, project_id, du: datetime.date, au: datetime.date
) -> Indicateur:
    """L'indicateur phare : rapports acceptés au premier envoi, envoyés entre `du` et `au`."""
    _habilite(utilisateur, "consulter", project_id)
    premiers = SoumissionBailleur.objects.filter(
        project_id=project_id, numero_envoi=1, envoyee_le__gte=du, envoyee_le__lte=au
    )
    acceptes = premiers.filter(resultat=ResultatSoumission.ACCEPTE).count()
    rejetes = premiers.filter(resultat=ResultatSoumission.REJETE).count()
    decides = acceptes + rejetes
    return Indicateur(
        acceptes=acceptes,
        decides=decides,
        en_attente=premiers.filter(resultat=ResultatSoumission.EN_ATTENTE).count(),
        taux=(Decimal(acceptes) / Decimal(decides)) if decides else None,
    )
