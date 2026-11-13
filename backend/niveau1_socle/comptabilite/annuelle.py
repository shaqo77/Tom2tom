"""Clôture annuelle et à-nouveaux. Voir L3-T08 (partie b), 04_PLAN_LOTS_L0_A_L4.md.

Clôturer un exercice reporte, dans une écriture d'à-nouveaux de l'exercice suivant, les soldes des
comptes de bilan (classes 1 à 5) PAR COMPTE, TIERS ET ACCORD DE FINANCEMENT ; le résultat
(classes 6 et 7) est porté sur un compte donné, au crédit pour un bénéfice. Les classes 8 et 9 ne
sont pas reportées : elles doivent se solder entre elles, sinon on refuse de générer.

Les à-nouveaux sont VERSIONNÉS. Tant que l'exercice d'origine n'est pas verrouillé, on peut les
régénérer après une correction : l'écriture de l'ancienne version est contre-passée (une écriture
comptabilisée ne se modifie jamais), puis la nouvelle version la remplace. Si rien n'a changé, rien
n'est écrit.
"""

import datetime
import hashlib
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from core.audit import journaliser
from niveau1_socle.exercices.models import Exercice
from niveau1_socle.exercices.services import exercice_verrouille
from niveau1_socle.organisations.models import Projet
from niveau1_socle.referentiels.comptes import exiger_compte_imputable

from .models import ANouveau, Ecriture, Journal, LigneEcriture
from .services import _creer_inverse, _exiger_habilitation

ZERO = Decimal(0)
CLASSES_REPORTEES = (1, 2, 3, 4, 5)
CLASSES_RESULTAT = (6, 7)
JOURNAL_A_NOUVEAUX = "AN"


class ExerciceNonCloturable(ValueError):
    """Une condition de la clôture annuelle n'est pas remplie."""


class ExerciceVerrouille(ValueError):
    """Toutes les périodes sont verrouillées : les à-nouveaux ne se régénèrent plus."""


class ANouveauxIncoherents(ValueError):
    """Les soldes ne permettent pas de produire des à-nouveaux fiables."""


@dataclass(frozen=True)
class LigneANouveau:
    compte: str
    tiers: str | None
    accord: object  # UUID de l'accord de financement, ou None
    montant: Decimal  # débit positif, crédit négatif
    compte_id: object = None
    tiers_id: object = None


@dataclass
class ResultatCloture:
    statut: str  # "genere", "inchange" ou "regenere"
    a_nouveau: ANouveau
    difference: dict


def _cle(ligne: LigneANouveau) -> tuple:
    return (ligne.compte, ligne.tiers, ligne.accord)


def calculer_a_nouveaux(exercice: Exercice, compte_resultat: str):
    """Les lignes d'à-nouveaux et le résultat (bénéfice positif) d'un exercice. N'écrit rien.

    Seules les écritures comptabilisées ou verrouillées comptent. Les soldes nuls ne sont pas
    reportés. Retourne `(lignes, resultat)`.
    """
    soldes = (
        LigneEcriture.objects.filter(
            entry__exercice=exercice, entry__status__in=("posted", "locked")
        )
        .values(
            "account_id",
            "account__code",
            "account__classe",
            "partner_id",
            "partner__code",
            "agreement_id",
        )
        .annotate(net=Sum(F("debit") - F("credit")))
        .order_by("account__code", "partner__code", "agreement_id")
    )
    reportees: dict[tuple, LigneANouveau] = {}
    ecart_89 = ZERO
    for s in soldes:
        net = s["net"] or ZERO
        classe = s["account__classe"]
        if classe in CLASSES_REPORTEES and net != 0:
            ligne = LigneANouveau(
                s["account__code"],
                s["partner__code"],
                s["agreement_id"],
                net,
                s["account_id"],
                s["partner_id"],
            )
            reportees[_cle(ligne)] = ligne
        elif classe not in CLASSES_REPORTEES and classe not in CLASSES_RESULTAT:
            ecart_89 += net
    if ecart_89 != 0:
        raise ANouveauxIncoherents(
            f"Les classes 8 et 9 ne se soldent pas entre elles : écart de {ecart_89}"
        )

    deficit = sum((ligne.montant for ligne in reportees.values()), ZERO)
    # Toutes classes confondues, les écritures s'équilibrent : le net de bilan est l'exact
    # opposé du net 6 + 7 (une fois les classes 8 et 9 soldées).
    resultat = deficit
    if resultat != 0:
        compte = exiger_compte_imputable(compte_resultat)
        cle = (compte_resultat, None, None)
        existante = reportees.get(cle)
        montant = -resultat + (existante.montant if existante else ZERO)
        if montant != 0:
            reportees[cle] = LigneANouveau(compte_resultat, None, None, montant, compte.id)
        else:
            reportees.pop(cle, None)
    return sorted(
        reportees.values(),
        key=lambda ligne: (ligne.compte, ligne.tiers or "", str(ligne.accord or "")),
    ), resultat


def _empreinte(lignes: list[LigneANouveau]) -> str:
    canonique = "\n".join(
        f"{ligne.compte}|{ligne.tiers or ''}|{ligne.accord or ''}|{ligne.montant:f}"
        for ligne in sorted(
            lignes, key=lambda ligne: (ligne.compte, ligne.tiers or "", str(ligne.accord or ""))
        )
    )
    return hashlib.sha256(canonique.encode()).hexdigest()


def comparer(avant: dict, apres: dict) -> dict:
    """Compare deux jeux de soldes `{(compte, tiers, accord): montant}`."""
    ajoutees = sorted((k, apres[k]) for k in apres.keys() - avant.keys())
    supprimees = sorted((k, avant[k]) for k in avant.keys() - apres.keys())
    modifiees = sorted(
        ((k, avant[k], apres[k]) for k in avant.keys() & apres.keys() if avant[k] != apres[k]),
        key=lambda m: str(m[0]),
    )
    return {
        "identique": not (ajoutees or supprimees or modifiees),
        "ajoutees": ajoutees,
        "supprimees": supprimees,
        "modifiees": modifiees,
    }


def _soldes_de(ecriture: Ecriture) -> dict:
    soldes: dict[tuple, Decimal] = {}
    for ligne in ecriture.lignes.select_related("account", "partner"):
        cle = (
            ligne.account.code,
            ligne.partner.code if ligne.partner else None,
            ligne.agreement_id,
        )
        soldes[cle] = soldes.get(cle, ZERO) + ligne.debit - ligne.credit
    return soldes


def _comptabiliser_par_le_systeme(ecriture: Ecriture, utilisateur) -> Ecriture:
    """Brouillon -> comptabilisée ; la base attribue le numéro. Pièce produite par le système."""
    Ecriture.objects.filter(pk=ecriture.pk).update(
        status="posted", posted_at=timezone.now(), posted_by=utilisateur.id
    )
    ecriture.refresh_from_db()
    return ecriture


def _exercice_suivant(exercice: Exercice) -> Exercice:
    suivant = Exercice.objects.filter(
        project_id=exercice.project_id, date_debut=exercice.date_fin + datetime.timedelta(days=1)
    ).first()
    if suivant is None:
        raise ExerciceNonCloturable(
            "Aucun exercice suivant ne commence le lendemain de la fin de cet exercice : "
            "créez-le avant de clôturer"
        )
    return suivant


def _periodes_non_closes(exercice: Exercice) -> list[int]:
    return list(
        exercice.periodes.filter(status="ouverte")
        .order_by("numero")
        .values_list("numero", flat=True)
    )


def cloturer_exercice(exercice: Exercice, *, utilisateur, compte_resultat: str) -> ResultatCloture:
    """Clôture l'exercice et génère (ou régénère) ses à-nouveaux. Rejouable sans effet de bord."""
    with transaction.atomic():
        # Verrou : deux clôtures simultanées ne produisent pas deux versions.
        exercice = Exercice.objects.select_for_update().get(pk=exercice.pk)
        _exiger_habilitation(utilisateur, "comptabiliser", exercice.project_id)
        if exercice_verrouille(exercice):
            raise ExerciceVerrouille(
                f"L'exercice {exercice.annee} est verrouillé : ses à-nouveaux ne se régénèrent plus"
            )
        ouvertes = _periodes_non_closes(exercice)
        if ouvertes:
            raise ExerciceNonCloturable(
                "Périodes non closes : " + ", ".join(str(n) for n in ouvertes)
            )
        cible = _exercice_suivant(exercice)
        premiere = cible.periodes.filter(numero=1).first()
        if premiere is None or premiere.status != "ouverte":
            raise ExerciceNonCloturable(
                f"La première période de l'exercice suivant ({cible.annee}) doit être ouverte "
                "pour recevoir les à-nouveaux"
            )
        exiger_compte_imputable(compte_resultat)
        lignes, resultat = calculer_a_nouveaux(exercice, compte_resultat)
        empreinte = _empreinte(lignes)
        apres = {_cle(ligne): ligne.montant for ligne in lignes}

        actif = ANouveau.objects.filter(exercice_source=exercice, status="actif").first()
        if actif is not None and actif.empreinte == empreinte:
            Exercice.objects.filter(pk=exercice.pk).update(status="clos")
            journaliser(
                org_id=exercice.org_id,
                actor_id=utilisateur.id,
                action="carry_forward_unchanged",
                object_type="a_nouveau",
                object_id=actif.id,
                project_id=exercice.project_id,
                after={"version": actif.version},
            )
            return ResultatCloture("inchange", actif, comparer(apres, apres))

        avant = _soldes_de(actif.ecriture) if actif else {}
        version = 1
        if actif is not None:
            version = actif.version + 1
            inverse = _creer_inverse(
                actif.ecriture,
                auteur_id=utilisateur.id,
                date=premiere.date_debut,
                periode=premiere,
                libelle=f"Annulation des à-nouveaux de l'exercice {exercice.annee} "
                f"(version {actif.version}) : {actif.ecriture.number}",
            )
            inverse = _comptabiliser_par_le_systeme(inverse, utilisateur)
            # L'ancienne version cesse d'être active AVANT que la nouvelle ne le devienne.
            ANouveau.objects.filter(pk=actif.pk).update(
                status="remplace", ecriture_annulation=inverse
            )

        projet = Projet.objects.get(pk=exercice.project_id)
        journal, _ = Journal.objects.get_or_create(
            org_id=exercice.org_id,
            code=JOURNAL_A_NOUVEAUX,
            defaults={"label": {"fr": "À-nouveaux"}},
        )
        ecriture = Ecriture.objects.create(
            org_id=exercice.org_id,
            project_id=exercice.project_id,
            exercice=cible,
            periode=premiere,
            journal=journal,
            accounting_date=premiere.date_debut,
            label=f"À-nouveaux de l'exercice {exercice.annee} (version {version})",
            status="draft",
            currency_id=projet.base_currency,
            fx_rate=Decimal(1),
            origin="module",
            origin_module="a_nouveaux",
            idempotency_key=f"a_nouveaux:{exercice.id}:v{version}",
            created_by=utilisateur.id,
        )
        LigneEcriture.objects.bulk_create(
            [
                LigneEcriture(
                    org_id=exercice.org_id,
                    project_id=exercice.project_id,
                    entry=ecriture,
                    line_no=rang,
                    account_id=ligne.compte_id,
                    partner_id=ligne.tiers_id,
                    agreement_id=ligne.accord,
                    debit=max(ligne.montant, ZERO),
                    credit=max(-ligne.montant, ZERO),
                    debit_cur=ZERO,
                    credit_cur=ZERO,
                    currency_id=projet.base_currency,
                    fx_rate=Decimal(1),
                )
                for rang, ligne in enumerate(lignes, start=1)
            ]
        )
        ecriture = _comptabiliser_par_le_systeme(ecriture, utilisateur)
        nouveau = ANouveau.objects.create(
            org_id=exercice.org_id,
            project_id=exercice.project_id,
            exercice_source=exercice,
            exercice_cible=cible,
            version=version,
            status="actif",
            ecriture=ecriture,
            compte_resultat=compte_resultat,
            resultat=resultat,
            empreinte=empreinte,
            genere_by=utilisateur.id,
        )
        Exercice.objects.filter(pk=exercice.pk).update(status="clos")
        journaliser(
            org_id=exercice.org_id,
            actor_id=utilisateur.id,
            action="carry_forward_regenerated" if actif else "fiscal_year_closed",
            object_type="a_nouveau",
            object_id=nouveau.id,
            project_id=exercice.project_id,
            after={"version": version, "ecriture": ecriture.number, "resultat": str(resultat)},
        )
    return ResultatCloture("regenere" if actif else "genere", nouveau, comparer(avant, apres))
