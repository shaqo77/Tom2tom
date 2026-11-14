"""Rapprochement bancaire : import du relevé, rapprochement, annulation, état. Voir L3-T07 (b).

Habilitation : `comptabiliser` pour importer, rapprocher et annuler ; `consulter` pour l'état.

Les deux sens de la monnaie :
- DEVISE : la somme des lignes du grand livre égale celle des mouvements du relevé, exactement ;
- MONNAIE DE TENUE : si la valorisation du relevé (taux du jour de l'opération) diffère de celle du
  grand livre (taux de l'écriture), la différence est un ÉCART DE CHANGE : il devient une écriture
  EXPLICITE (gain ou perte) qui entre dans le groupe, jamais un ajustement silencieux.
"""

import datetime
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.i18n import Liste, msg
from niveau1_socle.comptabilite.annuelle import _comptabiliser_par_le_systeme
from niveau1_socle.comptabilite.models import Ecriture, Journal, LigneEcriture
from niveau1_socle.comptabilite.services import (
    _creer_inverse,
    _exiger_periode_ouverte,
    _periode_pour,
)
from niveau1_socle.financements.models import CompteBancaire
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.organisations.models import Projet
from niveau1_socle.referentiels.comptes import exiger_compte_imputable
from niveau1_socle.referentiels.models import Devise

from .models import MouvementReleve, Rapprochement, StatutRapprochement

ZERO = Decimal(0)
JOURNAL_ECARTS = "CHG"


class ReleveInvalide(ValueError):
    """Le relevé importé est incohérent."""


class RapprochementImpossible(ValueError):
    """Le groupe ne peut pas être rapproché ; `raisons` les liste toutes."""

    def __init__(self, raisons: list[str]):
        self.raisons = raisons
        super().__init__(Liste(raisons))


def _habilite(utilisateur, operation: str, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(msg("rapprochement.vous_etes_habilite_projet", operation=operation))


def _contexte(compte: CompteBancaire):
    projet = Projet.objects.get(pk=compte.project_id)
    base = Devise.objects.get(pk=projet.base_currency)
    return projet, base, compte.devise_id != base.code


def _arrondi(montant: Decimal, devise: Devise) -> Decimal:
    return montant.quantize(Decimal(1).scaleb(-devise.decimales), rounding=ROUND_HALF_UP)


def _montant_devise(ligne: LigneEcriture, etrangere: bool) -> Decimal:
    """Le montant d'une ligne dans la devise du compte (même règle que la base)."""
    return ligne.debit_cur - ligne.credit_cur if etrangere else ligne.debit - ligne.credit


# --- import du relevé -------------------------------------------------------------------------


def importer_mouvements(*, utilisateur, compte: CompteBancaire, mouvements: list[dict]):
    """Importe des mouvements de relevé. Rejouable : une référence déjà importée est ignorée si
    elle porte les mêmes valeurs, refusée sinon. Retourne `(importés, ignorés)`.

    Un mouvement : `reference`, `date`, `montant` (devise du compte, positif = encaissement),
    `libelle` et, pour un compte en devise étrangère, `taux` vers la monnaie de tenue.
    """
    _habilite(utilisateur, "comptabiliser", compte.project_id)
    _, base, etrangere = _contexte(compte)
    deja = {m.reference: m for m in MouvementReleve.objects.filter(compte=compte)}
    nouveaux, ignores, vus = [], 0, set()
    for brut in mouvements:
        reference = str(brut.get("reference", "")).strip()
        if not reference:
            raise ReleveInvalide(msg("rapprochement.chaque_mouvement_releve_reference"))
        if reference in vus:
            raise ReleveInvalide(
                msg("rapprochement.reference_figure_deux_fois_import", reference=reference)
            )
        vus.add(reference)
        montant = Decimal(str(brut["montant"]))
        taux = Decimal(str(brut.get("taux", 1)))
        if montant == 0:
            raise ReleveInvalide(msg("rapprochement.mouvement_montant_nul", reference=reference))
        if taux <= 0:
            raise ReleveInvalide(
                msg("rapprochement.mouvement_taux_non_positif", reference=reference)
            )
        if not etrangere and taux != 1:
            raise ReleveInvalide(
                msg("rapprochement.mouvement_compte_monnaie_tenue_taux", reference=reference)
            )
        valeurs = (brut["date"], montant, taux)
        existant = deja.get(reference)
        if existant is not None:
            if (existant.date_operation, existant.montant, existant.taux) != valeurs:
                raise ReleveInvalide(
                    msg("rapprochement.reference_deja_importee_autres_valeurs", reference=reference)
                )
            ignores += 1
            continue
        nouveaux.append(
            MouvementReleve(
                org_id=utilisateur.org_id,
                project_id=compte.project_id,
                compte=compte,
                reference=reference,
                date_operation=brut["date"],
                libelle=brut.get("libelle", ""),
                montant=montant,
                taux=taux,
                montant_base=_arrondi(montant * taux, base),
                created_by=utilisateur.id,
            )
        )
    with transaction.atomic():
        MouvementReleve.objects.bulk_create(nouveaux)
        if nouveaux:
            journaliser(
                org_id=utilisateur.org_id,
                actor_id=utilisateur.id,
                action="bank_movements_imported",
                object_type="compte_bancaire",
                object_id=compte.id,
                project_id=compte.project_id,
                after={"importes": len(nouveaux), "ignores": ignores},
            )
    return nouveaux, ignores


# --- rapprocher -------------------------------------------------------------------------------


def _problemes(compte, etrangere, lignes, mouvements, ids_lignes, ids_mouvements) -> list[str]:
    raisons = []
    if len(lignes) != len(ids_lignes) or len(mouvements) != len(ids_mouvements):
        raisons.append(msg("rapprochement.ligne_mouvement_introuvable"))
    if not lignes or not mouvements:
        raisons.append(msg("rapprochement.rapprochement_compte_moins_ligne_mouvement"))
    for ligne in lignes:
        if ligne.bank_account_id != compte.pk:
            raisons.append(
                msg(
                    "rapprochement.ligne_celle_compte",
                    number=ligne.entry.number,
                    line_no=ligne.line_no,
                )
            )
        if ligne.bank_match_id is not None:
            raisons.append(
                msg(
                    "rapprochement.ligne_deja_rapprochee",
                    number=ligne.entry.number,
                    line_no=ligne.line_no,
                )
            )
        if ligne.entry.status not in ("posted", "locked"):
            raisons.append(msg("rapprochement.on_rapproche_lignes_comptabilisees"))
        if etrangere and ligne.currency_id != compte.devise_id:
            raisons.append(
                msg(
                    "rapprochement.ligne",
                    number=ligne.entry.number,
                    line_no=ligne.line_no,
                    devise_id=compte.devise_id,
                )
            )
    if len({ligne.account_id for ligne in lignes}) > 1:
        raisons.append(msg("rapprochement.lignes_doivent_porter_meme_compte"))
    for mouvement in mouvements:
        if mouvement.compte_id != compte.pk:
            raisons.append(
                msg("rapprochement.mouvement_celui_compte", reference=mouvement.reference)
            )
        if mouvement.rapprochement_id is not None:
            raisons.append(
                msg("rapprochement.mouvement_deja_rapproche", reference=mouvement.reference)
            )
    if lignes and mouvements and not raisons:
        grand_livre = sum((_montant_devise(ligne, etrangere) for ligne in lignes), ZERO)
        releve = sum((m.montant for m in mouvements), ZERO)
        if grand_livre != releve:
            raisons.append(
                msg(
                    "rapprochement.groupe_solde_grand_livre_releve",
                    devise_id=compte.devise_id,
                    grand_livre=grand_livre,
                    releve=releve,
                    v1=releve - grand_livre,
                )
            )
    return list(dict.fromkeys(raisons))


def rapprocher(
    *,
    utilisateur,
    compte: CompteBancaire,
    lignes,
    mouvements,
    compte_gain_change: str | None = None,
    compte_perte_change: str | None = None,
    date_ecart: datetime.date | None = None,
) -> Rapprochement:
    """Rapproche des lignes du grand livre et des mouvements du relevé.

    Le groupe doit être soldé en devise. S'il ne l'est pas en monnaie de tenue, l'écart de change
    est enregistré dans une écriture explicite (journal `CHG`), comptabilisée par le système et
    portée sur `compte_gain_change` (relevé plus favorable) ou `compte_perte_change`.
    """
    _habilite(utilisateur, "comptabiliser", compte.project_id)
    projet, base, etrangere = _contexte(compte)
    ids_lignes = list({getattr(x, "pk", x) for x in lignes})
    ids_mouvements = list({getattr(x, "pk", x) for x in mouvements})
    with transaction.atomic():
        # Verrou de ligne, dans un ordre fixe : deux rapprochements simultanés des mêmes lignes ou
        # mouvements ne passent pas ensemble (le second les trouve déjà rapprochés).
        courantes = list(
            LigneEcriture.objects.select_for_update(of=("self",))
            .select_related("entry")
            .filter(pk__in=ids_lignes)
            .order_by("pk")
        )
        releves = list(
            MouvementReleve.objects.select_for_update().filter(pk__in=ids_mouvements).order_by("pk")
        )
        raisons = _problemes(compte, etrangere, courantes, releves, ids_lignes, ids_mouvements)
        if raisons:
            raise RapprochementImpossible(raisons)

        valeur_grand_livre = sum((li.debit - li.credit for li in courantes), ZERO)
        valeur_releve = sum((m.montant_base for m in releves), ZERO)
        ecart = valeur_releve - valeur_grand_livre
        rapprochement_id = Rapprochement._meta.pk.default()  # connu avant l'écriture d'écart
        ecriture = None
        if ecart != 0:
            ecriture = _ecriture_d_ecart(
                utilisateur,
                compte,
                projet,
                courantes,
                releves,
                ecart,
                rapprochement_id,
                compte_gain_change,
                compte_perte_change,
                date_ecart,
            )
            courantes.append(ecriture.lignes.get(account_id=courantes[0].account_id))

        with connection.cursor() as cur:  # le code se déduit d'un décompte : on sérialise
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                [f"rapprochement:{compte.pk}"],
            )
        rang = Rapprochement.objects.filter(compte=compte).count() + 1
        rapprochement = Rapprochement.objects.create(
            id=rapprochement_id,
            org_id=utilisateur.org_id,
            project_id=compte.project_id,
            compte=compte,
            code=f"R{rang:05d}",
            rapproche_by=utilisateur.id,
            ecart_change=ecart,
            ecriture_ecart=ecriture,
            created_by=utilisateur.id,
        )
        # Le groupe, ligne d'écart comprise ; `update` d'un queryset : rien n'est « réécrit ».
        LigneEcriture.objects.filter(pk__in=[li.pk for li in courantes]).update(
            bank_match_id=rapprochement.pk
        )
        MouvementReleve.objects.filter(pk__in=ids_mouvements).update(rapprochement=rapprochement)
        journaliser(
            org_id=rapprochement.org_id,
            actor_id=utilisateur.id,
            action="bank_reconciled",
            object_type="rapprochement",
            object_id=rapprochement.id,
            project_id=rapprochement.project_id,
            after={
                "code": rapprochement.code,
                "compte": compte.code,
                "lignes": len(courantes),
                "mouvements": len(releves),
                "ecart_change": str(ecart),
            },
        )
    return rapprochement


def _ecriture_d_ecart(
    utilisateur, compte, projet, lignes, mouvements, ecart, rapprochement_id, gain, perte, date
) -> Ecriture:
    """L'écriture explicite de l'écart de change : le compte bancaire d'un côté, gain ou perte de
    l'autre. Montants en monnaie de tenue ; aucun montant en devise (c'est une revalorisation)."""
    compte_resultat = gain if ecart > 0 else perte
    nom = "compte_gain_change" if ecart > 0 else "compte_perte_change"
    if not compte_resultat:
        raise RapprochementImpossible(
            [f"Écart de change de {ecart} à enregistrer : précisez {nom}"]
        )
    resultat = exiger_compte_imputable(compte_resultat)
    jour = date or max(m.date_operation for m in mouvements)
    periode = _periode_pour(compte.project_id, jour)
    _exiger_periode_ouverte(periode)
    journal, _ = Journal.objects.get_or_create(
        org_id=compte.org_id, code=JOURNAL_ECARTS, defaults={"label": {"fr": "Écarts de change"}}
    )
    ecriture = Ecriture.objects.create(
        org_id=compte.org_id,
        project_id=compte.project_id,
        exercice=periode.exercice,
        periode=periode,
        journal=journal,
        accounting_date=jour,
        label=f"Écart de change du rapprochement de {compte.code}",
        status="draft",
        currency_id=compte.devise_id,
        fx_rate=Decimal(1),
        origin="module",
        origin_module="rapprochement",
        idempotency_key=f"rapprochement:{rapprochement_id}",
        created_by=utilisateur.id,
    )
    commun = {
        "org_id": compte.org_id,
        "project_id": compte.project_id,
        "entry": ecriture,
        "currency_id": compte.devise_id,
        "fx_rate": Decimal(1),
        "debit_cur": ZERO,
        "credit_cur": ZERO,
    }
    LigneEcriture.objects.create(
        line_no=1,
        account_id=lignes[0].account_id,
        bank_account_id=compte.pk,
        debit=max(ecart, ZERO),
        credit=max(-ecart, ZERO),
        **commun,
    )
    LigneEcriture.objects.create(
        line_no=2,
        account=resultat,
        debit=max(-ecart, ZERO),
        credit=max(ecart, ZERO),
        **commun,
    )
    return _comptabiliser_par_le_systeme(ecriture, utilisateur)


# --- annuler ----------------------------------------------------------------------------------


def annuler_rapprochement(
    rapprochement: Rapprochement,
    *,
    utilisateur,
    motif: str,
    date_comptable: datetime.date | None = None,
) -> Rapprochement:
    """Défait un rapprochement : lignes et mouvements reviennent à leur état initial. S'il avait
    produit une écriture d'écart de change, elle est CONTRE-PASSÉE (jamais supprimée), à
    `date_comptable` (par défaut le jour de l'écriture, qui doit alors être en période ouverte)."""
    if not (motif or "").strip():
        raise RapprochementImpossible(["L'annulation d'un rapprochement exige un motif"])
    with transaction.atomic():
        courant = Rapprochement.objects.select_for_update().get(pk=rapprochement.pk)
        _habilite(utilisateur, "comptabiliser", courant.project_id)
        if courant.status != StatutRapprochement.ACTIF:
            raise RapprochementImpossible([f"Le rapprochement {courant.code} est déjà annulé"])
        inverse = None
        if courant.ecriture_ecart_id:
            origine = Ecriture.objects.select_related("journal").get(pk=courant.ecriture_ecart_id)
            jour = date_comptable or origine.accounting_date
            periode = _periode_pour(origine.project_id, jour)
            _exiger_periode_ouverte(periode)
            inverse = _creer_inverse(
                origine,
                auteur_id=utilisateur.id,
                date=jour,
                periode=periode,
                libelle=f"Annulation de l'écart de change {origine.number} ({courant.code})",
            )
            inverse = _comptabiliser_par_le_systeme(inverse, utilisateur)
        LigneEcriture.objects.filter(bank_match_id=courant.pk).update(bank_match_id=None)
        MouvementReleve.objects.filter(rapprochement=courant).update(rapprochement=None)
        Rapprochement.objects.filter(pk=courant.pk).update(
            status=StatutRapprochement.ANNULE,
            annule_at=timezone.now(),
            annule_by=utilisateur.id,
            motif_annulation=motif.strip(),
            ecriture_ecart_annulation=inverse,
        )
        journaliser(
            org_id=courant.org_id,
            actor_id=utilisateur.id,
            action="bank_unreconciled",
            object_type="rapprochement",
            object_id=courant.id,
            project_id=courant.project_id,
            after={"code": courant.code, "motif": motif.strip()},
        )
    rapprochement.refresh_from_db()
    return rapprochement


# --- l'état de rapprochement ------------------------------------------------------------------


@dataclass
class EtatRapprochement:
    compte: CompteBancaire
    date: datetime.date
    devise: str
    solde_releve: Decimal  # ouverture + mouvements au plus tard à `date`
    solde_comptable: Decimal  # lignes comptabilisées du compte, dans la devise du compte
    lignes_en_suspens: list = field(default_factory=list)  # au grand livre, pas au relevé
    mouvements_en_suspens: list = field(default_factory=list)  # au relevé, pas au grand livre

    @property
    def total_lignes_en_suspens(self) -> Decimal:
        return sum((_montant for _, _montant in self.lignes_en_suspens), ZERO)

    @property
    def total_mouvements_en_suspens(self) -> Decimal:
        return sum((m.montant for m in self.mouvements_en_suspens), ZERO)

    @property
    def ecart(self) -> Decimal:
        """Ce que les éléments en suspens n'expliquent pas. Nul : le rapprochement est justifié.

        solde du relevé = solde comptable − lignes en suspens + mouvements en suspens.
        """
        attendu = (
            self.solde_comptable - self.total_lignes_en_suspens + self.total_mouvements_en_suspens
        )
        return self.solde_releve - attendu

    @property
    def justifie(self) -> bool:
        return self.ecart == 0


def etat_de_rapprochement(
    utilisateur, compte: CompteBancaire, date: datetime.date, *, solde_ouverture=0
) -> EtatRapprochement:
    """La preuve de solde d'un compte bancaire à `date`.

    `solde_ouverture` : le solde du relevé avant le premier mouvement importé, dans la devise du
    compte (nul pour un compte neuf). L'état de rapprochement est le document que le bailleur lit :
    il part du solde de la banque et retrouve le solde comptable, élément en suspens par élément.
    """
    _habilite(utilisateur, "consulter", compte.project_id)
    _, _, etrangere = _contexte(compte)
    lignes = list(
        LigneEcriture.objects.filter(
            bank_account_id=compte.pk,
            entry__status__in=("posted", "locked"),
            entry__accounting_date__lte=date,
        ).select_related("entry")
    )
    mouvements = list(
        MouvementReleve.objects.filter(compte=compte, date_operation__lte=date).order_by(
            "date_operation", "reference"
        )
    )
    return EtatRapprochement(
        compte=compte,
        date=date,
        devise=compte.devise_id,
        solde_releve=Decimal(str(solde_ouverture)) + sum((m.montant for m in mouvements), ZERO),
        solde_comptable=sum((_montant_devise(li, etrangere) for li in lignes), ZERO),
        lignes_en_suspens=[
            (li, _montant_devise(li, etrangere)) for li in lignes if li.bank_match_id is None
        ],
        mouvements_en_suspens=[m for m in mouvements if m.rapprochement_id is None],
    )
