"""Clés de cofinancement : versions, ventilation d'un montant, lignes produites. Voir L4-T05.

Le calcul est dans `cofinancement.py` (pur, sans base). Ici : lire une clé en vigueur, ventiler un
montant dans la devise donnée, et produire des lignes d'écriture qui portent chacune l'accord ET la
version de clé qui les a produites.
"""

import datetime
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.referentiels.models import Devise

from .cofinancement import normaliser_parts, pas_de_devise, ventiler
from .models import Accord, CleCofinancement, PartCle, StatutAccord, VersionCle


class CleInvalide(ValueError):
    """La clé ou sa version ne respecte pas les règles du cofinancement."""


def _habilite(utilisateur, project_id) -> None:
    if not est_habilite(utilisateur, "parametrer", project_id):
        raise PermissionDenied("Vous n'êtes pas habilité à « parametrer » sur ce projet.")


def creer_cle(*, utilisateur, project_id, code: str, label: dict) -> CleCofinancement:
    _habilite(utilisateur, project_id)
    with transaction.atomic():
        cle = CleCofinancement.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            code=code.strip(),
            label=label,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=cle.org_id,
            actor_id=utilisateur.id,
            action="cofunding_key_created",
            object_type="cle_cofinancement",
            object_id=cle.id,
            project_id=project_id,
            after={"code": cle.code},
        )
    return cle


def creer_version_cle(
    *,
    utilisateur,
    cle: CleCofinancement,
    poids: dict[Accord, int],
    porteur: Accord,
    valid_from: datetime.date,
    motif: str = "",
) -> VersionCle:
    """Ouvre une nouvelle version : les `poids` (60, 30, 10…) sont normalisés pour sommer
    EXACTEMENT à 1 (la dernière part par différence). La version en cours est close à `valid_from`.
    """
    _habilite(utilisateur, cle.project_id)
    if not poids:
        raise CleInvalide("Une clé a au moins une part")
    if porteur not in poids:
        raise CleInvalide("Le porteur d'arrondi doit être l'un des accords de la clé")
    for accord in poids:
        if accord.project_id != cle.project_id:
            raise CleInvalide(f"L'accord {accord.numero} n'appartient pas au projet de la clé")
        if accord.status in (StatutAccord.CLOS, StatutAccord.ANNULE):
            raise CleInvalide(f"L'accord {accord.numero} est {accord.status}")
    accords = sorted(poids, key=lambda a: a.numero)  # ordre stable : même clé, même résultat
    parts = normaliser_parts([poids[a] for a in accords])
    with transaction.atomic():
        versions = VersionCle.objects.filter(cle=cle)
        en_cours = versions.filter(valid_to__isnull=True).first()
        if en_cours is not None:
            if valid_from <= en_cours.valid_from:
                raise CleInvalide(
                    f"La nouvelle version doit prendre effet après le {en_cours.valid_from}"
                )
            VersionCle.objects.filter(pk=en_cours.pk).update(valid_to=valid_from)
        numero = (versions.order_by("-version").values_list("version", flat=True).first() or 0) + 1
        version = VersionCle.objects.create(
            org_id=utilisateur.org_id,
            cle=cle,
            version=numero,
            valid_from=valid_from,
            rounding_residual_agreement=porteur,
            motif=(motif or "").strip(),
            created_by=utilisateur.id,
        )
        PartCle.objects.bulk_create(
            [
                PartCle(org_id=utilisateur.org_id, version=version, accord=accord, share=part)
                for accord, part in zip(accords, parts, strict=True)
            ]
        )
        journaliser(
            org_id=version.org_id,
            actor_id=utilisateur.id,
            action="cofunding_key_version_created",
            object_type="version_cle",
            object_id=version.id,
            project_id=cle.project_id,
            after={
                "cle": cle.code,
                "version": numero,
                "parts": {a.numero: str(p) for a, p in zip(accords, parts, strict=True)},
                "porteur": porteur.numero,
            },
        )
    return version


def version_en_vigueur(cle: CleCofinancement, date: datetime.date) -> VersionCle | None:
    """La version de la clé valable à `date` (validité `[valid_from, valid_to[`), ou rien."""
    return (
        VersionCle.objects.filter(cle=cle, valid_from__lte=date).exclude(valid_to__lte=date).first()
    )


def ventiler_montant(version: VersionCle, montant, devise: str) -> list[tuple[Accord, Decimal]]:
    """Ventile `montant` (dans `devise`) entre les accords de la version ; le total est conservé."""
    pas = pas_de_devise(Devise.objects.get(pk=devise).decimales)
    parts = list(version.parts.select_related("accord").order_by("accord__numero"))
    accords = {p.accord_id: p.accord for p in parts}
    resultat = ventiler(
        Decimal(str(montant)),
        [(p.accord_id, p.share) for p in parts],
        version.rounding_residual_agreement_id,
        pas,
    )
    return [(accords[accord_id], m) for accord_id, m in resultat]


def lignes_ventilees(
    version: VersionCle, *, montant, devise: str, compte: str, sens: str = "debit", **champs
) -> list[dict]:
    """Les lignes d'écriture d'une charge cofinancée : une par accord ayant une part non nulle,
    chacune portant son accord et `cofunding_key_version_id`. À passer à `saisir_ecriture`, avec la
    contrepartie. `sens` : "debit" (dépense) ou "credit" (remboursement)."""
    if sens not in ("debit", "credit"):
        raise CleInvalide("sens inconnu : debit ou credit")
    lignes = []
    for accord, part in ventiler_montant(version, montant, devise):
        if part == 0:
            continue
        lignes.append(
            {
                "compte": compte,
                sens: str(part),
                "agreement_id": accord.pk,
                "cofunding_key_version_id": version.pk,
                **champs,
            }
        )
    return lignes
