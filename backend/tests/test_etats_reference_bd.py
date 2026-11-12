"""États de référence : verrouillent le comportement du moteur. Voir L0-T09.

Un jeu de données figé, deux mappings, deux modèles produits à partir des MÊMES
lignes (un TER et un rapport financier intermédiaire) et un résultat attendu
versionné dans `tests/references/`. Les attendus ont été calculés par un
oracle indépendant du moteur (Decimal pur sur le jeu figé), pas copiés de sa
sortie. Toute modification du moteur qui change un chiffre fait échouer la
construction en nommant la rubrique et la colonne.
"""

import datetime
import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from django.db import connection
from django.utils import timezone

from niveau4_reporting.mapping.models import RegleMapping, TableMapping
from niveau4_reporting.moteur.compilateur import generer
from tests.outils import creer_piece, id_objet

pytestmark = pytest.mark.django_db(transaction=True)

REFERENCES = Path(__file__).parent / "references"
DONOR_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
PROJETS = {
    "principal": uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"),
    "autre": uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002"),
}


def _json(*chemin):
    return json.loads(REFERENCES.joinpath(*chemin).read_text(encoding="utf-8"))


def _poser_org(org_id):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])


@pytest.fixture
def donnees_figees(org_a):
    """Insère le jeu figé et les mappings ; retourne les règles par code de mapping."""
    _poser_org(org_a)
    # Une pièce du jeu figé = une écriture comptabilisée, équilibrée.
    pieces: dict[tuple, list] = {}
    for ligne in _json("jeu_donnees.json"):
        pieces.setdefault(
            (ligne["projet"], ligne["piece"], ligne["exercice"], ligne["periode"]), []
        ).append(
            {
                "compte": ligne["compte"],
                "debit": ligne["debit"],
                "credit": ligne["credit"],
                "dim1": ligne["dim1"],
                "accord": ligne["accord"],
                "categorie": ligne["categorie"],
                "site": "SIEGE",
            }
        )
    for (projet, _, annee, periode), lignes in pieces.items():
        creer_piece(org_a, annee, periode, lignes, project_id=PROJETS[projet])
    regles = {}
    for code, definitions in _json("mappings.json").items():
        table = TableMapping.objects.create(
            org_id=org_a,
            project_id=PROJETS["principal"],
            donor_profile_id=DONOR_ID,
            code=code,
            version=1,
            valid_from=datetime.date(2024, 1, 1),
            status="active",
            validated_by=uuid.uuid4(),
            validated_at=timezone.now(),
        )
        for definition in definitions:
            RegleMapping.objects.create(
                org_id=org_a,
                table=table,
                priority=definition["priority"],
                match=definition["match"],
                target_code=definition["target"],
            )
        regles[code] = list(table.regles.all())
    return regles


def _modele_et_parametres(code_modele):
    """Modèle JSON et paramètres de génération.

    Les fichiers de référence nomment l'accord par son code (« IDA-6789 ») ; le grand livre
    le porte comme UUID. La traduction se fait ici pour garder ces fichiers inchangés.
    """
    modele = _json("modeles", f"{code_modele}.json")
    parametres = {**modele.pop("parametres"), "project_id": PROJETS["principal"]}
    if "agreement" in parametres:
        parametres["agreement"] = str(id_objet(parametres["agreement"]))
    return modele, parametres


def _produire(code_modele, regles):
    modele, parametres = _modele_et_parametres(code_modele)
    return generer(modele, regles, parametres)


def _ecarts(produit, attendu):
    """Liste lisible des cellules différentes, une par ligne, avec rubrique et colonne."""
    ecarts = []
    for rubrique, colonnes in attendu["valeurs"].items():
        for colonne, valeur in colonnes.items():
            obtenu = produit.valeurs.get(rubrique, {}).get(colonne)
            if obtenu is None or obtenu != Decimal(valeur):
                ecarts.append(f"{rubrique}/{colonne} : attendu {valeur}, obtenu {obtenu}")
    return ecarts


@pytest.mark.parametrize("code_modele", ["TER", "RFI"])
def test_etat_de_reference_conforme_au_centime(code_modele, donnees_figees):
    attendu = _json("attendus", f"{code_modele}.json")
    produit = _produire(code_modele, donnees_figees)

    assert produit.code == attendu["code"]
    ecarts = _ecarts(produit, attendu)
    assert not ecarts, "État de référence modifié :\n" + "\n".join(ecarts)


@pytest.mark.parametrize("code_modele", ["TER", "RFI"])
def test_les_attendus_couvrent_toutes_les_rubriques_non_titres(code_modele, donnees_figees):
    """Aucune rubrique ne peut sortir du filet de non-régression sans que cela se voie."""
    modele = _json("modeles", f"{code_modele}.json")
    attendu = _json("attendus", f"{code_modele}.json")
    rubriques = {ligne["code"] for ligne in modele["rows"] if ligne["type"] != "heading"}
    colonnes = {colonne["code"] for colonne in modele["columns"]}

    assert set(attendu["valeurs"]) == rubriques
    assert all(set(cellules) == colonnes for cellules in attendu["valeurs"].values())


@pytest.mark.parametrize("code_modele", ["TER", "RFI"])
def test_les_controles_de_coherence_de_reference_sont_tous_reussis(code_modele, donnees_figees):
    attendu = _json("attendus", f"{code_modele}.json")
    produit = _produire(code_modele, donnees_figees)

    obtenus = [
        {
            "rubrique": c.rubrique,
            "colonne": c.colonne,
            "reussi": c.reussi,
            "ecart": f"{c.ecart:.2f}",
        }
        for c in produit.controles
    ]
    assert obtenus == attendu["controles"]


def test_les_deux_etats_sortent_des_memes_donnees_avec_des_mappings_differents(donnees_figees):
    """Même grand livre, deux nomenclatures : le total des charges est identique."""
    ter = _produire("TER", donnees_figees)
    rfi = _produire("RFI", donnees_figees)

    assert ter["R110"]["YTD"] == rfi["RT"]["YTD"] == Decimal("1755.72")
    assert ter["R110"]["CUMUL"] == rfi["RT"]["CUMUL"] == Decimal("2956.22")


def test_le_jeu_fige_est_equilibre_et_ses_pieces_aussi():
    lignes = _json("jeu_donnees.json")
    assert sum(Decimal(ligne["debit"]) - Decimal(ligne["credit"]) for ligne in lignes) == 0
    par_piece = {}
    for ligne in lignes:
        par_piece[ligne["piece"]] = par_piece.get(ligne["piece"], Decimal(0)) + (
            Decimal(ligne["debit"]) - Decimal(ligne["credit"])
        )
    assert all(solde == 0 for solde in par_piece.values()), par_piece
