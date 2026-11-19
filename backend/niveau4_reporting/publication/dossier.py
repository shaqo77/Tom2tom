"""Le dossier de conformité d'un rapport publié. Voir L7-T01.

Pour chaque rubrique du rapport : l'exigence qui la justifie, SA CITATION exacte (document,
version, annexe, page, paragraphe, texte), la règle appliquée, le mapping utilisé et sa version, le
validateur et la date de validation.

D'où vient l'exigence d'une rubrique :
- une rubrique d'agrégat qui sélectionne par un MAPPING hérite des exigences rattachées à la
  version de ce mapping (L5-T03) ;
- une rubrique calculée hérite de celles des rubriques dont sa formule dépend ;
- une rubrique d'agrégat qui sélectionne des comptes SANS mapping n'a aucune source : elle est
  NOMMÉE dans la section « sans exigence source », jamais passée sous silence ;
- un intitulé (`heading`) ne porte aucune valeur : il n'est pas une rubrique à couvrir.

Les exigences retenues sont celles en vigueur à la date de publication du rapport (actives, ou
remplacées depuis) : le dossier d'un rapport ne change pas quand l'exigence est révisée plus tard.
Le dossier porte le scellé du rapport ; son propre PDF est enregistré avec son empreinte.
"""

import datetime
import hashlib
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.i18n import Localise, formater_date, msg, normaliser_langue
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.organisations.models import Utilisateur
from niveau3_config.models import RattachementExigence, StatutExigence, TypeCible
from niveau3_config.services.pdf_minimal import DocumentPDF
from niveau4_reporting.moteur.formules import references

from .models import FichierRapport, RapportPublie


@dataclass(frozen=True)
class SourceExigence:
    code: str
    version: int
    document: str
    document_version: str
    citation: dict
    validateur: str
    valide_le: datetime.date | None


@dataclass
class LigneDossier:
    code: str
    libelle: dict
    regle: str  # une description neutre : « mapping WB/CHARGES », « comptes … », « R110 + R120 »
    mapping: str | None  # « WB v2 »
    sources: list[SourceExigence] = field(default_factory=list)

    @property
    def couverte(self) -> bool:
        return bool(self.sources)


@dataclass
class Dossier:
    rapport_code: str
    periode: tuple[datetime.date, datetime.date]
    scelle: str  # le SHA-256 du rapport, en hexadécimal
    lignes: list[LigneDossier]

    @property
    def non_couvertes(self) -> list[LigneDossier]:
        return [ligne for ligne in self.lignes if not ligne.couverte]

    @property
    def taux_couverture(self) -> Decimal:
        return Decimal(len(self.lignes) - len(self.non_couvertes)) / Decimal(len(self.lignes))


def _sources_du_mapping(rapport: RapportPublie, code_mapping: str) -> list[SourceExigence]:
    reference = rapport.mapping_versions.get(code_mapping)
    if reference is None:
        return []
    jour = rapport.published_at.date()
    rattachements = (
        RattachementExigence.objects.filter(
            target_type=TypeCible.MAPPING,
            target_id=reference["id"],
            exigence__status__in=[StatutExigence.ACTIVE, StatutExigence.REMPLACEE],
            exigence__valid_from__lte=jour,
        )
        .filter(Q(exigence__valid_to__isnull=True) | Q(exigence__valid_to__gt=jour))
        .select_related("exigence", "exigence__document")
        .order_by("exigence__code", "exigence__version")
    )
    noms = {
        u.pk: u.get_username()
        for u in Utilisateur.objects.filter(
            pk__in=[r.exigence.validated_by for r in rattachements if r.exigence.validated_by]
        )
    }
    return [
        SourceExigence(
            code=r.exigence.code,
            version=r.exigence.version,
            document=r.exigence.document.title,
            document_version=r.exigence.document.version,
            citation=r.exigence.citation,
            validateur=noms.get(r.exigence.validated_by, str(r.exigence.validated_by)),
            valide_le=r.exigence.validated_at.date() if r.exigence.validated_at else None,
        )
        for r in rattachements
    ]


def regle_de_la_rubrique(rapport: RapportPublie, code: str) -> str:
    """La règle appliquée à une rubrique, décrite lisiblement, SANS interroger la base."""
    ligne = next((r for r in rapport.modele["rows"] if r["code"] == code), None)
    if ligne is None:
        return ""
    if ligne["type"] == "computed":
        return f"formule {ligne['formula']}"
    selection = ligne.get("select") or {}
    mapping = selection.get("mapping")
    if mapping:
        reference = rapport.mapping_versions.get(mapping)
        version = f"{mapping} v{reference['version']}" if reference else mapping
        return f"mapping {version} → {selection.get('target', '')}"
    return f"comptes {selection.get('accounts') or selection}"


def construire_dossier(rapport: RapportPublie) -> Dossier:
    """Les lignes du dossier, une par rubrique portant une valeur, dans l'ordre du modèle."""
    rubriques = [ligne for ligne in rapport.modele["rows"] if ligne.get("type") != "heading"]
    codes = [ligne["code"] for ligne in rapport.modele["rows"]]
    par_code: dict[str, LigneDossier] = {}
    # Les rubriques d'agrégat d'abord (leurs sources viennent des mappings), puis les calculées
    # dans l'ordre de leurs dépendances (une calculée peut citer une autre calculée).
    for ligne in rubriques:
        if ligne["type"] != "aggregate":
            continue
        selection = ligne.get("select") or {}
        code_mapping = selection.get("mapping")
        if code_mapping:
            reference = rapport.mapping_versions.get(code_mapping)
            version = f"{code_mapping} v{reference['version']}" if reference else code_mapping
            par_code[ligne["code"]] = LigneDossier(
                ligne["code"],
                ligne.get("label") or {},
                f"mapping {version} → {selection.get('target', '')}",
                version,
                _sources_du_mapping(rapport, code_mapping),
            )
        else:
            comptes = selection.get("accounts") or selection
            par_code[ligne["code"]] = LigneDossier(
                ligne["code"], ligne.get("label") or {}, f"comptes {comptes}", None, []
            )
    restantes = [ligne for ligne in rubriques if ligne["type"] == "computed"]
    while restantes:
        avancement = False
        for ligne in list(restantes):
            dependances = references(ligne["formula"], codes)
            if not all(d in par_code or _est_intitule(rapport, d) for d in dependances):
                continue
            sources, vues = [], set()
            for d in sorted(dependances):
                for source in par_code[d].sources if d in par_code else []:
                    if (source.code, source.version) not in vues:
                        vues.add((source.code, source.version))
                        sources.append(source)
            par_code[ligne["code"]] = LigneDossier(
                ligne["code"],
                ligne.get("label") or {},
                f"formule {ligne['formula']}",
                None,
                sources,
            )
            restantes.remove(ligne)
            avancement = True
        if not avancement:  # une dépendance introuvable : le modèle est invalide, on le dit
            raise ValueError(
                msg("dossier.dependance_introuvable", v1=[r["code"] for r in restantes])
            )
    return Dossier(
        rapport_code=rapport.template_code,
        periode=(rapport.period_from, rapport.period_to),
        scelle=bytes(rapport.seal).hex(),
        lignes=[par_code[ligne["code"]] for ligne in rubriques],
    )


def _est_intitule(rapport: RapportPublie, code: str) -> bool:
    return any(r["code"] == code and r.get("type") == "heading" for r in rapport.modele["rows"])


def rendre_pdf(dossier: Dossier, langue: str) -> bytes:
    def t(cle, **params):
        return msg(cle, **params).rendre(langue)

    doc = DocumentPDF(titre_court=t("dossier.pied", rapport=dossier.rapport_code))
    doc.ajouter(t("dossier.titre", rapport=dossier.rapport_code), "titre")
    doc.ajouter(
        t(
            "dossier.periode",
            du=formater_date(dossier.periode[0], langue),
            au=formater_date(dossier.periode[1], langue),
        ),
        "normal",
    )
    doc.ajouter(t("dossier.scelle", empreinte=dossier.scelle), "petit")
    couvertes = len(dossier.lignes) - len(dossier.non_couvertes)
    doc.ajouter(t("dossier.couverture", couvertes=couvertes, total=len(dossier.lignes)), "section")
    for ligne in dossier.lignes:
        if not ligne.couverte:
            continue
        libelle = Localise(ligne.libelle).rendre(langue) if ligne.libelle else ""
        doc.ajouter(f"{ligne.code} {libelle}".strip(), "sous_titre")
        doc.ajouter(t("dossier.regle", regle=ligne.regle), "retrait")
        for s in ligne.sources:
            doc.ajouter(t("dossier.exigence", code=s.code, version=s.version), "retrait")
            document = (
                t("dossier.document_version", titre=s.document, version=s.document_version)
                if s.document_version
                else s.document
            )
            reperes = ", ".join(
                t(cle, valeur=s.citation[champ])
                for champ, cle in (
                    ("annex", "dossier.annexe"),
                    ("page", "dossier.page"),
                    ("paragraph", "dossier.paragraphe"),
                )
                if s.citation.get(champ) not in (None, "")
            )
            doc.ajouter(t("dossier.source", document=document, reperes=reperes), "retrait")
            doc.ajouter(
                t("dossier.citation", extrait=s.citation.get("quote", "").strip()), "retrait"
            )
            doc.ajouter(
                t(
                    "dossier.validation",
                    nom=s.validateur,
                    date=formater_date(s.valide_le, langue) if s.valide_le else "—",
                ),
                "retrait",
            )
    if dossier.non_couvertes:
        doc.ajouter(t("dossier.section_sans_source", n=len(dossier.non_couvertes)), "section")
        for ligne in dossier.non_couvertes:
            libelle = Localise(ligne.libelle).rendre(langue) if ligne.libelle else ""
            doc.ajouter(
                t("dossier.ligne_sans_source", code=ligne.code, libelle=libelle, regle=ligne.regle),
                "retrait",
            )
    return doc.octets()


def exporter_dossier(*, utilisateur, rapport: RapportPublie, langue: str = "fr") -> FichierRapport:
    """Produit (ou retrouve) le PDF du dossier de conformité, avec son empreinte."""
    if not est_habilite(utilisateur, "exporter", rapport.project_id):
        raise PermissionDenied(msg("exports.habilitation_exporter"))
    langue = normaliser_langue(langue)
    filtre = {"rapport": rapport, "nature": "dossier", "format": "pdf", "langue": langue}
    existant = FichierRapport.objects.filter(**filtre).first()
    if existant is not None:
        return existant
    contenu = rendre_pdf(construire_dossier(rapport), langue)
    try:
        with transaction.atomic():
            fichier = FichierRapport.objects.create(
                org_id=rapport.org_id,
                nature="dossier",
                format="pdf",
                langue=langue,
                rapport=rapport,
                nom=f"conformite_{rapport.template_code}_{rapport.period_to.isoformat()}_{langue}.pdf",
                contenu=contenu,
                sha256=hashlib.sha256(contenu).hexdigest(),
                taille=len(contenu),
                produit_par=utilisateur.id,
                created_by=utilisateur.id,
            )
            journaliser(
                org_id=rapport.org_id,
                actor_id=utilisateur.id,
                action="compliance_file_produced",
                object_type="rapport_publie",
                object_id=rapport.id,
                project_id=rapport.project_id,
                after={"langue": langue, "sha256": fichier.sha256},
            )
    except IntegrityError:
        concurrent = FichierRapport.objects.filter(**filtre).first()
        if concurrent is None:
            raise
        return concurrent
    return fichier
