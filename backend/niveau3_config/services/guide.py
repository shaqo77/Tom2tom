"""Le guide de configuration d'un projet, en PDF lisible. Voir L5-T07.

Depuis le registre : chaque exigence ACTIVE à la date, sa source (document, version, paragraphe,
extrait), ce qu'elle justifie (mappings, rubriques, contrôles rattachés), sa périodicité, son
délai, son validateur ; les profils de décaissement en vigueur ; ce qui est encore seulement
proposé (donc non appliqué) ; et ce qui est configuré sans source.

Pourquoi : les équipes d'unités de gestion tournent. Le savoir du paramétrage doit rester dans le
système et s'imprimer, pas chez un consultant. Un comptable qui n'a jamais vu le logiciel doit
pouvoir y lire POURQUOI chaque rubrique existe.

Le guide est une fonction de la configuration résolue à une date (L5-T04) : mêmes données, même
date, mêmes octets. Son empreinte et celle de la configuration sont écrites au pied du document.
"""

import datetime
import hashlib
from dataclasses import dataclass, field

from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from niveau1_socle.financements.models import Accord
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.organisations.models import Projet, Utilisateur

from ..models import (
    Exigence,
    Obligation,
    ProfilDecaissement,
    RattachementExigence,
    StatutExigence,
    TypeCible,
)
from .activation import resoudre_configuration
from .decaissement import profil_en_vigueur
from .pdf_minimal import DocumentPDF
from .rattachement import SOURCES, detecter_configuration_orpheline

PERIODICITES = {
    "monthly": "mensuelle",
    "quarterly": "trimestrielle",
    "semiannual": "semestrielle",
    "annual": "annuelle",
    "event": "sur événement",
}
OBLIGATIONS = {
    "mandatory": "obligatoire",
    "conditional": "conditionnelle",
    "optional": "facultative",
}
TYPES_CIBLE = {
    TypeCible.MODELE_ETAT: "Modèle d'état",
    TypeCible.RUBRIQUE: "Rubrique d'état",
    TypeCible.MAPPING: "Mapping",
    TypeCible.CONTROLE: "Contrôle",
    TypeCible.CHAMP: "Champ",
}
REGIMES = {"transaction_based": "sur transactions", "report_based": "sur rapport"}
METHODES = {
    "advance": "avance",
    "reimbursement": "remboursement",
    "direct_payment": "paiement direct",
    "special_commitment": "engagement spécial",
}
PIECES = {
    "soe": "état certifié des dépenses",
    "records": "copies des pièces",
    "ifr": "rapport financier intermédiaire",
    "summary_sheet": "fiche récapitulative",
}
ASSIETTES = {"net_of_taxes": "hors taxes", "taxes_included": "taxes comprises"}


@dataclass
class EntreeExigence:
    code: str
    version: int
    sujet: str
    obligation: str
    condition: str | None
    periodicite: str
    delai: str
    valable_du: datetime.date
    valable_jusquau: datetime.date | None
    document: str
    citation: str
    validateur: str
    valide_le: str
    origine: str
    justifie: list[str]


@dataclass
class Guide:
    projet: str
    date: datetime.date
    empreinte_configuration: str
    exigences: list[EntreeExigence] = field(default_factory=list)
    profils: list[dict] = field(default_factory=list)
    en_attente: list[tuple[str, str, str]] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)


def _montant(valeur) -> str:
    """1 234 567,89 : milliers séparés par une espace, virgule décimale."""
    entier, _, decimales = f"{valeur:,.2f}".partition(".")
    return f"{entier.replace(',', ' ')},{decimales}"


def _pourcentage(taux) -> str:
    return f"{(taux * 100).normalize():f}".replace(".", ",") + " %"


def _nom(utilisateur_id) -> str:
    if utilisateur_id is None:
        return "non renseigné"
    utilisateur = Utilisateur.objects.filter(pk=utilisateur_id).first()
    return utilisateur.get_username() if utilisateur else f"utilisateur {utilisateur_id}"


def _libelles_des_cibles(project_id, date) -> dict:
    libelles = {}
    for type_cible, source in SOURCES.items():
        for cible_id, libelle in source.lister_actifs(project_id, date):
            libelles[(type_cible, cible_id)] = libelle
    return libelles


def _citation(exigence: Exigence) -> str:
    c = exigence.citation
    reperes = [
        f"{nom} {c[cle]}"
        for cle, nom in (("annex", "annexe"), ("page", "page"), ("paragraph", "§"))
        if c.get(cle) not in (None, "")
    ]
    return f"{', '.join(reperes)} : « {c.get('quote', '').strip()} »"


def construire_guide(project_id, date: datetime.date) -> Guide:
    projet = Projet.objects.get(pk=project_id)
    configuration = resoudre_configuration(project_id, date)
    guide = Guide(
        projet=f"{projet.code} — {next(iter(projet.label.values()))}",
        date=date,
        empreinte_configuration=configuration.empreinte,
    )
    libelles = _libelles_des_cibles(project_id, date)
    ids = [identifiant for _, _, identifiant in configuration.exigences]
    for exigence in (
        Exigence.objects.filter(pk__in=ids).select_related("document").order_by("code", "version")
    ):
        justifie = []
        for rattachement in RattachementExigence.objects.filter(exigence=exigence).order_by(
            "target_type", "created_at"
        ):
            type_fr = TYPES_CIBLE.get(rattachement.target_type, rattachement.target_type)
            libelle = libelles.get(
                (rattachement.target_type, rattachement.target_id),
                f"réf. {str(rattachement.target_id)[:8]}",
            )
            justifie.append(f"{type_fr} : {libelle}")
        document = exigence.document
        guide.exigences.append(
            EntreeExigence(
                code=exigence.code,
                version=exigence.version,
                sujet=exigence.subject,
                obligation=OBLIGATIONS.get(exigence.obligation, exigence.obligation),
                condition=exigence.condition_expr
                if exigence.obligation == Obligation.CONDITIONNELLE
                else None,
                periodicite=PERIODICITES.get(exigence.periodicity or "", "non précisée"),
                delai=(
                    f"{exigence.due_offset_days} jours après la fin de la période"
                    if exigence.due_offset_days is not None
                    else "non précisé"
                ),
                valable_du=exigence.valid_from,
                valable_jusquau=exigence.valid_to,
                document=f"{document.title}"
                + (f" (version {document.version})" if document.version else ""),
                citation=_citation(exigence),
                validateur=_nom(exigence.validated_by),
                valide_le=(
                    exigence.validated_at.date().strftime("%d/%m/%Y")
                    if exigence.validated_at
                    else ""
                ),
                origine=(
                    "issue d'un profil de bailleur, étayée par le document du projet"
                    if exigence.donor_profile_id
                    else "saisie pour ce projet"
                ),
                justifie=justifie,
            )
        )
    for accord in Accord.objects.filter(project_id=project_id).order_by("numero"):
        profil = profil_en_vigueur(accord, date)
        if profil is not None:
            guide.profils.append(_decrire_profil(accord, profil))
    for exigence in Exigence.objects.filter(
        project_id=project_id, status__in=[StatutExigence.PROPOSEE, StatutExigence.VALIDEE]
    ).order_by("code", "version"):
        guide.en_attente.append((exigence.code, exigence.subject, exigence.status))
    for orphelin in detecter_configuration_orpheline(project_id, date):
        guide.anomalies.append(
            f"{TYPES_CIBLE.get(orphelin.target_type, orphelin.target_type)} "
            f"« {orphelin.libelle} » : {orphelin.raison}"
        )
    return guide


def _decrire_profil(accord: Accord, profil: ProfilDecaissement) -> dict:
    return {
        "accord": accord.numero,
        "version": profil.version,
        "valable_du": profil.valid_from,
        "valable_jusquau": profil.valid_to,
        "regime": REGIMES.get(profil.regime, profil.regime),
        "jalons": {
            "entrée en vigueur": profil.effectiveness_date,
            "début d'éligibilité des dépenses": profil.eligibility_date,
            "clôture": profil.closing_date,
            "limite de décaissement": profil.disbursement_deadline,
        },
        "methodes": [
            f"{METHODES.get(m.method, m.method)}"
            + ("" if m.is_enabled else " (désactivée)")
            + (
                " — pièces exigées : " + ", ".join(PIECES.get(p, p) for p in m.supporting_docs)
                if m.supporting_docs
                else ""
            )
            for m in profil.methodes.order_by("method")
        ],
        "regles": [
            f"{r.category.code} : {_pourcentage(r.funding_rate)} "
            f"({ASSIETTES.get(r.tax_basis, '')}) ; allocation {_montant(r.allocation)}"
            for r in profil.regles.select_related("category").order_by("category__code")
        ],
        "comptes": [
            "Compte désigné, plafond "
            + (
                f"{_montant(c.ceiling_amount)} {c.currency_id}"
                if c.ceiling_kind == "fixed"
                else "variable"
            )
            for c in profil.comptes.all()
        ],
    }


def rendre_pdf(guide: Guide) -> bytes:
    doc = DocumentPDF(titre_court=f"Guide de configuration — {guide.projet}")
    doc.ajouter("Guide de configuration", "titre")
    doc.ajouter(guide.projet, "section")
    doc.ajouter(f"Configuration en vigueur au {guide.date.strftime('%d/%m/%Y')}", "normal")
    doc.ajouter(
        "Ce document est produit par le système à partir du registre des exigences. Il explique "
        "POURQUOI chaque élément de la configuration existe : chaque exigence active renvoie à un "
        "paragraphe d'un document contractuel du projet, et a été validée par une personne "
        "nommée.",
        "normal",
    )
    doc.ajouter(f"Empreinte de la configuration : {guide.empreinte_configuration}", "petit")

    doc.ajouter(f"1. Exigences actives ({len(guide.exigences)})", "section")
    if not guide.exigences:
        doc.ajouter("Aucune exigence n'est active à cette date.", "normal")
    for e in guide.exigences:
        doc.ajouter(f"{e.code} (version {e.version}) — {e.sujet}", "sous_titre")
        obligation = e.obligation + (f" — condition : {e.condition}" if e.condition else "")
        fin = f" au {e.valable_jusquau.strftime('%d/%m/%Y')} (exclu)" if e.valable_jusquau else ""
        doc.ajouter(f"Nature : {obligation}", "retrait")
        doc.ajouter(f"Périodicité : {e.periodicite} ; délai : {e.delai}", "retrait")
        doc.ajouter(f"En vigueur depuis le {e.valable_du.strftime('%d/%m/%Y')}{fin}", "retrait")
        doc.ajouter(f"Source : {e.document}", "retrait")
        doc.ajouter(f"Passage cité : {e.citation}", "retrait")
        doc.ajouter(f"Validée par {e.validateur}, le {e.valide_le} ; {e.origine}.", "retrait")
        if e.justifie:
            doc.ajouter("Ce que cette exigence justifie :", "retrait")
            for ligne in e.justifie:
                doc.ajouter(f"- {ligne}", "retrait")
        else:
            doc.ajouter("Elle ne justifie encore aucun objet de configuration.", "retrait")

    doc.ajouter(f"2. Profils de décaissement en vigueur ({len(guide.profils)})", "section")
    if not guide.profils:
        doc.ajouter("Aucun profil de décaissement n'est en vigueur à cette date.", "normal")
    for p in guide.profils:
        fin = (
            f" au {p['valable_jusquau'].strftime('%d/%m/%Y')} (exclu)"
            if p["valable_jusquau"]
            else ""
        )
        doc.ajouter(f"Accord {p['accord']} — version {p['version']}", "sous_titre")
        doc.ajouter(
            f"En vigueur depuis le {p['valable_du'].strftime('%d/%m/%Y')}{fin} ; "
            f"régime de décaissement : {p['regime']}",
            "retrait",
        )
        for nom, valeur in p["jalons"].items():
            if valeur:
                doc.ajouter(f"{nom} : {valeur.strftime('%d/%m/%Y')}", "retrait")
        for ligne in p["methodes"]:
            doc.ajouter(f"Méthode : {ligne}", "retrait")
        for ligne in p["regles"]:
            doc.ajouter(f"Taux de financement, catégorie {ligne}", "retrait")
        for ligne in p["comptes"]:
            doc.ajouter(ligne, "retrait")

    doc.ajouter(f"3. Propositions en attente ({len(guide.en_attente)})", "section")
    doc.ajouter(
        "Ces exigences ne sont PAS appliquées : elles attendent d'être étayées, validées puis "
        "activées par une personne habilitée.",
        "normal",
    )
    for code, sujet, statut in guide.en_attente:
        doc.ajouter(
            f"- {code} — {sujet} ({'proposée' if statut == 'proposed' else 'validée'})", "retrait"
        )

    doc.ajouter(f"4. Points d'attention ({len(guide.anomalies)})", "section")
    if not guide.anomalies:
        doc.ajouter("Toute la configuration active a son exigence source.", "normal")
    for ligne in guide.anomalies:
        doc.ajouter(f"- {ligne}", "retrait")
    return doc.octets()


def generer_guide(*, utilisateur, project_id, date: datetime.date) -> bytes:
    """Le PDF du guide ; l'opération est journalisée avec l'empreinte du document produit."""
    if not est_habilite(utilisateur, "consulter", project_id):
        raise PermissionDenied("Vous n'êtes pas habilité à « consulter » ce projet.")
    guide = construire_guide(project_id, date)
    contenu = rendre_pdf(guide)
    journaliser(
        org_id=utilisateur.org_id,
        actor_id=utilisateur.id,
        action="configuration_guide_generated",
        object_type="projet",
        object_id=project_id,
        project_id=project_id,
        after={
            "date": date.isoformat(),
            "sha256": hashlib.sha256(contenu).hexdigest(),
            "configuration": guide.empreinte_configuration,
        },
    )
    return contenu
