# ruff: noqa: F811, E501
"""La descente complète, en accès auditeur : cellule → lignes → écriture → pièces → scan. L7-T03.

Contrôle de bout en bout du plan : ouvrir un TER publié ; cliquer une cellule (la liste des
écritures) ; la somme des lignes est la valeur de la cellule, au centime ; cliquer une écriture (ses
pièces) ; ouvrir une pièce (le scan) ; le tout en accès auditeur, sans aucune assistance.
"""

import hashlib
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from django.db import IntegrityError, connection, transaction
from rest_framework.exceptions import PermissionDenied

from core.erreurs import ErreurMetier
from niveau1_socle.comptabilite.models import Ecriture, PieceJustificative
from niveau1_socle.comptabilite.pieces import joindre_piece
from niveau3_config import stockage
from tests.test_acces_auditeur_bd import _get, _urls, aud  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_exports_rapport_bd import rapport  # noqa: F401
from tests.test_regeneration_bd import _piece, pub  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
SCAN_1 = b"%PDF-1.4 facture fournisseur 001 \x00\x01\x02 scan"
SCAN_2 = b"%PDF-1.4 bon de commande 77 \xff\xfe scan"


@pytest.fixture
def descente(aud, settings, tmp_path):
    publie, profils, acces, jeton, fichier = aud
    settings.STOCKAGE_DOCUMENTS_ROOT = tmp_path
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(publie.org_id)])
    ecritures = list(
        Ecriture.objects.filter(project_id=publie.project_id).order_by("accounting_date", "number")
    )
    # Deux pièces du trimestre (100 et 50,10 en 6011) : une facture et un bon de commande.
    sources = [e for e in ecritures if e.lignes.filter(account__code="6011").exists()]
    assert len(sources) == 2
    p1 = joindre_piece(
        utilisateur=profils["amina"],
        ecriture=sources[0],
        type_piece="facture",
        nom="facture-001.pdf",
        contenu=SCAN_1,
    )
    p2 = joindre_piece(
        utilisateur=profils["amina"],
        ecriture=sources[1],
        type_piece="bon_de_commande",
        nom="bc-77.pdf",
        contenu=SCAN_2,
    )
    return publie, profils, jeton, sources, (p1, p2)


def _url_ecriture(publie, ecriture_id, piece_id=None):
    base = f"/auditeur/projets/{publie.project_id}/ecritures/{ecriture_id}/"
    return base + (f"pieces/{piece_id}/" if piece_id else "")


def test_descente_de_bout_en_bout_en_acces_auditeur(descente):
    publie, _, jeton, sources, (p1, p2) = descente
    base = _urls(publie)["detail"]

    # 1. Ouvrir un TER publié.
    rapport_json = _get(base, jeton).json()
    assert rapport_json["valeurs"]["R110/QTR"] == "150.1"

    # 2. Cliquer une cellule : la liste des écritures s'affiche.
    cellule = _get(f"{base}cellules/R110/QTR/", jeton).json()
    assert cellule["type"] == "aggregate" and "mapping WB v1" in cellule["regle"]
    assert {ligne["ecriture"] for ligne in cellule["lignes"]} == {str(e.id) for e in sources}

    # 3. La somme des lignes == la valeur de la cellule, au centime.
    assert (
        sum(Decimal(ligne["montant"]) for ligne in cellule["lignes"])
        == Decimal(cellule["valeur_publiee"])
        == Decimal("150.1")
    )
    assert cellule["coherente"] is True and Decimal(cellule["ecart"]) == 0

    # 4. Cliquer une écriture : ses pièces s'affichent.
    premiere = cellule["lignes"][0]["ecriture"]
    ecriture = _get(_url_ecriture(publie, premiere), jeton).json()
    assert len(ecriture["pieces"]) == 1 and ecriture["numero"] and ecriture["lignes"]
    piece = ecriture["pieces"][0]
    assert piece["type"] in ("facture", "bon_de_commande") and piece["sha256"]

    # 5. Ouvrir une pièce : le scan s'affiche (octets exacts, empreinte enregistrée).
    scan = _get(_url_ecriture(publie, premiere, piece["id"]), jeton)
    assert scan.status_code == 200
    attendu = {str(p1.id): SCAN_1, str(p2.id): SCAN_2}[piece["id"]]
    assert scan.content == attendu
    assert hashlib.sha256(scan.content).hexdigest() == piece["sha256"] == scan["X-Empreinte-SHA256"]


def test_une_cellule_calculee_descend_vers_les_cellules_dont_elle_depend(descente):
    publie, _, jeton, *_ = descente
    cellule = _get(f"{_urls(publie)['detail']}cellules/R190/QTR/", jeton).json()
    assert cellule["type"] == "computed" and cellule["coherente"] is True
    assert {c["rubrique"] for c in cellule["composantes"]} == {"R110", "R120"}
    assert sum(Decimal(c["valeur_publiee"]) for c in cellule["composantes"]) == Decimal(
        cellule["valeur_publiee"]
    )


def test_une_ecriture_arrivee_apres_la_publication_n_entre_pas_dans_la_somme(descente):
    publie, _, jeton, *_ = descente
    organisation = type("O", (), {"id": publie.org_id})
    projet = type("P", (), {"id": publie.project_id})
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(publie.org_id)])
    _piece(organisation, projet, "6011", "5211", "75.25")  # comptabilisée après la publication
    cellule = _get(f"{_urls(publie)['detail']}cellules/R110/QTR/", jeton).json()
    assert cellule["lignes_posterieures_a_la_publication"] == 1
    assert cellule["coherente"] is True
    assert Decimal(cellule["somme"]) == Decimal(
        "150.1"
    )  # la valeur publiée, pas celle d'aujourd'hui


def test_une_cellule_ou_une_ecriture_inconnue_est_un_404(descente):
    publie, _, jeton, *_ = descente
    base = _urls(publie)["detail"]
    for chemin in (
        f"{base}cellules/T100/QTR/",
        f"{base}cellules/R110/XXX/",
        f"{base}cellules/NOPE/QTR/",
        _url_ecriture(publie, uuid.uuid4()),
    ):
        assert _get(chemin, jeton).status_code == 404, chemin


def test_la_descente_reste_dans_le_perimetre_de_l_auditeur(descente):
    publie, profils, jeton, sources, (p1, _) = descente
    from tests.test_cycle_ecriture_bd import _creer_projet

    organisation = type("O", (), {"id": publie.org_id})
    autre = _creer_projet(organisation, "P-AUTRE")
    for chemin in (
        f"/auditeur/projets/{autre.id}/ecritures/{sources[0].id}/",
        f"/auditeur/projets/{autre.id}/rapports/{publie.id}/cellules/R110/QTR/",
    ):
        assert _get(chemin, jeton).status_code == 403
    # Une écriture réelle d'un AUTRE projet de la même organisation, demandée sous le projet de
    # l'auditeur : introuvable (jamais servie).
    from tests.outils import creer_piece

    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(publie.org_id)])
    etrangere = creer_piece(
        publie.org_id, 2026, 2,
        [{"compte": "6011", "debit": "10"}, {"compte": "5211", "credit": "10"}],
        project_id=autre.id,
    )  # fmt: skip
    assert _get(_url_ecriture(publie, etrangere.id), jeton).status_code == 404
    assert _get(_url_ecriture(publie, uuid.uuid4(), p1.id), jeton).status_code == 404


def test_un_scan_altere_n_est_pas_servi(descente):
    publie, _, jeton, sources, (p1, _) = descente
    chemin: Path = stockage._chemin(p1.file_ref)
    chemin.write_bytes(b"remplace en douce")
    reponse = _get(_url_ecriture(publie, sources[0].id, p1.id), jeton)
    assert reponse.status_code == 409


def test_chaque_descente_est_journalisee(descente):
    from niveau4_reporting.publication.auditeur import journal_des_acces

    publie, profils, jeton, sources, (p1, _) = descente
    base = _urls(publie)["detail"]
    _get(f"{base}cellules/R110/QTR/", jeton)
    _get(_url_ecriture(publie, sources[0].id), jeton)
    _get(_url_ecriture(publie, sources[0].id, p1.id), jeton)
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(publie.org_id)])
    ressources = [
        e.after["ressource"]
        for e in journal_des_acces(utilisateur=profils["admin"], project_id=publie.project_id)
        if e.action == "auditor_consulted"
    ]
    assert ressources[:3] == ["piece", "ecriture", "cellule"]


# --- les pièces ----------------------------------------------------------------------------------


def test_une_piece_se_joint_une_fois_et_ne_se_modifie_pas(descente):
    publie, profils, _, sources, (p1, _) = descente
    encore = joindre_piece(
        utilisateur=profils["amina"],
        ecriture=sources[0],
        type_piece="facture",
        nom="autre-nom.pdf",
        contenu=SCAN_1,
    )
    assert encore.pk == p1.pk  # mêmes octets : une seule pièce
    with pytest.raises(IntegrityError), transaction.atomic():
        PieceJustificative.objects.filter(pk=p1.pk).update(nom="réécrit")
    with pytest.raises(IntegrityError), transaction.atomic():
        PieceJustificative.objects.filter(pk=p1.pk).delete()


def test_joindre_une_piece_exige_l_habilitation_et_un_fichier_valide(descente):
    publie, profils, _, sources, _ = descente
    with pytest.raises(PermissionDenied):
        joindre_piece(
            utilisateur=profils["pia"],
            ecriture=sources[0],
            type_piece="facture",
            nom="x.pdf",
            contenu=b"abc",
        )
    for champs in ({"type_piece": "inconnu"}, {"nom": " "}, {"contenu": b""}):
        base = {
            "utilisateur": profils["amina"],
            "ecriture": sources[0],
            "type_piece": "facture",
            "nom": "x.pdf",
            "contenu": b"abc",
        }
        with pytest.raises(ErreurMetier):
            joindre_piece(**{**base, **champs})
