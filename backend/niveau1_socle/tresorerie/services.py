"""Trésorerie : soldes de relevé, appariement des demandes, prévisions, disponibilités, état de
reconstitution du compte désigné. Voir L9-T05.

Jamais deux devises dans un même total : les disponibilités et les prévisions sont ventilées par
devise. Le numéro d'un compte n'apparaît nulle part ici : seul `numero_masque` est exposé.
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, connection, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from niveau1_socle.comptabilite.models import LigneEcriture
from niveau1_socle.decaissements.models import DemandeRetrait
from niveau1_socle.financements.models import CompteBancaire, TypeCompte
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.rapprochement.models import MouvementReleve
from niveau1_socle.rapprochement.services import _contexte, _montant_devise, etat_de_rapprochement
from niveau1_socle.referentiels.models import ValeurDimension

from .models import (
    AppariementDemande,
    CibleEcart,
    JustificationEcart,
    PrevisionTresorerie,
    SoldeReleve,
)

ZERO = Decimal("0")
STATUTS_PAYES = ("acceptee", "remboursee")


def _habilite(utilisateur, operation: str, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(msg("tresorerie.habilitation_requise", operation=operation))


def _refuser(cle: str, **params):
    raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg(cle, **params))


def _decimal(valeur, champ: str, *, signe: str = "positif") -> Decimal:
    """`positif` : > 0 ; `positif_ou_nul` : ≥ 0 ; `libre` : tout nombre fini. Jamais un float."""
    try:
        nombre = Decimal(str(valeur))
    except InvalidOperation:
        _refuser("tresorerie.montant_invalide", champ=champ)
    if not nombre.is_finite() or isinstance(valeur, float):
        _refuser("tresorerie.montant_invalide", champ=champ)
    if (signe == "positif" and nombre <= 0) or (signe == "positif_ou_nul" and nombre < 0):
        _refuser("tresorerie.montant_invalide", champ=champ)
    return nombre


# --- le solde du relevé ------------------------------------------------------------------------


def enregistrer_solde_releve(
    *, utilisateur, compte: CompteBancaire, date_solde: datetime.date, solde, reference: str = ""
) -> SoldeReleve:
    """Enregistre le solde de clôture d'un jour, tel que le relevé le donne. Ajout seul."""
    _habilite(utilisateur, "saisir", compte.project_id)
    solde = _decimal(solde, "solde", signe="libre")
    try:
        with transaction.atomic():
            releve = SoldeReleve.objects.create(
                org_id=compte.org_id,
                compte=compte,
                project_id=compte.project_id,
                date_solde=date_solde,
                solde=solde,
                reference=(reference or "").strip(),
                saisi_par=utilisateur.id,
                created_by=utilisateur.id,
            )
            journaliser(
                org_id=releve.org_id,
                actor_id=utilisateur.id,
                action="bank_balance_recorded",
                object_type="compte_bancaire",
                object_id=compte.id,
                project_id=compte.project_id,
                after={"date": date_solde.isoformat(), "solde": str(solde), "reference": reference},
            )
    except IntegrityError:
        _refuser("tresorerie.solde_existe", date=date_solde.isoformat())
    return releve


def solde_releve_a(compte: CompteBancaire, jour: datetime.date):
    """`(solde, date_du_dernier_solde_enregistré)` du relevé à `jour`, ou `(None, None)`.

    Dernier solde enregistré au plus tard à `jour`, puis les mouvements importés après lui.
    """
    dernier = (
        SoldeReleve.objects.filter(compte=compte, date_solde__lte=jour)
        .order_by("-date_solde")
        .first()
    )
    if dernier is None:
        return None, None
    apres = (
        MouvementReleve.objects.filter(
            compte=compte, date_operation__gt=dernier.date_solde, date_operation__lte=jour
        ).aggregate(t=Sum("montant"))["t"]
        or ZERO
    )
    return dernier.solde + apres, dernier.date_solde


# --- l'appariement d'un encaissement à une demande ---------------------------------------------


def apparier_demande(
    *, utilisateur, mouvement: MouvementReleve, demande: DemandeRetrait
) -> AppariementDemande:
    """Apparie un encaissement du relevé à une demande, UNE SEULE FOIS (index unique en base)."""
    _habilite(utilisateur, "saisir", mouvement.project_id)
    try:
        with transaction.atomic():
            # Le verrou de la demande sérialise les appariements concurrents (plafond du total).
            DemandeRetrait.objects.select_for_update().get(pk=demande.pk)
            appariement = AppariementDemande.objects.create(
                org_id=mouvement.org_id,
                mouvement=mouvement,
                demande=demande,
                project_id=mouvement.project_id,
                apparie_par=utilisateur.id,
                created_by=utilisateur.id,
            )
            journaliser(
                org_id=appariement.org_id,
                actor_id=utilisateur.id,
                action="bank_movement_matched_to_request",
                object_type="demande_retrait",
                object_id=demande.id,
                project_id=mouvement.project_id,
                after={"mouvement": mouvement.reference, "montant": str(mouvement.montant)},
            )
    except IntegrityError as erreur:
        raise _traduire_appariement(erreur, mouvement, demande) from erreur
    return appariement


def _traduire_appariement(erreur, mouvement, demande) -> ErreurMetier:
    texte = str(erreur)
    if "uq_appariement_un_mouvement_une_demande" in texte:
        return ErreurMetier(
            CodeErreur.REGLE_INVALIDE,
            msg("tresorerie.mouvement_deja_apparie", reference=mouvement.reference),
        )
    # Les autres refus portent le message écrit par la base : une seule voix pour la règle.
    detail = texte.split("\n", 1)[0].removeprefix("Error: ")
    return ErreurMetier(
        CodeErreur.REGLE_INVALIDE,
        msg("tresorerie.appariement_refuse", demande=demande.numero, detail=detail),
    )


def annuler_appariement(*, utilisateur, appariement: AppariementDemande, motif: str):
    """Annule l'appariement (motivé) : le mouvement peut alors s'apparier ailleurs."""
    _habilite(utilisateur, "saisir", appariement.project_id)
    if not (motif or "").strip():
        _refuser("tresorerie.annulation_motivee")
    with transaction.atomic():
        courant = AppariementDemande.objects.select_for_update().get(pk=appariement.pk)
        if courant.annule_at is not None:
            raise ErreurMetier(
                CodeErreur.TRANSITION_INTERDITE, msg("tresorerie.appariement_deja_annule")
            )
        courant.annule_at = timezone.now()
        courant.annule_par = utilisateur.id
        courant.motif_annulation = motif.strip()
        courant.save(update_fields=["annule_at", "annule_par", "motif_annulation", "updated_at"])
        journaliser(
            org_id=courant.org_id,
            actor_id=utilisateur.id,
            action="bank_request_match_cancelled",
            object_type="demande_retrait",
            object_id=courant.demande_id,
            project_id=courant.project_id,
            after={"motif": courant.motif_annulation},
        )
    appariement.refresh_from_db()
    return appariement


# --- les prévisions ----------------------------------------------------------------------------


def etablir_prevision(
    *,
    utilisateur,
    project_id,
    devise: str,
    annee: int,
    mois: int,
    encaissements=0,
    decaissements=0,
    axe: ValeurDimension | None = None,
    motif: str = "",
) -> PrevisionTresorerie:
    """Établit la prévision d'un mois pour un axe (ou « tous axes ») : première, puis révisions.

    Chaque révision est CONSERVÉE ; la courante est la plus récente. À partir de la deuxième, le
    motif est obligatoire.
    """
    _habilite(utilisateur, "saisir", project_id)
    if not 1 <= mois <= 12 or annee < 2000:
        _refuser("tresorerie.periode_invalide")
    entrees = _decimal(encaissements, "encaissements", signe="positif_ou_nul")
    sorties = _decimal(decaissements, "decaissements", signe="positif_ou_nul")
    with transaction.atomic():
        # Verrou consultatif sur la clé de la prévision : numérotation sans trou des révisions.
        cle = f"prevision:{project_id}:{devise}:{annee}:{mois}:{axe.id if axe else '-'}"
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [cle])
        precedentes = PrevisionTresorerie.objects.filter(
            project_id=project_id, devise=devise, annee=annee, mois=mois, axe=axe
        )
        derniere = precedentes.order_by("-revision").first()
        revision = (derniere.revision if derniere else 0) + 1
        if revision > 1 and not (motif or "").strip():
            _refuser("tresorerie.revision_motivee")
        prevision = PrevisionTresorerie.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            devise=devise,
            annee=annee,
            mois=mois,
            axe=axe,
            revision=revision,
            encaissements=entrees,
            decaissements=sorties,
            motif=(motif or "").strip(),
            etablie_par=utilisateur.id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=prevision.org_id,
            actor_id=utilisateur.id,
            action="cash_forecast_set",
            object_type="prevision_tresorerie",
            object_id=prevision.id,
            project_id=project_id,
            after={
                "periode": f"{annee}-{mois:02d}",
                "devise": devise,
                "axe": axe.code if axe else None,
                "revision": revision,
                "encaissements": str(entrees),
                "decaissements": str(sorties),
            },
        )
    return prevision


@dataclass(frozen=True)
class LignePrevision:
    annee: int
    mois: int
    devise: str
    axe: str | None  # code de l'axe ; None : « tous axes » (ou axes confondus si `par_axe` faux)
    encaissements: Decimal
    decaissements: Decimal

    @property
    def net(self) -> Decimal:
        return self.encaissements - self.decaissements


def previsions(
    *, utilisateur, project_id, annee: int, mois: int, nombre_mois: int, par_axe: bool = True
) -> list[LignePrevision]:
    """Les prévisions COURANTES des `nombre_mois` mois à partir de `annee`/`mois`, par devise.

    `par_axe` faux : les axes d'un même mois et d'une même devise sont additionnés (jamais les
    devises). Les prévisions « tous axes » et celles par axe se lisent séparément : leur somme
    ferait un double compte si l'on a prévu les deux.
    """
    _habilite(utilisateur, "consulter", project_id)
    if nombre_mois < 1:
        _refuser("tresorerie.periode_invalide")
    debut = annee * 12 + (mois - 1)
    fin = debut + nombre_mois - 1
    courantes: dict = {}
    for p in PrevisionTresorerie.objects.filter(project_id=project_id).select_related("axe"):
        rang = p.annee * 12 + (p.mois - 1)
        if not debut <= rang <= fin:
            continue
        cle = (p.annee, p.mois, p.devise, p.axe_id)
        if cle not in courantes or p.revision > courantes[cle].revision:
            courantes[cle] = p
    cumul: dict = {}
    for p in courantes.values():
        axe = (p.axe.code if p.axe else None) if par_axe else None
        cle = (p.annee, p.mois, p.devise, axe)
        entree, sortie = cumul.get(cle, (ZERO, ZERO))
        cumul[cle] = (entree + p.encaissements, sortie + p.decaissements)
    return [
        LignePrevision(a, m, d, x, e, s)
        for (a, m, d, x), (e, s) in sorted(
            cumul.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3] or "")
        )
    ]


# --- les disponibilités ------------------------------------------------------------------------


@dataclass(frozen=True)
class PositionCompte:
    code: str
    numero_masque: str
    type: str
    devise: str
    solde_comptable: Decimal
    solde_releve: Decimal | None  # None : aucun solde de relevé enregistré à cette date
    date_releve: datetime.date | None
    marge_plafond: Decimal | None  # plafond − solde du relevé (compte à plafond seulement)


@dataclass
class Disponibilites:
    jour: datetime.date
    comptes: list[PositionCompte] = field(default_factory=list)

    def totaux_par_devise(self) -> dict[str, dict[str, Decimal]]:
        """Totaux comptable et relevé PAR DEVISE ; jamais une devise ajoutée à une autre."""
        totaux: dict[str, dict[str, Decimal]] = {}
        for c in self.comptes:
            t = totaux.setdefault(c.devise, {"comptable": ZERO, "releve": ZERO})
            t["comptable"] += c.solde_comptable
            if c.solde_releve is not None:
                t["releve"] += c.solde_releve
        return totaux


def solde_comptable_a(compte: CompteBancaire, jour: datetime.date) -> Decimal:
    _, _, etrangere = _contexte(compte)
    lignes = LigneEcriture.objects.filter(
        bank_account_id=compte.pk,
        entry__status__in=("posted", "locked"),
        entry__accounting_date__lte=jour,
    )
    return sum((_montant_devise(li, etrangere) for li in lignes), ZERO)


def disponibilites(*, utilisateur, project_id, jour: datetime.date) -> Disponibilites:
    """Soldes des comptes actifs du projet à `jour` (comptable et relevé), par compte et devise."""
    _habilite(utilisateur, "consulter", project_id)
    resultat = Disponibilites(jour=jour)
    for compte in CompteBancaire.objects.filter(project_id=project_id, actif=True).order_by("code"):
        releve, date_releve = solde_releve_a(compte, jour)
        resultat.comptes.append(
            PositionCompte(
                code=compte.code,
                numero_masque=compte.numero_masque,
                type=compte.type,
                devise=compte.devise_id,
                solde_comptable=solde_comptable_a(compte, jour),
                solde_releve=releve,
                date_releve=date_releve,
                marge_plafond=(
                    compte.plafond - releve
                    if compte.plafond is not None and releve is not None
                    else None
                ),
            )
        )
    return resultat


# --- l'état de reconstitution du compte désigné -------------------------------------------------


def justifier_ecart(
    *,
    utilisateur,
    compte: CompteBancaire,
    date_debut: datetime.date,
    date_fin: datetime.date,
    cible: str,
    montant,
    explication: str,
) -> JustificationEcart:
    """Explique une partie de l'écart d'un état (signé, non nul). Ajout seul."""
    _habilite(utilisateur, "valider", compte.project_id)
    if cible not in CibleEcart.values:
        _refuser("tresorerie.cible_inconnue", cible=cible)
    montant = _decimal(montant, "montant", signe="libre")
    if montant == 0:
        _refuser("tresorerie.montant_invalide", champ="montant")
    if not (explication or "").strip():
        _refuser("tresorerie.explication_obligatoire")
    if date_fin < date_debut:
        _refuser("tresorerie.periode_invalide")
    with transaction.atomic():
        justification = JustificationEcart.objects.create(
            org_id=compte.org_id,
            compte=compte,
            project_id=compte.project_id,
            date_debut=date_debut,
            date_fin=date_fin,
            cible=cible,
            montant=montant,
            explication=explication.strip(),
            saisie_par=utilisateur.id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=justification.org_id,
            actor_id=utilisateur.id,
            action="reconciliation_gap_justified",
            object_type="compte_bancaire",
            object_id=compte.id,
            project_id=compte.project_id,
            after={
                "periode": [date_debut.isoformat(), date_fin.isoformat()],
                "cible": cible,
                "montant": str(montant),
                "explication": justification.explication,
            },
        )
    return justification


@dataclass
class EtatReconstitution:
    compte_code: str
    compte_masque: str  # jamais le numéro complet
    devise: str
    date_debut: datetime.date
    date_fin: datetime.date
    manques: list = field(default_factory=list)  # soldes de relevé absents : l'état est incomplet
    ouverture: Decimal | None = None
    avances_recues: list = field(default_factory=list)  # (numéro de demande, montant)
    autres_encaissements: Decimal = ZERO
    decaissements: Decimal = ZERO  # positif : total des sorties
    cloture_calculee: Decimal | None = None
    cloture_releve: Decimal | None = None
    ecart_releve: Decimal | None = None  # relevé − calculé
    solde_comptable: Decimal | None = None
    ecart_comptable: Decimal | None = None  # ce que le rapprochement n'explique pas
    justifie_releve: Decimal = ZERO  # somme des justifications
    justifie_comptable: Decimal = ZERO
    plafond: Decimal | None = None
    depasse_plafond: bool = False

    @property
    def total_avances(self) -> Decimal:
        return sum((m for _, m in self.avances_recues), ZERO)

    @property
    def complet(self) -> bool:
        return not self.manques

    @property
    def non_justifie_releve(self) -> Decimal | None:
        return None if self.ecart_releve is None else self.ecart_releve - self.justifie_releve

    @property
    def non_justifie_comptable(self) -> Decimal | None:
        return (
            None if self.ecart_comptable is None else self.ecart_comptable - self.justifie_comptable
        )

    @property
    def justifie(self) -> bool:
        """Vrai si l'état est complet et que CHAQUE écart est expliqué exactement (ou nul)."""
        return self.complet and self.non_justifie_releve == 0 and self.non_justifie_comptable == 0


def etat_reconstitution(
    *, utilisateur, compte: CompteBancaire, date_debut: datetime.date, date_fin: datetime.date
) -> EtatReconstitution:
    """L'état de reconstitution du compte désigné pour la période `[date_debut, date_fin]`.

    Solde d'ouverture (relevé de la veille) + avances reçues du bailleur (encaissements appariés
    à des demandes) + autres encaissements − décaissements = solde de clôture CALCULÉ, comparé au
    solde du relevé à `date_fin`, puis au grand livre par les éléments en suspens du rapprochement.
    Chaque écart doit être justifié explicitement (`justifier_ecart`), au centime.
    """
    _habilite(utilisateur, "consulter", compte.project_id)
    if compte.type != TypeCompte.DESIGNE:
        _refuser("tresorerie.compte_non_designe", code=compte.code)
    if date_fin < date_debut:
        _refuser("tresorerie.periode_invalide")
    etat = EtatReconstitution(
        compte_code=compte.code,
        compte_masque=compte.numero_masque,
        devise=compte.devise_id,
        date_debut=date_debut,
        date_fin=date_fin,
        plafond=compte.plafond,
    )
    veille = date_debut - datetime.timedelta(days=1)
    ouverture = SoldeReleve.objects.filter(compte=compte, date_solde=veille).first()
    cloture = SoldeReleve.objects.filter(compte=compte, date_solde=date_fin).first()
    if ouverture is None:
        etat.manques.append("ouverture")
    if cloture is None:
        etat.manques.append("cloture")
    mouvements = list(
        MouvementReleve.objects.filter(
            compte=compte, date_operation__gte=date_debut, date_operation__lte=date_fin
        ).order_by("date_operation", "reference")
    )
    apparies = {
        ap.mouvement_id: ap.demande.numero
        for ap in AppariementDemande.objects.filter(
            mouvement__in=[m.pk for m in mouvements], annule_at__isnull=True
        ).select_related("demande")
    }
    par_demande: dict[str, Decimal] = {}
    for m in mouvements:
        if m.montant > 0 and m.pk in apparies:
            numero = apparies[m.pk]
            par_demande[numero] = par_demande.get(numero, ZERO) + m.montant
        elif m.montant > 0:
            etat.autres_encaissements += m.montant
        else:
            etat.decaissements += -m.montant
    etat.avances_recues = sorted(par_demande.items())
    justifs = JustificationEcart.objects.filter(
        compte=compte, date_debut=date_debut, date_fin=date_fin
    )
    etat.justifie_releve = (
        justifs.filter(cible=CibleEcart.RELEVE).aggregate(t=Sum("montant"))["t"] or ZERO
    )
    etat.justifie_comptable = (
        justifs.filter(cible=CibleEcart.COMPTABLE).aggregate(t=Sum("montant"))["t"] or ZERO
    )
    if not etat.complet:
        return etat
    etat.ouverture = ouverture.solde
    etat.cloture_releve = cloture.solde
    etat.cloture_calculee = (
        etat.ouverture + etat.total_avances + etat.autres_encaissements - etat.decaissements
    )
    etat.ecart_releve = etat.cloture_releve - etat.cloture_calculee
    # Du relevé au grand livre : le rapprochement existant, avec le solde du relevé ENREGISTRÉ.
    rapprochement = etat_de_rapprochement(utilisateur, compte, date_fin)
    rapprochement.solde_releve = etat.cloture_releve
    etat.solde_comptable = rapprochement.solde_comptable
    etat.ecart_comptable = rapprochement.ecart
    if compte.plafond is not None:
        etat.depasse_plafond = etat.cloture_releve > compte.plafond
    return etat


# Pour les consommateurs qui ne veulent que l'ensemble fermé des statuts d'une demande payée.
__all__ = [
    "Disponibilites",
    "EtatReconstitution",
    "LignePrevision",
    "PositionCompte",
    "annuler_appariement",
    "apparier_demande",
    "disponibilites",
    "enregistrer_solde_releve",
    "etablir_prevision",
    "etat_reconstitution",
    "justifier_ecart",
    "previsions",
    "solde_comptable_a",
    "solde_releve_a",
]
