"""Contrats, avenants versionnés, garanties et assurances, avec échéances et alertes. L9-T03.

Le contrat porte sa valeur initiale ; chaque avenant porte la valeur SUIVANTE (montant total, date
de fin) sans rien modifier : la valeur courante est celle du dernier avenant. Les avenants sont
numérotés sans trou. Une garantie a une échéance ; les alertes se calculent à la date du jour, avec
un horizon que l'appelant choisit (aucun délai n'est supposé).
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.referentiels.models import Tiers

from .avis import avis_manquants
from .models import (
    AvenantContrat,
    AvisNonObjection,
    Contrat,
    Garantie,
    LignePassation,
    ObjetAvis,
    StatutAvis,
    StatutGarantie,
    StatutLigne,
    TypeGarantie,
)


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
    if not nombre.is_finite() or isinstance(valeur, float) or nombre <= 0:
        _refuser("passation.montant_invalide", champ=champ)
    return nombre


# --- le contrat et ses avenants ----------------------------------------------------------------


def conclure_contrat(
    *,
    utilisateur,
    ligne: LignePassation,
    reference: str,
    tiers: Tiers,
    objet: str,
    montant,
    date_signature: datetime.date,
    date_debut: datetime.date,
    date_fin: datetime.date,
) -> Contrat:
    """Conclut le contrat d'un marché attribué, dans la devise de la ligne.

    Si le marché est soumis à non-objection, son avis doit être obtenu : sinon refus.
    """
    _habilite(utilisateur, "saisir", ligne.project_id)
    if not (reference or "").strip() or not (objet or "").strip():
        _refuser("passation.code_obligatoire")
    montant = _montant(montant, "montant")
    if date_fin < date_debut:
        _refuser("passation.contrat_periode")
    courante = LignePassation.objects.get(pk=ligne.pk)
    if courante.statut not in (StatutLigne.ATTRIBUE, StatutLigne.SIGNE):
        raise ErreurMetier(
            CodeErreur.TRANSITION_INTERDITE,
            msg("passation.contrat_marche_non_attribue", reference=courante.reference),
        )
    manquants = avis_manquants(courante)
    if manquants:
        _refuser(
            "passation.contrat_sans_avis",
            reference=courante.reference,
            objets=", ".join(m for m in manquants if m) or "—",
        )
    try:
        with transaction.atomic():
            contrat = Contrat.objects.create(
                org_id=courante.org_id,
                ligne=courante,
                project_id=courante.project_id,
                reference=reference.strip(),
                tiers=tiers,
                objet=objet.strip(),
                montant_initial=montant,
                devise=courante.devise,
                date_signature=date_signature,
                date_debut=date_debut,
                date_fin_initiale=date_fin,
                created_by=utilisateur.id,
            )
            journaliser(
                org_id=contrat.org_id,
                actor_id=utilisateur.id,
                action="contract_concluded",
                object_type="contrat",
                object_id=contrat.id,
                project_id=contrat.project_id,
                after={
                    "reference": contrat.reference,
                    "marche": courante.reference,
                    "montant": str(montant),
                    "devise": contrat.devise,
                },
            )
    except IntegrityError:
        _refuser("passation.contrat_existe", reference=reference.strip())
    return contrat


def montant_courant(contrat: Contrat) -> Decimal:
    dernier = contrat.avenants.order_by("-numero").first()
    return dernier.montant if dernier else contrat.montant_initial


def date_fin_courante(contrat: Contrat) -> datetime.date:
    dernier = contrat.avenants.order_by("-numero").first()
    return dernier.date_fin if dernier else contrat.date_fin_initiale


def ajouter_avenant(
    *,
    utilisateur,
    contrat: Contrat,
    date_effet: datetime.date,
    montant,
    date_fin: datetime.date,
    motif: str,
    avis: AvisNonObjection | None = None,
) -> AvenantContrat:
    """Ajoute l'avenant suivant, qui porte le nouveau montant total et la nouvelle date de fin.

    Sur un marché soumis à non-objection, `avis` doit être un avis obtenu d'objet « avenant » de
    la même ligne, qu'aucun autre avenant n'a déjà utilisé.
    """
    _habilite(utilisateur, "saisir", contrat.project_id)
    if not (motif or "").strip():
        _refuser("passation.avenant_motif")
    montant = _montant(montant, "montant")
    with transaction.atomic():
        # Le verrou sur le contrat sérialise les avenants simultanés : numérotation sans trou.
        verrouille = Contrat.objects.select_for_update().get(pk=contrat.pk)
        ligne = verrouille.ligne
        if ligne.non_objection_requise:
            if (
                avis is None
                or avis.ligne_id != ligne.id
                or avis.objet != ObjetAvis.AVENANT
                or AvisNonObjection.objects.get(pk=avis.pk).statut != StatutAvis.OBTENU
            ):
                _refuser("passation.avenant_sans_avis", reference=verrouille.reference)
            if AvenantContrat.objects.filter(avis=avis).exists():
                _refuser("passation.avenant_avis_deja_utilise")
        elif avis is not None:
            _refuser("passation.avenant_avis_inutile", reference=verrouille.reference)
        precedent = verrouille.avenants.order_by("-numero").first()
        numero = (precedent.numero if precedent else 0) + 1
        plancher = precedent.date_effet if precedent else verrouille.date_signature
        if date_effet < plancher:
            _refuser("passation.avenant_date_anterieure", date=plancher.isoformat())
        if date_fin < verrouille.date_debut:
            _refuser("passation.contrat_periode")
        avenant = AvenantContrat.objects.create(
            org_id=verrouille.org_id,
            contrat=verrouille,
            project_id=verrouille.project_id,
            numero=numero,
            date_effet=date_effet,
            montant=montant,
            date_fin=date_fin,
            motif=motif.strip(),
            avis=avis,
            cree_par=utilisateur.id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=avenant.org_id,
            actor_id=utilisateur.id,
            action="contract_amended",
            object_type="contrat",
            object_id=verrouille.id,
            project_id=verrouille.project_id,
            before={"montant": str(precedent.montant if precedent else verrouille.montant_initial)},
            after={
                "numero": numero,
                "montant": str(montant),
                "date_fin": date_fin.isoformat(),
                "motif": avenant.motif,
            },
        )
    return avenant


# --- les garanties et assurances ---------------------------------------------------------------


def enregistrer_garantie(
    *,
    utilisateur,
    contrat: Contrat,
    type_garantie: str,
    emetteur: str,
    reference: str,
    montant,
    date_emission: datetime.date,
    date_echeance: datetime.date,
) -> Garantie:
    _habilite(utilisateur, "saisir", contrat.project_id)
    if type_garantie not in TypeGarantie.values:
        _refuser("passation.garantie_type_inconnu", type=type_garantie)
    if not (emetteur or "").strip() or not (reference or "").strip():
        _refuser("passation.code_obligatoire")
    montant = _montant(montant, "montant")
    if date_echeance < date_emission:
        _refuser("passation.garantie_periode")
    try:
        with transaction.atomic():
            garantie = Garantie.objects.create(
                org_id=contrat.org_id,
                contrat=contrat,
                project_id=contrat.project_id,
                type_garantie=type_garantie,
                emetteur=emetteur.strip(),
                reference=reference.strip(),
                montant=montant,
                devise=contrat.devise,
                date_emission=date_emission,
                date_echeance=date_echeance,
                created_by=utilisateur.id,
            )
            journaliser(
                org_id=garantie.org_id,
                actor_id=utilisateur.id,
                action="guarantee_recorded",
                object_type="garantie",
                object_id=garantie.id,
                project_id=garantie.project_id,
                after={
                    "contrat": contrat.reference,
                    "type": type_garantie,
                    "montant": str(montant),
                    "echeance": date_echeance.isoformat(),
                },
            )
    except IntegrityError:
        _refuser("passation.garantie_existe", reference=reference.strip())
    return garantie


def cloturer_garantie(
    *, utilisateur, garantie: Garantie, statut: str, date_cloture: datetime.date, note: str = ""
) -> Garantie:
    """Libère la garantie (mainlevée) ou la déclare appelée (motivé). Définitif."""
    _habilite(utilisateur, "saisir", garantie.project_id)
    if statut not in (StatutGarantie.LIBEREE, StatutGarantie.APPELEE):
        _refuser("passation.garantie_statut_invalide", statut=statut)
    if statut == StatutGarantie.APPELEE and not (note or "").strip():
        _refuser("passation.garantie_appel_motive")
    with transaction.atomic():
        courante = Garantie.objects.select_for_update().get(pk=garantie.pk)
        if courante.statut != StatutGarantie.ACTIVE:
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("passation.garantie_definitive", statut=courante.statut),
            )
        if date_cloture < courante.date_emission:
            _refuser(
                "passation.garantie_cloture_anterieure", date=courante.date_emission.isoformat()
            )
        courante.statut = statut
        courante.date_cloture = date_cloture
        courante.note_cloture = (note or "").strip()
        courante.save(update_fields=["statut", "date_cloture", "note_cloture", "updated_at"])
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action="guarantee_closed",
            object_type="garantie",
            object_id=courante.id,
            project_id=courante.project_id,
            before={"statut": StatutGarantie.ACTIVE},
            after={
                "statut": statut,
                "date": date_cloture.isoformat(),
                "note": courante.note_cloture,
            },
        )
    garantie.refresh_from_db()
    return garantie


# --- les alertes d'échéance --------------------------------------------------------------------


@dataclass(frozen=True)
class Alerte:
    nature: str  # "garantie" ou "contrat"
    objet: object  # la garantie ou le contrat concerné
    reference: str
    echeance: datetime.date
    jours_restants: int  # négatif : échéance dépassée
    etat: str  # "depassee" ou "proche"


def alertes_echeances(
    *, utilisateur, project_id, jour: datetime.date, horizon_jours: int
) -> list[Alerte]:
    """Garanties actives et contrats arrivant à échéance dans `horizon_jours`, ou déjà dépassés.

    Le plus urgent d'abord. L'horizon est choisi par l'appelant : aucun délai n'est supposé. Un
    contrat s'évalue à sa date de fin COURANTE (celle du dernier avenant).
    """
    _habilite(utilisateur, "consulter", project_id)
    if not isinstance(horizon_jours, int) or horizon_jours < 0:
        _refuser("passation.horizon_invalide")
    limite = jour + datetime.timedelta(days=horizon_jours)
    alertes = []
    for g in Garantie.objects.filter(
        project_id=project_id, statut=StatutGarantie.ACTIVE, date_echeance__lte=limite
    ).select_related("contrat"):
        alertes.append(_alerte("garantie", g, g.reference, g.date_echeance, jour))
    for c in Contrat.objects.filter(project_id=project_id):
        fin = date_fin_courante(c)
        if fin <= limite:
            alertes.append(_alerte("contrat", c, c.reference, fin, jour))
    return sorted(alertes, key=lambda a: (a.echeance, a.nature, a.reference))


def _alerte(nature, objet, reference, echeance, jour) -> Alerte:
    restants = (echeance - jour).days
    return Alerte(
        nature, objet, reference, echeance, restants, "depassee" if restants < 0 else "proche"
    )
