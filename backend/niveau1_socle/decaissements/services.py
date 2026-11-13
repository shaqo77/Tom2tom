"""L'atelier DRF et le cycle d'une demande de retrait de fonds. Voir L4-T06.

Un seul parcours : choisir un accord et une période ; voir les dépenses éligibles non encore
justifiées, avec leur pièce ; en écarter avec un motif tracé ; vérifier le plafond des catégories et
le disponible de l'accord ; produire la demande (`preparer_demande`) puis, soumise, son état
certifié de dépenses (`soumettre_demande`).

Droits : préparer et annuler = `saisir` ; soumettre et enregistrer la suite (acceptation, rejet,
contestation, remboursement) = `valider`, la soumission par une AUTRE personne que le préparateur.

Limite : montants en monnaie de tenue du projet. Un accord dans une autre devise est refusé tant
que la conversion des dépenses n'existe pas (`DeviseNonSupportee`).
"""

import datetime
import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from niveau1_socle.exercices.services import TransitionInterdite
from niveau1_socle.financements.models import Accord, Categorie
from niveau1_socle.financements.services import exiger_accord_actif
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.habilitations.separation import exiger_separation_des_taches
from niveau1_socle.organisations.models import Projet

from .models import (
    DemandeRetrait,
    LigneDemande,
    MiseAEcart,
    StatutDemande,
    TypeDemande,
)

ZERO = Decimal(0)


class DemandeInvalide(ValueError):
    """Les données de la demande ne respectent pas les règles."""


class DepenseNonSelectionnable(DemandeInvalide):
    """Une dépense choisie n'est pas (ou plus) sélectionnable pour cette demande."""


class DisponibleInsuffisant(DemandeInvalide):
    """Le plafond d'une catégorie ou le montant de l'accord ne permet pas cette demande."""


class DeviseNonSupportee(DemandeInvalide):
    """L'accord n'est pas dans la monnaie de tenue du projet : pas de conversion automatique."""


def _habilite(utilisateur, operation: str, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(f"Vous n'êtes pas habilité à « {operation} » sur ce projet.")


def _exiger_devise(accord: Accord) -> None:
    base = Projet.objects.get(pk=accord.project_id).base_currency
    if accord.devise_id != base:
        raise DeviseNonSupportee(
            f"L'accord {accord.numero} est en {accord.devise_id}, le projet tient ses comptes en "
            f"{base} : la conversion des dépenses n'est pas disponible"
        )


# --- l'atelier : dépenses éligibles ---------------------------------------------------------


@dataclass(frozen=True)
class Depense:
    ligne_id: object
    piece: str
    date: datetime.date
    compte: str
    categorie_id: object
    montant: Decimal
    libelle: str


@dataclass
class Atelier:
    selectionnables: list[Depense] = field(default_factory=list)
    non_selectionnables: list[tuple[Depense, str]] = field(default_factory=list)

    @property
    def total_selectionnable(self) -> Decimal:
        return sum((d.montant for d in self.selectionnables), ZERO)


def depenses_eligibles(
    accord: Accord, debut: datetime.date, fin: datetime.date, *, reprise_de=None
) -> Atelier:
    """Les dépenses comptabilisées de l'accord sur la période, et ce qu'on peut en justifier.

    Éligible : charge budgétée (mêmes comptes que le disponible budgétaire), comptabilisée, imputée
    à l'accord, dans la période. Sélectionnable : de plus, non justifiée par une demande en cours,
    avec une catégorie, et non rejetée (sauf si `reprise_de` est la demande qui l'a été).
    """
    with connection.cursor() as cur:
        cur.execute(
            """SELECT l.id, COALESCE(e.number, ''), e.accounting_date, c.code, l.category_id,
                      l.debit - l.credit, COALESCE(NULLIF(l.label, ''), e.label),
                      (SELECT o.demande_id FROM decaissements_lignedemande o
                        WHERE o.ligne_ecriture_id = l.id AND o.etat = 'actif'),
                      (SELECT o.demande_id FROM decaissements_lignedemande o
                        WHERE o.ligne_ecriture_id = l.id AND o.etat = 'rejete'
                        ORDER BY o.created_at DESC, o.id DESC LIMIT 1)
                 FROM comptabilite_ligneecriture l
                 JOIN comptabilite_ecriture e ON e.id = l.entry_id
                 JOIN referentiels_compte c ON c.id = l.account_id
                WHERE e.project_id = %s AND l.agreement_id = %s
                  AND e.status IN ('posted', 'locked')
                  AND e.accounting_date BETWEEN %s AND %s
                  AND budget_compte_budgete(c.code, c.classe) AND l.debit - l.credit > 0
                ORDER BY e.accounting_date, e.number, l.line_no""",
            [accord.project_id, accord.pk, debut, fin],
        )
        rangees = cur.fetchall()
    atelier = Atelier()
    for ligne_id, piece, date, compte, categorie_id, montant, libelle, active, rejetee in rangees:
        depense = Depense(ligne_id, piece, date, compte, categorie_id, montant, libelle)
        if active is not None:
            atelier.non_selectionnables.append((depense, "déjà justifiée par une demande en cours"))
        elif rejetee is not None and rejetee != reprise_de:
            atelier.non_selectionnables.append(
                (
                    depense,
                    "rejetée dans une demande : à reprendre par une demande qui la représente",
                )
            )
        elif categorie_id is None:
            atelier.non_selectionnables.append((depense, "sans catégorie de dépenses"))
        else:
            atelier.selectionnables.append(depense)
    return atelier


@dataclass(frozen=True)
class LigneVerification:
    cible: str  # "accord" ou "catégorie X"
    plafond: Decimal | None
    utilise: Decimal
    demande: Decimal

    @property
    def disponible(self) -> Decimal | None:
        return None if self.plafond is None else self.plafond - self.utilise

    @property
    def conforme(self) -> bool:
        return self.plafond is None or self.demande <= self.disponible


def _chaine(categorie: Categorie) -> list[Categorie]:
    chaine = [categorie]
    while chaine[-1].parent_id:
        chaine.append(Categorie.objects.get(pk=chaine[-1].parent_id))
    return chaine


def _montants_par_cible(accord: Accord, depenses: list[Depense]):
    """Le montant demandé par catégorie (parents compris) et au total."""
    par_categorie: dict = {}
    for depense in depenses:
        for categorie in _chaine(Categorie.objects.get(pk=depense.categorie_id)):
            entree = par_categorie.setdefault(categorie.pk, [categorie, ZERO])
            entree[1] += depense.montant
    return par_categorie, sum((d.montant for d in depenses), ZERO)


def verifier_disponible(accord: Accord, depenses: list[Depense]) -> list[LigneVerification]:
    """Le plafond de chaque catégorie concernée et le disponible de l'accord, face à la demande.
    Lecture seule : c'est la soumission qui verrouille et tranche."""
    from niveau1_socle.financements.services import montant_courant

    from .models import SoldeAccord, SoldeCategorie

    par_categorie, total = _montants_par_cible(accord, depenses)
    lignes = []
    for categorie, demande in par_categorie.values():
        solde = SoldeCategorie.objects.filter(categorie=categorie).first()
        lignes.append(
            LigneVerification(
                f"catégorie {categorie.code}",
                categorie.plafond,
                solde.utilise if solde else ZERO,
                demande,
            )
        )
    solde = SoldeAccord.objects.filter(accord=accord).first()
    lignes.append(
        LigneVerification(
            "accord", montant_courant(accord), solde.utilise if solde else ZERO, total
        )
    )
    return lignes


# --- préparer, annuler ----------------------------------------------------------------------


def _verrou_accord(accord_id) -> None:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [f"demande:{accord_id}"]
        )


def preparer_demande(
    *,
    utilisateur,
    accord: Accord,
    type: str,
    periode_debut: datetime.date,
    periode_fin: datetime.date,
    lignes: list,
    ecarts: dict | None = None,
    reprise_de: DemandeRetrait | None = None,
) -> DemandeRetrait:
    """Produit une demande PRÉPARÉE à partir des dépenses choisies (`lignes` : identifiants de
    lignes d'écriture). `ecarts` : `{ligne: motif}`, dépenses éligibles écartées avec leur motif."""
    _habilite(utilisateur, "saisir", accord.project_id)
    if type not in TypeDemande.values:
        raise DemandeInvalide(f"type de demande inconnu : {type}")
    ecarts = ecarts or {}
    if not lignes:
        raise DemandeInvalide("Une demande justifie au moins une dépense")
    if set(lignes) & set(ecarts):
        raise DemandeInvalide("Une dépense ne peut être à la fois choisie et écartée")
    if any(not (motif or "").strip() for motif in ecarts.values()):
        raise DemandeInvalide("Écarter une dépense exige un motif")
    with transaction.atomic():
        _verrou_accord(accord.pk)
        accord = Accord.objects.get(pk=accord.pk)
        exiger_accord_actif(accord.pk, pour="demande de décaissement")
        _exiger_devise(accord)
        if reprise_de is not None and (
            reprise_de.accord_id != accord.pk or reprise_de.status != StatutDemande.REJETEE
        ):
            raise DemandeInvalide("On ne représente qu'une demande rejetée du même accord")
        atelier = depenses_eligibles(
            accord, periode_debut, periode_fin, reprise_de=reprise_de.pk if reprise_de else None
        )
        choisies = {d.ligne_id: d for d in atelier.selectionnables}
        raisons = {d.ligne_id: r for d, r in atelier.non_selectionnables}
        for ligne_id in lignes:
            if ligne_id not in choisies:
                raison = raisons.get(ligne_id, "non éligible (hors période, accord ou compte)")
                raise DepenseNonSelectionnable(
                    f"La dépense {ligne_id} n'est pas sélectionnable : {raison}"
                )
        for ligne_id in ecarts:
            if ligne_id not in choisies:
                raise DepenseNonSelectionnable(
                    f"La dépense {ligne_id} ne peut être écartée : elle n'est pas sélectionnable"
                )
        numero = (
            f"DRF-{accord.numero}-{DemandeRetrait.objects.filter(accord=accord).count() + 1:03d}"
        )
        demande = DemandeRetrait.objects.create(
            org_id=utilisateur.org_id,
            project_id=accord.project_id,
            accord=accord,
            numero=numero,
            type=type,
            periode_debut=periode_debut,
            periode_fin=periode_fin,
            reprise_de=reprise_de,
            created_by=utilisateur.id,
        )
        for ligne_id in lignes:
            depense = choisies[ligne_id]
            LigneDemande.objects.create(
                org_id=utilisateur.org_id,
                demande=demande,
                ligne_ecriture_id=ligne_id,
                categorie_id=depense.categorie_id,
                montant=depense.montant,
                piece=depense.piece,
                date_piece=depense.date,
            )
        for ligne_id, motif in ecarts.items():
            MiseAEcart.objects.create(
                org_id=utilisateur.org_id,
                demande=demande,
                ligne_ecriture_id=ligne_id,
                motif=motif.strip(),
                created_by=utilisateur.id,
            )
        total = sum((choisies[i].montant for i in lignes), ZERO)
        DemandeRetrait.objects.filter(pk=demande.pk).update(montant_total=total)
        journaliser(
            org_id=demande.org_id,
            actor_id=utilisateur.id,
            action="drf_prepared",
            object_type="demande_retrait",
            object_id=demande.id,
            project_id=demande.project_id,
            after={
                "numero": numero,
                "lignes": len(lignes),
                "montant": str(total),
                "ecartees": {str(i): m.strip() for i, m in ecarts.items()},
                "reprise_de": reprise_de.numero if reprise_de else None,
            },
        )
    demande.refresh_from_db()
    return demande


def annuler_demande(demande: DemandeRetrait, *, utilisateur, motif: str) -> DemandeRetrait:
    """Abandonne une demande préparée : ses dépenses redeviennent libres."""
    _habilite(utilisateur, "saisir", demande.project_id)
    if not (motif or "").strip():
        raise DemandeInvalide("Le motif d'annulation est obligatoire")
    with transaction.atomic():
        courante = DemandeRetrait.objects.select_for_update().get(pk=demande.pk)
        if courante.status != StatutDemande.PREPAREE:
            raise TransitionInterdite(
                f"La demande {courante.numero} est {courante.status} : seule une demande préparée "
                "s'annule"
            )
        DemandeRetrait.objects.filter(pk=courante.pk).update(status=StatutDemande.ANNULEE)
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action="drf_cancelled",
            object_type="demande_retrait",
            object_id=courante.id,
            project_id=courante.project_id,
            after={"motif": motif.strip()},
        )
    demande.refresh_from_db()
    return demande


# --- soumettre : verrou, contrôle, état certifié --------------------------------------------


def _verrouiller_soldes(demande: DemandeRetrait):
    """Pose un verrou de ligne sur les soldes de l'accord et de chaque catégorie concernée (parents
    compris), dans un ORDRE FIXE : deux demandes qui se disputent un disponible s'attendent, sans
    jamais s'interbloquer. Retourne `({categorie: (plafond, utilise)}, (courant, utilise))`."""
    lignes = list(demande.lignes.filter(etat="actif"))
    categories: dict = {}
    for ligne in lignes:
        for categorie in _chaine(Categorie.objects.get(pk=ligne.categorie_id)):
            categories[categorie.pk] = categorie
    with connection.cursor() as cur:
        for categorie_id in categories:
            cur.execute(
                """INSERT INTO decaissements_soldecategorie
                       (id, created_at, updated_at, org_id, categorie_id, utilise)
                   VALUES (gen_random_uuid(), now(), now(), %s, %s, 0)
                   ON CONFLICT (categorie_id) DO NOTHING""",
                [demande.org_id, categorie_id],
            )
        cur.execute(
            """INSERT INTO decaissements_soldeaccord
                   (id, created_at, updated_at, org_id, accord_id, utilise)
               VALUES (gen_random_uuid(), now(), now(), %s, %s, 0)
               ON CONFLICT (accord_id) DO NOTHING""",
            [demande.org_id, demande.accord_id],
        )
        cur.execute(
            """SELECT categorie_id, utilise FROM decaissements_soldecategorie
                WHERE categorie_id = ANY(%s) ORDER BY categorie_id FOR UPDATE""",
            [list(categories)],
        )
        utilises = dict(cur.fetchall())
        cur.execute(
            """SELECT utilise, financements_montant_courant(accord_id)
                 FROM decaissements_soldeaccord WHERE accord_id = %s FOR UPDATE""",
            [demande.accord_id],
        )
        utilise_accord, courant = cur.fetchone()
    return categories, utilises, (courant, utilise_accord), lignes


def etat_certifie_de(demande: DemandeRetrait, lignes: list[LigneDemande]) -> dict:
    """L'état certifié de dépenses : les dépenses justifiées, par catégorie, avec leur pièce."""
    par_categorie: dict = {}
    for ligne in sorted(lignes, key=lambda x: (x.date_piece, x.piece, str(x.ligne_ecriture_id))):
        categorie = Categorie.objects.get(pk=ligne.categorie_id)
        entree = par_categorie.setdefault(
            categorie.code,
            {"categorie": categorie.code, "libelle": categorie.label, "lignes": [], "total": ZERO},
        )
        entree["lignes"].append(
            {
                "ligne": str(ligne.ligne_ecriture_id),
                "piece": ligne.piece,
                "date": ligne.date_piece.isoformat(),
                "montant": str(ligne.montant),
            }
        )
        entree["total"] += ligne.montant
    categories = [
        {**entree, "total": str(entree["total"])} for _, entree in sorted(par_categorie.items())
    ]
    return {
        "demande": demande.numero,
        "type": demande.type,
        "accord": demande.accord.numero,
        "periode": [demande.periode_debut.isoformat(), demande.periode_fin.isoformat()],
        "categories": categories,
        "total": str(sum((ligne.montant for ligne in lignes), ZERO)),
        "reprise_de": demande.reprise_de.numero if demande.reprise_de_id else None,
    }


def empreinte_de(etat: dict) -> str:
    return hashlib.sha256(
        json.dumps(etat, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def soumettre_demande(
    demande: DemandeRetrait, *, utilisateur, cle_idempotence: str | None = None
) -> DemandeRetrait:
    """Préparée -> soumise, ou rien. L'état certifié est figé avec son empreinte.

    - Concurrence : verrou de ligne sur le solde de chaque catégorie concernée et de l'accord ;
      deux demandes qui se disputent le même disponible passent l'une après l'autre.
    - Idempotence : rejouer la soumission avec la même clé rend la même demande, sans second effet.
    """
    with transaction.atomic():
        courante = DemandeRetrait.objects.select_for_update().get(pk=demande.pk)
        if cle_idempotence and courante.cle_idempotence == cle_idempotence:
            demande.refresh_from_db()
            return demande  # déjà soumise sous cette clé : même résultat, aucun effet de plus
        _habilite(utilisateur, "valider", courante.project_id)
        if courante.status != StatutDemande.PREPAREE:
            raise TransitionInterdite(
                f"La demande {courante.numero} est {courante.status} : seule une demande préparée "
                "se soumet"
            )
        exiger_separation_des_taches(utilisateur, courante.created_by)
        accord = Accord.objects.get(pk=courante.accord_id)
        exiger_accord_actif(accord.pk, pour="demande de décaissement")
        _exiger_devise(accord)

        categories, utilises, (courant, utilise_accord), lignes = _verrouiller_soldes(courante)
        par_categorie: dict = {}
        for ligne in lignes:
            for categorie in _chaine(Categorie.objects.get(pk=ligne.categorie_id)):
                par_categorie[categorie.pk] = par_categorie.get(categorie.pk, ZERO) + ligne.montant
        total = sum((ligne.montant for ligne in lignes), ZERO)
        problemes = []
        for categorie_id, demande_montant in par_categorie.items():
            plafond = categories[categorie_id].plafond
            utilise = utilises[categorie_id]
            if plafond is not None and utilise + demande_montant > plafond:
                problemes.append(
                    f"catégorie {categories[categorie_id].code} : plafond {plafond}, déjà "
                    f"demandé {utilise}, cette demande {demande_montant}"
                )
        if utilise_accord + total > courant:
            problemes.append(
                f"accord {accord.numero} : montant {courant}, déjà demandé {utilise_accord}, "
                f"cette demande {total}"
            )
        if problemes:
            raise DisponibleInsuffisant("Disponible insuffisant : " + " ; ".join(problemes))

        etat = etat_certifie_de(courante, lignes)
        try:
            with transaction.atomic():  # le refus ultime de la base ne doit pas laisser de trace
                DemandeRetrait.objects.filter(pk=courante.pk).update(
                    status=StatutDemande.SOUMISE,
                    soumise_le=timezone.now(),
                    soumise_par=utilisateur.id,
                    cle_idempotence=cle_idempotence or None,
                    etat_certifie=etat,
                    empreinte_etat=empreinte_de(etat),
                )
        except IntegrityError as erreur:
            if "serait dépassé" in str(erreur):
                raise DisponibleInsuffisant(str(erreur).splitlines()[0]) from erreur
            raise
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action="drf_submitted",
            object_type="demande_retrait",
            object_id=courante.id,
            project_id=courante.project_id,
            after={
                "numero": courante.numero,
                "montant": str(total),
                "empreinte": empreinte_de(etat),
            },
        )
    demande.refresh_from_db()
    return demande


# --- la suite : acceptation, rejet, contestation, remboursement ------------------------------


def _decider(demande, utilisateur, nouveau: str, *, attendus, action: str, motif: str = ""):
    _habilite(utilisateur, "valider", demande.project_id)
    champs = {
        StatutDemande.REJETEE: "motif_rejet",
        StatutDemande.CONTESTEE: "motif_contestation",
    }
    if nouveau in champs and not (motif or "").strip():
        raise DemandeInvalide("Le motif est obligatoire pour rejeter ou contester une demande")
    with transaction.atomic():
        courante = DemandeRetrait.objects.select_for_update().get(pk=demande.pk)
        if courante.status not in attendus:
            raise TransitionInterdite(
                f"La demande {courante.numero} est {courante.status} : elle ne peut pas passer à "
                f"{nouveau}"
            )
        if nouveau == StatutDemande.REJETEE:
            _verrouiller_soldes(courante)  # même ordre de verrous que la soumission
        misajour = {"status": nouveau, "decidee_le": timezone.now(), "decidee_par": utilisateur.id}
        if nouveau in champs:
            misajour[champs[nouveau]] = motif.strip()
        DemandeRetrait.objects.filter(pk=courante.pk).update(**misajour)
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action=action,
            object_type="demande_retrait",
            object_id=courante.id,
            project_id=courante.project_id,
            before={"status": courante.status},
            after={"status": nouveau, "motif": (motif or "").strip()},
        )
    demande.refresh_from_db()
    return demande


def accepter_demande(demande, *, utilisateur):
    return _decider(
        demande,
        utilisateur,
        StatutDemande.ACCEPTEE,
        attendus=(StatutDemande.SOUMISE, StatutDemande.CONTESTEE),
        action="drf_accepted",
    )


def rejeter_demande(demande, *, utilisateur, motif: str):
    """Rejet motivé : les dépenses ne reviennent que par une demande qui reprend celle-ci."""
    return _decider(
        demande,
        utilisateur,
        StatutDemande.REJETEE,
        attendus=(StatutDemande.SOUMISE, StatutDemande.CONTESTEE),
        action="drf_rejected",
        motif=motif,
    )


def contester_demande(demande, *, utilisateur, motif: str):
    return _decider(
        demande,
        utilisateur,
        StatutDemande.CONTESTEE,
        attendus=(StatutDemande.SOUMISE, StatutDemande.ACCEPTEE),
        action="drf_disputed",
        motif=motif,
    )


def rembourser_demande(demande, *, utilisateur):
    return _decider(
        demande,
        utilisateur,
        StatutDemande.REMBOURSEE,
        attendus=(StatutDemande.ACCEPTEE,),
        action="drf_reimbursed",
    )
