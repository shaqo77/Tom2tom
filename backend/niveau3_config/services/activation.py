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
from core.i18n import Liste, msg
from niveau1_socle.financements.models import Accord
from niveau1_socle.habilitations.permissions import est_habilite

from ..models import Exigence, ProfilDecaissement, StatutExigence, StatutProfil
from .completude import verifier_completude


class ActivationRefusee(ValueError):
    """La transition demandée n'est pas permise."""


class ConflitActivation(ActivationRefusee):
    """Une autre version active couvre déjà la période : une seule aboutit."""


def _habilite(utilisateur, operation, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(msg("activation.vous_etes_habilite_projet", operation=operation))


def _motif(motif: str | None) -> str:
    if not (motif or "").strip():
        raise ActivationRefusee(msg("activation.rejet_exige_motif"))
    return motif.strip()


def _transition(*, utilisateur, objet, type_objet, depuis, vers, action, apres=None, avant=None):
    if objet.status not in depuis:
        raise ActivationRefusee(
            msg(
                "activation.passage_impossible_etat_attendu",
                status=objet.status,
                vers=vers,
                v1=" ou ".join(depuis),
            )
        )
    objet.status = vers
    for champ, valeur in (apres or {}).items():
        if hasattr(objet, champ):
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
                msg(
                    "activation.version_debute_version_prend_effet",
                    nom=nom,
                    version=precedente.version,
                    valid_from=precedente.valid_from,
                    date_effet=date_effet,
                )
            )
        if precedente.valid_to is not None and precedente.valid_to > date_effet:
            raise ActivationRefusee(
                msg(
                    "activation.version_programmee_jusqu_peut_etre",
                    nom=nom,
                    version=precedente.version,
                    valid_to=precedente.valid_to,
                )
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
                msg("activation.document_remplace_citez_version_vigueur", title=document.title)
            )
        if bytes(exigence.citation_verifiee_sha256 or b"") != bytes(document.sha256):
            raise ActivationRefusee(msg("activation.citation_ete_verifiee_document"))
        _transition(
            utilisateur=utilisateur,
            objet=exigence,
            type_objet="exigence",
            depuis=[StatutExigence.PROPOSEE],
            vers=StatutExigence.VALIDEE,
            action="requirement_validated",
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
                    msg("activation.seule_exigence_validee_s_active", status=exigence.status)
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
                avant=StatutExigence.VALIDEE,
                apres={"valid_from": exigence.valid_from},
            )
    except IntegrityError as erreur:
        raise ConflitActivation(
            msg("activation.exigence_version_active_couvre_deja", code=exigence.code)
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
            avant=statut,
            apres={"motif": motif},
        )
    return exigence


# --- Profils de décaissement -----------------------------------------------------------------


def valider_profil(
    *, utilisateur, profil: ProfilDecaissement, justifications: dict | None = None
) -> ProfilDecaissement:
    """`draft` → `validated`. Le profil se fige : méthodes, comptes et règles ne bougent plus.

    Refusé si le contrôle de complétude relève une erreur bloquante (chacune est nommée). Les
    avertissements ne bloquent pas : ils sont tracés dans le journal avec la justification de qui
    valide (`justifications = {code: texte}`).
    """
    _habilite(utilisateur, "valider", profil.project_id)
    with transaction.atomic():
        profil = ProfilDecaissement.objects.select_for_update().get(pk=profil.pk)
        completude = verifier_completude(profil)
        if not completude.complet:
            raise ActivationRefusee(
                msg(
                    "activation.profil_incomplet",
                    details=Liste([a.message for a in completude.bloquantes]),
                )
            )
        _transition(
            utilisateur=utilisateur,
            objet=profil,
            type_objet="profil_decaissement",
            depuis=[StatutProfil.BROUILLON],
            vers=StatutProfil.VALIDE,
            action="disbursement_profile_validated",
            avant=StatutProfil.BROUILLON,
            apres={
                "validated_by": utilisateur.id,
                "validated_at": timezone.now(),
                "avertissements": json.dumps(
                    {
                        a.code: (justifications or {}).get(a.code, "")
                        for a in completude.avertissements
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                ),
            },
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
                    msg("activation.seul_profil_valide_s_active", status=profil.status)
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
                avant=StatutProfil.VALIDE,
                apres={"valid_from": profil.valid_from},
            )
    except IntegrityError as erreur:
        raise ConflitActivation(
            msg("activation.accord_profil_actif_couvre_deja", accord_id=profil.accord_id)
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
