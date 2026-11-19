"""L'archive d'export complet d'une organisation. Voir L8-T03.

Contenu (un ZIP, UTF-8 partout) :
- `MANIFESTE.json` : chaque fichier avec son SHA-256, chaque table avec son nombre de lignes ;
- `LISEZMOI.txt` : comment lire et restaurer ;
- `schema/dictionnaire.json` : le schéma documenté (voir `core/dictionnaire.py`) ;
- `donnees/<table>.csv` : une table par fichier, avec en-têtes ;
- `restauration.sql` : un dépôt SQL restaurable (`COPY … FROM stdin`) ;
- `parametrage/parametrage.json` : plans, axes, journaux, schémas, mappings, modèles d'états ;
- `registre/exigences.json` et `registre/guide_<projet>.pdf` ;
- `rapports/<id>/…` : chaque rapport publié scellé, avec ses fichiers ;
- `journal_audit.csv` : le journal d'audit ;
- `fichiers/…` : les fichiers stockés (documents de référence, pièces justificatives).

Deux choix de sécurité : les MOTS DE PASSE ne sortent pas (colonne remplacée par un marqueur
inutilisable : les comptes se réinitialisent à la restauration) ; les JETONS d'accès auditeur ne
sortent pas (la table n'est pas exportée). Aucun filtre d'organisation n'est écrit à la main,
sauf pour la table des utilisateurs, la seule qui n'est pas isolée par RLS.
"""

import datetime
import hashlib
import io
import json
import zipfile
from decimal import Decimal

from django.db import connection

from core.dictionnaire import dictionnaire
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from niveau1_socle.comptabilite.models import Journal, PieceJustificative, SchemaEcriture
from niveau1_socle.organisations.models import Projet
from niveau1_socle.referentiels.models import Compte, PlanDimension, ValeurDimension
from niveau3_config import stockage
from niveau3_config.models import DocumentReference, Exigence
from niveau3_config.services.guide import construire_guide, rendre_pdf
from niveau4_reporting.mapping.models import RegleMapping, TableMapping
from niveau4_reporting.publication.models import FichierRapport, RapportPublie

VERSION_ARCHIVE = 1
DATE_FIXE_ZIP = (2020, 1, 1, 0, 0, 0)
# Les jetons d'accès auditeur ne sortent pas ; une demande d'export n'est pas une donnée à restaurer
# (son fichier et son lien n'ont de sens que dans l'instance qui les a produits).
TABLES_EXCLUES = frozenset({"publication_accesauditeur", "reversibilite_exportorganisation"})
TABLE_SANS_RLS = "organisations_utilisateur"  # login : lue avant de connaître l'organisation
MARQUEUR_MOT_DE_PASSE = "!"  # un hash Django inutilisable : le compte doit être réinitialisé


def _q(identifiant: str) -> str:
    return '"' + identifiant.replace('"', '""') + '"'


def tables_exportees(cur) -> list[str]:
    cur.execute(
        """
        SELECT c.table_name FROM information_schema.columns c
          JOIN information_schema.tables t
            ON t.table_schema = c.table_schema AND t.table_name = c.table_name
         WHERE c.table_schema = current_schema() AND t.table_type = 'BASE TABLE'
           AND c.column_name = 'org_id'
        """
    )
    noms = {r[0] for r in cur.fetchall()} | {"organisations_organisation"}
    return sorted(noms - TABLES_EXCLUES)


def _colonnes(cur, table: str) -> list[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position",
        [table],
    )
    return [r[0] for r in cur.fetchall()]


def _requete(table: str, colonnes: list[str], org_id) -> tuple[str, list]:
    """La sélection d'une table. La RLS borne l'organisation ; seule la table des utilisateurs, qui
    n'est pas isolée, reçoit un filtre explicite, et n'exporte jamais les mots de passe."""
    champs = ", ".join(
        f"'{MARQUEUR_MOT_DE_PASSE}'::text AS {_q(c)}"
        if (table == TABLE_SANS_RLS and c == "password")
        else _q(c)
        for c in colonnes
    )
    sql = f"SELECT {champs} FROM {_q(table)}"  # noqa: S608  (noms issus du catalogue)
    params: list = []
    if table == TABLE_SANS_RLS:
        sql += " WHERE org_id = %s"
        params.append(str(org_id))
    return sql + " ORDER BY 1", params


def _copier(cur, table: str, colonnes: list[str], org_id, format_: str) -> bytes:
    sql, params = _requete(table, colonnes, org_id)
    options = "(FORMAT csv, HEADER true, ENCODING 'UTF8')" if format_ == "csv" else ""
    tampon = io.BytesIO()
    with cur.cursor.copy(f"COPY ({sql}) TO STDOUT {options}".strip(), params) as copie:
        for morceau in copie:
            tampon.write(bytes(morceau))
    return tampon.getvalue()


def _json(objet) -> bytes:
    def defaut(v):
        if isinstance(v, bytes | memoryview):
            return bytes(v).hex()
        if isinstance(v, datetime.date | datetime.datetime):
            return v.isoformat()
        return str(v) if isinstance(v, Decimal) else str(v)

    return json.dumps(objet, ensure_ascii=False, indent=2, sort_keys=True, default=defaut).encode()


def _objet(instance) -> dict:
    """Un enregistrement lisible : colonnes, sans l'organisation ni les traces techniques."""
    ignores = {"org_id", "created_at", "updated_at", "created_by", "updated_by"}
    sortie = {}
    for champ in instance._meta.concrete_fields:
        if champ.attname in ignores:
            continue
        valeur = getattr(instance, champ.attname)
        sortie[champ.attname] = (
            bytes(valeur).hex() if isinstance(valeur, memoryview | bytes) else valeur
        )
    return sortie


def _parametrage() -> dict:
    ordre = {
        "plan_comptable": Compte.objects.order_by("code"),
        "axes": PlanDimension.objects.order_by("kind", "slot"),
        "valeurs_d_axes": ValeurDimension.objects.order_by("plan_id", "code"),
        "journaux": Journal.objects.order_by("code"),
        "schemas_d_ecriture": SchemaEcriture.objects.order_by("id"),
        "mappings": TableMapping.objects.order_by("code", "version"),
        "regles_de_mapping": RegleMapping.objects.order_by("table_id", "priority"),
    }
    sortie = {nom: [_objet(i) for i in qs] for nom, qs in ordre.items()}
    modeles = {}
    for r in RapportPublie.objects.order_by("published_at"):
        modeles.setdefault(f"{r.template_code}@{r.template_version}", r.modele)
    sortie["modeles_d_etats"] = modeles  # tels que les rapports publiés les ont utilisés
    return sortie


def construire_archive(org_id, *, utilisateur_nom: str = "") -> tuple[bytes, dict]:
    """Construit l'archive. À appeler avec le périmètre de l'organisation posé (RLS)."""
    fichiers: dict[str, bytes] = {}
    lignes_par_table: dict[str, int] = {}
    sql = [
        "-- Dépôt SQL restaurable de l'organisation " + str(org_id),
        "-- Restauration : psql -f restauration.sql, en rôle propriétaire, sur une instance",
        "-- migrée et vierge pour cette organisation. Les déclencheurs sont suspendus pendant la",
        "-- copie (session_replication_role = replica) : numéros, statuts et empreintes sont",
        "-- repris tels quels, rien n'est recalculé.",
        "SET session_replication_role = replica;",
    ]
    with connection.cursor() as cur:
        cur.execute("SELECT current_setting('app.org_id', true)")
        if cur.fetchone()[0] != str(org_id):
            # Sans cela, la RLS rendrait des tables vides (ou celles d'une autre organisation) sous
            # un manifeste qui annonce `org_id` : une sauvegarde vide présentée comme complète.
            raise ErreurMetier(
                CodeErreur.ACCES_ORGANISATION_REFUSE, msg("export.perimetre_incoherent")
            )
        tables = tables_exportees(cur)
        for table in tables:
            colonnes = _colonnes(cur, table)
            sql_lignes, params = _requete(table, colonnes, org_id)
            cur.execute(f"SELECT count(*) FROM ({sql_lignes}) t", params)  # noqa: S608
            lignes_par_table[table] = cur.fetchone()[0]
            fichiers[f"donnees/{table}.csv"] = _copier(cur, table, colonnes, org_id, "csv")
            texte = _copier(cur, table, colonnes, org_id, "text").decode("utf-8")
            liste = ", ".join(_q(c) for c in colonnes)
            sql.append(f"COPY {_q(table)} ({liste}) FROM stdin;")
            sql.append(texte.rstrip("\n") if texte else "")
            sql.append("\\.")
        fichiers["journal_audit.csv"] = fichiers["donnees/core_auditlog.csv"]
    fichiers["restauration.sql"] = ("\n".join(sql) + "\n").encode("utf-8")
    d = dictionnaire()
    d["tables"] = [t for t in d["tables"] if t["table"] in lignes_par_table]
    fichiers["schema/dictionnaire.json"] = _json(d)
    fichiers["parametrage/parametrage.json"] = _json(_parametrage())

    exigences = [
        {
            **_objet(e),
            "document": {"titre": e.document.title, "version": e.document.version},
        }
        for e in Exigence.objects.select_related("document").order_by("code", "version")
    ]
    documents = [_objet(doc) for doc in DocumentReference.objects.order_by("title", "version")]
    fichiers["registre/exigences.json"] = _json({"exigences": exigences, "documents": documents})
    notes: list[str] = []
    aujourdhui = datetime.date.today()
    for projet in Projet.objects.order_by("code"):
        try:
            guide = construire_guide(projet.id, aujourdhui)
            fichiers[f"registre/guide_{projet.code}.pdf"] = rendre_pdf(guide, "fr")
        except (LookupError, ValueError) as erreur:
            notes.append(f"guide du projet {projet.code} non produit : {erreur}")

    for r in RapportPublie.objects.order_by("published_at"):
        racine = f"rapports/{r.id}"
        fichiers[f"{racine}/rapport.json"] = _json({**_objet(r), "scelle": bytes(r.seal).hex()})
        for f in FichierRapport.objects.filter(rapport=r).order_by("nom"):
            fichiers[f"{racine}/{f.nom}"] = bytes(f.contenu)

    references = {d.file_ref for d in DocumentReference.objects.all()} | {
        p.file_ref for p in PieceJustificative.objects.all()
    }
    for ref in sorted(references):
        try:
            fichiers[f"fichiers/{ref.removeprefix(stockage.SCHEMA)}"] = stockage.lire(ref)
        except stockage.FichierIntrouvable:
            notes.append(f"fichier stocké introuvable : {ref}")

    fichiers["LISEZMOI.txt"] = _lisez_moi(org_id, len(tables), notes).encode("utf-8")
    manifeste = {
        "version_archive": VERSION_ARCHIVE,
        "organisation": str(org_id),
        "produit_le": datetime.datetime.now(datetime.UTC).isoformat(),
        "produit_par": utilisateur_nom,
        "tables": lignes_par_table,
        "fichiers": {nom: hashlib.sha256(contenu).hexdigest() for nom, contenu in fichiers.items()},
        "notes": notes,
    }
    fichiers["MANIFESTE.json"] = _json(manifeste)
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        for nom in sorted(fichiers):
            info = zipfile.ZipInfo(nom, date_time=DATE_FIXE_ZIP)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, fichiers[nom])
    return tampon.getvalue(), manifeste


def _lisez_moi(org_id, nb_tables: int, notes: list[str]) -> str:
    lignes = [
        f"Export complet de l'organisation {org_id}",
        f"{nb_tables} tables. Tous les fichiers sont en UTF-8.",
        "",
        "MANIFESTE.json   chaque fichier de l'archive avec son SHA-256 : vérifiez-le d'abord.",
        "schema/          le dictionnaire de données (tables, colonnes, types, relations).",
        "donnees/         une table par fichier CSV, avec en-têtes.",
        "restauration.sql dépôt SQL restaurable (COPY), à jouer en rôle propriétaire.",
        "parametrage/     plans, axes, journaux, schémas d'écriture, mappings, modèles d'états.",
        "registre/        registre des exigences et guide de configuration par projet.",
        "rapports/        les rapports publiés scellés, avec leurs fichiers.",
        "journal_audit.csv  le journal d'audit.",
        "fichiers/        les fichiers stockés (documents, pièces justificatives).",
        "",
        "Mots de passe : ils ne sont PAS exportés ; les comptes se réinitialisent.",
        "Jetons d'accès auditeur : ils ne sont PAS exportés.",
    ]
    if notes:
        lignes += ["", "Notes :", *[f"- {n}" for n in notes]]
    return "\n".join(lignes) + "\n"


def lire_manifeste(archive: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        return json.loads(z.read("MANIFESTE.json"))
