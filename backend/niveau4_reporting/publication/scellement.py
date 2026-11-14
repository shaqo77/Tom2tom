"""Le scellement : une empreinte stable de tout ce qui détermine le résultat d'un rapport. L6-T03.

Deux rapports qui portent la même empreinte ont le même modèle, la même période, les mêmes
paramètres, la même configuration, les mêmes mappings, le même jeu d'écritures et les mêmes
valeurs. C'est ce qui permet de tenir « un rapport historique reste reproductible » : la
régénération (L6-T04) compare des empreintes, et en cas d'écart cherche pourquoi.

Choix qui s'écartent de l'esquisse du plan, et pourquoi :
- SHA-256 partout, y compris pour le jeu de données (le plan proposait MD5, dont on évite l'usage
  dans tout ce qui prétend prouver une intégrité) ;
- le jeu de données se lit dans la vue `moteur_ligneecriture` (règle du projet : jamais le grand
  livre directement), donc sous la RLS et limité aux écritures comptabilisées ;
- les montants sont écrits sous une forme canonique (`10`, `10.5`, jamais `10.50` ni `1E+1`) : un
  même nombre ne peut pas produire deux empreintes ;
- la charge est versionnée (`schema`) : changer ce qu'on scelle un jour ne fera pas passer d'anciens
  scellés pour invalides sans que ce soit dit.
"""

import hashlib
import json
from decimal import Decimal
from typing import Protocol

from django.db import connection

SCHEMA = 1
VIDE = hashlib.sha256(b"").digest()


class Scellable(Protocol):
    """Ce qu'un rapport doit exposer pour être scellé."""

    template: object  # .code
    template_version: int
    period_from: object
    period_to: object
    params: dict
    config_version: object
    mapping_versions: object
    dataset_hash: bytes
    values: dict


def montant_canonique(valeur) -> str:
    """Un nombre, écrit d'une seule façon (`Decimal('10.50')` et `Decimal('10.5')` : `10.5`)."""
    if isinstance(valeur, float):
        raise TypeError("un montant scellé n'est jamais un float")
    nombre = Decimal(str(valeur))
    if not nombre.is_finite():
        raise ValueError(f"valeur non finie : {valeur!r}")
    if nombre == 0:
        return "0"
    texte = format(nombre.normalize(), "f")
    return texte


def _canonique(objet):
    """Rend un objet JSON-compatible déterministe ; refuse ce qui ne l'est pas."""
    if isinstance(objet, Decimal):
        return montant_canonique(objet)
    if isinstance(objet, float):
        raise TypeError("un float ne se scelle pas : utilisez Decimal ou str")
    if isinstance(objet, dict):
        return {str(k): _canonique(v) for k, v in objet.items()}
    if isinstance(objet, list | tuple):
        return [_canonique(v) for v in objet]
    if isinstance(objet, set | frozenset):
        raise TypeError("un ensemble n'a pas d'ordre : fournissez une liste triée")
    if objet is None or isinstance(objet, bool | int | str):
        return objet
    return str(objet)  # dates, UUID : leur forme texte est stable


def charge_du_scellement(rapport: Scellable) -> dict:
    return {
        "schema": SCHEMA,
        "template": [rapport.template.code, rapport.template_version],
        "period": [str(rapport.period_from), str(rapport.period_to)],
        "params": _canonique(rapport.params),
        "config_version": _canonique(rapport.config_version),
        "mapping_versions": _canonique(rapport.mapping_versions),
        "dataset_hash": bytes(rapport.dataset_hash).hex(),
        "values": {k: montant_canonique(v) for k, v in sorted(rapport.values.items())},
    }


def sceller(rapport: Scellable) -> bytes:
    """L'empreinte SHA-256 (32 octets) de tout ce qui détermine le résultat du rapport."""
    texte = json.dumps(
        charge_du_scellement(rapport), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(texte.encode("ascii")).digest()


def empreinte_jeu_de_donnees(predicat_sql: str, params: list | tuple) -> bytes:
    """Empreinte des lignes comptabilisées retenues : toute modification du périmètre la change.

    `predicat_sql` vient du résolveur de mappings (colonnes de la vue en liste blanche) ;
    les valeurs sont des paramètres. Aucun filtre d'organisation ici : la RLS le fait. Aucune
    ligne : empreinte de la chaîne vide (distincte d'un jeu non calculé, qui n'a pas d'empreinte).
    """
    with connection.cursor() as cur:
        cur.execute(
            f"""
            SELECT encode(sha256(convert_to(COALESCE(string_agg(
                     concat_ws(':', id::text, compte, accounting_date::text, debit::text,
                               credit::text, devise, taux::text, COALESCE(accord, ''),
                               COALESCE(categorie, '')),
                     '|' ORDER BY id), ''), 'UTF8')), 'hex')
              FROM moteur_ligneecriture WHERE {predicat_sql}
            """,  # noqa: S608  (prédicat issu de la liste blanche du résolveur)
            list(params),
        )
        return bytes.fromhex(cur.fetchone()[0])
