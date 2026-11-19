"""Copier un profil en une nouvelle version BROUILLON. Voir L5-T04bis.

Une réallocation, un avenant : jamais une modification du profil en vigueur, toujours une nouvelle
version qui en reprend tout (méthodes, comptes désignés, règles) avec les changements voulus. La
copie est générique (tous les champs concrets) : un champ ajouté plus tard au profil ou à ses
enfants est reporté sans qu'on y pense.
"""

import datetime

from django.db.models import Max

from core.i18n import msg

from ..models import ProfilDecaissement, StatutProfil

NON_COPIES = {"id", "org_id", "profil", "created_at", "created_by", "updated_at", "updated_by"}
DATES_MODIFIABLES = (
    "effectiveness_date",
    "eligibility_date",
    "closing_date",
    "disbursement_deadline",
)


def _champs(objet, exclus=()):
    return {
        f.attname: getattr(objet, f.attname)
        for f in objet._meta.concrete_fields
        if f.name not in NON_COPIES and f.name not in exclus
    }


def nouvelle_version(
    base: ProfilDecaissement,
    *,
    valid_from: datetime.date,
    utilisateur,
    allocations: dict | None = None,
    dates: dict | None = None,
    profil_id=None,
) -> ProfilDecaissement:
    """Une copie brouillon de `base` à effet de `valid_from`.

    `allocations` : `{catégorie: nouvelle allocation}` ; `dates` : jalons à remplacer.
    """
    derniere = ProfilDecaissement.objects.filter(
        accord_id=base.accord_id, project_id=base.project_id
    ).aggregate(m=Max("version"))["m"]
    inconnues = set(dates or {}) - set(DATES_MODIFIABLES)
    if inconnues:
        raise ValueError(f"jalons inconnus : {sorted(inconnues)}")
    champs = _champs(
        base,
        exclus={
            "version",
            "valid_from",
            "valid_to",
            "status",
            "rejection_reason",
            "validated_by",
            "validated_at",
        },
    )
    champs.update(dates or {})
    nouveau = ProfilDecaissement.objects.create(
        org_id=base.org_id,
        **({"id": profil_id} if profil_id else {}),
        **champs,
        version=(derniere or 0) + 1,
        valid_from=valid_from,
        status=StatutProfil.BROUILLON,
        created_by=utilisateur.id,
    )
    for methode in base.methodes.all():
        nouveau.methodes.create(org_id=base.org_id, **_champs(methode))
    for compte in base.comptes.all():
        nouveau.comptes.create(org_id=base.org_id, **_champs(compte))
    allocations = dict(allocations or {})
    for regle in base.regles.all():
        donnees = _champs(regle)
        if regle.category_id in allocations:
            donnees["allocation"] = allocations.pop(regle.category_id)
        nouveau.regles.create(org_id=base.org_id, **donnees)
    if allocations:
        raise ValueError(msg("versions.allocations_visent_categorie_sans_regle"))
    return nouveau
