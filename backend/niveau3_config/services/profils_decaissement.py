"""Créer un profil de décaissement (brouillon) avec ses méthodes, règles et comptes. Voir L11-B4.

Avant : un profil ne se construisait que par l'ORM (tests, scripts). Ce service est le chemin
d'écriture de l'API : il vérifie l'habilitation `parametrer`, résout catégories et comptes DANS
l'accord et le projet (jamais ailleurs), numérote la version et journalise. Les contraintes de la
base (taux dans ]0, 1], jalons dans l'ordre, ensembles fermés) restent la dernière barrière : leurs
violations sont traduites par l'API en refus métier, pas ici.

Le profil naît TOUJOURS en brouillon : il ne s'applique à aucune opération avant d'avoir été validé
puis activé (`activation.py`), et un profil actif ne se modifie pas — on crée une version.
"""

import datetime

from django.db import transaction
from django.db.models import Max
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.i18n import msg
from niveau1_socle.financements.models import Accord, Categorie, CompteBancaire
from niveau1_socle.habilitations.permissions import est_habilite

from ..models import (
    Exigence,
    MethodeDecaissement,
    ProfilDecaissement,
    RegleCompteDesigne,
    RegleFinancementCategorie,
    StatutExigence,
    StatutProfil,
)


class ProfilDecaissementInvalide(ValueError):
    """Une donnée du profil ne se rattache à rien de connu (catégorie, compte, exigence)."""


JALONS = ("effectiveness_date", "eligibility_date", "closing_date", "disbursement_deadline")


def _exigence(project_id, code: str) -> Exigence:
    """La version la plus récente, VALIDÉE ou ACTIVE, de l'exigence qui justifie le profil."""
    exigence = (
        Exigence.objects.filter(
            project_id=project_id,
            code=code,
            status__in=[StatutExigence.VALIDEE, StatutExigence.ACTIVE],
        )
        .order_by("-version")
        .first()
    )
    if exigence is None:
        raise ProfilDecaissementInvalide(msg("profils_decaissement.exigence_inconnue", code=code))
    return exigence


def creer_profil_decaissement(
    *,
    utilisateur,
    accord: Accord,
    valid_from: datetime.date,
    regime: str,
    jalons: dict | None = None,
    methodes: list[dict],
    regles: list[dict],
    comptes: list[dict] | None = None,
    exigence: str | None = None,
) -> ProfilDecaissement:
    """Un profil brouillon à effet de `valid_from`.

    `regles` : `category` = CODE de la catégorie de l'accord ; `comptes` : `compte` = CODE d'un
    compte bancaire du projet ; `exigence` = code de l'exigence source (validée ou active).
    """
    if not est_habilite(utilisateur, "parametrer", accord.project_id):
        raise PermissionDenied(
            msg("profils_decaissement.vous_etes_habilite_projet", operation="parametrer")
        )
    jalons = jalons or {}
    with transaction.atomic():
        categories = {c.code: c for c in Categorie.objects.filter(accord=accord)}
        comptes_projet = {
            c.code: c for c in CompteBancaire.objects.filter(project_id=accord.project_id)
        }
        for regle in regles:
            if regle["category"] not in categories:
                raise ProfilDecaissementInvalide(
                    msg("profils_decaissement.categorie_inconnue", code=regle["category"])
                )
        for compte in comptes or []:
            if compte["compte"] not in comptes_projet:
                raise ProfilDecaissementInvalide(
                    msg("profils_decaissement.compte_inconnu", code=compte["compte"])
                )
        source = _exigence(accord.project_id, exigence) if exigence else None
        derniere = ProfilDecaissement.objects.filter(
            accord=accord, project_id=accord.project_id
        ).aggregate(m=Max("version"))["m"]
        profil = ProfilDecaissement.objects.create(
            org_id=utilisateur.org_id,
            project_id=accord.project_id,
            accord=accord,
            version=(derniere or 0) + 1,
            valid_from=valid_from,
            regime=regime,
            requirement=source,
            status=StatutProfil.BROUILLON,
            created_by=utilisateur.id,
            **{j: jalons.get(j) for j in JALONS},
        )
        for methode in methodes:
            MethodeDecaissement.objects.create(org_id=profil.org_id, profil=profil, **methode)
        for regle in regles:
            RegleFinancementCategorie.objects.create(
                org_id=profil.org_id,
                profil=profil,
                **{**regle, "category": categories[regle["category"]]},
            )
        for compte in comptes or []:
            champs = {k: v for k, v in compte.items() if k != "compte"}
            RegleCompteDesigne.objects.create(
                org_id=profil.org_id,
                profil=profil,
                bank_account=comptes_projet[compte["compte"]],
                **champs,
            )
        journaliser(
            org_id=profil.org_id,
            actor_id=utilisateur.id,
            action="disbursement_profile_created",
            object_type="profil_decaissement",
            object_id=profil.id,
            project_id=profil.project_id,
            after={"accord": accord.numero, "version": profil.version, "regime": regime},
        )
    return profil
