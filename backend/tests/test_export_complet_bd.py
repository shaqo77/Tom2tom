# ruff: noqa: F811, E501
"""L'export complet d'une organisation et sa restauration dans une instance vierge. Voir L8-T03.

CONTRÔLE DÉCISIF du plan : exporter une organisation, l'importer dans une instance vierge,
régénérer un rapport scellé : résultat identique. Si ce test passe, la réversibilité n'est plus une
promesse commerciale, c'est un fait vérifié.

« Instance vierge » : l'organisation est SUPPRIMÉE de la base (toutes ses lignes, tous ses fichiers
stockés), puis l'archive est restaurée par le rôle propriétaire. Ce test ne crée pas une seconde
base : il prouve que l'archive suffit à reconstruire l'organisation, pas que les migrations
construisent un schéma identique (c'est la CI qui le prouve, à chaque exécution).
"""

import hashlib
import io
import shutil
import time
import zipfile

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from core.audit import verifier_chaine
from niveau1_socle.comptabilite.models import Ecriture, PieceJustificative
from niveau1_socle.comptabilite.pieces import joindre_piece, lire_piece
from niveau1_socle.reversibilite import services
from niveau1_socle.reversibilite.archive import TABLES_EXCLUES, tables_exportees
from niveau1_socle.reversibilite.models import ExportOrganisation
from niveau1_socle.reversibilite.restauration import (
    ArchiveCorrompue,
    InstanceNonVierge,
    restaurer_archive,
    verifier_archive,
)
from niveau1_socle.reversibilite.services import demander_export, lien_signe, produire_export
from niveau3_config import stockage
from niveau4_reporting.publication.dossier import construire_dossier, exporter_dossier
from niveau4_reporting.publication.exports import exporter_rapport, lire_fichier
from niveau4_reporting.publication.models import FichierRapport, RapportPublie
from niveau4_reporting.publication.rapports import regenerer
from tests.outils import connexion_proprietaire
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_dossier_conformite_bd import _exigence_sur_le_mapping
from tests.test_exports_rapport_bd import rapport  # noqa: F401
from tests.test_regeneration_bd import pub  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
SCAN = b"%PDF-1.4 facture 001 \x00\xff scan"


@pytest.fixture
def org(rapport, settings, tmp_path):
    """Une organisation complète : écritures, rapport publié scellé et exporté, dossier, pièce,
    exigence rattachée au mapping, journal d'audit."""
    publie, profils = rapport
    settings.STOCKAGE_DOCUMENTS_ROOT = tmp_path
    _exigence_sur_le_mapping(publie)
    ecriture = (
        Ecriture.objects.filter(project_id=publie.project_id).order_by("accounting_date").first()
    )
    piece = joindre_piece(
        utilisateur=profils["amina"],
        ecriture=ecriture,
        type_piece="facture",
        nom="f.pdf",
        contenu=SCAN,
    )
    exporter_rapport(utilisateur=profils["pia"], rapport=publie, format="xlsx")
    exporter_rapport(utilisateur=profils["pia"], rapport=publie, format="pdf", langue="en")
    exporter_dossier(utilisateur=profils["pia"], rapport=publie)
    return publie, profils, piece, tmp_path


def _poser(org_id):
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.org_id', %s, false)", [str(org_id)])


def _produire(publie, profils):
    _poser(publie.org_id)
    export = demander_export(utilisateur=profils["pia"])
    return produire_export(export)


def _archive(export) -> bytes:
    return stockage.lire(export.file_ref)


def _supprimer_l_organisation(org_id, racine):
    """Rend l'instance vierge POUR CETTE organisation : lignes (toutes tables) et fichiers."""
    with connexion_proprietaire() as c:
        c.execute("SET session_replication_role = replica")
        tables = [
            r[0]
            for r in c.execute(
                "SELECT table_name FROM information_schema.columns c WHERE table_schema = current_schema() "
                "AND column_name = 'org_id' AND EXISTS (SELECT 1 FROM information_schema.tables t "
                "WHERE t.table_name = c.table_name AND t.table_type = 'BASE TABLE')"
            ).fetchall()
        ]
        for t in tables:
            c.execute(f'DELETE FROM "{t}" WHERE org_id = %s', [str(org_id)])
        c.execute("DELETE FROM organisations_organisation WHERE id = %s", [str(org_id)])
    shutil.rmtree(racine, ignore_errors=True)
    racine.mkdir()


def _compter(org_id) -> dict:
    with connexion_proprietaire() as c:
        resultat = {}
        for t in [
            r[0]
            for r in c.execute(
                "SELECT table_name FROM information_schema.columns c WHERE table_schema = current_schema() "
                "AND column_name = 'org_id' AND EXISTS (SELECT 1 FROM information_schema.tables t "
                "WHERE t.table_name = c.table_name AND t.table_type = 'BASE TABLE')"
            ).fetchall()
        ]:
            resultat[t] = c.execute(
                f'SELECT count(*) FROM "{t}" WHERE org_id = %s', [str(org_id)]
            ).fetchone()[0]
        return resultat


# --- le contrôle décisif ---------------------------------------------------------------------


def test_exporter_supprimer_restaurer_puis_regenerer_un_rapport_scelle_donne_le_meme_resultat(org):
    publie, profils, piece, racine = org
    org_id = publie.org_id
    scelle_avant = bytes(publie.seal)
    assert regenerer(publie).identique
    dossier_avant = construire_dossier(publie)
    fichiers_avant = {f.nom: f.sha256 for f in FichierRapport.objects.filter(rapport=publie)}
    verifier_chaine(org_id)
    lignes_avant = _compter(org_id)

    export = _produire(publie, profils)
    archive = _archive(export)
    assert export.statut == "pret" and hashlib.sha256(archive).hexdigest() == export.sha256

    _supprimer_l_organisation(org_id, racine)
    assert sum(_compter(org_id).values()) == 0  # instance vierge pour cette organisation

    with connexion_proprietaire() as proprietaire:
        restaurees = restaurer_archive(archive, proprietaire)
    assert restaurees["comptabilite_ecriture"] == lignes_avant["comptabilite_ecriture"]
    # Chaque table a retrouvé exactement ses lignes (celles d'avant, plus la demande d'export et
    # l'entrée d'audit qui la décrit, présentes dans l'archive puisqu'elle les a produites).
    propres_a_l_export = {"core_auditlog", "reversibilite_exportorganisation"}
    apres = _compter(org_id)
    assert {t: n for t, n in apres.items() if t not in TABLES_EXCLUES | propres_a_l_export} == {
        t: n for t, n in lignes_avant.items() if t not in TABLES_EXCLUES | propres_a_l_export
    }
    assert all(restaurees[t] == apres[t] for t in restaurees if t in apres)  # le manifeste dit vrai

    # Le rapport scellé, REGÉNÉRÉ dans l'instance restaurée : résultat identique.
    _poser(org_id)
    restaure = RapportPublie.objects.get(pk=publie.pk)
    assert bytes(restaure.seal) == scelle_avant
    resultat = regenerer(restaure)
    assert resultat.identique, (resultat.ecarts, resultat.inexpliquee)
    # Le dossier de conformité, les fichiers du rapport, le journal d'audit, le scan : identiques.
    assert construire_dossier(restaure).lignes == dossier_avant.lignes
    assert {
        f.nom: f.sha256 for f in FichierRapport.objects.filter(rapport=restaure)
    } == fichiers_avant
    verifier_chaine(org_id)
    pia = Utilisateur.objects.get(username="pia")
    for f in FichierRapport.objects.filter(rapport=restaure):
        assert hashlib.sha256(lire_fichier(utilisateur=pia, fichier=f)).hexdigest() == f.sha256
    assert lire_piece(PieceJustificative.objects.get(pk=piece.pk)) == SCAN


# --- ce que contient l'archive ----------------------------------------------------------------


def test_l_archive_contient_toutes_les_parties_et_son_manifeste_est_exact(org):
    publie, profils, *_ = org
    archive = _archive(_produire(publie, profils))
    manifeste = verifier_archive(archive)  # chaque SHA-256 recalculé et comparé
    noms = set(manifeste["fichiers"])
    assert {"LISEZMOI.txt", "restauration.sql", "schema/dictionnaire.json", "journal_audit.csv",
            "parametrage/parametrage.json", "registre/exigences.json"} <= noms  # fmt: skip
    assert any(n.startswith("donnees/comptabilite_ecriture") for n in noms)
    assert any(n.startswith(f"rapports/{publie.id}/rapport.json") for n in noms)
    assert any(n.endswith(".xlsx") for n in noms) and sum(n.endswith(".pdf") for n in noms) >= 2
    assert any(n.startswith("fichiers/") for n in noms)  # le scan de la pièce
    assert any(n.startswith("registre/guide_") for n in noms) or manifeste["notes"]
    assert (
        manifeste["tables"]["comptabilite_ecriture"]
        == _compter(publie.org_id)["comptabilite_ecriture"]
    )
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert all(info.date_time == (2020, 1, 1, 0, 0, 0) for info in z.infolist())
        schema = __import__("json").loads(z.read("schema/dictionnaire.json"))
    assert {t["table"] for t in schema["tables"]} == set(manifeste["tables"])  # schéma documenté


def test_les_csv_sont_lisibles_en_utf8_avec_leurs_en_tetes(org):
    publie, profils, *_ = org
    archive = _archive(_produire(publie, profils))
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        texte = z.read("donnees/referentiels_compte.csv").decode("utf-8")
        parametrage = __import__("json").loads(z.read("parametrage/parametrage.json"))
    assert texte.splitlines()[0].startswith("id,")
    assert "6011" in texte
    assert {c["code"] for c in parametrage["plan_comptable"]} >= {"6011", "5211"}
    assert any(m["code"] == "WB" for m in parametrage["mappings"])
    assert "TER@3" in parametrage["modeles_d_etats"]


def test_ni_les_mots_de_passe_ni_les_jetons_auditeur_ne_sortent(org):
    publie, profils, *_ = org
    from niveau1_socle.habilitations.models import Habilitation, Role
    from niveau4_reporting.publication.auditeur import creer_acces_auditeur

    role = Role.objects.create(
        org_id=publie.org_id, code="ADM", label={"fr": "a"}, operations=["parametrer"]
    )
    Habilitation.objects.create(
        org_id=publie.org_id, user_id=profils["pia"].id, project_id=publie.project_id, role=role
    )
    _poser(publie.org_id)
    creer_acces_auditeur(
        utilisateur=profils["pia"], nom="Cabinet", project_ids=[publie.project_id],
        period_from=publie.period_from, period_to=publie.period_to, duree_jours=5,
    )  # fmt: skip
    archive = _archive(_produire(publie, profils))
    hash_mdp = Utilisateur.objects.get(username="pia").password
    assert hash_mdp.startswith("pbkdf2")
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        tout = b"".join(z.read(n) for n in z.namelist())
        assert b"donnees/publication_accesauditeur.csv" not in z.namelist()
    assert hash_mdp.encode() not in tout and b"pbkdf2" not in tout
    assert "publication_accesauditeur" in TABLES_EXCLUES


# --- la restauration refuse ce qu'elle doit refuser -----------------------------------------


def test_une_archive_alteree_est_refusee_avant_toute_ecriture(org):
    publie, profils, _, racine = org
    archive = _archive(_produire(publie, profils))
    tampon = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(archive)) as source, zipfile.ZipFile(tampon, "w") as cible:
        for nom in source.namelist():
            donnees = source.read(nom)
            if nom == "donnees/referentiels_compte.csv":
                donnees = donnees.replace(b"6011", b"6012")
            cible.writestr(nom, donnees)
    _supprimer_l_organisation(publie.org_id, racine)
    with connexion_proprietaire() as proprietaire, pytest.raises(ArchiveCorrompue):
        restaurer_archive(tampon.getvalue(), proprietaire)
    assert sum(_compter(publie.org_id).values()) == 0  # rien n'a été écrit


def test_on_ne_restaure_pas_dans_une_instance_ou_l_organisation_existe(org):
    publie, profils, *_ = org
    archive = _archive(_produire(publie, profils))
    avant = _compter(publie.org_id)
    with connexion_proprietaire() as proprietaire, pytest.raises(InstanceNonVierge):
        restaurer_archive(archive, proprietaire)
    assert _compter(publie.org_id) == avant  # ni doublon ni écrasement


# --- la demande, la tâche de fond, le lien signé ----------------------------------------------


def test_l_export_exige_l_habilitation_sur_tous_les_projets(org):
    publie, profils, *_ = org
    _poser(publie.org_id)
    with pytest.raises(PermissionDenied):
        demander_export(utilisateur=profils["amina"])


def test_un_export_pret_ne_change_plus_et_un_echec_est_enregistre(org, monkeypatch):
    publie, profils, *_ = org
    export = _produire(publie, profils)
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        ExportOrganisation.objects.filter(pk=export.pk).update(sha256="0" * 64)
    with pytest.raises(IntegrityError), transaction.atomic():
        ExportOrganisation.objects.filter(pk=export.pk).delete()

    def panne(*a, **k):
        raise RuntimeError("disque plein")

    monkeypatch.setattr(services, "construire_archive", panne)
    nouveau = demander_export(utilisateur=profils["pia"])
    with pytest.raises(RuntimeError):
        produire_export(nouveau)
    nouveau.refresh_from_db()
    assert nouveau.statut == "echec" and "disque plein" in nouveau.erreur


def test_le_lien_signe_donne_l_archive_tant_qu_il_est_valable_puis_403(org, monkeypatch):
    publie, profils, *_ = org
    export = _produire(publie, profils)
    jeton = lien_signe(utilisateur=profils["pia"], export=export, duree_secondes=120)

    def appeler(valeur):
        with connection.cursor() as cur:
            cur.execute("RESET app.org_id")
        return APIClient().get(f"/export/{valeur}/")

    reponse = appeler(jeton)
    assert reponse.status_code == 200 and reponse["X-Empreinte-SHA256"] == export.sha256
    assert hashlib.sha256(reponse.content).hexdigest() == export.sha256
    assert appeler(jeton + "x").status_code == 403  # signature falsifiée
    assert appeler("n-importe-quoi").status_code == 403
    futur = time.time() + 121
    monkeypatch.setattr(services.time, "time", lambda: futur)
    assert appeler(jeton).status_code == 403  # expiré
    _poser(publie.org_id)  # l'appel HTTP a retiré l'organisation de la connexion de test
    with pytest.raises(Exception, match="1 minute"):
        lien_signe(utilisateur=profils["pia"], export=export, duree_secondes=5)
    with pytest.raises(Exception, match="24 heures"):
        lien_signe(utilisateur=profils["pia"], export=export, duree_secondes=48 * 3600)


def test_un_lien_ne_sert_que_pour_un_export_pret(org):
    publie, profils, *_ = org
    _poser(publie.org_id)
    export = demander_export(utilisateur=profils["pia"])
    with pytest.raises(Exception, match="pas prêt"):
        lien_signe(utilisateur=profils["pia"], export=export)


def test_les_exports_sont_journalises(org):
    publie, profils, *_ = org
    export = _produire(publie, profils)
    lien_signe(utilisateur=profils["pia"], export=export)
    from core.models import AuditLog

    actions = {e.action for e in AuditLog.objects.filter(org_id=publie.org_id)}
    assert {"export_requested", "export_produced", "export_link_issued"} <= actions
    assert tables_exportees  # (importé : la liste des tables se découvre, elle ne se maintient pas)


def test_une_restauration_incomplete_est_detectee_par_le_comptage_du_manifeste(org):
    """Une archive cohérente avec son manifeste, mais dont le dépôt SQL omet une table : la
    restauration compare les lignes restaurées au manifeste et refuse."""
    import json

    from niveau1_socle.reversibilite.restauration import RestaurationIncomplete

    publie, profils, _, racine = org
    archive = _archive(_produire(publie, profils))
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        fichiers = {n: source.read(n) for n in source.namelist()}
    sql = fichiers["restauration.sql"].decode()
    debut = sql.index('COPY "referentiels_compte"')
    fin = sql.index("\\.\n", debut) + 3
    fichiers["restauration.sql"] = (sql[:debut] + sql[fin:]).encode()
    manifeste = json.loads(fichiers["MANIFESTE.json"])
    manifeste["fichiers"]["restauration.sql"] = hashlib.sha256(
        fichiers["restauration.sql"]
    ).hexdigest()
    fichiers["MANIFESTE.json"] = json.dumps(manifeste).encode()
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as cible:
        for nom, contenu in fichiers.items():
            cible.writestr(nom, contenu)
    _supprimer_l_organisation(publie.org_id, racine)
    with connexion_proprietaire() as proprietaire, pytest.raises(RestaurationIncomplete):
        restaurer_archive(tampon.getvalue(), proprietaire)
    assert (
        sum(_compter(publie.org_id).values()) == 0
    )  # la transaction est annulée : rien de partiel
