"""Les fichiers d'un rapport publié : Excel et PDF, stockés avec leur empreinte. Voir L6-T05.

Excel : les montants sont de vrais NOMBRES (jamais du texte), au format de la devise (2 ou 4
décimales selon `Devise.decimales`). Le fichier est DÉTERMINISTE (dates de propriétés et des
entrées du ZIP fixées sur la date de publication) : régénéré, il redonne les mêmes octets.

PDF : l'écrivain minimal du projet (polices standard, latin). Il ne sait pas écrire de droite à
gauche : demander une langue RTL est REFUSÉ explicitement plutôt que de produire un PDF faux. Le
plan prévoit Typst ou WeasyPrint pour l'arabe ; aucun n'est installé ici (voir la note du plan).

Lire un fichier recalcule son SHA-256 et le compare à celui enregistré.
"""

import hashlib
import io
import re
import zipfile
from decimal import Decimal

import openpyxl
from django.db import IntegrityError, transaction
from openpyxl.styles import Alignment, Font
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import LANGUES, formater_date, formater_montant, msg
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.referentiels.models import Devise
from niveau3_config.services.pdf_minimal import DocumentPDF

from .models import FichierRapport, RapportPublie

FORMATS = ("xlsx", "pdf")
LANGUES_DROITE_A_GAUCHE = frozenset({"ar", "he", "fa", "ur"})
DATE_FIXE_ZIP = (2020, 1, 1, 0, 0, 0)


class FichierAltere(ValueError):
    """Le contenu stocké ne correspond plus à l'empreinte enregistrée."""


def _libelle(ligne: dict, langue: str) -> str:
    label = ligne.get("label")
    if isinstance(label, dict):
        return label.get(langue) or label.get("fr") or ligne["code"]
    return label or ligne["code"]


def _decimales(rapport: RapportPublie) -> int:
    code = rapport.params.get("devise")
    devise = Devise.objects.filter(code=code).first() if code else None
    return devise.decimales if devise else 2


def _format_nombre(decimales: int) -> str:
    return (
        "#,##0"
        + ("." + "0" * decimales if decimales else "")
        + ";[Red]-#,##0"
        + ("." + "0" * decimales if decimales else "")
    )


def _valeurs(rapport: RapportPublie) -> dict[str, dict[str, Decimal]]:
    sortie: dict[str, dict[str, Decimal]] = {}
    for cle, texte in rapport.values.items():
        rubrique, _, colonne = cle.partition("/")
        sortie.setdefault(rubrique, {})[colonne] = Decimal(texte)
    return sortie


def _colonnes(rapport: RapportPublie) -> list[str]:
    return [c["code"] for c in rapport.modele["columns"]]


def _zip_deterministe(contenu: bytes, modifie: str) -> bytes:
    """Réécrit un ZIP : dates d'entrée fixes, date de modification (openpyxl pose « maintenant »
    à l'enregistrement) fixée sur `modifie`. Mêmes données, mêmes octets."""
    sortie = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(contenu)) as source,
        zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as cible,
    ):
        for info in sorted(source.infolist(), key=lambda i: i.filename):
            nouveau = zipfile.ZipInfo(info.filename, date_time=DATE_FIXE_ZIP)
            nouveau.compress_type = zipfile.ZIP_DEFLATED
            nouveau.external_attr = info.external_attr
            donnees = source.read(info.filename)
            if info.filename == "docProps/core.xml":
                donnees = re.sub(
                    rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                    rb"\g<1>" + modifie.encode() + rb"\g<2>",
                    donnees,
                )
            cible.writestr(nouveau, donnees)
    return sortie.getvalue()


def rendre_excel(rapport: RapportPublie, langue: str) -> bytes:
    decimales = _decimales(rapport)
    valeurs, colonnes = _valeurs(rapport), _colonnes(rapport)
    classeur = openpyxl.Workbook()
    feuille = classeur.active
    # Un titre de feuille Excel : 31 caractères, sans / \\ ? * [ ] : (sinon openpyxl refuse).
    feuille.title = re.sub(r"[/\\?*\[\]:]", "-", rapport.template_code)[:31] or "Rapport"
    feuille.sheet_view.rightToLeft = langue in LANGUES_DROITE_A_GAUCHE
    feuille.append(["", *colonnes])
    for cellule in feuille[1]:
        cellule.font = Font(bold=True)
        cellule.alignment = Alignment(horizontal="center")
    for ligne in rapport.modele["rows"]:
        code = ligne["code"]
        if ligne.get("type") == "heading":
            feuille.append([f"{code} {_libelle(ligne, langue)}"])
            feuille.cell(feuille.max_row, 1).font = Font(bold=True)
            continue
        feuille.append(
            [f"{code} {_libelle(ligne, langue)}", *(valeurs[code][col] for col in colonnes)]
        )
        for cellule in feuille[feuille.max_row][1:]:
            cellule.number_format = _format_nombre(decimales)  # un NOMBRE, pas un texte
    feuille.column_dimensions["A"].width = 48
    feuille.freeze_panes = "B2"
    classeur.properties.creator = "SIGF"
    publie_le = rapport.published_at.replace(tzinfo=None, microsecond=0)
    classeur.properties.created = classeur.properties.modified = publie_le
    tampon = io.BytesIO()
    classeur.save(tampon)
    return _zip_deterministe(tampon.getvalue(), publie_le.isoformat() + "Z")


def rendre_pdf(rapport: RapportPublie, langue: str) -> bytes:
    if langue in LANGUES_DROITE_A_GAUCHE:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("exports.pdf_droite_a_gauche"))
    decimales = _decimales(rapport)
    valeurs, colonnes = _valeurs(rapport), _colonnes(rapport)
    doc = DocumentPDF(titre_court=rapport.template_code)
    doc.ajouter(rapport.template_code, "titre")
    doc.ajouter(
        f"{formater_date(rapport.period_from, langue)} — "
        f"{formater_date(rapport.period_to, langue)}",
        "normal",
    )
    doc.ajouter("SHA-256 " + bytes(rapport.seal).hex(), "petit")
    for ligne in rapport.modele["rows"]:
        code, titre = ligne["code"], _libelle(ligne, langue)
        if ligne.get("type") == "heading":
            doc.ajouter(f"{code} {titre}", "section")
            continue
        doc.ajouter(f"{code} {titre}", "sous_titre")
        doc.ajouter(
            "   ".join(
                f"{col}: {formater_montant(valeurs[code][col], langue, decimales)}"
                for col in colonnes
            ),
            "retrait",
        )
    return doc.octets()


RENDUS = {"xlsx": rendre_excel, "pdf": rendre_pdf}


def exporter_rapport(*, utilisateur, rapport: RapportPublie, format: str, langue: str = "fr"):
    """Produit (ou retrouve) le fichier du rapport dans ce format et cette langue."""
    if not est_habilite(utilisateur, "exporter", rapport.project_id):
        raise PermissionDenied(msg("exports.habilitation_exporter"))
    if format not in FORMATS:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("exports.format_inconnu", format=format))
    langue = (langue or "fr").strip().lower().replace("_", "-").split("-")[0]
    if langue not in LANGUES and langue not in LANGUES_DROITE_A_GAUCHE:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("exports.langue_inconnue", langue=langue))
    existant = FichierRapport.objects.filter(rapport=rapport, format=format, langue=langue).first()
    if existant is not None:
        return existant
    contenu = RENDUS[format](rapport, langue)
    try:
        with transaction.atomic():
            fichier = FichierRapport.objects.create(
                org_id=rapport.org_id,
                rapport=rapport,
                format=format,
                langue=langue,
                nom=f"{rapport.template_code}_{rapport.period_to.isoformat()}_{langue}.{format}",
                contenu=contenu,
                sha256=hashlib.sha256(contenu).hexdigest(),
                taille=len(contenu),
                produit_par=utilisateur.id,
                created_by=utilisateur.id,
            )
            journaliser(
                org_id=rapport.org_id,
                actor_id=utilisateur.id,
                action="report_file_produced",
                object_type="rapport_publie",
                object_id=rapport.id,
                project_id=rapport.project_id,
                after={"format": format, "langue": langue, "sha256": fichier.sha256},
            )
    except IntegrityError:
        # Un export simultané du même fichier l'a créé entre-temps : on rend celui-là.
        concurrent = FichierRapport.objects.filter(
            rapport=rapport, format=format, langue=langue
        ).first()
        if concurrent is None:
            raise
        return concurrent
    return fichier


def lire_fichier(*, utilisateur, fichier: FichierRapport) -> bytes:
    """Le contenu du fichier, après vérification de son empreinte enregistrée."""
    if not est_habilite(utilisateur, "exporter", fichier.rapport.project_id):
        raise PermissionDenied(msg("exports.habilitation_exporter"))
    contenu = bytes(fichier.contenu)
    if hashlib.sha256(contenu).hexdigest() != fichier.sha256:
        raise FichierAltere(msg("exports.fichier_altere", nom=fichier.nom))
    return contenu
