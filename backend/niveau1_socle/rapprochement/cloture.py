"""Contrôle de clôture : les mouvements du relevé non rapprochés. Voir L3-T07 (b) et L3-T08.

Un mouvement du relevé dont aucune écriture ne rend compte, à la fin de la période, est une
opération bancaire que la comptabilité ignore : on ne clôt pas dessus. L'inverse (une écriture pas
encore passée en banque, un chèque en circulation) est normal et ne bloque jamais ; il figure dans
l'état de rapprochement.
"""

from django.db import connection

from core.i18n import Liste, msg

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
    cites = Liste(
        [msg("cloture.compte_cite", code=code, n=n) for code, n in comptes[:MAX_COMPTES_CITES]],
        ", ",
    )
    reste = len(comptes) - MAX_COMPTES_CITES
    if reste > 0:
        return msg("cloture.mouvements_non_rapproches_et_autres", cites=cites, reste=reste)
    return msg("cloture.mouvements_non_rapproches", cites=cites)


CONTROLES_DE_CLOTURE = (mouvements_non_rapproches,)
