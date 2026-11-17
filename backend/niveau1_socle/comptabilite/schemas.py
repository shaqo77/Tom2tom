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

from core.i18n import msg

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
        raise SchemaIncoherent(
            msg("schemas.compte_regle_inconnue", compte=modele.compte, regle=modele.regle)
        )
    if modele.regle == "solde":
        if modele.sens is not None:
            raise SchemaIncoherent(
                msg("schemas.compte_contrepartie_automatique_sens_declare", compte=modele.compte)
            )
    elif modele.sens is None:
        raise SchemaIncoherent(msg("schemas.compte_sens_obligatoire", compte=modele.compte))
    elif modele.sens not in SENS:
        raise SchemaIncoherent(
            msg("schemas.compte_sens_inconnu", compte=modele.compte, sens=modele.sens)
        )
    if modele.regle == "taux" and (modele.taux is None or modele.taux <= 0):
        raise SchemaIncoherent(
            msg("schemas.compte_taux_doit_etre_strictement", compte=modele.compte)
        )
    if modele.regle != "taux" and modele.taux is not None:
        raise SchemaIncoherent(msg("schemas.compte_seule_regle_taux_porte", compte=modele.compte))
    inconnus = set(modele.axes) - set(AXES_PERMIS)
    if inconnus:
        raise SchemaIncoherent(
            msg("schemas.compte_axe_inconnu", compte=modele.compte, v1=sorted(inconnus))
        )


def calculer_lignes(modeles: list[ModeleLigne], montant: Decimal, *, decimales: int) -> list[dict]:
    """Lignes de pièce prêtes pour `saisir_ecriture`, équilibrées arrondis compris.

    Les arrondis se font à `decimales` (celles de la devise), moitié vers le haut. La contrepartie
    automatique absorbe l'écart d'arrondi : la pièce est équilibrée quel que soit le montant.
    Une ligne dont le montant arrondi est nul n'est pas générée.
    """
    for modele in modeles:
        _verifier(modele)
    if sum(1 for modele in modeles if modele.regle == "solde") > 1:
        raise SchemaIncoherent(msg("schemas.schema_compte_seule_contrepartie_automatique"))

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
            msg("schemas.montant_nul_apres_arrondi_decimale", decimales=decimales)
        )
    if any(modele.regle == "solde" for modele in modeles) and debit == credit:
        raise SchemaIncoherent(msg("schemas.contrepartie_automatique_rien_equilibrer"))

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
            msg("schemas.aucune_version_schema_vigueur", code=code, v1=date.isoformat())
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
    devise: str | None = None,
    taux=1,
    journal: str | None = None,
    reference_piece: str = "",
    cle_idempotence: str | None = None,
):
    """Saisit un brouillon dont les lignes viennent d'un schéma. Même garde-fous que la saisie."""
    from niveau1_socle.referentiels.parametres_devises import monnaie_de_base

    from .services import JournalIntrouvable, saisir_ecriture

    devise = devise or monnaie_de_base(project_id)
    schema, lignes = generer_lignes_du_schema(code_schema, date_comptable, montant, devise)
    code_journal = journal or (schema.journal.code if schema.journal else None)
    if code_journal is None:
        raise JournalIntrouvable(msg("schemas.schema_indique_journal", code_schema=code_schema))
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
