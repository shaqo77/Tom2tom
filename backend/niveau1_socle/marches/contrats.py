"""Contrats, avenants versionnés, garanties et assurances, avec échéances et alertes. L9-T03.

Le contrat porte sa valeur initiale ; chaque avenant porte la valeur SUIVANTE (montant total, date
de fin) sans rien modifier : la valeur courante est celle du dernier avenant. Les avenants sont
numérotés sans trou. Une garantie a une échéance ; les alertes se calculent à la date du jour, avec
un horizon que l'appelant choisit (aucun délai n'est supposé).
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import DecimalField, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from core.metier import decimal as nombre_decimal
from core.metier import habilite, refuser, traduire_integrite
from niveau1_socle.referentiels.models import Tiers

from .avis import avis_manquants
from .models import (
    AvenantContrat,
    AvisNonObjection,
    Contrat,
    Decompte,
    Garantie,
    LignePassation,
    ObjetAvis,
    Paiement,
    StatutAvis,
    StatutGarantie,
    StatutLigne,
    TypeGarantie,
)

ZERO = Decimal("0")


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
    habilite(utilisateur, "saisir", ligne.project_id)
    if not (reference or "").strip() or not (objet or "").strip():
        refuser("passation.code_obligatoire")
    montant = nombre_decimal(montant, "montant")
    if date_fin < date_debut:
        refuser("passation.contrat_periode")
    courante = LignePassation.objects.get(pk=ligne.pk)
    if courante.statut not in (StatutLigne.ATTRIBUE, StatutLigne.SIGNE):
        raise ErreurMetier(
            CodeErreur.TRANSITION_INTERDITE,
            msg("passation.contrat_marche_non_attribue", reference=courante.reference),
        )
    manquants = avis_manquants(courante)
    if manquants:
        refuser(
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
    except IntegrityError as erreur:
        raise traduire_integrite(
            erreur,
            {
                "uq_contrat_reference": (
                    "passation.contrat_reference_existe",
                    {"reference": reference.strip()},
                ),
                "marches_contrat_ligne_id_key": (
                    "passation.contrat_marche_deja_conclu",
                    {"marche": courante.reference},
                ),
            },
        ) from erreur
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
    habilite(utilisateur, "saisir", contrat.project_id)
    if not (motif or "").strip():
        refuser("passation.avenant_motif")
    montant = nombre_decimal(montant, "montant")
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
                refuser("passation.avenant_sans_avis", reference=verrouille.reference)
            if AvenantContrat.objects.filter(avis=avis).exists():
                refuser("passation.avenant_avis_deja_utilise")
        elif avis is not None:
            refuser("passation.avenant_avis_inutile", reference=verrouille.reference)
        certifie = Decompte.objects.filter(contrat=verrouille, statut="certifie").aggregate(
            t=Sum("montant_brut")
        )["t"] or Decimal("0")
        if montant < certifie:
            refuser("passation.avenant_sous_le_certifie", montant=montant, certifie=certifie)
        precedent = verrouille.avenants.order_by("-numero").first()
        numero = (precedent.numero if precedent else 0) + 1
        plancher = precedent.date_effet if precedent else verrouille.date_signature
        if date_effet < plancher:
            refuser("passation.avenant_date_anterieure", date=plancher.isoformat())
        if date_fin < verrouille.date_debut:
            refuser("passation.contrat_periode")
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
    habilite(utilisateur, "saisir", contrat.project_id)
    if type_garantie not in TypeGarantie.values:
        refuser("passation.garantie_type_inconnu", type=type_garantie)
    if not (emetteur or "").strip() or not (reference or "").strip():
        refuser("passation.code_obligatoire")
    montant = nombre_decimal(montant, "montant")
    if date_echeance < date_emission:
        refuser("passation.garantie_periode")
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
    except IntegrityError as erreur:
        raise traduire_integrite(
            erreur,
            {
                "uq_garantie_reference": (
                    "passation.garantie_existe",
                    {"reference": reference.strip()},
                )
            },
        ) from erreur
    return garantie


def cloturer_garantie(
    *, utilisateur, garantie: Garantie, statut: str, date_cloture: datetime.date, note: str = ""
) -> Garantie:
    """Libère la garantie (mainlevée) ou la déclare appelée (motivé). Définitif."""
    habilite(utilisateur, "saisir", garantie.project_id)
    if statut not in (StatutGarantie.LIBEREE, StatutGarantie.APPELEE):
        refuser("passation.garantie_statut_invalide", statut=statut)
    if statut == StatutGarantie.APPELEE and not (note or "").strip():
        refuser("passation.garantie_appel_motive")
    with transaction.atomic():
        courante = Garantie.objects.select_for_update().get(pk=garantie.pk)
        if courante.statut != StatutGarantie.ACTIVE:
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE,
                msg("passation.garantie_definitive", statut=courante.statut),
            )
        if date_cloture < courante.date_emission:
            refuser(
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
    contrat s'évalue à sa date de fin COURANTE (celle du dernier avenant). Un contrat SOLDÉ
    (décomptes certifiés égaux à son montant courant et entièrement payés) n'alerte plus : il n'y
    a plus rien à échoir. Tout se lit en quelques requêtes, jamais une par contrat.
    """
    habilite(utilisateur, "consulter", project_id)
    if not isinstance(horizon_jours, int) or horizon_jours < 0:
        refuser("passation.horizon_invalide")
    limite = jour + datetime.timedelta(days=horizon_jours)
    alertes = []
    for g in Garantie.objects.filter(
        project_id=project_id, statut=StatutGarantie.ACTIVE, date_echeance__lte=limite
    ):
        alertes.append(_alerte("garantie", g, g.reference, g.date_echeance, jour))
    dernier = AvenantContrat.objects.filter(contrat=OuterRef("pk")).order_by("-numero")
    certifies = Decompte.objects.filter(contrat=OuterRef("pk"), statut="certifie").values("contrat")
    zero = Value(ZERO, output_field=DecimalField(max_digits=20, decimal_places=4))
    contrats = Contrat.objects.filter(project_id=project_id).annotate(
        fin_courante=Coalesce(Subquery(dernier.values("date_fin")[:1]), F("date_fin_initiale")),
        montant_actuel=Coalesce(Subquery(dernier.values("montant")[:1]), F("montant_initial")),
        certifie=Coalesce(Subquery(certifies.annotate(t=Sum("montant_brut")).values("t")), zero),
        retenu=Coalesce(Subquery(certifies.annotate(t=Sum("retenue")).values("t")), zero),
        paye=Coalesce(
            Subquery(
                Paiement.objects.filter(
                    decompte__contrat=OuterRef("pk"), decompte__statut="certifie"
                )
                .values("decompte__contrat")
                .annotate(t=Sum("montant"))
                .values("t")
            ),
            zero,
        ),
    )
    for c in contrats:
        solde = c.certifie == c.montant_actuel and c.paye == c.certifie - c.retenu
        if c.fin_courante <= limite and not solde:
            alertes.append(_alerte("contrat", c, c.reference, c.fin_courante, jour))
    return sorted(alertes, key=lambda a: (a.echeance, a.nature, a.reference))


def _alerte(nature, objet, reference, echeance, jour) -> Alerte:
    restants = (echeance - jour).days
    return Alerte(
        nature, objet, reference, echeance, restants, "depassee" if restants < 0 else "proche"
    )
