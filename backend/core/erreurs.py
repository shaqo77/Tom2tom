"""Codes d'erreur stables, en français, renvoyés par l'API. Voir L6-T01.

Un code est un contrat : on peut en ajouter, jamais en renommer. Les messages ne révèlent jamais
l'existence de données d'une autre organisation : un objet qui n'est pas visible par la RLS est
« introuvable », exactement comme un objet qui n'existe pas.
"""

from enum import StrEnum


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
    """Une erreur de règle métier, portant son code stable."""

    def __init__(self, code: CodeErreur, message: str):
        super().__init__(message)
        self.code = CodeErreur(code)
        self.message = message

    def vers_dict(self) -> dict:
        return {"code": self.code.value, "message": self.message}
