"""Compte spécial (BAD) : justifications soumises à la Banque et situation. Voir L11-D4.

La réconciliation du compte spécial (annexe 9 du manuel des décaissements de la BAD) se lit ainsi :

    (2) avances versées au compte, DEPUIS L'OUVERTURE
    (3) solde de clôture du relevé
    (4) justification soumise avec la demande en cours
    (5) dépenses déjà justifiées à la Banque
    (6) total justifié = (3) + (4) + (5)
    (7) écart = (2) − (6), à expliquer dans une note

Les avances viennent des encaissements du relevé appariés à une demande (jamais « tous les
encaissements »), le solde du relevé, et les justifications de ce que `JustificationCompteSpecial`
enregistre. Rien n'est estimé : un solde de relevé absent rend la situation INCOMPLÈTE.

Habilitation : `saisir` pour justifier ou annuler.
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from core.metier import decimal as nombre_decimal
from core.metier import habilite, refuser, traduire_integrite
from niveau1_socle.decaissements.models import DemandeRetrait
from niveau1_socle.financements.models import CompteBancaire, TypeCompte
from niveau1_socle.rapprochement.models import MouvementReleve

from .models import AppariementDemande, JustificationCompteSpecial
from .services import solde_releve_a

ZERO = Decimal(0)


@dataclass
class SituationCompteSpecial:
    compte_code: str
    devise: str
    date: datetime.date
    manques: list = field(default_factory=list)  # ce qui empêche de conclure
    avances: list = field(default_factory=list)  # (numéro de demande, montant reçu)
    solde_cloture: Decimal | None = None
    justifie_cette_demande: Decimal = ZERO
    justifie_precedemment: Decimal = ZERO

    @property
    def total_avances(self) -> Decimal:
        return sum((m for _, m in self.avances), ZERO)

    @property
    def total_justifie(self) -> Decimal | None:
        if self.solde_cloture is None:
            return None
        return self.solde_cloture + self.justifie_cette_demande + self.justifie_precedemment

    @property
    def ecart(self) -> Decimal | None:
        return None if self.total_justifie is None else self.total_avances - self.total_justifie

    @property
    def complet(self) -> bool:
        return not self.manques


def _compte_special(compte: CompteBancaire) -> None:
    if compte.type != TypeCompte.SPECIAL:
        refuser("compte_special.compte_non_special", code=compte.code)


def calculer_situation(
    compte: CompteBancaire, date: datetime.date, demande_numero: str | None = None
) -> SituationCompteSpecial:
    """La situation du compte spécial à `date`, SANS contrôle d'habilitation (états du moteur).

    `demande_numero` désigne la demande en cours d'examen (ligne 4 du modèle) ; les autres
    justifications soumises avant `date` forment les « dépenses déjà justifiées » (ligne 5).
    """
    _compte_special(compte)
    situation = SituationCompteSpecial(compte_code=compte.code, devise=compte.devise_id, date=date)
    mouvements = {
        m.pk: m
        for m in MouvementReleve.objects.filter(
            compte=compte, date_operation__lte=date, montant__gt=0
        )
    }
    par_demande: dict[str, Decimal] = {}
    for appariement in AppariementDemande.objects.filter(
        mouvement__in=list(mouvements), annule_at__isnull=True
    ).select_related("demande"):
        numero = appariement.demande.numero
        par_demande[numero] = (
            par_demande.get(numero, ZERO) + mouvements[appariement.mouvement_id].montant
        )
    situation.avances = sorted(par_demande.items())
    situation.solde_cloture, _ = solde_releve_a(compte, date)
    if situation.solde_cloture is None:
        situation.manques.append("cloture")
    for justification in JustificationCompteSpecial.objects.filter(
        compte=compte, annule_at__isnull=True, date_soumission__lte=date
    ).select_related("demande"):
        if demande_numero is not None and justification.demande.numero == demande_numero:
            situation.justifie_cette_demande += justification.montant
        else:
            situation.justifie_precedemment += justification.montant
    return situation


def justifier_aupres_de_la_banque(
    *,
    utilisateur,
    compte: CompteBancaire,
    demande: DemandeRetrait,
    montant,
    date_soumission: datetime.date | None = None,
) -> JustificationCompteSpecial:
    """Enregistre les dépenses justifiées à la Banque sous une demande, pour un compte spécial."""
    habilite(utilisateur, "saisir", compte.project_id)
    _compte_special(compte)
    montant = nombre_decimal(montant, "montant", signe="positif")
    try:
        with transaction.atomic():
            # Le verrou de la demande sérialise deux justifications concurrentes de la même demande.
            DemandeRetrait.objects.select_for_update().get(pk=demande.pk)
            if JustificationCompteSpecial.objects.filter(
                compte=compte, demande=demande, annule_at__isnull=True
            ).exists():
                refuser("compte_special.deja_justifiee", demande=demande.numero)
            justification = JustificationCompteSpecial.objects.create(
                org_id=compte.org_id,
                compte=compte,
                demande=demande,
                project_id=compte.project_id,
                montant=montant,
                date_soumission=date_soumission or timezone.localdate(),
                saisie_par=utilisateur.id,
                created_by=utilisateur.id,
            )
            journaliser(
                org_id=justification.org_id,
                actor_id=utilisateur.id,
                action="sa_justification_recorded",
                object_type="demande_retrait",
                object_id=demande.id,
                project_id=compte.project_id,
                after={"compte": compte.code, "montant": str(montant)},
            )
    except IntegrityError as erreur:
        raise traduire_integrite(
            erreur,
            {
                "uq_justifcs_une_par_demande": (
                    "compte_special.deja_justifiee",
                    {"demande": demande.numero},
                )
            },
            defaut="compte_special.justification_refusee",
        ) from erreur
    return justification


def annuler_justification(
    *, utilisateur, justification: JustificationCompteSpecial, motif: str
) -> JustificationCompteSpecial:
    """Annule la justification (motivée, une seule fois) ; on enregistre ensuite la bonne."""
    habilite(utilisateur, "saisir", justification.project_id)
    if not (motif or "").strip():
        refuser("compte_special.annulation_motivee")
    with transaction.atomic():
        courante = JustificationCompteSpecial.objects.select_for_update().get(pk=justification.pk)
        if courante.annule_at is not None:
            raise ErreurMetier(CodeErreur.TRANSITION_INTERDITE, msg("compte_special.deja_annulee"))
        courante.annule_at = timezone.now()
        courante.annule_par = utilisateur.id
        courante.motif_annulation = motif.strip()
        courante.save(update_fields=["annule_at", "annule_par", "motif_annulation", "updated_at"])
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action="sa_justification_cancelled",
            object_type="demande_retrait",
            object_id=courante.demande_id,
            project_id=courante.project_id,
            after={"motif": courante.motif_annulation},
        )
    justification.refresh_from_db()
    return justification
