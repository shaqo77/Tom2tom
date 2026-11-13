"""Contrôle de clôture : les mouvements du relevé non rapprochés. Voir L3-T07 (b) et L3-T08.

Un mouvement du relevé dont aucune écriture ne rend compte, à la fin de la période, est une
opération bancaire que la comptabilité ignore : on ne clôt pas dessus. L'inverse (une écriture pas
encore passée en banque, un chèque en circulation) est normal et ne bloque jamais ; il figure dans
l'état de rapprochement.
"""

from django.db import connection

MAX_COMPTES_CITES = 5


def mouvements_non_rapproches(periode) -> str | None:
    with connection.cursor() as cur:
        cur.execute(
            """SELECT c.code, count(*)
                 FROM rapprochement_mouvementreleve m
                 JOIN financements_comptebancaire c ON c.id = m.compte_id
                WHERE m.project_id = %s AND m.date_operation <= %s AND m.rapprochement_id IS NULL
                GROUP BY c.code ORDER BY c.code""",
            [periode.exercice.project_id, periode.date_fin],
        )
        comptes = cur.fetchall()
    if not comptes:
        return None
    cites = ", ".join(f"{code} ({n})" for code, n in comptes[:MAX_COMPTES_CITES])
    reste = len(comptes) - MAX_COMPTES_CITES
    suite = f" et {reste} autre(s)" if reste > 0 else ""
    return f"Mouvements de relevé non rapprochés : {cites}{suite}"


CONTROLES_DE_CLOTURE = (mouvements_non_rapproches,)
