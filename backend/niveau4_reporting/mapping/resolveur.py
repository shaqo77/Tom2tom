"""Compilation et contrôle d'exhaustivité du mapping. Voir L0-T04.

Les valeurs de configuration sont toujours des paramètres SQL. Les noms de
colonnes passent par une liste blanche : aucune expression SQL utilisateur
n'est interpolée dans une requête.
"""

import datetime
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from django.db import connection
from django.db.models import Q

from .models import RegleMapping, StatutMapping, TableMapping

CHAMPS_FILTRES = {
    "dim1": "dim1",
    "dim2": "dim2",
    "dim3": "dim3",
    "dim4": "dim4",
    "accord": "accord",
    "agreement": "accord",
    "categorie": "categorie",
    "site": "site",
}


class MappingInvalide(ValueError):
    """La configuration ne peut pas être compilée sans ambiguïté."""


class MappingIndisponible(LookupError):
    """Aucune version active ne couvre la date d'effet demandée."""


class MappingIncomplet(ValueError):
    """Des lignes mouvementées ne sont couvertes par aucune règle."""

    def __init__(self, comptes: Iterable[str]):
        self.comptes = tuple(sorted(set(comptes)))
        liste = ", ".join(self.comptes)
        super().__init__(f"Mapping incomplet — comptes non couverts : {liste}")


def _liste_valeurs(valeurs: Any, champ: str) -> list[str]:
    if isinstance(valeurs, str):
        valeurs = [valeurs]
    if (
        not isinstance(valeurs, Sequence)
        or isinstance(valeurs, str | bytes)
        or not valeurs
        or any(not isinstance(v, str) or not v for v in valeurs)
    ):
        raise MappingInvalide(f"{champ} doit contenir au moins une valeur textuelle")
    return list(valeurs)


def _ajouter_comptes(match: Mapping[str, Any], conds: list[str], params: list) -> None:
    if "accounts" not in match:
        return
    plages = match["accounts"]
    if not isinstance(plages, Sequence) or isinstance(plages, str | bytes) or not plages:
        raise MappingInvalide("accounts doit contenir au moins une fourchette de comptes")
    ors = []
    for plage in plages:
        if (
            not isinstance(plage, Sequence)
            or isinstance(plage, str | bytes)
            or len(plage) != 2
            or any(not isinstance(borne, str) or not borne for borne in plage)
        ):
            raise MappingInvalide("fourchette de comptes invalide : [début, fin] attendu")
        debut, fin = plage
        if debut > fin:
            raise MappingInvalide(f"fourchette inversée : {debut} > {fin}")
        # La borne haute est inclusive, y compris pour les sous-comptes préfixés.
        ors.append("(compte >= %s AND compte < %s)")
        params += [debut, fin + "\uffff"]
    conds.append("(" + " OR ".join(ors) + ")")


def construire_predicat(match: Mapping[str, Any]) -> tuple[str, list]:
    """Compile une sélection paramétrée sur les colonnes de LigneEcriture."""
    if not isinstance(match, Mapping):
        raise MappingInvalide("match doit être un objet JSON")
    inconnues = set(match) - {"accounts", *CHAMPS_FILTRES}
    if inconnues:
        raise MappingInvalide(f"clé de filtre inconnue : {sorted(inconnues)!r}")
    if not match:
        raise MappingInvalide("une règle doit contenir au moins un critère")

    conds: list[str] = []
    params: list = []
    _ajouter_comptes(match, conds, params)
    for champ, colonne in CHAMPS_FILTRES.items():
        if champ in match:
            valeurs = _liste_valeurs(match[champ], champ)
            conds.append(f"{colonne} = ANY(%s)")
            params.append(valeurs)
    return " AND ".join(conds), params


def construire_cas_sql(regles: Iterable[RegleMapping]) -> tuple[str, list]:
    """Compile les règles en un CASE ; la première correspondance gagne."""
    morceaux, params = [], []
    for regle in sorted(regles, key=lambda r: r.priority):
        if getattr(regle, "condition_expr", None):
            raise MappingInvalide(
                "condition_expr n'est pas exécutable : utilisez les filtres match déclarés"
            )
        if not isinstance(regle.target_code, str) or not regle.target_code:
            raise MappingInvalide("target_code doit être une rubrique non vide")
        predicat, params_predicat = construire_predicat(regle.match)
        morceaux.append(f"WHEN {predicat} THEN %s")
        params += [*params_predicat, regle.target_code]

    if not morceaux:
        return "NULL", []
    return "CASE " + " ".join(morceaux) + " ELSE NULL END", params


def table_active(
    *,
    code: str,
    donor_profile_id,
    project_id,
    date_effet: datetime.date,
) -> TableMapping:
    """Choisit la plus récente version active applicable, sous RLS.

    Validité en intervalle semi-ouvert [valid_from, valid_to[ (guide §B.6) :
    le jour de fin n'appartient plus à la version.
    """
    table = (
        TableMapping.objects.filter(
            code=code,
            donor_profile_id=donor_profile_id,
            project_id=project_id,
            status=StatutMapping.ACTIF,
            valid_from__lte=date_effet,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=date_effet))
        .order_by("-version")
        .first()
    )
    if table is None:
        raise MappingIndisponible(
            f"Aucun mapping actif {code!r} à la date d'effet {date_effet.isoformat()}"
        )
    return table


def _parametres_periode(periode: Mapping[str, Any]) -> tuple[str, list, datetime.date]:
    try:
        project_id = periode["project_id"]
        fiscal_year = periode["fiscal_year"]
    except KeyError as e:
        raise MappingInvalide(f"paramètre de période manquant : {e.args[0]}") from e
    debut = periode.get("period_from", 1)
    fin = periode.get("period_to", 12)
    if (
        type(fiscal_year) is not int
        or type(debut) is not int
        or type(fin) is not int
        or not 1 <= debut <= fin <= 12
    ):
        raise MappingInvalide("exercice ou plage de périodes invalide")
    date_effet = periode.get("date_effet") or datetime.date(fiscal_year, 12, 31)
    where = (
        "project_id = %s AND fiscal_year = %s "
        "AND period BETWEEN %s AND %s AND (debit <> 0 OR credit <> 0)"
    )
    return where, [project_id, fiscal_year, debut, fin], date_effet


def comptes_non_mappes(table: TableMapping, periode: Mapping[str, Any]) -> list[str]:
    """Nomme les comptes ayant au moins une ligne mouvementée non couverte."""
    where, params, date_effet = _parametres_periode(periode)
    if (
        table.status != StatutMapping.ACTIF
        or date_effet < table.valid_from
        or (table.valid_to is not None and date_effet >= table.valid_to)
    ):
        raise MappingIndisponible(f"La version {table.version} n'est pas active à {date_effet}")
    regles = list(table.regles.all().order_by("priority"))
    cas, params_cas = construire_cas_sql(regles)
    # Pas de filtre org_id : la politique RLS impose le périmètre courant.
    sql = f"""
        SELECT compte FROM moteur_ligneecriture
        WHERE {where} AND ({cas}) IS NULL
        GROUP BY compte ORDER BY compte
    """
    with connection.cursor() as cur:
        cur.execute(sql, [*params, *params_cas])
        return [row[0] for row in cur.fetchall()]


def verifier_exhaustivite(table: TableMapping, periode: Mapping[str, Any]) -> None:
    """Bloque la génération si une seule ligne échappe au mapping."""
    if comptes := comptes_non_mappes(table, periode):
        raise MappingIncomplet(comptes)
