"""La langue de la requête : celle de l'utilisateur, sinon Accept-Language, sinon le français."""

from django.http import HttpResponse
from django.test import RequestFactory
from django.utils import translation

from core.i18n import langue_courante, msg
from core.middleware import LangueMiddleware


class _Utilisateur:
    def __init__(self, langue=None, connecte=True):
        self.langue = langue
        self.is_authenticated = connecte


def _servir(utilisateur=None, accept=None, leve=False):
    vu = {}

    def vue(requete):
        vu["langue"] = langue_courante()
        vu["django"] = translation.get_language()
        vu["message"] = str(msg("erreur.inconnue"))
        if leve:
            raise RuntimeError("boum")
        return HttpResponse()

    requete = RequestFactory().get(
        "/", **({"headers": {"Accept-Language": accept}} if accept else {})
    )
    if utilisateur is not None:
        requete.user = utilisateur
    try:
        reponse = LangueMiddleware(vue)(requete)
    except RuntimeError:
        reponse = None
    return vu, reponse, requete


def test_sans_utilisateur_ni_en_tete_c_est_le_francais():
    vu, reponse, requete = _servir()
    assert (vu["langue"], vu["message"]) == ("fr", "Une erreur est survenue")
    assert reponse["Content-Language"] == "fr" and requete.LANGUE_CODE == "fr"


def test_l_en_tete_accept_language_choisit_la_langue_d_un_visiteur():
    vu, reponse, _ = _servir(accept="en-US,en;q=0.9,fr;q=0.5")
    assert (vu["langue"], vu["message"]) == ("en", "An error occurred")
    assert reponse["Content-Language"] == "en"


def test_la_langue_d_un_utilisateur_connecte_l_emporte_sur_l_en_tete():
    vu, _, _ = _servir(_Utilisateur("en"), accept="fr")
    assert vu["langue"] == "en"
    vu, _, _ = _servir(_Utilisateur("fr"), accept="en")
    assert vu["langue"] == "fr"


def test_un_utilisateur_sans_preference_ou_anonyme_retombe_sur_l_en_tete():
    vu, _, _ = _servir(_Utilisateur(None), accept="en")
    assert vu["langue"] == "en"
    vu, _, _ = _servir(_Utilisateur("en", connecte=False), accept="fr")
    assert vu["langue"] == "fr"  # un anonyme n'a pas de préférence : ce qu'il demande fait foi


def test_une_langue_non_geree_donne_le_francais():
    assert _servir(_Utilisateur("ar"))[0]["langue"] == "fr"
    assert _servir(accept="de,es")[0]["langue"] == "fr"


def test_django_et_drf_suivent_la_meme_langue():
    vu, _, _ = _servir(accept="en")
    assert vu["django"] == "en"


def test_la_langue_est_retablie_apres_la_requete_meme_si_la_vue_leve():
    _servir(accept="en")
    assert langue_courante() == "fr"
    vu, reponse, _ = _servir(accept="en", leve=True)
    assert vu["langue"] == "en" and reponse is None
    assert langue_courante() == "fr"  # rien ne déborde sur la requête suivante du même fil
    assert translation.get_language() != "en" or translation.get_language() == "fr"


def test_un_en_tete_pathologique_ne_fait_rien_planter():
    for entete in ("," * 500, "en;q=" + "9" * 100, ";;;;", "en;q=-1", "  "):
        assert _servir(accept=entete)[0]["langue"] in ("fr", "en")
