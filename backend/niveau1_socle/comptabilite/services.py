"""Saisie, validation et comptabilisation des écritures. Voir L3-T05 (partie a).

Chaque service s'exécute au serveur, dans UNE transaction, et vérifie dans l'ordre :
l'habilitation de l'utilisateur sur le projet, la séparation des tâches, puis le contenu de la
pièce. Chaque transition laisse une trace dans le journal d'audit.

Les garanties d'intégrité (équilibre, immuabilité, période ouverte, numérotation sans trou) sont
posées en base. Ces services les anticipent pour rendre une erreur lisible (« la période 3 est
close ») au lieu d'une violation de contrainte, mais la base reste le dernier mot.

La numérotation n'est pas faite ici : elle est attribuée par la base au passage à `posted`.
"""

import datetime
from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from niveau1_socle.exercices.models import Periode
from niveau1_socle.exercices.services import TransitionInterdite
from niveau1_socle.financements.models import Accord
from niveau1_socle.financements.services import exiger_accord_actif
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.habilitations.separation import exiger_separation_des_taches
from niveau1_socle.referentiels.axes import exiger_valeur_imputable
from niveau1_socle.referentiels.comptes import exiger_compte_imputable
from niveau1_socle.referentiels.models import PlanDimension, Tiers

from .models import Ecriture, Journal, LigneEcriture

ZERO = Decimal(0)
AXES = (  # champ de la ligne -> (type d'axe, emplacement)
    ("dim1", "gestion", 1),
    ("dim2", "gestion", 2),
    ("dim3", "gestion", 3),
    ("dim4", "gestion", 4),
    ("aux1", "auxiliaire", 1),
    ("aux2", "auxiliaire", 2),
    ("aux3", "auxiliaire", 3),
    ("aux4", "auxiliaire", 4),
)
IDENTIFIANTS_LIBRES = ("site_id", "agreement_id", "category_id", "contract_id", "bank_account_id")


class EcritureInvalide(ValueError):
    """La pièce ne peut pas passer à l'étape demandée ; `raisons` les liste toutes."""

    def __init__(self, raisons: list[str]):
        self.raisons = raisons
        super().__init__(" ; ".join(raisons))


class PeriodeIntrouvable(LookupError):
    """Aucune période du projet ne couvre la date comptable."""


class PeriodeNonOuverte(ValueError):
    """La période de l'écriture n'est plus ouverte."""


class JournalIntrouvable(LookupError):
    """Aucun journal de ce code dans l'organisation courante."""


class DejaContrepassee(ValueError):
    """L'écriture a déjà sa contre-passation (une seule par écriture)."""


class ContrepassationImpossible(ValueError):
    """Cette écriture ne se contre-passe pas."""


def _exiger_habilitation(utilisateur, operation: str, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(f"Vous n'êtes pas habilité à « {operation} » sur ce projet.")


def _exiger_periode_ouverte(periode: Periode) -> None:
    if periode.status != "ouverte":
        raise PeriodeNonOuverte(
            f"La période {periode.numero} est {periode.status} : aucune écriture ne peut y être "
            "saisie ni comptabilisée"
        )


def _periode_pour(project_id, date_comptable: datetime.date) -> Periode:
    periode = (
        Periode.objects.select_related("exercice")
        .filter(
            exercice__project_id=project_id,
            date_debut__lte=date_comptable,
            date_fin__gte=date_comptable,
        )
        .first()
    )
    if periode is None:
        raise PeriodeIntrouvable(
            f"Aucune période du projet ne couvre le {date_comptable.isoformat()}"
        )
    return periode


def _valeur_dimension(champ: str, type_axe: str, emplacement: int, code: str):
    plan = PlanDimension.objects.filter(kind=type_axe, slot=emplacement).first()
    if plan is None:
        raise ValueError(f"Aucun plan d'axe n'occupe l'emplacement {champ} ({type_axe})")
    return exiger_valeur_imputable(plan.code, code)


def _ligne_vers_modele(
    ligne: dict, ecriture: Ecriture, rang: int, devise: str, taux
) -> LigneEcriture:
    compte = exiger_compte_imputable(ligne["compte"])
    champs = {
        champ: _valeur_dimension(champ, type_axe, emplacement, ligne[champ])
        for champ, type_axe, emplacement in AXES
        if ligne.get(champ)
    }
    champs |= {cle: ligne[cle] for cle in IDENTIFIANTS_LIBRES if ligne.get(cle)}
    tiers = Tiers.objects.get(code=ligne["tiers"]) if ligne.get("tiers") else None
    return LigneEcriture(
        org_id=ecriture.org_id,
        project_id=ecriture.project_id,
        entry=ecriture,
        line_no=rang,
        account=compte,
        partner=tiers,
        debit=Decimal(str(ligne.get("debit", 0))),
        credit=Decimal(str(ligne.get("credit", 0))),
        debit_cur=Decimal(str(ligne.get("debit_cur", 0))),
        credit_cur=Decimal(str(ligne.get("credit_cur", 0))),
        currency_id=devise,
        fx_rate=taux,
        label=ligne.get("label", ""),
        **champs,
    )


def saisir_ecriture(
    *,
    utilisateur,
    project_id,
    journal: str,
    date_comptable: datetime.date,
    libelle: str,
    lignes: list[dict],
    devise: str = "DJF",
    taux=1,
    reference_piece: str = "",
    cle_idempotence: str | None = None,
    schema=None,
) -> Ecriture:
    """Enregistre un BROUILLON équilibré. Retourne l'écriture existante si la clé est connue.

    Les montants des lignes sont en monnaie de tenue. Le brouillon doit être équilibré (la base
    l'exige à la fin de la transaction) : une pièce est saisie complète, en une fois.
    """
    _exiger_habilitation(utilisateur, "saisir", project_id)
    if cle_idempotence:
        deja = Ecriture.objects.filter(idempotency_key=cle_idempotence).first()
        if deja is not None:
            return deja

    # Un accord qui n'est pas actif (suspendu, clos…) ne reçoit aucune nouvelle imputation (L4-T04).
    for agreement_id in {ligne["agreement_id"] for ligne in lignes if ligne.get("agreement_id")}:
        exiger_accord_actif(agreement_id, pour="imputation")

    jrn = Journal.objects.filter(code=journal).first()
    if jrn is None:
        raise JournalIntrouvable(f"Le journal {journal} n'existe pas")
    periode = _periode_pour(project_id, date_comptable)
    _exiger_periode_ouverte(periode)

    debit = sum((Decimal(str(ligne.get("debit", 0))) for ligne in lignes), ZERO)
    credit = sum((Decimal(str(ligne.get("credit", 0))) for ligne in lignes), ZERO)
    if debit != credit:
        raise EcritureInvalide([f"Écriture déséquilibrée : débit {debit}, crédit {credit}"])

    with transaction.atomic():
        ecriture = Ecriture.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            exercice=periode.exercice,
            periode=periode,
            journal=jrn,
            accounting_date=date_comptable,
            document_ref=reference_piece,
            label=libelle,
            status="draft",
            currency_id=devise,
            fx_rate=Decimal(str(taux)),
            origin="saisie",
            schema=schema,
            idempotency_key=cle_idempotence,
            created_by=utilisateur.id,
        )
        modeles = [
            _ligne_vers_modele(ligne, ecriture, rang, devise, Decimal(str(taux)))
            for rang, ligne in enumerate(lignes, start=1)
        ]
        LigneEcriture.objects.bulk_create(modeles)
        journaliser(
            org_id=ecriture.org_id,
            actor_id=utilisateur.id,
            action="entry_created",
            object_type="ecriture",
            object_id=ecriture.id,
            project_id=project_id,
            after={"status": "draft", "lignes": len(modeles)},
        )
    return ecriture


CHAMPS_DE_LIGNE = (
    "account_id",
    "partner_id",
    "dim1_id",
    "dim2_id",
    "dim3_id",
    "dim4_id",
    "aux1_id",
    "aux2_id",
    "aux3_id",
    "aux4_id",
    "site_id",
    "agreement_id",
    "category_id",
    "contract_id",
    "bank_account_id",
    "currency_id",
)


def _signature(ligne: LigneEcriture, *, inverse: bool = False) -> tuple:
    """Ce qui identifie une ligne ; `inverse` échange débit et crédit (montants en devise aussi)."""
    debit, credit = (ligne.credit, ligne.debit) if inverse else (ligne.debit, ligne.credit)
    debit_cur, credit_cur = (
        (ligne.credit_cur, ligne.debit_cur) if inverse else (ligne.debit_cur, ligne.credit_cur)
    )
    return (
        *(getattr(ligne, champ) for champ in CHAMPS_DE_LIGNE),
        debit,
        credit,
        debit_cur,
        credit_cur,
    )


def _problemes_de_contenu(ecriture: Ecriture) -> list[str]:
    """Toutes les raisons pour lesquelles la pièce n'est pas valide, pas seulement la première."""
    lignes = list(
        ecriture.lignes.select_related(
            "account", "dim1", "dim2", "dim3", "dim4", "aux1", "aux2", "aux3", "aux4"
        ).order_by("line_no")
    )
    raisons = []
    if ecriture.reverses_id:
        miroir = Counter(
            _signature(ligne, inverse=True) for ligne in ecriture.reverses.lignes.all()
        )
        if miroir != Counter(_signature(ligne) for ligne in lignes):
            raisons.append(
                "La contre-passation ne reproduit pas l'écriture d'origine en sens inverse"
            )
    if ecriture.origin != "reversal":  # une correction de l'historique reste possible
        statuts = dict(
            Accord.objects.filter(
                pk__in={ligne.agreement_id for ligne in lignes if ligne.agreement_id}
            ).values_list("pk", "status")
        )
        for ligne in lignes:
            statut = statuts.get(ligne.agreement_id)
            if statut is not None and statut != "actif":
                raisons.append(
                    f"Ligne {ligne.line_no} : l'accord est {statut}, il ne reçoit plus d'imputation"
                )
    if len(lignes) < 2:
        raisons.append("Une écriture compte au moins deux lignes")
    if lignes and sum((ligne.debit for ligne in lignes), ZERO) == ZERO:
        raisons.append("Une écriture à montant nul n'a pas de sens")
    for ligne in lignes:
        compte = ligne.account
        if not compte.imputable:
            raisons.append(f"Ligne {ligne.line_no} : le compte {compte.code} n'est pas imputable")
        if not compte.actif:
            raisons.append(f"Ligne {ligne.line_no} : le compte {compte.code} est inactif")
        for champ, _, _ in AXES:
            valeur = getattr(ligne, champ)
            if valeur is None:
                continue
            if not valeur.is_postable:
                raisons.append(
                    f"Ligne {ligne.line_no} : la valeur {valeur.code} n'est pas imputable"
                )
            if not valeur.is_active:
                raisons.append(f"Ligne {ligne.line_no} : la valeur {valeur.code} est inactive")
    return raisons


def _transition(
    ecriture, utilisateur, *, attendu, nouveau, operation, action, controle_supplementaire
):
    with transaction.atomic():
        # Verrou de ligne : deux transitions simultanées de la même pièce ne passent pas ensemble.
        courante = (
            Ecriture.objects.select_for_update().select_related("periode").get(pk=ecriture.pk)
        )
        if courante.status != attendu:
            raise TransitionInterdite(
                f"L'écriture est {courante.status} : seule une écriture {attendu} peut passer à "
                f"{nouveau}"
            )
        _exiger_habilitation(utilisateur, operation, courante.project_id)
        controle_supplementaire(courante)
        raisons = _problemes_de_contenu(courante)
        if raisons:
            raise EcritureInvalide(raisons)

        champs = {"status": nouveau}
        if nouveau == "posted":
            champs |= {"posted_at": timezone.now(), "posted_by": utilisateur.id}
        Ecriture.objects.filter(pk=courante.pk).update(**champs)
        courante.refresh_from_db()  # reprend le numéro attribué par la base
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action=action,
            object_type="ecriture",
            object_id=courante.id,
            project_id=courante.project_id,
            before={"status": attendu},
            after={"status": nouveau, "number": courante.number},
        )
    ecriture.refresh_from_db()
    return ecriture


def valider_ecriture(ecriture: Ecriture, *, utilisateur) -> Ecriture:
    """Brouillon -> validée. L'auteur de la pièce ne la valide pas (séparation des tâches).

    Le contrôle budgétaire s'applique ici (L4-T03) : un dépassement `bloquant` refuse la
    validation ; un `avertissement` la laisse passer et se lit dans
    `ecriture.avertissements_budgetaires`.
    """
    avertissements: list[str] = []

    def controle(courante):
        exiger_separation_des_taches(utilisateur, courante.created_by)
        # Import local : le budget lit le grand livre en SQL et ne doit pas l'importer.
        from niveau1_socle.budget.controle import appliquer, evaluer_ecriture

        avertissements.extend(
            appliquer(
                evaluer_ecriture(courante),
                utilisateur=utilisateur,
                objet_type="ecriture",
                objet_id=courante.id,
                project_id=courante.project_id,
            )
        )

    resultat = _transition(
        ecriture,
        utilisateur,
        attendu="draft",
        nouveau="validated",
        operation="valider",
        action="entry_validated",
        controle_supplementaire=controle,
    )
    resultat.avertissements_budgetaires = avertissements
    return resultat


def comptabiliser_ecriture(ecriture: Ecriture, *, utilisateur) -> Ecriture:
    """Validée -> comptabilisée. La base attribue le numéro, sans trou, dans cette transaction."""
    return _transition(
        ecriture,
        utilisateur,
        attendu="validated",
        nouveau="posted",
        operation="comptabiliser",
        action="entry_posted",
        controle_supplementaire=lambda courante: _exiger_periode_ouverte(courante.periode),
    )


def _creer_inverse(originale: Ecriture, *, auteur_id, date, periode, libelle: str) -> Ecriture:
    """Le BROUILLON de l'écriture inverse : mêmes comptes, axes et devises, sens contraire.

    Partagé par `contre_passer` et par la régénération des à-nouveaux (clôture annuelle). L'appelant
    a déjà vérifié les droits, que l'originale est comptabilisée et que la période est ouverte.
    """
    inverse = Ecriture.objects.create(
        org_id=originale.org_id,
        project_id=originale.project_id,
        exercice=periode.exercice,
        periode=periode,
        journal=originale.journal,
        accounting_date=date,
        document_ref=originale.number or "",
        label=libelle,
        status="draft",
        currency_id=originale.currency_id,
        fx_rate=originale.fx_rate,
        origin="reversal",
        reverses=originale,
        created_by=auteur_id,
    )
    LigneEcriture.objects.bulk_create(
        [
            LigneEcriture(
                org_id=ligne.org_id,
                project_id=ligne.project_id,
                entry=inverse,
                line_no=ligne.line_no,
                debit=ligne.credit,
                credit=ligne.debit,
                debit_cur=ligne.credit_cur,
                credit_cur=ligne.debit_cur,
                fx_rate=ligne.fx_rate,
                label=ligne.label,
                **{champ: getattr(ligne, champ) for champ in CHAMPS_DE_LIGNE},
            )
            for ligne in originale.lignes.order_by("line_no")
        ]
    )
    return inverse


def contre_passer(
    ecriture: Ecriture,
    *,
    utilisateur,
    date_comptable: datetime.date | None = None,
    libelle: str | None = None,
) -> Ecriture:
    """Crée le BROUILLON de contre-passation d'une écriture comptabilisée.

    L'écriture d'origine n'est jamais touchée : elle est immuable. L'inverse reprend chaque
    ligne en sens contraire, avec les mêmes comptes, axes et devises, et suit le circuit
    habituel (validation par un autre, puis comptabilisation). Sans date, elle reprend celle
    de l'originale : si sa période est close, on précise une date dans une période ouverte.
    """
    with transaction.atomic():
        # Verrou de ligne : deux demandes simultanées ne créent pas deux contre-passations.
        originale = (
            Ecriture.objects.select_for_update().select_related("journal").get(pk=ecriture.pk)
        )
        _exiger_habilitation(utilisateur, "saisir", originale.project_id)
        if originale.status not in ("posted", "locked"):
            raise TransitionInterdite(
                f"L'écriture est {originale.status} : on ne contre-passe qu'une écriture "
                "comptabilisée"
            )
        if originale.origin == "reversal":
            raise ContrepassationImpossible(
                "Une contre-passation ne se contre-passe pas : saisissez une nouvelle écriture"
            )
        existante = Ecriture.objects.filter(reverses=originale).first()
        if existante is not None:
            raise DejaContrepassee(
                f"L'écriture {originale.number} est déjà contre-passée "
                f"({existante.number or 'brouillon ' + str(existante.pk)})"
            )

        date = date_comptable or originale.accounting_date
        periode = _periode_pour(originale.project_id, date)
        try:
            _exiger_periode_ouverte(periode)
        except PeriodeNonOuverte as erreur:
            raise PeriodeNonOuverte(
                f"{erreur}. Précisez une date comptable dans une période ouverte."
            ) from erreur

        inverse = _creer_inverse(
            originale,
            auteur_id=utilisateur.id,
            date=date,
            periode=periode,
            libelle=libelle or f"Contre-passation de {originale.number} : {originale.label}",
        )
        journaliser(
            org_id=inverse.org_id,
            actor_id=utilisateur.id,
            action="entry_reversed",
            object_type="ecriture",
            object_id=inverse.id,
            project_id=inverse.project_id,
            after={"reverses": str(originale.id), "number": originale.number},
        )
    return inverse
