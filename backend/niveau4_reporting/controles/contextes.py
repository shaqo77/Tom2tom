"""Les contextes qui nourrissent les contrôles. Voir L6-T01.

Un contexte est un dictionnaire dont les champs sont EXACTEMENT ceux du schéma du type de règle
(`conditions.SCHEMAS`) : `contexte()` refuse un champ inconnu ou d'un mauvais type, pour qu'un
module appelant ne passe pas en silence une donnée mal nommée (un champ mal nommé serait lu comme
absent, donc un contrôle « renseigné » échouerait, ou pire, un contrôle de plafond serait
non applicable).

Aucun module ne réimplémente les règles : il construit un contexte et appelle le moteur.
"""

import datetime
from decimal import Decimal

from niveau1_socle.comptabilite.models import LigneEcriture
from niveau1_socle.financements.models import Accord, Categorie

from . import conditions


def contexte(type_regle: str, **champs) -> dict:
    """Un contexte conforme au schéma de `type_regle` ; lève sinon (`KeyError`/`TypeError`)."""
    if type_regle not in conditions.SCHEMAS:
        raise KeyError(f"type de règle inconnu : {type_regle}")
    schema = conditions.SCHEMAS[type_regle]
    inconnus = set(champs) - set(schema)
    if inconnus:
        raise KeyError(f"champs hors du schéma « {type_regle} » : {sorted(inconnus)}")
    for nom, valeur in champs.items():
        conditions._verifier_type(valeur, schema[nom].type, nom)
    return dict(champs)


def reste_apres(limite: Decimal | None, deja: Decimal, montant: Decimal) -> Decimal | None:
    """Ce qui reste d'une limite après `montant` ; rien si la limite n'existe pas.

    Un reste négatif est un dépassement. Une limite absente donne `None` : le contrôle de plafond
    est alors non applicable (il n'y a rien à dépasser).
    """
    return None if limite is None else limite - deja - montant


def facture_en_double(ligne: LigneEcriture) -> bool:
    """Vrai si une AUTRE écriture du projet porte la même référence de document pour le même
    tiers. Sans référence ou sans tiers, on ne peut pas affirmer un doublon."""
    reference = ligne.entry.document_ref
    if not reference or ligne.partner_id is None:
        return False
    return (
        LigneEcriture.objects.filter(
            project_id=ligne.project_id,
            entry__document_ref=reference,
            partner_id=ligne.partner_id,
        )
        .exclude(entry_id=ligne.entry_id)
        .exists()
    )


def contexte_depense(
    ligne: LigneEcriture,
    *,
    source: str | None = None,
    pieces=(),
    nature: str | None = None,
    zone: str | None = None,
    beneficiaire: str | None = None,
    methode: str | None = None,
    destinee_etat_certifie: bool = False,
) -> dict:
    """Le contexte d'une dépense, lu sur sa ligne comptable.

    Ce que le grand livre ne porte pas (nature, zone, bénéficiaire, méthode, pièces) est fourni par
    l'appelant ; `pieces` est une liste de `{"type", "rattachee", "valide"}`.
    """
    categorie = None
    if ligne.category_id is not None:
        categorie = (
            Categorie.objects.filter(pk=ligne.category_id).values_list("code", flat=True).first()
        )
    if source is None and ligne.agreement_id is not None:
        source = (
            Accord.objects.filter(pk=ligne.agreement_id).values_list("numero", flat=True).first()
        )
    axes = {
        f"axe_{i}": (getattr(ligne, f"dim{i}").code if getattr(ligne, f"dim{i}_id") else None)
        for i in range(1, 5)
    }
    return contexte(
        "codification",
        montant=ligne.debit or ligne.credit,
        date=ligne.entry.accounting_date,
        categorie=categorie,
        source=source,
        compte=ligne.account.code,
        numero_facture=ligne.entry.document_ref or None,
        facture_en_double=facture_en_double(ligne),
        destinee_etat_certifie=destinee_etat_certifie,
        nature=nature,
        zone=zone,
        beneficiaire=beneficiaire,
        methode=methode,
        pieces=list(pieces),
        **axes,
    )


def contexte_avance(situation, date: datetime.date) -> dict:
    """Le contexte d'une avance, lu sur sa situation à `date` (module des avances, L4-T07)."""
    avance = situation.avance
    return contexte(
        "avances",
        montant_avance=avance.montant,
        montant_justifie=situation.justifie,
        jours_depuis_versement=(date - avance.date_versement).days,
        delai_applicable_jours=avance.delai_jours,
        jours_de_retard=situation.jours_de_retard,
        justifiee=situation.reste == 0,
    )
