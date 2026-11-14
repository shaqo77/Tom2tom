"""Imputation sur les axes analytiques. Voir L2-T03."""

from core.i18n import msg

from .models import ValeurDimension


class ValeurIntrouvable(LookupError):
    """Aucune valeur de ce code dans ce plan, pour l'organisation courante."""


class ValeurNonImputable(ValueError):
    """La valeur est un regroupement : on n'impute qu'en feuille."""


class ValeurInactive(ValueError):
    """La valeur est désactivée : elle ne reçoit plus d'imputation."""


def exiger_valeur_imputable(code_plan: str, code: str) -> ValeurDimension:
    """Retourne la valeur d'axe, ou refuse l'imputation qui ne lui est pas permise."""
    valeur = ValeurDimension.objects.filter(plan__code=code_plan, code=code).first()
    if valeur is None:
        raise ValeurIntrouvable(msg("axes.valeur_existe_plan", code=code, code_plan=code_plan))
    if not valeur.is_postable:
        raise ValeurNonImputable(msg("axes.valeur_imputable_c_regroupement", code=code))
    if not valeur.is_active:
        raise ValeurInactive(msg("axes.valeur_inactive", code=code))
    return valeur
