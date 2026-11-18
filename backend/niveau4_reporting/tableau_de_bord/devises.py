"""La consolidation dans une devise de référence : méthode, date et taux affichés. Voir L10-T02.

Par défaut un tableau de bord ventile par devise. Consolider demande une devise de référence et un
type de taux. Ils viennent des RÉGLAGES de l'organisation et du projet (`parametres_devises`),
sauf si la personne en donne un explicitement : le paramètre explicite l'emporte. Rien n'est écrit
dans le code : sans réglage ni paramètre, l'indicateur n'est pas consolidé et la raison est dite.
Si les projets du périmètre règlent des références différentes, aucun total unique n'a de sens :
on les nomme et on laisse la personne trancher, on ne choisit pas pour elle.

Les taux du référentiel sont exprimés en monnaie de TENUE de l'organisation (unités de monnaie de
tenue par unité de devise). Convertir vers une référence qui n'est pas la monnaie de tenue passe
donc par un croisement : `montant × taux(devise) / taux(référence)`, la monnaie de tenue valant 1.

Chaque montant (projet, devise) est converti au taux le plus récent à la date, ARRONDI à la devise
de référence, puis additionné : le total consolidé est donc exactement la somme des consolidations
par projet. Sans taux disponible, l'indicateur n'est PAS consolidé et la raison est dite.
"""

import datetime
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from core.i18n import msg
from niveau1_socle.organisations.models import Organisation, Projet
from niveau1_socle.referentiels.models import Devise, Taux
from niveau1_socle.referentiels.parametres_devises import resoudre_parametres_devises

ZERO = Decimal("0")


@dataclass
class Consolidation:
    devise_reference: str | None
    jour: datetime.date
    type_taux: str | None
    montant: Decimal | None = None  # None : non consolidé (voir `raison`)
    par_projet: dict = field(default_factory=dict)  # project_id -> montant dans la devise de réf.
    taux: dict = field(default_factory=dict)  # devise -> (taux, date du taux)
    raison: str | None = None
    # champ -> "demande" (paramètre explicite) | "projet" | "organisation" (réglage)
    origine: dict = field(default_factory=dict)
    monnaie_tenue: str | None = None

    @property
    def methode(self) -> str:
        jour = self.jour.isoformat()
        if self.monnaie_tenue not in (None, self.devise_reference):
            return str(
                msg(
                    "tableau_de_bord.methode_consolidation_croisee",
                    type_taux=self.type_taux,
                    jour=jour,
                    reference=self.devise_reference,
                    tenue=self.monnaie_tenue,
                )
            )
        return str(
            msg(
                "tableau_de_bord.methode_consolidation",
                type_taux=self.type_taux,
                jour=jour,
                reference=self.devise_reference,
            )
        )


@dataclass
class ReferenceResolue:
    devise_reference: str | None
    type_taux: str | None
    origine: dict
    raison: str | None = None


def _resoudre_champ(projets, jour, champ, explicite, cle_non_parametre, cle_differents):
    """(valeur, origine, raison) pour `devise_reference` ou `type_taux`."""
    if explicite:
        return explicite, "demande", None
    cibles = list(projets) or [None]
    par_projet = {p: resoudre_parametres_devises(p, jour) for p in cibles}
    valeurs = {p: getattr(r, champ) for p, r in par_projet.items()}
    if any(v is None for v in valeurs.values()):
        return None, None, str(msg(cle_non_parametre, jour=jour.isoformat()))
    if len(set(valeurs.values())) > 1:
        codes = dict(
            Projet.objects.filter(pk__in=[p for p in cibles if p]).values_list("pk", "code")
        )
        detail = ", ".join(
            f"{codes.get(p, p)} = {v}" for p, v in sorted(valeurs.items(), key=lambda x: str(x[0]))
        )
        return None, None, str(msg(cle_differents, detail=detail))
    origines = {r.origine[champ] for r in par_projet.values()}
    return (
        next(iter(valeurs.values())),
        ("projet" if "projet" in origines else "organisation"),
        None,
    )


def resoudre_reference(
    projets, jour: datetime.date, devise_reference: str | None = None, type_taux: str | None = None
) -> ReferenceResolue:
    """Devise de référence et type de taux d'une consolidation : le paramètre explicite d'abord,
    sinon le réglage (projet puis organisation), sinon « non paramétré » (jamais de repli).
    """
    reference, o_ref, raison = _resoudre_champ(
        projets,
        jour,
        "devise_reference",
        devise_reference,
        "tableau_de_bord.reference_non_parametree",
        "tableau_de_bord.references_differentes",
    )
    taux, o_taux, raison_taux = _resoudre_champ(
        projets,
        jour,
        "type_taux",
        type_taux,
        "tableau_de_bord.type_taux_non_parametre",
        "tableau_de_bord.type_taux_differents",
    )
    return ReferenceResolue(
        reference,
        taux,
        {"devise_reference": o_ref, "type_taux": o_taux},
        raison or raison_taux,
    )


def _taux_le_plus_recent(devise: str, jour: datetime.date, type_taux: str):
    ligne = (
        Taux.objects.filter(devise_id=devise, type_taux=type_taux, date__lte=jour)
        .order_by("-date")
        .first()
    )
    return (ligne.taux, ligne.date) if ligne else None


def consolider(
    indicateur,
    *,
    devise_reference: str | None = None,
    jour: datetime.date,
    type_taux: str | None = None,
):
    """Consolide un indicateur ; référence et type de taux : le paramètre, sinon le réglage.
    Jamais de taux inventé : un seul taux manquant empêche toute la consolidation, et le dit."""
    resolue = resoudre_reference(list(indicateur.par_projet), jour, devise_reference, type_taux)
    resultat = Consolidation(
        resolue.devise_reference, jour, resolue.type_taux, origine=resolue.origine
    )
    if resolue.raison:
        resultat.raison = resolue.raison
        return resultat
    devise_reference, type_taux = resolue.devise_reference, resolue.type_taux
    reference = Devise.objects.filter(pk=devise_reference).first()
    if reference is None:
        resultat.raison = str(
            msg("tableau_de_bord.devise_reference_inconnue", devise=devise_reference)
        )
        return resultat
    tenue = Organisation.objects.values_list("monnaie_tenue", flat=True).get()
    resultat.monnaie_tenue = tenue
    unite = Decimal(1).scaleb(-reference.decimales)
    devises = {d for montants in indicateur.par_projet.values() for d in montants}
    # Toute devise (référence comprise) autre que la monnaie de tenue demande un taux.
    manquantes = []
    for devise in sorted((devises | {devise_reference}) - {tenue}):
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

    def en_tenue(devise: str) -> Decimal:
        return Decimal(1) if devise == tenue else resultat.taux[devise][0]

    diviseur = en_tenue(devise_reference)
    for projet, montants in indicateur.par_projet.items():
        convertis = (
            montant if devise == devise_reference else (montant * en_tenue(devise) / diviseur)
            for devise, montant in montants.items()
        )
        resultat.par_projet[projet] = sum(
            (c.quantize(unite, rounding=ROUND_HALF_UP) for c in convertis), ZERO
        )
    resultat.montant = sum(resultat.par_projet.values(), ZERO)
    return resultat
