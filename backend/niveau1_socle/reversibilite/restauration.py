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


def restaurer_archive(archive: bytes, connexion) -> dict:
    """Restaure l'archive via `connexion` (psycopg, propriétaire) ; rend les lignes par table."""
    manifeste = verifier_archive(archive)
    org_id = manifeste["organisation"]
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        sql = z.read("restauration.sql").decode("utf-8")
        fichiers = {n: z.read(n) for n in z.namelist() if n.startswith("fichiers/")}
    with connexion.transaction(), connexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM organisations_organisation WHERE id = %s", [org_id])
        if cur.fetchone()[0]:
            raise InstanceNonVierge(msg("restauration.instance_non_vierge", organisation=org_id))
        cur.execute("SET LOCAL session_replication_role = replica")
        for _table, instruction, corps in _blocs(sql):
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
