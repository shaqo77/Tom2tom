"""Journal d'audit chaîné. Voir 04_PLAN_LOTS_L0_A_L4.md, L1-T03."""

import hashlib
import json

from django.db import connection


def _serialiser(valeur) -> str:
    return json.dumps(valeur, sort_keys=True, separators=(",", ":"), default=str)


def journaliser(
    *,
    org_id,
    actor_id,
    action,
    object_type,
    object_id=None,
    project_id=None,
    before=None,
    after=None,
    actor_ip=None,
) -> bytes:
    """Ajoute une entrée au journal et retourne son empreinte."""
    charge = _serialiser(
        {
            "org_id": str(org_id),
            "actor_id": str(actor_id) if actor_id else None,
            "action": action,
            "object_type": object_type,
            "object_id": str(object_id) if object_id else None,
            "project_id": str(project_id) if project_id else None,
            "before": before,
            "after": after,
        }
    ).encode()

    with connection.cursor() as cur:
        # Le chaînage impose une insertion strictement séquentielle par organisation.
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"audit:{org_id}"])
        cur.execute(
            "SELECT hash FROM core_auditlog WHERE org_id = %s ORDER BY id DESC LIMIT 1",
            [str(org_id)],
        )
        rangee = cur.fetchone()
        precedent = bytes(rangee[0]) if rangee else b""
        courant = hashlib.sha256(precedent + charge).digest()
        cur.execute(
            """INSERT INTO core_auditlog
               (org_id, occurred_at, actor_id, actor_ip, action, object_type,
                object_id, project_id, before, after, prev_hash, hash)
               VALUES (%s, now(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                org_id,
                actor_id,
                actor_ip,
                action,
                object_type,
                object_id,
                project_id,
                _serialiser(before) if before is not None else None,
                _serialiser(after) if after is not None else None,
                precedent,
                courant,
            ],
        )
    return courant


def verifier_chaine(org_id) -> int | None:
    """Relit la chaîne. Retourne l'id de la PREMIÈRE entrée altérée, ou None."""
    with connection.cursor() as cur:
        cur.execute(
            """SELECT id, actor_id, action, object_type, object_id, project_id,
                      before, after, prev_hash, hash
               FROM core_auditlog WHERE org_id = %s ORDER BY id""",
            [str(org_id)],
        )
        precedent = b""
        for (
            rid,
            actor_id,
            action,
            object_type,
            object_id,
            project_id,
            before,
            after,
            prev_hash,
            hash_,
        ) in cur.fetchall():
            charge = _serialiser(
                {
                    "org_id": str(org_id),
                    "actor_id": str(actor_id) if actor_id else None,
                    "action": action,
                    "object_type": object_type,
                    "object_id": str(object_id) if object_id else None,
                    "project_id": str(project_id) if project_id else None,
                    "before": json.loads(before) if before else None,
                    "after": json.loads(after) if after else None,
                }
            ).encode()
            attendu = hashlib.sha256(precedent + charge).digest()
            if bytes(prev_hash or b"") != precedent or bytes(hash_) != attendu:
                return rid
            precedent = bytes(hash_)
    return None
