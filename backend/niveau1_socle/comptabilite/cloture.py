"""Contrôles de la clôture mensuelle. Voir L3-T08 (partie a).

Chaque contrôle reçoit la période et retourne `None` s'il ne s'oppose à rien, sinon la raison du
refus. Ils sont enregistrés dans `exercices.services.VERIFICATIONS_DE_CLOTURE` au démarrage
(`apps.ComptabiliteConfig.ready`) : `cloturer_periode` les exécute tous et liste toutes les raisons.

Le troisième contrôle du plan, « rapprochements non soldés », est branché par le rapprochement
bancaire (L3-T07b, `niveau1_socle/rapprochement/cloture.py`).
"""

from django.db import connection

from core.i18n import Liste, msg

from .models import Ecriture

MAX_GROUPES_CITES = 5


def ecritures_non_comptabilisees(periode) -> str | None:
    """Une écriture brouillon ou validée dans la période : pas encore dans les comptes."""
    nombre = Ecriture.objects.filter(periode=periode, status__in=["draft", "validated"]).count()
    if nombre == 0:
        return None
    return msg(
        "cloture.ecritures_non_comptabilisees"
        if nombre > 1
        else "cloture.ecriture_non_comptabilisee",
        nombre=nombre,
        numero=periode.numero,
    )


def groupes_soldes_non_lettres(periode) -> str | None:
    """Des lignes de tiers qui se soldent entre elles mais ne sont pas lettrées.

    On regroupe, par compte, tiers et projet, les lignes comptabilisées non lettrées jusqu'à la fin
    de la période, toutes périodes confondues : une facture de mars et son règlement d'avril
    forment un groupe soldé dès avril. Une facture impayée (groupe non soldé) ne bloque jamais.
    """
    with connection.cursor() as cur:
        cur.execute(
            """SELECT c.code, t.code, count(*)
                 FROM comptabilite_ligneecriture l
                 JOIN comptabilite_ecriture e ON e.id = l.entry_id
                 JOIN referentiels_compte c ON c.id = l.account_id
                 JOIN referentiels_tiers t ON t.id = l.partner_id
                WHERE e.status IN ('posted', 'locked')
                  AND e.project_id = %s
                  AND e.accounting_date <= %s
                  AND l.reconciliation_id IS NULL
                GROUP BY c.code, t.code, l.account_id, l.partner_id
               HAVING count(*) >= 2 AND sum(l.debit - l.credit) = 0
                ORDER BY c.code, t.code""",
            [periode.exercice.project_id, periode.date_fin],
        )
        groupes = cur.fetchall()
    if not groupes:
        return None
    cites = Liste(
        [
            msg("cloture.groupe_cite", compte=compte, tiers=tiers, n=n)
            for compte, tiers, n in groupes[:MAX_GROUPES_CITES]
        ],
        ", ",
    )
    reste = len(groupes) - MAX_GROUPES_CITES
    if reste > 0:
        return msg("cloture.groupes_non_lettres_et_autres", cites=cites, reste=reste)
    return msg("cloture.groupes_non_lettres", cites=cites)


CONTROLES_DE_CLOTURE = (ecritures_non_comptabilisees, groupes_soldes_non_lettres)
