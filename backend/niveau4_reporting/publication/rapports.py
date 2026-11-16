"""Générer, publier et RÉGÉNÉRER un rapport. Voir L6-T04.

La promesse : un rapport publié se rejoue. Rejoué avec le modèle d'alors, les mappings d'alors et
les paramètres d'alors, il redonne soit l'identique (même scellé), soit un différentiel qui dit
POURQUOI : quelles rubriques ont bougé, de combien, et quelles écritures sont arrivées depuis,
nommées, avec leur montant. Un simple « écart détecté » ne tient pas la promesse.

Les causes qu'on sait nommer : les écritures comptabilisées après la publication dans le périmètre
du rapport (contre-passations comprises). Les autres (écart sans écriture nouvelle) sont signalées
comme INEXPLIQUÉES, jamais passées sous silence : c'est une alerte d'intégrité.
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from types import SimpleNamespace

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from niveau1_socle.habilitations.permissions import est_habilite
from niveau4_reporting.mapping.models import TableMapping
from niveau4_reporting.moteur.compilateur import _parametres_source, generer

from .models import RapportPublie
from .scellement import (
    empreinte_jeu_de_donnees,
    montant_canonique,
    sceller,
)

SEP = "/"  # « rubrique/colonne »
TENTATIVES = 3


@dataclass
class RapportGenere:
    """Un rapport produit, pas encore publié : de quoi le sceller (protocole `Scellable`)."""

    template: object
    template_version: int | None
    modele: dict
    period_from: datetime.date
    period_to: datetime.date
    params: dict
    config_version: dict
    mapping_versions: dict
    dataset_hash: bytes
    values: dict = field(default_factory=dict)  # {"rubrique/colonne": Decimal}


@dataclass(frozen=True)
class Ecart:
    rubrique: str
    colonne: str
    ancien: Decimal | None
    nouveau: Decimal | None

    @property
    def difference(self) -> Decimal:
        return (self.nouveau or Decimal(0)) - (self.ancien or Decimal(0))


@dataclass(frozen=True)
class CauseEcriture:
    """Une écriture comptabilisée après la publication, dans le périmètre du rapport."""

    ecriture: str  # le numéro de pièce
    date: datetime.date
    compte: str
    montant: Decimal  # signé : débit - crédit
    contre_passation_de: str | None
    comptabilisee_le: datetime.datetime


@dataclass
class ResultatRegeneration:
    identique: bool
    ecarts: list[Ecart] = field(default_factory=list)
    causes: list[CauseEcriture] = field(default_factory=list)
    inexpliquee: bool = False  # écart sans écriture nouvelle : à investiguer


def _tables_par_code(mapping_versions: dict) -> dict:
    tables = {}
    for code, ref in mapping_versions.items():
        tables[code] = TableMapping.objects.get(pk=ref["id"])
    return tables


def versions_des_mappings(tables: dict[str, TableMapping]) -> dict:
    return {code: {"id": str(t.pk), "version": t.version} for code, t in tables.items()}


def generer_rapport(
    *,
    modele: dict,
    params: dict,
    tables: dict[str, TableMapping],
    period_from: datetime.date,
    period_to: datetime.date,
    config_version: dict | None = None,
) -> RapportGenere:
    """Produit le rapport (sans le publier). Une assertion fausse ou un mapping incomplet lève."""
    where, source_params, annee, courante = _parametres_source(params)
    if not (
        period_from <= period_to
        and period_to.year == annee
        and period_to.month == courante
        and period_from.year == annee
    ):
        raise ErreurMetier(
            CodeErreur.REGLE_INVALIDE,
            msg(
                "rapports.periode_incoherente",
                du=period_from.isoformat(),
                au=period_to.isoformat(),
                annee=annee,
                periode=courante,
            ),
        )
    regles = {code: list(table.regles.all()) for code, table in tables.items()}
    # Les valeurs et l'empreinte du jeu de données doivent décrire le MÊME état du grand livre :
    # on lit l'empreinte avant et après la génération, et on recommence si une écriture est
    # arrivée entre les deux (la base ne permet pas ici un instantané unique, voir la note du plan).
    for _tentative in range(TENTATIVES):
        avant = empreinte_jeu_de_donnees(where, source_params)
        produit = generer(modele, regles, params)
        apres = empreinte_jeu_de_donnees(where, source_params)
        if avant == apres:
            break
    else:
        raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("rapports.jeu_en_mouvement"))
    return RapportGenere(
        template=SimpleNamespace(code=modele["code"]),
        template_version=modele.get("version"),
        modele=modele,
        period_from=period_from,
        period_to=period_to,
        params=params,
        config_version=config_version or {},
        mapping_versions=versions_des_mappings(tables),
        dataset_hash=apres,
        values={
            f"{rubrique}{SEP}{colonne}": montant
            for rubrique, colonnes in produit.valeurs.items()
            for colonne, montant in colonnes.items()
        },
    )


def publier_rapport(*, utilisateur, project_id, **champs) -> RapportPublie:
    """Génère, scelle et ENREGISTRE le rapport. Le rapport publié ne change plus."""
    if not est_habilite(utilisateur, "publier", project_id):
        raise PermissionDenied(msg("rapports.habilitation_publier"))
    params = {**champs.pop("params"), "project_id": str(project_id)}
    # La date de publication est prise AVANT la génération : toute écriture comptabilisée après
    # cet instant est « arrivée depuis la publication » pour le différentiel, et celles arrivées
    # pendant la génération sont reprises par la relecture de l'empreinte.
    publie_le = timezone.now()
    rapport = generer_rapport(params=params, **champs)
    with transaction.atomic():
        publie = RapportPublie.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            template_code=rapport.template.code,
            template_version=rapport.template_version,
            modele=rapport.modele,
            period_from=rapport.period_from,
            period_to=rapport.period_to,
            params=rapport.params,
            config_version=rapport.config_version,
            mapping_versions=rapport.mapping_versions,
            dataset_hash=rapport.dataset_hash,
            values={k: montant_canonique(v) for k, v in rapport.values.items()},
            seal=sceller(rapport),
            published_by=utilisateur.id,
            published_at=publie_le,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=publie.org_id,
            actor_id=utilisateur.id,
            action="report_published",
            object_type="rapport_publie",
            object_id=publie.id,
            project_id=project_id,
            after={"template": publie.template_code, "seal": bytes(publie.seal).hex()},
        )
    return publie


def comparer_valeurs(anciennes: dict, nouvelles: dict) -> list[Ecart]:
    """Les rubriques/colonnes qui diffèrent (ajoutées, retirées ou modifiées), triées."""
    ecarts = []
    for cle in sorted(set(anciennes) | set(nouvelles)):
        ancien = Decimal(anciennes[cle]) if cle in anciennes else None
        nouveau = Decimal(nouvelles[cle]) if cle in nouvelles else None
        if ancien != nouveau:
            rubrique, _, colonne = cle.partition(SEP)
            ecarts.append(Ecart(rubrique, colonne, ancien, nouveau))
    return ecarts


def analyser_causes(rapport: RapportPublie) -> list[CauseEcriture]:
    """Les écritures comptabilisées APRÈS la publication, dans le périmètre du rapport."""
    where, params, _, _ = _parametres_source(rapport.params)
    with connection.cursor() as cur:
        cur.execute(
            f"""
            SELECT numero, accounting_date, compte, debit - credit,
                   contrepasse_ecriture_id, comptabilisee_le,
                   (SELECT r.numero FROM moteur_ligneecriture r
                     WHERE r.ecriture_id = moteur_ligneecriture.contrepasse_ecriture_id LIMIT 1)
              FROM moteur_ligneecriture
             WHERE {where} AND comptabilisee_le > %s
             ORDER BY comptabilisee_le, moteur_ligneecriture.numero, ligne_no
            """,  # noqa: S608  (prédicat issu du compilateur ; valeurs en paramètres)
            [*params, rapport.published_at],
        )
        lignes = cur.fetchall()
    return [
        CauseEcriture(
            ecriture=numero or "",
            date=date,
            compte=compte,
            montant=montant,
            contre_passation_de=inverse,
            comptabilisee_le=quand,
        )
        for numero, date, compte, montant, _, quand, inverse in lignes
    ]


def regenerer(rapport: RapportPublie) -> ResultatRegeneration:
    """Rejoue le rapport avec le modèle, les mappings et les paramètres D'ALORS.

    Même scellé : identique. Sinon : les écarts par rubrique et leurs causes nommées.
    """
    nouveau = generer_rapport(
        modele=rapport.modele,
        params=rapport.params,
        tables=_tables_par_code(rapport.mapping_versions),
        period_from=rapport.period_from,
        period_to=rapport.period_to,
        config_version=rapport.config_version,
    )
    if sceller(nouveau) == bytes(rapport.seal):
        return ResultatRegeneration(identique=True)
    ecarts = comparer_valeurs(
        rapport.values, {k: montant_canonique(v) for k, v in nouveau.values.items()}
    )
    causes = analyser_causes(rapport)
    return ResultatRegeneration(
        identique=False,
        ecarts=ecarts,
        causes=causes,
        inexpliquee=not causes,
    )
