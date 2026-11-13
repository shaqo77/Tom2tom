"""Schémas d'écritures : des modèles de lignes qui alimentent la saisie. Voir L3-T06.

Un schéma décrit une pièce type (achat avec TVA, recette…) : des comptes, un sens, une règle de
calcul. Il ALIMENTE la saisie sans la remplacer : on obtient des lignes que l'utilisateur peut
retoucher avant de les enregistrer par `saisir_ecriture`.

La règle de calcul est un élément d'un ensemble FERMÉ, jamais une formule libre :
- `base`  : le montant saisi ;
- `taux`  : montant × taux (TVA, retenue…), arrondi à la devise ;
- `solde` : la contrepartie automatique, qui équilibre la pièce, arrondis compris.
"""

import datetime
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q

REGLES = ("base", "taux", "solde")
SENS = ("debit", "credit")
AXES_PERMIS = ("dim1", "dim2", "dim3", "dim4", "aux1", "aux2", "aux3", "aux4")
ZERO = Decimal(0)


class SchemaIncoherent(ValueError):
    """Le schéma ne peut pas produire une pièce équilibrée."""


class SchemaIntrouvable(LookupError):
    """Aucune version de ce schéma n'est en vigueur à la date demandée."""


@dataclass(frozen=True)
class ModeleLigne:
    compte: str
    sens: str | None
    regle: str
    taux: Decimal | None
    axes: dict = field(default_factory=dict)


def _verifier(modele: ModeleLigne) -> None:
    if modele.regle not in REGLES:
        raise SchemaIncoherent(f"Compte {modele.compte} : règle inconnue {modele.regle!r}")
    if modele.regle == "solde":
        if modele.sens is not None:
            raise SchemaIncoherent(
                f"Compte {modele.compte} : une contrepartie automatique n'a pas de sens déclaré, "
                "il se déduit du solde"
            )
    elif modele.sens is None:
        raise SchemaIncoherent(f"Compte {modele.compte} : le sens est obligatoire")
    elif modele.sens not in SENS:
        raise SchemaIncoherent(f"Compte {modele.compte} : sens inconnu {modele.sens!r}")
    if modele.regle == "taux" and (modele.taux is None or modele.taux <= 0):
        raise SchemaIncoherent(f"Compte {modele.compte} : le taux doit être strictement positif")
    if modele.regle != "taux" and modele.taux is not None:
        raise SchemaIncoherent(f"Compte {modele.compte} : seule la règle taux porte un taux")
    inconnus = set(modele.axes) - set(AXES_PERMIS)
    if inconnus:
        raise SchemaIncoherent(f"Compte {modele.compte} : axe inconnu {sorted(inconnus)}")


def calculer_lignes(modeles: list[ModeleLigne], montant: Decimal, *, decimales: int) -> list[dict]:
    """Lignes de pièce prêtes pour `saisir_ecriture`, équilibrées arrondis compris.

    Les arrondis se font à `decimales` (celles de la devise), moitié vers le haut. La contrepartie
    automatique absorbe l'écart d'arrondi : la pièce est équilibrée quel que soit le montant.
    Une ligne dont le montant arrondi est nul n'est pas générée.
    """
    for modele in modeles:
        _verifier(modele)
    if sum(1 for modele in modeles if modele.regle == "solde") > 1:
        raise SchemaIncoherent("Un schéma ne compte qu'une seule contrepartie automatique")

    pas = Decimal(1).scaleb(-decimales)
    montants: list[Decimal | None] = []
    for modele in modeles:
        if modele.regle == "base":
            montants.append(montant.quantize(pas, rounding=ROUND_HALF_UP))
        elif modele.regle == "taux":
            montants.append((montant * modele.taux).quantize(pas, rounding=ROUND_HALF_UP))
        else:
            montants.append(None)  # la contrepartie se calcule en dernier

    debit = sum(
        (m for m, x in zip(montants, modeles, strict=True) if m and x.sens == "debit"), ZERO
    )
    credit = sum(
        (m for m, x in zip(montants, modeles, strict=True) if m and x.sens == "credit"), ZERO
    )
    if debit == credit == 0:
        raise SchemaIncoherent(
            f"Le montant est nul après arrondi à {decimales} décimale(s) : aucune pièce à générer"
        )
    if any(modele.regle == "solde" for modele in modeles) and debit == credit:
        raise SchemaIncoherent("La contrepartie automatique n'a rien à équilibrer")

    lignes = []
    for modele, valeur in zip(modeles, montants, strict=True):
        if modele.regle == "solde":
            sens, valeur = (
                ("credit", debit - credit) if debit > credit else ("debit", credit - debit)
            )
        else:
            sens = modele.sens
        if valeur == 0:
            continue
        lignes.append(
            {
                "compte": modele.compte,
                "debit": str(valeur) if sens == "debit" else "0",
                "credit": str(valeur) if sens == "credit" else "0",
                **modele.axes,
            }
        )
    return lignes


# --- accès à la base : version applicable, génération, saisie -----------------------------


def schema_applicable(code: str, date: datetime.date):
    """La version du schéma en vigueur à `date` : validité `[valid_from, valid_to[`."""
    from .models import SchemaEcriture

    schema = (
        SchemaEcriture.objects.select_related("journal")
        .filter(code=code, valid_from__lte=date)
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=date))
        .order_by("-version")
        .first()
    )
    if schema is None:
        raise SchemaIntrouvable(
            f"Aucune version du schéma {code} n'est en vigueur le {date.isoformat()}"
        )
    return schema


def generer_lignes_du_schema(code_schema, date_comptable, montant, devise):
    """Résout la version à la date comptable et calcule ses lignes. Retourne (schéma, lignes)."""
    from niveau1_socle.referentiels.models import Devise

    schema = schema_applicable(code_schema, date_comptable)
    modeles = [
        ModeleLigne(
            compte=ligne.compte.code,
            sens=ligne.sens,
            regle=ligne.regle,
            taux=ligne.taux,
            axes=ligne.axes,
        )
        for ligne in schema.lignes.select_related("compte").order_by("rang")
    ]
    decimales = Devise.objects.get(pk=devise).decimales
    return schema, calculer_lignes(modeles, Decimal(str(montant)), decimales=decimales)


def saisir_depuis_schema(
    *,
    utilisateur,
    project_id,
    code_schema: str,
    montant,
    date_comptable: datetime.date,
    libelle: str,
    devise: str = "DJF",
    taux=1,
    journal: str | None = None,
    reference_piece: str = "",
    cle_idempotence: str | None = None,
):
    """Saisit un brouillon dont les lignes viennent d'un schéma. Même garde-fous que la saisie."""
    from .services import JournalIntrouvable, saisir_ecriture

    schema, lignes = generer_lignes_du_schema(code_schema, date_comptable, montant, devise)
    code_journal = journal or (schema.journal.code if schema.journal else None)
    if code_journal is None:
        raise JournalIntrouvable(f"Le schéma {code_schema} n'indique pas de journal")
    return saisir_ecriture(
        utilisateur=utilisateur,
        project_id=project_id,
        journal=code_journal,
        date_comptable=date_comptable,
        libelle=libelle,
        lignes=lignes,
        devise=devise,
        taux=taux,
        reference_piece=reference_piece,
        cle_idempotence=cle_idempotence,
        schema=schema,
    )
