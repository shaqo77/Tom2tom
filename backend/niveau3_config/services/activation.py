"""Valider, activer, rejeter et résoudre la configuration à une date. Voir L5-T04.

Exigences et profils de décaissement suivent le même cycle : `proposed`/`draft` → `validated` →
`active`, ou `rejected` (motif obligatoire). Rien ne recule, rien ne se modifie une fois validé :
un changement est une NOUVELLE version, avec sa date d'effet (`valid_from`).

Activer une version ferme la précédente : sa fin de validité est posée au `valid_from` de la
nouvelle (`[valid_from, valid_to[`, fin exclue). La précédente reste `active` pour les dates
antérieures : une dépense de juin se contrôle toujours avec la version de juin. Un changement qui
prendrait effet AVANT le début de la version en vigueur réécrirait l'histoire : on refuse.

L'unicité de la version active par période est garantie par la base (`EXCLUDE USING gist`) ; ce
module sérialise les activations d'un même accord (ou code) par un verrou de ligne et traduit
l'échec de la base en `ConflitActivation`.

La configuration d'un projet à une date (`resoudre_configuration`) ne regarde que ces versions
actives : une génération de rapport la résout à la DATE D'EFFET de la période, jamais au présent.
"""

import datetime
import hashlib
import json
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from niveau1_socle.financements.models import Accord
from niveau1_socle.habilitations.permissions import est_habilite

from ..models import Exigence, ProfilDecaissement, StatutExigence, StatutProfil


class ActivationRefusee(ValueError):
    """La transition demandée n'est pas permise."""


class ConflitActivation(ActivationRefusee):
    """Une autre version active couvre déjà la période : une seule aboutit."""


def _habilite(utilisateur, operation, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(f"Vous n'êtes pas habilité à « {operation} » sur ce projet.")


def _motif(motif: str | None) -> str:
    if not (motif or "").strip():
        raise ActivationRefusee("Un rejet exige un motif")
    return motif.strip()


def _transition(
    *, utilisateur, objet, type_objet, depuis, vers, action, operation, apres=None, avant=None
):
    if objet.status not in depuis:
        raise ActivationRefusee(
            f"Passage de « {objet.status} » à « {vers} » impossible : l'état attendu est "
            f"{' ou '.join(depuis)}"
        )
    objet.status = vers
    for champ, valeur in (apres or {}).items():
        setattr(objet, champ, valeur)
    objet.save()
    journaliser(
        org_id=objet.org_id,
        actor_id=utilisateur.id,
        action=action,
        object_type=type_objet,
        object_id=objet.id,
        project_id=objet.project_id,
        before={"status": avant},
        after={"status": vers, **{k: str(v) for k, v in (apres or {}).items()}},
    )


def _fermer_les_precedentes(actives, date_effet: datetime.date, nom: str) -> None:
    """Pose la fin de validité des versions actives qui couvrent `date_effet` ou la suivent."""
    for precedente in actives.select_for_update():
        if precedente.valid_from >= date_effet:
            raise ActivationRefusee(
                f"{nom} : la version {precedente.version} débute le {precedente.valid_from} ; "
                f"une version qui prend effet le {date_effet} réécrirait l'histoire"
            )
        if precedente.valid_to is not None and precedente.valid_to > date_effet:
            raise ActivationRefusee(
                f"{nom} : la version {precedente.version} est programmée jusqu'au "
                f"{precedente.valid_to} et ne peut pas être raccourcie"
            )
        if precedente.valid_to is None:
            precedente.valid_to = date_effet
            precedente.save(update_fields=["valid_to"])


# --- Exigences -------------------------------------------------------------------------------


def valider_exigence(*, utilisateur, exigence: Exigence) -> Exigence:
    """`proposed` → `validated` : un humain habilité (`valider`) nomme et date la validation."""
    _habilite(utilisateur, "valider", exigence.project_id)
    with transaction.atomic():
        exigence = Exigence.objects.select_for_update().get(pk=exigence.pk)
        document = exigence.document
        if document.superseded_by_id is not None:
            raise ActivationRefusee(
                f"Le document « {document.title} » est remplacé : citez la version en vigueur"
            )
        if bytes(exigence.citation_verifiee_sha256 or b"") != bytes(document.sha256):
            raise ActivationRefusee("La citation n'a pas été vérifiée sur ce document")
        _transition(
            utilisateur=utilisateur,
            objet=exigence,
            type_objet="exigence",
            depuis=[StatutExigence.PROPOSEE],
            vers=StatutExigence.VALIDEE,
            action="requirement_validated",
            operation="valider",
            avant=StatutExigence.PROPOSEE,
            apres={"validated_by": utilisateur.id, "validated_at": timezone.now()},
        )
    return exigence


def activer_exigence(*, utilisateur, exigence: Exigence) -> Exigence:
    """`validated` → `active` à la date d'effet de l'exigence (`valid_from`).

    L'exigence qu'elle remplace (même code) est close à cette date. Aucune activation
    automatique : c'est un acte de `parametrer`, jamais un effet de bord.
    """
    _habilite(utilisateur, "parametrer", exigence.project_id)
    try:
        with transaction.atomic():
            exigence = Exigence.objects.select_for_update().get(pk=exigence.pk)
            if exigence.status != StatutExigence.VALIDEE:
                raise ActivationRefusee(
                    f"Seule une exigence validée s'active (celle-ci est « {exigence.status} »)"
                )
            # Sérialise les activations d'un même code : les versions sont verrouillées ensemble.
            list(
                Exigence.objects.select_for_update()
                .filter(project_id=exigence.project_id, code=exigence.code)
                .order_by("version")
            )
            _fermer_les_precedentes(
                Exigence.objects.filter(
                    project_id=exigence.project_id,
                    code=exigence.code,
                    status=StatutExigence.ACTIVE,
                ).exclude(pk=exigence.pk),
                exigence.valid_from,
                f"Exigence {exigence.code}",
            )
            _transition(
                utilisateur=utilisateur,
                objet=exigence,
                type_objet="exigence",
                depuis=[StatutExigence.VALIDEE],
                vers=StatutExigence.ACTIVE,
                action="requirement_activated",
                operation="parametrer",
                avant=StatutExigence.VALIDEE,
                apres={"valid_from": exigence.valid_from},
            )
    except IntegrityError as erreur:
        raise ConflitActivation(
            f"Exigence {exigence.code} : une version active couvre déjà cette période"
        ) from erreur
    return exigence


def rejeter_exigence(*, utilisateur, exigence: Exigence, motif: str) -> Exigence:
    """`proposed` ou `validated` → `rejected`. Le motif est tracé dans le journal."""
    _habilite(utilisateur, "valider", exigence.project_id)
    motif = _motif(motif)
    with transaction.atomic():
        exigence = Exigence.objects.select_for_update().get(pk=exigence.pk)
        statut = exigence.status
        _transition(
            utilisateur=utilisateur,
            objet=exigence,
            type_objet="exigence",
            depuis=[StatutExigence.PROPOSEE, StatutExigence.VALIDEE],
            vers=StatutExigence.REJETEE,
            action="requirement_rejected",
            operation="valider",
            avant=statut,
            apres={"motif": motif},
        )
    return exigence


# --- Profils de décaissement -----------------------------------------------------------------


def valider_profil(*, utilisateur, profil: ProfilDecaissement) -> ProfilDecaissement:
    """`draft` → `validated`. Le profil se fige : méthodes, comptes et règles ne bougent plus."""
    _habilite(utilisateur, "valider", profil.project_id)
    with transaction.atomic():
        profil = ProfilDecaissement.objects.select_for_update().get(pk=profil.pk)
        if not profil.methodes.exists():
            raise ActivationRefusee(
                "Un profil sans aucune méthode de décaissement ne se valide pas"
            )
        if not profil.regles.exists():
            raise ActivationRefusee("Un profil sans aucune règle de financement ne se valide pas")
        _transition(
            utilisateur=utilisateur,
            objet=profil,
            type_objet="profil_decaissement",
            depuis=[StatutProfil.BROUILLON],
            vers=StatutProfil.VALIDE,
            action="disbursement_profile_validated",
            operation="valider",
            avant=StatutProfil.BROUILLON,
            apres={"validated_by": utilisateur.id, "validated_at": timezone.now()},
        )
    return profil


def activer_profil(*, utilisateur, profil: ProfilDecaissement) -> ProfilDecaissement:
    """`validated` → `active` à `valid_from` ; ferme le profil précédent de l'accord."""
    _habilite(utilisateur, "parametrer", profil.project_id)
    try:
        with transaction.atomic():
            # Le verrou de l'accord sérialise toutes les activations de ses versions.
            Accord.objects.select_for_update().get(pk=profil.accord_id)
            profil = ProfilDecaissement.objects.select_for_update().get(pk=profil.pk)
            if profil.status != StatutProfil.VALIDE:
                raise ActivationRefusee(
                    f"Seul un profil validé s'active (celui-ci est « {profil.status} »)"
                )
            _fermer_les_precedentes(
                ProfilDecaissement.objects.filter(
                    accord_id=profil.accord_id, status=StatutProfil.ACTIF
                ).exclude(pk=profil.pk),
                profil.valid_from,
                f"Profil de l'accord {profil.accord_id}",
            )
            _transition(
                utilisateur=utilisateur,
                objet=profil,
                type_objet="profil_decaissement",
                depuis=[StatutProfil.VALIDE],
                vers=StatutProfil.ACTIF,
                action="disbursement_profile_activated",
                operation="parametrer",
                avant=StatutProfil.VALIDE,
                apres={"valid_from": profil.valid_from},
            )
    except IntegrityError as erreur:
        raise ConflitActivation(
            f"Accord {profil.accord_id} : un profil actif couvre déjà cette période"
        ) from erreur
    return profil


def rejeter_profil(*, utilisateur, profil: ProfilDecaissement, motif: str) -> ProfilDecaissement:
    """`draft` ou `validated` → `rejected`, avec un motif obligatoire (aussi imposé par la base)."""
    _habilite(utilisateur, "valider", profil.project_id)
    motif = _motif(motif)
    with transaction.atomic():
        profil = ProfilDecaissement.objects.select_for_update().get(pk=profil.pk)
        statut = profil.status
        _transition(
            utilisateur=utilisateur,
            objet=profil,
            type_objet="profil_decaissement",
            depuis=[StatutProfil.BROUILLON, StatutProfil.VALIDE],
            vers=StatutProfil.REJETE,
            action="disbursement_profile_rejected",
            operation="valider",
            avant=statut,
            apres={"rejection_reason": motif},
        )
    return profil


# --- Configuration d'un projet à une date ----------------------------------------------------


@dataclass(frozen=True)
class ConfigurationProjet:
    """Tout ce qui est actif pour un projet à `date`, et l'empreinte qui l'identifie."""

    project_id: object
    date: datetime.date
    exigences: tuple  # ((code, version, id), …) triées par code
    profils: tuple  # ((accord_id, version, id), …) triés par accord

    @property
    def empreinte(self) -> str:
        contenu = json.dumps(
            {
                "projet": str(self.project_id),
                "date": self.date.isoformat(),
                "exigences": [[c, v, str(i)] for c, v, i in self.exigences],
                "profils": [[str(a), v, str(i)] for a, v, i in self.profils],
            },
            sort_keys=True,
        )
        return hashlib.sha256(contenu.encode()).hexdigest()


def resoudre_configuration(project_id, date: datetime.date) -> ConfigurationProjet:
    """La configuration ACTIVE à `date` (validité `[valid_from, valid_to[`), jamais la courante."""
    exigences = (
        Exigence.objects.filter(
            project_id=project_id, status=StatutExigence.ACTIVE, valid_from__lte=date
        )
        .exclude(valid_to__lte=date)
        .order_by("code", "version")
    )
    profils = (
        ProfilDecaissement.objects.filter(
            project_id=project_id, status=StatutProfil.ACTIF, valid_from__lte=date
        )
        .exclude(valid_to__lte=date)
        .order_by("accord_id", "version")
    )
    return ConfigurationProjet(
        project_id=project_id,
        date=date,
        exigences=tuple((e.code, e.version, e.id) for e in exigences),
        profils=tuple((p.accord_id, p.version, p.id) for p in profils),
    )
