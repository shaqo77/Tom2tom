"""Le guide de configuration d'un projet, en PDF lisible, en français ou en anglais. Voir L5-T07.

Depuis le registre : chaque exigence ACTIVE à la date, sa source (document, version, paragraphe,
extrait), ce qu'elle justifie (mappings, rubriques, contrôles rattachés), sa périodicité, son
délai, son validateur ; les profils de décaissement en vigueur ; ce qui est encore seulement
proposé (donc non appliqué) ; et ce qui est configuré sans source.

Pourquoi : les équipes d'unités de gestion tournent. Le savoir du paramétrage doit rester dans le
système et s'imprimer, pas chez un consultant. Un comptable qui n'a jamais vu le logiciel doit
pouvoir y lire POURQUOI chaque rubrique existe.

Le guide est une fonction de la configuration résolue à une date (L5-T04) ET d'une langue : mêmes
données, même date, même langue, mêmes octets. Les données du guide sont NEUTRES (codes, dates,
montants) ; chaque texte passe par le catalogue de messages (`core/locales`) au moment du rendu,
chaque libellé d'ensemble fermé par `libelle_valeur`, chaque date et montant par les formats de la
langue. Son empreinte et celle de la configuration sont écrites au pied du document.
"""

import datetime
import hashlib
from dataclasses import dataclass, field

from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.i18n import (
    Localise,
    formater_date,
    formater_montant,
    formater_pourcentage,
    langue_courante,
    libelle,
    libelle_valeur,
    msg,
    normaliser_langue,
)
from niveau1_socle.financements.models import Accord
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.organisations.models import Projet, Utilisateur

from ..models import (
    AssietteTaxes,
    Exigence,
    MethodeDecaissementCode,
    Obligation,
    Periodicite,
    ProfilDecaissement,
    RattachementExigence,
    RegimeDecaissement,
    StatutExigence,
    TypeCible,
)
from .activation import resoudre_configuration
from .decaissement import profil_en_vigueur
from .pdf_minimal import DocumentPDF
from .rattachement import SOURCES, detecter_configuration_orpheline


@dataclass
class EntreeExigence:
    code: str
    version: int
    sujet: str
    obligation: str
    condition: str | None
    periodicite: str | None
    delai_jours: int | None
    valable_du: datetime.date
    valable_jusquau: datetime.date | None
    document_titre: str
    document_version: str
    citation: dict
    validateur_id: object
    valide_le: datetime.date | None
    issue_profil: bool
    justifie: list = field(default_factory=list)  # [(type de cible, libellé ou None, réf.)]


@dataclass
class Guide:
    projet: str
    date: datetime.date
    empreinte_configuration: str
    exigences: list[EntreeExigence] = field(default_factory=list)
    profils: list[dict] = field(default_factory=list)
    en_attente: list[tuple[str, str, str]] = field(default_factory=list)
    anomalies: list[tuple] = field(default_factory=list)  # [(type de cible, libellé, raison)]
    noms: dict = field(default_factory=dict)  # identifiant d'utilisateur -> nom d'utilisateur


_CLES_JALONS = {
    "effectiveness_date": "guide.jalon_effectiveness_date",
    "eligibility_date": "guide.jalon_eligibility_date",
    "closing_date": "guide.jalon_closing_date",
    "disbursement_deadline": "guide.jalon_disbursement_deadline",
}


def _libelles_des_cibles(project_id, date) -> dict:
    libelles = {}
    for type_cible, source in SOURCES.items():
        for cible_id, intitule in source.lister_actifs(project_id, date):
            libelles[(type_cible, cible_id)] = intitule
    return libelles


def construire_guide(project_id, date: datetime.date) -> Guide:
    """Les données du guide, sans aucun texte de langue : c'est `rendre_pdf` qui parle."""
    projet = Projet.objects.get(pk=project_id)
    configuration = resoudre_configuration(project_id, date)
    guide = Guide(
        projet=f"{projet.code} — " + "{label}",
        date=date,
        empreinte_configuration=configuration.empreinte,
    )
    guide.projet_label = projet.label  # le libellé du projet est multilingue (JSONB)
    libelles = _libelles_des_cibles(project_id, date)
    ids = [identifiant for _, _, identifiant in configuration.exigences]
    for exigence in (
        Exigence.objects.filter(pk__in=ids).select_related("document").order_by("code", "version")
    ):
        justifie = []
        for rattachement in RattachementExigence.objects.filter(exigence=exigence).order_by(
            "target_type", "created_at"
        ):
            justifie.append(
                (
                    rattachement.target_type,
                    libelles.get((rattachement.target_type, rattachement.target_id)),
                    str(rattachement.target_id)[:8],
                )
            )
        document = exigence.document
        guide.exigences.append(
            EntreeExigence(
                code=exigence.code,
                version=exigence.version,
                sujet=exigence.subject,
                obligation=exigence.obligation,
                condition=exigence.condition_expr
                if exigence.obligation == Obligation.CONDITIONNELLE
                else None,
                periodicite=exigence.periodicity,
                delai_jours=exigence.due_offset_days,
                valable_du=exigence.valid_from,
                valable_jusquau=exigence.valid_to,
                document_titre=document.title,
                document_version=document.version or "",
                citation=exigence.citation,
                validateur_id=exigence.validated_by,
                valide_le=exigence.validated_at.date() if exigence.validated_at else None,
                issue_profil=bool(exigence.donor_profile_id),
                justifie=justifie,
            )
        )
    guide.noms = {
        u.pk: u.get_username()
        for u in Utilisateur.objects.filter(
            pk__in={e.validateur_id for e in guide.exigences if e.validateur_id}
        )
    }
    for accord in Accord.objects.filter(project_id=project_id).order_by("numero"):
        profil = profil_en_vigueur(accord, date)
        if profil is not None:
            guide.profils.append(_decrire_profil(accord, profil))
    for exigence in Exigence.objects.filter(
        project_id=project_id, status__in=[StatutExigence.PROPOSEE, StatutExigence.VALIDEE]
    ).order_by("code", "version"):
        guide.en_attente.append((exigence.code, exigence.subject, exigence.status))
    for orphelin in detecter_configuration_orpheline(project_id, date):
        guide.anomalies.append((orphelin.target_type, orphelin.libelle, orphelin.raison))
    return guide


def _decrire_profil(accord: Accord, profil: ProfilDecaissement) -> dict:
    return {
        "accord": accord.numero,
        "version": profil.version,
        "valable_du": profil.valid_from,
        "valable_jusquau": profil.valid_to,
        "regime": profil.regime,
        "jalons": {
            "effectiveness_date": profil.effectiveness_date,
            "eligibility_date": profil.eligibility_date,
            "closing_date": profil.closing_date,
            "disbursement_deadline": profil.disbursement_deadline,
        },
        "methodes": [
            (m.method, m.is_enabled, list(m.supporting_docs))
            for m in profil.methodes.order_by("method")
        ],
        "regles": [
            (r.category.code, r.funding_rate, r.tax_basis, r.allocation)
            for r in profil.regles.select_related("category").order_by("category__code")
        ],
        "comptes": [
            (c.ceiling_kind, c.ceiling_amount, c.currency_id) for c in profil.comptes.all()
        ],
    }


def rendre_pdf(guide: Guide, langue: str | None = None) -> bytes:
    """Le PDF du guide dans `langue` (sinon la langue active)."""
    langue = normaliser_langue(langue) if langue else langue_courante()

    def t(cle, **params):
        return msg(cle, **params).rendre(langue)

    def mot(classe, valeur):  # un libellé d'ensemble fermé, en minuscules dans une phrase
        return libelle_valeur(classe, valeur, langue).lower()

    def jour(date):
        return formater_date(date, langue)

    projet = f"{guide.projet.split(' — ')[0]} — {Localise(guide.projet_label).rendre(langue)}"
    doc = DocumentPDF(titre_court=t("guide.pied", projet=projet))
    doc.ajouter(t("guide.titre"), "titre")
    doc.ajouter(projet, "section")
    doc.ajouter(t("guide.date_vigueur", date=jour(guide.date)), "normal")
    doc.ajouter(t("guide.introduction"), "normal")
    doc.ajouter(t("guide.empreinte", empreinte=guide.empreinte_configuration), "petit")

    doc.ajouter(t("guide.section_exigences", n=len(guide.exigences)), "section")
    if not guide.exigences:
        doc.ajouter(t("guide.aucune_exigence"), "normal")
    for e in guide.exigences:
        doc.ajouter(
            t("guide.exigence_titre", code=e.code, version=e.version, sujet=e.sujet), "sous_titre"
        )
        nature = mot(Obligation, e.obligation)
        doc.ajouter(
            t("guide.nature_conditionnelle", nature=nature, condition=e.condition)
            if e.condition
            else t("guide.nature", nature=nature),
            "retrait",
        )
        periodicite = (
            mot(Periodicite, e.periodicite)
            if e.periodicite
            else t("guide.periodicite_non_precisee")
        )
        delai = (
            t("guide.delai_jours", n=e.delai_jours)
            if e.delai_jours is not None
            else t("guide.delai_non_precise")
        )
        doc.ajouter(t("guide.periodicite_delai", periodicite=periodicite, delai=delai), "retrait")
        doc.ajouter(
            t("guide.vigueur_fin", debut=jour(e.valable_du), fin=jour(e.valable_jusquau))
            if e.valable_jusquau
            else t("guide.vigueur", debut=jour(e.valable_du)),
            "retrait",
        )
        titre = (
            t("guide.document_version", titre=e.document_titre, version=e.document_version)
            if e.document_version
            else e.document_titre
        )
        doc.ajouter(t("guide.source", document=titre), "retrait")
        reperes = ", ".join(
            t(cle, valeur=e.citation[champ])
            for champ, cle in (
                ("annex", "guide.annexe"),
                ("page", "guide.page"),
                ("paragraph", "guide.paragraphe"),
            )
            if e.citation.get(champ) not in (None, "")
        )
        extrait = e.citation.get("quote", "").strip()
        doc.ajouter(
            t("guide.passage_cite", citation=t("guide.citation", reperes=reperes, extrait=extrait)),
            "retrait",
        )
        nom = (
            guide.noms.get(e.validateur_id) or t("guide.utilisateur_inconnu", id=e.validateur_id)
            if e.validateur_id
            else t("guide.nom_non_renseigne")
        )
        doc.ajouter(
            t(
                "guide.validation",
                nom=nom,
                date=jour(e.valide_le) if e.valide_le else "",
                origine=t("guide.origine_profil" if e.issue_profil else "guide.origine_projet"),
            ),
            "retrait",
        )
        if e.justifie:
            doc.ajouter(t("guide.justifie_titre"), "retrait")
            for type_cible, intitule, ref in e.justifie:
                doc.ajouter(
                    t(
                        "guide.justifie_ligne",
                        type=libelle_valeur(TypeCible, type_cible, langue),
                        libelle=intitule or t("guide.cible_ref", ref=ref),
                    ),
                    "retrait",
                )
        else:
            doc.ajouter(t("guide.justifie_rien"), "retrait")

    doc.ajouter(t("guide.section_profils", n=len(guide.profils)), "section")
    if not guide.profils:
        doc.ajouter(t("guide.aucun_profil"), "normal")
    for p in guide.profils:
        doc.ajouter(t("guide.profil_titre", accord=p["accord"], version=p["version"]), "sous_titre")
        regime = mot(RegimeDecaissement, p["regime"])
        doc.ajouter(
            t(
                "guide.profil_vigueur_fin",
                debut=jour(p["valable_du"]),
                fin=jour(p["valable_jusquau"]),
                regime=regime,
            )
            if p["valable_jusquau"]
            else t("guide.profil_vigueur", debut=jour(p["valable_du"]), regime=regime),
            "retrait",
        )
        for champ, valeur in p["jalons"].items():
            if valeur:
                doc.ajouter(
                    t("guide.jalon_ligne", nom=t(_CLES_JALONS[champ]), date=jour(valeur)),
                    "retrait",
                )
        for methode, active, pieces in p["methodes"]:
            doc.ajouter(
                t(
                    "guide.methode_ligne",
                    methode=mot(MethodeDecaissementCode, methode),
                    etat="" if active else t("guide.methode_desactivee"),
                    pieces=t(
                        "guide.methode_pieces",
                        pieces=", ".join(libelle("piece_exigee", x, langue) for x in pieces),
                    )
                    if pieces
                    else "",
                ),
                "retrait",
            )
        for code, taux, assiette, allocation in p["regles"]:
            doc.ajouter(
                t(
                    "guide.regle_taux",
                    code=code,
                    taux=formater_pourcentage(taux, langue),
                    assiette=mot(AssietteTaxes, assiette),
                    allocation=formater_montant(allocation, langue),
                ),
                "retrait",
            )
        for genre, plafond, devise in p["comptes"]:
            doc.ajouter(
                t(
                    "guide.compte_designe",
                    plafond=t(
                        "guide.plafond_fixe",
                        montant=formater_montant(plafond, langue),
                        devise=devise,
                    )
                    if genre == "fixed"
                    else t("guide.plafond_variable"),
                ),
                "retrait",
            )

    doc.ajouter(t("guide.section_attente", n=len(guide.en_attente)), "section")
    doc.ajouter(t("guide.attente_intro"), "normal")
    for code, sujet, statut in guide.en_attente:
        doc.ajouter(
            t("guide.attente_ligne", code=code, sujet=sujet, statut=mot(StatutExigence, statut)),
            "retrait",
        )

    doc.ajouter(t("guide.section_attention", n=len(guide.anomalies)), "section")
    if not guide.anomalies:
        doc.ajouter(t("guide.aucune_anomalie"), "normal")
    for type_cible, intitule, raison in guide.anomalies:
        doc.ajouter(
            t(
                "guide.anomalie_ligne",
                type=libelle_valeur(TypeCible, type_cible, langue),
                libelle=intitule,
                raison=raison.rendre(langue),
            ),
            "retrait",
        )
    return doc.octets()


def generer_guide(
    *, utilisateur, project_id, date: datetime.date, langue: str | None = None
) -> bytes:
    """Le PDF du guide dans `langue` ; l'opération est journalisée avec l'empreinte du document."""
    if not est_habilite(utilisateur, "consulter", project_id):
        raise PermissionDenied(msg("guide.vous_etes_habilite_consulter_projet"))
    langue = normaliser_langue(langue) if langue else langue_courante()
    guide = construire_guide(project_id, date)
    contenu = rendre_pdf(guide, langue)
    journaliser(
        org_id=utilisateur.org_id,
        actor_id=utilisateur.id,
        action="configuration_guide_generated",
        object_type="projet",
        object_id=project_id,
        project_id=project_id,
        after={
            "date": date.isoformat(),
            "langue": langue,
            "sha256": hashlib.sha256(contenu).hexdigest(),
            "configuration": guide.empreinte_configuration,
        },
    )
    return contenu
