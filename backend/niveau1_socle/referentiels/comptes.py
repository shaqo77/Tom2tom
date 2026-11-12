"""Imputation sur le plan comptable. Voir L2-T02."""

from .models import Compte


class CompteIntrouvable(LookupError):
    """Aucun compte de ce code dans le plan de l'organisation courante."""


class CompteNonImputable(ValueError):
    """Le compte est un total : on n'impute que sur un compte feuille."""


class CompteInactif(ValueError):
    """Le compte est désactivé : il ne reçoit plus d'imputation."""


def exiger_compte_imputable(code: str) -> Compte:
    """Retourne le compte, ou refuse l'imputation directe qui ne lui est pas permise.

    Lu sous la RLS de l'organisation courante. L'écran de saisie et le grand livre
    (lot L3) passent par cette fonction : un total ne reçoit jamais d'écriture.
    """
    compte = Compte.objects.filter(code=code).first()
    if compte is None:
        raise CompteIntrouvable(f"Le compte {code} n'existe pas dans le plan comptable")
    if not compte.imputable:
        raise CompteNonImputable(f"Le compte {code} n'est pas imputable : c'est un total")
    if not compte.actif:
        raise CompteInactif(f"Le compte {code} est inactif")
    return compte
