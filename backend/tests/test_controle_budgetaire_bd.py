"""Le contrôle budgétaire. Voir L4-T03.

Contrôle : les trois modes se comportent correctement sur un même dépassement.
"""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework.exceptions import PermissionDenied

from niveau1_socle.budget.controle import (
    DepassementBudgetaire,
    mode_effectif,
    parametrer_controle,
)
from niveau1_socle.budget.engagements import creer_engagement
from niveau1_socle.budget.models import ControleBudgetaire, Engagement
from niveau1_socle.budget.services import (
    BudgetInvalide,
    ajouter_ligne,
    approuver_version,
    creer_version,
)
from niveau1_socle.comptabilite.models import Ecriture
from niveau1_socle.comptabilite.services import (
    comptabiliser_ecriture,
    contre_passer,
    valider_ecriture,
)
from niveau1_socle.habilitations.models import Habilitation, Role
from tests.outils import _compte, _valeur_axe, connexion_proprietaire, creer_piece, id_objet
from tests.test_cycle_ecriture_bd import decor  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = Decimal
DEBUT = datetime.date(2020, 1, 1)


@pytest.fixture
def cadre(decor):  # noqa: F811
    """Budget approuvé : composante B 5 000 ; composante A + catégorie 1 : 10 000 ; accord : 20 000.

    Retourne aussi `dora`, habilitée à paramétrer.
    """
    organisation, projet, profils = decor
    _valeur_axe(organisation.id, "COMP-B")
    _compte(organisation.id, "7061")
    amina = profils["amina"]
    version = creer_version(utilisateur=amina, project_id=projet.id, type="initial")
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
        montant="10000",
        devise="DJF",
        axes={"dim1": "COMP-A"},
        category_id=id_objet("CAT-1"),
    )
    ajouter_ligne(
        version,
        utilisateur=amina,
        annee=2026,
        montant="20000",
        devise="DJF",
        agreement_id=id_objet("IDA-1"),
    )
    approuver_version(version, utilisateur=profils["bruno"])
    role = Role.objects.create(
        org_id=organisation.id,
        code="PARAM",
        label={"fr": "P"},
        operations=["consulter", "parametrer"],
    )
    dora = Utilisateur.objects.create_user("dora", password="x", org_id=organisation.id)
    Habilitation.objects.create(
        org_id=organisation.id, user_id=dora.id, project_id=projet.id, role=role
    )
    profils["dora"] = dora
    return organisation, projet, profils


def _brouillon(organisation, projet, profils, montant, *, dim1="COMP-B", periode=3, **axes):
    """Une charge en brouillon, écrite par amina, prête à être validée par bruno."""
    return creer_piece(
        organisation.id,
        2026,
        periode,
        [
            {"compte": "6011", "debit": str(montant), "dim1": dim1, **axes},
            {"compte": "5211", "credit": str(montant)},
        ],
        project_id=projet.id,
        statut="draft",
        utilisateur_id=profils["amina"].id,
    )


def _mode(profils, projet, mode, axe="dim1", date_effet=DEBUT):
    return parametrer_controle(
        utilisateur=profils["dora"], project_id=projet.id, axe=axe, mode=mode, date_effet=date_effet
    )


def _actions():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT action FROM core_auditlog WHERE action LIKE 'budget_overrun%' ORDER BY id"
        )
        return [ligne[0] for ligne in cur.fetchall()]


# --- le contrôle de la tâche : un même dépassement, trois modes -----------------------------


def test_les_trois_modes_sur_un_meme_depassement(cadre):
    organisation, projet, profils = cadre
    # 6 000 sur la composante B dont le budget est de 5 000 : dépassement de 1 000.

    _mode(profils, projet, "bloquant")
    piece = _brouillon(organisation, projet, profils, 6000)
    with pytest.raises(DepassementBudgetaire, match="dépassement 1000") as erreur:
        valider_ecriture(piece, utilisateur=profils["bruno"])
    assert erreur.value.depassements[0].mode == "bloquant"
    assert Ecriture.objects.get(pk=piece.pk).status == "draft"

    _mode(profils, projet, "avertissement", date_effet=datetime.date(2021, 1, 1))
    valide = valider_ecriture(piece, utilisateur=profils["bruno"])
    assert valide.status == "validated"
    assert len(valide.avertissements_budgetaires) == 1
    assert "dépassement 1000" in valide.avertissements_budgetaires[0]
    assert _actions() == ["budget_overrun_warning"]

    _mode(profils, projet, "inactif", date_effet=datetime.date(2022, 1, 1))
    autre = _brouillon(organisation, projet, profils, 6000)
    valide = valider_ecriture(autre, utilisateur=profils["bruno"])
    assert valide.status == "validated" and valide.avertissements_budgetaires == []
    assert _actions() == ["budget_overrun_warning"]  # inactif : aucune trace de plus


def test_sans_parametrage_un_depassement_avertit_sans_bloquer(cadre):
    organisation, projet, profils = cadre
    assert mode_effectif(projet.id, "dim1", datetime.date(2026, 3, 1)) == "avertissement"
    valide = valider_ecriture(
        _brouillon(organisation, projet, profils, 6000), utilisateur=profils["bruno"]
    )
    assert valide.status == "validated" and len(valide.avertissements_budgetaires) == 1


def test_une_ecriture_dans_le_budget_passe_sans_avertissement_meme_en_mode_bloquant(cadre):
    organisation, projet, profils = cadre
    _mode(profils, projet, "bloquant")
    valide = valider_ecriture(
        _brouillon(organisation, projet, profils, 4000), utilisateur=profils["bruno"]
    )
    assert valide.status == "validated" and valide.avertissements_budgetaires == []


def test_atteindre_exactement_le_disponible_n_est_pas_un_depassement(cadre):
    organisation, projet, profils = cadre
    _mode(profils, projet, "bloquant")
    valide = valider_ecriture(
        _brouillon(organisation, projet, profils, 5000), utilisateur=profils["bruno"]
    )
    assert valide.status == "validated"
    centime = _brouillon(organisation, projet, profils, "0.01", periode=4)
    comptabiliser_ecriture(valide, utilisateur=profils["claire"])  # 5 000 consommés
    with pytest.raises(DepassementBudgetaire):
        valider_ecriture(centime, utilisateur=profils["bruno"])  # un centime de trop


def test_le_consomme_et_l_engage_reduisent_le_disponible_controle(cadre):
    organisation, projet, profils = cadre
    creer_engagement(
        utilisateur=profils["amina"],
        project_id=projet.id,
        reference="E1",
        annee=2026,
        montant="3000",
        axes={"dim1": "COMP-B"},
    )
    _mode(profils, projet, "bloquant")
    with pytest.raises(DepassementBudgetaire, match="disponible 2000"):
        valider_ecriture(
            _brouillon(organisation, projet, profils, 2500), utilisateur=profils["bruno"]
        )


def test_une_operation_qui_restitue_du_budget_ne_depasse_jamais(cadre):
    organisation, projet, profils = cadre
    posee = creer_piece(
        organisation.id,
        2026,
        1,
        [
            {"compte": "6011", "debit": "7000", "dim1": "COMP-B"},
            {"compte": "5211", "credit": "7000"},
        ],
        project_id=projet.id,
    )  # déjà dépassée : 7 000 sur 5 000
    _mode(profils, projet, "bloquant")
    inverse = contre_passer(posee, utilisateur=profils["amina"])
    valide = valider_ecriture(inverse, utilisateur=profils["bruno"])
    assert valide.status == "validated" and valide.avertissements_budgetaires == []


def test_un_remboursement_partiel_sur_une_ligne_encore_depassee_n_est_pas_bloque(cadre):
    organisation, projet, profils = cadre
    creer_piece(
        organisation.id,
        2026,
        1,
        [
            {"compte": "6011", "debit": "7000", "dim1": "COMP-B"},
            {"compte": "5211", "credit": "7000"},
        ],
        project_id=projet.id,
    )  # 7 000 consommés sur 5 000 : la ligne reste dépassée de 1 000 après le remboursement
    _mode(profils, projet, "bloquant")
    remboursement = creer_piece(
        organisation.id,
        2026,
        2,
        [
            {"compte": "6011", "credit": "1000", "dim1": "COMP-B"},
            {"compte": "5211", "debit": "1000"},
        ],
        project_id=projet.id,
        statut="draft",
        utilisateur_id=profils["amina"].id,
    )
    valide = valider_ecriture(remboursement, utilisateur=profils["bruno"])
    assert valide.status == "validated" and valide.avertissements_budgetaires == []


# --- engagements : bloqué, puis débloqué par l'option paramétrée -----------------------------


def test_un_engagement_bloque_sur_depassement_puis_debloque_par_l_option(cadre):
    organisation, projet, profils = cadre
    _mode(profils, projet, "bloquant")
    with pytest.raises(DepassementBudgetaire):
        creer_engagement(
            utilisateur=profils["amina"],
            project_id=projet.id,
            reference="E1",
            annee=2026,
            montant="5001",
            axes={"dim1": "COMP-B"},
        )
    assert Engagement.objects.count() == 0

    _mode(profils, projet, "avertissement", date_effet=datetime.date(2021, 1, 1))
    eng = creer_engagement(
        utilisateur=profils["amina"],
        project_id=projet.id,
        reference="E1",
        annee=2026,
        montant="5001",
        axes={"dim1": "COMP-B"},
    )
    assert eng.pk and len(eng.avertissements_budgetaires) == 1


# --- quel mode pour quelle ligne ? --------------------------------------------------------


def test_une_ligne_a_plusieurs_axes_suit_le_plus_strict_de_ses_modes(cadre):
    organisation, projet, profils = cadre
    # La ligne « composante A + catégorie 1 » : composante tolérante, catégorie bloquante.
    _mode(profils, projet, "avertissement", axe="dim1")
    _mode(profils, projet, "bloquant", axe="category")
    piece = _brouillon(organisation, projet, profils, 10001, dim1="COMP-A", categorie="CAT-1")
    with pytest.raises(DepassementBudgetaire, match="dim1\\+category"):
        valider_ecriture(piece, utilisateur=profils["bruno"])
    _mode(profils, projet, "avertissement", axe="category", date_effet=datetime.date(2021, 1, 1))
    assert valider_ecriture(piece, utilisateur=profils["bruno"]).status == "validated"


def test_une_ligne_sans_axe_suit_l_axe_projet_et_chaque_ligne_a_son_mode(cadre):
    organisation, projet, profils = cadre
    # La charge est couverte par la ligne de composante B (5 000) ET par celle de l'accord (20 000).
    # Dépasser la composante en la tolérant n'est pas bloqué parce que l'accord, lui, est bloquant.
    _mode(profils, projet, "avertissement", axe="dim1")
    _mode(profils, projet, "bloquant", axe="agreement")
    piece = _brouillon(organisation, projet, profils, 6000, accord="IDA-1")
    valide = valider_ecriture(piece, utilisateur=profils["bruno"])  # 6 000 < 20 000 : accord ok
    assert valide.status == "validated" and len(valide.avertissements_budgetaires) == 1
    gros = _brouillon(organisation, projet, profils, 25000, accord="IDA-1", periode=4)
    with pytest.raises(DepassementBudgetaire, match="agreement"):
        valider_ecriture(gros, utilisateur=profils["bruno"])


def test_ce_qui_n_est_pas_budgete_ou_pas_couvert_n_est_pas_controle(cadre):
    organisation, projet, profils = cadre
    _mode(profils, projet, "bloquant")
    produit = creer_piece(
        organisation.id,
        2026,
        3,
        [
            {"compte": "7061", "credit": "90000", "dim1": "COMP-B"},
            {"compte": "5211", "debit": "90000"},
        ],
        project_id=projet.id,
        statut="draft",
        utilisateur_id=profils["amina"].id,
    )
    assert valider_ecriture(produit, utilisateur=profils["bruno"]).status == "validated"
    hors_budget = _brouillon(organisation, projet, profils, 90000, dim1=None)
    assert valider_ecriture(hors_budget, utilisateur=profils["bruno"]).status == "validated"


# --- le paramétrage est versionné ----------------------------------------------------------


def test_changer_de_mode_clot_la_version_en_cours_et_en_ouvre_une_autre(cadre):
    organisation, projet, profils = cadre
    v1 = _mode(profils, projet, "bloquant", date_effet=datetime.date(2026, 1, 1))
    v2 = _mode(profils, projet, "avertissement", date_effet=datetime.date(2026, 7, 1))
    v1.refresh_from_db()
    assert (v1.version, v2.version) == (1, 2)
    assert v1.valid_to == datetime.date(2026, 7, 1) and v2.valid_to is None
    assert mode_effectif(projet.id, "dim1", datetime.date(2026, 6, 30)) == "bloquant"
    assert mode_effectif(projet.id, "dim1", datetime.date(2026, 7, 1)) == "avertissement"
    assert (
        mode_effectif(projet.id, "dim1", datetime.date(2025, 12, 31)) == "avertissement"
    )  # défaut


def test_le_mode_applique_est_celui_de_la_date_comptable_de_l_ecriture(cadre):
    organisation, projet, profils = cadre
    _mode(profils, projet, "bloquant", date_effet=datetime.date(2026, 1, 1))
    _mode(profils, projet, "inactif", date_effet=datetime.date(2026, 7, 1))
    mars = _brouillon(organisation, projet, profils, 6000, periode=3)
    with pytest.raises(DepassementBudgetaire):
        valider_ecriture(mars, utilisateur=profils["bruno"])
    aout = _brouillon(organisation, projet, profils, 6000, periode=8)
    assert valider_ecriture(aout, utilisateur=profils["bruno"]).status == "validated"


def test_parametrer_exige_l_habilitation_une_date_posterieure_et_un_mode_connu(cadre):
    organisation, projet, profils = cadre
    with pytest.raises(PermissionDenied):
        parametrer_controle(
            utilisateur=profils["amina"],
            project_id=projet.id,
            axe="dim1",
            mode="bloquant",
            date_effet=DEBUT,
        )
    _mode(profils, projet, "bloquant", date_effet=datetime.date(2026, 5, 1))
    with pytest.raises(BudgetInvalide, match="après le 2026-05-01"):
        _mode(profils, projet, "inactif", date_effet=datetime.date(2026, 5, 1))
    with pytest.raises(BudgetInvalide, match="mode"):
        _mode(profils, projet, "strict", date_effet=datetime.date(2027, 1, 1))
    with pytest.raises(BudgetInvalide, match="axe"):
        _mode(profils, projet, "bloquant", axe="compte", date_effet=datetime.date(2027, 1, 1))


def test_la_base_garde_le_parametrage(cadre):
    organisation, projet, profils = cadre
    v1 = _mode(profils, projet, "bloquant", date_effet=datetime.date(2026, 1, 1))
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="ne se supprime pas"):
            admin.execute("DELETE FROM budget_controlebudgetaire WHERE id = %s", [v1.pk])
        with pytest.raises(Exception, match="clôture de sa validité"):
            admin.execute(
                "UPDATE budget_controlebudgetaire SET mode = 'inactif' WHERE id = %s", [v1.pk]
            )
        with pytest.raises(Exception, match="chevauchement"):
            admin.execute(
                """INSERT INTO budget_controlebudgetaire (id, created_at, updated_at, org_id,
                       project_id, axe, mode, version, valid_from, motif)
                   VALUES (gen_random_uuid(), now(), now(), %s, %s, 'dim1', 'inactif', 9,
                           '2026-03-01', '')""",
                [organisation.id, projet.id],
            )
    assert ControleBudgetaire.objects.count() == 1
