"""Décomptes, apurement des engagements, paiements et soldes contractuels. Voir L9-T04.

Un décompte est soumis par une personne, certifié par une AUTRE (habilitation « valider »). La
certification apure, dans la même transaction, l'engagement du marché du contrat : c'est ce qui
libère le disponible budgétaire que cet engagement réservait. Les montants du décompte sont dans
la devise du contrat ; l'apurement est en monnaie de tenue du projet (identique si les devises
coïncident, sinon donné explicitement par le certificateur : aucun taux n'est supposé).
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Sum
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from niveau1_socle.budget.engagements import apurer_verrouille
from niveau1_socle.budget.models import Engagement
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.organisations.models import Projet

from .contrats import montant_courant
from .models import Contrat, Decompte, Paiement, StatutDecompte

ZERO = Decimal("0")
CENT = Decimal("100")


def _habilite(utilisateur, operation: str, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(msg("passation.habilitation_requise", operation=operation))


def _refuser(cle: str, **params):
    raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg(cle, **params))


def _nombre(valeur, champ: str, *, strict: bool = True) -> Decimal:
    try:
        nombre = Decimal(str(valeur))
    except InvalidOperation:
        _refuser("passation.montant_invalide", champ=champ)
    if (
        not nombre.is_finite()
        or isinstance(valeur, float)
        or nombre < 0
        or (strict and nombre == 0)
    ):
        _refuser("passation.montant_invalide", champ=champ)
    return nombre


# --- soumission, certification, rejet ----------------------------------------------------------


def soumettre_decompte(
    *,
    utilisateur,
    contrat: Contrat,
    date_decompte: datetime.date,
    montant_brut,
    avancement_physique,
    retenue=0,
    facture_reference: str = "",
    facture_date: datetime.date | None = None,
) -> Decompte:
    """Soumet le décompte suivant du contrat (numéroté sans trou). Rien n'est encore apuré."""
    _habilite(utilisateur, "saisir", contrat.project_id)
    brut = _nombre(montant_brut, "montant_brut")
    retenue = _nombre(retenue, "retenue", strict=False)
    avancement = _nombre(avancement_physique, "avancement_physique", strict=False)
    if retenue > brut:
        _refuser("passation.decompte_retenue")
    if avancement > CENT:
        _refuser("passation.decompte_avancement")
    if date_decompte < contrat.date_debut:
        _refuser("passation.decompte_avant_contrat", date=contrat.date_debut.isoformat())
    with transaction.atomic():
        # Le verrou sur le contrat sérialise les soumissions simultanées : numérotation sans trou.
        verrouille = Contrat.objects.select_for_update().get(pk=contrat.pk)
        dernier = verrouille.decomptes.order_by("-numero").first()
        decompte = Decompte.objects.create(
            org_id=verrouille.org_id,
            contrat=verrouille,
            project_id=verrouille.project_id,
            numero=(dernier.numero if dernier else 0) + 1,
            date_decompte=date_decompte,
            montant_brut=brut,
            retenue=retenue,
            avancement_physique=avancement,
            facture_reference=(facture_reference or "").strip(),
            facture_date=facture_date,
            soumis_par=utilisateur.id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=decompte.org_id,
            actor_id=utilisateur.id,
            action="statement_submitted",
            object_type="decompte",
            object_id=decompte.id,
            project_id=decompte.project_id,
            after={
                "contrat": verrouille.reference,
                "numero": decompte.numero,
                "brut": str(brut),
                "retenue": str(retenue),
                "avancement": str(avancement),
            },
        )
    return decompte


def certifier_decompte(
    *,
    utilisateur,
    decompte: Decompte,
    engagement: Engagement,
    date_certification: datetime.date,
    montant_apure=None,
) -> Decompte:
    """Certifie le décompte et apure l'engagement du marché, dans la même transaction.

    Refus : même personne que l'auteur ; engagement d'un autre marché ; dépassement du montant
    courant du contrat ; avancement physique qui recule ; apurement supérieur au reste de
    l'engagement. Tout échec défait tout : ni certification ni apurement partiel.
    """
    _habilite(utilisateur, "valider", decompte.project_id)
    with transaction.atomic():
        verrouille_contrat = Contrat.objects.select_for_update().get(pk=decompte.contrat_id)
        courant = Decompte.objects.select_for_update().get(pk=decompte.pk)
        if courant.statut != StatutDecompte.SOUMIS:
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("passation.decompte_definitif", statut=courant.statut),
            )
        if courant.soumis_par == utilisateur.id:
            _refuser("passation.decompte_meme_personne")
        if date_certification < courant.date_decompte:
            _refuser("passation.decompte_date_anterieure", date=courant.date_decompte.isoformat())
        engagement_v = Engagement.objects.select_for_update().get(pk=engagement.pk)
        if engagement_v.ligne_passation_id != verrouille_contrat.ligne_id:
            _refuser("passation.decompte_autre_engagement", reference=engagement_v.reference)
        projet = Projet.objects.get(pk=courant.project_id)
        if montant_apure is None:
            if projet.base_currency != verrouille_contrat.devise:
                _refuser(
                    "passation.decompte_devise_differente",
                    contrat=verrouille_contrat.devise,
                    projet=projet.base_currency,
                )
            apure = courant.montant_brut
        else:
            apure = _nombre(montant_apure, "montant_apure")
            if projet.base_currency == verrouille_contrat.devise and apure != courant.montant_brut:
                _refuser("passation.decompte_apurement_different")
        certifie_avant = (
            Decompte.objects.filter(contrat=verrouille_contrat, statut=StatutDecompte.CERTIFIE)
            .exclude(pk=courant.pk)
            .aggregate(total=Sum("montant_brut"))["total"]
            or ZERO
        )
        plafond = montant_courant(verrouille_contrat)
        if certifie_avant + courant.montant_brut > plafond:
            _refuser(
                "passation.decompte_depasse_contrat",
                total=certifie_avant + courant.montant_brut,
                plafond=plafond,
            )
        recul = (
            Decompte.objects.filter(contrat=verrouille_contrat, statut=StatutDecompte.CERTIFIE)
            .exclude(pk=courant.pk)
            .order_by("-avancement_physique")
            .values_list("avancement_physique", flat=True)
            .first()
        )
        if recul is not None and courant.avancement_physique < recul:
            _refuser(
                "passation.decompte_avancement_recule",
                avancement=courant.avancement_physique,
                precedent=recul,
            )
        # L'apurement d'abord : s'il échoue, rien n'est certifié
        apurer_verrouille(engagement_v, utilisateur=utilisateur, montant=apure)
        courant.statut = StatutDecompte.CERTIFIE
        courant.decide_par = utilisateur.id
        courant.date_decision = date_certification
        courant.engagement = engagement_v
        courant.montant_apure = apure
        courant.save(
            update_fields=[
                "statut",
                "decide_par",
                "date_decision",
                "engagement",
                "montant_apure",
                "updated_at",
            ]
        )
        journaliser(
            org_id=courant.org_id,
            actor_id=utilisateur.id,
            action="statement_certified",
            object_type="decompte",
            object_id=courant.id,
            project_id=courant.project_id,
            before={"statut": StatutDecompte.SOUMIS},
            after={
                "numero": courant.numero,
                "brut": str(courant.montant_brut),
                "engagement": engagement_v.reference,
                "apure": str(apure),
            },
        )
    decompte.refresh_from_db()
    return decompte


def rejeter_decompte(
    *, utilisateur, decompte: Decompte, date_decision: datetime.date, motif: str
) -> Decompte:
    _habilite(utilisateur, "valider", decompte.project_id)
    if not (motif or "").strip():
        _refuser("passation.decompte_rejet_motive")
    with transaction.atomic():
        courant = Decompte.objects.select_for_update().get(pk=decompte.pk)
        if courant.statut != StatutDecompte.SOUMIS:
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("passation.decompte_definitif", statut=courant.statut),
            )
        if date_decision < courant.date_decompte:
            _refuser("passation.decompte_date_anterieure", date=courant.date_decompte.isoformat())
        courant.statut = StatutDecompte.REJETE
        courant.decide_par = utilisateur.id
        courant.date_decision = date_decision
        courant.motif_rejet = motif.strip()
        courant.save(
            update_fields=["statut", "decide_par", "date_decision", "motif_rejet", "updated_at"]
        )
        journaliser(
            org_id=courant.org_id,
            actor_id=utilisateur.id,
            action="statement_rejected",
            object_type="decompte",
            object_id=courant.id,
            project_id=courant.project_id,
            before={"statut": StatutDecompte.SOUMIS},
            after={"numero": courant.numero, "motif": courant.motif_rejet},
        )
    decompte.refresh_from_db()
    return decompte


# --- paiements ---------------------------------------------------------------------------------


def enregistrer_paiement(
    *, utilisateur, decompte: Decompte, reference: str, date_paiement: datetime.date, montant
) -> Paiement:
    """Enregistre un paiement sur un décompte certifié, sans dépasser son net (brut − retenue)."""
    _habilite(utilisateur, "saisir", decompte.project_id)
    if not (reference or "").strip():
        _refuser("passation.code_obligatoire")
    montant = _nombre(montant, "montant")
    try:
        with transaction.atomic():
            courant = Decompte.objects.select_for_update().get(pk=decompte.pk)
            if courant.statut != StatutDecompte.CERTIFIE:
                _refuser("passation.paiement_decompte_non_certifie", numero=courant.numero)
            deja = (
                Paiement.objects.filter(decompte=courant).aggregate(t=Sum("montant"))["t"] or ZERO
            )
            net = courant.montant_brut - courant.retenue
            if deja + montant > net:
                _refuser("passation.paiement_depasse_net", reste=net - deja, montant=montant)
            if date_paiement < courant.date_decision:
                _refuser(
                    "passation.paiement_date_anterieure", date=courant.date_decision.isoformat()
                )
            paiement = Paiement.objects.create(
                org_id=courant.org_id,
                decompte=courant,
                project_id=courant.project_id,
                reference=reference.strip(),
                date_paiement=date_paiement,
                montant=montant,
                enregistre_par=utilisateur.id,
                created_by=utilisateur.id,
            )
            journaliser(
                org_id=paiement.org_id,
                actor_id=utilisateur.id,
                action="statement_payment_recorded",
                object_type="decompte",
                object_id=courant.id,
                project_id=courant.project_id,
                after={"reference": paiement.reference, "montant": str(montant)},
            )
    except IntegrityError:
        _refuser("passation.paiement_existe", reference=reference.strip())
    return paiement


# --- soldes contractuels et taux d'exécution ---------------------------------------------------


@dataclass(frozen=True)
class SituationContrat:
    montant_courant: Decimal
    certifie: Decimal  # Σ montants bruts certifiés
    solde_contractuel: Decimal  # montant courant − certifié
    net_certifie: Decimal  # Σ (brut − retenue) certifiés
    paye: Decimal
    reste_a_payer: Decimal  # net certifié − payé
    taux_financier: Decimal  # certifié / montant courant, en %
    taux_physique: Decimal  # avancement du dernier décompte certifié, en %


def situation_contrat(*, utilisateur, contrat: Contrat) -> SituationContrat:
    """Les soldes du contrat, calculés depuis les décomptes certifiés et les paiements."""
    _habilite(utilisateur, "consulter", contrat.project_id)
    certifies = Decompte.objects.filter(contrat=contrat, statut=StatutDecompte.CERTIFIE)
    totaux = certifies.aggregate(brut=Sum("montant_brut"), retenue=Sum("retenue"))
    certifie = totaux["brut"] or ZERO
    net = certifie - (totaux["retenue"] or ZERO)
    paye = Paiement.objects.filter(decompte__in=certifies).aggregate(t=Sum("montant"))["t"] or ZERO
    courant = montant_courant(contrat)
    dernier = certifies.order_by("-numero").first()
    return SituationContrat(
        montant_courant=courant,
        certifie=certifie,
        solde_contractuel=courant - certifie,
        net_certifie=net,
        paye=paye,
        reste_a_payer=net - paye,
        taux_financier=(certifie * CENT / courant).quantize(Decimal("0.01")),
        taux_physique=dernier.avancement_physique if dernier else ZERO,
    )
