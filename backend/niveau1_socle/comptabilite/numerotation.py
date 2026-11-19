"""Contrôle de la numérotation d'un journal. Voir L3-T04.

L'attribution se fait en base (déclencheur de comptabilisation). Ce module ne fait que
VÉRIFIER : un auditeur doit pouvoir demander « y a-t-il un trou ? » et obtenir la réponse.
"""

from django.db import connection


def trous_de_numerotation(journal, exercice) -> list[int]:
    """Rangs manquants dans la suite des numéros d'un journal sur un exercice.

    Une suite saine va de 1 au dernier numéro attribué sans interruption. On compare aussi au
    compteur : un compteur en avance sur les numéros signale un numéro attribué puis perdu.
    """
    with connection.cursor() as cur:
        cur.execute(
            """SELECT right(e.number, 6)::int
                 FROM comptabilite_ecriture e
                WHERE e.journal_id = %s AND e.exercice_id = %s AND e.number IS NOT NULL""",
            [journal.pk, exercice.pk],
        )
        presents = {rang for (rang,) in cur.fetchall()}
        cur.execute(
            "SELECT dernier FROM comptabilite_compteur WHERE journal_id = %s AND exercice_id = %s",
            [journal.pk, exercice.pk],
        )
        compteur = cur.fetchone()
    plus_haut = max(presents | {compteur[0] if compteur else 0})
    return [rang for rang in range(1, plus_haut + 1) if rang not in presents]
