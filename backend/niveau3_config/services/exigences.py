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
        raise CitationInvalide("La citation est un objet : extrait, paragraphe ou page")
    extrait = citation.get("quote")
    if not isinstance(extrait, str) or not extrait.strip():
        raise CitationInvalide("La citation doit contenir l'extrait exact (« quote »)")
    if citation.get("paragraph") in (None, "") and citation.get("page") in (None, ""):
        raise CitationInvalide("La citation désigne un paragraphe ou une page")
    voulu = normaliser(extrait)
    if len(voulu) < LONGUEUR_MINIMALE:
        raise CitationInvalide(
            f"L'extrait est trop court pour désigner un passage ({LONGUEUR_MINIMALE} caractères "
            "au moins)"
        )
    genre, pages = document_lu(document)
    normalisees = [normaliser(page) for page in pages]
    if voulu not in normaliser(" ".join(pages)):
        raise CitationIntrouvable()
    page = citation.get("page")
    if genre == "pdf" and page not in (None, ""):
        if type(page) is not int or not 1 <= page <= len(pages):
            raise CitationMalPlacee(
                f"La page {page} n'existe pas (le document en compte {len(pages)})"
            )
        # L'extrait est sur la page citée, ou commence sur elle et se poursuit sur la suivante
        # (jamais entièrement sur la suivante : ce serait la mauvaise page).
        ici = normalisees[page - 1]
        suite = normalisees[page] if page < len(pages) else ""
        if not (voulu in ici or (voulu in f"{ici} {suite}" and voulu not in suite)):
            raise CitationMalPlacee(
                f"La citation figure dans le document, mais pas à la page indiquée ({page})"
            )


def _habilite(utilisateur, project_id) -> None:
    if not est_habilite(utilisateur, "parametrer", project_id):
        raise PermissionDenied("Vous n'êtes pas habilité à « parametrer » sur ce projet.")


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
        raise ExigenceInvalide("Le code et la rubrique de l'exigence sont obligatoires")
    if document.project_id != project_id:
        raise ExigenceInvalide("Le document référencé n'appartient pas au projet")
    if document.superseded_by_id is not None:
        raise ExigenceInvalide(
            f"Le document « {document.title} » est remplacé : citez la version en vigueur"
        )
    if obligation not in Obligation.values:
        raise ExigenceInvalide(f"obligation inconnue : {obligation}")
    if periodicity is not None and periodicity not in Periodicite.values:
        raise ExigenceInvalide(f"périodicité inconnue : {periodicity}")
    if obligation == Obligation.CONDITIONNELLE and not (condition_expr or "").strip():
        raise ExigenceInvalide("Une exigence conditionnelle précise sa condition")
    if source not in OrigineExigence.values:
        raise ExigenceInvalide(f"origine inconnue : {source}")
    if source == OrigineExigence.ASSISTEE:
        if confidence is None or not Decimal(0) <= Decimal(str(confidence)) <= Decimal(1):
            raise ExigenceInvalide("Une exigence assistée porte une confiance entre 0 et 1")
    elif confidence is not None:
        raise ExigenceInvalide(
            "La confiance n'existe que pour une exigence proposée par l'assistant"
        )
    if not isinstance(rule, dict):
        raise ExigenceInvalide("La règle est un objet")
    try:
        valider_citation(document, citation)
    except ExtractionImpossible as erreur:
        raise CitationInvalide(f"Citation invérifiable : {erreur}") from erreur
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
        raise CitationInvalide(f"Citation invérifiable : {erreur}") from erreur
    with transaction.atomic():
        exigence = Exigence.objects.select_for_update().get(pk=exigence.pk)
        if exigence.status != "proposed":
            raise ExigenceInvalide(
                f"Seule une exigence proposée s'étaye (celle-ci est « {exigence.status} »)"
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
