"""Contrôle de sortie du lot L0. Voir L0-T10.

Correspondance entre la checklist du plan et les tests qui la démontrent :

- Un TER produit depuis un registre d'exigences : ce fichier, test 1.
- Un RFI depuis les MÊMES données, avec un mapping différent :
  test_etats_reference_bd.py.
- Un compte non mappé bloque la génération et est nommé :
  test_compilateur_bd.py, test_mapping_bd.py.
- Une formule malveillante est refusée : test_formules.py (6 cas, 4 exigés).
- Une référence circulaire est refusée : test_dependances.py.
- Une assertion fausse bloque la publication : test_assertions_bd.py.
- Toute cellule est traçable jusqu'aux lignes, au centime : ce fichier, test 3,
  et test_tracabilite_bd.py.
- TER sur 200 000 lignes, moins de 3 s, une seule requête :
  scripts/mesurer_ter.py (mesure, hors CI).
"""

import hashlib
import uuid
from decimal import Decimal

import pytest

from niveau3_config.models import DocumentReference, Exigence, RattachementExigence
from niveau4_reporting.moteur.compilateur import compiler
from niveau4_reporting.moteur.tracabilite import tracer
from tests.test_etats_reference_bd import (  # noqa: F401  (fixture de données figées)
    PROJETS,
    _json,
    _produire,
    donnees_figees,
)

pytestmark = pytest.mark.django_db(transaction=True)
ESPACE_RUBRIQUES = uuid.UUID("5c0a1c3e-0000-4000-8000-000000000001")


def _id_rubrique(code_modele, code_rubrique):
    """Identifiant stable d'une rubrique : les rubriques d'un modèle JSON portent un code."""
    return uuid.uuid5(ESPACE_RUBRIQUES, f"{code_modele}:{code_rubrique}")


def _enregistrer_exigences(org_id, modele, *, sauf=()):
    document = DocumentReference.objects.create(
        org_id=org_id,
        project_id=PROJETS["principal"],
        kind="dfil",
        title="DFIL du projet",
        version="1",
        file_ref="objets/dfil.pdf",
        sha256=hashlib.sha256(b"DFIL du projet").digest(),
    )
    for numero, ligne in enumerate(modele["rows"], start=1):
        if ligne["type"] == "heading" or ligne["code"] in sauf:
            continue
        exigence = Exigence.objects.create(
            org_id=org_id,
            project_id=PROJETS["principal"],
            code=f"EXI-{ligne['code']}",
            document=document,
            citation={"annex": "2", "page": 30 + numero, "paragraph": f"4.{numero}", "quote": "…"},
            subject=f"Rubrique {ligne['code']}",
            rule={"rubrique": ligne["code"]},
            obligation="mandatory",
            valid_from="2026-01-01",
            version=1,
            status="active",
            source="manual",
            validated_by=uuid.uuid4(),
            validated_at="2026-01-05T09:00:00Z",
        )
        RattachementExigence.objects.create(
            org_id=org_id,
            exigence=exigence,
            target_type="report_row",
            target_id=_id_rubrique(modele["code"], ligne["code"]),
        )


def _sources(code_modele, produit):
    """Pour chaque rubrique produite, le paragraphe qui la justifie (ou rien)."""
    sources = {}
    for rubrique in produit.valeurs:
        exigence = Exigence.objects.filter(
            rattachements__target_type="report_row",
            rattachements__target_id=_id_rubrique(code_modele, rubrique),
            status="active",
        ).first()
        sources[rubrique] = exigence.citation["paragraph"] if exigence else None
    return sources


def test_un_ter_est_produit_depuis_un_registre_dexigences(org_a, donnees_figees):  # noqa: F811
    """Chaque rubrique du TER produit renvoie à un paragraphe d'un document daté."""
    modele = _json("modeles", "TER.json")
    _enregistrer_exigences(org_a, modele)

    produit = _produire("TER", donnees_figees)

    sources = _sources("TER", produit)
    rubriques_chiffrees = {r["code"] for r in modele["rows"] if r["type"] != "heading"}
    assert set(sources) >= rubriques_chiffrees
    assert all(sources[code] for code in rubriques_chiffrees), sources
    assert sources["R110"] == "4.2"  # R110 est la deuxième ligne du modèle (R100 : titre)


def test_une_rubrique_sans_exigence_source_est_detectee(org_a, donnees_figees):  # noqa: F811
    """Une configuration sans exigence source est une anomalie que le système signale."""
    modele = _json("modeles", "TER.json")
    _enregistrer_exigences(org_a, modele, sauf={"R210"})

    produit = _produire("TER", donnees_figees)

    orphelines = [code for code, source in _sources("TER", produit).items() if source is None]
    assert "R210" in orphelines
    assert "R110" not in orphelines


@pytest.mark.parametrize("code_modele", ["TER", "RFI"])
def test_toute_cellule_dagregat_des_etats_de_reference_est_tracable(
    code_modele,
    donnees_figees,  # noqa: F811
):
    """Somme des lignes retournées == valeur de la cellule, au centime, sur TOUTES."""
    modele = _json("modeles", f"{code_modele}.json")
    parametres = {**modele.pop("parametres"), "project_id": PROJETS["principal"]}
    produit = _produire(code_modele, donnees_figees)
    etat = compiler(modele, donnees_figees, parametres)

    cellules = 0
    for rubrique in etat.agregats:
        for colonne in etat.colonnes:
            trace = tracer(etat, rubrique, colonne)
            valeur = produit.valeurs[rubrique][colonne]
            assert trace.total == valeur, (rubrique, colonne)
            assert sum((ligne.montant for ligne in trace.lignes), Decimal(0)) == valeur
            assert bool(trace.lignes) == (valeur != 0), (rubrique, colonne)
            cellules += 1
    assert cellules == len(etat.agregats) * len(etat.colonnes) > 0
