"""Suivi des avances : versement, justification, échéances, alertes. Voir L4-T07.

Droits : verser, justifier = `saisir` ; fixer le délai = `parametrer` ; lire le suivi = `consulter`.
Aucun délai n'est supposé : tant qu'un projet n'en a pas paramétré un, verser une avance sans
préciser son délai est refusé (une règle contractuelle ne se devine pas).

Le reste à justifier se calcule, il n'est jamais stocké. `avances_non_justifiees_au_dela_du_delai`
est la ressource que consomme le contrôle du même nom du lot L6.
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.db import connection, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.referentiels.models import Tiers

from .models import Avance, DelaiAvance, JustificationAvance, TypeJustification

ZERO = Decimal(0)
PREAVIS_PAR_DEFAUT = 7  # jours avant l'échéance où une avance non justifiée est signalée


class AvanceInvalide(ValueError):
    """Une avance ou une justification ne respecte pas les règles."""


def _habilite(utilisateur, operation: str, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(f"Vous n'êtes pas habilité à « {operation} » sur ce projet.")


# --- délai applicable -------------------------------------------------------------------------


def delai_applicable(project_id, date: datetime.date) -> DelaiAvance | None:
    """Le délai en vigueur à `date` (validité `[valid_from, valid_to[`), ou rien."""
    return (
        DelaiAvance.objects.filter(project_id=project_id, valid_from__lte=date)
        .exclude(valid_to__lte=date)
        .first()
    )


def parametrer_delai(
    *, utilisateur, project_id, jours: int, date_effet: datetime.date, motif: str = ""
) -> DelaiAvance:
    """Fixe le délai de justification à partir de `date_effet` ; clôt la version en cours.
    Les avances déjà versées gardent le délai de leur versement."""
    _habilite(utilisateur, "parametrer", project_id)
    if type(jours) is not int or jours <= 0:
        raise AvanceInvalide("Le délai est un nombre entier de jours strictement positif")
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                [f"delai-avance:{project_id}"],
            )
        versions = DelaiAvance.objects.filter(project_id=project_id)
        en_cours = versions.filter(valid_to__isnull=True).first()
        if en_cours is not None:
            if date_effet <= en_cours.valid_from:
                raise AvanceInvalide(
                    f"La nouvelle version doit prendre effet après le {en_cours.valid_from}"
                )
            DelaiAvance.objects.filter(pk=en_cours.pk).update(valid_to=date_effet)
        numero = (versions.order_by("-version").values_list("version", flat=True).first() or 0) + 1
        delai = DelaiAvance.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            jours=jours,
            version=numero,
            valid_from=date_effet,
            motif=(motif or "").strip(),
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=delai.org_id,
            actor_id=utilisateur.id,
            action="advance_deadline_configured",
            object_type="delai_avance",
            object_id=delai.id,
            project_id=project_id,
            before={"jours": en_cours.jours if en_cours else None},
            after={"jours": jours, "valid_from": str(date_effet)},
        )
    return delai


# --- verser, justifier ------------------------------------------------------------------------


def verser_avance(
    *,
    utilisateur,
    project_id,
    tiers: Tiers,
    reference: str,
    montant,
    date_versement: datetime.date,
    delai_jours: int | None = None,
    libelle: str = "",
    ligne_ecriture_id=None,
) -> Avance:
    """Enregistre une avance. Son délai est celui en vigueur à la date de versement (ou celui qui
    est précisé), puis il est FIGÉ sur l'avance."""
    _habilite(utilisateur, "saisir", project_id)
    montant = Decimal(str(montant))
    if montant <= 0:
        raise AvanceInvalide("Une avance a un montant strictement positif")
    if not (reference or "").strip():
        raise AvanceInvalide("La référence de l'avance est obligatoire")
    if delai_jours is None:
        delai = delai_applicable(project_id, date_versement)
        if delai is None:
            raise AvanceInvalide(
                f"Aucun délai de justification n'est paramétré à la date du {date_versement} : "
                "paramétrez-le ou précisez le délai de cette avance"
            )
        delai_jours = delai.jours
    elif type(delai_jours) is not int or delai_jours <= 0:
        raise AvanceInvalide("Le délai est un nombre entier de jours strictement positif")
    with transaction.atomic():
        avance = Avance.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            tiers=tiers,
            reference=reference.strip(),
            libelle=libelle,
            montant=montant,
            date_versement=date_versement,
            delai_jours=delai_jours,
            ligne_ecriture_id=ligne_ecriture_id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=avance.org_id,
            actor_id=utilisateur.id,
            action="advance_paid",
            object_type="avance",
            object_id=avance.id,
            project_id=project_id,
            after={
                "reference": avance.reference,
                "tiers": tiers.code,
                "montant": str(montant),
                "echeance": str(date_versement + datetime.timedelta(days=delai_jours)),
            },
        )
    return avance


def justifier_avance(
    avance: Avance,
    *,
    utilisateur,
    type: str,
    montant,
    date_justification: datetime.date,
    reference: str = "",
    ligne_ecriture_id=None,
) -> JustificationAvance:
    """Justifie tout ou partie d'une avance : dépense prouvée ou remboursement. Jamais plus que ce
    qui reste ; le refus est tranché par la base, sous verrou de l'avance."""
    _habilite(utilisateur, "saisir", avance.project_id)
    if type not in TypeJustification.values:
        raise AvanceInvalide(f"type de justification inconnu : {type}")
    montant = Decimal(str(montant))
    if montant <= 0:
        raise AvanceInvalide("Une justification a un montant strictement positif")
    if type == TypeJustification.DEPENSE and not (reference or "").strip():
        raise AvanceInvalide("Une dépense se justifie par une pièce : indiquez sa référence")
    with transaction.atomic():
        courante = Avance.objects.select_for_update().get(pk=avance.pk)
        deja = sum((j.montant for j in courante.justifications.all()), ZERO)
        if deja + montant > courante.montant:
            raise AvanceInvalide(
                f"On ne justifie pas plus que l'avance : reste {courante.montant - deja}, "
                f"{montant} demandé"
            )
        justification = JustificationAvance.objects.create(
            org_id=utilisateur.org_id,
            avance=courante,
            type=type,
            montant=montant,
            date_justification=date_justification,
            reference=(reference or "").strip(),
            ligne_ecriture_id=ligne_ecriture_id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action="advance_justified",
            object_type="avance",
            object_id=courante.id,
            project_id=courante.project_id,
            after={
                "type": type,
                "montant": str(montant),
                "reste": str(courante.montant - deja - montant),
            },
        )
    return justification


# --- situation, suivi, alertes ----------------------------------------------------------------


@dataclass(frozen=True)
class SituationAvance:
    avance: Avance
    justifie_depenses: Decimal
    justifie_remboursements: Decimal
    reste: Decimal
    echeance: datetime.date
    jours_de_retard: int  # > 0 : échue depuis autant de jours ; 0 : pas échue
    niveau: str  # "soldee", "en_cours", "a_echeance" ou "echue"

    @property
    def justifie(self) -> Decimal:
        return self.justifie_depenses + self.justifie_remboursements


def _situation(avance: Avance, justifications, date: datetime.date, preavis: int):
    depenses = sum((j.montant for j in justifications if j.type == "depense"), ZERO)
    remboursements = sum((j.montant for j in justifications if j.type == "remboursement"), ZERO)
    reste = avance.montant - depenses - remboursements
    echeance = avance.date_versement + datetime.timedelta(days=avance.delai_jours)
    retard = max((date - echeance).days, 0) if reste > 0 else 0
    if reste == 0:
        niveau = "soldee"
    elif date > echeance:
        niveau = "echue"
    elif (echeance - date).days <= preavis:
        niveau = "a_echeance"
    else:
        niveau = "en_cours"
    return SituationAvance(avance, depenses, remboursements, reste, echeance, retard, niveau)


def situation_avance(
    utilisateur, avance: Avance, date: datetime.date, *, preavis: int = PREAVIS_PAR_DEFAUT
) -> SituationAvance:
    """La situation d'une avance à `date` : seules comptent les justifications datées au plus tard
    ce jour-là, pour pouvoir relire le passé."""
    _habilite(utilisateur, "consulter", avance.project_id)
    justifications = avance.justifications.filter(date_justification__lte=date)
    return _situation(avance, list(justifications), date, preavis)


def suivi(
    utilisateur, project_id, date: datetime.date, *, preavis: int = PREAVIS_PAR_DEFAUT
) -> list[SituationAvance]:
    """Toutes les avances versées au plus tard à `date`, du plus en retard au plus récent."""
    _habilite(utilisateur, "consulter", project_id)
    avances = Avance.objects.filter(project_id=project_id, date_versement__lte=date)
    rangees = []
    for avance in avances.prefetch_related("justifications").select_related("tiers"):
        justifications = [j for j in avance.justifications.all() if j.date_justification <= date]
        rangees.append(_situation(avance, justifications, date, preavis))
    ordre = {"echue": 0, "a_echeance": 1, "en_cours": 2, "soldee": 3}
    return sorted(rangees, key=lambda s: (ordre[s.niveau], -s.jours_de_retard, s.echeance))


def avances_non_justifiees_au_dela_du_delai(
    utilisateur, project_id, date: datetime.date
) -> list[SituationAvance]:
    """Les avances échues à `date` avec un reste à justifier : la ressource du contrôle de L6."""
    return [s for s in suivi(utilisateur, project_id, date) if s.niveau == "echue"]


@dataclass(frozen=True)
class Alerte:
    niveau: str  # "echue" ou "a_echeance"
    situation: SituationAvance
    message: str


def alertes(
    utilisateur, project_id, date: datetime.date, *, preavis: int = PREAVIS_PAR_DEFAUT
) -> list[Alerte]:
    """Une alerte par avance échue (avec son retard) ou arrivant à échéance dans `preavis` jours."""
    resultat = []
    for s in suivi(utilisateur, project_id, date, preavis=preavis):
        if s.niveau == "echue":
            message = (
                f"Avance {s.avance.reference} ({s.avance.tiers.code}) : {s.reste} non justifié, "
                f"échue depuis {s.jours_de_retard} jour(s) (échéance {s.echeance})"
            )
        elif s.niveau == "a_echeance":
            message = (
                f"Avance {s.avance.reference} ({s.avance.tiers.code}) : {s.reste} à justifier "
                f"avant le {s.echeance}"
            )
        else:
            continue
        resultat.append(Alerte(s.niveau, s, message))
    return resultat


def encours_par_tiers(utilisateur, project_id, date: datetime.date) -> dict[str, Decimal]:
    """Le reste à justifier par tiers (code), à `date`."""
    total: dict[str, Decimal] = {}
    for s in suivi(utilisateur, project_id, date):
        if s.reste > 0:
            code = s.avance.tiers.code
            total[code] = total.get(code, ZERO) + s.reste
    return total
