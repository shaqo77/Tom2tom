"""Le disponible budgétaire. Voir L4-T02.

    disponible = Σ lignes de la version approuvée courante
               − Σ engagements non apurés
               − Σ lignes d'écriture comptabilisées

Contrôle : après 10 000 opérations aléatoires, `recalculer_soldes` donne exactement les mêmes
valeurs que l'incrémental (et qu'un calcul indépendant en Python).
"""

import random
import uuid
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from niveau1_socle.budget.engagements import (
    annuler_engagement,
    apurer_engagement,
    creer_engagement,
)
from niveau1_socle.budget.models import Engagement, LigneBudget, SoldeBudgetaire
from niveau1_socle.budget.services import (
    BudgetInvalide,
    ajouter_ligne,
    approuver_version,
    creer_version,
    modifier_ligne,
)
from niveau1_socle.budget.soldes import (
    comparer_soldes,
    recalculer_soldes,
    situation,
    verifier_soldes,
)
from niveau1_socle.comptabilite.models import Ecriture, Journal, LigneEcriture
from niveau1_socle.comptabilite.services import (
    comptabiliser_ecriture,
    contre_passer,
    valider_ecriture,
)
from niveau1_socle.exercices.models import Exercice
from niveau1_socle.exercices.services import TransitionInterdite
from tests.outils import _compte, _valeur_axe, connexion_proprietaire, creer_piece, id_objet
from tests.test_cycle_ecriture_bd import decor  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
D = Decimal


def _piece(org, projet, periode, lignes, **champs):
    """Une pièce dont la contrepartie en trésorerie (5211) est ajoutée pour l'équilibrer."""
    net = sum((D(str(x.get("debit", 0))) - D(str(x.get("credit", 0))) for x in lignes), D(0))
    contrepartie = (
        {"compte": "5211", "credit": str(net)}
        if net > 0
        else {"compte": "5211", "debit": str(-net)}
    )
    return creer_piece(
        org.id, 2026, periode, [*lignes, contrepartie], project_id=projet.id, **champs
    )


def _soldes(projet):
    """`{(dim1, periode, catégorie): (budget, engagé, consommé)}` des lignes de la courante."""
    return {
        (
            r.solde.ligne.dim1.code if r.solde.ligne.dim1 else None,
            r.solde.ligne.periode,
            r.solde.ligne.category_id,
            r.solde.ligne.agreement_id,
        ): (r.budget, r.engage, r.consomme)
        for r in situation(projet.id)
    }


L1 = ("COMP-A", None, id_objet("CAT-1"), None)  # composante A, catégorie 1
L2 = ("COMP-B", None, None, None)  # composante B
L3 = (None, None, None, id_objet("IDA-1"))  # tout l'accord IDA-1


@pytest.fixture
def cadre(decor):  # noqa: F811
    """Budget approuvé de trois lignes qui se recouvrent : A/CAT-1, B, et l'accord IDA-1."""
    organisation, projet, profils = decor
    _valeur_axe(organisation.id, "COMP-B")
    for code in ("2411", "7061", "6021"):
        _compte(organisation.id, code)
    version = creer_version(utilisateur=profils["amina"], project_id=projet.id, type="initial")
    amina = profils["amina"]
    ajouter_ligne(
        version,
        utilisateur=amina,
        annee=2026,
        montant="10000",
        devise="DJF",
        axes={"dim1": "COMP-A"},
        category_id=id_objet("CAT-1"),
    )
    ajouter_ligne(
        version,
        utilisateur=amina,
        annee=2026,
        montant="5000",
        devise="DJF",
        axes={"dim1": "COMP-B"},
    )
    ajouter_ligne(
        version,
        utilisateur=amina,
        annee=2026,
        montant="20000",
        devise="DJF",
        agreement_id=id_objet("IDA-1"),
    )
    return organisation, projet, profils, version


def _approuver(version, profils):
    approuver_version(version, utilisateur=profils["bruno"])


# --- initialisation, consommation ---------------------------------------------------------


def test_l_approbation_initialise_les_soldes_avec_l_existant(cadre):
    organisation, projet, profils, version = cadre
    # Avant l'approbation : une charge déjà comptabilisée et un engagement déjà ouvert.
    _piece(
        organisation,
        projet,
        1,
        [
            {
                "compte": "6011",
                "debit": "3000",
                "dim1": "COMP-A",
                "categorie": "CAT-1",
                "accord": "IDA-1",
            }
        ],
    )
    creer_engagement(
        utilisateur=profils["amina"],
        project_id=projet.id,
        reference="ENG-0",
        annee=2026,
        montant="1200",
        axes={"dim1": "COMP-B"},
    )
    assert SoldeBudgetaire.objects.count() == 0

    _approuver(version, profils)

    assert _soldes(projet) == {
        L1: (D(10000), D(0), D(3000)),
        L2: (D(5000), D(1200), D(0)),
        L3: (D(20000), D(0), D(3000)),  # la même charge compte aussi dans la ligne de l'accord
    }
    assert comparer_soldes(projet.id) == []


def test_une_ecriture_comptabilisee_consomme_les_seules_lignes_qui_la_couvrent(cadre):
    organisation, projet, profils, version = cadre
    _approuver(version, profils)

    _piece(organisation, projet, 2, [{"compte": "6011", "debit": "700", "dim1": "COMP-B"}])
    assert _soldes(projet)[L2][2] == D(700)
    assert _soldes(projet)[L1][2] == D(0) and _soldes(projet)[L3][2] == D(0)

    # Charge de la composante A, catégorie 1, accord IDA-1 : deux lignes la couvrent.
    _piece(
        organisation,
        projet,
        3,
        [
            {
                "compte": "6021",
                "debit": "300",
                "dim1": "COMP-A",
                "categorie": "CAT-1",
                "accord": "IDA-1",
            }
        ],
    )
    # Même composante A mais autre catégorie : la ligne A/CAT-1 ne la couvre pas.
    _piece(
        organisation,
        projet,
        3,
        [{"compte": "6021", "debit": "50", "dim1": "COMP-A", "categorie": "CAT-2"}],
    )
    soldes = _soldes(projet)
    assert soldes[L1][2] == D(300) and soldes[L3][2] == D(300) and soldes[L2][2] == D(700)
    assert comparer_soldes(projet.id) == []


def test_ce_qui_n_est_pas_une_charge_budgetee_ne_consomme_pas(cadre):
    organisation, projet, profils, version = cadre
    _approuver(version, profils)
    # Produit (7) et amortissement (28) : pas de consommation. Équipement (24) : oui.
    _compte(organisation.id, "2841")
    _piece(organisation, projet, 1, [{"compte": "7061", "credit": "900", "dim1": "COMP-B"}])
    _piece(organisation, projet, 1, [{"compte": "2841", "debit": "400", "dim1": "COMP-B"}])
    assert _soldes(projet)[L2][2] == D(0)
    _piece(organisation, projet, 1, [{"compte": "2411", "debit": "800", "dim1": "COMP-B"}])
    assert _soldes(projet)[L2][2] == D(800)


def test_un_brouillon_ne_consomme_rien_et_une_contrepassation_restitue(cadre):
    organisation, projet, profils, version = cadre
    _approuver(version, profils)
    _piece(
        organisation,
        projet,
        1,
        [{"compte": "6011", "debit": "999", "dim1": "COMP-B"}],
        statut="draft",
    )
    assert _soldes(projet)[L2][2] == D(0)

    posee = _piece(organisation, projet, 1, [{"compte": "6011", "debit": "600", "dim1": "COMP-B"}])
    assert _soldes(projet)[L2][2] == D(600)
    inverse = contre_passer(posee, utilisateur=profils["amina"])
    assert _soldes(projet)[L2][2] == D(600)  # un brouillon de contre-passation ne bouge rien
    valider_ecriture(inverse, utilisateur=profils["bruno"])
    comptabiliser_ecriture(inverse, utilisateur=profils["claire"])
    assert _soldes(projet)[L2][2] == D(0)
    assert comparer_soldes(projet.id) == []


def test_une_periode_precise_ne_couvre_que_sa_periode(decor):  # noqa: F811
    organisation, projet, profils = decor
    version = creer_version(utilisateur=profils["amina"], project_id=projet.id, type="initial")
    ajouter_ligne(
        version,
        utilisateur=profils["amina"],
        annee=2026,
        periode=2,
        montant="1000",
        devise="DJF",
        axes={"dim1": "COMP-A"},
    )
    _approuver(version, profils)
    for periode in (1, 2, 3):
        _piece(
            organisation, projet, periode, [{"compte": "6011", "debit": "100", "dim1": "COMP-A"}]
        )
    cle = ("COMP-A", 2, None, None)
    assert _soldes(projet)[cle][2] == D(100)  # seule la période 2


# --- engagements --------------------------------------------------------------------------


def test_un_engagement_reserve_le_budget_et_son_apurement_le_libere(cadre):
    organisation, projet, profils, version = cadre
    _approuver(version, profils)
    eng = creer_engagement(
        utilisateur=profils["amina"],
        project_id=projet.id,
        reference="ENG-1",
        annee=2026,
        montant="2000",
        axes={"dim1": "COMP-B"},
    )
    assert _soldes(projet)[L2][1] == D(2000)
    apurer_engagement(eng, utilisateur=profils["amina"], montant="500")
    assert _soldes(projet)[L2][1] == D(1500) and eng.status == "ouvert"
    apurer_engagement(eng, utilisateur=profils["amina"], montant="1500")
    assert _soldes(projet)[L2][1] == D(0) and eng.status == "solde"
    rangee = next(r for r in situation(projet.id) if r.budget == D(5000))
    assert rangee.disponible == D(5000)

    autre = creer_engagement(
        utilisateur=profils["amina"],
        project_id=projet.id,
        reference="ENG-2",
        annee=2026,
        montant="800",
        axes={"dim1": "COMP-B"},
    )
    annuler_engagement(autre, utilisateur=profils["amina"], motif="Marché abandonné")
    assert _soldes(projet)[L2][1] == D(0) and autre.status == "annule"
    assert comparer_soldes(projet.id) == []


def test_le_disponible_est_le_budget_moins_l_engage_moins_le_consomme(cadre):
    organisation, projet, profils, version = cadre
    _approuver(version, profils)
    _piece(organisation, projet, 1, [{"compte": "6011", "debit": "1000", "dim1": "COMP-B"}])
    creer_engagement(
        utilisateur=profils["amina"],
        project_id=projet.id,
        reference="ENG-1",
        annee=2026,
        montant="2500",
        axes={"dim1": "COMP-B"},
    )
    rangee = next(r for r in situation(projet.id) if r.budget == D(5000))
    assert (rangee.engage, rangee.consomme, rangee.disponible) == (D(2500), D(1000), D(1500))


@pytest.mark.parametrize(
    "champs, message",
    [
        ({"montant": "0"}, "strictement positif"),
        ({"montant": "5", "reference": " "}, "référence"),
        ({"montant": "5", "periode": 13}, "période"),
    ],
)
def test_un_engagement_invalide_est_refuse(cadre, champs, message):
    _, projet, profils, _ = cadre
    donnees = {"reference": "E", "annee": 2026} | champs
    with pytest.raises(BudgetInvalide, match=message):
        creer_engagement(utilisateur=profils["amina"], project_id=projet.id, **donnees)
    assert Engagement.objects.count() == 0


def test_on_n_apure_pas_plus_que_le_reste_ni_un_engagement_clos(cadre):
    _, projet, profils, _ = cadre
    eng = creer_engagement(
        utilisateur=profils["amina"],
        project_id=projet.id,
        reference="E1",
        annee=2026,
        montant="100",
    )
    with pytest.raises(BudgetInvalide, match="reste"):
        apurer_engagement(eng, utilisateur=profils["amina"], montant="101")
    with pytest.raises(BudgetInvalide, match="strictement positif"):
        apurer_engagement(eng, utilisateur=profils["amina"], montant="0")
    apurer_engagement(eng, utilisateur=profils["amina"], montant="100")
    with pytest.raises(TransitionInterdite):
        apurer_engagement(eng, utilisateur=profils["amina"], montant="1")
    with pytest.raises(TransitionInterdite):
        annuler_engagement(eng, utilisateur=profils["amina"], motif="x")
    with pytest.raises(PermissionDenied):
        creer_engagement(
            utilisateur=profils["claire"],
            project_id=projet.id,
            reference="E2",
            annee=2026,
            montant="1",
        )


def test_la_base_garde_les_engagements(cadre):
    organisation, projet, profils, _ = cadre
    eng = creer_engagement(
        utilisateur=profils["amina"],
        project_id=projet.id,
        reference="E1",
        annee=2026,
        montant="100",
    )
    with connexion_proprietaire() as admin:
        for requete, motif in [
            ("DELETE FROM budget_engagement WHERE id = %s", "ne se supprime pas"),
            ("UPDATE budget_engagement SET montant = 1 WHERE id = %s", "ne change que"),
            ("UPDATE budget_engagement SET annee = 2030 WHERE id = %s", "ne change que"),
        ]:
            with pytest.raises(Exception, match=motif):
                admin.execute(requete, [eng.pk])
        admin.execute("UPDATE budget_engagement SET apure = 40 WHERE id = %s", [eng.pk])
        with pytest.raises(Exception, match="ne change que"):  # l'apuré ne baisse jamais
            admin.execute("UPDATE budget_engagement SET apure = 10 WHERE id = %s", [eng.pk])
        with pytest.raises(Exception, match="naît ouvert"):
            admin.execute(
                """INSERT INTO budget_engagement (id, created_at, updated_at, org_id, project_id,
                       reference, libelle, annee, montant, apure, status)
                   VALUES (gen_random_uuid(), now(), now(), %s, %s, 'E9', '', 2026, 10, 0,
                           'solde')""",
                [organisation.id, projet.id],
            )


# --- vérification, alerte, reconstruction -------------------------------------------------


def test_une_derive_est_detectee_alertee_puis_corrigee_par_le_recalcul(cadre):
    organisation, projet, profils, version = cadre
    _approuver(version, profils)
    _piece(organisation, projet, 1, [{"compte": "6011", "debit": "1000", "dim1": "COMP-B"}])
    assert verifier_soldes(organisation.id, projet.id) == []

    with connexion_proprietaire() as admin:  # une dérive silencieuse, fabriquée hors déclencheur
        admin.execute(
            "UPDATE budget_soldebudgetaire SET consomme = consomme + 7 "
            "WHERE ligne_id = (SELECT id FROM budget_lignebudget WHERE montant = 5000)"
        )
    divergences = comparer_soldes(projet.id)
    assert len(divergences) == 1
    assert (divergences[0].consomme_incremental, divergences[0].consomme_calcule) == (
        D(1007),
        D(1000),
    )

    assert len(verifier_soldes(organisation.id, projet.id)) == 1
    with connection.cursor() as cur:
        cur.execute("SELECT action FROM core_auditlog WHERE action = 'budget_balance_divergence'")
        assert cur.fetchall() == [("budget_balance_divergence",)]

    corriges = recalculer_soldes(organisation.id, projet.id)
    assert len(corriges) == 1
    assert comparer_soldes(projet.id) == []
    assert _soldes(projet)[L2][2] == D(1000)
    assert verifier_chaine(organisation.id) is None


def test_une_ligne_de_solde_manquante_est_aussi_une_divergence(cadre):
    organisation, projet, profils, version = cadre
    _approuver(version, profils)
    with connexion_proprietaire() as admin:
        admin.execute(
            "DELETE FROM budget_soldebudgetaire WHERE ligne_id = "
            "(SELECT id FROM budget_lignebudget WHERE montant = 5000)"
        )
    assert len(comparer_soldes(projet.id)) == 1


def test_la_commande_nocturne_echoue_sur_une_divergence_et_reussit_sinon(cadre, capsys):
    organisation, projet, profils, version = cadre
    _approuver(version, profils)
    call_command("verifier_soldes", organisation=str(organisation.id))
    with connexion_proprietaire() as admin:
        admin.execute(
            "UPDATE budget_soldebudgetaire SET engage = engage + 1 "
            "WHERE ligne_id = (SELECT id FROM budget_lignebudget WHERE montant = 5000)"
        )
    with pytest.raises(CommandError, match="divergent"):
        call_command("verifier_soldes", organisation=str(organisation.id))
    call_command("recalculer_soldes", organisation=str(organisation.id))
    call_command("verifier_soldes", organisation=str(organisation.id))


# --- révision : les soldes suivent la nouvelle version --------------------------------------


def test_une_revision_reconstruit_les_soldes_de_la_nouvelle_version(cadre):
    organisation, projet, profils, version = cadre
    _approuver(version, profils)
    _piece(organisation, projet, 1, [{"compte": "6011", "debit": "400", "dim1": "COMP-B"}])
    revision = creer_version(
        utilisateur=profils["amina"], project_id=projet.id, type="revision", motif="Hausse"
    )
    ligne = revision.lignes.get(dim1__code="COMP-B")
    modifier_ligne(ligne, utilisateur=profils["amina"], montant="6000")
    approuver_version(revision, utilisateur=profils["bruno"])

    assert _soldes(projet)[L2] == (D(6000), D(0), D(400))  # le consommé suit, depuis le grand livre
    anciennes = SoldeBudgetaire.objects.filter(version=version)
    assert anciennes.count() == 3  # conservées, mais hors « courante »
    _piece(organisation, projet, 2, [{"compte": "6011", "debit": "100", "dim1": "COMP-B"}])
    assert _soldes(projet)[L2][2] == D(500)
    assert all(s.consomme == D(400) or s.consomme == 0 for s in anciennes.all()), "ancien touché"
    assert comparer_soldes(projet.id) == []


# --- le contrôle de la tâche : 10 000 opérations aléatoires ---------------------------------

DIM1 = ["COMP-A", "COMP-B", "COMP-C", None]
CATEGORIES = [id_objet("CAT-1"), id_objet("CAT-2"), None]
ACCORDS = [id_objet("IDA-1"), id_objet("IDA-2"), None]
COMPTES = ["6011", "6021", "2411", "2841", "7061", "5311"]


def _couvre(ligne, annee, periode, dim1, categorie, accord):
    return (
        ligne["annee"] == annee
        and ligne["periode"] in (None, periode)
        and ligne["dim1"] in (None, dim1)
        and ligne["categorie"] in (None, categorie)
        and ligne["accord"] in (None, accord)
    )


def test_apres_10000_operations_aleatoires_le_recalcul_egale_l_incremental(decor):  # noqa: F811
    organisation, projet, profils = decor
    for code in ("2411", "2841", "7061", "6021", "5311"):
        _compte(organisation.id, code)
    for code in ("COMP-B", "COMP-C"):
        _valeur_axe(organisation.id, code)
    hasard = random.Random(20260713)
    exercice = Exercice.objects.get(project_id=projet.id, annee=2026)
    periodes = {p.numero: p for p in exercice.periodes.all()}
    journal = Journal.objects.get(code="OD")
    valeurs = {c: _valeur_axe(organisation.id, c) for c in ("COMP-A", "COMP-B", "COMP-C")}
    comptes = {c: _compte(organisation.id, c) for c in COMPTES + ["5211"]}
    maintenant = timezone.now()

    # Budget initial : des lignes de granularités variées qui se recouvrent.
    amina, bruno = profils["amina"], profils["bruno"]
    modele = []

    def budget(revision=False):
        version = creer_version(
            utilisateur=amina,
            project_id=projet.id,
            type="revision" if revision else "initial",
            motif="Hausse" if revision else "",
        )
        if revision:
            for ligne in version.lignes.all()[:2]:
                modifier_ligne(ligne, utilisateur=amina, montant=ligne.montant + 1000)
        else:
            for dim1 in DIM1:
                for categorie in (CATEGORIES[0], None):
                    ajouter_ligne(
                        version,
                        utilisateur=amina,
                        annee=2026,
                        montant="500000",
                        devise="DJF",
                        axes={"dim1": dim1} if dim1 else None,
                        category_id=categorie,
                    )
            ajouter_ligne(
                version,
                utilisateur=amina,
                annee=2026,
                periode=6,
                montant="90000",
                devise="DJF",
                agreement_id=ACCORDS[0],
            )
            ajouter_ligne(
                version,
                utilisateur=amina,
                annee=2026,
                montant="70000",
                devise="DJF",
                agreement_id=ACCORDS[1],
                axes={"dim1": "COMP-C"},
            )
        approuver_version(version, utilisateur=bruno)
        modele[:] = [
            {
                "id": ligne.id,
                "annee": ligne.annee,
                "periode": ligne.periode,
                "dim1": ligne.dim1.code if ligne.dim1 else None,
                "categorie": ligne.category_id,
                "accord": ligne.agreement_id,
                "budget": ligne.montant_base,
            }
            for ligne in LigneBudget.objects.filter(version=version).select_related("dim1")
        ]

    budget()
    lignes_posees = []  # (periode, dim1, categorie, accord, net) des charges budgétées
    engagements = []  # dicts mutables : engagements ouverts
    nb_operations = 10_000

    def poster():
        compte = hasard.choice(COMPTES)
        periode = hasard.randint(1, 12)
        dim1 = hasard.choice(DIM1)
        categorie = hasard.choice(CATEGORIES)
        accord = hasard.choice(ACCORDS)
        montant = D(hasard.randint(1, 90_000))
        sens = hasard.random() < 0.85  # 15 % de crédits : contre-passations, remboursements
        debit, credit = (montant, D(0)) if sens else (D(0), montant)
        ecriture = Ecriture.objects.create(
            org_id=organisation.id,
            project_id=projet.id,
            exercice=exercice,
            periode=periodes[periode],
            journal=journal,
            accounting_date=periodes[periode].date_debut,
            label="aléatoire",
            status="draft",
            currency_id="DJF",
            fx_rate=D(1),
            origin="saisie",
        )
        commun = {
            "org_id": organisation.id,
            "project_id": projet.id,
            "entry": ecriture,
            "currency_id": "DJF",
            "fx_rate": D(1),
        }
        LigneEcriture.objects.bulk_create(
            [
                LigneEcriture(
                    line_no=1,
                    account=comptes[compte],
                    debit=debit,
                    credit=credit,
                    dim1=valeurs.get(dim1),
                    category_id=categorie,
                    agreement_id=accord,
                    **commun,
                ),
                LigneEcriture(
                    line_no=2, account=comptes["5211"], debit=credit, credit=debit, **commun
                ),
            ]
        )
        Ecriture.objects.filter(pk=ecriture.pk).update(
            status="posted", posted_at=maintenant, posted_by=uuid.uuid4()
        )
        if hasard.random() < 0.3:  # le verrouillage ne change rien au consommé
            Ecriture.objects.filter(pk=ecriture.pk).update(status="locked")
        if compte[0] == "6" or (compte[0] == "2" and not compte.startswith(("28", "29"))):
            lignes_posees.append((periode, dim1, categorie, accord, debit - credit))

    def engager(numero):
        montant = D(hasard.randint(1, 60_000))
        eng = creer_engagement(
            utilisateur=amina,
            project_id=projet.id,
            reference=f"E{numero}",
            annee=2026,
            montant=montant,
            periode=hasard.choice([None, None, hasard.randint(1, 12)]),
            axes={"dim1": hasard.choice(DIM1)} if hasard.random() < 0.8 else None,
            category_id=hasard.choice(CATEGORIES),
            agreement_id=hasard.choice(ACCORDS),
        )
        engagements.append(eng)

    def manipuler_engagement():
        if not engagements:
            return
        eng = hasard.choice(engagements)
        eng.refresh_from_db()
        if eng.status != "ouvert":
            engagements.remove(eng)
            return
        if hasard.random() < 0.2:
            annuler_engagement(eng, utilisateur=amina, motif="aléatoire")
        else:
            apurer_engagement(
                eng, utilisateur=amina, montant=D(hasard.randint(1, int(eng.montant - eng.apure)))
            )

    for numero in range(nb_operations):
        if numero == nb_operations // 2:
            budget(revision=True)  # une révision en plein vol : les soldes sont reconstruits
        tirage = hasard.random()
        with transaction.atomic():
            if tirage < 0.65:
                poster()
            elif tirage < 0.80:
                engager(numero)
            else:
                manipuler_engagement()

    # 1. le calcul complet de la base et l'incrémental concordent ;
    assert comparer_soldes(projet.id) == []
    avant = {
        s.ligne_id: (s.consomme, s.engage)
        for s in SoldeBudgetaire.objects.filter(version__status="approuve")
    }
    assert recalculer_soldes(organisation.id, projet.id) == []
    apres = {
        s.ligne_id: (s.consomme, s.engage)
        for s in SoldeBudgetaire.objects.filter(version__status="approuve")
    }
    assert apres == avant, "le recalcul n'a rien à corriger"

    # 2. un calcul INDÉPENDANT, en Python, donne les mêmes valeurs.
    engagements_ouverts = list(Engagement.objects.filter(status="ouvert").select_related("dim1"))
    attendu = {}
    for ligne in modele:
        consomme = sum(
            (
                net
                for periode, dim1, categorie, accord, net in lignes_posees
                if _couvre(ligne, 2026, periode, dim1, categorie, accord)
            ),
            D(0),
        )
        engage = sum(
            (
                e.montant - e.apure
                for e in engagements_ouverts
                if _couvre(
                    ligne,
                    e.annee,
                    e.periode,
                    e.dim1.code if e.dim1 else None,
                    e.category_id,
                    e.agreement_id,
                )
            ),
            D(0),
        )
        attendu[ligne["id"]] = (consomme, engage)
    assert apres == attendu
    assert any(c != 0 for c, _ in attendu.values()) and any(e != 0 for _, e in attendu.values())
    assert Engagement.objects.count() > 1000 and LigneEcriture.objects.count() > 10_000
