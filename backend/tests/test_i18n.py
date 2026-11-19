"""Les messages en plusieurs langues : catalogue, langue de la requête, rendu (logique pure)."""

import pickle
import threading
from decimal import Decimal

import pytest

from core import i18n
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import (
    CatalogueInvalide,
    activer,
    catalogue,
    champs_du_gabarit,
    choisir_langue,
    langue_courante,
    libelle,
    msg,
    normaliser_langue,
    texte,
    textes,
    valider_catalogue,
)

VALIDE = {
    "fr": {"d": {"d.a": "Bonjour {nom}", "d.b": "Total {n:.2f}"}},
    "en": {"d": {"d.a": "Hello {nom}", "d.b": "Total {n:.2f}"}},
}


def variante(langue, domaine, cle, gabarit):
    copie = {lg: {d: dict(m) for d, m in ds.items()} for lg, ds in VALIDE.items()}
    copie[langue][domaine][cle] = gabarit
    return copie


# --- le catalogue --------------------------------------------------------------------------


def test_le_catalogue_reel_est_valide_et_complet_dans_les_deux_langues():
    cat = catalogue()
    assert set(cat) == {"fr", "en"} and cat["fr"].keys() == cat["en"].keys()
    assert "erreur.exemple" in cat["fr"]


def test_un_catalogue_valide_est_accepte():
    plat = valider_catalogue(VALIDE)
    assert plat["fr"]["d.a"] == "Bonjour {nom}" and plat["en"]["d.a"] == "Hello {nom}"


@pytest.mark.parametrize(
    "brut, message",
    [
        ({"fr": VALIDE["fr"]}, "langues attendues"),
        ({**VALIDE, "de": {}}, "langues attendues"),
        (variante("en", "d", "d.a", "Hello"), "paramètres"),
        (variante("en", "d", "d.a", "Hello {autre}"), "paramètres"),
        (variante("fr", "d", "d.c", "Texte"), "clés"),
        (variante("en", "d", "d.c", "Text"), "clés"),
        (variante("fr", "d", "autre.a", "Texte"), "n'appartient pas au domaine"),
        (variante("fr", "d", "d.vide", "   "), "n'a pas de texte"),
        (variante("fr", "d", "d.nul", None), "n'a pas de texte"),
        (variante("fr", "d", "d.x", "Valeur {a.b}"), "interdit"),
        (variante("fr", "d", "d.x", "Valeur {a[0]}"), "interdit"),
        (variante("fr", "d", "d.x", "Valeur {0}"), "interdit"),
        (variante("fr", "d", "d.x", "Valeur {}"), "interdit"),
        (variante("fr", "d", "d.x", "Valeur {a!a}"), "conversion"),
        (variante("fr", "d", "d.x", "Valeur {a:{b}}"), "interdit"),
        (variante("fr", "d", "d.x", "Valeur {a"), "mal formé"),
    ],
)
def test_un_catalogue_incoherent_est_refuse(brut, message):
    with pytest.raises(CatalogueInvalide, match=message):
        valider_catalogue(brut)


def test_une_cle_en_double_dans_une_langue_est_refusee():
    brut = {lg: {d: dict(m) for d, m in ds.items()} for lg, ds in VALIDE.items()}
    brut["fr"]["e"] = {"e.z": "Z"}
    brut["en"]["e"] = {"e.z": "Z"}
    brut["fr"]["f"] = {"d.a": "Autre"}  # même clé « d.a » sous un autre domaine : refusée
    brut["en"]["f"] = {"d.a": "Other"}
    with pytest.raises(CatalogueInvalide):
        valider_catalogue(brut)


@pytest.mark.parametrize("gabarit", ["{nom}", "{n:.2f}", "{n:>8}", "{nom!r}", "{a} et {b}"])
def test_les_gabarits_simples_sont_acceptes(gabarit):
    assert champs_du_gabarit(gabarit)


# --- les messages --------------------------------------------------------------------------


def test_un_message_se_rend_dans_la_langue_active_francais_par_defaut():
    message = msg("erreur.exemple", nom="Alpha", n=Decimal("12.5"))
    assert langue_courante() == "fr"
    assert str(message) == "Le projet Alpha compte 12.50 unités"
    with activer("en"):
        assert langue_courante() == "en"
        assert str(message) == "Project Alpha has 12.50 units"
    assert langue_courante() == "fr"  # la langue précédente est rétablie


def test_un_message_se_rend_aussi_dans_une_langue_explicite_ou_dans_toutes():
    message = msg("erreur.exemple", nom="A", n=Decimal("1"))
    assert message.rendre("en") == "Project A has 1.00 units"
    assert message.rendre("EN-gb") == "Project A has 1.00 units"
    assert message.rendre("xx") == "Le projet A compte 1.00 unités"  # langue inconnue : français
    assert message.toutes() == {
        "fr": "Le projet A compte 1.00 unités",
        "en": "Project A has 1.00 units",
    }


def test_une_cle_inconnue_ou_des_parametres_faux_echouent_tout_de_suite():
    with pytest.raises(KeyError, match="inconnu"):
        msg("erreur.n_existe_pas")
    with pytest.raises(KeyError, match="attend les paramètres"):
        msg("erreur.exemple", nom="A")
    with pytest.raises(KeyError, match="attend les paramètres"):
        msg("erreur.exemple", nom="A", n=1, en_trop=2)


def test_une_valeur_de_parametre_n_est_jamais_interpretee_comme_un_gabarit():
    piege = "{__class__} {0} {nom.__init__}"
    assert (
        str(msg("erreur.exemple", nom=piege, n=Decimal("1")))
        == f"Le projet {piege} compte 1.00 unités"
    )


def test_un_message_est_comparable_hachable_et_se_serialise():
    a, b = msg("erreur.inconnue"), msg("erreur.inconnue")
    assert a == b and hash(a) == hash(b) and a != msg("erreur.exemple", nom="x", n=1)
    assert pickle.loads(pickle.dumps(msg("erreur.exemple", nom="x", n=1))) == msg(
        "erreur.exemple", nom="x", n=1
    )
    assert "erreur.inconnue" in repr(a)


def test_texte_et_textes_lisent_un_message_une_exception_ou_un_texte_brut():
    message = msg("erreur.inconnue")
    assert (
        texte(message) == "Une erreur est survenue" and texte(message, "en") == "An error occurred"
    )
    erreur = ValueError(message)
    assert texte(erreur, "en") == "An error occurred" and str(erreur) == "Une erreur est survenue"
    assert textes(erreur) == {"fr": "Une erreur est survenue", "en": "An error occurred"}
    assert texte("brut") == "brut" and textes("brut") == {"fr": "brut", "en": "brut"}
    assert texte(ValueError()) == "" and textes(ValueError()) == {"fr": "", "en": ""}


def test_un_libelle_d_ensemble_ferme_retombe_sur_la_valeur_si_inconnu():
    assert libelle("famille_inconnue", "x") == "x"


# --- la langue de la requête ---------------------------------------------------------------


@pytest.mark.parametrize(
    "valeur, attendu",
    [("fr", "fr"), ("en", "en"), ("EN", "en"), ("en-GB", "en"), ("fr_CA", "fr"), ("ar", "fr"),
     ("", "fr"), (None, "fr"), ("  en ", "en"), ("xx-YY", "fr")],
)  # fmt: skip
def test_normaliser_langue(valeur, attendu):
    assert normaliser_langue(valeur) == attendu


@pytest.mark.parametrize(
    "entete, attendu",
    [
        ("en", "en"), ("fr", "fr"), ("", "fr"), (None, "fr"),
        ("en-US,en;q=0.9,fr;q=0.8", "en"),
        ("fr;q=0.5,en;q=0.9", "en"),
        ("de,es;q=0.8", "fr"),  # aucune langue gérée : le défaut
        ("de,en;q=0.2", "en"),
        ("en;q=0,fr;q=0.1", "fr"),  # q=0 : refusée
        ("en;q=abc,fr", "fr"),  # poids illisible : écarté
        ("fr-CA,en", "fr"),
        ("*", "fr"),
    ],
)  # fmt: skip
def test_choisir_langue_suit_les_poids_de_l_en_tete_accept_language(entete, attendu):
    assert choisir_langue(entete) == attendu


def test_la_langue_active_est_propre_a_chaque_fil_d_execution():
    resultats = {}

    def travailler(nom, langue):
        with activer(langue):
            barriere.wait()  # les deux fils sont dans leur bloc en même temps
            resultats[nom] = (langue_courante(), str(msg("erreur.inconnue")))

    barriere = threading.Barrier(2)
    fils = [
        threading.Thread(target=travailler, args=("a", "en")),
        threading.Thread(target=travailler, args=("b", "fr")),
    ]
    [f.start() for f in fils]
    [f.join() for f in fils]
    assert resultats == {"a": ("en", "An error occurred"), "b": ("fr", "Une erreur est survenue")}
    assert langue_courante() == "fr"


def test_la_langue_est_retablie_meme_si_le_bloc_leve():
    with pytest.raises(RuntimeError):
        with activer("en"):
            raise RuntimeError("boum")
    assert langue_courante() == "fr"


# --- les erreurs métier --------------------------------------------------------------------


def test_une_erreur_metier_porte_un_code_stable_et_un_message_dans_la_langue_active():
    erreur = ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("erreur.inconnue"))
    assert erreur.code is CodeErreur.REGLE_INVALIDE
    assert erreur.message == "Une erreur est survenue"
    with activer("en"):
        assert erreur.message == "An error occurred"
        assert erreur.vers_dict() == {"code": "REGLE_INVALIDE", "message": "An error occurred"}
    assert erreur.vers_dict("en")["message"] == "An error occurred"
    assert erreur.vers_dict("fr")["message"] == "Une erreur est survenue"
    brute = ErreurMetier(CodeErreur.TRANSITION_INTERDITE, "Texte brut")
    assert brute.message == "Texte brut" and brute.vers_dict("en")["message"] == "Texte brut"


def test_les_codes_d_erreur_restent_les_douze_du_plan():
    assert len(list(CodeErreur)) == 12
    with pytest.raises(ValueError):
        ErreurMetier("CODE_INCONNU", "x")


def test_les_langues_gerees_sont_le_francais_et_l_anglais_pour_l_instant():
    assert i18n.LANGUES == ("fr", "en") and i18n.LANGUE_PAR_DEFAUT == "fr"


# --- les libellés des ensembles fermés ------------------------------------------------------


def test_chaque_ensemble_ferme_a_ses_libelles_dans_les_deux_langues():
    """Aucune `TextChoices` du code n'est sans libellé : un statut sans traduction se verrait."""
    import importlib
    import inspect

    from django.apps import apps
    from django.db import models

    from core.i18n import famille_de

    attendues = set()
    for config in apps.get_app_configs():
        if not config.name.startswith(("niveau", "core")):
            continue
        module = importlib.import_module(config.name + ".models")
        for _, classe in vars(module).items():
            if (
                inspect.isclass(classe)
                and issubclass(classe, models.TextChoices)
                and classe is not models.TextChoices
                and classe.__module__ == module.__name__
            ):
                attendues |= {f"enum.{famille_de(classe)}.{m.value}" for m in classe}
    assert len(attendues) > 150
    for langue in ("fr", "en"):
        manquantes = attendues - set(catalogue()[langue])
        assert not manquantes, f"{langue} : libellés manquants {sorted(manquantes)[:5]}"
    # Aucun libellé orphelin : hors ensembles « non classe » (operation, piece_exigee).
    orphelins = {
        c
        for c in catalogue()["fr"]
        if c.startswith("enum.")
        and c not in attendues
        and not c.startswith(("enum.operation.", "enum.piece_exigee."))
    }
    assert not orphelins, sorted(orphelins)[:5]


def test_libelle_valeur_rend_le_libelle_dans_la_langue_demandee():
    from core.i18n import libelle_valeur
    from niveau3_config.models import StatutExigence

    assert libelle_valeur(StatutExigence, "proposed") == "Proposée"
    assert libelle_valeur(StatutExigence, "proposed", "en") == "Proposed"
    with activer("en"):
        assert libelle_valeur(StatutExigence, StatutExigence.ACTIVE) == "Active"
    assert (
        libelle_valeur(StatutExigence, "inconnu") == "inconnu"
    )  # une valeur inconnue : telle quelle


# --- messages composés : listes, textes multilingues, messages imbriqués ---------------------


def test_un_message_imbrique_se_rend_dans_la_meme_langue_que_son_parent():
    from core.i18n import Liste, Localise

    interieur = msg("erreur.inconnue")
    parent = msg("erreur.exemple", nom=interieur, n=Decimal("1"))
    assert str(parent) == "Le projet Une erreur est survenue compte 1.00 unités"
    assert parent.rendre("en") == "Project An error occurred has 1.00 units"  # PAS « Une erreur… »
    liste = Liste([msg("erreur.inconnue"), "brut", Localise({"fr": "texte", "en": "text"})])
    assert liste.rendre("fr") == "Une erreur est survenue ; brut ; texte"
    assert liste.rendre("en") == "An error occurred ; brut ; text"
    assert Liste([msg("erreur.inconnue")], " | ").toutes() == {
        "fr": "Une erreur est survenue",
        "en": "An error occurred",
    }
    with activer("en"):
        assert str(liste) == "An error occurred ; brut ; text"


def test_un_texte_localise_retombe_sur_le_francais_puis_sur_la_premiere_langue():
    from core.i18n import Localise

    assert Localise({"fr": "bonjour", "en": "hello"}).rendre("en") == "hello"
    assert Localise({"fr": "bonjour"}).rendre("en") == "bonjour"  # pas de traduction : le français
    assert Localise({"en": "hello"}).rendre("fr") == "hello"  # ni français : la première langue
    assert Localise({}).rendre("fr") == "" and Localise("brut").rendre("en") == "brut"
    assert Localise({"fr": "a"}) == Localise({"fr": "a"}) and hash(Localise({"fr": "a"}))
    assert pickle.loads(pickle.dumps(Localise({"fr": "a"}))) == Localise({"fr": "a"})


def test_une_liste_est_comparable_et_se_serialise():
    from core.i18n import Liste

    a = Liste([msg("erreur.inconnue")], "; ")
    assert a == Liste([msg("erreur.inconnue")], "; ") and a != Liste([], "; ") and hash(a)
    assert pickle.loads(pickle.dumps(a)) == a and "Liste" in repr(a)


# --- formats propres à chaque langue --------------------------------------------------------


def test_les_dates_les_montants_et_les_pourcentages_suivent_la_langue():
    import datetime

    from core.i18n import formater_date, formater_montant, formater_pourcentage

    jour = datetime.date(2026, 11, 4)
    assert formater_date(jour, "fr") == "04/11/2026"
    assert formater_date(jour, "en") == "4 November 2026"
    assert formater_montant(Decimal("1234567.5"), "fr") == "1 234 567,50"
    assert formater_montant(Decimal("1234567.5"), "en") == "1,234,567.50"
    assert (
        formater_montant(Decimal("0"), "fr") == "0,00"
        and formater_montant(Decimal("-12.3"), "en") == "-12.30"
    )
    assert formater_pourcentage(Decimal("0.800000"), "fr") == "80 %"
    assert formater_pourcentage(Decimal("0.8"), "en") == "80%"
    assert formater_pourcentage(Decimal("0.125"), "fr") == "12,5 %"
    with activer("en"):
        assert (
            formater_date(jour) == "4 November 2026"
            and formater_montant(Decimal("1000")) == "1,000.00"
        )


def test_normaliser_textes_accepte_les_langues_gerees_seulement():
    from core.i18n import normaliser_textes

    assert normaliser_textes({"fr": " a ", "en": "b"}) == {"fr": "a", "en": "b"}
    assert normaliser_textes("simple") == {"fr": "simple"}
    assert (
        normaliser_textes(None) == {}
        and normaliser_textes("") == {}
        and normaliser_textes("  ") == {}
    )
    assert normaliser_textes({"fr": "a", "en": "  "}) == {"fr": "a"}  # un texte vide est ignoré
    assert normaliser_textes({"fr": "a"}, obligatoire=True) == {"fr": "a"}
    for faux, message in [
        ({"de": "x"}, "langues non gérées"),
        ({"fr": 3}, "chaîne"),
        (["x"], "objet"),
        ({"en": "x"}, "obligatoire") if False else (None, None),
    ]:
        if message:
            with pytest.raises(ValueError, match=message):
                normaliser_textes(faux)
    for vide in ({"en": "only"}, None, "", "  ", {"fr": " "}):
        with pytest.raises(ValueError, match="obligatoire"):
            normaliser_textes(vide, obligatoire=True)
