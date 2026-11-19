"""Création des exercices et clôture des périodes. Voir L1-T04.

`VERIFICATIONS_DE_CLOTURE` est le point d'extension du grand livre : en L3, il
y enregistrera le contrôle « aucune écriture en brouillon dans la période ».
Une vérification reçoit la période et retourne `None` si elle ne s'oppose à
rien, sinon la raison du refus. Avant L3, il n'y a pas d'écriture en brouillon
à contrôler : le registre est vide et la clôture n'est pas bloquée.
"""

import calendar
import datetime
from collections.abc import Callable

from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.i18n import Liste, msg
from niveau1_socle.habilitations.permissions import est_habilite

from .models import Exercice, Periode, StatutExercice, StatutPeriode

VERIFICATIONS_DE_CLOTURE: list[Callable[[Periode], str | None]] = []


class TransitionInterdite(ValueError):
    """Le changement de statut demandé n'est pas permis depuis l'état courant."""


class ClotureImpossible(ValueError):
    """Un contrôle de clôture s'oppose à la clôture ; `raisons` les liste toutes."""

    def __init__(self, raisons: list[str]):
        self.raisons = raisons
        super().__init__(msg("exercices.cloture_impossible", details=Liste(raisons)))


def _ajouter_mois(date: datetime.date, mois: int) -> datetime.date:
    index = date.year * 12 + (date.month - 1) + mois
    return datetime.date(index // 12, index % 12 + 1, 1)


def creer_exercice(projet, annee: int, *, utilisateur, mois_debut: int = 1) -> Exercice:
    """Crée un exercice de douze mois et ses douze périodes contiguës, ouvertes."""
    if not 1 <= mois_debut <= 12:
        raise ValueError(msg("exercices.mois_debut_doit_etre_compris"))
    debut = datetime.date(annee, mois_debut, 1)
    with transaction.atomic():
        exercice = Exercice.objects.create(
            org_id=projet.org_id,
            project_id=projet.id,
            annee=annee,
            date_debut=debut,
            date_fin=_ajouter_mois(debut, 12) - datetime.timedelta(days=1),
        )
        for numero in range(1, 13):
            premier = _ajouter_mois(debut, numero - 1)
            dernier_jour = calendar.monthrange(premier.year, premier.month)[1]
            Periode.objects.create(
                org_id=projet.org_id,
                exercice=exercice,
                numero=numero,
                date_debut=premier,
                date_fin=premier.replace(day=dernier_jour),
            )
        journaliser(
            org_id=projet.org_id,
            actor_id=getattr(utilisateur, "id", None),
            action="fiscal_year_created",
            object_type="exercice",
            object_id=exercice.id,
            project_id=projet.id,
            after={"annee": annee, "date_debut": str(exercice.date_debut)},
        )
    return exercice


def _changer_statut(periode: Periode, attendu: str, nouveau: str, action: str, utilisateur):
    with transaction.atomic():
        # Verrou de ligne : deux clôtures simultanées ne passent pas toutes les deux.
        courante = Periode.objects.select_for_update().get(pk=periode.pk)
        if courante.status != attendu:
            raise TransitionInterdite(
                msg(
                    "exercices.periode_seule_periode_peut_passer",
                    numero=courante.numero,
                    status=courante.status,
                    attendu=attendu,
                    nouveau=nouveau,
                )
            )
        if nouveau == StatutPeriode.CLOSE:
            raisons = [raison for verif in VERIFICATIONS_DE_CLOTURE if (raison := verif(courante))]
            if raisons:
                raise ClotureImpossible(raisons)
        courante.status = nouveau
        courante.save(update_fields=["status", "updated_at"])
        journaliser(
            org_id=courante.org_id,
            actor_id=getattr(utilisateur, "id", None),
            action=action,
            object_type="periode",
            object_id=courante.id,
            project_id=courante.exercice.project_id,
            before={"status": attendu},
            after={"status": nouveau},
        )
    periode.status = nouveau
    return periode


def cloturer_periode(periode: Periode, *, utilisateur) -> Periode:
    """Ferme une période ouverte, sauf si un contrôle de clôture s'y oppose."""
    return _changer_statut(
        periode, StatutPeriode.OUVERTE, StatutPeriode.CLOSE, "period_closed", utilisateur
    )


def verrouiller_periode(periode: Periode, *, utilisateur) -> Periode:
    """Verrouille définitivement une période close. Aucun retour en arrière."""
    return _changer_statut(
        periode, StatutPeriode.CLOSE, StatutPeriode.VERROUILLEE, "period_locked", utilisateur
    )


def exercice_verrouille(exercice: Exercice) -> bool:
    """Un exercice est verrouillé quand toutes ses périodes le sont : plus rien ne s'y corrige."""
    return not exercice.periodes.exclude(status=StatutPeriode.VERROUILLEE).exists()


def rouvrir_periode(periode: Periode, *, utilisateur, motif: str) -> Periode:
    """Rouvre une période CLOSE pour y passer une correction. Tracé, avec son motif.

    Une période verrouillée ne se rouvre jamais (la base le refuse aussi). Rouvrir une période d'un
    exercice clos le fait redevenir ouvert : la clôture annuelle est à refaire, et elle régénérera
    les à-nouveaux. Opération sensible : elle exige l'habilitation `parametrer`.
    """
    if not (motif or "").strip():
        raise ValueError(msg("exercices.reouverture_periode_exige_motif"))
    with transaction.atomic():
        courante = Periode.objects.select_for_update().select_related("exercice").get(pk=periode.pk)
        if not est_habilite(utilisateur, "parametrer", courante.exercice.project_id):
            raise PermissionDenied(msg("exercices.vous_etes_habilite_parametrer_projet"))
        if courante.status != StatutPeriode.CLOSE:
            raise TransitionInterdite(
                msg(
                    "exercices.periode_seule_periode_close_peut",
                    numero=courante.numero,
                    status=courante.status,
                )
            )
        Periode.objects.filter(pk=courante.pk).update(status=StatutPeriode.OUVERTE)
        if courante.exercice.status == StatutExercice.CLOS:
            Exercice.objects.filter(pk=courante.exercice_id).update(status=StatutExercice.OUVERT)
        journaliser(
            org_id=courante.org_id,
            actor_id=getattr(utilisateur, "id", None),
            action="period_reopened",
            object_type="periode",
            object_id=courante.id,
            project_id=courante.exercice.project_id,
            before={"status": courante.status},
            after={"status": StatutPeriode.OUVERTE, "motif": motif.strip()},
        )
    periode.status = StatutPeriode.OUVERTE
    return periode
