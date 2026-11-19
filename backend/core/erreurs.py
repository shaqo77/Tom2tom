"""Codes d'erreur stables renvoyés par l'API. Voir L6-T01.

Un code est un contrat : on peut en ajouter, jamais en renommer. Le MESSAGE accompagne le code
dans la langue de la requête (voir `core/i18n.py`). Il ne révèle jamais l'existence de données
d'une autre organisation : un objet que la RLS ne montre pas est « introuvable », exactement comme
un objet qui n'existe pas.
"""

from enum import StrEnum

from .i18n import Message, texte


class CodeErreur(StrEnum):
    ACCES_ORGANISATION_REFUSE = "ACCES_ORGANISATION_REFUSE"
    ACCES_PROJET_REFUSE = "ACCES_PROJET_REFUSE"
    ACCORD_INTROUVABLE = "ACCORD_INTROUVABLE"
    AUCUNE_CONFIGURATION_A_LA_DATE = "AUCUNE_CONFIGURATION_A_LA_DATE"
    CONFIGURATION_NON_APPROUVEE = "CONFIGURATION_NON_APPROUVEE"
    CONFLIT_DE_PERIODE = "CONFLIT_DE_PERIODE"
    REGLE_INVALIDE = "REGLE_INVALIDE"
    CONTROLE_BLOQUANT = "CONTROLE_BLOQUANT"
    PIECE_OBLIGATOIRE = "PIECE_OBLIGATOIRE"
    SOLDE_CATEGORIE_INSUFFISANT = "SOLDE_CATEGORIE_INSUFFISANT"
    APPROBATION_REQUISE = "APPROBATION_REQUISE"
    TRANSITION_INTERDITE = "TRANSITION_INTERDITE"


class ErreurMetier(ValueError):
    """Une erreur de règle métier : un code stable et un message (catalogué ou brut)."""

    def __init__(self, code: CodeErreur, message: Message | str):
        super().__init__(message)
        self.code = CodeErreur(code)

    @property
    def message(self) -> str:
        """Le message dans la langue active."""
        return texte(self)

    def vers_dict(self, langue: str | None = None) -> dict:
        return {"code": self.code.value, "message": texte(self, langue)}
