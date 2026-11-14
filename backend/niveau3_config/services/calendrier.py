"""Le calendrier des obligations, généré depuis le registre des exigences. Voir L6-T06.

Chaque exigence ACTIVE qui a une périodicité et un délai produit ses échéances : une par période
civile (mois, trimestre, semestre, année), à `fin de période + due_offset_days`. Aucun délai n'est
inventé : une exigence périodique sans délai est LISTÉE à part, pas échéancée. Une exigence « à
l'événement » n'a pas de calendrier : elle se déclenche, elle ne se planifie pas.

Le feu (vert, orange, rouge) se calcule à la date du jour ; il n'est jamais stocké.
"""

import calendar
import datetime
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from niveau1_socle.habilitations.permissions import est_habilite

from ..models import Echeance, Exigence, Periodicite, StatutEcheance, StatutExigence

MOIS_PAR_PERIODE = {
    Periodicite.MENSUELLE: 1,
    Periodicite.TRIMESTRIELLE: 3,
    Periodicite.SEMESTRIELLE: 6,
    Periodicite.ANNUELLE: 12,
}
# Seuils du feu. En jours avant l'échéance ; l'escalade, en jours de retard.
JOURS_ORANGE = 15
JOURS_ESCALADE = 7


def periodes_de_l_annee(periodicite: str, annee: int) -> list[tuple[datetime.date, datetime.date]]:
    """Les périodes civiles `(début, fin)` d'une année ; vide pour « à l'événement »."""
    pas = MOIS_PAR_PERIODE.get(periodicite)
    if pas is None:
        return []
    periodes = []
    for premier_mois in range(1, 13, pas):
        dernier_mois = premier_mois + pas - 1
        fin = datetime.date(annee, dernier_mois, calendar.monthrange(annee, dernier_mois)[1])
        periodes.append((datetime.date(annee, premier_mois, 1), fin))
    return periodes


def date_echeance(fin_de_periode: datetime.date, delai_jours: int) -> datetime.date:
    return fin_de_periode + datetime.timedelta(days=delai_jours)


def feu(echeance: Echeance, jour: datetime.date) -> str:
    """`remise`, `annulee`, `vert`, `orange` (≤ 15 jours) ou `rouge` (échéance dépassée)."""
    if echeance.statut != StatutEcheance.A_REMETTRE:
        return echeance.statut
    restant = (echeance.date_echeance - jour).days
    if restant < 0:
        return "rouge"
    return "orange" if restant <= JOURS_ORANGE else "vert"


@dataclass
class ResultatGeneration:
    creees: list[Echeance] = field(default_factory=list)
    existantes: int = 0
    annulees: list[Echeance] = field(default_factory=list)
    sans_delai: list[Exigence] = field(
        default_factory=list
    )  # périodiques, sans délai : pas échéancées


def _valable(exigence: Exigence, jour: datetime.date) -> bool:
    return exigence.valid_from <= jour and (exigence.valid_to is None or jour < exigence.valid_to)


def generer_calendrier(*, utilisateur, project_id, annee: int) -> ResultatGeneration:
    """Génère (idempotent) les échéances de l'année depuis les exigences actives du projet.

    Une échéance n'est produite que si l'exigence est en vigueur à la FIN de la période. Les
    échéances à remettre dont l'exigence n'est plus active à cette date sont annulées (jamais
    supprimées) ; celles déjà remises ne bougent pas.
    """
    if not est_habilite(utilisateur, "parametrer", project_id):
        raise PermissionDenied(msg("calendrier.habilitation_requise", operation="parametrer"))
    resultat = ResultatGeneration()
    with transaction.atomic():
        actives = list(
            Exigence.objects.filter(project_id=project_id, status=StatutExigence.ACTIVE).order_by(
                "code", "version"
            )
        )
        for exigence in actives:
            if exigence.periodicity not in MOIS_PAR_PERIODE:
                continue
            if exigence.due_offset_days is None:
                resultat.sans_delai.append(exigence)
                continue
            for debut, fin in periodes_de_l_annee(exigence.periodicity, annee):
                if not _valable(exigence, fin):
                    continue
                _, cree = Echeance.objects.get_or_create(
                    exigence=exigence,
                    periode_fin=fin,
                    defaults={
                        "org_id": exigence.org_id,
                        "project_id": project_id,
                        "periode_debut": debut,
                        "date_echeance": date_echeance(fin, exigence.due_offset_days),
                        "created_by": utilisateur.id,
                    },
                )
                if cree:
                    resultat.creees.append(Echeance.objects.get(exigence=exigence, periode_fin=fin))
                else:
                    resultat.existantes += 1
        for echeance in (
            Echeance.objects.select_for_update()
            .filter(
                project_id=project_id,
                statut=StatutEcheance.A_REMETTRE,
                periode_fin__year=annee,
            )
            .select_related("exigence")
        ):
            exigence = echeance.exigence
            if exigence.status != StatutExigence.ACTIVE or not _valable(
                exigence, echeance.periode_fin
            ):
                Echeance.objects.filter(pk=echeance.pk).update(statut=StatutEcheance.ANNULEE)
                resultat.annulees.append(echeance)
        journaliser(
            org_id=utilisateur.org_id,
            actor_id=utilisateur.id,
            action="calendar_generated",
            object_type="projet",
            object_id=project_id,
            project_id=project_id,
            after={
                "annee": annee,
                "creees": len(resultat.creees),
                "annulees": len(resultat.annulees),
                "sans_delai": [e.code for e in resultat.sans_delai],
            },
        )
    return resultat


def calendrier(*, utilisateur, project_id, annee: int, jour: datetime.date) -> list[tuple]:
    """Le calendrier de l'année, trié par date : `[(échéance, feu), …]`."""
    if not est_habilite(utilisateur, "consulter", project_id):
        raise PermissionDenied(msg("calendrier.habilitation_requise", operation="consulter"))
    echeances = (
        Echeance.objects.filter(project_id=project_id, date_echeance__year=annee)
        .select_related("exigence")
        .order_by("date_echeance", "exigence__code")
    )
    return [(e, feu(e, jour)) for e in echeances]


def marquer_remise(*, utilisateur, echeance: Echeance, rapport_id) -> Echeance:
    """Une échéance est remise par UN rapport publié, une fois."""
    if not est_habilite(utilisateur, "publier", echeance.project_id):
        raise PermissionDenied(msg("calendrier.habilitation_requise", operation="publier"))
    with transaction.atomic():
        courante = Echeance.objects.select_for_update().get(pk=echeance.pk)
        if courante.statut != StatutEcheance.A_REMETTRE:
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("calendrier.deja_traitee", statut=courante.statut),
            )
        courante.statut = StatutEcheance.REMISE
        courante.rapport_id = rapport_id
        courante.remise_le = timezone.now()
        courante.remise_par = utilisateur.id
        courante.save(
            update_fields=["statut", "rapport_id", "remise_le", "remise_par", "updated_at"]
        )
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action="deadline_met",
            object_type="echeance",
            object_id=courante.id,
            project_id=courante.project_id,
            after={"rapport": str(rapport_id)},
        )
    echeance.refresh_from_db()
    return echeance


def alertes_du_jour(*, project_id, jour: datetime.date) -> list[tuple[Echeance, str]]:
    """Ce que la tâche quotidienne doit signaler : `[(échéance, niveau), …]`.

    `imminente` : à ≤ 15 jours ; `en_retard` : dépassée ; `escalade` : dépassée de plus de 7 jours.
    """
    alertes = []
    for e in (
        Echeance.objects.filter(project_id=project_id, statut=StatutEcheance.A_REMETTRE)
        .select_related("exigence")
        .order_by("date_echeance", "exigence__code")
    ):
        restant = (e.date_echeance - jour).days
        if restant < -JOURS_ESCALADE:
            alertes.append((e, "escalade"))
        elif restant < 0:
            alertes.append((e, "en_retard"))
        elif restant <= JOURS_ORANGE:
            alertes.append((e, "imminente"))
    return alertes
