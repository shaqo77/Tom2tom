"""La décision d'un contrôle, en logique pure : applicabilité, pièces, résultat. Voir L6-T01.

Séparée du service pour être testée sans base : c'est ce module qui dit « réussi », « bloquant »,
« non applicable » ou « à vérifier » ; le service ne fait que l'enregistrer au journal.

Règle de pièces : une pièce requise est une règle de ce moteur (type de pièce, portée par
`applicable_si` : catégorie, méthode, seuil de montant, nature), pas une table de plus. Le moteur
ne retient, parmi les pièces fournies, que celles **du bon type, rattachées à l'opération**, et
validées lorsque la règle l'exige : une pièce du mauvais type ou non rattachée est refusée comme
absente. Il n'existe pas de liste universelle de justificatifs.
"""

from dataclasses import dataclass, field

from core.i18n import Liste, Localise, Message, msg

from . import conditions
from .models import ModeControle, Resultat

CLES_PARAMETRES = {"type_piece", "validee"}


class ParametresInvalides(ValueError):
    """Les paramètres d'une règle sortent de ce que son type de règle accepte."""


def valider_parametres(type_regle: str, parametres) -> dict:
    parametres = {} if parametres is None else parametres
    if not isinstance(parametres, dict):
        raise ParametresInvalides(msg("decision.parametres_objet"))
    if not parametres:
        return {}
    if type_regle != "pieces":
        raise ParametresInvalides(msg("decision.seule_regle_pieces_porte_parametres"))
    inconnus = set(parametres) - CLES_PARAMETRES
    if inconnus:
        raise ParametresInvalides(msg("decision.parametres_inconnus", v1=sorted(inconnus)))
    type_piece = parametres.get("type_piece")
    if not isinstance(type_piece, str) or not type_piece.strip():
        raise ParametresInvalides(msg("decision.type_piece_type_piece_exigee"))
    validee = parametres.get("validee", False)
    if not isinstance(validee, bool):
        raise ParametresInvalides(msg("decision.validee_booleen"))
    return {"type_piece": type_piece.strip(), "validee": validee}


def pieces_retenues(pieces, parametres: dict) -> list:
    """Les pièces qui comptent : du bon type, rattachées à l'opération, validées si exigé."""
    retenues = []
    for piece in pieces or ():
        if piece.get("type") != parametres["type_piece"]:
            continue
        if piece.get("rattachee") is not True:
            continue
        if parametres.get("validee") and piece.get("valide") is not True:
            continue
        retenues.append(piece)
    return retenues


@dataclass
class Decision:
    resultat: Resultat
    constats: list = field(default_factory=list)  # les constats de l'expression (échec ou succès)
    message: Message | None = None
    premier_echec: conditions.Constat | None = None


def decider(
    *,
    libelle: dict | str,
    mode: str,
    severity: str,
    type_regle: str,
    expression: dict | None,
    applicable_si: dict | None,
    parametres: dict | None,
    contexte: dict,
) -> Decision:
    libelle = Localise(libelle)
    if mode == ModeControle.MANUEL:
        return Decision(
            Resultat.A_VERIFIER, [], msg("decision.verification_humaine_requise", libelle=libelle)
        )
    if applicable_si is not None:
        applicable = conditions.reussit(
            conditions.evaluer(conditions.preparer_expression(applicable_si, type_regle), contexte)
        )
        if not applicable:
            return Decision(
                Resultat.NON_APPLICABLE, [], msg("decision.non_applicable", libelle=libelle)
            )
    if parametres and parametres.get("type_piece"):
        contexte = {**contexte, "pieces": pieces_retenues(contexte.get("pieces"), parametres)}
    constats = conditions.evaluer(conditions.preparer_expression(expression, type_regle), contexte)
    if conditions.reussit(constats):
        return Decision(Resultat.REUSSI, constats, msg("decision.reussi", libelle=libelle))
    echecs = [c for c in constats if not c.satisfaite]
    return Decision(
        Resultat(severity),
        constats,
        msg(
            "decision.echec",
            libelle=libelle,
            details=Liste([c.lisible() for c in echecs], "; "),
        ),
        echecs[0],
    )
