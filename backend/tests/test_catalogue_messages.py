"""Les catalogues de messages tiennent leurs promesses. (logique pure : analyse du code)

- chaque `msg("clé", …)` du code vise une clé qui existe, avec exactement ses paramètres ;
- chaque clé du catalogue est utilisée (pas de message mort), sauf les libellés d'ensembles fermés
  (`enum.*`), lus par `libelle()` ;
- chaque texte est traduit : l'anglais n'est jamais le français recopié ;
- aucun `raise` du code de production ne porte plus un texte français en dur.
"""

import ast
import re
from pathlib import Path

import pytest

from core.i18n import LANGUES, catalogue, champs_du_gabarit

RACINE = Path(__file__).resolve().parent.parent
DOSSIERS = ("core", "niveau1_socle", "niveau2_profils", "niveau3_config", "niveau4_reporting")
# Un texte peut légitimement être identique dans les deux langues (code, nom propre, format).
IDENTIQUES_ADMIS = {
    "erreur.exemple",
    "controles.en_attente_ligne",
    "rattachement.orphelin",
}
# Les erreurs de programmation ne se traduisent pas : elles s'adressent à qui écrit le code.
ERREURS_DE_PROGRAMMATION = {
    "TypeError", "AssertionError", "NotImplementedError", "KeyError", "AttributeError",
    "RuntimeError", "ImportError", "ImproperlyConfigured", "LookupError", "CatalogueInvalide",
}  # fmt: skip
FRANCAIS = re.compile(
    r"[éèàêçùôîâû]|\b(le|la|les|un|une|des|est|sont|pas|ne|du|de|pour|au|aux|sur|dans|doit)\b", re.I
)
# Les fichiers qui définissent le mécanisme lui-même, ou qui s'adressent à l'exploitation.
EXEMPTES = {"core/i18n.py", "core/checks.py"}


def _sources():
    for dossier in DOSSIERS:
        for fichier in sorted((RACINE / dossier).rglob("*.py")):
            relatif = fichier.relative_to(RACINE).as_posix()
            if "/migrations/" in relatif or relatif in EXEMPTES:
                continue
            yield relatif, ast.parse(fichier.read_text(encoding="utf-8"))


def _appels_msg():
    for relatif, arbre in _sources():
        for noeud in ast.walk(arbre):
            if (
                isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Name)
                and noeud.func.id == "msg"
                and noeud.args
                and isinstance(noeud.args[0], ast.Constant)
            ):
                yield relatif, noeud.lineno, noeud.args[0].value, {k.arg for k in noeud.keywords}


def test_chaque_appel_a_msg_vise_une_cle_qui_existe_avec_ses_parametres():
    francais = catalogue()["fr"]
    fautes = []
    appels = list(_appels_msg())
    assert len(appels) > 300  # l'analyse voit bien le code
    for relatif, ligne, cle, params in appels:
        if cle not in francais:
            fautes.append(f"{relatif}:{ligne} clé inconnue {cle}")
        elif params != champs_du_gabarit(francais[cle]):
            fautes.append(
                f"{relatif}:{ligne} {cle} attend {sorted(champs_du_gabarit(francais[cle]))}"
            )
    assert not fautes, fautes


def test_aucun_message_mort_dans_le_catalogue():
    utilisees = {cle for _, _, cle, _ in _appels_msg()}
    # Les clés construites autrement qu'en littéral (ex. une clé choisie par une condition) :
    for _, arbre in _sources():
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
                if re.fullmatch(r"[a-z_0-9]+\.[a-z_0-9]+", noeud.value):
                    utilisees.add(noeud.value)
    mortes = [
        cle
        for cle in catalogue()["fr"]
        if not cle.startswith("enum.") and cle not in utilisees and cle != "erreur.inconnue"
    ]
    # `erreur.inconnue` et `erreur.exemple` servent aux tests du mécanisme.
    assert not [c for c in mortes if c != "erreur.exemple"], mortes


@pytest.mark.parametrize("langue", [lg for lg in LANGUES if lg != "fr"])
def test_chaque_texte_est_traduit(langue):
    francais, autre = catalogue()["fr"], catalogue()[langue]
    recopies = [c for c in francais if francais[c] == autre[c] and c not in IDENTIQUES_ADMIS]
    assert not recopies, f"{langue} : textes non traduits {recopies}"


def test_les_traductions_anglaises_ne_contiennent_pas_de_francais_evident():
    suspects = []
    for cle, texte in catalogue()["en"].items():
        sans_parametres = re.sub(r"\{[^}]*\}", " ", texte)
        if re.search(r"[éèàêçùôîâû]", sans_parametres) and cle not in IDENTIQUES_ADMIS:
            suspects.append((cle, texte[:60]))
    # Quelques signes typographiques ou unités non anglais sont admis (≠, ≤, —) : pas d'accent.
    assert not suspects, suspects


def test_aucun_raise_de_production_ne_porte_un_texte_francais_en_dur():
    fautes = []
    for relatif, arbre in _sources():
        for noeud in ast.walk(arbre):
            if not (isinstance(noeud, ast.Raise) and isinstance(noeud.exc, ast.Call)):
                continue
            classe = ast.unparse(noeud.exc.func).split(".")[-1]
            if classe in ERREURS_DE_PROGRAMMATION:
                continue
            for argument in noeud.exc.args:
                if isinstance(argument, ast.Constant | ast.JoinedStr):
                    texte = (
                        argument.value
                        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
                        else "".join(
                            v.value
                            for v in getattr(argument, "values", [])
                            if isinstance(v, ast.Constant)
                        )
                    )
                    if texte and FRANCAIS.search(re.sub(r"\{[^}]*\}", " ", texte)):
                        fautes.append(f"{relatif}:{noeud.lineno} {texte[:50]!r}")
    assert not fautes, f"texte français en dur dans un raise : {fautes}"


def test_chaque_fichier_de_catalogue_porte_le_nom_de_son_domaine():
    for langue in LANGUES:
        for fichier in (RACINE / "core" / "locales" / langue).glob("*.json"):
            domaine = fichier.stem
            assert all(
                c.startswith(domaine + ".")
                for c in catalogue()[langue]
                if c.startswith(domaine + ".")
            )
    # Les deux langues ont les mêmes fichiers.
    assert sorted(p.name for p in (RACINE / "core/locales/fr").glob("*.json")) == sorted(
        p.name for p in (RACINE / "core/locales/en").glob("*.json")
    )
