"""Le dictionnaire de données, généré depuis les modèles. Voir L8-T04.

Table, colonne, type, nullité, clé primaire, relation, contraintes, description. Publié ouvertement
(`DICTIONNAIRE_DE_DONNEES.md`) : le client peut lire son schéma sans nous le demander, c'est la
moitié de la réversibilité. Un test échoue si le fichier publié n'est plus celui que les modèles
produisent : la documentation ne peut pas vieillir en silence.

Les descriptions de colonnes viennent de `help_text` quand il existe, sinon du vocabulaire
des colonnes techniques communes ; le reste est vide, et le dit (« — »).
"""

import re

from django.apps import apps
from django.db import connection
from django.db import models as dj

VERSION = 1

COLONNES_COMMUNES = {
    "id": "Identifiant unique (UUID) de la ligne.",
    "org_id": "Organisation propriétaire : l'isolation des données repose dessus (RLS).",
    "created_at": "Date et heure de création de la ligne.",
    "updated_at": "Date et heure de la dernière modification.",
    "created_by": "Identifiant de l'utilisateur qui a créé la ligne.",
    "updated_by": "Identifiant de l'utilisateur qui l'a modifiée en dernier.",
    "project_id": "Projet auquel la ligne se rattache (cloisonné par habilitation).",
    "valid_from": "Début de validité, inclus (intervalle semi-ouvert [valid_from, valid_to[).",
    "valid_to": "Fin de validité, EXCLUE ; vide si la ligne est ouverte.",
    "version": "Numéro de version : une configuration utilisée ne se modifie pas, on en crée une.",
    "status": "Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base).",
    "label": 'Libellé multilingue : objet JSON {"fr": …, "en": …}.',
    "sha256": "Empreinte SHA-256 du contenu : preuve d'intégrité.",
}


def _premiere_phrase(texte: str | None) -> str:
    if not texte:
        return ""
    bloc = re.split(r"\n\s*\n", texte.strip(), maxsplit=1)[0]
    return " ".join(bloc.split())


def _colonne(champ: dj.Field) -> dict:
    reference = None
    if champ.is_relation and champ.related_model is not None:
        cible = champ.related_model._meta
        reference = f"{cible.db_table}.{cible.pk.column}"
    return {
        "nom": champ.column,
        "type": champ.db_type(connection),
        "nullable": bool(champ.null),
        "cle_primaire": bool(champ.primary_key),
        "reference": reference,
        "description": champ.help_text or COLONNES_COMMUNES.get(champ.column, ""),
    }


def _contraintes(meta) -> list[dict]:
    sortie = []
    for c in meta.constraints:
        genre = {
            "CheckConstraint": "verification",
            "UniqueConstraint": "unicite",
            "ExclusionConstraint": "exclusion",
        }.get(type(c).__name__, type(c).__name__)
        sortie.append({"nom": c.name, "genre": genre})
    return sorted(sortie, key=lambda c: c["nom"])


def dictionnaire() -> dict:
    """Le dictionnaire complet, déterministe (tables et colonnes triées)."""
    tables = []
    for modele in apps.get_models():
        meta = modele._meta
        if meta.proxy or meta.abstract or not meta.managed:
            continue
        colonnes = [_colonne(c) for c in meta.concrete_fields]
        tables.append(
            {
                "table": meta.db_table,
                "modele": f"{meta.app_label}.{meta.object_name}",
                "description": _premiere_phrase(modele.__doc__)
                if modele.__doc__ and not modele.__doc__.startswith(modele.__name__ + "(")
                else "",
                "isole_par_organisation": any(c["nom"] == "org_id" for c in colonnes),
                "colonnes": colonnes,
                "contraintes": _contraintes(meta),
            }
        )
    tables.sort(key=lambda t: t["table"])
    return {"version": VERSION, "tables": tables}


def rendre_markdown(d: dict) -> str:
    lignes = [
        "# Dictionnaire de données",
        "",
        "Généré depuis les modèles (`python manage.py generer_dictionnaire`). Ne le modifiez pas",
        "à la main : un test échoue si ce fichier n'est plus celui que les modèles produisent.",
        "",
        f"{len(d['tables'])} tables. « Isolée » : la table porte `org_id` et sa politique de",
        "sécurité par ligne (RLS). Les contraintes nommées sont contrôlées par la base.",
        "",
        "## Index",
        "",
    ]
    lignes += [f"- [`{t['table']}`](#{t['table']}) — {t['modele']}" for t in d["tables"]]
    for t in d["tables"]:
        lignes += [
            "",
            f"## {t['table']}",
            "",
            f"Modèle `{t['modele']}`"
            + (" — isolée par organisation" if t["isole_par_organisation"] else "")
            + ".",
        ]
        if t["description"]:
            lignes += ["", t["description"]]
        lignes += [
            "",
            "| Colonne | Type | Null | Clé | Relation | Description |",
            "|---|---|---|---|---|---|",
        ]
        for c in t["colonnes"]:
            cle = "PK" if c["cle_primaire"] else ""
            lignes.append(
                f"| `{c['nom']}` | {c['type']} | {'oui' if c['nullable'] else 'non'} | {cle} | "
                f"{('`' + c['reference'] + '`') if c['reference'] else ''} | "
                f"{c['description'].replace('|', '\\|') or '—'} |"
            )
        if t["contraintes"]:
            lignes += [
                "",
                "Contraintes : "
                + ", ".join(f"`{c['nom']}` ({c['genre']})" for c in t["contraintes"]),
            ]
    return "\n".join(lignes) + "\n"
