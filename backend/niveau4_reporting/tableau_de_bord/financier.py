"""Les indicateurs financiers du tableau de bord, par projet et par devise. Voir L10-T02.

Chaque indicateur est `{projet: {devise: montant}}`. Les montants du budget, de l'engagé, du
consommé, des engagements et des avances sont en MONNAIE DE TENUE DU PROJET ; ceux des accords et
des comptes bancaires sont dans leur propre devise. Aucun d'eux n'est jamais additionné à un
montant d'une autre devise : le total d'un indicateur est un dictionnaire par devise.
"""

import datetime
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Sum

from niveau1_socle.avances.services import suivi
from niveau1_socle.budget.soldes import situation
from niveau1_socle.organisations.models import Projet
from niveau1_socle.rapprochement.models import MouvementReleve
from niveau1_socle.tresorerie.services import disponibilites
from niveau3_config.services.activation import resoudre_configuration

from .conformite import Conformite, conformite_du_projet
from .filtres import (
    CONFIGURE,
    NON_CONFIGURE,
    Filtres,
    accords_du_filtre,
    ids_accords_du_filtre,
    perimetre,
)
from .sources import (
    appariements_recus,
    engagements_ouverts,
    lignes_budget,
    montant_accord,
    version_budget,
)

ZERO = Decimal("0")


@dataclass
class Indicateur:
    code: str
    par_projet: dict = field(default_factory=dict)  # project_id -> {devise: Decimal}

    def ajouter(self, project_id, devise: str, montant: Decimal) -> None:
        cellule = self.par_projet.setdefault(project_id, {})
        cellule[devise] = cellule.get(devise, ZERO) + montant

    @property
    def total(self) -> dict[str, Decimal]:
        """Le total PAR DEVISE : somme exacte des détails par projet, sans mélanger les devises."""
        total: dict[str, Decimal] = {}
        for montants in self.par_projet.values():
            for devise, montant in montants.items():
                total[devise] = total.get(devise, ZERO) + montant
        return total

    def restreindre_a(self, devise: str | None) -> "Indicateur":
        if not devise:
            return self
        filtre = Indicateur(self.code)
        for projet, montants in self.par_projet.items():
            if devise in montants:
                filtre.par_projet[projet] = {devise: montants[devise]}
        return filtre


@dataclass
class ProjetVue:
    id: uuid.UUID
    code: str
    libelle: dict
    statut: str
    configuration: str
    bailleurs: list[str]
    base_comptable: str  # cash, cash_with_commitments ou accrual : voir L11-A3


@dataclass
class TableauDeBord:
    jour: datetime.date
    filtres: Filtres
    projets: list[ProjetVue] = field(default_factory=list)
    indicateurs: dict[str, Indicateur] = field(default_factory=dict)
    # composante (code de la 1re dimension, « » : sans composante) -> {budget, engage, consomme}
    par_composante: dict[str, dict[str, Indicateur]] = field(default_factory=dict)
    conformite: Conformite = field(default_factory=Conformite)
    avertissements: list[str] = field(default_factory=list)

    def taux_execution(self, composante: str | None = None) -> dict[str, Decimal | None]:
        """consommé ÷ budget, par devise (None si le budget est nul), global ou d'une composante."""
        source = self.par_composante[composante] if composante is not None else None
        budget = (source["budget"] if source else self.indicateurs["execution_budget"]).total
        consomme = (source["consomme"] if source else self.indicateurs["execution_consomme"]).total
        return {
            devise: (consomme.get(devise, ZERO) / montant if montant else None)
            for devise, montant in budget.items()
        }


def tableau_de_bord(
    *, utilisateur, jour: datetime.date, filtres: Filtres | None = None
) -> TableauDeBord:
    """Le tableau de bord à `jour`, pour les projets que l'utilisateur peut consulter."""
    filtres = filtres or Filtres()
    projets = perimetre(utilisateur, filtres, jour)
    tdb = TableauDeBord(jour=jour, filtres=filtres)
    codes = (
        "budget_approuve", "budget_initial", "financements_accordes", "financements_recus",
        "execution_budget", "execution_engage", "execution_consomme", "soldes_comptables",
        "soldes_releves", "engagements_ouverts", "avances_non_justifiees",
    )  # fmt: skip
    ind = {code: Indicateur(code) for code in codes}
    for projet in projets:
        ids_accords = ids_accords_du_filtre(projet, filtres)
        tdb.projets.append(_vue_projet(projet, filtres, jour))
        _budgets(projet, ids_accords, ind)
        _financements(projet, filtres, jour, ind)
        _execution(projet, ids_accords, ind, tdb)
        _soldes_bancaires(utilisateur, projet, jour, ind)
        _engagements(projet, ids_accords, jour, ind)
        _avances(utilisateur, projet, jour, ind)
        tdb.conformite.par_projet[projet.id] = conformite_du_projet(
            utilisateur, projet.id, jour, filtres.du, filtres.au
        )
    tdb.indicateurs = {code: i.restreindre_a(filtres.devise) for code, i in ind.items()}
    for ventilation in tdb.par_composante.values():
        for code, i in ventilation.items():
            ventilation[code] = i.restreindre_a(filtres.devise)
    tdb.avertissements.append("tableau_de_bord.execution_recouvrement")
    if jour != datetime.date.today():
        # Les soldes budgétaires sont tenus au fil de l'eau : l'exécution est celle d'aujourd'hui.
        tdb.avertissements.append("tableau_de_bord.execution_etat_courant")
    return tdb


def _vue_projet(projet: Projet, filtres: Filtres, jour: datetime.date) -> ProjetVue:
    bailleurs = sorted(
        set(
            accords_du_filtre(projet.id, filtres)
            .select_related("bailleur")
            .values_list("bailleur__code", flat=True)
        )
    )
    configure = bool(resoudre_configuration(projet.id, jour).exigences)
    return ProjetVue(
        id=projet.id,
        code=projet.code,
        libelle=projet.label,
        statut=projet.status,
        configuration=CONFIGURE if configure else NON_CONFIGURE,
        bailleurs=bailleurs,
        base_comptable=projet.accounting_basis,
    )


def _budgets(projet: Projet, ids_accords, ind: dict) -> None:
    for code in ("budget_approuve", "budget_initial"):
        version = version_budget(projet.id, code)
        if version is None:
            continue
        lignes = lignes_budget(version, ids_accords)
        ind[code].ajouter(
            projet.id, projet.base_currency, lignes.aggregate(t=Sum("montant_base"))["t"] or ZERO
        )


def _financements(projet: Projet, filtres: Filtres, jour: datetime.date, ind: dict) -> None:
    for accord in accords_du_filtre(projet.id, filtres).select_related("devise"):
        ind["financements_accordes"].ajouter(
            projet.id, accord.devise_id, montant_accord(accord, jour)
        )
    for appariement in appariements_recus(projet.id, filtres, jour):
        mouvement: MouvementReleve = appariement.mouvement
        ind["financements_recus"].ajouter(projet.id, mouvement.compte.devise_id, mouvement.montant)


def _execution(projet: Projet, ids_accords, ind: dict, tdb: TableauDeBord) -> None:
    devise = projet.base_currency
    for rangee in situation(projet.id):
        ligne = rangee.solde.ligne
        if ids_accords is not None and ligne.agreement_id not in ids_accords:
            continue
        composante = ligne.dim1.code if ligne.dim1_id else ""
        ventilation = tdb.par_composante.setdefault(
            composante,
            {c: Indicateur(c) for c in ("budget", "engage", "consomme")},
        )
        for code, montant in (
            ("budget", rangee.budget),
            ("engage", rangee.engage),
            ("consomme", rangee.consomme),
        ):
            ventilation[code].ajouter(projet.id, devise, montant)
            ind[f"execution_{code}"].ajouter(projet.id, devise, montant)


def _soldes_bancaires(utilisateur, projet: Projet, jour: datetime.date, ind: dict) -> None:
    for compte in disponibilites(utilisateur=utilisateur, project_id=projet.id, jour=jour).comptes:
        ind["soldes_comptables"].ajouter(projet.id, compte.devise, compte.solde_comptable)
        if compte.solde_releve is not None:
            ind["soldes_releves"].ajouter(projet.id, compte.devise, compte.solde_releve)


def _engagements(projet: Projet, ids_accords, jour: datetime.date, ind: dict) -> None:
    ouvert = sum(
        (e.montant - e.apure for e in engagements_ouverts(projet.id, ids_accords, jour)), ZERO
    )
    ind["engagements_ouverts"].ajouter(projet.id, projet.base_currency, ouvert)


def _avances(utilisateur, projet: Projet, jour: datetime.date, ind: dict) -> None:
    reste = sum((s.reste for s in suivi(utilisateur, projet.id, jour) if s.reste > 0), ZERO)
    ind["avances_non_justifiees"].ajouter(projet.id, projet.base_currency, reste)
