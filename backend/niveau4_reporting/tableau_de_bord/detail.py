"""La descente du tableau de bord : indicateur → détail par projet → écriture. Voir L10-T02.

`detail_indicateur` rend les objets qui composent un indicateur pour UN projet ; leur somme égale,
devise par devise, le chiffre du tableau (contrôle du plan, testé). `ecritures_du_detail` rend les
écritures du grand livre derrière un objet quand il en a : un compte bancaire (ses lignes), une
avance (versement et justifications). Un engagement, un accord ou une ligne de budget n'ont pas
d'écriture : on ne l'invente pas, `a_une_ecriture` le dit. Le dernier pas (l'écriture, ses lignes et
ses pièces) est `publication.descente.detail_ecriture`.
"""

import datetime
import uuid
from dataclasses import dataclass
from decimal import Decimal

from core.metier import habilite
from niveau1_socle.avances.models import Avance
from niveau1_socle.avances.services import suivi
from niveau1_socle.budget.models import LigneBudget
from niveau1_socle.budget.soldes import situation
from niveau1_socle.comptabilite.models import LigneEcriture
from niveau1_socle.organisations.models import Projet
from niveau1_socle.rapprochement.services import _contexte, _montant_devise
from niveau1_socle.tresorerie.models import CompteBancaire
from niveau1_socle.tresorerie.services import solde_releve_a

from .filtres import Filtres, accords_du_filtre, ids_accords_du_filtre
from .sources import (
    appariements_recus,
    engagements_ouverts,
    lignes_budget,
    montant_accord,
    version_budget,
)

ZERO = Decimal("0")
AVEC_ECRITURE = {"compte_bancaire", "avance"}  # un solde de relevé (compte_releve) : aucune
CODES = (
    "budget_approuve", "budget_initial", "financements_accordes", "financements_recus",
    "execution_budget", "execution_engage", "execution_consomme", "soldes_comptables",
    "soldes_releves", "engagements_ouverts", "avances_non_justifiees",
)  # fmt: skip


@dataclass(frozen=True)
class LigneDetail:
    type: str  # ligne_budget, accord, appariement, compte_bancaire, engagement, avance
    id: uuid.UUID
    libelle: str
    devise: str
    montant: Decimal

    @property
    def a_une_ecriture(self) -> bool:
        return self.type in AVEC_ECRITURE


@dataclass(frozen=True)
class EcritureRef:
    ecriture_id: uuid.UUID
    numero: str | None
    date: datetime.date
    libelle: str
    montant: Decimal  # dans la devise du détail, signé (débit − crédit)


def _libelle_ligne(ligne: LigneBudget) -> str:
    composante = ligne.dim1.code if ligne.dim1_id else "-"
    return f"{ligne.annee}/{ligne.periode or '-'} {composante}"


def detail_indicateur(
    *,
    utilisateur,
    code: str,
    project_id,
    jour: datetime.date,
    filtres: Filtres | None = None,
) -> list[LigneDetail]:
    """Les objets qui composent `code` pour ce projet, avec les MÊMES règles que le tableau."""
    if code not in CODES:
        raise KeyError(code)
    habilite(utilisateur, "consulter", project_id)
    filtres = filtres or Filtres()
    projet = Projet.objects.get(pk=project_id)
    ids_accords = ids_accords_du_filtre(projet, filtres)
    devise = projet.base_currency
    if code in ("budget_approuve", "budget_initial"):
        lignes = lignes_budget(version_budget(project_id, code), ids_accords)
        return [
            LigneDetail("ligne_budget", ligne.pk, _libelle_ligne(ligne), devise, ligne.montant_base)
            for ligne in lignes.select_related("dim1").order_by("annee", "periode", "id")
        ]
    if code.startswith("execution_"):
        champ = code.removeprefix("execution_")
        resultat = []
        for rangee in situation(project_id):
            ligne = rangee.solde.ligne
            if ids_accords is not None and ligne.agreement_id not in ids_accords:
                continue
            montant = {
                "budget": rangee.budget,
                "engage": rangee.engage,
                "consomme": rangee.consomme,
            }
            resultat.append(
                LigneDetail("ligne_budget", ligne.pk, _libelle_ligne(ligne), devise, montant[champ])
            )
        return resultat
    if code == "financements_accordes":
        return [
            LigneDetail("accord", a.pk, a.numero, a.devise_id, montant_accord(a, jour))
            for a in accords_du_filtre(project_id, filtres).select_related("devise")
        ]
    if code == "financements_recus":
        return [
            LigneDetail(
                "appariement", r.pk, r.mouvement.reference, r.mouvement.compte.devise_id,
                r.mouvement.montant,
            )
            for r in appariements_recus(project_id, filtres, jour)
        ]  # fmt: skip
    if code in ("soldes_comptables", "soldes_releves"):
        from niveau1_socle.tresorerie.services import solde_comptable_a

        comptes = CompteBancaire.objects.filter(project_id=project_id, actif=True).order_by("code")
        resultat = []
        for compte in comptes:
            if code == "soldes_comptables":
                montant = solde_comptable_a(compte, jour)
            else:
                montant, _ = solde_releve_a(compte, jour)
                if montant is None:
                    continue
            genre = "compte_bancaire" if code == "soldes_comptables" else "compte_releve"
            resultat.append(LigneDetail(genre, compte.pk, compte.code, compte.devise_id, montant))
        return resultat
    if code == "engagements_ouverts":
        return [
            LigneDetail("engagement", e.pk, e.reference, devise, e.montant - e.apure)
            for e in engagements_ouverts(project_id, ids_accords, jour).order_by("reference")
        ]
    return [  # avances_non_justifiees
        LigneDetail("avance", s.avance.pk, s.avance.reference, devise, s.reste)
        for s in suivi(utilisateur, project_id, jour)
        if s.reste > 0
    ]


def ecritures_du_detail(
    *, utilisateur, detail: LigneDetail, project_id, jour: datetime.date
) -> list[EcritureRef]:
    """Les écritures comptabilisées derrière un détail ; `[]` s'il n'a pas d'écriture."""
    habilite(utilisateur, "consulter", project_id)
    if detail.type == "compte_bancaire":
        compte = CompteBancaire.objects.get(pk=detail.id, project_id=project_id)
        _, _, etrangere = _contexte(compte)
        lignes = LigneEcriture.objects.filter(
            bank_account_id=compte.pk,
            entry__status__in=("posted", "locked"),
            entry__accounting_date__lte=jour,
        ).select_related("entry")
    elif detail.type == "avance":
        avance = Avance.objects.prefetch_related("justifications").get(
            pk=detail.id, project_id=project_id
        )
        ids = [avance.ligne_ecriture_id] + [
            j.ligne_ecriture_id for j in avance.justifications.all() if j.date_justification <= jour
        ]
        etrangere = False
        lignes = LigneEcriture.objects.filter(
            pk__in=[i for i in ids if i], project_id=project_id
        ).select_related("entry")
    else:
        return []
    par_ecriture: dict = {}
    for ligne in lignes.order_by("entry__accounting_date", "entry__number", "line_no"):
        ref = par_ecriture.get(ligne.entry_id)
        montant = _montant_devise(ligne, etrangere)
        if ref is None:
            e = ligne.entry
            par_ecriture[e.pk] = EcritureRef(e.pk, e.number, e.accounting_date, e.label, montant)
        else:
            par_ecriture[ligne.entry_id] = EcritureRef(
                ref.ecriture_id, ref.numero, ref.date, ref.libelle, ref.montant + montant
            )
    return list(par_ecriture.values())
