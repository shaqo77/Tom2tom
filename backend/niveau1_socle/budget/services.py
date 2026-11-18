"""Cycle de vie des versions de budget. Voir L4-T01.

brouillon --approuver--> approuvé --(une révision est approuvée)--> clos

- Création et édition d'un brouillon : habilitation `saisir`.
- Approbation : habilitation `valider`, par une autre personne que l'auteur (séparation des tâches).
- Une révision part de la version approuvée courante, dont elle reprend les lignes ; quand elle est
  approuvée, l'ancienne passe à « clos » dans la même transaction. Aucune ligne n'est jamais perdue.
"""

import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.i18n import Liste, msg
from niveau1_socle.exercices.services import TransitionInterdite
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.habilitations.separation import exiger_separation_des_taches
from niveau1_socle.organisations.models import Projet
from niveau1_socle.referentiels.models import Devise, PlanDimension, ValeurDimension
from niveau1_socle.referentiels.parametres_devises import exiger_devise_autorisee

from .models import LigneBudget, StatutVersion, TypeVersion, VersionBudget

ZERO = Decimal(0)
AXES = (("dim1", 1), ("dim2", 2), ("dim3", 3), ("dim4", 4))  # axes de gestion
IDENTIFIANTS_LIBRES = ("agreement_id", "category_id", "site_id")


class BudgetInvalide(ValueError):
    """Une ligne ou une version ne respecte pas les règles du budget."""


class VersionIntrouvable(LookupError):
    pass


def _habilite(utilisateur, operation: str, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(msg("budget.vous_etes_habilite_projet", operation=operation))


def _verrou_projet(project_id) -> None:
    """Sérialise les créations de version d'un même projet (numéro sans trou)."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [f"budget:{project_id}"]
        )


def version_courante(project_id) -> VersionBudget | None:
    """La version approuvée en vigueur, ou rien si aucun budget n'est encore approuvé."""
    return VersionBudget.objects.filter(
        project_id=project_id, status=StatutVersion.APPROUVE
    ).first()


def _exiger_brouillon(version: VersionBudget) -> VersionBudget:
    courante = VersionBudget.objects.get(pk=version.pk)
    if courante.status != StatutVersion.BROUILLON:
        raise TransitionInterdite(
            msg(
                "budget.version_seul_brouillon_modifie",
                numero=courante.numero,
                status=courante.status,
            )
        )
    return courante


def creer_version(*, utilisateur, project_id, type: str, motif: str = "") -> VersionBudget:
    """Crée un BROUILLON : le budget initial, ou une révision/réallocation de la version courante.

    Une révision reprend les lignes de la version courante, à modifier ensuite dans le brouillon.
    """
    if type not in TypeVersion.values:
        raise BudgetInvalide(msg("budget.type_version_inconnu", type=type))
    _habilite(utilisateur, "saisir", project_id)
    with transaction.atomic():
        _verrou_projet(project_id)
        existants = VersionBudget.objects.filter(project_id=project_id)
        if existants.filter(status=StatutVersion.BROUILLON).exists():
            raise BudgetInvalide(msg("budget.version_budget_deja_preparation_projet"))
        parent = None
        if type == TypeVersion.INITIAL:
            if existants.exists():
                raise BudgetInvalide(msg("budget.projet_deja_budget_initial_creez"))
        else:
            if not (motif or "").strip():
                raise BudgetInvalide(msg("budget.motif_obligatoire_revision_reallocation"))
            parent = version_courante(project_id)
            if parent is None:
                raise BudgetInvalide(msg("budget.aucune_version_approuvee_reviser_approuvez"))
        numero = (existants.order_by("-numero").values_list("numero", flat=True).first() or 0) + 1
        version = VersionBudget.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            numero=numero,
            type=type,
            parent=parent,
            motif=(motif or "").strip(),
            created_by=utilisateur.id,
        )
        if parent is not None:
            LigneBudget.objects.bulk_create(
                [
                    LigneBudget(
                        org_id=ligne.org_id,
                        version=version,
                        annee=ligne.annee,
                        periode=ligne.periode,
                        dim1_id=ligne.dim1_id,
                        dim2_id=ligne.dim2_id,
                        dim3_id=ligne.dim3_id,
                        dim4_id=ligne.dim4_id,
                        agreement_id=ligne.agreement_id,
                        category_id=ligne.category_id,
                        site_id=ligne.site_id,
                        montant=ligne.montant,
                        devise_id=ligne.devise_id,
                        taux_budget=ligne.taux_budget,
                        montant_base=ligne.montant_base,
                    )
                    for ligne in parent.lignes.all()
                ]
            )
        journaliser(
            org_id=version.org_id,
            actor_id=utilisateur.id,
            action="budget_version_created",
            object_type="version_budget",
            object_id=version.id,
            project_id=project_id,
            after={"numero": numero, "type": type, "parent": str(parent.id) if parent else None},
        )
    return version


def _montant_base(montant: Decimal, taux: Decimal, project_id) -> Decimal:
    """Montant en monnaie de tenue du projet : montant × taux, arrondi à ses décimales."""
    devise = Devise.objects.get(pk=Projet.objects.get(pk=project_id).base_currency)
    return (montant * taux).quantize(Decimal(1).scaleb(-devise.decimales), rounding=ROUND_HALF_UP)


def _axes(axes: dict | None) -> dict:
    resolus = {}
    for champ, emplacement in AXES:
        code = (axes or {}).get(champ)
        if not code:
            continue
        plan = PlanDimension.objects.filter(kind="gestion", slot=emplacement).first()
        valeur = ValeurDimension.objects.filter(plan=plan, code=code).first() if plan else None
        if valeur is None or not valeur.is_active:
            raise BudgetInvalide(msg("budget.valeur_existe_inactive_axe", code=code, champ=champ))
        resolus[champ] = valeur
    inconnus = set(axes or {}) - {champ for champ, _ in AXES}
    if inconnus:
        raise BudgetInvalide(msg("budget.axe_inconnu", v1=sorted(inconnus)))
    return resolus


def _champs_de_ligne(version, *, annee, periode, montant, devise, taux, axes, identifiants) -> dict:
    montant = Decimal(str(montant))
    taux = Decimal(str(taux))
    if montant < 0:
        raise BudgetInvalide(msg("budget.montant_budget_jamais_negatif"))
    if taux <= 0:
        raise BudgetInvalide(msg("budget.taux_budget_doit_etre_strictement"))
    if periode is not None and not 1 <= periode <= 12:
        raise BudgetInvalide(msg("budget.periode_comprise_entre_1_12"))
    if not Devise.objects.filter(pk=devise).exists():
        raise BudgetInvalide(msg("budget.devise_inconnue", devise=devise))
    inconnus = set(identifiants) - set(IDENTIFIANTS_LIBRES)
    if inconnus:
        raise BudgetInvalide(msg("budget.identifiant_inconnu", v1=sorted(inconnus)))
    return {
        "annee": annee,
        "periode": periode,
        "montant": montant,
        "devise_id": devise,
        "taux_budget": taux,
        "montant_base": _montant_base(montant, taux, version.project_id),
        **{f"{champ}": valeur for champ, valeur in _axes(axes).items()},
        **{cle: valeur for cle, valeur in identifiants.items() if valeur},
    }


def ajouter_ligne(
    version: VersionBudget,
    *,
    utilisateur,
    annee: int,
    montant,
    devise: str,
    periode: int | None = None,
    taux=1,
    axes: dict | None = None,
    **identifiants,
) -> LigneBudget:
    """Ajoute une ligne à un brouillon. `axes` : `{"dim1": code, …}` ; `identifiants` : accord,
    catégorie, site (UUID)."""
    _habilite(utilisateur, "saisir", version.project_id)
    with transaction.atomic():
        courante = _exiger_brouillon(version)
        champs = _champs_de_ligne(
            courante,
            annee=annee,
            periode=periode,
            montant=montant,
            devise=devise,
            taux=taux,
            axes=axes,
            identifiants=identifiants,
        )
        # La liste de devises autorisées applicable est celle du début de la période budgétée.
        # Elle se vérifie APRÈS la validation de la ligne : une période ou une année invalide est
        # refusée avec son propre message, jamais par une erreur de date brute.
        try:
            debut_de_periode = datetime.date(annee, periode or 1, 1)
        except (ValueError, TypeError):  # année hors bornes : la base refusera (1900 à 2200)
            debut_de_periode = None
        if debut_de_periode is not None:
            exiger_devise_autorisee(courante.project_id, devise, debut_de_periode)
        return LigneBudget.objects.create(org_id=courante.org_id, version=courante, **champs)


def modifier_ligne(ligne: LigneBudget, *, utilisateur, montant, taux=None) -> LigneBudget:
    """Change le montant (et le taux) d'une ligne d'un brouillon. Les axes ne changent pas :
    on supprime la ligne et on en ajoute une autre."""
    with transaction.atomic():
        courante = LigneBudget.objects.select_related("version").get(pk=ligne.pk)
        _habilite(utilisateur, "saisir", courante.version.project_id)
        _exiger_brouillon(courante.version)
        taux = courante.taux_budget if taux is None else Decimal(str(taux))
        montant = Decimal(str(montant))
        if montant < 0 or taux <= 0:
            raise BudgetInvalide(msg("budget.montant_negatif_taux_non_positif"))
        courante.montant = montant
        courante.taux_budget = taux
        courante.montant_base = _montant_base(montant, taux, courante.version.project_id)
        courante.save(update_fields=["montant", "taux_budget", "montant_base", "updated_at"])
    return courante


def supprimer_ligne(ligne: LigneBudget, *, utilisateur) -> None:
    with transaction.atomic():
        courante = LigneBudget.objects.select_related("version").get(pk=ligne.pk)
        _habilite(utilisateur, "saisir", courante.version.project_id)
        _exiger_brouillon(courante.version)
        courante.delete()


def supprimer_version(version: VersionBudget, *, utilisateur) -> None:
    """Abandonne un brouillon. Une version approuvée ou close ne se supprime jamais."""
    _habilite(utilisateur, "saisir", version.project_id)
    with transaction.atomic():
        courante = _exiger_brouillon(version)
        courante.delete()
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action="budget_version_deleted",
            object_type="version_budget",
            object_id=version.id,
            project_id=version.project_id,
            before={"numero": version.numero},
        )


def _problemes_de_contenu(version: VersionBudget) -> list[str]:
    """Une même combinaison d'axes ne peut pas mêler année entière et périodes : on compterait
    deux fois le même budget."""
    clefs = ("dim1_id", "dim2_id", "dim3_id", "dim4_id", "agreement_id", "category_id", "site_id")
    groupes: dict[tuple, dict] = {}
    for ligne in version.lignes.all():
        cle = (ligne.annee, *(getattr(ligne, c) for c in clefs))
        g = groupes.setdefault(cle, {"annuelle": False, "periodes": False})
        g["annuelle" if ligne.periode is None else "periodes"] = True
    return [
        f"{cle[0]} : une combinaison d'axes a une ligne annuelle ET des lignes par période"
        for cle, g in groupes.items()
        if g["annuelle"] and g["periodes"]
    ]


def approuver_version(version: VersionBudget, *, utilisateur) -> VersionBudget:
    """Brouillon -> approuvé ; la version courante précédente passe à « clos ».

    L'auteur ne l'approuve pas. Une révision partie d'une version qui n'est plus la courante est
    refusée : elle écraserait une approbation plus récente.
    """
    with transaction.atomic():
        _verrou_projet(version.project_id)
        courante = VersionBudget.objects.select_for_update().get(pk=version.pk)
        if courante.status != StatutVersion.BROUILLON:
            raise TransitionInterdite(
                msg(
                    "budget.version_seul_brouillon_s_approuve",
                    numero=courante.numero,
                    status=courante.status,
                )
            )
        _habilite(utilisateur, "valider", courante.project_id)
        exiger_separation_des_taches(utilisateur, courante.created_by)
        raisons = _problemes_de_contenu(courante)
        if raisons:
            raise BudgetInvalide(Liste(raisons, "; "))
        actuelle = version_courante(courante.project_id)
        if (actuelle.pk if actuelle else None) != (courante.parent_id):
            raise BudgetInvalide(msg("budget.version_ete_preparee_partir_version"))
        maintenant = timezone.now()
        if actuelle is not None:  # AVANT d'approuver : une seule version courante à tout instant
            VersionBudget.objects.filter(pk=actuelle.pk).update(
                status=StatutVersion.CLOS, closed_at=maintenant
            )
        VersionBudget.objects.filter(pk=courante.pk).update(
            status=StatutVersion.APPROUVE, approved_at=maintenant, approved_by=utilisateur.id
        )
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action="budget_version_approved",
            object_type="version_budget",
            object_id=courante.id,
            project_id=courante.project_id,
            before={"status": StatutVersion.BROUILLON},
            after={
                "status": StatutVersion.APPROUVE,
                "remplace": str(actuelle.id) if actuelle else None,
            },
        )
    version.refresh_from_db()
    return version


def total_base(version: VersionBudget) -> Decimal:
    """Total de la version, en monnaie de tenue."""
    return sum((ligne.montant_base for ligne in version.lignes.all()), ZERO)


def ecarts(avant: VersionBudget, apres: VersionBudget) -> dict:
    """Ce qui change d'une version à l'autre, par combinaison : ajoutées, supprimées, modifiées."""

    def index(version):
        return {
            (
                ligne.annee,
                ligne.periode,
                ligne.dim1_id,
                ligne.dim2_id,
                ligne.dim3_id,
                ligne.dim4_id,
                ligne.agreement_id,
                ligne.category_id,
                ligne.site_id,
            ): ligne.montant_base
            for ligne in version.lignes.all()
        }

    a, b = index(avant), index(apres)
    return {
        "ajoutees": sorted(((k, b[k]) for k in b.keys() - a.keys()), key=str),
        "supprimees": sorted(((k, a[k]) for k in a.keys() - b.keys()), key=str),
        "modifiees": sorted(
            ((k, a[k], b[k]) for k in a.keys() & b.keys() if a[k] != b[k]), key=str
        ),
        "total_avant": sum(a.values(), ZERO),
        "total_apres": sum(b.values(), ZERO),
    }
