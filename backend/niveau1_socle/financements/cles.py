"""Clés de cofinancement : versions, ventilation d'un montant, lignes produites. Voir L4-T05.

Le calcul est dans `cofinancement.py` (pur, sans base). Ici : lire une clé en vigueur, ventiler un
montant dans la devise donnée, et produire des lignes d'écriture qui portent chacune l'accord ET la
version de clé qui les a produites.
"""

import datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.i18n import msg
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.referentiels.models import Devise

from .cofinancement import normaliser_parts, pas_de_devise, ventiler
from .models import Accord, CleCofinancement, PartCle, StatutAccord, VersionCle


class CleInvalide(ValueError):
    """La clé ou sa version ne respecte pas les règles du cofinancement."""


def _habilite(utilisateur, project_id) -> None:
    if not est_habilite(utilisateur, "parametrer", project_id):
        raise PermissionDenied(msg("cles.vous_etes_habilite_parametrer_projet"))


def creer_cle(*, utilisateur, project_id, code: str, label: dict) -> CleCofinancement:
    _habilite(utilisateur, project_id)
    try:
        with transaction.atomic():  # la clé et sa trace d'audit : ensemble, ou rien
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
    except IntegrityError:
        raise CleInvalide(msg("cles.code_deja_utilise", code=code.strip())) from None
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
        raise CleInvalide(msg("cles.cle_moins_part"))
    if porteur not in poids:
        raise CleInvalide(msg("cles.porteur_arrondi_doit_etre_accords"))
    for accord in poids:
        if accord.project_id != cle.project_id:
            raise CleInvalide(msg("cles.accord_appartient_projet_cle", numero=accord.numero))
        if accord.status in (StatutAccord.CLOS, StatutAccord.ANNULE):
            raise CleInvalide(msg("cles.accord", numero=accord.numero, status=accord.status))
    accords = sorted(poids, key=lambda a: a.numero)  # ordre stable : même clé, même résultat
    parts = normaliser_parts([poids[a] for a in accords])
    with transaction.atomic():
        versions = VersionCle.objects.filter(cle=cle)
        en_cours = versions.filter(valid_to__isnull=True).first()
        if en_cours is not None:
            if valid_from <= en_cours.valid_from:
                raise CleInvalide(
                    msg("cles.nouvelle_version_doit_prendre_effet", valid_from=en_cours.valid_from)
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
        raise CleInvalide(msg("cles.sens_inconnu_debit_credit"))
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


# Les montants d'une ligne : (champ, devise du pas d'arrondi). `monnaie_tenue` pour les montants de
# tenue, la devise de l'écriture pour les montants en devise : chacun s'arrondit à SON pas.
CHAMPS_VENTILES = (
    ("debit", "tenue"),
    ("credit", "tenue"),
    ("debit_cur", "ecriture"),
    ("credit_cur", "ecriture"),
)


def developper_cles(
    lignes: list[dict], *, project_id, date_comptable: datetime.date, devise: str
) -> list[dict]:
    """Remplace chaque ligne portant `"cle": <code>` par une ligne PAR ACCORD de la version de la
    clé en vigueur à `date_comptable`, chacune portant son accord et `cofunding_key_version_id`.

    C'est le branchement de la répartition à la saisie : l'appelant dit « cette charge suit la clé
    CHARGES », il ne calcule aucune part. Chaque montant de la ligne (tenue et devise) est ventilé
    séparément, à son pas d'arrondi, par le même calcul que `ventiler_montant` : le total de chaque
    montant est conservé. Les lignes de l'appelant ne sont pas modifiées ; sans clé, rien ne change.
    """
    if not any(ligne.get("cle") for ligne in lignes):
        return lignes
    from niveau1_socle.organisations.models import Organisation

    tenue = Organisation.objects.values_list("monnaie_tenue", flat=True).get()
    resultat: list[dict] = []
    for ligne in lignes:
        code = ligne.get("cle")
        if not code:
            resultat.append(ligne)
            continue
        if ligne.get("agreement_id"):
            raise CleInvalide(msg("cles.ligne_cle_et_accord", compte=ligne.get("compte", "")))
        cle = CleCofinancement.objects.filter(project_id=project_id, code=code).first()
        if cle is None:
            raise CleInvalide(msg("cles.cle_inconnue", code=code))
        version = version_en_vigueur(cle, date_comptable)
        if version is None:
            raise CleInvalide(
                msg("cles.aucune_version_en_vigueur", code=code, jour=date_comptable.isoformat())
            )
        par_accord: dict = {}
        for champ, pas_de in CHAMPS_VENTILES:
            montant = Decimal(str(ligne.get(champ, 0)))
            if montant == 0:
                continue
            monnaie = tenue if pas_de == "tenue" else devise
            for accord, part in ventiler_montant(version, montant, monnaie):
                par_accord.setdefault(accord.pk, {})[champ] = part
        base = {
            k: v for k, v in ligne.items() if k not in ("cle", *(c for c, _ in CHAMPS_VENTILES))
        }
        for accord_id, montants in par_accord.items():
            if all(m == 0 for m in montants.values()):
                continue  # une part nulle ne produit pas de ligne
            resultat.append(
                {
                    **base,
                    **{champ: str(m) for champ, m in montants.items()},
                    "agreement_id": accord_id,
                    "cofunding_key_version_id": version.pk,
                }
            )
    return resultat
