"""Fabrique de pièces comptables pour les tests. Voir L3-T01.

Les états de référence du lot L0 ont été écrits avec des lignes « à plat » (comptes et axes en
codes texte). Le grand livre définitif exige de vraies pièces : journal, exercice, période,
comptes, valeurs d'axe. Cette fabrique les crée à la demande, avec des identifiants stables,
pour que les tests restent lisibles.

Accord, catégorie et site n'ont pas encore de référentiel (lot L4) : la fabrique accepte leur
nom symbolique (`"IDA-6789"`) et le traduit en UUID stable, que la vue du moteur expose en
texte. Les tests qui filtrent sur un accord utilisent `id_objet("IDA-6789")` côté paramètre.
"""

import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace

from django.db import connection, transaction
from django.utils import timezone

from niveau1_socle.comptabilite.models import Ecriture, Journal, LigneEcriture
from niveau1_socle.exercices.models import Exercice
from niveau1_socle.exercices.services import creer_exercice
from niveau1_socle.referentiels.models import Compte, Devise, PlanDimension, Tiers, ValeurDimension
from niveau1_socle.referentiels.semences import charger

PROJET_PAR_DEFAUT = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
_ESPACE = uuid.UUID("0b1ec7a5-0000-4000-8000-00000000f00d")


def id_objet(nom: str | None):
    """UUID stable d'un objet symbolique (accord, catégorie, site). `None` reste `None`."""
    return None if nom is None else uuid.uuid5(_ESPACE, nom)


def assurer_devises() -> None:
    """Recharge le référentiel des devises.

    Les tests en `transaction=True` vident toutes les tables après chaque test, y compris
    les données posées par migration. Le référentiel est en lecture seule pour l'application :
    on lève donc, le temps de la recharge, le verrou que les migrations lèvent aussi.
    """
    if not Devise.objects.exists():
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute("SET LOCAL sigf.ecriture_referentiel = 'on'")
            charger(Devise)


def _compte(org_id, code):
    compte, _ = Compte.objects.get_or_create(
        org_id=org_id,
        code=code,
        defaults={
            "label": {"fr": f"Compte {code}", "en": f"Account {code}"},
            "classe": int(code[0]),
            "sens_normal": "credit" if code[0] in "17" else "debit",
        },
    )
    return compte


def _valeur_axe(org_id, code, emplacement=1):
    if code is None:
        return None
    plan, _ = PlanDimension.objects.get_or_create(
        org_id=org_id,
        kind="gestion",
        slot=emplacement,
        defaults={"code": f"AXE{emplacement}", "label": {"fr": f"Axe {emplacement}"}},
    )
    valeur, _ = ValeurDimension.objects.get_or_create(
        org_id=org_id, plan=plan, code=code, defaults={"label": {"fr": code}}
    )
    return valeur


def _exercice(org_id, project_id, annee):
    exercice = Exercice.objects.filter(project_id=project_id, annee=annee).first()
    if exercice is None:
        exercice = creer_exercice(
            SimpleNamespace(org_id=org_id, id=project_id), annee, utilisateur=None
        )
    return exercice


def creer_ligne(
    org_id,
    compte,
    annee,
    periode,
    *,
    debit="0",
    credit="0",
    accord=None,
    categorie=None,
    site=None,
    dim1=None,
    tiers=None,
    project_id=PROJET_PAR_DEFAUT,
    devise="DJF",
    taux="1",
    statut="posted",
    utilisateur_id=None,
    journal="OD",
):
    """Crée une pièce d'UNE ligne. Utile aux tests de lecture du moteur ; déséquilibrée."""
    return creer_piece(
        org_id,
        annee,
        periode,
        [
            {
                "compte": compte,
                "debit": debit,
                "credit": credit,
                "accord": accord,
                "categorie": categorie,
                "site": site,
                "dim1": dim1,
                "tiers": tiers,
            }
        ],
        project_id=project_id,
        devise=devise,
        taux=taux,
        statut=statut,
        utilisateur_id=utilisateur_id,
        journal=journal,
    ).lignes.get()


def creer_piece(
    org_id,
    annee,
    periode,
    lignes,
    *,
    project_id=PROJET_PAR_DEFAUT,
    devise="DJF",
    taux="1",
    statut="posted",
    utilisateur_id=None,
    journal="OD",
    jour=15,
):
    """Crée une écriture et ses lignes. Un `statut` comptabilisé reçoit son numéro."""
    assurer_devises()
    with transaction.atomic():
        exercice = _exercice(org_id, project_id, annee)
        per = exercice.periodes.get(numero=periode)
        jrn, _ = Journal.objects.get_or_create(
            org_id=org_id, code=journal, defaults={"label": {"fr": journal}}
        )
        numero = None
        comptabilisee = statut in ("posted", "locked")
        if comptabilisee:
            deja = Ecriture.objects.filter(journal=jrn, exercice=exercice).count()
            numero = f"{journal}-{annee}-{deja + 1:06d}"
        ecriture = Ecriture.objects.create(
            org_id=org_id,
            project_id=project_id,
            exercice=exercice,
            periode=per,
            journal=jrn,
            number=numero,
            accounting_date=datetime.date(annee, per.date_debut.month, min(jour, 28)),
            label="Pièce de test",
            status=statut,
            currency_id=devise,
            fx_rate=Decimal(str(taux)),
            origin="saisie",
            posted_at=timezone.now() if comptabilisee else None,
            posted_by=(utilisateur_id or uuid.uuid4()) if comptabilisee else None,
            created_by=utilisateur_id,
        )
        for numero_ligne, ligne in enumerate(lignes, start=1):
            LigneEcriture.objects.create(
                org_id=org_id,
                project_id=project_id,
                entry=ecriture,
                line_no=numero_ligne,
                account=_compte(org_id, ligne["compte"]),
                partner=(
                    Tiers.objects.get_or_create(
                        org_id=org_id,
                        code=ligne["tiers"],
                        defaults={"nature": "autre", "nom": ligne["tiers"]},
                    )[0]
                    if ligne.get("tiers")
                    else None
                ),
                dim1=_valeur_axe(org_id, ligne.get("dim1")),
                agreement_id=id_objet(ligne.get("accord")),
                category_id=id_objet(ligne.get("categorie")),
                site_id=id_objet(ligne.get("site")),
                debit=Decimal(str(ligne.get("debit", "0"))),
                credit=Decimal(str(ligne.get("credit", "0"))),
                currency_id=devise,
                fx_rate=Decimal(str(taux)),
            )
    return ecriture
