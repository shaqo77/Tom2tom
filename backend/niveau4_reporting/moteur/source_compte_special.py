"""La source « compte_special » : la situation du compte spécial de la BAD. Voir L11-D4.

Paramètres de l'état : `project_id`, `compte_special` (code du compte bancaire de type spécial),
`date_fin` (ISO, la date du relevé) et, facultatif, `demande` (numéro de la demande en cours : sa
justification forme la ligne 4 du modèle ; sans elle, tout ce qui est justifié forme la ligne 5).
Les éléments sont les lignes de l'annexe 9 du manuel des décaissements, en montants seulement.
"""

import datetime
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from core.i18n import msg
from niveau1_socle.financements.models import CompteBancaire
from niveau1_socle.tresorerie.compte_special import calculer_situation

from .compilateur import ModeleEtatInvalide
from .sources_externes import SourceIncomplete, enregistrer

ELEMENTS = {
    "avances_versees": lambda s: s.total_avances,
    "solde_cloture": lambda s: s.solde_cloture,
    "justifie_cette_demande": lambda s: s.justifie_cette_demande,
    "justifie_precedemment": lambda s: s.justifie_precedemment,
}


def lire(element: str, parametres: Mapping[str, Any]) -> Decimal:
    code = parametres.get("compte_special")
    if not isinstance(code, str) or not code:
        raise ModeleEtatInvalide(msg("compilateur.parametre_source_invalide", nom="compte_special"))
    try:
        date = datetime.date.fromisoformat(str(parametres["date_fin"]))
    except (KeyError, ValueError) as e:
        raise ModeleEtatInvalide(
            msg("compilateur.parametre_source_invalide", nom="date_fin")
        ) from e
    demande = parametres.get("demande")
    if demande is not None and not isinstance(demande, str):
        raise ModeleEtatInvalide(msg("compilateur.parametre_source_invalide", nom="demande"))
    compte = CompteBancaire.objects.filter(project_id=parametres["project_id"], code=code).first()
    if compte is None or compte.type != "special":
        raise ModeleEtatInvalide(msg("compilateur.compte_special_introuvable", code=code[:40]))
    situation = calculer_situation(compte, date, demande)
    if not situation.complet:
        raise SourceIncomplete(
            msg("compilateur.releve_incomplet", manques=", ".join(situation.manques))
        )
    return ELEMENTS[element](situation)


enregistrer("compte_special", set(ELEMENTS), lire)
