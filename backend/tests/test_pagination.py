"""Pagination optionnelle des listes (Lot 2-B) : `?limite=` et `?decalage=`, état en en-têtes.

Le corps reste un tableau JSON, donc le frontend existant ne change pas. Sans `limite`, la liste
est rendue en entier jusqu'à 500 lignes ; au-delà, un refus demande de paginer.
"""

import pytest
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from core.erreurs import ErreurMetier
from core.pagination import PLAFOND, paginer


def _requete(**query):
    brut = APIRequestFactory().get("/x/", query)
    return APIView().initialize_request(brut)


class _Ordonnee(list):
    """Un faux queryset trié : `ordered`, `count()` et le découpage."""

    ordered = True

    def count(self):  # noqa: A003 - même signature que QuerySet.count
        return len(self)


class _NonOrdonnee(_Ordonnee):
    ordered = False


def test_sans_limite_la_liste_est_rendue_en_entier_avec_son_total():
    liste, entetes = paginer(_Ordonnee(range(30)), _requete())
    assert liste == list(range(30))
    assert entetes == {"X-Total-Count": "30"}


def test_une_limite_rend_la_premiere_tranche_et_annonce_la_suite():
    liste, entetes = paginer(_Ordonnee(range(30)), _requete(limite=10))
    assert liste == list(range(10))
    assert entetes == {"X-Total-Count": "30", "X-Decalage-Suivant": "10"}


def test_un_decalage_rend_la_tranche_suivante():
    liste, entetes = paginer(_Ordonnee(range(30)), _requete(limite=10, decalage=20))
    assert liste == list(range(20, 30))
    assert entetes == {"X-Total-Count": "30"}  # dernière tranche : pas de suite


def test_un_decalage_au_dela_de_la_fin_rend_une_liste_vide():
    liste, entetes = paginer(_Ordonnee(range(5)), _requete(limite=10, decalage=50))
    assert liste == []
    assert entetes == {"X-Total-Count": "5"}


def test_une_tranche_exactement_pleine_en_fin_de_liste_n_annonce_pas_de_suite():
    _, entetes = paginer(_Ordonnee(range(20)), _requete(limite=10, decalage=10))
    assert "X-Decalage-Suivant" not in entetes


@pytest.mark.parametrize(
    "parametres",
    [
        {"limite": 0},
        {"limite": -5},
        {"limite": PLAFOND + 1},
        {"limite": "abc"},
        {"limite": "1.5"},
        {"decalage": -1},
        {"decalage": "x"},
        {"limite": 10, "decalage": "2.0"},
    ],
)
def test_un_parametre_invalide_est_refuse(parametres):
    with pytest.raises(ErreurMetier):
        paginer(_Ordonnee(range(30)), _requete(**parametres))


def test_au_dela_du_plafond_sans_limite_un_refus_demande_de_paginer():
    with pytest.raises(ErreurMetier) as exc:
        paginer(_Ordonnee(range(PLAFOND + 1)), _requete())
    assert "limite" in str(exc.value.args[0].rendre("fr"))


def test_exactement_le_plafond_sans_limite_passe():
    liste, entetes = paginer(_Ordonnee(range(PLAFOND)), _requete())
    assert len(liste) == PLAFOND and entetes["X-Total-Count"] == str(PLAFOND)


def test_une_liste_non_triee_est_refusee_car_la_pagination_serait_instable():
    with pytest.raises(TypeError):
        paginer(_NonOrdonnee(range(5)), _requete(limite=2))


def test_une_liste_python_ordinaire_se_pagine_aussi():
    liste, entetes = paginer(list(range(7)), _requete(limite=3, decalage=3))
    assert liste == [3, 4, 5]
    assert entetes == {"X-Total-Count": "7", "X-Decalage-Suivant": "6"}
