# ruff: noqa: F811
"""Corrections de la revue de code du lot L10 (tableau de bord).

Chaque test échoue avant le correctif.
"""

import datetime
import re
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from niveau1_socle.financements.services import creer_avenant
from niveau4_reporting.controles.models import EvaluationControle
from niveau4_reporting.controles.services import (
    activer_controle,
    installer_bibliotheque,
    valider_controle,
)
from niveau4_reporting.tableau_de_bord import (
    Filtres,
    detail_indicateur,
    ecritures_du_detail,
    tableau_de_bord,
)
from tests.test_api_marches_bd import appeler
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import _document, cadre  # noqa: F401
from tests.test_tableau_de_bord_bd import JOUR, _poser, parc  # noqa: F401
from tests.test_tresorerie_bd import banque  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
J = datetime.date
D = Decimal


def _tdb(parc, jour=JOUR, **champs):
    organisation, _, _, _, _, profils, _ = parc
    _poser(organisation)
    return tableau_de_bord(utilisateur=profils["amina"], jour=jour, filtres=Filtres(**champs))


def test_le_montant_d_un_accord_est_celui_de_la_date_du_tableau_pas_celui_d_aujourd_hui(parc):
    organisation, p1, p2, _, _, profils, _ = parc
    from niveau1_socle.financements.models import Accord

    _poser(organisation)
    accord = Accord.objects.get(project_id=p2.id, numero="A-EUR")
    creer_avenant(
        utilisateur=profils["dora"], accord=accord, reference="AV-X", date_avenant=J(2026, 9, 1),
        document=_document(organisation, p2), montant_revise="600000", motif="Plus",
        profile_version_id=uuid.uuid4(),
    )  # fmt: skip
    avant = _tdb(parc, jour=J(2026, 6, 30)).indicateurs["financements_accordes"]
    apres = _tdb(parc, jour=J(2026, 10, 1)).indicateurs["financements_accordes"]
    assert avant.par_projet[p2.id] == {
        "EUR": D("500000")
    }  # l'avenant du 01/09 n'existe pas au 30/06
    assert apres.par_projet[p2.id] == {"EUR": D("600000")}
    detail = detail_indicateur(
        utilisateur=profils["amina"], code="financements_accordes", project_id=p2.id,
        jour=J(2026, 6, 30),
    )  # fmt: skip
    assert [d.montant for d in detail] == [D("500000")]


def test_un_financement_recu_apres_la_date_du_tableau_n_y_est_pas_compte(parc):
    avant_le_virement = _tdb(parc, jour=J(2026, 2, 1)).indicateurs["financements_recus"]
    assert avant_le_virement.total == {}  # le mouvement apparié est du 20/02
    assert _tdb(parc, jour=J(2026, 3, 1)).indicateurs["financements_recus"].total == {
        "DJF": D("300")
    }


def test_la_descente_d_un_solde_de_releve_ne_propose_pas_les_ecritures_du_grand_livre(parc):
    organisation, p1, _, _, _, profils, _ = parc
    _poser(organisation)
    comptes = detail_indicateur(
        utilisateur=profils["amina"], code="soldes_releves", project_id=p1.id, jour=JOUR
    )
    assert comptes, "le scénario enregistre un solde de relevé sur P1"
    for c in comptes:
        assert c.a_une_ecriture is False and c.type == "compte_releve"
        assert (
            ecritures_du_detail(utilisateur=profils["amina"], detail=c, project_id=p1.id, jour=JOUR)
            == []
        )


def test_seuls_les_objets_en_anomalie_sont_examines_un_par_un(parc, monkeypatch):
    organisation, p1, _, _, _, profils, _ = parc
    from niveau4_reporting.tableau_de_bord import conformite

    _poser(organisation)
    installes = installer_bibliotheque(
        utilisateur=profils["dora"], project_id=p1.id, valid_from=J(2026, 1, 1), codes=["AVA-DELAI"]
    )
    controle = installes.crees[0]
    valider_controle(utilisateur=profils["bruno"], controle=controle)
    activer_controle(utilisateur=profils["dora"], controle=controle)
    for resultat in ("reussi",) * 3 + ("bloquant",):
        EvaluationControle.objects.create(
            org_id=organisation.id, controle=controle, controle_version=controle.version,
            project_id=p1.id, objet_type="avance", objet_id=uuid.uuid4(), resultat=resultat,
            severity="bloquant", evaluee_le=J(2026, 6, 1), declencheur_type="service",
            declencheur_nom="test",
        )  # fmt: skip
    appels = []
    reel = conformite.controles_en_attente
    monkeypatch.setattr(
        conformite, "controles_en_attente", lambda *a, **k: appels.append(a) or reel(*a, **k)
    )
    _tdb(parc)
    assert len(appels) == 1  # les trois objets sans anomalie ne coûtent aucune requête


def test_un_tableau_a_une_date_passee_dit_que_l_execution_budgetaire_est_celle_d_aujourd_hui(parc):
    assert (
        "tableau_de_bord.execution_etat_courant" in _tdb(parc, jour=J(2026, 6, 30)).avertissements
    )
    assert (
        "tableau_de_bord.execution_etat_courant"
        not in _tdb(parc, jour=datetime.date.today()).avertissements
    )


def test_l_api_refuse_un_type_de_taux_ou_une_devise_inconnus(parc):
    q = f"jour={JOUR.isoformat()}"
    chemin = f"/tableau-de-bord/soldes_comptables/consolidation/?{q}&devise_reference=DJF"
    assert appeler(parc[5]["amina"], "get", f"{chemin}&type_taux=xyz").status_code == 422
    assert appeler(parc[5]["amina"], "get", f"/tableau-de-bord/?{q}&devise=ZZZ").status_code == 422
    assert appeler(parc[5]["amina"], "get", f"{chemin}&type_taux=officiel").status_code == 200


def test_la_recette_refuse_un_test_cite_qui_est_ignore_ou_desactive():
    source = (Path(__file__).parent / "test_recette_architecture_bd.py").read_text(encoding="utf-8")
    assert "def _est_desactive" in source  # la vérification existe dans la recette
    from tests.test_recette_architecture_bd import _est_desactive

    assert _est_desactive("@pytest.mark.skip\ndef test_x():\n    pass\n", "test_x")
    assert _est_desactive("@pytest.mark.xfail(reason='x')\ndef test_x():\n    pass\n", "test_x")
    assert _est_desactive("def test_x():\n    pass\n", "test_x")  # corps vide
    assert not _est_desactive("def test_x():\n    assert 1 == 1\n", "test_x")
    assert re.search(r"_est_desactive", source)
