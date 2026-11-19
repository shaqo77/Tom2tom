"""Réallocations et avenants : des événements qui créent une version de profil. Voir L5-T04bis.

Une réallocation n'écrase rien : elle demande un transfert d'une catégorie à une autre ; à
l'approbation, une NOUVELLE version du profil est créée (allocations modifiées, `valid_from` = date
d'effet), validée puis activée dans la même transaction. L'ancienne version reste, donc les demandes
de retrait antérieures restent explicables telles qu'elles étaient.

Verrous, toujours dans cet ordre : la réallocation, l'accord, les deux catégories (par identifiant),
puis les versions du profil (L5-T04). Deux réallocations simultanées sur la même catégorie source
sont donc sérialisées, et le solde est relu sous verrou ; deux approbations simultanées de la même
réallocation n'en produisent qu'une (statut relu sous verrou, et clé unique sur `profil_cree`).
"""

import datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.i18n import msg
from niveau1_socle.decaissements.models import SoldeCategorie
from niveau1_socle.financements.models import Accord, Categorie
from niveau1_socle.habilitations.permissions import est_habilite

from ..models import DocumentReference, Reallocation, StatutReallocation
from .activation import ActivationRefusee, activer_profil, valider_profil
from .decaissement import profil_en_vigueur
from .versions import nouvelle_version


class ReallocationRefusee(ValueError):
    """La réallocation ne respecte pas les règles."""


class SoldeInsuffisant(ReallocationRefusee):
    """La catégorie source ne couvre pas le montant à transférer."""


def _habilite(utilisateur, operation, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(msg("reallocation.vous_etes_habilite_projet", operation=operation))


def solde_categorie(profil, categorie) -> Decimal:
    """Ce qui reste de l'allocation d'une catégorie : allocation du profil − demandes en cours."""
    regle = profil.regles.filter(category=categorie).first()
    if regle is None:
        raise ReallocationRefusee(
            msg("reallocation.categorie_regle_profil_vigueur", code=categorie.code)
        )
    solde = SoldeCategorie.objects.filter(categorie=categorie).first()
    return regle.allocation - (solde.utilise if solde else Decimal(0))


def demander_reallocation(
    *,
    utilisateur,
    accord: Accord,
    source: Categorie,
    cible: Categorie,
    montant,
    date_effet: datetime.date,
    motif: str,
    document: DocumentReference | None = None,
) -> Reallocation:
    _habilite(utilisateur, "parametrer", accord.project_id)
    montant = Decimal(str(montant))
    if montant <= 0:
        raise ReallocationRefusee(msg("reallocation.montant_transferer_strictement_positif"))
    if source.pk == cible.pk:
        raise ReallocationRefusee(msg("reallocation.categorie_source_categorie_cible_distinctes"))
    if source.accord_id != accord.pk or cible.accord_id != accord.pk:
        raise ReallocationRefusee(msg("reallocation.deux_categories_appartiennent_accord"))
    if source.devise_id != cible.devise_id:
        raise ReallocationRefusee(msg("reallocation.deux_categories_ont_meme_devise"))
    if not (motif or "").strip():
        raise ReallocationRefusee(msg("reallocation.reallocation_motivee"))
    if document is not None and document.project_id != accord.project_id:
        raise ReallocationRefusee(msg("reallocation.justificatif_appartient_projet"))
    if profil_en_vigueur(accord, date_effet) is None:
        raise ReallocationRefusee(
            msg("reallocation.aucun_profil_decaissement_vigueur", date_effet=date_effet)
        )
    with transaction.atomic():
        realloc = Reallocation.objects.create(
            org_id=utilisateur.org_id,
            project_id=accord.project_id,
            accord=accord,
            source=source,
            cible=cible,
            montant=montant,
            devise_id=source.devise_id,
            date_effet=date_effet,
            motif=motif.strip(),
            document=document,
            demandeur=utilisateur.id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=realloc.org_id,
            actor_id=utilisateur.id,
            action="reallocation_requested",
            object_type="reallocation",
            object_id=realloc.id,
            project_id=accord.project_id,
            after={
                "source": source.code,
                "cible": cible.code,
                "montant": str(montant),
                "date_effet": date_effet.isoformat(),
            },
        )
    return realloc


def approuver_reallocation(*, utilisateur, reallocation: Reallocation) -> Reallocation:
    """Approuve : crée, valide et active la nouvelle version du profil, et lie la réallocation.

    L'approbateur est distinct du demandeur et détient `valider` ET `parametrer` (il valide puis
    active la version qu'il crée).
    """
    _habilite(utilisateur, "valider", reallocation.project_id)
    _habilite(utilisateur, "parametrer", reallocation.project_id)
    try:
        with transaction.atomic():
            realloc = Reallocation.objects.select_for_update().get(pk=reallocation.pk)
            if realloc.status != StatutReallocation.DEMANDEE:
                raise ReallocationRefusee(
                    msg("reallocation.reallocation_deja", status=realloc.status)
                )
            if utilisateur.id == realloc.demandeur:
                raise ReallocationRefusee(
                    msg("reallocation.approbateur_doit_etre_distinct_demandeur")
                )
            accord = Accord.objects.select_for_update().get(pk=realloc.accord_id)
            source, cible = list(
                Categorie.objects.select_for_update()
                .filter(pk__in=[realloc.source_id, realloc.cible_id])
                .order_by("pk")
            )
            if source.pk != realloc.source_id:
                source, cible = cible, source
            base = profil_en_vigueur(accord, realloc.date_effet)
            if base is None:
                raise ReallocationRefusee(
                    msg(
                        "reallocation.aucun_profil_decaissement_vigueur",
                        date_effet=realloc.date_effet,
                    )
                )
            if base.valid_from >= realloc.date_effet:
                raise ReallocationRefusee(
                    msg("reallocation.version_profil_prend_deja_effet", valid_from=base.valid_from)
                )
            disponible = solde_categorie(base, source)
            if disponible < realloc.montant:
                raise SoldeInsuffisant(
                    msg(
                        "reallocation.categorie_solde_transfert_demande",
                        code=source.code,
                        disponible=disponible,
                        montant=realloc.montant,
                    )
                )
            alloc_source = base.regles.get(category=source).allocation
            if not base.regles.filter(category=cible).exists():
                raise ReallocationRefusee(
                    msg("reallocation.categorie_regle_profil_vigueur", code=cible.code)
                )
            alloc_cible = base.regles.get(category=cible).allocation
            nouveau = nouvelle_version(
                base,
                valid_from=realloc.date_effet,
                utilisateur=utilisateur,
                allocations={
                    source.pk: alloc_source - realloc.montant,
                    cible.pk: alloc_cible + realloc.montant,
                },
            )
            valider_profil(utilisateur=utilisateur, profil=nouveau)
            nouveau = activer_profil(utilisateur=utilisateur, profil=nouveau)
            realloc.status = StatutReallocation.APPROUVEE
            realloc.approbateur = utilisateur.id
            realloc.decided_at = timezone.now()
            realloc.profil_cree = nouveau
            realloc.save()
            journaliser(
                org_id=realloc.org_id,
                actor_id=utilisateur.id,
                action="reallocation_approved",
                object_type="reallocation",
                object_id=realloc.id,
                project_id=realloc.project_id,
                before={"profil": str(base.id), "version": base.version},
                after={"profil": str(nouveau.id), "version": nouveau.version},
            )
    except ActivationRefusee as erreur:
        raise ReallocationRefusee(
            msg("reallocation.nouvelle_version_profil_refusee", erreur=erreur)
        ) from erreur
    except IntegrityError as erreur:
        raise ReallocationRefusee(msg("reallocation.reallocation_vient_etre_decidee")) from erreur
    return realloc


def rejeter_reallocation(*, utilisateur, reallocation: Reallocation, motif: str) -> Reallocation:
    _habilite(utilisateur, "valider", reallocation.project_id)
    if not (motif or "").strip():
        raise ReallocationRefusee(msg("reallocation.rejet_exige_motif"))
    with transaction.atomic():
        realloc = Reallocation.objects.select_for_update().get(pk=reallocation.pk)
        if realloc.status != StatutReallocation.DEMANDEE:
            raise ReallocationRefusee(msg("reallocation.reallocation_deja", status=realloc.status))
        realloc.status = StatutReallocation.REJETEE
        realloc.approbateur = utilisateur.id
        realloc.decided_at = timezone.now()
        realloc.motif_rejet = motif.strip()
        realloc.save()
        journaliser(
            org_id=realloc.org_id,
            actor_id=utilisateur.id,
            action="reallocation_rejected",
            object_type="reallocation",
            object_id=realloc.id,
            project_id=realloc.project_id,
            after={"motif": realloc.motif_rejet},
        )
    return realloc
