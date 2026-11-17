"""Le tableau de bord multi-projets. Voir L10-T02.

Une LECTURE : aucun modèle, aucune écriture. Il ne calcule rien que les services des lots
précédents ne sachent déjà (soldes budgétaires, disponibilités, avances, engagements) : il les
rassemble par projet, dans le périmètre des projets que l'utilisateur peut consulter.

Règles : **jamais deux devises dans un même chiffre sans le dire** (chaque montant est ventilé par
devise) ; une consolidation dans une devise de référence affiche sa méthode, sa date et les taux
utilisés, et refuse de répondre sans taux ; le total d'un indicateur est TOUJOURS la somme de ses
détails par projet.
"""

from .conformite import Conformite, ConformiteProjet
from .detail import EcritureRef, LigneDetail, detail_indicateur, ecritures_du_detail
from .devises import Consolidation, consolider
from .filtres import Filtres, perimetre
from .financier import Indicateur, TableauDeBord, tableau_de_bord

__all__ = [
    "Conformite",
    "ConformiteProjet",
    "Consolidation",
    "EcritureRef",
    "LigneDetail",
    "detail_indicateur",
    "ecritures_du_detail",
    "Filtres",
    "Indicateur",
    "TableauDeBord",
    "consolider",
    "perimetre",
    "tableau_de_bord",
]
