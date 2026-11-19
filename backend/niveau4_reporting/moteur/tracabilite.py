"""Traçabilité descendante : d'une cellule d'état aux écritures qui l'alimentent.

Voir L0-T07. Le compilateur conserve, pour chaque rubrique d'agrégat, son
prédicat de sélection ; la traçabilité rejoue ce prédicat et ce même filtre de
période en `SELECT` des lignes au lieu de `SUM`. Aucun filtre `org_id` n'est
écrit ici : la Row-Level Security impose le périmètre courant (règle n°4).
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from django.db import connection

from core.i18n import msg

from .compilateur import ZERO, EtatCompile


class TracabiliteImpossible(LookupError):
    """La cellule demandée n'existe pas ou n'est pas alimentée par des écritures."""


@dataclass(frozen=True)
class LigneTracee:
    """Une ligne d'écriture, avec sa contribution signée à la cellule."""

    id: uuid.UUID
    accounting_date: object
    fiscal_year: int
    period: int
    compte: str
    debit: Decimal
    credit: Decimal
    montant: Decimal


@dataclass(frozen=True)
class Trace:
    rubrique: str
    colonne: str
    lignes: tuple[LigneTracee, ...]
    total: Decimal


def tracer(etat: EtatCompile, rubrique: str, colonne: str) -> Trace:
    """Liste les lignes d'écriture qui composent la cellule `(rubrique, colonne)`.

    Seule une rubrique d'agrégat se trace : un titre n'a pas de montant et une
    rubrique calculée se retrace par les rubriques qu'elle référence.
    """
    selection = etat.selections.get(rubrique)
    if selection is None:
        raise TracabiliteImpossible(msg("tracabilite.rubrique_agregat_cet_etat", rubrique=rubrique))
    if colonne not in etat.conditions_colonnes:
        raise TracabiliteImpossible(msg("tracabilite.colonne_inconnue", colonne=colonne))

    condition, params_condition = etat.conditions_colonnes[colonne]
    montant = "(debit - credit)" if selection.signe == 1 else "(credit - debit)"
    colonnes_source = ", ".join(
        ["id, accounting_date, fiscal_year, period, compte, debit, credit", *etat.colonnes_mapping]
    )
    sql = f"""
        WITH source AS (
            SELECT {colonnes_source}, project_id,
                   dim1, dim2, dim3, dim4, accord, categorie, site
            FROM moteur_ligneecriture
            WHERE {etat.source_where}
        )
        SELECT id, accounting_date, fiscal_year, period, compte, debit, credit,
               {montant} AS montant
        FROM source
        WHERE ({selection.sql_source}) AND ({condition})
        ORDER BY accounting_date, fiscal_year, period, compte, id
    """
    params = [*etat.params_cas, *etat.source_params, *selection.params_source, *params_condition]
    with connection.cursor() as cur:
        cur.execute(sql, params)
        lignes = tuple(LigneTracee(*enregistrement) for enregistrement in cur.fetchall())
    total = sum((ligne.montant for ligne in lignes), ZERO)
    return Trace(rubrique=rubrique, colonne=colonne, lignes=lignes, total=total)
