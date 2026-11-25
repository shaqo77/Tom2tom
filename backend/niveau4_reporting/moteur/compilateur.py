"""Compilateur d'états en une requête d'agrégation. Voir L0-T05.

La sélection du modèle et la matérialisation des règles Django ont lieu avant
l'appel : `generer` n'exécute qu'une requête sur les lignes d'écriture.
"""

import datetime
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import connection
from django.db.models import QuerySet

from core.i18n import msg
from niveau4_reporting.mapping.models import RegleMapping
from niveau4_reporting.mapping.resolveur import (
    MappingIncomplet,
    construire_cas_sql,
    construire_predicat,
)

from .assertions import (
    AssertionPreparee,
    AssertionsViolees,
    analyser_assertion,
    controler_assertion,
)
from .dependances import ordonner
from .formules import evaluer
from .sources_externes import lire as lire_source_externe
from .sources_externes import verifier

ZERO = Decimal(0)
COLONNES_SOURCE = (
    "compte, fiscal_year, period, accounting_date, debit, credit, "
    "dim1, dim2, dim3, dim4, accord, categorie, site"
)
# Les paramètres d'une plage libre : une liste blanche de DEUX noms (distincts de `date_debut` et
# `date_fin`, que les sources externes de trésorerie emploient déjà) ; leurs valeurs sont des
# paramètres SQL, jamais du texte collé dans la requête.
PARAMETRES_PLAGE = ("plage_debut", "plage_fin")
_DATE_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


class ModeleEtatInvalide(ValueError):
    """Le modèle JSON ne peut pas produire un état déterministe."""


@dataclass(frozen=True)
class SelectionCompilee:
    """Prédicat conservé pour la traçabilité descendante (voir `tracabilite.tracer`)."""

    sql: str
    params: tuple
    sql_source: str
    params_source: tuple
    mapping: str | None
    target: str | None
    signe: int


@dataclass(frozen=True)
class EtatCompile:
    sql: str
    params: list
    source_where: str
    source_params: tuple
    colonnes: tuple[str, ...]
    agregats: tuple[str, ...]
    formules: dict[str, str]
    ordre_formules: tuple[str, ...]
    codes_connus: list[str]
    selections: dict[str, SelectionCompilee]
    conditions_colonnes: dict[str, tuple[str, tuple]]
    index_valeurs: dict[tuple[str, str], int]
    mappings_utilises: tuple[str, ...]
    assertions: dict[str, AssertionPreparee]
    prefixes_balance: tuple[str, ...]
    index_balances: dict[tuple[str, str], int]
    # Colonnes de mapping de la CTE « source » et leurs paramètres : la
    # traçabilité (L0-T07) rejoue la même CTE pour lister les lignes.
    colonnes_mapping: tuple[str, ...]
    params_cas: tuple
    # Rubriques lues auprès d'une source externe (voir `sources_externes`) : pas de SQL pour elles.
    externes: tuple = ()


@dataclass(frozen=True)
class EtatProduit:
    code: str
    version: int | None
    colonnes: tuple[str, ...]
    valeurs: dict[str, dict[str, Decimal]]
    controles: tuple
    publiable: bool

    def __getitem__(self, code_rubrique: str) -> dict[str, Decimal]:
        return self.valeurs[code_rubrique]


def _valider_modele(
    modele: Mapping[str, Any],
) -> tuple[list, list, list, dict[str, str], dict[str, str]]:
    lignes = modele.get("rows")
    colonnes = modele.get("columns")
    if not isinstance(lignes, list) or not lignes:
        raise ModeleEtatInvalide(msg("compilateur.rows_doit_contenir_rubriques_etat"))
    if not isinstance(colonnes, list) or not colonnes:
        raise ModeleEtatInvalide(msg("compilateur.columns_doit_contenir_moins_colonne"))
    codes = [ligne.get("code") for ligne in lignes]
    if any(not isinstance(code, str) or not code for code in codes) or len(set(codes)) != len(
        codes
    ):
        raise ModeleEtatInvalide(msg("compilateur.chaque_rubrique_doit_porter_code"))
    codes_colonnes = [colonne.get("code") for colonne in colonnes]
    if any(not isinstance(code, str) or not code for code in codes_colonnes) or len(
        set(codes_colonnes)
    ) != len(codes_colonnes):
        raise ModeleEtatInvalide(msg("compilateur.chaque_colonne_doit_porter_code"))
    agregats = [ligne for ligne in lignes if ligne.get("type") == "aggregate"]
    externes = [ligne for ligne in lignes if ligne.get("type") == "external"]
    if not agregats and not externes:
        raise ModeleEtatInvalide(msg("compilateur.etat_l0_doit_contenir_rubrique"))
    for ligne in lignes:
        if ligne.get("type") not in {"heading", "aggregate", "computed", "external"}:
            raise ModeleEtatInvalide(msg("compilateur.type_rubrique_inconnu", v1=ligne.get("type")))
    for (
        ligne
    ) in externes:  # source et élément déclarés : refus à la compilation, pas à la génération
        verifier(ligne.get("source"), ligne.get("item"))
    formules = {
        ligne["code"]: ligne.get("formula") for ligne in lignes if ligne.get("type") == "computed"
    }
    if any(not isinstance(formule, str) or not formule for formule in formules.values()):
        raise ModeleEtatInvalide(msg("compilateur.rubrique_computed_exige_formule"))
    assertions = {ligne["code"]: ligne["assert"] for ligne in lignes if ligne.get("assert")}
    return lignes, colonnes, agregats, formules, assertions


def _date_de_plage(valeur: Any, nom: str) -> datetime.date:
    """Une date de plage : un objet `date` ou une chaîne ISO `AAAA-MM-JJ`, rien d'autre."""
    if isinstance(valeur, datetime.datetime):
        valeur = None  # un horodatage n'est pas une date : on ne tronque pas en silence
    if isinstance(valeur, datetime.date):
        return valeur
    if isinstance(valeur, str) and _DATE_ISO.fullmatch(valeur):
        try:
            return datetime.date.fromisoformat(valeur)
        except ValueError:
            pass
    raise ModeleEtatInvalide(msg("compilateur.plage_date_illisible", champ=nom))


def plage_libre(parametres: Mapping[str, Any]) -> tuple[datetime.date, datetime.date] | None:
    """La plage `[plage_debut, plage_fin]` (bornes INCLUSES) demandée, ou `None` si aucune.

    Dès que l'un des deux paramètres figure, les deux sont exigés et doivent être lisibles."""
    if not any(nom in parametres for nom in PARAMETRES_PLAGE):
        return None
    debut = _date_de_plage(parametres.get("plage_debut"), "plage_debut")
    fin = _date_de_plage(parametres.get("plage_fin"), "plage_fin")
    if fin < debut:
        raise ModeleEtatInvalide(
            msg("compilateur.plage_inversee", debut=debut.isoformat(), fin=fin.isoformat())
        )
    return debut, fin


def _parametres_source(parametres: Mapping[str, Any]) -> tuple[str, tuple, int | None, int | None]:
    plage = plage_libre(parametres)
    if plage is not None:  # plage libre : ni exercice ni période courante
        try:
            project_id = parametres["project_id"]
        except KeyError as e:
            raise ModeleEtatInvalide(
                msg("compilateur.parametre_obligatoire_manquant", v1=e.args[0])
            ) from e
        where = "project_id = %s AND accounting_date BETWEEN %s AND %s"
        return where, (project_id, *plage), None, None
    try:
        project_id = parametres["project_id"]
        annee = parametres["fiscal_year"]
        courante = parametres["current_period"]
    except KeyError as e:
        raise ModeleEtatInvalide(
            msg("compilateur.parametre_obligatoire_manquant", v1=e.args[0])
        ) from e
    if type(annee) is not int or type(courante) is not int or not 1 <= courante <= 12:
        raise ModeleEtatInvalide(msg("compilateur.exercice_periode_courante_invalide"))
    where = "project_id = %s AND (fiscal_year < %s OR (fiscal_year = %s AND period <= %s))"
    return where, (project_id, annee, annee, courante), annee, courante


def _condition_colonne(
    colonne: Mapping[str, Any],
    annee: int | None,
    courante: int | None,
    plage: tuple[datetime.date, datetime.date] | None = None,
) -> tuple[str, tuple]:
    periode = colonne.get("period")
    if periode == "range":
        if plage is None:
            raise ModeleEtatInvalide(msg("compilateur.plage_parametres_manquants"))
        return "accounting_date BETWEEN %s AND %s", plage
    if plage is not None:  # une plage libre ne se mélange pas aux périodes de l'exercice
        raise ModeleEtatInvalide(msg("compilateur.plage_colonnes_exclusives"))
    if periode == "current_quarter":
        debut = ((courante - 1) // 3) * 3 + 1
    elif periode == "year_to_date":
        debut = 1
    elif periode in {"inception_to_date", "current_period"}:
        debut = None
    else:
        raise ModeleEtatInvalide(msg("compilateur.type_periode_inconnu", periode=periode))
    if periode == "inception_to_date":
        return "(fiscal_year < %s OR (fiscal_year = %s AND period <= %s))", (
            annee,
            annee,
            courante,
        )
    if periode == "current_period":
        return "fiscal_year = %s AND period = %s", (annee, courante)
    return "fiscal_year = %s AND period BETWEEN %s AND %s", (annee, debut, courante)


def _resoudre_parametre(valeur: Any, parametres: Mapping[str, Any]) -> Any:
    if isinstance(valeur, str) and valeur.startswith("$param."):
        cle = valeur.removeprefix("$param.")
        if cle not in parametres:
            raise ModeleEtatInvalide(msg("compilateur.parametre_selection_manquant", parametre=cle))
        return parametres[cle]
    return valeur


def _signe(ligne: Mapping[str, Any]) -> int:
    signe = ligne.get("sign", 1)
    if signe in {1, "debit"}:
        return 1
    if signe in {-1, "credit"}:
        return -1
    raise ModeleEtatInvalide(msg("compilateur.signe_invalide", v1=ligne["code"]))


def _selection(
    ligne: Mapping[str, Any],
    parametres: Mapping[str, Any],
    cas_mapping: dict[str, tuple[str, list]],
    alias_mapping: dict[str, str],
) -> SelectionCompilee:
    select = ligne.get("select")
    if not isinstance(select, Mapping):
        raise ModeleEtatInvalide(msg("compilateur.selection_absente", v1=ligne["code"]))
    if inconnues := set(select) - {"mapping", "target", "filters", "accounts"}:
        raise ModeleEtatInvalide(msg("compilateur.cle_selection_inconnue", v1=sorted(inconnues)))
    filtres = select.get("filters", {})
    if not isinstance(filtres, Mapping) or "accounts" in filtres:
        raise ModeleEtatInvalide(msg("compilateur.filters_doit_etre_objet_filtres"))
    filtres = {cle: _resoudre_parametre(valeur, parametres) for cle, valeur in filtres.items()}
    mapping_code = select.get("mapping")
    target = select.get("target")

    if mapping_code is None:
        if target is not None or "accounts" not in select:
            raise ModeleEtatInvalide(
                msg("compilateur.selection_directe_invalide", v1=ligne["code"])
            )
        predicat, params = construire_predicat({"accounts": select["accounts"], **filtres})
        return SelectionCompilee(
            sql=predicat,
            params=tuple(params),
            sql_source=predicat,
            params_source=tuple(params),
            mapping=None,
            target=None,
            signe=_signe(ligne),
        )

    if (
        not isinstance(mapping_code, str)
        or mapping_code not in cas_mapping
        or not isinstance(target, str)
        or not target
        or "accounts" in select
    ):
        raise ModeleEtatInvalide(msg("compilateur.mapping_cible_invalide", v1=ligne["code"]))
    cas, params_cas = cas_mapping[mapping_code]
    sql = f"({cas}) = %s"
    params = [*params_cas, target]
    sql_source = f"{alias_mapping[mapping_code]} = %s"
    params_source = [target]
    if filtres:
        predicat_filtres, params_filtres = construire_predicat(filtres)
        sql = f"({sql}) AND ({predicat_filtres})"
        params += params_filtres
        sql_source = f"({sql_source}) AND ({predicat_filtres})"
        params_source += params_filtres
    return SelectionCompilee(
        sql=sql,
        params=tuple(params),
        sql_source=sql_source,
        params_source=tuple(params_source),
        mapping=mapping_code,
        target=target,
        signe=_signe(ligne),
    )


def compiler(
    modele: Mapping[str, Any],
    mappings: Mapping[str, Iterable[RegleMapping]],
    parametres: Mapping[str, Any],
) -> EtatCompile:
    """Compile tout l'état sans exécuter de requête."""
    lignes, colonnes, agregats, formules, assertions_brutes = _valider_modele(modele)
    source_where, source_params, annee, courante = _parametres_source(parametres)
    plage_demandee = plage_libre(parametres)
    codes_connus = [ligne["code"] for ligne in lignes]
    ordre_formules = tuple(ordonner(formules, codes_connus))
    assertions = {
        code: analyser_assertion(expression, codes_connus)
        for code, expression in assertions_brutes.items()
    }
    # Un même préfixe cité par deux assertions ne donne qu'une colonne : la
    # promesse d'une requête unique vaut aussi pour ce qui la vérifie.
    prefixes_balance = tuple(
        dict.fromkeys(
            prefixe for assertion in assertions.values() for prefixe in assertion.prefixes
        )
    )
    mappings_utilises = tuple(
        dict.fromkeys(
            ligne["select"].get("mapping")
            for ligne in agregats
            if isinstance(ligne.get("select"), Mapping)
            and isinstance(ligne["select"].get("mapping"), str)
        )
    )

    cas_mapping: dict[str, tuple[str, list]] = {}
    for code in mappings_utilises:
        if code not in mappings:
            raise ModeleEtatInvalide(msg("compilateur.regles_absentes_mapping", code=code))
        regles = mappings[code]
        if isinstance(regles, QuerySet):
            raise ModeleEtatInvalide(msg("compilateur.materialisez_regles_list_avant_generation"))
        cas_mapping[code] = construire_cas_sql(regles)
    alias_mapping = {code: f"mapping_{i}" for i, code in enumerate(mappings_utilises)}
    selections = {
        ligne["code"]: _selection(ligne, parametres, cas_mapping, alias_mapping)
        for ligne in agregats
    }
    conditions_colonnes = {
        colonne["code"]: _condition_colonne(colonne, annee, courante, plage_demandee)
        for colonne in colonnes
    }

    colonnes_mapping = [
        f"{cas_mapping[code][0]} AS {alias_mapping[code]}" for code in mappings_utilises
    ]
    source_select = ", ".join([COLONNES_SOURCE, *colonnes_mapping])
    valeurs_sql: list[str] = []
    params_valeurs: list = []
    index_valeurs: dict[tuple[str, str], int] = {}
    for ligne in agregats:
        code = ligne["code"]
        selection = selections[code]
        montant = "(debit - credit)" if selection.signe == 1 else "(credit - debit)"
        for colonne in colonnes:
            code_colonne = colonne["code"]
            condition, params_condition = conditions_colonnes[code_colonne]
            alias = f"valeur_{len(valeurs_sql)}"
            valeurs_sql.append(
                f"COALESCE(SUM(CASE WHEN ({selection.sql_source}) AND ({condition}) "
                f"THEN {montant} ELSE 0 END), 0) AS {alias}"
            )
            params_valeurs += [*selection.params_source, *params_condition]
            index_valeurs[(code, code_colonne)] = len(valeurs_sql) - 1

    index_balances: dict[tuple[str, str], int] = {}
    for prefixe in prefixes_balance:
        for colonne in colonnes:
            code_colonne = colonne["code"]
            condition, params_condition = conditions_colonnes[code_colonne]
            alias = f"balance_{len(index_balances)}"
            valeurs_sql.append(
                f"COALESCE(SUM(CASE WHEN compte LIKE %s AND ({condition}) "
                f"THEN (debit - credit) ELSE 0 END), 0) AS {alias}"
            )
            # Le préfixe est validé à l'analyse : ni « % » ni « _ » n'y survit,
            # donc rien à échapper ici.
            params_valeurs += [f"{prefixe}%", *params_condition]
            index_balances[(prefixe, code_colonne)] = len(valeurs_sql) - 1

    if not valeurs_sql and not mappings_utilises:  # état uniquement externe : colonne neutre
        valeurs_sql.append("0 AS neutre")
    for i, _ in enumerate(mappings_utilises):
        valeurs_sql.append(
            f"ARRAY_AGG(DISTINCT compte) FILTER (WHERE mapping_{i} IS NULL "
            f"AND (debit <> 0 OR credit <> 0)) AS non_mappe_{i}"
        )
    sql = f"""
        WITH source AS (
            SELECT {source_select}
            FROM moteur_ligneecriture
            WHERE {source_where}
        )
        SELECT {", ".join(valeurs_sql)}
        FROM source
        GROUP BY ()
    """
    params_cas = [parametre for code in mappings_utilises for parametre in cas_mapping[code][1]]
    return EtatCompile(
        sql=sql,
        params=[*params_cas, *source_params, *params_valeurs],
        source_where=source_where,
        source_params=source_params,
        colonnes=tuple(colonne["code"] for colonne in colonnes),
        agregats=tuple(ligne["code"] for ligne in agregats),
        formules=formules,
        ordre_formules=ordre_formules,
        codes_connus=codes_connus,
        selections=selections,
        conditions_colonnes=conditions_colonnes,
        index_valeurs=index_valeurs,
        mappings_utilises=mappings_utilises,
        assertions=assertions,
        prefixes_balance=prefixes_balance,
        index_balances=index_balances,
        colonnes_mapping=tuple(colonnes_mapping),
        params_cas=tuple(params_cas),
        externes=tuple(ligne for ligne in lignes if ligne.get("type") == "external"),
    )


def generer(
    modele: Mapping[str, Any],
    mappings: Mapping[str, Iterable[RegleMapping]],
    parametres: Mapping[str, Any],
) -> EtatProduit:
    """Exécute l'unique requête, contrôle le mapping puis calcule les rubriques."""
    etat = compiler(modele, mappings, parametres)
    with connection.cursor() as cur:
        cur.execute(etat.sql, etat.params)
        resultat = cur.fetchone()
    if resultat is None:  # GROUP BY () produit normalement toujours une ligne.
        raise RuntimeError("La requête d'agrégation n'a produit aucun résultat")

    debut_controles = len(etat.index_valeurs) + len(etat.index_balances)
    comptes = []
    for i, _ in enumerate(etat.mappings_utilises):
        comptes += resultat[debut_controles + i] or []
    if comptes:
        raise MappingIncomplet(comptes)

    valeurs = {code: {colonne: ZERO for colonne in etat.colonnes} for code in etat.codes_connus}
    for (code, colonne), index in etat.index_valeurs.items():
        valeur = resultat[index]
        valeurs[code][colonne] = valeur if isinstance(valeur, Decimal) else Decimal(str(valeur))
    for ligne in etat.externes:  # la valeur d'une source externe vaut pour chaque colonne
        valeur_externe = lire_source_externe(ligne["source"], ligne["item"], parametres)
        for colonne in etat.colonnes:
            valeurs[ligne["code"]][colonne] = valeur_externe
    for code in etat.ordre_formules:
        for colonne in etat.colonnes:
            valeurs_colonne = {
                code_connu: valeurs[code_connu][colonne] for code_connu in etat.codes_connus
            }
            valeurs[code][colonne] = evaluer(
                etat.formules[code], valeurs_colonne, etat.codes_connus
            )
    balances: dict[str, dict[str, Decimal]] = {colonne: {} for colonne in etat.colonnes}
    for (prefixe, colonne), index in etat.index_balances.items():
        solde = resultat[index]
        balances[colonne][prefixe] = solde if isinstance(solde, Decimal) else Decimal(str(solde))

    controles = tuple(
        controler_assertion(
            assertion,
            {code_connu: valeurs[code_connu][colonne] for code_connu in etat.codes_connus},
            etat.codes_connus,
            balances[colonne],
            rubrique=code,
            colonne=colonne,
        )
        for code, assertion in etat.assertions.items()
        for colonne in etat.colonnes
    )
    # Une assertion fausse arrête la génération. Un état incohérent qu'on
    # publierait en signalant l'écart ailleurs serait un état incohérent publié.
    if any(not controle.reussi for controle in controles):
        raise AssertionsViolees(controles)

    return EtatProduit(
        code=modele["code"],
        version=modele.get("version"),
        colonnes=etat.colonnes,
        valeurs=valeurs,
        controles=controles,
        publiable=True,
    )
