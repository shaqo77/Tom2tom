"""La consolidation dans une devise de référence : méthode, date et taux affichés. Voir L10-T02.

Par défaut un tableau de bord ventile par devise. Consolider est un choix explicite : on donne la
devise de référence (la monnaie de tenue de l'ORGANISATION, dans laquelle les taux du référentiel
sont exprimés) et le type de taux. Chaque montant (projet, devise) est converti au taux le plus
récent à la date, ARRONDI à la devise de référence, puis additionné : le total consolidé est donc
exactement la somme des consolidations par projet. Sans taux disponible, l'indicateur n'est PAS
consolidé et la raison est dite.
"""

import datetime
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from core.i18n import msg
from niveau1_socle.referentiels.models import Devise, Taux

ZERO = Decimal("0")


@dataclass
class Consolidation:
    devise_reference: str
    jour: datetime.date
    type_taux: str
    montant: Decimal | None = None  # None : non consolidé (voir `raison`)
    par_projet: dict = field(default_factory=dict)  # project_id -> montant dans la devise de réf.
    taux: dict = field(default_factory=dict)  # devise -> (taux, date du taux)
    raison: str | None = None

    @property
    def methode(self) -> str:
        return str(
            msg(
                "tableau_de_bord.methode_consolidation",
                type_taux=self.type_taux,
                jour=self.jour.isoformat(),
                reference=self.devise_reference,
            )
        )


def _taux_le_plus_recent(devise: str, jour: datetime.date, type_taux: str):
    ligne = (
        Taux.objects.filter(devise_id=devise, type_taux=type_taux, date__lte=jour)
        .order_by("-date")
        .first()
    )
    return (ligne.taux, ligne.date) if ligne else None


def consolider(
    indicateur, *, devise_reference: str, jour: datetime.date, type_taux: str = "officiel"
):
    """Consolide un indicateur dans `devise_reference`. Jamais de taux inventé : un seul taux
    manquant empêche toute la consolidation, et le dit."""
    resultat = Consolidation(devise_reference, jour, type_taux)
    reference = Devise.objects.filter(pk=devise_reference).first()
    if reference is None:
        resultat.raison = str(
            msg("tableau_de_bord.devise_reference_inconnue", devise=devise_reference)
        )
        return resultat
    unite = Decimal(1).scaleb(-reference.decimales)
    devises = {d for montants in indicateur.par_projet.values() for d in montants}
    manquantes = []
    for devise in sorted(devises - {devise_reference}):
        trouve = _taux_le_plus_recent(devise, jour, type_taux)
        if trouve is None:
            manquantes.append(devise)
        else:
            resultat.taux[devise] = trouve
    if manquantes:
        resultat.raison = str(
            msg(
                "tableau_de_bord.taux_manquant",
                devises=", ".join(manquantes),
                type_taux=type_taux,
                jour=jour.isoformat(),
            )
        )
        resultat.taux = {}
        return resultat
    for projet, montants in indicateur.par_projet.items():
        convertis = (
            montant if devise == devise_reference else (montant * resultat.taux[devise][0])
            for devise, montant in montants.items()
        )
        resultat.par_projet[projet] = sum(
            (c.quantize(unite, rounding=ROUND_HALF_UP) for c in convertis), ZERO
        )
    resultat.montant = sum(resultat.par_projet.values(), ZERO)
    return resultat
