"""Décomptes, apurement des engagements, paiements et soldes contractuels. Voir L9-T04.

Un décompte est soumis par une personne, certifié par une AUTRE (habilitation « valider »). La
certification apure, dans la même transaction, l'engagement du marché du contrat : c'est ce qui
libère le disponible budgétaire que cet engagement réservait. Les montants du décompte sont dans
la devise du contrat ; l'apurement est en monnaie de tenue du projet (identique si les devises
coïncident, sinon donné explicitement par le certificateur : aucun taux n'est supposé).
"""

import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Max, Sum

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from core.metier import decimal as nombre_decimal
from core.metier import habilite, refuser, traduire_integrite
from niveau1_socle.budget.engagements import apurer_verrouille
from niveau1_socle.budget.models import Engagement
from niveau1_socle.comptabilite.services import saisir_ecriture
from niveau1_socle.financements.models import CompteBancaire
from niveau1_socle.organisations.models import Projet
from niveau1_socle.referentiels.models import Devise

from .contrats import montant_courant
from .models import Contrat, Decompte, Paiement, StatutDecompte

ZERO = Decimal("0")
CENT = Decimal("100")


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
    habilite(utilisateur, "saisir", contrat.project_id)
    brut = nombre_decimal(montant_brut, "montant_brut")
    retenue = nombre_decimal(retenue, "retenue", signe="positif_ou_nul")
    avancement = nombre_decimal(avancement_physique, "avancement_physique", signe="positif_ou_nul")
    if retenue > brut:
        refuser("passation.decompte_retenue")
    if avancement > CENT:
        refuser("passation.decompte_avancement")
    if date_decompte < contrat.date_debut:
        refuser("passation.decompte_avant_contrat", date=contrat.date_debut.isoformat())
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
    habilite(utilisateur, "valider", decompte.project_id)
    with transaction.atomic():
        verrouille_contrat = Contrat.objects.select_for_update().get(pk=decompte.contrat_id)
        courant = Decompte.objects.select_for_update().get(pk=decompte.pk)
        if courant.statut != StatutDecompte.SOUMIS:
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("passation.decompte_definitif", statut=courant.statut),
            )
        if courant.soumis_par == utilisateur.id:
            refuser("passation.decompte_meme_personne")
        if date_certification < courant.date_decompte:
            refuser("passation.decompte_date_anterieure", date=courant.date_decompte.isoformat())
        engagement_v = Engagement.objects.select_for_update().get(pk=engagement.pk)
        if engagement_v.ligne_passation_id != verrouille_contrat.ligne_id:
            refuser("passation.decompte_autre_engagement", reference=engagement_v.reference)
        projet = Projet.objects.get(pk=courant.project_id)
        if montant_apure is None:
            if projet.base_currency != verrouille_contrat.devise:
                refuser(
                    "passation.decompte_devise_differente",
                    contrat=verrouille_contrat.devise,
                    projet=projet.base_currency,
                )
            apure = courant.montant_brut
        else:
            apure = nombre_decimal(montant_apure, "montant_apure")
            if projet.base_currency == verrouille_contrat.devise and apure != courant.montant_brut:
                refuser("passation.decompte_apurement_different")
        certifie_avant = (
            Decompte.objects.filter(contrat=verrouille_contrat, statut=StatutDecompte.CERTIFIE)
            .exclude(pk=courant.pk)
            .aggregate(total=Sum("montant_brut"))["total"]
            or ZERO
        )
        plafond = montant_courant(verrouille_contrat)
        if certifie_avant + courant.montant_brut > plafond:
            refuser(
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
            refuser(
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
    habilite(utilisateur, "valider", decompte.project_id)
    if not (motif or "").strip():
        refuser("passation.decompte_rejet_motive")
    with transaction.atomic():
        courant = Decompte.objects.select_for_update().get(pk=decompte.pk)
        if courant.statut != StatutDecompte.SOUMIS:
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("passation.decompte_definitif", statut=courant.statut),
            )
        if date_decision < courant.date_decompte:
            refuser("passation.decompte_date_anterieure", date=courant.date_decompte.isoformat())
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
    *,
    utilisateur,
    decompte: Decompte,
    reference: str,
    date_paiement: datetime.date,
    montant,
    compte_bancaire: CompteBancaire,
    compte_fournisseur: str,
    compte_banque: str,
    journal: str,
    taux=None,
) -> Paiement:
    """Enregistre un paiement sur un décompte certifié, sans dépasser son net (brut − retenue), et
    l'ÉCRIT au grand livre : fournisseur (tiers du contrat) au débit, banque au crédit.

    L'écriture naît BROUILLON : elle suit le cycle ordinaire (validée par une autre personne, puis
    comptabilisée), comme toute saisie. Aucun compte, journal ni taux n'est supposé : l'appelant les
    donne. Le compte bancaire est dans la devise du contrat ; si cette devise n'est pas la monnaie
    de tenue du projet, `taux` (vers la monnaie de tenue) est obligatoire et le montant converti
    est arrondi à la devise de tenue. Le paiement et son écriture naissent ensemble ou pas du tout.
    """
    habilite(utilisateur, "saisir", decompte.project_id)
    if not (reference or "").strip():
        refuser("passation.code_obligatoire")
    montant = nombre_decimal(montant, "montant")
    try:
        with transaction.atomic():
            courant = Decompte.objects.select_for_update().get(pk=decompte.pk)
            if courant.statut != StatutDecompte.CERTIFIE:
                refuser("passation.paiement_decompte_non_certifie", numero=courant.numero)
            deja = (
                Paiement.objects.filter(decompte=courant).aggregate(t=Sum("montant"))["t"] or ZERO
            )
            net = courant.montant_brut - courant.retenue
            if deja + montant > net:
                refuser("passation.paiement_depasse_net", reste=net - deja, montant=montant)
            if date_paiement < courant.date_decision:
                refuser(
                    "passation.paiement_date_anterieure", date=courant.date_decision.isoformat()
                )
            contrat = courant.contrat
            ecriture = _ecrire_le_paiement(
                utilisateur=utilisateur,
                contrat=contrat,
                decompte=courant,
                reference=reference.strip(),
                date_paiement=date_paiement,
                montant=montant,
                compte_bancaire=compte_bancaire,
                compte_fournisseur=compte_fournisseur,
                compte_banque=compte_banque,
                journal=journal,
                taux=taux,
            )
            paiement = Paiement.objects.create(
                org_id=courant.org_id,
                decompte=courant,
                project_id=courant.project_id,
                reference=reference.strip(),
                date_paiement=date_paiement,
                montant=montant,
                enregistre_par=utilisateur.id,
                ecriture=ecriture,
                created_by=utilisateur.id,
            )
            journaliser(
                org_id=paiement.org_id,
                actor_id=utilisateur.id,
                action="statement_payment_recorded",
                object_type="decompte",
                object_id=courant.id,
                project_id=courant.project_id,
                after={
                    "reference": paiement.reference,
                    "montant": str(montant),
                    "ecriture": str(ecriture.id),
                },
            )
    except IntegrityError as erreur:
        raise traduire_integrite(
            erreur,
            {
                "uq_paiement_reference": (
                    "passation.paiement_existe",
                    {"reference": reference.strip()},
                )
            },
        ) from erreur
    return paiement


def _ecrire_le_paiement(
    *,
    utilisateur,
    contrat: Contrat,
    decompte: Decompte,
    reference: str,
    date_paiement: datetime.date,
    montant: Decimal,
    compte_bancaire: CompteBancaire,
    compte_fournisseur: str,
    compte_banque: str,
    journal: str,
    taux,
):
    """Le brouillon d'écriture d'un paiement : équilibré en monnaie de tenue ET en devise."""
    if compte_bancaire.devise_id != contrat.devise:
        refuser(
            "passation.paiement_devise_compte",
            compte=compte_bancaire.devise_id,
            contrat=contrat.devise,
        )
    projet = Projet.objects.get(pk=contrat.project_id)
    etrangere = contrat.devise != projet.base_currency
    if etrangere:
        if taux is None:
            refuser(
                "passation.paiement_taux_obligatoire",
                devise=contrat.devise,
                base=projet.base_currency,
            )
        facteur = nombre_decimal(taux, "taux")
        decimales = Devise.objects.get(pk=projet.base_currency).decimales
        en_base = (montant * facteur).quantize(
            Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP
        )
        lignes = [
            {
                "compte": compte_fournisseur,
                "debit": en_base,
                "debit_cur": montant,
                "tiers": contrat.tiers.code,
                "contract_id": contrat.id,
            },
            {
                "compte": compte_banque,
                "credit": en_base,
                "credit_cur": montant,
                "bank_account_id": compte_bancaire.id,
            },
        ]
        taux_ecriture = facteur
    else:
        lignes = [
            {
                "compte": compte_fournisseur,
                "debit": montant,
                "tiers": contrat.tiers.code,
                "contract_id": contrat.id,
            },
            {"compte": compte_banque, "credit": montant, "bank_account_id": compte_bancaire.id},
        ]
        taux_ecriture = 1
    return saisir_ecriture(
        utilisateur=utilisateur,
        project_id=contrat.project_id,
        journal=journal,
        date_comptable=date_paiement,
        libelle=f"Paiement {reference} — décompte {decompte.numero} du contrat {contrat.reference}",
        lignes=lignes,
        devise=contrat.devise,
        taux=taux_ecriture,
        reference_piece=reference,
        cle_idempotence=f"paiement-decompte:{decompte.id}:{reference}",
    )


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
    taux_physique: Decimal  # avancement cumulé le plus élevé des décomptes certifiés, en %


def situation_contrat(*, utilisateur, contrat: Contrat) -> SituationContrat:
    """Les soldes du contrat, calculés depuis les décomptes certifiés et les paiements."""
    habilite(utilisateur, "consulter", contrat.project_id)
    certifies = Decompte.objects.filter(contrat=contrat, statut=StatutDecompte.CERTIFIE)
    totaux = certifies.aggregate(brut=Sum("montant_brut"), retenue=Sum("retenue"))
    certifie = totaux["brut"] or ZERO
    net = certifie - (totaux["retenue"] or ZERO)
    paye = Paiement.objects.filter(decompte__in=certifies).aggregate(t=Sum("montant"))["t"] or ZERO
    courant = montant_courant(contrat)
    avancement_max = certifies.aggregate(m=Max("avancement_physique"))["m"]
    return SituationContrat(
        montant_courant=courant,
        certifie=certifie,
        solde_contractuel=courant - certifie,
        net_certifie=net,
        paye=paye,
        reste_a_payer=net - paye,
        taux_financier=(certifie * CENT / courant).quantize(Decimal("0.01")),
        taux_physique=avancement_max if avancement_max is not None else ZERO,
    )
