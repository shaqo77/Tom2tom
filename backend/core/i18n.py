"""Les messages du système, en plusieurs langues (français et anglais pour l'instant).

QUI VA OÙ, selon les bonnes pratiques :
- les MESSAGES du logiciel (refus, erreurs, textes de documents, libellés d'ensembles fermés)
  sont liés à une VERSION du code : ils vivent dans des catalogues versionnés avec lui
  (`core/locales/<langue>/<domaine>.json`), relus en revue, jamais dans la base ;
- le CONTENU MÉTIER (libellé d'une catégorie, d'un contrôle, d'un profil) est une donnée du
  client : il vit en base, en JSONB multilingue `{"fr": …, "en": …}`.

Un message a une CLÉ STABLE et des paramètres nommés : `msg("activation.statut_attendu", ...)`.
On ne lève jamais de texte en dur et on ne concatène jamais de phrase : la grammaire d'une langue
n'est pas celle d'une autre. La langue est celle de la requête (`LangueMiddleware`), le français
par défaut ; un message lu plus tard (journal, PDF) est rendu dans la langue demandée, ou dans
toutes (`Message.toutes()`) quand il doit être figé à l'écriture.

Sécurité : un gabarit n'accepte que des champs simples (`{nom}` ou `{nom:.2f}`), jamais
`{x.attribut}` ni `{x[0]}` (attaque par chaîne de format) ; le catalogue est validé au chargement
(mêmes clés et mêmes paramètres dans toutes les langues) et par un test d'analyse du code.
"""

import contextlib
import contextvars
import json
import re
import string
from functools import lru_cache
from pathlib import Path

LANGUES = ("fr", "en")
LANGUE_PAR_DEFAUT = "fr"
DOSSIER = Path(__file__).resolve().parent / "locales"
TAILLE_MAX_FICHIER = 1_000_000
_FORMAT_SIMPLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SPEC_SIMPLE = re.compile(r"^[-+ 0-9.,%a-zA-Z<>^=]*$")
_langue = contextvars.ContextVar("langue_active", default=LANGUE_PAR_DEFAUT)


class CatalogueInvalide(ValueError):
    """Un catalogue de messages est incohérent : on refuse de démarrer avec lui."""


# --- gabarits et catalogue -----------------------------------------------------------------


def champs_du_gabarit(gabarit: str) -> set[str]:
    """Les paramètres d'un gabarit ; refuse tout champ qui ne soit pas un nom simple."""
    noms = set()
    try:
        morceaux = list(string.Formatter().parse(gabarit))
    except ValueError as erreur:
        raise CatalogueInvalide(f"gabarit mal formé : {gabarit!r} ({erreur})") from erreur
    for _, champ, spec, conversion in morceaux:
        if champ is None:
            continue
        if not _FORMAT_SIMPLE.match(champ):
            raise CatalogueInvalide(f"champ de gabarit interdit « {{{champ}}} » dans {gabarit!r}")
        if conversion not in (None, "r", "s"):
            raise CatalogueInvalide(f"conversion interdite dans {gabarit!r}")
        if spec and (not _SPEC_SIMPLE.match(spec) or "{" in spec):
            raise CatalogueInvalide(f"format interdit « {spec} » dans {gabarit!r}")
        noms.add(champ)
    return noms


def valider_catalogue(brut: dict[str, dict[str, dict[str, str]]]) -> dict[str, dict[str, str]]:
    """`brut[langue][domaine] = {clé: gabarit}` → `{langue: {clé: gabarit}}`, ou lève.

    Toutes les langues ont les mêmes domaines, les mêmes clés et les mêmes paramètres pour chaque
    clé ; une clé commence par le nom de son domaine ; aucun gabarit n'est vide.
    """
    if set(brut) != set(LANGUES):
        raise CatalogueInvalide(f"langues attendues {sorted(LANGUES)}, trouvées {sorted(brut)}")
    plat: dict[str, dict[str, str]] = {langue: {} for langue in LANGUES}
    for langue, domaines in brut.items():
        for domaine, messages in domaines.items():
            for cle, gabarit in messages.items():
                if not cle.startswith(domaine + "."):
                    raise CatalogueInvalide(
                        f"la clé « {cle} » n'appartient pas au domaine {domaine}"
                    )
                if not isinstance(gabarit, str) or not gabarit.strip():
                    raise CatalogueInvalide(f"la clé « {cle} » ({langue}) n'a pas de texte")
                if cle in plat[langue]:
                    raise CatalogueInvalide(f"la clé « {cle} » est définie deux fois ({langue})")
                champs_du_gabarit(gabarit)
                plat[langue][cle] = gabarit
    reference = plat[LANGUE_PAR_DEFAUT]
    for langue in LANGUES:
        manquantes = set(reference) - set(plat[langue])
        en_trop = set(plat[langue]) - set(reference)
        if manquantes or en_trop:
            raise CatalogueInvalide(
                f"{langue} : clés manquantes {sorted(manquantes)[:5]}, "
                f"clés en trop {sorted(en_trop)[:5]}"
            )
        for cle, gabarit in plat[langue].items():
            if champs_du_gabarit(gabarit) != champs_du_gabarit(reference[cle]):
                raise CatalogueInvalide(
                    f"« {cle} » n'a pas les mêmes paramètres en {langue} et en fr"
                )
    return plat


@lru_cache(maxsize=1)
def catalogue() -> dict[str, dict[str, str]]:
    brut: dict[str, dict[str, dict[str, str]]] = {}
    for langue in LANGUES:
        brut[langue] = {}
        dossier = DOSSIER / langue
        for fichier in sorted(dossier.glob("*.json")):
            if fichier.stat().st_size > TAILLE_MAX_FICHIER:
                raise CatalogueInvalide(f"{fichier.name} dépasse {TAILLE_MAX_FICHIER} octets")
            contenu = json.loads(fichier.read_text(encoding="utf-8"))
            if not isinstance(contenu, dict):
                raise CatalogueInvalide(f"{fichier.name} : un objet JSON est attendu")
            brut[langue][fichier.stem] = contenu
    return valider_catalogue(brut)


# --- la langue active ----------------------------------------------------------------------


def langue_courante() -> str:
    return _langue.get()


def normaliser_langue(valeur: str | None) -> str:
    """`fr`, `en-GB`, `FR_ca`… → une langue gérée, sinon le français."""
    base = (valeur or "").strip().lower().replace("_", "-").split("-")[0]
    return base if base in LANGUES else LANGUE_PAR_DEFAUT


def choisir_langue(accept_language: str | None) -> str:
    """La langue la mieux classée de l'en-tête HTTP `Accept-Language` qui soit gérée."""
    candidates = []
    for position, partie in enumerate((accept_language or "").split(",")[:20]):
        morceaux = partie.strip().split(";")
        etiquette = morceaux[0].strip().lower()
        poids = 1.0
        for parametre in morceaux[1:]:
            nom, _, valeur = parametre.strip().partition("=")
            if nom.strip() == "q":
                try:
                    poids = max(0.0, min(1.0, float(valeur)))
                except ValueError:
                    poids = 0.0
        base = etiquette.split("-")[0]
        if base in LANGUES and poids > 0:
            candidates.append((-poids, position, base))
    return min(candidates)[2] if candidates else LANGUE_PAR_DEFAUT


@contextlib.contextmanager
def activer(langue: str | None):
    """Rend les messages de ce bloc dans `langue` (propre au fil d'exécution, comme au thread)."""
    jeton = _langue.set(normaliser_langue(langue))
    try:
        yield
    finally:
        _langue.reset(jeton)


# --- les messages --------------------------------------------------------------------------


class Message:
    """Un message identifié par une clé stable, avec ses paramètres, rendu à la demande."""

    __slots__ = ("cle", "params")

    def __init__(self, cle: str, params: dict | None = None):
        self.cle = cle
        self.params = dict(params or {})

    def rendre(self, langue: str | None = None) -> str:
        langue = normaliser_langue(langue) if langue else langue_courante()
        gabarit = catalogue()[langue].get(self.cle) or catalogue()[LANGUE_PAR_DEFAUT][self.cle]
        # Un message passé en paramètre se rend dans LA MÊME langue que son parent.
        params = {
            nom: valeur.rendre(langue) if isinstance(valeur, Message) else valeur
            for nom, valeur in self.params.items()
        }
        return gabarit.format_map(params)

    def toutes(self) -> dict[str, str]:
        """Le message dans CHAQUE langue : pour ce qui se fige à l'écriture (journal)."""
        return {langue: self.rendre(langue) for langue in LANGUES}

    def __str__(self) -> str:
        return self.rendre()

    def __repr__(self) -> str:
        return f"Message({self.cle!r}, {self.params!r})"

    def __eq__(self, autre) -> bool:
        return isinstance(autre, Message) and (self.cle, self.params) == (autre.cle, autre.params)

    def __hash__(self) -> int:
        return hash(self.cle)

    def __reduce__(self):
        return (Message, (self.cle, self.params))


class Liste(Message):
    """Une liste de messages (ou de textes), rendue dans UNE langue puis assemblée : on n'assemble
    jamais des textes déjà rendus, la ponctuation d'une langue n'étant pas celle d'une autre."""

    __slots__ = ("elements", "separateur")

    def __init__(self, elements, separateur: str = " ; "):
        super().__init__("", {})
        self.elements = list(elements)
        self.separateur = separateur

    def rendre(self, langue: str | None = None) -> str:
        langue = normaliser_langue(langue) if langue else langue_courante()
        return self.separateur.join(texte(e, langue) for e in self.elements)

    def __repr__(self) -> str:
        return f"Liste({self.elements!r})"

    def __eq__(self, autre) -> bool:
        return isinstance(autre, Liste) and (self.elements, self.separateur) == (
            autre.elements,
            autre.separateur,
        )

    def __hash__(self) -> int:
        return hash(("liste", self.separateur, len(self.elements)))

    def __reduce__(self):
        return (Liste, (self.elements, self.separateur))


def msg(cle: str, **params) -> Message:
    """Un message du catalogue. Échoue TOUT DE SUITE si la clé est inconnue ou si les paramètres
    ne sont pas exactement ceux du gabarit : une faute de frappe se voit au premier test."""
    gabarit = catalogue()[LANGUE_PAR_DEFAUT].get(cle)
    if gabarit is None:
        raise KeyError(f"message inconnu : « {cle} »")
    attendus = champs_du_gabarit(gabarit)
    if set(params) != attendus:
        raise KeyError(
            f"« {cle} » attend les paramètres {sorted(attendus)}, reçoit {sorted(params)}"
        )
    return Message(cle, params)


def texte(objet, langue: str | None = None) -> str:
    """Le texte d'un message ou d'une exception, dans `langue` (sinon la langue active)."""
    if isinstance(objet, BaseException):
        objet = objet.args[0] if objet.args else ""
    return objet.rendre(langue) if isinstance(objet, Message) else str(objet)


def textes(objet) -> dict[str, str]:
    """Le texte dans chaque langue ; un texte brut (non catalogué) est le même partout."""
    if isinstance(objet, BaseException):
        objet = objet.args[0] if objet.args else ""
    if isinstance(objet, Message):
        return objet.toutes()
    return {langue: str(objet) for langue in LANGUES}


def libelle(famille: str, valeur: str, langue: str | None = None) -> str:
    """Le libellé d'une valeur d'ensemble fermé (`enum.<famille>.<valeur>`), sinon la valeur."""
    cle = f"enum.{famille}.{valeur}"
    return Message(cle).rendre(langue) if cle in catalogue()[LANGUE_PAR_DEFAUT] else str(valeur)
