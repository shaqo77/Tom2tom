"""Bailleurs, accords, catégories, avenants, comptes bancaires. Voir L4-T04.

Habilitations : tout ce qui se paramètre (bailleur, accord, catégorie, avenant, compte) demande
`parametrer` ; le numéro complet d'un compte demande `voir_numero_compte`, et chaque lecture est
journalisée, comme pour les coordonnées bancaires d'un tiers.
"""

import datetime
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.i18n import libelle, msg
from niveau1_socle.exercices.services import TransitionInterdite
from niveau1_socle.habilitations.models import Habilitation
from niveau1_socle.habilitations.permissions import est_habilite
from niveau3_config.models import DocumentReference

from .models import (
    Accord,
    AvenantAccord,
    Bailleur,
    Categorie,
    CompteBancaire,
    StatutAccord,
)

ZERO = Decimal(0)
TRANSITIONS = {
    StatutAccord.BROUILLON: {StatutAccord.ACTIF, StatutAccord.ANNULE},
    StatutAccord.ACTIF: {StatutAccord.SUSPENDU, StatutAccord.CLOS, StatutAccord.ANNULE},
    StatutAccord.SUSPENDU: {StatutAccord.ACTIF, StatutAccord.CLOS},
    StatutAccord.CLOS: set(),
    StatutAccord.ANNULE: set(),
}


class FinancementInvalide(ValueError):
    """Une donnée de financement ne respecte pas les règles."""


class AccordNonActif(ValueError):
    """L'accord n'accepte pas de nouvelle imputation ni de nouvelle demande de décaissement."""


def _habilite(utilisateur, operation: str, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(msg("financements.vous_etes_habilite_projet", operation=operation))


def _habilite_quelque_part(utilisateur, operation: str) -> None:
    """Pour ce qui ne dépend d'aucun projet (le bailleur appartient à l'organisation)."""
    if not Habilitation.objects.filter(
        user_id=utilisateur.id, role__operations__contains=[operation]
    ).exists():
        raise PermissionDenied(msg("financements.vous_etes_habilite", operation=operation))


# --- bailleurs ------------------------------------------------------------------------------


def creer_bailleur(*, utilisateur, code: str, nom: str, pays: str = "") -> Bailleur:
    _habilite_quelque_part(utilisateur, "parametrer")
    if not (code or "").strip() or not (nom or "").strip():
        raise FinancementInvalide(msg("financements.code_nom_bailleur_obligatoires"))
    with transaction.atomic():
        bailleur = Bailleur.objects.create(
            org_id=utilisateur.org_id,
            code=code.strip(),
            nom=nom.strip(),
            pays=pays,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=bailleur.org_id,
            actor_id=utilisateur.id,
            action="donor_created",
            object_type="bailleur",
            object_id=bailleur.id,
            after={"code": bailleur.code},
        )
    return bailleur


# --- accords --------------------------------------------------------------------------------


def creer_accord(
    *,
    utilisateur,
    project_id,
    bailleur: Bailleur,
    numero: str,
    nature: str,
    devise: str,
    montant_initial,
    libelle: str = "",
    date_effet: datetime.date | None = None,
    date_fin_eligibilite: datetime.date | None = None,
    date_cloture: datetime.date | None = None,
    date_limite_decaissement: datetime.date | None = None,
) -> Accord:
    """Crée un accord en BROUILLON. Plusieurs accords du même bailleur sur un même projet
    coexistent : numéro unique par organisation, rien d'autre."""
    _habilite(utilisateur, "parametrer", project_id)
    if not (numero or "").strip():
        raise FinancementInvalide(msg("financements.numero_accord_obligatoire"))
    with transaction.atomic():
        accord = Accord.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            bailleur=bailleur,
            numero=numero.strip(),
            libelle=libelle,
            nature=nature,
            devise_id=devise,
            montant_initial=Decimal(str(montant_initial)),
            date_effet=date_effet,
            date_fin_eligibilite=date_fin_eligibilite,
            date_cloture=date_cloture,
            date_limite_decaissement=date_limite_decaissement,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=accord.org_id,
            actor_id=utilisateur.id,
            action="agreement_created",
            object_type="accord",
            object_id=accord.id,
            project_id=project_id,
            after={"numero": accord.numero, "montant_initial": str(accord.montant_initial)},
        )
    return accord


def changer_statut_accord(accord: Accord, nouveau: str, *, utilisateur, motif: str = "") -> Accord:
    """Fait passer l'accord à un autre statut (transitions fermées, vérifiées aussi par la base).

    Suspendre, clore ou annuler exige un motif. Un accord suspendu refuse toute NOUVELLE
    imputation et toute nouvelle demande de décaissement ; son historique reste consultable.
    """
    with transaction.atomic():
        courant = Accord.objects.select_for_update().get(pk=accord.pk)
        _habilite(utilisateur, "parametrer", courant.project_id)
        if nouveau not in StatutAccord.values:
            raise FinancementInvalide(msg("financements.statut_accord_inconnu", nouveau=nouveau))
        if nouveau not in TRANSITIONS[courant.status]:
            raise TransitionInterdite(
                msg("financements.accord_peut_passer", status=courant.status, nouveau=nouveau)
            )
        if nouveau != StatutAccord.ACTIF and not (motif or "").strip():
            raise FinancementInvalide(msg("financements.motif_obligatoire_suspendre_clore_annuler"))
        Accord.objects.filter(pk=courant.pk).update(status=nouveau)
        journaliser(
            org_id=courant.org_id,
            actor_id=utilisateur.id,
            action=f"agreement_{nouveau}",
            object_type="accord",
            object_id=courant.id,
            project_id=courant.project_id,
            before={"status": courant.status},
            after={"status": nouveau, "motif": (motif or "").strip()},
        )
    accord.refresh_from_db()
    return accord


def exiger_accord_actif(agreement_id, *, pour: str = "imputation") -> Accord:
    """Retourne l'accord, ou refuse : seul un accord ACTIF reçoit de nouvelles opérations.

    Point d'appui commun de la saisie d'écritures et, en L4-T06, des demandes de décaissement.
    """
    accord = Accord.objects.filter(pk=agreement_id).first()
    if accord is None:
        raise AccordNonActif(msg("financements.accord_existe", agreement_id=agreement_id))
    if accord.status != StatutAccord.ACTIF:
        raise AccordNonActif(
            msg(
                "financements.accord_aucune_nouvelle_y_possible",
                numero=accord.numero,
                status=accord.status,
                pour=libelle("operation", pour),
            )
        )
    return accord


# --- catégories -----------------------------------------------------------------------------


def creer_categorie(
    *,
    utilisateur,
    accord: Accord,
    code: str,
    label: dict,
    plafond=None,
    parent: Categorie | None = None,
    devise: str | None = None,
) -> Categorie:
    _habilite(utilisateur, "parametrer", accord.project_id)
    with transaction.atomic():
        categorie = Categorie.objects.create(
            org_id=utilisateur.org_id,
            accord=accord,
            code=code.strip(),
            label=label,
            plafond=None if plafond is None else Decimal(str(plafond)),
            parent=parent,
            devise_id=devise or accord.devise_id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=categorie.org_id,
            actor_id=utilisateur.id,
            action="category_created",
            object_type="categorie",
            object_id=categorie.id,
            project_id=accord.project_id,
            after={"accord": accord.numero, "code": categorie.code},
        )
    return categorie


# --- avenants -------------------------------------------------------------------------------


def montant_courant(accord: Accord, date: datetime.date | None = None) -> Decimal:
    """Le montant de l'accord à une date : celui du dernier avenant daté au plus tard ce jour-là,
    sinon le montant initial. L'accord, lui, ne change jamais de montant."""
    avenants = AvenantAccord.objects.filter(accord=accord)
    if date is not None:
        avenants = avenants.filter(date_avenant__lte=date)
    dernier = avenants.order_by("-date_avenant", "-created_at").first()
    return dernier.montant_revise if dernier else accord.montant_initial


def situation_avant_apres(avenant: AvenantAccord) -> dict:
    """La situation de l'accord juste avant et juste après un avenant."""
    veille = avenant.date_avenant - datetime.timedelta(days=1)
    avant = montant_courant(avenant.accord, veille)
    return {
        "reference": avenant.reference,
        "date": avenant.date_avenant,
        "montant_avant": avant,
        "montant_apres": avenant.montant_revise,
        "variation": avenant.montant_revise - avant,
        "profile_version_id": avenant.profile_version_id,
    }


def creer_avenant(
    *,
    utilisateur,
    accord: Accord,
    reference: str,
    date_avenant: datetime.date,
    document: DocumentReference,
    montant_revise,
    motif: str = "",
    profile_version_id=None,
) -> AvenantAccord:
    """Enregistre un avenant : nouvelle valeur du montant, sans toucher à l'accord."""
    _habilite(utilisateur, "parametrer", accord.project_id)
    with transaction.atomic():
        avenant = AvenantAccord.objects.create(
            org_id=utilisateur.org_id,
            accord=accord,
            reference=reference.strip(),
            date_avenant=date_avenant,
            document=document,
            montant_revise=Decimal(str(montant_revise)),
            motif=motif,
            profile_version_id=profile_version_id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=avenant.org_id,
            actor_id=utilisateur.id,
            action="agreement_amended",
            object_type="avenant",
            object_id=avenant.id,
            project_id=accord.project_id,
            before={"montant": str(montant_courant(accord, date_avenant - datetime.timedelta(1)))},
            after={"reference": avenant.reference, "montant_revise": str(avenant.montant_revise)},
        )
    return avenant


# --- comptes bancaires ----------------------------------------------------------------------


def creer_compte_bancaire(
    *,
    utilisateur,
    project_id,
    code: str,
    type: str,
    devise: str,
    banque: str,
    numero: str,
    accord: Accord | None = None,
    libelle: str = "",
    plafond=None,
    seuil_reapprovisionnement=None,
) -> CompteBancaire:
    _habilite(utilisateur, "parametrer", project_id)
    if not (numero or "").strip():
        raise FinancementInvalide(msg("financements.numero_compte_obligatoire"))
    with transaction.atomic():
        compte = CompteBancaire.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            accord=accord,
            code=code.strip(),
            libelle=libelle,
            type=type,
            devise_id=devise,
            banque=banque,
            numero=numero.strip(),
            plafond=None if plafond is None else Decimal(str(plafond)),
            seuil_reapprovisionnement=(
                None
                if seuil_reapprovisionnement is None
                else Decimal(str(seuil_reapprovisionnement))
            ),
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=compte.org_id,
            actor_id=utilisateur.id,
            action="bank_account_created",
            object_type="compte_bancaire",
            object_id=compte.id,
            project_id=project_id,
            after={"code": compte.code, "type": type, "numero": compte.numero_masque},
        )
    return compte


def consulter_numero_compte(utilisateur, compte: CompteBancaire) -> str:
    """Le numéro COMPLET, pour qui détient `voir_numero_compte` ; la lecture est journalisée.

    Sans l'habilitation, la lecture est refusée (403). Partout ailleurs, `compte.numero_masque`.
    """
    courant = CompteBancaire.objects.get(pk=compte.pk)
    _habilite(utilisateur, "voir_numero_compte", courant.project_id)
    with transaction.atomic():
        journaliser(
            org_id=courant.org_id,
            actor_id=utilisateur.id,
            action="bank_account_number_read",
            object_type="compte_bancaire",
            object_id=courant.id,
            project_id=courant.project_id,
            after={"code": courant.code},
        )
    return courant.numero
