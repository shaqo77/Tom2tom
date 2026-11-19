"""Restitutions : balances, grand livre, journaux. Voir L3-T09.

Construites sur le MÊME socle que le moteur d'états de L0 : la vue `moteur_ligneecriture`
(écritures comptabilisées ou verrouillées seulement, sous la RLS de l'organisation). Aucune
restitution ne lit le grand livre à côté. Les noms de colonnes interpolés dans le SQL passent par
une liste blanche ; toutes les valeurs sont des paramètres.

Les trois balances (générale, auxiliaire, analytique) et la balance par accord ne sont que des
ventilations différentes du même ensemble de lignes, **avec une ligne « non ventilé »** pour ce
qui n'a ni tiers, ni axe, ni accord : leur total est donc le même, au centime. `controler_balances`
le vérifie et refuse de répondre si ce n'est pas le cas.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.db import connection
from rest_framework.exceptions import PermissionDenied

from core.i18n import Liste, msg
from niveau1_socle.habilitations.permissions import est_habilite

ZERO = Decimal(0)

# nature de balance -> colonne de ventilation (None : le compte seul)
VENTILATIONS = {
    "generale": None,
    "auxiliaire": "tiers",
    "analytique_1": "dim1",
    "analytique_2": "dim2",
    "analytique_3": "dim3",
    "analytique_4": "dim4",
    "accord": "accord",
}


class RestitutionInvalide(ValueError):
    """Paramètres de restitution incohérents."""


class BalancesIncoherentes(ValueError):
    """Les balances d'un même périmètre ne donnent pas le même chiffre : on ne publie rien."""


@dataclass(frozen=True)
class LigneBalance:
    compte: str
    ventilation: str | None  # tiers, valeur d'axe ou accord ; None = non ventilé
    ouverture: Decimal  # solde avant la période (débit positif)
    debit: Decimal
    credit: Decimal
    solde: Decimal  # ouverture + débit - crédit


@dataclass(frozen=True)
class Balance:
    nature: str
    lignes: tuple[LigneBalance, ...]

    @property
    def total_debit(self) -> Decimal:
        return sum((ligne.debit for ligne in self.lignes), ZERO)

    @property
    def total_credit(self) -> Decimal:
        return sum((ligne.credit for ligne in self.lignes), ZERO)

    @property
    def total_ouverture(self) -> Decimal:
        return sum((ligne.ouverture for ligne in self.lignes), ZERO)

    @property
    def total_solde(self) -> Decimal:
        return sum((ligne.solde for ligne in self.lignes), ZERO)

    def par_compte(self) -> dict[str, tuple[Decimal, Decimal, Decimal]]:
        """`{compte: (ouverture, débit, crédit)}` : la clé de comparaison entre balances."""
        total: dict[str, list[Decimal]] = {}
        for ligne in self.lignes:
            cumul = total.setdefault(ligne.compte, [ZERO, ZERO, ZERO])
            cumul[0] += ligne.ouverture
            cumul[1] += ligne.debit
            cumul[2] += ligne.credit
        return {compte: tuple(valeurs) for compte, valeurs in total.items()}


@dataclass(frozen=True)
class LigneDetail:
    date: object
    journal: str
    numero: str | None
    ligne_no: int
    compte: str
    tiers: str | None
    libelle: str
    debit: Decimal
    credit: Decimal
    solde_cumule: Decimal | None  # seulement au grand livre


@dataclass(frozen=True)
class GrandLivre:
    compte: str
    report: Decimal  # solde avant la période
    lignes: tuple[LigneDetail, ...]
    total_debit: Decimal
    total_credit: Decimal
    solde: Decimal


@dataclass(frozen=True)
class Journal:
    code: str
    lignes: tuple[LigneDetail, ...]
    total_debit: Decimal
    total_credit: Decimal


def _exiger_consultation(utilisateur, project_id) -> None:
    if not est_habilite(utilisateur, "consulter", project_id):
        raise PermissionDenied(msg("restitutions.vous_etes_habilite_consulter_projet"))


def _periode(annee, periode_debut, periode_fin) -> None:
    if (
        type(annee) is not int
        or type(periode_debut) is not int
        or type(periode_fin) is not int
        or not 1 <= periode_debut <= periode_fin <= 12
    ):
        raise RestitutionInvalide(msg("restitutions.exercice_bornes_periode_invalides_1"))


# « avant la période » : les exercices antérieurs et les périodes précédentes de l'exercice.
AVANT = "(fiscal_year < %s OR (fiscal_year = %s AND period < %s))"
DANS = "(fiscal_year = %s AND period BETWEEN %s AND %s)"


def balance(
    utilisateur, project_id, annee: int, periode_debut: int, periode_fin: int, *, nature: str
) -> Balance:
    """Une balance par compte et, selon `nature`, par tiers, valeur d'axe ou accord.

    `nature` : voir `VENTILATIONS`. Les comptes sans mouvement ni solde n'apparaissent pas.
    """
    if nature not in VENTILATIONS:
        raise RestitutionInvalide(msg("restitutions.nature_balance_inconnue", nature=nature))
    _periode(annee, periode_debut, periode_fin)
    _exiger_consultation(utilisateur, project_id)
    colonne = VENTILATIONS[nature]  # liste blanche : jamais une valeur de l'appelant
    groupes = f"compte, {colonne}" if colonne else "compte"
    selection = (
        f"compte, {colonne} AS ventilation" if colonne else "compte, NULL::text AS ventilation"
    )
    sql = f"""
        SELECT {selection},
               COALESCE(SUM(debit - credit) FILTER (WHERE {AVANT}), 0) AS ouverture,
               COALESCE(SUM(debit) FILTER (WHERE {DANS}), 0) AS debit,
               COALESCE(SUM(credit) FILTER (WHERE {DANS}), 0) AS credit
          FROM moteur_ligneecriture
         WHERE project_id = %s
           AND (fiscal_year < %s OR (fiscal_year = %s AND period <= %s))
         GROUP BY {groupes}
        HAVING COALESCE(SUM(debit - credit) FILTER (WHERE {AVANT}), 0) <> 0
            OR COALESCE(SUM(debit) FILTER (WHERE {DANS}), 0) <> 0
            OR COALESCE(SUM(credit) FILTER (WHERE {DANS}), 0) <> 0
         ORDER BY compte, ventilation NULLS FIRST
    """  # noqa: S608  (colonne issue d'une liste blanche)
    avant = [annee, annee, periode_debut]
    dans = [annee, periode_debut, periode_fin]
    params = [*avant, *dans, *dans, project_id, annee, annee, periode_fin, *avant, *dans, *dans]
    with connection.cursor() as cur:
        cur.execute(sql, params)
        rangees = cur.fetchall()
    return Balance(
        nature=nature,
        lignes=tuple(
            LigneBalance(compte, ventilation, ouv, deb, cre, ouv + deb - cre)
            for compte, ventilation, ouv, deb, cre in rangees
        ),
    )


def controler_balances(
    utilisateur, project_id, annee: int, periode_debut: int, periode_fin: int
) -> dict[str, Balance]:
    """Calcule toutes les balances d'un périmètre et exige qu'elles donnent le même chiffre.

    Contrôles : (1) chaque balance est équilibrée (débits = crédits, ouverture et solde nuls au
    total) ; (2) pour chaque compte, ouverture, débits et crédits sont identiques d'une balance à
    l'autre. Sinon `BalancesIncoherentes` énumère TOUS les écarts.
    """
    balances = {
        nature: balance(utilisateur, project_id, annee, periode_debut, periode_fin, nature=nature)
        for nature in VENTILATIONS
    }
    ecarts: list[str] = []
    for nature, b in balances.items():
        if b.total_debit != b.total_credit:
            ecarts.append(
                msg(
                    "restitutions.balance_desequilibree_debit_credit",
                    nature=nature,
                    total_debit=b.total_debit,
                    total_credit=b.total_credit,
                )
            )
        if b.total_ouverture != 0:
            ecarts.append(
                msg(
                    "restitutions.balance_ouverture_s_equilibre",
                    nature=nature,
                    total_ouverture=b.total_ouverture,
                )
            )
    reference = balances["generale"].par_compte()
    for nature, b in balances.items():
        if nature == "generale":
            continue
        autre = b.par_compte()
        for compte in sorted(reference.keys() | autre.keys()):
            attendu = reference.get(compte, (ZERO, ZERO, ZERO))
            obtenu = autre.get(compte, (ZERO, ZERO, ZERO))
            if attendu != obtenu:
                ecarts.append(
                    msg(
                        "restitutions.compte_balance_balance_generale",
                        compte=compte,
                        nature=nature,
                        obtenu=obtenu,
                        attendu=attendu,
                    )
                )
    if ecarts:
        raise BalancesIncoherentes(Liste(ecarts, "\n"))
    return balances


_DETAIL = """
    SELECT accounting_date, journal, numero, ligne_no, compte, tiers,
           COALESCE(NULLIF(libelle_ligne, ''), libelle_ecriture), debit, credit
      FROM moteur_ligneecriture
     WHERE project_id = %s AND {filtre}
       AND fiscal_year = %s AND period BETWEEN %s AND %s
     ORDER BY accounting_date, numero, ligne_no
"""


def grand_livre(
    utilisateur,
    project_id,
    compte: str,
    annee: int,
    periode_debut: int,
    periode_fin: int,
    *,
    tiers: str | None = None,
) -> GrandLivre:
    """Les lignes d'un compte (et d'un tiers, si précisé), avec report et solde cumulé."""
    _periode(annee, periode_debut, periode_fin)
    _exiger_consultation(utilisateur, project_id)
    filtre = "compte = %s" + (" AND tiers = %s" if tiers is not None else "")
    cle = [compte] if tiers is None else [compte, tiers]
    with connection.cursor() as cur:
        cur.execute(
            f"""SELECT COALESCE(SUM(debit - credit), 0) FROM moteur_ligneecriture
                 WHERE project_id = %s AND {filtre} AND {AVANT}""",  # noqa: S608
            [project_id, *cle, annee, annee, periode_debut],
        )
        report = cur.fetchone()[0]
        cur.execute(
            _DETAIL.format(filtre=filtre), [project_id, *cle, annee, periode_debut, periode_fin]
        )
        rangees = cur.fetchall()
    cumul = report
    lignes = []
    for date, journal, numero, ligne_no, cpt, t, libelle, debit, credit in rangees:
        cumul += debit - credit
        lignes.append(
            LigneDetail(date, journal, numero, ligne_no, cpt, t, libelle, debit, credit, cumul)
        )
    total_debit = sum((ligne.debit for ligne in lignes), ZERO)
    total_credit = sum((ligne.credit for ligne in lignes), ZERO)
    return GrandLivre(
        compte,
        report,
        tuple(lignes),
        total_debit,
        total_credit,
        report + total_debit - total_credit,
    )


def journal(
    utilisateur, project_id, code: str, annee: int, periode_debut: int, periode_fin: int
) -> Journal:
    """Les lignes d'un journal par numéro de pièce. Débits et crédits s'y égalent."""
    _periode(annee, periode_debut, periode_fin)
    _exiger_consultation(utilisateur, project_id)
    with connection.cursor() as cur:
        cur.execute(
            _DETAIL.format(filtre="journal = %s"),
            [project_id, code, annee, periode_debut, periode_fin],
        )
        rangees = cur.fetchall()
    lignes = tuple(
        LigneDetail(date, jrn, numero, ligne_no, cpt, t, libelle, debit, credit, None)
        for date, jrn, numero, ligne_no, cpt, t, libelle, debit, credit in rangees
    )
    return Journal(
        code,
        lignes,
        sum((ligne.debit for ligne in lignes), ZERO),
        sum((ligne.credit for ligne in lignes), ZERO),
    )
