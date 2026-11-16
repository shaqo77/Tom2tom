"""Modèles d'états livrés avec le code. Voir L9-T05.

Un modèle d'état est un JSON lu par le moteur ; celui-ci est livré parce qu'il dépend d'une source
externe (le relevé bancaire) que le moteur ne connaît pas par lui-même.
"""


def modele_rapprochement_compte_designe(version: int = 1) -> dict:
    """Le rapprochement du compte désigné : ouverture + avances reçues + autres encaissements
    − décaissements = clôture calculée, comparée au relevé, puis au grand livre.

    Les deux ÉCARTS NON JUSTIFIÉS (R180 relevé, R210 grand livre) portent une assertion : tant
    qu'un écart n'est pas expliqué au centime (`justifier_ecart`), l'état ne se publie pas.
    Les écarts eux-mêmes (R170, R200) restent affichés, justifiés ou non.
    """
    externe = {"type": "external", "source": "compte_designe"}
    return {
        "code": "RCD",
        "version": version,
        "columns": [{"code": "PER", "period": "year_to_date"}],
        "rows": [
            {"code": "H100", "type": "heading"},
            {"code": "R110", "item": "ouverture", **externe},
            {"code": "R120", "item": "avances_recues", **externe},
            {"code": "R130", "item": "autres_encaissements", **externe},
            {"code": "R140", "item": "decaissements", **externe},
            {"code": "R150", "type": "computed", "formula": "R110 + R120 + R130 - R140"},
            {"code": "R160", "item": "cloture_releve", **externe},
            {"code": "R170", "type": "computed", "formula": "R160 - R150"},
            {"code": "R180", "item": "non_justifie_releve", "assert": "R180 == 0", **externe},
            {"code": "R190", "item": "solde_comptable", **externe},
            {"code": "R200", "item": "ecart_comptable", **externe},
            {"code": "R210", "item": "non_justifie_comptable", "assert": "R210 == 0", **externe},
        ],
    }
