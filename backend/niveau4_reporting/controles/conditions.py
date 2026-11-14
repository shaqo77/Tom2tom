"""Le langage de conditions des contrôles : structuré, borné, sans `eval`. Voir L6-T01.

L'`expression` d'un contrôle n'est JAMAIS du texte libre : c'est une structure JSON
`{"type_regle": …, "conditions": [{"champ": …, "op": …, "valeur": …}, …]}` validée par un schéma
PROPRE À CHAQUE TYPE DE RÈGLE, puis évaluée en Python avec des `Decimal`. Règle 5 : aucune requête
SQL, aucun JavaScript, aucun `eval`/`exec`, et le jeu d'opérateurs est FERMÉ.

Les conditions d'une expression se lisent ensemble : le contrôle est réussi si TOUTES sont vraies
(un contrôle énonce ce qui doit être vrai ; sinon il porte sa sévérité). Une condition qui sort du
schéma est refusée à l'enregistrement (`ConditionInvalide`), jamais au moment de l'évaluation.

Aucun `float` sur un montant : les montants s'écrivent en chaîne (`"1250.50"`) ou en entier, et le
contexte d'évaluation fournit des `Decimal`.
"""

import datetime
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

MAX_CONDITIONS = 20
MAX_LISTE = 200


class ConditionInvalide(ValueError):
    """La condition sort du schéma ou du jeu d'opérateurs : refusée à l'enregistrement."""


class TypeChamp(StrEnum):
    DECIMAL = "decimal"
    ENTIER = "entier"
    DATE = "date"
    TEXTE = "texte"
    BOOLEEN = "booleen"
    LISTE = "liste"


class Operateur(StrEnum):
    """Le jeu fermé du plan (L6-T01), et aucun autre."""

    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    EST_RENSEIGNE = "est_renseigne"
    EST_ABSENT = "est_absent"
    AVANT = "avant"
    APRES = "apres"
    ENTRE = "entre"
    EST_VRAI = "est_vrai"
    EST_FAUX = "est_faux"
    SOMME_LTE = "somme_lte"
    NOMBRE_EQ = "nombre_eq"


OPERATEURS = tuple(op.value for op in Operateur)
SCALAIRES = (TypeChamp.DECIMAL, TypeChamp.ENTIER, TypeChamp.DATE, TypeChamp.TEXTE)
# Quel opérateur pour quel type de champ.
COMPATIBILITE: dict[Operateur, tuple[TypeChamp, ...]] = {
    Operateur.EQ: SCALAIRES,
    Operateur.NEQ: SCALAIRES,
    Operateur.GT: (TypeChamp.DECIMAL, TypeChamp.ENTIER),
    Operateur.GTE: (TypeChamp.DECIMAL, TypeChamp.ENTIER),
    Operateur.LT: (TypeChamp.DECIMAL, TypeChamp.ENTIER),
    Operateur.LTE: (TypeChamp.DECIMAL, TypeChamp.ENTIER),
    Operateur.IN: SCALAIRES,
    Operateur.NOT_IN: SCALAIRES,
    Operateur.EST_RENSEIGNE: (*SCALAIRES, TypeChamp.BOOLEEN, TypeChamp.LISTE),
    Operateur.EST_ABSENT: (*SCALAIRES, TypeChamp.BOOLEEN, TypeChamp.LISTE),
    Operateur.AVANT: (TypeChamp.DATE,),
    Operateur.APRES: (TypeChamp.DATE,),
    Operateur.ENTRE: (TypeChamp.DATE,),
    Operateur.EST_VRAI: (TypeChamp.BOOLEEN,),
    Operateur.EST_FAUX: (TypeChamp.BOOLEEN,),
    Operateur.SOMME_LTE: (TypeChamp.LISTE,),
    Operateur.NOMBRE_EQ: (TypeChamp.LISTE,),
}
SANS_VALEUR = (
    Operateur.EST_RENSEIGNE,
    Operateur.EST_ABSENT,
    Operateur.EST_VRAI,
    Operateur.EST_FAUX,
)


@dataclass(frozen=True)
class Champ:
    type: TypeChamp
    # Pour une liste : le schéma de ses éléments (champ → type), utile à `somme_lte`.
    elements: tuple[tuple[str, TypeChamp], ...] = ()

    def sous_champ(self, nom: str) -> TypeChamp | None:
        return dict(self.elements).get(nom)


def _champs(**types) -> dict[str, Champ]:
    return {nom: Champ(TypeChamp(t)) for nom, t in types.items()}


def _liste(**elements) -> Champ:
    return Champ(TypeChamp.LISTE, tuple((n, TypeChamp(t)) for n, t in elements.items()))


_DEPENSE = {
    **_champs(
        montant="decimal",
        taxes="decimal",
        date="date",
        categorie="texte",
        sous_categorie="texte",
        source="texte",
        axe_1="texte",
        axe_2="texte",
        axe_3="texte",
        axe_4="texte",
        axe_5="texte",
        compte="texte",
        nature="texte",
        zone="texte",
        beneficiaire="texte",
        numero_facture="texte",
        facture_en_double="booleen",
        destinee_etat_certifie="booleen",
        methode="texte",
    ),
    "pieces": _liste(type="texte", valide="booleen", rattachee="booleen"),
}
# Un schéma PAR TYPE DE RÈGLE : un champ qui n'est pas ici est refusé à l'enregistrement.
SCHEMAS: dict[str, dict[str, Champ]] = {
    "codification": _DEPENSE,
    "pieces": _DEPENSE,
    "eligibilite": {
        **_DEPENSE,
        **_champs(date_debut_eligibilite="date", date_fin_eligibilite="date"),
    },
    "budget": _champs(
        montant="decimal",
        depense_cumulee="decimal",
        budget_ligne="decimal",
        plafond_categorie="decimal",
        allocation_categorie="decimal",
        plafond_accord="decimal",
        utilise_accord="decimal",
        disponible_categorie="decimal",
        disponible_ligne="decimal",
        disponible_allocation="decimal",
        disponible_accord="decimal",
    ),
    "tresorerie": _champs(
        ecart_rapprochement="decimal",
        ecart_justifie="booleen",
        solde_compte_designe="decimal",
        solde_attendu="decimal",
        ecart_solde="decimal",
        plafond_compte_designe="decimal",
    ),
    "avances": _champs(
        montant_avance="decimal",
        montant_justifie="decimal",
        jours_depuis_versement="entier",
        delai_applicable_jours="entier",
        jours_de_retard="entier",
        justifiee="booleen",
    ),
    "rapport": {
        **_champs(rubrique_obligatoire="booleen", rubrique_vide="booleen", valeur="decimal"),
        "comptes_non_mappes": _liste(code="texte"),
        "assertions_non_verifiees": _liste(code="texte"),
    },
    "coherence": _champs(
        ecart_entre_etats="decimal",
        ecart_entre_periodes="decimal",
        rupture_de_cumul="decimal",
    ),
    "risque": _champs(
        taux_consommation_categorie="decimal",
        jours_avance_non_apuree="entier",
        rejets_categorie="entier",
    ),
}
TYPES_DE_REGLE = tuple(SCHEMAS)


# --- validation ----------------------------------------------------------------------------


def _decimal(valeur, contexte: str) -> Decimal:
    if isinstance(valeur, bool) or isinstance(valeur, float):
        raise ConditionInvalide(
            f"{contexte} : un montant s'écrit en chaîne (« 1250.50 ») ou en entier, jamais en "
            "nombre à virgule flottante"
        )
    if not isinstance(valeur, (str, int)):
        raise ConditionInvalide(f"{contexte} : décimal attendu")
    try:
        nombre = Decimal(valeur) if isinstance(valeur, str) else Decimal(int(valeur))
    except InvalidOperation as erreur:
        raise ConditionInvalide(f"{contexte} : « {valeur} » n'est pas un décimal") from erreur
    if not nombre.is_finite():
        raise ConditionInvalide(f"{contexte} : « {valeur} » n'est pas un nombre fini")
    return nombre


def _entier(valeur, contexte: str) -> int:
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        raise ConditionInvalide(f"{contexte} : entier attendu")
    return valeur


def _date(valeur, contexte: str) -> datetime.date:
    if not isinstance(valeur, str):
        raise ConditionInvalide(f"{contexte} : date ISO (AAAA-MM-JJ) attendue")
    try:
        return datetime.date.fromisoformat(valeur)
    except ValueError as erreur:
        raise ConditionInvalide(f"{contexte} : « {valeur} » n'est pas une date ISO") from erreur


def _texte(valeur, contexte: str) -> str:
    if not isinstance(valeur, str):
        raise ConditionInvalide(f"{contexte} : texte attendu")
    return valeur


_CONVERTISSEURS = {
    TypeChamp.DECIMAL: _decimal,
    TypeChamp.ENTIER: _entier,
    TypeChamp.DATE: _date,
    TypeChamp.TEXTE: _texte,
}


@dataclass(frozen=True)
class ConditionPreparee:
    champ: str
    operateur: Operateur
    type_champ: TypeChamp
    valeur: object  # converti : Decimal, int, date, str, tuple ou None
    somme_de: str | None = None


def _preparer_condition(condition, champs: dict[str, Champ], numero: int) -> ConditionPreparee:
    lieu = f"condition {numero}"
    if not isinstance(condition, dict):
        raise ConditionInvalide(f"{lieu} : un objet est attendu")
    inconnues = set(condition) - {"champ", "op", "valeur", "somme_de"}
    if inconnues:
        raise ConditionInvalide(f"{lieu} : clés inconnues {sorted(inconnues)}")
    nom = condition.get("champ")
    if nom not in champs:
        raise ConditionInvalide(f"{lieu} : champ « {nom} » hors du schéma de ce type de règle")
    champ = champs[nom]
    brut = condition.get("op")
    if brut not in OPERATEURS:
        raise ConditionInvalide(f"{lieu} : opérateur « {brut} » inconnu (jeu fermé : {OPERATEURS})")
    operateur = Operateur(brut)
    if champ.type not in COMPATIBILITE[operateur]:
        raise ConditionInvalide(
            f"{lieu} : l'opérateur « {brut} » ne s'applique pas à un champ {champ.type.value} "
            f"(« {nom} »)"
        )
    somme_de = condition.get("somme_de")
    if operateur is not Operateur.SOMME_LTE and somme_de is not None:
        raise ConditionInvalide(f"{lieu} : « somme_de » n'existe que pour somme_lte")
    if operateur in SANS_VALEUR:
        if "valeur" in condition:
            raise ConditionInvalide(f"{lieu} : « {brut} » ne prend pas de valeur")
        return ConditionPreparee(nom, operateur, champ.type, None)
    if "valeur" not in condition:
        raise ConditionInvalide(f"{lieu} : « {brut} » exige une valeur")
    valeur = condition["valeur"]
    if operateur is Operateur.SOMME_LTE:
        if champ.sous_champ(somme_de) not in (TypeChamp.DECIMAL, TypeChamp.ENTIER):
            raise ConditionInvalide(
                f"{lieu} : « somme_de » désigne un champ numérique des éléments de « {nom} »"
            )
        return ConditionPreparee(nom, operateur, champ.type, _decimal(valeur, lieu), somme_de)
    if operateur is Operateur.NOMBRE_EQ:
        return ConditionPreparee(nom, operateur, champ.type, _entier(valeur, lieu))
    convertir = _CONVERTISSEURS[champ.type]
    if operateur in (Operateur.IN, Operateur.NOT_IN):
        if not isinstance(valeur, list) or not valeur or len(valeur) > MAX_LISTE:
            raise ConditionInvalide(f"{lieu} : une liste de 1 à {MAX_LISTE} valeurs est attendue")
        return ConditionPreparee(
            nom, operateur, champ.type, tuple(convertir(v, lieu) for v in valeur)
        )
    if operateur is Operateur.ENTRE:
        if not isinstance(valeur, list) or len(valeur) != 2:
            raise ConditionInvalide(f"{lieu} : « entre » prend deux dates [du, au[")
        du, au = (_date(v, lieu) for v in valeur)
        if du >= au:
            raise ConditionInvalide(f"{lieu} : l'intervalle [du, au[ est vide ou à l'envers")
        return ConditionPreparee(nom, operateur, champ.type, (du, au))
    return ConditionPreparee(nom, operateur, champ.type, convertir(valeur, lieu))


@dataclass(frozen=True)
class ExpressionPreparee:
    type_regle: str
    conditions: tuple[ConditionPreparee, ...]


def preparer_expression(expression, type_regle: str | None = None) -> ExpressionPreparee:
    """Valide `expression` contre le schéma de son type de règle ; lève `ConditionInvalide`."""
    if not isinstance(expression, dict):
        raise ConditionInvalide("l'expression est un objet JSON")
    inconnues = set(expression) - {"type_regle", "conditions"}
    if inconnues:
        raise ConditionInvalide(f"clés inconnues {sorted(inconnues)}")
    type_regle = expression.get("type_regle") if type_regle is None else type_regle
    if type_regle not in SCHEMAS:
        raise ConditionInvalide(f"type de règle « {type_regle} » inconnu ({TYPES_DE_REGLE})")
    if "type_regle" in expression and expression["type_regle"] != type_regle:
        raise ConditionInvalide("le type de règle de l'expression diffère de celui du contrôle")
    conditions = expression.get("conditions")
    if not isinstance(conditions, list) or not 1 <= len(conditions) <= MAX_CONDITIONS:
        raise ConditionInvalide(f"de 1 à {MAX_CONDITIONS} conditions sont attendues")
    schema = SCHEMAS[type_regle]
    return ExpressionPreparee(
        type_regle,
        tuple(_preparer_condition(c, schema, i) for i, c in enumerate(conditions, start=1)),
    )


# --- évaluation ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Constat:
    champ: str
    operateur: str
    constate: object
    attendu: object
    satisfaite: bool

    def lisible(self) -> str:
        attendu = "" if self.attendu is None else f" {self.attendu}"
        return f"{self.champ} = {self.constate} ; attendu : {self.operateur}{attendu}"


def _verifier_type(valeur, type_champ: TypeChamp, nom: str):
    """Le contexte doit fournir le bon type : jamais de `float` pour un montant (règle 1)."""
    if valeur is None:
        return None
    attendu = {
        TypeChamp.DECIMAL: Decimal,
        TypeChamp.ENTIER: int,
        TypeChamp.DATE: datetime.date,
        TypeChamp.TEXTE: str,
        TypeChamp.BOOLEEN: bool,
        TypeChamp.LISTE: (list, tuple),
    }[type_champ]
    if isinstance(valeur, float) or (
        type_champ is not TypeChamp.BOOLEEN and isinstance(valeur, bool)
    ):
        raise TypeError(f"le champ « {nom} » reçoit un {type(valeur).__name__}")
    if type_champ is TypeChamp.DATE and isinstance(valeur, datetime.datetime):
        raise TypeError(f"le champ « {nom} » est une date, pas un horodatage")
    if not isinstance(valeur, attendu):
        raise TypeError(f"le champ « {nom} » attend un {type_champ.value}, pas {type(valeur)}")
    return valeur


def _condition(c: ConditionPreparee, valeur) -> bool:
    op = c.operateur
    if op is Operateur.EST_ABSENT:
        return valeur is None or valeur == "" or valeur == [] or valeur == ()
    if op is Operateur.EST_RENSEIGNE:
        return not _condition(
            ConditionPreparee(c.champ, Operateur.EST_ABSENT, c.type_champ, None), valeur
        )
    if op is Operateur.EST_VRAI:
        return valeur is True
    if op is Operateur.EST_FAUX:
        return valeur is False
    if op is Operateur.SOMME_LTE:
        elements = valeur or ()
        somme = sum(
            (
                _verifier_type(e.get(c.somme_de), TypeChamp.DECIMAL, c.somme_de) or 0
                for e in elements
            ),
            Decimal(0),
        )
        return somme <= c.valeur
    if op is Operateur.NOMBRE_EQ:
        return len(valeur or ()) == c.valeur
    if valeur is None:
        return op in (Operateur.NEQ, Operateur.NOT_IN)  # l'absence n'égale ni n'appartient à rien
    if op is Operateur.EQ:
        return valeur == c.valeur
    if op is Operateur.NEQ:
        return valeur != c.valeur
    if op is Operateur.GT:
        return valeur > c.valeur
    if op is Operateur.GTE:
        return valeur >= c.valeur
    if op is Operateur.LT:
        return valeur < c.valeur
    if op is Operateur.LTE:
        return valeur <= c.valeur
    if op is Operateur.IN:
        return valeur in c.valeur
    if op is Operateur.NOT_IN:
        return valeur not in c.valeur
    if op is Operateur.AVANT:
        return valeur < c.valeur
    if op is Operateur.APRES:
        return valeur > c.valeur
    if op is Operateur.ENTRE:
        du, au = c.valeur
        return du <= valeur < au  # semi-ouvert : [du, au[
    raise AssertionError(f"opérateur non géré : {op}")  # pragma: no cover (jeu fermé)


def _presenter(valeur):
    if isinstance(valeur, (list, tuple)) and valeur and isinstance(valeur[0], dict):
        return f"{len(valeur)} élément(s)"
    return valeur


def evaluer(expression: ExpressionPreparee, contexte: dict) -> list[Constat]:
    """Un constat par condition, dans l'ordre. Le contrôle est réussi si tous sont satisfaits."""
    schema = SCHEMAS[expression.type_regle]
    constats = []
    for c in expression.conditions:
        valeur = _verifier_type(contexte.get(c.champ), schema[c.champ].type, c.champ)
        attendu = c.valeur
        if c.operateur is Operateur.SOMME_LTE:
            attendu = f"somme de {c.somme_de} <= {c.valeur}"
        constats.append(
            Constat(c.champ, c.operateur.value, _presenter(valeur), attendu, _condition(c, valeur))
        )
    return constats


def reussit(constats: list[Constat]) -> bool:
    return all(c.satisfaite for c in constats)
