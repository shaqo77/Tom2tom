"""Les réglages de devises : par organisation, surchargés par projet, entièrement en base. Voir L10.

Ce module ne contient AUCUNE devise, AUCUN taux, AUCUNE valeur par défaut : ce que l'organisation ou
le projet n'a pas réglé reste « non paramétré », et l'appelant le dit (une consolidation sans devise
de référence refuse de répondre ; elle ne choisit pas pour vous).

Héritage : pour chaque champ, la valeur du projet si elle existe, sinon celle de l'organisation,
sinon rien. La liste des devises autorisées d'un projet REMPLACE celle de l'organisation.
"""

import datetime
from dataclasses import dataclass

from django.db import connection, transaction
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.i18n import msg
from core.metier import habilite, refuser
from niveau1_socle.habilitations.models import Habilitation
from niveau1_socle.organisations.models import Organisation, Projet

from .models import Devise, ParametreDevises, TypeTaux

CHAMPS = ("devise_reference", "devises_autorisees", "type_taux")
OPERATION = "parametrer"


@dataclass(frozen=True)
class ParametresDevises:
    """Les réglages EN VIGUEUR un jour donné pour un projet, avec leur provenance."""

    devise_reference: str | None
    devises_autorisees: tuple[str, ...] | None  # None : aucune restriction paramétrée
    type_taux: str | None
    origine: dict[str, str | None]  # champ -> "projet" | "organisation" | None
    versions: dict[str, int | None]  # niveau -> numéro de version en vigueur


def _en_vigueur(project_id, jour: datetime.date) -> ParametreDevises | None:
    versions = ParametreDevises.objects.filter(valid_from__lte=jour).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gt=jour)
    )
    versions = (
        versions.filter(project_id=project_id)
        if project_id is not None
        else versions.filter(project_id__isnull=True)
    )
    return versions.order_by("-version").first()


def _valeur(version: ParametreDevises | None, champ: str):
    if version is None:
        return None
    if champ == "devise_reference":
        return version.devise_reference_id
    if champ == "devises_autorisees":
        return tuple(version.devises_autorisees) if version.devises_autorisees is not None else None
    return version.type_taux


def resoudre_parametres_devises(project_id, jour: datetime.date) -> ParametresDevises:
    """Les réglages en vigueur à `jour` : le projet d'abord, puis l'organisation, puis rien."""
    organisation = _en_vigueur(None, jour)
    projet = _en_vigueur(project_id, jour) if project_id is not None else None
    valeurs, origine = {}, {}
    for champ in CHAMPS:
        propre, herite = _valeur(projet, champ), _valeur(organisation, champ)
        valeurs[champ] = propre if propre is not None else herite
        origine[champ] = (
            "projet" if propre is not None else "organisation" if herite is not None else None
        )
    return ParametresDevises(
        devise_reference=valeurs["devise_reference"],
        devises_autorisees=valeurs["devises_autorisees"],
        type_taux=valeurs["type_taux"],
        origine=origine,
        versions={
            "organisation": organisation.version if organisation else None,
            "projet": projet.version if projet else None,
        },
    )


def devise_autorisee(project_id, devise: str, jour: datetime.date) -> bool:
    """Cette devise est-elle utilisable sur ce projet à cette date ?

    Une devise hors du référentiel ne l'est jamais. Sans liste paramétrée, tout le référentiel
    l'est.
    """
    if not Devise.objects.filter(pk=devise).exists():
        return False
    liste = resoudre_parametres_devises(project_id, jour).devises_autorisees
    return liste is None or devise in liste


def monnaie_de_base(project_id) -> str:
    """La monnaie de base du projet : une DONNÉE du projet, jamais une valeur du code."""
    return Projet.objects.values_list("base_currency", flat=True).get(pk=project_id)


def exiger_devise_autorisee(project_id, devise: str, jour: datetime.date | None = None) -> None:
    """Refuse (422) une devise que les réglages n'autorisent pas pour ce projet à `jour`.

    Sans liste paramétrée, rien n'est restreint ici : une devise inconnue du référentiel reste
    refusée par la base (clé étrangère), comme avant.
    """
    liste = resoudre_parametres_devises(
        project_id, jour or datetime.date.today()
    ).devises_autorisees
    if liste is not None and devise not in liste:
        refuser("parametres_devises.devise_non_autorisee", code=devise)


def _habiliter(utilisateur, project_id) -> None:
    if project_id is not None:
        habilite(utilisateur, OPERATION, project_id, cle="parametres_devises.habilitation_requise")
    elif not Habilitation.objects.filter(
        user_id=utilisateur.id, role__operations__contains=[OPERATION]
    ).exists():
        raise PermissionDenied(msg("parametres_devises.habilitation_requise", operation=OPERATION))


def _normaliser(devise_reference, devises_autorisees, type_taux):
    reference = devise_reference.strip().upper() if devise_reference else None
    liste = None
    if devises_autorisees is not None:
        liste = sorted(
            {c.strip().upper() for c in devises_autorisees if c.strip()}
        )  # forme canonique
        if not liste:
            refuser("parametres_devises.liste_vide")
    type_ = type_taux.strip() if type_taux else None
    if reference is None and liste is None and type_ is None:
        refuser("parametres_devises.rien_a_parametrer")
    if type_ is not None and type_ not in TypeTaux.values:
        refuser("parametres_devises.type_taux_inconnu", type_taux=type_)
    connues = set(
        Devise.objects.filter(
            pk__in=[*(liste or []), *([reference] if reference else [])]
        ).values_list("pk", flat=True)
    )
    for code in [*(liste or []), *([reference] if reference else [])]:
        if code not in connues:
            refuser("parametres_devises.devise_inconnue", code=code)
    return reference, liste, type_


def _verifier_projet(projet: Projet, liste: list[str] | None) -> None:
    if liste is not None and projet.base_currency not in liste:
        refuser(
            "parametres_devises.sans_monnaie_du_projet",
            projet=projet.code,
            code=projet.base_currency,
        )


def parametrer_devises(
    *,
    utilisateur,
    project_id=None,
    devise_reference: str | None = None,
    devises_autorisees: list[str] | None = None,
    type_taux: str | None = None,
    date_effet: datetime.date,
    motif: str = "",
) -> ParametreDevises:
    """Pose une NOUVELLE version des réglages (`project_id` nul : l'organisation), à partir de
    `date_effet`. Chaque champ à `None` signifie « hérite du niveau au-dessus » ; la version
    précédente du même niveau est close à cette date, elle ne change pas."""
    _habiliter(utilisateur, project_id)
    reference, liste, type_ = _normaliser(devise_reference, devises_autorisees, type_taux)
    organisation = Organisation.objects.get(pk=utilisateur.org_id)
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                [f"parametres-devises:{utilisateur.org_id}"],
            )
        # Cohérence : on juge sur la liste EFFECTIVE de ce niveau (la sienne, sinon la parente).
        parent_liste = _valeur(_en_vigueur(None, date_effet), "devises_autorisees")
        if project_id is None:
            effective = liste
            if liste is not None and organisation.monnaie_tenue not in liste:
                refuser("parametres_devises.sans_monnaie_de_tenue", code=organisation.monnaie_tenue)
            for projet in Projet.objects.order_by("code"):
                propre = _en_vigueur(projet.id, date_effet)
                if propre is None or propre.devises_autorisees is None:
                    _verifier_projet(projet, liste)
                    ref = (propre.devise_reference_id if propre else None) or reference
                    if liste is not None and ref and ref not in liste:
                        refuser("parametres_devises.reference_hors_liste", code=ref)
        else:
            projet = Projet.objects.get(pk=project_id)
            effective = (
                list(liste) if liste is not None else (list(parent_liste) if parent_liste else None)
            )
            _verifier_projet(projet, liste)
        if reference and effective is not None and reference not in effective:
            refuser("parametres_devises.reference_hors_liste", code=reference)

        versions = ParametreDevises.objects.filter(project_id=project_id)
        en_cours = versions.filter(valid_to__isnull=True).first()
        if en_cours is not None:
            if date_effet <= en_cours.valid_from:
                refuser("parametres_devises.date_effet_posterieure", valid_from=en_cours.valid_from)
            ParametreDevises.objects.filter(pk=en_cours.pk).update(valid_to=date_effet)
        numero = (versions.order_by("-version").values_list("version", flat=True).first() or 0) + 1
        reglage = ParametreDevises.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            devise_reference_id=reference,
            devises_autorisees=liste,
            type_taux=type_,
            version=numero,
            valid_from=date_effet,
            motif=(motif or "").strip(),
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=reglage.org_id,
            actor_id=utilisateur.id,
            action="currency_settings_configured",
            object_type="parametre_devises",
            object_id=reglage.id,
            project_id=project_id,
            before={champ: _valeur(en_cours, champ) for champ in CHAMPS} if en_cours else None,
            after={
                "devise_reference": reference,
                "devises_autorisees": liste,
                "type_taux": type_,
                "valid_from": str(date_effet),
                "version": numero,
            },
        )
    return reglage
