"""Budgets et versions. Voir L4-T01.

Contrôle : une version approuvée est immuable ; une révision crée une nouvelle version et conserve
l'ancienne.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from niveau1_socle.budget.models import LigneBudget, VersionBudget
from niveau1_socle.budget.services import (
    BudgetInvalide,
    ajouter_ligne,
    approuver_version,
    creer_version,
    ecarts,
    modifier_ligne,
    supprimer_ligne,
    supprimer_version,
    total_base,
    version_courante,
)
from niveau1_socle.exercices.services import TransitionInterdite
from niveau1_socle.habilitations.models import Habilitation, Role
from tests.outils import _valeur_axe, connexion_proprietaire, id_objet
from tests.test_cycle_ecriture_bd import (
    _poser,
    decor,  # noqa: F401
)
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = Decimal


@pytest.fixture
def cadre(decor):  # noqa: F401, F811
    """amina saisit, bruno valide (approuve), claire comptabilise : le projet P1 de `decor`."""
    organisation, projet, profils = decor
    _valeur_axe(organisation.id, "COMP-B")
    return organisation, projet, profils


def _initial(projet, profils, *, approuve=True):
    version = creer_version(utilisateur=profils["amina"], project_id=projet.id, type="initial")
    ajouter_ligne(
        version,
        utilisateur=profils["amina"],
        annee=2026,
        montant="10000",
        devise="DJF",
        axes={"dim1": "COMP-A"},
        category_id=id_objet("CAT-1"),
    )
    ajouter_ligne(
        version,
        utilisateur=profils["amina"],
        annee=2026,
        montant="5000",
        devise="DJF",
        axes={"dim1": "COMP-B"},
        category_id=id_objet("CAT-2"),
    )
    if approuve:
        approuver_version(version, utilisateur=profils["bruno"])
    version.refresh_from_db()
    return version


# --- création, lignes, approbation --------------------------------------------------------


def test_un_budget_initial_se_prepare_puis_s_approuve_par_une_autre_personne(cadre):
    _, projet, profils = cadre
    version = _initial(projet, profils, approuve=False)
    assert (version.numero, version.type, version.status) == (1, "initial", "brouillon")
    assert version_courante(projet.id) is None
    with pytest.raises(PermissionDenied):  # l'auteur n'approuve pas (et amina n'a pas « valider »)
        approuver_version(version, utilisateur=profils["amina"])
    approuver_version(version, utilisateur=profils["bruno"])
    version.refresh_from_db()
    assert version.status == "approuve" and version.approved_by == profils["bruno"].id
    assert version_courante(projet.id).pk == version.pk
    assert total_base(version) == D(15000)


def test_l_auteur_habilite_a_valider_n_approuve_pas_son_propre_budget(cadre):
    organisation, projet, profils = cadre
    role = Role.objects.create(
        org_id=organisation.id,
        code="DUO",
        label={"fr": "Duo"},
        operations=["consulter", "saisir", "valider"],
    )
    duo = Utilisateur.objects.create_user("duo", password="x", org_id=organisation.id)
    Habilitation.objects.create(
        org_id=organisation.id, user_id=duo.id, project_id=projet.id, role=role
    )
    version = creer_version(utilisateur=duo, project_id=projet.id, type="initial")
    ajouter_ligne(version, utilisateur=duo, annee=2026, montant="1", devise="DJF")
    with pytest.raises(PermissionDenied, match="même"):
        approuver_version(version, utilisateur=duo)


def test_le_montant_en_monnaie_de_tenue_applique_le_taux_de_budget_et_arrondit(cadre):
    _, projet, profils = cadre
    version = creer_version(utilisateur=profils["amina"], project_id=projet.id, type="initial")
    ligne = ajouter_ligne(
        version,
        utilisateur=profils["amina"],
        annee=2026,
        periode=3,
        montant="1000.50",
        devise="USD",
        taux="177.7210000000",
    )
    assert ligne.montant == D("1000.50")
    assert ligne.montant_base == D("177810")  # 1000,50 × 177,721 = 177 810,3 -> DJF sans décimale
    ligne = modifier_ligne(ligne, utilisateur=profils["amina"], montant="2000", taux="177.5")
    assert ligne.montant_base == D("355000")


@pytest.mark.parametrize(
    "champs, message",
    [
        ({"montant": "-1"}, "négatif"),
        ({"montant": "1", "taux": "0"}, "taux"),
        ({"montant": "1", "periode": 13}, "période"),
        ({"montant": "1", "devise": "ZZZ"}, "Devise"),
        ({"montant": "1", "axes": {"dim1": "INCONNU"}}, "INCONNU"),
        ({"montant": "1", "axes": {"dimX": "COMP-A"}}, "axe inconnu"),
    ],
)
def test_une_ligne_invalide_est_refusee_avec_un_message_precis(cadre, champs, message):
    _, projet, profils = cadre
    version = creer_version(utilisateur=profils["amina"], project_id=projet.id, type="initial")
    donnees = {"annee": 2026, "devise": "DJF"} | champs
    with pytest.raises(BudgetInvalide, match=message):
        ajouter_ligne(version, utilisateur=profils["amina"], **donnees)
    assert LigneBudget.objects.count() == 0


def test_une_combinaison_d_axes_n_apparait_qu_une_fois_par_version_null_compris(cadre):
    _, projet, profils = cadre
    version = creer_version(utilisateur=profils["amina"], project_id=projet.id, type="initial")
    ajouter_ligne(version, utilisateur=profils["amina"], annee=2026, montant="1", devise="DJF")
    with pytest.raises(IntegrityError, match="uq_lignebudget_combinaison"), transaction.atomic():
        ajouter_ligne(version, utilisateur=profils["amina"], annee=2026, montant="2", devise="DJF")


def test_on_n_approuve_pas_une_version_vide_ni_qui_melange_annee_et_periodes(cadre):
    _, projet, profils = cadre
    version = creer_version(utilisateur=profils["amina"], project_id=projet.id, type="initial")
    with pytest.raises(Exception, match="sans ligne"):
        approuver_version(version, utilisateur=profils["bruno"])
    ajouter_ligne(version, utilisateur=profils["amina"], annee=2026, montant="100", devise="DJF")
    ajouter_ligne(
        version, utilisateur=profils["amina"], annee=2026, periode=1, montant="10", devise="DJF"
    )
    with pytest.raises(BudgetInvalide, match="ligne annuelle ET"):
        approuver_version(version, utilisateur=profils["bruno"])


def test_il_n_y_a_qu_un_budget_initial_et_un_seul_brouillon_a_la_fois(cadre):
    _, projet, profils = cadre
    _initial(projet, profils)
    with pytest.raises(BudgetInvalide, match="déjà un budget initial"):
        creer_version(utilisateur=profils["amina"], project_id=projet.id, type="initial")
    creer_version(
        utilisateur=profils["amina"], project_id=projet.id, type="revision", motif="Hausse"
    )
    with pytest.raises(BudgetInvalide, match="déjà en préparation"):
        creer_version(
            utilisateur=profils["amina"], project_id=projet.id, type="reallocation", motif="Autre"
        )


def test_une_revision_exige_un_motif_et_une_version_approuvee(cadre):
    _, projet, profils = cadre
    with pytest.raises(BudgetInvalide, match="Aucune version approuvée"):
        creer_version(
            utilisateur=profils["amina"], project_id=projet.id, type="revision", motif="x"
        )
    _initial(projet, profils)
    with pytest.raises(BudgetInvalide, match="motif"):
        creer_version(
            utilisateur=profils["amina"], project_id=projet.id, type="revision", motif=" "
        )


def test_creer_une_version_exige_l_habilitation_saisir(cadre):
    _, projet, profils = cadre
    with pytest.raises(PermissionDenied):
        creer_version(utilisateur=profils["claire"], project_id=projet.id, type="initial")


# --- le contrôle de la tâche --------------------------------------------------------------


def test_une_version_approuvee_est_immuable_pour_les_services_comme_pour_la_base(cadre):
    organisation, projet, profils = cadre
    version = _initial(projet, profils)
    ligne = version.lignes.first()

    with pytest.raises(TransitionInterdite):
        ajouter_ligne(version, utilisateur=profils["amina"], annee=2027, montant="1", devise="DJF")
    with pytest.raises(TransitionInterdite):
        modifier_ligne(ligne, utilisateur=profils["amina"], montant="1")
    with pytest.raises(TransitionInterdite):
        supprimer_ligne(ligne, utilisateur=profils["amina"])
    with pytest.raises(TransitionInterdite):
        supprimer_version(version, utilisateur=profils["amina"])

    with connexion_proprietaire() as admin:  # même le propriétaire : c'est la base qui refuse
        for requete, motif in [
            ("UPDATE budget_lignebudget SET montant = 1 WHERE id = %s", "figées"),
            ("DELETE FROM budget_lignebudget WHERE id = %s", "figées"),
        ]:
            with pytest.raises(Exception, match=motif):
                admin.execute(requete, [ligne.pk])
        with pytest.raises(Exception, match="figées"):
            admin.execute(
                """INSERT INTO budget_lignebudget (id, created_at, updated_at, org_id, version_id,
                       annee, montant, devise_id, taux_budget, montant_base)
                   VALUES (gen_random_uuid(), now(), now(), %s, %s, 2030, 1, 'DJF', 1, 1)""",
                [organisation.id, version.pk],
            )
        for requete, motif in [
            ("UPDATE budget_versionbudget SET motif = 'x' WHERE id = %s", "immuable"),
            ("UPDATE budget_versionbudget SET status = 'brouillon' WHERE id = %s", "immuable"),
            ("DELETE FROM budget_versionbudget WHERE id = %s", "ne se supprime pas"),
        ]:
            with pytest.raises(Exception, match=motif):
                admin.execute(requete, [version.pk])
    assert LigneBudget.objects.filter(version=version).count() == 2


def test_une_revision_cree_une_nouvelle_version_et_conserve_l_ancienne(cadre):
    _, projet, profils = cadre
    v1 = _initial(projet, profils)
    avant = list(v1.lignes.order_by("id").values())

    v2 = creer_version(
        utilisateur=profils["amina"], project_id=projet.id, type="revision", motif="Hausse du lot 1"
    )
    assert (v2.numero, v2.parent_id, v2.status) == (2, v1.pk, "brouillon")
    assert v2.lignes.count() == 2  # elle reprend les lignes de la courante
    ligne = v2.lignes.get(dim1__code="COMP-A")
    modifier_ligne(ligne, utilisateur=profils["amina"], montant="12000")
    ajouter_ligne(
        v2,
        utilisateur=profils["amina"],
        annee=2026,
        montant="700",
        devise="DJF",
        axes={"dim1": "COMP-A"},
        category_id=id_objet("CAT-3"),
    )
    approuver_version(v2, utilisateur=profils["bruno"])

    v1.refresh_from_db()
    v2.refresh_from_db()
    assert (v1.status, v2.status) == ("clos", "approuve")
    assert version_courante(projet.id).pk == v2.pk
    assert v1.closed_at is not None
    assert list(v1.lignes.order_by("id").values()) == avant, "L'ANCIENNE VERSION A ÉTÉ TOUCHÉE"
    assert total_base(v1) == D(15000) and total_base(v2) == D(17700)
    e = ecarts(v1, v2)
    assert (e["total_avant"], e["total_apres"]) == (D(15000), D(17700))
    assert len(e["ajoutees"]) == 1 and len(e["modifiees"]) == 1 and e["supprimees"] == []


def test_une_seule_version_est_courante_et_une_version_close_est_figee(cadre):
    organisation, projet, profils = cadre
    v1 = _initial(projet, profils)
    creer_version(
        utilisateur=profils["amina"], project_id=projet.id, type="reallocation", motif="Transfert"
    )
    v2 = VersionBudget.objects.get(numero=2)
    approuver_version(v2, utilisateur=profils["bruno"])
    v3 = creer_version(
        utilisateur=profils["amina"], project_id=projet.id, type="revision", motif="Encore"
    )
    with pytest.raises(IntegrityError, match="uq_versionbudget_une_courante"), transaction.atomic():
        VersionBudget.objects.filter(pk=v3.pk).update(
            status="approuve", approved_at=timezone.now(), approved_by=profils["bruno"].id
        )
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="close est figée"):
            admin.execute(
                "UPDATE budget_versionbudget SET status = 'approuve' WHERE id = %s", [v1.pk]
            )


def test_un_brouillon_perime_ne_s_approuve_pas(cadre):
    """Un brouillon parti d'une version qui n'est plus la courante écraserait une approbation."""
    organisation, projet, profils = cadre
    v1 = _initial(projet, profils)
    brouillon = creer_version(
        utilisateur=profils["amina"], project_id=projet.id, type="revision", motif="Premier"
    )
    # La version dont il part n'est plus la courante (changement fabriqué hors service).
    with connexion_proprietaire() as admin:
        admin.execute(
            "UPDATE budget_versionbudget SET closed_at = now(), status = 'clos' WHERE id = %s",
            [v1.pk],
        )
    with pytest.raises(BudgetInvalide, match="n'est plus la courante"):
        approuver_version(brouillon, utilisateur=profils["bruno"])


def test_la_base_refuse_un_parent_d_un_autre_projet_et_une_version_qui_ne_nait_pas_en_brouillon(
    cadre,
):
    organisation, projet, profils = cadre
    v1 = _initial(projet, profils)
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="même projet"):
            admin.execute(
                """INSERT INTO budget_versionbudget (id, created_at, updated_at, org_id, project_id,
                       numero, type, status, motif, parent_id)
                   VALUES (gen_random_uuid(), now(), now(), %s, gen_random_uuid(), 1, 'revision',
                           'brouillon', 'x', %s)""",
                [organisation.id, v1.pk],
            )
        with pytest.raises(Exception, match="naît en brouillon"):
            admin.execute(
                """INSERT INTO budget_versionbudget (id, created_at, updated_at, org_id, project_id,
                       numero, type, status, motif, approved_at, approved_by)
                   VALUES (gen_random_uuid(), now(), now(), %s, gen_random_uuid(), 1, 'initial',
                           'approuve', '', now(), gen_random_uuid())""",
                [organisation.id],
            )


def test_un_brouillon_se_supprime_et_libere_la_place(cadre):
    _, projet, profils = cadre
    version = _initial(projet, profils, approuve=False)
    supprimer_version(version, utilisateur=profils["amina"])
    assert VersionBudget.objects.count() == 0 and LigneBudget.objects.count() == 0
    assert (
        creer_version(utilisateur=profils["amina"], project_id=projet.id, type="initial").numero
        == 1
    )


def test_les_budgets_sont_isoles_par_organisation(cadre):
    _, projet, profils = cadre
    _initial(projet, profils)
    autre = _creer_organisation("ORG-B")
    _poser(autre)
    assert VersionBudget.objects.count() == 0 and LigneBudget.objects.count() == 0
