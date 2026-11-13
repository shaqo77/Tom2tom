"""Créer, publier et importer un profil de bailleur. Voir L5-T05.

RÈGLE ABSOLUE : un profil n'impose JAMAIS automatiquement ses exigences à un projet. L'import crée
des exigences `proposed`, jamais `active`, et il n'existe aucun chemin pour le contraire : la
création des exigences passe par `_proposer_depuis_element`, qui fixe le statut, et la base refuse
(déclencheur) toute exigence issue d'un profil qui ne naît pas `proposed`.

Une exigence importée porte une citation « à étayer » : le texte de la bibliothèque n'est pas celui
du document contractuel du projet. Elle ne se valide qu'une fois étayée par un passage réellement
présent dans ce document (`niveau3_config.services.exigences.etayer_exigence`).
"""

from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from niveau1_socle.financements.models import Bailleur
from niveau1_socle.habilitations.models import Habilitation
from niveau1_socle.habilitations.permissions import est_habilite
from niveau3_config.models import (
    DocumentReference,
    Exigence,
    Obligation,
    OrigineExigence,
    Periodicite,
    StatutExigence,
)

from ..models import ElementProfil, ProfilBailleur, StatutProfilBailleur, TypeElement

CHAMPS_EXIGENCE = {
    "subject",
    "rule",
    "obligation",
    "periodicity",
    "due_offset_days",
    "condition_expr",
}
CITATION_A_ETAYER = "À étayer par un passage du document contractuel du projet"


class ProfilInvalide(ValueError):
    """Le profil ou l'un de ses éléments ne respecte pas les règles."""


def _habilite(utilisateur) -> None:
    """Le profil appartient à l'organisation, pas à un projet."""
    if not Habilitation.objects.filter(
        user_id=utilisateur.id, role__operations__contains=["parametrer"]
    ).exists():
        raise PermissionDenied("Vous n'êtes pas habilité à « parametrer ».")


def _valider_exigence_type(payload) -> None:
    if not isinstance(payload, dict):
        raise ProfilInvalide("L'exigence d'un élément est un objet")
    inconnus = set(payload) - CHAMPS_EXIGENCE
    if inconnus:
        raise ProfilInvalide(f"Champs d'exigence inconnus : {sorted(inconnus)}")
    if not str(payload.get("subject", "")).strip():
        raise ProfilInvalide("L'exigence d'un élément a une rubrique (`subject`)")
    if not isinstance(payload.get("rule", {}), dict):
        raise ProfilInvalide("La règle de l'exigence est un objet")
    if payload.get("obligation", Obligation.OBLIGATOIRE) not in Obligation.values:
        raise ProfilInvalide(f"obligation inconnue : {payload.get('obligation')}")
    if payload.get("periodicity") not in (None, *Periodicite.values):
        raise ProfilInvalide(f"périodicité inconnue : {payload.get('periodicity')}")
    if (
        payload.get("obligation") == Obligation.CONDITIONNELLE
        and not str(payload.get("condition_expr") or "").strip()
    ):
        raise ProfilInvalide("Une exigence conditionnelle précise sa condition")


def creer_profil_bailleur(
    *,
    utilisateur,
    code: str,
    label: dict,
    bailleur: Bailleur | None = None,
    description: str = "",
    version: int = 1,
) -> ProfilBailleur:
    _habilite(utilisateur)
    if not (code or "").strip() or not isinstance(label, dict) or not label:
        raise ProfilInvalide("Le code et le libellé (JSON par langue) du profil sont obligatoires")
    with transaction.atomic():
        profil = ProfilBailleur.objects.create(
            org_id=utilisateur.org_id,
            bailleur=bailleur,
            code=code.strip(),
            version=version,
            label=label,
            description=description,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=profil.org_id,
            actor_id=utilisateur.id,
            action="donor_profile_created",
            object_type="profil_bailleur",
            object_id=profil.id,
            after={"code": profil.code, "version": profil.version},
        )
    return profil


def ajouter_element(
    *,
    utilisateur,
    profil: ProfilBailleur,
    kind: str,
    code: str,
    label: dict,
    contenu: dict | None = None,
    exigence: dict | None = None,
    position: int = 0,
) -> ElementProfil:
    _habilite(utilisateur)
    if kind not in TypeElement.values:
        raise ProfilInvalide(f"type d'élément inconnu : {kind}")
    if not (code or "").strip() or not isinstance(label, dict) or not label:
        raise ProfilInvalide("Le code et le libellé de l'élément sont obligatoires")
    if exigence is not None:
        _valider_exigence_type(exigence)
    with transaction.atomic():
        profil = ProfilBailleur.objects.select_for_update().get(pk=profil.pk)
        if profil.status != StatutProfilBailleur.BROUILLON:
            raise ProfilInvalide("Un profil publié ne reçoit plus d'élément : publiez une version")
        return ElementProfil.objects.create(
            org_id=profil.org_id,
            profil=profil,
            kind=kind,
            code=code.strip(),
            label=label,
            contenu=contenu or {},
            exigence=exigence,
            position=position,
            created_by=utilisateur.id,
        )


def publier_profil(*, utilisateur, profil: ProfilBailleur) -> ProfilBailleur:
    _habilite(utilisateur)
    with transaction.atomic():
        profil = ProfilBailleur.objects.select_for_update().get(pk=profil.pk)
        if profil.status != StatutProfilBailleur.BROUILLON:
            raise ProfilInvalide("Ce profil est déjà publié")
        if not profil.elements.exists():
            raise ProfilInvalide("Un profil sans aucun élément ne se publie pas")
        profil.status = StatutProfilBailleur.PUBLIE
        profil.published_by = utilisateur.id
        profil.published_at = timezone.now()
        profil.save()
        journaliser(
            org_id=profil.org_id,
            actor_id=utilisateur.id,
            action="donor_profile_published",
            object_type="profil_bailleur",
            object_id=profil.id,
            after={"code": profil.code, "version": profil.version},
        )
    return profil


@dataclass
class ResultatImport:
    creees: list = field(default_factory=list)
    deja_proposees: list = field(default_factory=list)  # codes déjà en attente pour ce profil

    @property
    def exigences(self) -> list:
        return self.creees


def _proposer_depuis_element(*, utilisateur, profil, element, project_id, document) -> Exigence:
    """LE seul chemin de création d'une exigence depuis un profil : statut `proposed`, en dur."""
    modele = element.exigence
    derniere = (
        Exigence.objects.filter(project_id=project_id, code=element.code)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
    )
    return Exigence.objects.create(
        org_id=utilisateur.org_id,
        project_id=project_id,
        code=element.code,
        donor_profile_id=profil.id,
        document=document,
        citation={
            "quote": CITATION_A_ETAYER,
            "paragraph": "à confirmer",
            "origine": f"profil {profil.code} v{profil.version}, élément {element.code}",
        },
        subject=modele["subject"].strip(),
        rule=modele.get("rule", {}),
        periodicity=modele.get("periodicity"),
        due_offset_days=modele.get("due_offset_days"),
        obligation=modele.get("obligation", Obligation.OBLIGATOIRE),
        condition_expr=modele.get("condition_expr"),
        valid_from=timezone.localdate(),
        version=(derniere or 0) + 1,
        status=StatutExigence.PROPOSEE,
        source=OrigineExigence.MANUELLE,
        created_by=utilisateur.id,
    )


def importer_profil(
    *, utilisateur, profil: ProfilBailleur, project_id, document: DocumentReference
) -> ResultatImport:
    """Met le profil à disposition du projet : une exigence PROPOSÉE par élément qui en porte une.

    `document` est le document contractuel du projet (DFIL, accord…) sur lequel ces propositions
    devront être étayées. Importer deux fois ne duplique rien.
    """
    if not est_habilite(utilisateur, "parametrer", project_id):
        raise PermissionDenied("Vous n'êtes pas habilité à « parametrer » sur ce projet.")
    if profil.status != StatutProfilBailleur.PUBLIE:
        raise ProfilInvalide("Seul un profil publié se met à disposition d'un projet")
    if document.project_id != project_id:
        raise ProfilInvalide("Le document n'appartient pas au projet")
    if document.superseded_by_id is not None:
        raise ProfilInvalide(
            f"Le document « {document.title} » est remplacé : désignez la version en vigueur"
        )
    resultat = ResultatImport()
    with transaction.atomic():
        for element in profil.elements.exclude(exigence__isnull=True):
            if Exigence.objects.filter(
                project_id=project_id,
                code=element.code,
                donor_profile_id=profil.id,
                status=StatutExigence.PROPOSEE,
            ).exists():
                resultat.deja_proposees.append(element.code)
                continue
            resultat.creees.append(
                _proposer_depuis_element(
                    utilisateur=utilisateur,
                    profil=profil,
                    element=element,
                    project_id=project_id,
                    document=document,
                )
            )
        journaliser(
            org_id=utilisateur.org_id,
            actor_id=utilisateur.id,
            action="donor_profile_imported",
            object_type="profil_bailleur",
            object_id=profil.id,
            project_id=project_id,
            after={
                "creees": [e.code for e in resultat.creees],
                "deja_proposees": resultat.deja_proposees,
                "statut": StatutExigence.PROPOSEE,
            },
        )
    return resultat
