"""Restaurer une archive d'export dans une instance migrée et vierge pour cette organisation.

Voir L8-T03. La restauration reprend les lignes TELLES QUELLES (numéros, statuts, empreintes,
scellés) : les déclencheurs sont suspendus pendant la copie (`session_replication_role = replica`,
réservé au rôle propriétaire). Elle vérifie d'abord le manifeste (le SHA-256 de chaque fichier),
refuse une instance où l'organisation existe déjà, copie tout dans UNE transaction, puis compare le
nombre de lignes restaurées à celui du manifeste.
"""

import hashlib
import io
import json
import re
import zipfile

from core.i18n import msg
from niveau3_config import stockage

from .archive import TABLES_EXCLUES, tables_exportees


class ArchiveCorrompue(ValueError):
    """Un fichier de l'archive ne correspond pas à son empreinte du manifeste."""


class InstanceNonVierge(ValueError):
    """L'organisation existe déjà dans l'instance cible."""


class RestaurationIncomplete(ValueError):
    """Le nombre de lignes restaurées ne correspond pas au manifeste."""


_COPY = re.compile(r'^COPY "([^"]+)" \((.+)\) FROM stdin;$')


def _blocs(sql: str):
    """`(table, instruction COPY, texte des lignes)` pour chaque bloc COPY du dépôt SQL."""
    lignes = sql.split("\n")
    i = 0
    while i < len(lignes):
        trouve = _COPY.match(lignes[i])
        if trouve:
            debut = i + 1
            i = debut
            while lignes[i] != "\\.":
                i += 1
            corps = "\n".join(lignes[debut:i])
            instruction = lignes[debut - 1].removesuffix("FROM stdin;") + "FROM STDIN"
            yield trouve.group(1), instruction, (corps + "\n") if corps else ""
        i += 1


def verifier_archive(archive: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        manifeste = json.loads(z.read("MANIFESTE.json"))
        for nom, attendu in manifeste["fichiers"].items():
            if hashlib.sha256(z.read(nom)).hexdigest() != attendu:
                raise ArchiveCorrompue(msg("restauration.fichier_altere", nom=nom))
    return manifeste


def _remettre_les_sequences(cur, tables) -> None:
    """Après une copie avec identifiants explicites, la séquence d'une clé série ne sait rien des
    lignes copiées : sans ce rattrapage, la prochaine insertion reprendrait un identifiant déjà
    pris (le journal d'audit, par exemple, ne pourrait plus rien enregistrer)."""
    for table in tables:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s "
            "AND (column_default LIKE 'nextval%%' OR is_identity = 'YES')",
            [table],
        )
        for (colonne,) in cur.fetchall():
            cur.execute("SELECT pg_get_serial_sequence(%s, %s)", [f'"{table}"', colonne])
            sequence = cur.fetchone()[0]
            cur.execute(f'SELECT max("{colonne}") FROM "{table}"')  # noqa: S608
            maximum = cur.fetchone()[0]
            if sequence is None or maximum is None:
                continue
            cur.execute(f"SELECT last_value, is_called FROM {sequence}")  # noqa: S608
            dernier, appelee = cur.fetchone()
            cur.execute(
                "SELECT setval(%s, %s, true)", [sequence, max(maximum, dernier if appelee else 0)]
            )


def restaurer_archive(archive: bytes, connexion, *, sha256_attendu: str | None = None) -> dict:
    """Restaure l'archive via `connexion` (psycopg, propriétaire) ; rend les lignes par table.

    Le manifeste est DANS l'archive : il garantit qu'elle n'est pas abîmée, pas qu'elle est celle
    qu'on a exportée. Deux défenses s'y ajoutent. `sha256_attendu` (l'empreinte enregistrée à
    l'export, transmise hors de l'archive) l'authentifie. Et la restauration n'admet que les tables
    du manifeste, vérifie que chaque table n'a gagné QUE les lignes de l'organisation annoncée, et
    refuse tout compte privilégié : une archive forgée avec un manifeste recalculé ne passe pas.
    """
    if sha256_attendu is not None and hashlib.sha256(archive).hexdigest() != sha256_attendu:
        raise ArchiveCorrompue(msg("restauration.empreinte_attendue"))
    manifeste = verifier_archive(archive)
    org_id = manifeste["organisation"]
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        sql = z.read("restauration.sql").decode("utf-8")
        fichiers = {n: z.read(n) for n in z.namelist() if n.startswith("fichiers/")}
    blocs = list(_blocs(sql))
    connues = set(manifeste["tables"])
    for table, _instruction, _corps in blocs:
        if table not in connues or table in TABLES_EXCLUES:
            raise ArchiveCorrompue(msg("restauration.table_inattendue", table=table))
    with connexion.transaction(), connexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM organisations_organisation WHERE id = %s", [org_id])
        if cur.fetchone()[0]:
            raise InstanceNonVierge(msg("restauration.instance_non_vierge", organisation=org_id))
        autorisees = set(tables_exportees(cur))
        inconnues = sorted(connues - autorisees)
        if inconnues:
            raise ArchiveCorrompue(msg("restauration.table_inattendue", table=inconnues[0]))
        avant = {}
        for table in connues:
            cur.execute(f'SELECT count(*) FROM "{table}"')  # noqa: S608
            avant[table] = cur.fetchone()[0]
        cur.execute("SET LOCAL session_replication_role = replica")
        for _table, instruction, corps in blocs:
            with cur.copy(instruction) as copie:
                copie.write(corps.encode("utf-8"))
        restaurees = {}
        for table, attendu in manifeste["tables"].items():
            cur.execute(f'SELECT count(*) FROM "{table}"' + _filtre(table), _params(table, org_id))  # noqa: S608
            restaurees[table] = cur.fetchone()[0]
            if restaurees[table] != attendu:
                raise RestaurationIncomplete(
                    msg(
                        "restauration.lignes_differentes",
                        table=table,
                        attendu=attendu,
                        obtenu=restaurees[table],
                    )
                )
            cur.execute(f'SELECT count(*) FROM "{table}"')  # noqa: S608
            if cur.fetchone()[0] - avant[table] != attendu:
                raise ArchiveCorrompue(msg("restauration.lignes_etrangeres", table=table))
        cur.execute(
            "SELECT count(*) FROM organisations_utilisateur "
            "WHERE org_id = %s AND (is_superuser OR is_staff)",
            [org_id],
        )
        if cur.fetchone()[0]:
            raise ArchiveCorrompue(msg("restauration.compte_privilegie"))
        _remettre_les_sequences(cur, connues)
    for nom, contenu in fichiers.items():
        ref = stockage.SCHEMA + nom.removeprefix("fichiers/")
        if stockage.deposer(org_id, contenu) != ref:
            raise ArchiveCorrompue(msg("restauration.fichier_altere", nom=nom))
    return restaurees


def _filtre(table: str) -> str:
    if table == "organisations_organisation":
        return " WHERE id = %s"
    return " WHERE org_id = %s"


def _params(table: str, org_id) -> list:
    return [org_id]
