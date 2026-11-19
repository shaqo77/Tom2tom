"""Socle des API métier : lecture stricte du JSON, sortie sérialisable, erreurs au format stable.

- **Entrée** : un corps JSON objet. Un montant se donne en CHAÎNE (« 1250.50 ») : un nombre JSON
  décimal est un `float`, refusé par la règle « jamais de float sur un montant ». Chaque champ est
  typé et son refus nomme le champ.
- **Sortie** : montants, dates et identifiants en chaînes ; jamais de `float`.
- **Erreurs** : `{"code", "message"}` dans la langue de la requête. Règle invalide → 422,
  transition interdite → 409, habilitation → 403, objet d'une autre organisation ou absent → 404.
"""

import base64
import binascii
import datetime
import uuid
from decimal import Decimal
from typing import Any

from django.http import Http404
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.views import APIView, exception_handler

from .erreurs import CodeErreur, ErreurMetier
from .i18n import msg, texte


class VueMetier(APIView):
    """Une vue métier : la session authentifie ; le SERVICE appelé contrôle l'habilitation sur le
    projet de l'objet (403), la base l'isolation par organisation (404)."""


# --- entrée ------------------------------------------------------------------------------------


def _refuser(cle: str, **params):
    raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg(cle, **params))


def corps(requete) -> dict:
    donnees = requete.data
    if not isinstance(donnees, dict):
        raise ParseError(str(msg("api.corps_objet")))
    return donnees


def champ(donnees: dict, nom: str, *, obligatoire: bool = True, defaut: Any = None) -> Any:
    valeur = donnees.get(nom)
    if valeur is None or valeur == "":
        if obligatoire:
            _refuser("api.champ_obligatoire", champ=nom)
        return defaut
    return valeur


def champ_texte(donnees: dict, nom: str, **options) -> str | None:
    valeur = champ(donnees, nom, **options)
    if valeur is None:
        return valeur
    if not isinstance(valeur, str):
        _refuser("api.champ_invalide", champ=nom, attendu="texte")
    return valeur.strip()


def champ_decimal(donnees: dict, nom: str, **options) -> str | None:
    """Un montant : une CHAÎNE (ou un entier). Un nombre à virgule JSON (float) est refusé."""
    valeur = champ(donnees, nom, **options)
    if valeur is None:
        return valeur
    if isinstance(valeur, bool) or isinstance(valeur, float) or not isinstance(valeur, str | int):
        _refuser("api.champ_invalide", champ=nom, attendu="montant en chaîne")
    return str(valeur)


def champ_date(donnees: dict, nom: str, **options) -> datetime.date | None:
    valeur = champ(donnees, nom, **options)
    if valeur is None:
        return valeur
    try:
        return datetime.date.fromisoformat(str(valeur))
    except ValueError:
        _refuser("api.champ_invalide", champ=nom, attendu="date AAAA-MM-JJ")


def champ_entier(donnees: dict, nom: str, **options) -> int | None:
    valeur = champ(donnees, nom, **options)
    if valeur is None:
        return valeur
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        _refuser("api.champ_invalide", champ=nom, attendu="entier")
    return valeur


def champ_uuid(donnees: dict, nom: str, **options) -> uuid.UUID | None:
    valeur = champ(donnees, nom, **options)
    if valeur is None:
        return valeur
    try:
        return uuid.UUID(str(valeur))
    except ValueError:
        _refuser("api.champ_invalide", champ=nom, attendu="identifiant")


def champ_octets(donnees: dict, nom: str) -> bytes:
    """Un fichier transporté en base64 (le JSON ne porte pas d'octets)."""
    valeur = champ_texte(donnees, nom)
    try:
        return base64.b64decode(valeur, validate=True)
    except (binascii.Error, ValueError):
        _refuser("api.champ_invalide", champ=nom, attendu="base64")


def parametre_date(requete, nom: str, *, obligatoire: bool = True) -> datetime.date | None:
    return champ_date(requete.query_params, nom, obligatoire=obligatoire)


def parametre_entier(requete, nom: str, *, obligatoire: bool = True) -> int | None:
    brut = requete.query_params.get(nom)
    if brut in (None, ""):
        if obligatoire:
            _refuser("api.champ_obligatoire", champ=nom)
        return None
    try:
        return int(brut)
    except ValueError:
        _refuser("api.champ_invalide", champ=nom, attendu="entier")


def objet_ou_404(modele, **filtres):
    """L'objet, ou 404 : un objet d'une autre organisation est invisible (RLS), donc introuvable."""
    objet = modele.objects.filter(**filtres).first()
    if objet is None:
        raise Http404
    return objet


# --- sortie ------------------------------------------------------------------------------------


def serialiser(valeur: Any) -> Any:
    """Récursif : Decimal, date, UUID → chaîne ; jamais de float."""
    if isinstance(valeur, Decimal):
        return format(valeur, "f")
    if isinstance(valeur, datetime.datetime | datetime.date):
        return valeur.isoformat()
    if isinstance(valeur, uuid.UUID):
        return str(valeur)
    if isinstance(valeur, dict):
        return {str(k): serialiser(v) for k, v in valeur.items()}
    if isinstance(valeur, list | tuple):
        return [serialiser(v) for v in valeur]
    if isinstance(valeur, float):
        raise TypeError("un float ne se sérialise pas dans une API financière")
    return valeur


def projeter(objet, *champs: str, **calcules) -> dict:
    """Les attributs nommés d'un objet (clé étrangère : `x_id`), plus des valeurs calculées."""
    sortie = {}
    for nom in champs:
        valeur = getattr(objet, nom)
        sortie[nom] = valeur
    sortie.update(calcules)
    return serialiser(sortie)


def recharge(objet):
    """L'objet relu en base : un service renvoie ce qu'il a créé, montants tels que saisis ;
    la base les rend à leur précision (quatre décimales)."""
    objet.refresh_from_db()
    return objet


def reponse(donnees: Any, statut: int = 200) -> Response:
    return Response(serialiser(donnees), status=statut)


# --- erreurs -----------------------------------------------------------------------------------

STATUTS = {CodeErreur.TRANSITION_INTERDITE: 409}


def gestionnaire_exceptions(exc, contexte):
    """Les refus métier deviennent `{"code", "message"}` ; le reste suit le gestionnaire de DRF."""
    from niveau1_socle.budget.services import BudgetInvalide
    from niveau1_socle.comptabilite.services import EcritureInvalide, JournalIntrouvable
    from niveau1_socle.exercices.services import TransitionInterdite
    from niveau1_socle.financements.cles import CleInvalide
    from niveau1_socle.financements.cofinancement import VentilationImpossible
    from niveau1_socle.financements.services import AccordNonActif, FinancementInvalide
    from niveau1_socle.rapprochement.services import ReleveInvalide
    from niveau3_config.services.documents import DocumentInvalide
    from niveau4_reporting.moteur.assertions import AssertionsViolees
    from niveau4_reporting.moteur.compilateur import ModeleEtatInvalide
    from niveau4_reporting.moteur.sources_externes import SourceIncomplete

    if isinstance(exc, ErreurMetier):
        return Response(
            {"code": str(exc.code), "message": texte(exc)}, status=STATUTS.get(exc.code, 422)
        )
    if isinstance(exc, TransitionInterdite):
        return Response(
            {"code": CodeErreur.TRANSITION_INTERDITE.value, "message": texte(exc)}, status=409
        )
    if isinstance(
        exc,
        AccordNonActif
        | BudgetInvalide
        | CleInvalide
        | DocumentInvalide
        | FinancementInvalide
        | VentilationImpossible
        | EcritureInvalide
        | JournalIntrouvable
        | ReleveInvalide
        | AssertionsViolees
        | ModeleEtatInvalide
        | SourceIncomplete,
    ):
        return Response(
            {"code": CodeErreur.REGLE_INVALIDE.value, "message": texte(exc)}, status=422
        )
    return exception_handler(exc, contexte)
