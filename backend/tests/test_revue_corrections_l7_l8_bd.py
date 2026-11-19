# ruff: noqa: F811, E501
"""Corrections issues de la revue de code des lots L7 et L8 : un test par constat, écrit pour
ÉCHOUER avant la correction.
"""

import hashlib
import io
import json
import uuid
import zipfile
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework.test import APIClient

from core.audit import journaliser, verifier_chaine
from core.erreurs import ErreurMetier
from niveau1_socle.comptabilite.models import LigneEcriture
from niveau1_socle.reprise.models import Reprise
from niveau1_socle.reprise.services import controler_reprise, signer_rapport
from niveau1_socle.reversibilite.archive import TABLES_EXCLUES, construire_archive
from niveau1_socle.reversibilite.models import ExportOrganisation
from niveau1_socle.reversibilite.restauration import (
    ArchiveCorrompue,
    restaurer_archive,
)
from niveau1_socle.reversibilite.services import (
    demander_export,
    lien_signe,
    recuperer_exports_bloques,
)
from niveau3_config import stockage
from tests.outils import _valeur_axe, connexion_proprietaire
from tests.test_acces_auditeur_bd import _get, _urls, aud  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_descente_complete_bd import descente  # noqa: F401
from tests.test_export_complet_bd import (  # noqa: F401
    _archive,
    _compter,
    _poser,
    _produire,
    _supprimer_l_organisation,
    org,
)
from tests.test_exports_rapport_bd import rapport  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_regeneration_bd import pub  # noqa: F401
from tests.test_reprise_bd import BALANCE, HISTORIQUE, _balance, _historique, rep  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = Decimal


def _reconstruire(archive: bytes, changements: dict, *, manifeste_a_jour=True) -> bytes:
    """Une archive modifiée dont le manifeste est RECALCULÉ : ce qu'un attaquant ferait."""
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        fichiers = {n: source.read(n) for n in source.namelist()}
    fichiers.update(changements)
    if manifeste_a_jour:
        manifeste = json.loads(fichiers["MANIFESTE.json"])
        for nom in changements:
            if nom in manifeste["fichiers"]:
                manifeste["fichiers"][nom] = hashlib.sha256(fichiers[nom]).hexdigest()
        fichiers["MANIFESTE.json"] = json.dumps(manifeste).encode()
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as cible:
        for nom, contenu in fichiers.items():
            cible.writestr(nom, contenu)
    return tampon.getvalue()


# --- 1. les séquences suivent les lignes restaurées -------------------------------------------


def test_apres_restauration_le_journal_d_audit_accepte_de_nouvelles_entrees(org):
    publie, profils, _, racine = org
    archive = _archive(_produire(publie, profils))
    _supprimer_l_organisation(publie.org_id, racine)
    with connexion_proprietaire() as proprietaire:
        # Une instance neuve : la séquence de l'identifiant d'audit repart de 1.
        proprietaire.execute(
            "SELECT setval(pg_get_serial_sequence('core_auditlog', 'id'), 1, false)"
        )
        restaurer_archive(archive, proprietaire)
    _poser(publie.org_id)
    journaliser(org_id=publie.org_id, actor_id=None, action="after_restore", object_type="test")
    verifier_chaine(publie.org_id)


# --- 2. l'archive n'est pas crue sur parole ----------------------------------------------------


def test_une_archive_qui_copie_des_lignes_d_une_autre_organisation_est_refusee(org):
    publie, profils, _, racine = org
    archive = _archive(_produire(publie, profils))
    sql = zipfile.ZipFile(io.BytesIO(archive)).read("restauration.sql").decode()
    intrus = uuid.uuid4()
    # Un bloc supplémentaire dont l'org_id n'est PAS celui du manifeste.
    ligne = f'COPY "comptabilite_journal" ("id", "org_id", "code", "label", "actif", "created_at", "updated_at") FROM stdin;\n{uuid.uuid4()}\t{intrus}\tX\t{{}}\tt\t2026-01-01 00:00:00+00\t2026-01-01 00:00:00+00\n\\.\n'
    piege = _reconstruire(archive, {"restauration.sql": (sql + ligne).encode()})
    _supprimer_l_organisation(publie.org_id, racine)
    with connexion_proprietaire() as proprietaire, pytest.raises(ArchiveCorrompue):
        restaurer_archive(piege, proprietaire)
    assert sum(_compter(publie.org_id).values()) == 0
    with connexion_proprietaire() as proprietaire:
        assert (
            proprietaire.execute(
                "SELECT count(*) FROM comptabilite_journal WHERE org_id = %s", [str(intrus)]
            ).fetchone()[0]
            == 0
        )


def test_une_archive_qui_cible_une_table_hors_de_l_export_est_refusee(org):
    publie, profils, _, racine = org
    archive = _archive(_produire(publie, profils))
    sql = zipfile.ZipFile(io.BytesIO(archive)).read("restauration.sql").decode()
    piege = _reconstruire(
        archive,
        {
            "restauration.sql": (
                sql + 'COPY "publication_accesauditeur" ("id") FROM stdin;\n\\.\n'
            ).encode()
        },
    )
    _supprimer_l_organisation(publie.org_id, racine)
    with connexion_proprietaire() as proprietaire, pytest.raises(ArchiveCorrompue):
        restaurer_archive(piege, proprietaire)


def test_un_compte_superutilisateur_dans_l_archive_est_refuse(org):
    publie, profils, _, racine = org
    archive = _archive(_produire(publie, profils))
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        sql = z.read("restauration.sql").decode()
    debut = sql.index('COPY "organisations_utilisateur"')
    entete = sql[debut : sql.index("\n", debut)]
    colonnes = [c.strip().strip('"') for c in entete.split("(", 1)[1].split(")", 1)[0].split(",")]
    fin_bloc = sql.index("\n\\.\n", debut)
    lignes = sql[sql.index("\n", debut) + 1 : fin_bloc].split("\n")
    champs = lignes[0].split("\t")
    champs[colonnes.index("is_superuser")] = "t"
    lignes[0] = "\t".join(champs)
    nouveau = sql[: sql.index("\n", debut) + 1] + "\n".join(lignes) + sql[fin_bloc:]
    piege = _reconstruire(archive, {"restauration.sql": nouveau.encode()})
    _supprimer_l_organisation(publie.org_id, racine)
    with connexion_proprietaire() as proprietaire, pytest.raises(ArchiveCorrompue):
        restaurer_archive(piege, proprietaire)
    assert sum(_compter(publie.org_id).values()) == 0


def test_l_empreinte_attendue_authentifie_l_archive_hors_de_l_archive(org):
    publie, profils, _, racine = org
    export = _produire(publie, profils)
    archive = _archive(export)
    faux = _reconstruire(archive, {"LISEZMOI.txt": b"autre texte"})
    _supprimer_l_organisation(publie.org_id, racine)
    with connexion_proprietaire() as proprietaire:
        with pytest.raises(ArchiveCorrompue):  # manifeste cohérent, mais pas l'archive exportée
            restaurer_archive(faux, proprietaire, sha256_attendu=export.sha256)
        restaurer_archive(archive, proprietaire, sha256_attendu=export.sha256)


# --- 3. l'axe 1 est celui du plan de gestion du rang 1 ----------------------------------------


def test_l_axe_1_ne_se_resout_pas_sur_un_autre_plan_portant_le_meme_code(rep):
    organisation, projet, profils, reprise = rep
    autre = _valeur_axe(organisation.id, "COMP-A", emplacement=2)  # même code, plan du rang 2
    _balance(rep)
    _historique(rep)
    lignes = LigneEcriture.objects.filter(dim1__isnull=False)
    assert lignes.count() == 2
    assert all(ligne.dim1.plan.slot == 1 and ligne.dim1_id != autre.id for ligne in lignes)


# --- 4. l'archive vérifie son périmètre --------------------------------------------------------


def test_construire_une_archive_hors_du_perimetre_de_l_organisation_est_refuse(org):
    publie, profils, *_ = org
    _poser(publie.org_id)
    with pytest.raises(ErreurMetier):
        construire_archive(uuid.uuid4())  # une autre organisation que celle du périmètre
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")
    with pytest.raises(ErreurMetier):
        construire_archive(publie.org_id)  # aucun périmètre posé : l'archive serait vide


# --- 5. le téléchargement vérifie l'empreinte --------------------------------------------------


def test_un_export_altere_dans_le_stockage_n_est_pas_servi(org):
    publie, profils, *_ = org
    export = _produire(publie, profils)
    jeton = lien_signe(utilisateur=profils["pia"], export=export)
    stockage._chemin(export.file_ref).write_bytes(b"remplace en douce")
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")
    reponse = APIClient().get(f"/export/{jeton}/")
    assert reponse.status_code == 409


# --- 6. un export interrompu ne reste pas bloqué -----------------------------------------------


def test_un_export_interrompu_est_recupere_en_echec_et_n_est_pas_dans_l_archive(org):
    publie, profils, *_ = org
    _poser(publie.org_id)
    export = demander_export(utilisateur=profils["pia"])
    ExportOrganisation.objects.filter(pk=export.pk).update(statut="en_cours")
    with connexion_proprietaire() as c:
        c.execute(
            "ALTER TABLE reversibilite_exportorganisation DISABLE TRIGGER reversibilite_export_garde"
        )
        c.execute(
            "UPDATE reversibilite_exportorganisation SET updated_at = now() - interval '3 hours' WHERE id = %s",
            [str(export.pk)],
        )
        c.execute(
            "ALTER TABLE reversibilite_exportorganisation ENABLE TRIGGER reversibilite_export_garde"
        )
    assert recuperer_exports_bloques(delai_minutes=60) == 1
    export.refresh_from_db()
    assert export.statut == "echec" and "interrompu" in export.erreur
    assert recuperer_exports_bloques(delai_minutes=60) == 0  # une seule fois
    assert "reversibilite_exportorganisation" in TABLES_EXCLUES


# --- 7. les erreurs de reprise nomment la pièce de la source ---------------------------------


def test_les_erreurs_de_reprise_nomment_le_journal_et_le_numero_de_piece(rep):
    with pytest.raises(ErreurMetier) as e:
        _historique(rep, HISTORIQUE.replace("2026-03-05", "2026-04-05"))
    assert "OD/P003" in str(e.value)
    with pytest.raises(ErreurMetier) as e:
        _historique(rep, HISTORIQUE.replace("0;75,25", "0;70"))
    assert "OD/P003" in str(e.value)
    _historique(rep)
    with pytest.raises(ErreurMetier) as e:
        _historique(rep, HISTORIQUE.replace("1000,50", "1000,60"))
    assert "OD/P001" in str(e.value)


# --- 8. le signataire n'est ni l'ouvreur ni le contrôleur ni l'importeur ----------------------


def test_celui_qui_a_controle_ou_importe_ne_signe_pas(rep):
    organisation, projet, profils, reprise = rep
    from niveau1_socle.habilitations.models import Habilitation, Role

    for nom in ("bernard", "claude_i"):
        u = Utilisateur.objects.create_user(nom, password="x", org_id=organisation.id)
        role = Role.objects.create(
            org_id=organisation.id,
            code=nom.upper(),
            label={"fr": nom},
            operations=["consulter", "parametrer", "valider"],
        )
        Habilitation.objects.create(
            org_id=organisation.id, user_id=u.id, project_id=projet.id, role=role
        )
        profils[nom] = u
    role_v = Role.objects.create(
        org_id=organisation.id, code="DV", label={"fr": "d"}, operations=["valider"]
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=profils["dora"].id, project_id=projet.id, role=role_v
    )
    from niveau1_socle.reprise.services import importer_balance_origine, importer_historique

    importer_balance_origine(
        utilisateur=profils["dora"], reprise=reprise, contenu=BALANCE.encode(), nom_fichier="b.csv"
    )
    importer_historique(
        utilisateur=profils["claude_i"],
        reprise=reprise,
        contenu=HISTORIQUE.encode(),
        nom_fichier="h.csv",
    )
    rapport = controler_reprise(utilisateur=profils["bernard"], reprise=reprise)
    for coupable in ("bernard", "claude_i", "dora"):
        with pytest.raises(ErreurMetier) as e:
            signer_rapport(utilisateur=profils[coupable], rapport=rapport)
        assert e.value.code == "APPROBATION_REQUISE", coupable
    signer_rapport(utilisateur=profils["sonia"], rapport=rapport)
    assert Reprise.objects.get().statut == "acceptee"


# --- 9. la descente est paginée et ne reconstruit pas le dossier -------------------------------


def test_la_descente_est_paginee_et_la_somme_porte_sur_toutes_les_lignes(descente):
    publie, _, jeton, sources, _ = descente
    base = _urls(publie)["detail"]
    page = _get(f"{base}cellules/R110/QTR/?limite=1&decalage=0", jeton).json()
    assert len(page["lignes"]) == 1 and page["nombre_de_lignes"] == 2
    assert page["limite"] == 1 and page["decalage"] == 0
    assert (
        Decimal(page["somme"]) == Decimal(page["valeur_publiee"]) == Decimal("150.1")
    )  # TOUTES les lignes
    suite = _get(f"{base}cellules/R110/QTR/?limite=1&decalage=1", jeton).json()
    assert {page["lignes"][0]["id"], suite["lignes"][0]["id"]} == {
        ligne["id"] for ligne in _get(f"{base}cellules/R110/QTR/", jeton).json()["lignes"]
    }
    bornee = _get(f"{base}cellules/R110/QTR/?limite=999999", jeton).json()
    assert bornee["limite"] == 5000
    assert _get(f"{base}cellules/R110/QTR/?limite=abc", jeton).status_code == 400


def test_la_regle_d_une_cellule_ne_construit_pas_le_dossier(descente, monkeypatch):
    publie, _, jeton, *_ = descente
    from niveau4_reporting.publication import descente as module

    def interdit(*a, **k):
        raise AssertionError("le dossier de conformité ne doit pas être reconstruit")

    monkeypatch.setattr(module, "construire_dossier", interdit, raising=False)
    reponse = _get(f"{_urls(publie)['detail']}cellules/R110/QTR/", jeton)
    assert reponse.status_code == 200 and "mapping WB v1" in reponse.json()["regle"]


# --- 10. les réponses HTTP passent par le catalogue -------------------------------------------


def test_les_refus_http_suivent_la_langue_demandee(org):
    publie, profils, *_ = org
    export = _produire(publie, profils)
    lien_signe(utilisateur=profils["pia"], export=export)
    with connection.cursor() as cur:
        cur.execute("RESET app.org_id")
    client = APIClient()
    en = client.get("/export/faux/", HTTP_ACCEPT_LANGUAGE="en").json()["detail"]
    fr = client.get("/export/faux/", HTTP_ACCEPT_LANGUAGE="fr").json()["detail"]
    assert "Invalid or expired" in en and "invalide" in fr
