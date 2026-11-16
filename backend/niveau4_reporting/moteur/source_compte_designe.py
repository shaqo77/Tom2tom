"""La source « compte_designe » : l'état de reconstitution du compte désigné. Voir L9-T05.

Paramètres de l'état : `project_id`, `compte_designe` (code du compte bancaire), `date_debut` et
`date_fin` (ISO). Les éléments sont les lignes de `etat_reconstitution`, en montants seulement.
"""

import datetime
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from core.i18n import msg
from niveau1_socle.financements.models import CompteBancaire
from niveau1_socle.tresorerie.services import calculer_reconstitution

from .compilateur import ModeleEtatInvalide
from .sources_externes import SourceIncomplete, enregistrer

ELEMENTS = {
    "ouverture": lambda e: e.ouverture,
    "avances_recues": lambda e: e.total_avances,
    "autres_encaissements": lambda e: e.autres_encaissements,
    "decaissements": lambda e: e.decaissements,
    "cloture_releve": lambda e: e.cloture_releve,
    "solde_comptable": lambda e: e.solde_comptable,
    "ecart_releve": lambda e: e.ecart_releve,
    "ecart_comptable": lambda e: e.ecart_comptable,
    "non_justifie_releve": lambda e: e.non_justifie_releve,
    "non_justifie_comptable": lambda e: e.non_justifie_comptable,
}


def _date(parametres: Mapping[str, Any], cle: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(str(parametres[cle]))
    except (KeyError, ValueError) as e:
        raise ModeleEtatInvalide(msg("compilateur.parametre_source_invalide", nom=cle)) from e


def lire(element: str, parametres: Mapping[str, Any]) -> Decimal:
    code = parametres.get("compte_designe")
    if not isinstance(code, str) or not code:
        raise ModeleEtatInvalide(msg("compilateur.parametre_source_invalide", nom="compte_designe"))
    debut, fin = _date(parametres, "date_debut"), _date(parametres, "date_fin")
    compte = CompteBancaire.objects.filter(project_id=parametres["project_id"], code=code).first()
    if compte is None or compte.type != "designe":
        raise ModeleEtatInvalide(msg("compilateur.compte_designe_introuvable", code=code[:40]))
    etat = calculer_reconstitution(compte, debut, fin)
    if not etat.complet:
        raise SourceIncomplete(msg("compilateur.releve_incomplet", manques=", ".join(etat.manques)))
    return ELEMENTS[element](etat)


enregistrer("compte_designe", set(ELEMENTS), lire)
