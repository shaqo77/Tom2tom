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


def _habiliter(utilisateur, accord: Accord) -> None:
    if not est_habilite(utilisateur, "parametrer", accord.project_id):
        raise PermissionDenied(
            msg("profils_decaissement.vous_etes_habilite_projet", operation="parametrer")
        )


def _resoudre(accord: Accord, regles, comptes, exigence):
    """Catégories, comptes et exigence résolus DANS l'accord et le projet, ou refus nommé."""
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
    return categories, comptes_projet, source


def _enfants(profil, categories, comptes_projet, methodes, regles, comptes) -> None:
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
    _habiliter(utilisateur, accord)
    jalons = jalons or {}
    with transaction.atomic():
        categories, comptes_projet, source = _resoudre(accord, regles, comptes, exigence)
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
        _enfants(profil, categories, comptes_projet, methodes, regles, comptes)
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


def _brouillon_verrouille(profil: ProfilDecaissement) -> ProfilDecaissement:
    """Le profil relu sous verrou, refusé s'il n'est plus un brouillon : un profil validé ou actif
    ne se modifie pas, on crée une version."""
    courant = ProfilDecaissement.objects.select_for_update().get(pk=profil.pk)
    if courant.status != StatutProfil.BROUILLON:
        raise ProfilDecaissementInvalide(
            msg("profils_decaissement.profil_non_brouillon", status=courant.status)
        )
    return courant


def remplacer_brouillon(
    *,
    utilisateur,
    profil: ProfilDecaissement,
    valid_from: datetime.date,
    regime: str,
    jalons: dict | None = None,
    methodes: list[dict],
    regles: list[dict],
    comptes: list[dict] | None = None,
    exigence: str | None = None,
) -> ProfilDecaissement:
    """Remplace TOUT le contenu d'un brouillon, d'un bloc : tout est accepté ou rien ne change.

    Une règle ou un compte ne se corrige pas à l'unité (il faudrait des états intermédiaires
    invalides) : on renvoie le profil entier, comme à la création. L'accord reste le même.
    """
    _habiliter(utilisateur, profil.accord)
    jalons = jalons or {}
    with transaction.atomic():
        courant = _brouillon_verrouille(profil)
        categories, comptes_projet, source = _resoudre(courant.accord, regles, comptes, exigence)
        courant.valid_from = valid_from
        courant.regime = regime
        courant.requirement = source
        for jalon in JALONS:
            setattr(courant, jalon, jalons.get(jalon))
        courant.save()
        courant.methodes.all().delete()
        courant.regles.all().delete()
        courant.comptes.all().delete()
        _enfants(courant, categories, comptes_projet, methodes, regles, comptes)
        journaliser(
            org_id=courant.org_id,
            actor_id=utilisateur.id,
            action="disbursement_profile_updated",
            object_type="profil_decaissement",
            object_id=courant.id,
            project_id=courant.project_id,
            after={"version": courant.version, "regime": regime},
        )
    return courant


def supprimer_brouillon(*, utilisateur, profil: ProfilDecaissement) -> None:
    """Abandonne un brouillon. Un profil validé, actif, remplacé ou rejeté ne se supprime jamais."""
    _habiliter(utilisateur, profil.accord)
    with transaction.atomic():
        courant = _brouillon_verrouille(profil)
        identifiant, version = courant.id, courant.version
        courant.methodes.all().delete()
        courant.regles.all().delete()
        courant.comptes.all().delete()
        org_id, project_id = courant.org_id, courant.project_id
        courant.delete()
        journaliser(
            org_id=org_id,
            actor_id=utilisateur.id,
            action="disbursement_profile_deleted",
            object_type="profil_decaissement",
            object_id=identifiant,
            project_id=project_id,
            after={"version": version},
        )
