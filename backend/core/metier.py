"""Helpers communs aux services métier : habilitation, refus, montants, violations d'intégrité.

Un seul jeu, partagé par les services du plan de passation, des contrats, des décomptes et de la
trésorerie : une règle (« jamais de float », message d'habilitation) se corrige en un seul endroit.
Le message d'habilitation et celui d'un montant invalide restent ceux du domaine appelant : on
passe la clé de catalogue.
"""

from decimal import Decimal, InvalidOperation

from rest_framework.exceptions import PermissionDenied

from niveau1_socle.habilitations.permissions import est_habilite

from .erreurs import CodeErreur, ErreurMetier
from .i18n import msg


def habilite(
    utilisateur, operation: str, project_id, *, cle: str = "metier.habilitation_requise"
) -> None:
    """Refuse (403) un utilisateur sans l'habilitation `operation` sur le projet."""
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(msg(cle, operation=operation))


def refuser(cle: str, **params):
    """Lève un refus métier (règle invalide) avec un message du catalogue."""
    raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg(cle, **params))


def decimal(valeur, champ: str, *, signe: str = "positif", cle: str = "metier.montant_invalide"):
    """Un montant décimal exact. Jamais un float, jamais NaN ni infini.

    `signe` : `positif` (> 0), `positif_ou_nul` (≥ 0) ou `libre` (tout nombre fini).
    """
    try:
        nombre = Decimal(str(valeur))
    except InvalidOperation:
        refuser(cle, champ=champ)
    if not nombre.is_finite() or isinstance(valeur, float):
        refuser(cle, champ=champ)
    if (signe == "positif" and nombre <= 0) or (signe == "positif_ou_nul" and nombre < 0):
        refuser(cle, champ=champ)
    return nombre


def traduire_integrite(
    erreur: Exception,
    connues: dict[str, tuple[str, dict]] | None = None,
    *,
    defaut: str = "metier.integrite_refusee",
) -> ErreurMetier:
    """Traduit une violation d'intégrité de la base en refus métier SPÉCIFIQUE.

    `connues` associe le nom d'une contrainte (présent dans le message de la base) à
    `(clé de catalogue, paramètres)`. Toute autre violation garde le message écrit par la
    base (sa première ligne) : jamais « référence déjà existante » à tort.
    """
    texte = str(erreur)
    for contrainte, (cle, params) in (connues or {}).items():
        if contrainte in texte:
            return ErreurMetier(CodeErreur.REGLE_INVALIDE, msg(cle, **params))
    detail = texte.split("\n", 1)[0].strip()
    return ErreurMetier(CodeErreur.REGLE_INVALIDE, msg(defaut, detail=detail))
