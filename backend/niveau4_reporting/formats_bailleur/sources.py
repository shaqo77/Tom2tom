"""Les SOURCES qu'un fichier de correspondance peut citer : liste FERMÉE (règle 5).

Chaque source reçoit un contexte et rend un texte exact (jamais un nombre à virgule flottante).
Une source inconnue dans un fichier de correspondance est refusée au chargement.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from niveau1_socle.decaissements.models import DemandeRetrait, LigneDemande
from niveau1_socle.financements.models import Accord
from niveau1_socle.marches.models import Contrat
from niveau1_socle.organisations.models import Projet
from niveau1_socle.referentiels.models import Devise

from .types_bad import VIVANTES, type_bad

ZERO = Decimal(0)


@dataclass
class Contexte:
    demande: DemandeRetrait
    accord: Accord
    lignes: list[LigneDemande]
    decimales: int
    langue: str = "fr"
    cumuls: dict = field(
        default_factory=dict
    )  # contrat -> déjà payé par la Banque (requête, jamais saisi)

    def texte(self, montant: Decimal) -> str:
        return f"{montant.quantize(Decimal(1).scaleb(-self.decimales))}"


def contexte_de(demande: DemandeRetrait) -> Contexte:
    accord = Accord.objects.select_related("bailleur").get(pk=demande.accord_id)
    devise = Devise.objects.filter(code=accord.devise_id).first()
    lignes = list(
        demande.lignes.filter(etat="actif")
        .select_related("categorie")
        .order_by("date_piece", "piece", "id")
    )
    contexte = Contexte(demande, accord, lignes, devise.decimales if devise else 2)
    contrats = {x.contrat_id for x in lignes if x.contrat_id}
    for contrat_id in contrats:
        # « Déjà payé par la Banque » : ce que les demandes ANTÉRIEURES ont retiré à ce contrat.
        paye = ZERO
        for autre in LigneDemande.objects.filter(
            contrat_id=contrat_id,
            demande__status__in=VIVANTES,
            demande__created_at__lt=demande.created_at,
        ).exclude(demande_id=demande.pk):
            paye += autre.montant_a_retirer
        contexte.cumuls[contrat_id] = paye
    return contexte


def _titre_projet(c: Contexte) -> str:
    projet = Projet.objects.filter(pk=c.demande.project_id).first()
    label = projet.label if projet else {}
    return (
        (label.get(c.langue) or label.get("fr") or next(iter(label.values()), ""))
        if isinstance(label, dict)
        else ""
    )


def _numero_bad(c: Contexte) -> str:
    return c.demande.numero


def _date_demande(c: Contexte) -> str:
    return c.demande.soumise_le.date().isoformat() if c.demande.soumise_le else ""


# --- sources de DEMANDE (une valeur par fichier) --------------------------------------------------
SOURCES_DEMANDE = {
    "demande.type_bad": lambda c: type_bad(c.demande),
    "demande.numero": _numero_bad,
    "demande.date": _date_demande,
    "demande.devise": lambda c: c.accord.devise_id,
    "demande.montant_a_retirer": lambda c: c.texte(
        sum((x.montant_a_retirer for x in c.lignes), ZERO)
    ),
    "demande.periode": lambda c: (
        f"{c.demande.periode_debut.isoformat()} / {c.demande.periode_fin.isoformat()}"
    ),
    "accord.numero": lambda c: c.accord.numero,
    "accord.libelle": lambda c: c.accord.libelle,
    "accord.bailleur": lambda c: c.accord.bailleur.nom,
    "projet.titre": _titre_projet,
}


# --- sources de LIGNE (une valeur par dépense du tableau) -----------------------------------
def _contrat(c: Contexte, ligne: LigneDemande) -> Contrat | None:
    return Contrat.objects.filter(pk=ligne.contrat_id).first() if ligne.contrat_id else None


def _ligne_contrat(attribut):
    def lire(c: Contexte, ligne: LigneDemande) -> str:
        contrat = _contrat(c, ligne)
        return str(getattr(contrat, attribut)) if contrat else ""

    return lire


def _deja_paye(c: Contexte, ligne: LigneDemande) -> str:
    return c.texte(c.cumuls[ligne.contrat_id]) if ligne.contrat_id in c.cumuls else ""


def _valeur_contrat(c: Contexte, ligne: LigneDemande) -> str:
    contrat = _contrat(c, ligne)
    if contrat is None:
        return ""
    # La valeur d'un contrat est dans SA devise, qui n'est pas forcément celle de la demande.
    devise = Devise.objects.filter(code=contrat.devise).first()
    decimales = devise.decimales if devise else 2
    return f"{contrat.montant_initial.quantize(Decimal(1).scaleb(-decimales))}"


SOURCES_LIGNE = {
    "ligne.categorie": lambda c, x: x.categorie.code,
    "ligne.categorie_libelle": lambda c, x: (
        (x.categorie.label or {}).get(c.langue) or (x.categorie.label or {}).get("fr", "")
    ),
    "ligne.piece": lambda c, x: x.piece,
    "ligne.date_piece": lambda c, x: x.date_piece.isoformat(),
    "ligne.montant_a_retirer": lambda c, x: c.texte(x.montant_a_retirer),
    "ligne.montant_depense": lambda c, x: c.texte(x.montant),
    "ligne.taux": lambda c, x: "" if x.taux_applique is None else str(x.taux_applique.normalize()),
    "ligne.contrat_reference": _ligne_contrat("reference"),
    "ligne.contrat_objet": _ligne_contrat("objet"),
    "ligne.contrat_valeur": _valeur_contrat,
    "ligne.deja_paye_par_la_banque": _deja_paye,
}

# Le total d'un groupe de lignes (une catégorie) : somme exacte de la source indiquée.
SOURCES_TOTAL = {"ligne.montant_a_retirer", "ligne.montant_depense"}
