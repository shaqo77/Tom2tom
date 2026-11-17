"""Les indicateurs de conformité du tableau de bord : échéances, rapports, anomalies. Voir L10-T02.

Des comptes par projet (jamais de montants, donc pas de devise). Le total d'un compte est la somme
exacte de ses détails par projet ; le taux d'acceptation consolidé est calculé sur les SOMMES
(acceptés ÷ décidés de tous les projets), jamais comme une moyenne de taux.

Les filtres d'accord ne s'appliquent pas ici : une échéance, un envoi ou un contrôle se rattache au
projet, pas à un accord.
"""

import datetime
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from niveau3_config.models import Echeance, StatutEcheance
from niveau3_config.services.calendrier import alertes_du_jour
from niveau4_reporting.controles.models import EvaluationControle, Resultat
from niveau4_reporting.controles.services import controles_en_attente
from niveau4_reporting.publication.models import ResultatSoumission, SoumissionBailleur
from niveau4_reporting.publication.revue import taux_acceptation_premier_envoi

CHAMPS = (
    "echeances_a_remettre",
    "echeances_imminentes",
    "echeances_en_retard",
    "echeances_en_escalade",
    "rapports_en_attente",
    "anomalies_ouvertes",
    "premiers_envois_acceptes",
    "premiers_envois_decides",
)


@dataclass
class ConformiteProjet:
    """Les comptes d'un projet. `en_retard` ne contient pas `en_escalade` (niveaux exclusifs)."""

    echeances_a_remettre: int = 0
    echeances_imminentes: int = 0
    echeances_en_retard: int = 0
    echeances_en_escalade: int = 0
    # Rapports envoyés au bailleur dont l'issue n'est pas encore connue.
    rapports_en_attente: int = 0
    # Contrôles qui bloquent ou attendent une décision humaine, tous objets confondus.
    anomalies_ouvertes: int = 0
    premiers_envois_acceptes: int = 0
    premiers_envois_decides: int = 0


@dataclass
class Conformite:
    par_projet: dict[uuid.UUID, ConformiteProjet] = field(default_factory=dict)

    def total(self, champ: str) -> int:
        """La somme exacte du champ sur les projets du périmètre."""
        return sum(getattr(c, champ) for c in self.par_projet.values())

    @property
    def taux_acceptation(self) -> Decimal | None:
        """Acceptés ÷ décidés au premier envoi, sur les sommes ; None sans issue connue."""
        decides = self.total("premiers_envois_decides")
        if not decides:
            return None
        return Decimal(self.total("premiers_envois_acceptes")) / Decimal(decides)


def conformite_du_projet(
    utilisateur,
    project_id,
    jour: datetime.date,
    du: datetime.date | None = None,
    au: datetime.date | None = None,
) -> ConformiteProjet:
    c = ConformiteProjet()
    c.echeances_a_remettre = Echeance.objects.filter(
        project_id=project_id, statut=StatutEcheance.A_REMETTRE
    ).count()
    for _, niveau in alertes_du_jour(project_id=project_id, jour=jour):
        champ = {
            "imminente": "echeances_imminentes",
            "en_retard": "echeances_en_retard",
            "escalade": "echeances_en_escalade",
        }[niveau]
        setattr(c, champ, getattr(c, champ) + 1)
    c.rapports_en_attente = SoumissionBailleur.objects.filter(
        project_id=project_id, resultat=ResultatSoumission.EN_ATTENTE
    ).count()
    # Un objet dont aucune évaluation n'est bloquante ni « à vérifier » ne peut rien avoir en
    # attente : on ne l'examine pas (sinon une requête par objet évalué, à chaque affichage).
    objets = (
        EvaluationControle.objects.filter(
            project_id=project_id, resultat__in=(Resultat.BLOQUANT, Resultat.A_VERIFIER)
        )
        .values_list("objet_type", "objet_id")
        .distinct()
    )
    c.anomalies_ouvertes = sum(
        len(controles_en_attente(project_id, objet_type, objet_id, jour))
        for objet_type, objet_id in objets
    )
    indicateur = taux_acceptation_premier_envoi(
        utilisateur=utilisateur,
        project_id=project_id,
        du=du or datetime.date.min,
        au=au or jour,
    )
    c.premiers_envois_acceptes = indicateur.acceptes
    c.premiers_envois_decides = indicateur.decides
    return c
