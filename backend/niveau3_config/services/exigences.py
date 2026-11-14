"""Le registre des exigences : proposer une exigence dont la citation est RETROUVÉE. Voir L5-T02.

Une exigence cite un paragraphe d'un document : « DFIL §4.2, "…texte exact…" ». Une citation
inventée ne doit pas entrer dans le registre : à l'enregistrement, l'extrait doit se retrouver
LITTÉRALEMENT dans le texte du document référencé (typographie et espaces normalisés, casse et
accents conservés). Si le document est paginé (PDF) et que la citation donne une page, l'extrait
doit s'y trouver.

Habilitation : `parametrer`. Une exigence naît toujours `proposed` : l'activation est l'objet de
L5-T04, et la base refuse qu'une exigence validée ou active n'ait pas sa citation vérifiée.
"""

import datetime
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.i18n import msg
from niveau1_socle.habilitations.permissions import est_habilite

from ..models import DocumentReference, Exigence, Obligation, OrigineExigence, Periodicite
from .extraction import ExtractionImpossible, document_lu, normaliser

MESSAGE_INTROUVABLE = "La citation n'a pas été retrouvée dans le document référencé."
LONGUEUR_MINIMALE = 10  # un extrait plus court ne désigne aucun passage : « le » est partout


class CitationInvalide(ValueError):
    """La citation ne respecte pas les règles."""


class CitationIntrouvable(CitationInvalide):
    """L'extrait n'existe pas dans le texte du document référencé."""

    def __init__(self):
        super().__init__(MESSAGE_INTROUVABLE)


class CitationMalPlacee(CitationInvalide):
    """L'extrait existe dans le document, mais pas à la page indiquée."""


class ExigenceInvalide(ValueError):
    """L'exigence ne respecte pas les règles."""


def valider_citation(document: DocumentReference, citation: dict) -> None:
    """Refuse la citation si son extrait n'est pas littéralement retrouvable dans le document."""
    if not isinstance(citation, dict):
        raise CitationInvalide(msg("exigences.citation_objet_extrait_paragraphe_page"))
    extrait = citation.get("quote")
    if not isinstance(extrait, str) or not extrait.strip():
        raise CitationInvalide(msg("exigences.citation_doit_contenir_extrait_exact"))
    if citation.get("paragraph") in (None, "") and citation.get("page") in (None, ""):
        raise CitationInvalide(msg("exigences.citation_designe_paragraphe_page"))
    voulu = normaliser(extrait)
    if len(voulu) < LONGUEUR_MINIMALE:
        raise CitationInvalide(
            msg(
                "exigences.extrait_trop_court_designer_passage", LONGUEUR_MINIMALE=LONGUEUR_MINIMALE
            )
        )
    genre, pages = document_lu(document)
    normalisees = [normaliser(page) for page in pages]
    if voulu not in normaliser(" ".join(pages)):
        raise CitationIntrouvable()
    page = citation.get("page")
    if genre == "pdf" and page not in (None, ""):
        if type(page) is not int or not 1 <= page <= len(pages):
            raise CitationMalPlacee(
                msg("exigences.page_existe_document_compte", page=page, v1=len(pages))
            )
        # L'extrait est sur la page citée, ou commence sur elle et se poursuit sur la suivante
        # (jamais entièrement sur la suivante : ce serait la mauvaise page).
        ici = normalisees[page - 1]
        suite = normalisees[page] if page < len(pages) else ""
        if not (voulu in ici or (voulu in f"{ici} {suite}" and voulu not in suite)):
            raise CitationMalPlacee(msg("exigences.citation_figure_document_mais_page", page=page))


def _habilite(utilisateur, project_id) -> None:
    if not est_habilite(utilisateur, "parametrer", project_id):
        raise PermissionDenied(msg("exigences.vous_etes_habilite_parametrer_projet"))


def proposer_exigence(
    *,
    utilisateur,
    project_id,
    code: str,
    document: DocumentReference,
    citation: dict,
    subject: str,
    rule: dict,
    obligation: str,
    valid_from: datetime.date,
    periodicity: str | None = None,
    due_offset_days: int | None = None,
    condition_expr: str | None = None,
    source: str = OrigineExigence.MANUELLE,
    confidence=None,
    donor_profile_id=None,
) -> Exigence:
    """Enregistre une exigence PROPOSÉE, après avoir retrouvé sa citation dans le document.

    Un code déjà connu donne une nouvelle version (le numéro suit), jamais une modification.
    """
    _habilite(utilisateur, project_id)
    if not (code or "").strip() or not (subject or "").strip():
        raise ExigenceInvalide(msg("exigences.code_rubrique_exigence_obligatoires"))
    if document.project_id != project_id:
        raise ExigenceInvalide(msg("exigences.document_reference_appartient_projet"))
    if document.superseded_by_id is not None:
        raise ExigenceInvalide(
            msg("exigences.document_remplace_citez_version_vigueur", title=document.title)
        )
    if obligation not in Obligation.values:
        raise ExigenceInvalide(msg("exigences.obligation_inconnue", obligation=obligation))
    if periodicity is not None and periodicity not in Periodicite.values:
        raise ExigenceInvalide(msg("exigences.periodicite_inconnue", periodicity=periodicity))
    if obligation == Obligation.CONDITIONNELLE and not (condition_expr or "").strip():
        raise ExigenceInvalide(msg("exigences.exigence_conditionnelle_precise_condition"))
    if source not in OrigineExigence.values:
        raise ExigenceInvalide(msg("exigences.origine_inconnue", source=source))
    if source == OrigineExigence.ASSISTEE:
        if confidence is None or not Decimal(0) <= Decimal(str(confidence)) <= Decimal(1):
            raise ExigenceInvalide(msg("exigences.exigence_assistee_porte_confiance_entre"))
    elif confidence is not None:
        raise ExigenceInvalide(msg("exigences.confiance_existe_exigence_proposee_assistant"))
    if not isinstance(rule, dict):
        raise ExigenceInvalide(msg("exigences.regle_objet"))
    try:
        valider_citation(document, citation)
    except ExtractionImpossible as erreur:
        raise CitationInvalide(msg("exigences.citation_inverifiable", erreur=erreur)) from erreur
    with transaction.atomic():
        derniere = (
            Exigence.objects.filter(project_id=project_id, code=code.strip())
            .order_by("-version")
            .values_list("version", flat=True)
            .first()
        )
        exigence = Exigence.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            code=code.strip(),
            donor_profile_id=donor_profile_id,
            document=document,
            citation=citation,
            subject=subject.strip(),
            rule=rule,
            periodicity=periodicity,
            due_offset_days=due_offset_days,
            obligation=obligation,
            condition_expr=condition_expr,
            valid_from=valid_from,
            version=(derniere or 0) + 1,
            status="proposed",
            source=source,
            confidence=None if confidence is None else Decimal(str(confidence)),
            citation_verifiee_sha256=bytes(document.sha256),
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=exigence.org_id,
            actor_id=utilisateur.id,
            action="requirement_proposed",
            object_type="exigence",
            object_id=exigence.id,
            project_id=project_id,
            after={
                "code": exigence.code,
                "version": exigence.version,
                "document": document.title,
                "sha256": bytes(document.sha256).hex(),
                "citation": citation,
            },
        )
    return exigence


def etayer_exigence(*, utilisateur, exigence: Exigence, citation: dict) -> Exigence:
    """Pose, sur une exigence PROPOSÉE (typiquement importée d'un profil), la citation que le
    document du projet contient réellement. Sans cela, elle ne se valide pas (L5-T04).

    La citation est retrouvée littéralement dans le document de l'exigence, comme à la proposition.
    """
    _habilite(utilisateur, exigence.project_id)
    try:
        valider_citation(exigence.document, citation)
    except ExtractionImpossible as erreur:
        raise CitationInvalide(msg("exigences.citation_inverifiable", erreur=erreur)) from erreur
    with transaction.atomic():
        exigence = Exigence.objects.select_for_update().get(pk=exigence.pk)
        if exigence.status != "proposed":
            raise ExigenceInvalide(
                msg("exigences.seule_exigence_proposee_s_etaye", status=exigence.status)
            )
        avant = exigence.citation
        exigence.citation = citation
        exigence.citation_verifiee_sha256 = bytes(exigence.document.sha256)
        exigence.save(update_fields=["citation", "citation_verifiee_sha256", "updated_at"])
        journaliser(
            org_id=exigence.org_id,
            actor_id=utilisateur.id,
            action="requirement_supported",
            object_type="exigence",
            object_id=exigence.id,
            project_id=exigence.project_id,
            before={"citation": avant},
            after={"citation": citation, "sha256": bytes(exigence.document.sha256).hex()},
        )
    return exigence
