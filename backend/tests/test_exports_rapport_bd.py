# ruff: noqa: F811
"""Fichiers Excel et PDF d'un rapport publié. Voir L6-T05.

Contrôle du plan : le fichier téléchargé a exactement l'empreinte enregistrée. Plus : montants
numériques (pas du texte) au bon nombre de décimales, sortie déterministe, altération détectée,
langue de droite à gauche refusée pour le PDF.
"""

import hashlib
import io
import time
from decimal import Decimal

import openpyxl
import pypdf
import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied

from core.erreurs import ErreurMetier
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau4_reporting.publication.exports import (
    FichierAltere,
    exporter_rapport,
    lire_fichier,
)
from niveau4_reporting.publication.models import FichierRapport
from tests.outils import connexion_proprietaire
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_regeneration_bd import _publier, pub  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def rapport(pub):
    organisation, projet, profils, table = pub
    role = Role.objects.create(
        org_id=organisation.id,
        code="EXP",
        label={"fr": "exp"},
        operations=["consulter", "exporter"],
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=profils["pia"].id, project_id=projet.id, role=role
    )
    return _publier(
        pub, params={"fiscal_year": 2026, "current_period": 3, "devise": "USD"}
    ), profils


def test_le_fichier_lu_a_exactement_l_empreinte_enregistree(rapport):
    publie, profils = rapport
    for format in ("xlsx", "pdf"):
        fichier = exporter_rapport(utilisateur=profils["pia"], rapport=publie, format=format)
        contenu = lire_fichier(utilisateur=profils["pia"], fichier=fichier)
        assert hashlib.sha256(contenu).hexdigest() == fichier.sha256
        assert len(contenu) == fichier.taille


def test_les_montants_excel_sont_des_nombres_au_format_de_la_devise(rapport):
    publie, profils = rapport
    fichier = exporter_rapport(utilisateur=profils["pia"], rapport=publie, format="xlsx")
    feuille = openpyxl.load_workbook(io.BytesIO(bytes(fichier.contenu))).active
    cellules = [
        c for ligne in feuille.iter_rows(min_row=2) for c in ligne[1:] if c.value is not None
    ]
    assert cellules
    for cellule in cellules:
        assert cellule.data_type == "n" and isinstance(cellule.value, int | float), (
            cellule.coordinate
        )
        assert cellule.number_format.startswith("#,##0.00")  # USD : 2 décimales
    valeurs = {feuille.cell(r, 1).value.split()[0]: feuille.cell(r, 2).value for r in range(2, 6)}
    assert Decimal(str(valeurs["R110"])) == Decimal("150.1")


@pytest.mark.parametrize(
    ("devise", "attendu"), [("DJF", "#,##0;"), ("USD", "#,##0.00;"), ("TND", "#,##0.000;")]
)
def test_le_nombre_de_decimales_suit_la_devise(rapport, devise, attendu):
    publie, profils = rapport
    from niveau4_reporting.publication.exports import rendre_excel

    publie.params = {**publie.params, "devise": devise}  # (en mémoire : le rapport publié est figé)
    feuille = openpyxl.load_workbook(io.BytesIO(rendre_excel(publie, "fr"))).active
    assert feuille["B3"].number_format.startswith(attendu)


def test_le_fichier_est_deterministe_et_idempotent(rapport):
    publie, profils = rapport
    from niveau4_reporting.publication.exports import rendre_excel, rendre_pdf

    premier = rendre_excel(publie, "fr")
    time.sleep(2.1)  # les dates d'entrée d'un ZIP ont 2 secondes de résolution
    assert rendre_excel(publie, "fr") == premier
    assert rendre_pdf(publie, "fr") == rendre_pdf(publie, "fr")
    a = exporter_rapport(utilisateur=profils["pia"], rapport=publie, format="pdf")
    b = exporter_rapport(utilisateur=profils["pia"], rapport=publie, format="pdf")
    assert a.pk == b.pk and FichierRapport.objects.count() == 1


def test_le_pdf_porte_le_scelle_du_rapport(rapport):
    publie, profils = rapport
    fichier = exporter_rapport(utilisateur=profils["pia"], rapport=publie, format="pdf")
    texte = pypdf.PdfReader(io.BytesIO(bytes(fichier.contenu))).pages[0].extract_text()
    assert bytes(publie.seal).hex()[:32] in texte.replace("\n", "")


def test_un_fichier_altere_est_refuse_a_la_lecture(rapport):
    publie, profils = rapport
    fichier = exporter_rapport(utilisateur=profils["pia"], rapport=publie, format="xlsx")
    with connexion_proprietaire() as proprietaire:
        # Ce qu'un administrateur malveillant devrait défaire : contrainte ET déclencheur. On remet
        # tout en place ensuite (le DDL ne se défait pas avec la transaction du test).
        proprietaire.execute(
            "ALTER TABLE publication_fichierrapport DISABLE TRIGGER ALL; "
            "ALTER TABLE publication_fichierrapport DROP CONSTRAINT fichier_empreinte_coherente"
        )
        try:
            proprietaire.execute(
                "UPDATE publication_fichierrapport SET contenu = contenu || '\\x00'::bytea"
            )
            fichier.refresh_from_db()
            with pytest.raises(FichierAltere):
                lire_fichier(utilisateur=profils["pia"], fichier=fichier)
        finally:
            proprietaire.execute("DELETE FROM publication_fichierrapport")
            proprietaire.execute(
                "ALTER TABLE publication_fichierrapport ENABLE TRIGGER ALL; "
                "ALTER TABLE publication_fichierrapport ADD CONSTRAINT fichier_empreinte_coherente "
                "CHECK (sha256 ~ '^[0-9a-f]{64}$' AND taille = octet_length(contenu) "
                "AND sha256 = encode(sha256(contenu), 'hex'))"
            )


def test_la_base_refuse_un_fichier_dont_l_empreinte_ne_correspond_pas(rapport):
    publie, profils = rapport
    with pytest.raises(IntegrityError), transaction.atomic():
        FichierRapport.objects.create(
            org_id=publie.org_id, rapport=publie, format="pdf", langue="fr", nom="x.pdf",
            contenu=b"abc", sha256="0" * 64, taille=3, produit_par=profils["pia"].id,
        )  # fmt: skip


def test_un_fichier_produit_ne_se_modifie_pas(rapport):
    publie, profils = rapport
    fichier = exporter_rapport(utilisateur=profils["pia"], rapport=publie, format="pdf")
    with pytest.raises(IntegrityError), transaction.atomic():
        FichierRapport.objects.filter(pk=fichier.pk).update(nom="autre.pdf")


def test_langue_droite_a_gauche_refusee_pour_le_pdf_acceptee_pour_excel(rapport):
    publie, profils = rapport
    with pytest.raises(ErreurMetier):
        exporter_rapport(utilisateur=profils["pia"], rapport=publie, format="pdf", langue="ar")
    fichier = exporter_rapport(
        utilisateur=profils["pia"], rapport=publie, format="xlsx", langue="ar"
    )
    assert openpyxl.load_workbook(io.BytesIO(bytes(fichier.contenu))).active.sheet_view.rightToLeft
    with pytest.raises(ErreurMetier):
        exporter_rapport(utilisateur=profils["pia"], rapport=publie, format="docx")


def test_exporter_et_lire_exigent_l_habilitation(rapport):
    publie, profils = rapport
    with pytest.raises(PermissionDenied):
        exporter_rapport(utilisateur=profils["amina"], rapport=publie, format="pdf")
    fichier = exporter_rapport(utilisateur=profils["pia"], rapport=publie, format="pdf")
    with pytest.raises(PermissionDenied):
        lire_fichier(utilisateur=profils["amina"], fichier=fichier)
