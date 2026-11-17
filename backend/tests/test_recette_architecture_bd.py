# ruff: noqa: F811, E501
"""Recette d'architecture (L10-T03) : les dix-sept tests de réception de la spécification §17.

Chaque scénario renvoie au test qui le démontre (le premier test vérifie que chaque test cité
existe). T14 (connectivité dégradée) relève de la VERSION 2 du plan : il est déclaré non livré, pas
contourné. T17, le scénario de référence, est joué ici de bout en bout.
"""

import datetime
import re
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings

from niveau1_socle.comptabilite.models import Ecriture, LigneEcriture
from niveau1_socle.decaissements.services import DemandeInvalide
from niveau1_socle.financements.models import Accord
from niveau1_socle.financements.services import creer_bailleur, creer_categorie
from niveau3_config.models import ProfilDecaissement
from niveau3_config.services.decaissement import profil_en_vigueur
from tests.outils_profil import creer_profil
from tests.test_activation_bd import cfg  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import _depense, _preparer, drf  # noqa: F401
from tests.test_financements_bd import _accord, _activer, cadre  # noqa: F401
from tests.test_organisations_bd import _creer_organisation, _poser
from tests.test_reallocation_bd import _avenant, realloc  # noqa: F401

DOSSIER = Path(__file__).parent
D = Decimal
J = datetime.date

# Les tests de réception, avec le(s) test(s) qui les démontrent.
CORRESPONDANCE = {
    "T1 création d'un projet sans développement": [
        (
            "test_organisations_bd",
            "test_deux_organisations_et_deux_projets_chacune_se_creent_sans_erreur",
        ),
        (
            "test_profils_bailleurs_livres_bd",
            "test_ajouter_un_profil_et_un_modele_ne_demande_aucun_code",
        ),
    ],
    "T2 deux projets d'un même bailleur, configurations différentes": [
        (
            "test_profil_decaissement_bd",
            "test_trois_projets_du_meme_bailleur_coexistent_avec_des_minimums_differents",
        ),
    ],
    "T3 un autre bailleur : un profil et un modèle, sans nouvelle application": [
        (
            "test_profils_bailleurs_livres_bd",
            "test_ajouter_un_profil_et_un_modele_ne_demande_aucun_code",
        ),
        (
            "test_profils_bailleurs_livres_bd",
            "test_chaque_profil_se_charge_par_le_meme_mecanisme_que_la_banque_mondiale",
        ),
    ],
    "T4 rapports distincts à partir des mêmes données": [
        (
            "test_profils_bailleurs_livres_bd",
            "test_deux_bailleurs_differents_lisent_les_memes_donnees_dans_leur_propre_nomenclature",
        ),
    ],
    "T5 évolution d'une exigence sans altérer l'historique": [
        (
            "test_activation_bd",
            "test_une_exigence_modifiee_avec_effet_2028_laisse_inchange_le_troisieme_trimestre_2027",
        ),
        (
            "test_dossier_conformite_bd",
            "test_le_dossier_d_un_rapport_ne_change_pas_quand_l_exigence_est_revisee_apres",
        ),
    ],
    "T6 traçabilité d'un montant publié aux écritures et justificatifs": [
        ("test_descente_complete_bd", "test_descente_de_bout_en_bout_en_acces_auditeur"),
    ],
    "T7 contrôles : manquants, incohérences, dépassements": [
        ("test_compilateur_bd", "test_un_compte_non_mappe_bloque_apres_la_meme_requete_unique"),
        ("test_controle_budgetaire_bd", "test_les_trois_modes_sur_un_meme_depassement"),
        (
            "test_revue_bailleur_bd",
            "test_une_avance_non_justifiee_au_dela_du_delai_donne_no_go_et_nomme_l_avance_et_le_retard",
        ),
    ],
    "T8 dossier de conformité au paragraphe": [
        (
            "test_dossier_conformite_bd",
            "test_le_dossier_couvre_toutes_les_rubriques_avec_la_citation_exacte",
        ),
    ],
    "T9 reproductibilité : identique ou écart expliqué": [
        ("test_regeneration_bd", "test_un_rapport_publie_se_rejoue_a_l_identique"),
        (
            "test_regeneration_bd",
            "test_une_ecriture_ajoutee_apres_la_publication_est_nommee_avec_son_montant",
        ),
    ],
    "T10 accès auditeur de la cellule à la pièce": [
        ("test_descente_complete_bd", "test_descente_de_bout_en_bout_en_acces_auditeur"),
    ],
    "T11 exhaustivité du mapping": [
        ("test_mapping_bd", "test_un_compte_mouvemente_non_couvert_est_nomme"),
        ("test_compilateur_bd", "test_un_compte_non_mappe_bloque_apres_la_meme_requete_unique"),
    ],
    "T12 réversibilité : exporter et réimporter": [
        (
            "test_export_complet_bd",
            "test_exporter_supprimer_restaurer_puis_regenerer_un_rapport_scelle_donne_le_meme_resultat",
        ),
    ],
    "T13 reprise à écart nul": [
        (
            "test_sortie_l8_bd",
            "test_une_base_migree_a_ecart_nul_se_reexporte_et_se_restaure_a_l_identique",
        ),
    ],
    "T15 méthodes de décaissement variables, même bailleur": [
        (
            "test_profil_decaissement_bd",
            "test_trois_projets_du_meme_bailleur_coexistent_avec_des_minimums_differents",
        ),
        ("test_profil_decaissement_bd", "test_une_methode_non_autorisee_par_le_profil_est_refusee"),
    ],
    "T16 changement de régime en cours de projet": [
        (
            "test_profil_decaissement_bd",
            "test_changer_de_regime_au_premier_juillet_laisse_inchangees_les_demandes_du_semestre",
        ),
        (
            "test_profil_decaissement_bd",
            "test_une_reallocation_qui_change_un_taux_ne_recalcule_aucune_demande_anterieure",
        ),
    ],
    "T17 deux accords, un projet": [
        ("test_recette_architecture_bd", "test_t17_deux_accords_un_projet"),
    ],
}

# Déclaré, pas contourné : la capture hors ligne est la version 2 (plan, « APRÈS : VERSION 2 »).
NON_LIVRES = {"T14": "connectivité dégradée : capture hors ligne, version 2 du plan"}


def test_chaque_scenario_de_reception_renvoie_a_un_test_qui_existe():
    manquants = []
    for scenario, tests in CORRESPONDANCE.items():
        for fichier, nom in tests:
            source = (DOSSIER / f"{fichier}.py").read_text(encoding="utf-8")
            if not re.search(rf"^def {re.escape(nom)}\(", source, flags=re.MULTILINE):
                manquants.append(f"{scenario} -> {fichier}::{nom}")
    assert not manquants, manquants


def test_les_dix_sept_scenarios_sont_tous_traites_ou_declares_non_livres():
    traites = {re.match(r"T\d+", s).group() for s in CORRESPONDANCE} | set(NON_LIVRES)
    assert traites == {f"T{n}" for n in range(1, 18)}
    plan = (DOSSIER.parents[1] / "05_PLAN_LOTS_L5_A_L10.md").read_text(encoding="utf-8")
    assert "Capture hors ligne" in plan.split("APRÈS : VERSION 2")[1]  # T14 est bien reporté


def test_aucune_application_n_est_propre_a_un_bailleur():
    """Le critère qui prime : un bailleur s'ajoute par paramétrage, pas par une application."""
    bailleurs = {
        "banque_mondiale",
        "bad",
        "union_europeenne",
        "fida",
        "fonds_mondial",
        "bid",
        "nations_unies",
        "ida",
    }
    applications = {nom.split(".")[-1] for nom in settings.INSTALLED_APPS}
    assert not applications & bailleurs, applications & bailleurs


# --- T17 : deux accords, un projet ---------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_t17_deux_accords_un_projet(realloc):
    organisation, projet, profils, a1, cat, v1 = realloc
    dora = profils["dora"]
    avant = (Ecriture.objects.count(), LigneEcriture.objects.count())

    # Un second bailleur, un second accord INDÉPENDANT du même projet, sa configuration propre.
    bailleur2 = creer_bailleur(
        utilisateur=dora, code="BAD", nom="Banque africaine de développement"
    )
    a2 = _activer(
        _accord(projet, profils, bailleur2, "BAD-1", devise="DJF", montant_initial="500"), profils
    )
    serv2 = creer_categorie(
        utilisateur=dora, accord=a2, code="SERV", label={"fr": "Services"}, plafond="200"
    )  # même code que l'accord 1 : l'identité d'une catégorie est (accord, code)
    p2 = creer_profil(
        organisation, projet, a2, version=1, valid_from=J(2026, 1, 1), regles=[(serv2, "0.5")]
    )
    # Ajouter un accord et sa configuration n'a créé aucune donnée comptable : pas de duplication.
    assert (Ecriture.objects.count(), LigneEcriture.objects.count()) == avant

    # Une dépense sur chaque accord, contrôlée par SES règles : 80 % d'un côté, 50 % de l'autre.
    d1 = _depense(organisation, projet, a1, cat["serv"], 100, jour=5)
    d2 = _depense(organisation, projet, a2, serv2, 100, jour=6)
    dem1 = _preparer(profils, a1, [d1], date_demande=J(2026, 6, 15))
    dem2 = _preparer(profils, a2, [d2], date_demande=J(2026, 6, 15))
    ligne1, ligne2 = dem1.lignes.get(), dem2.lignes.get()
    assert (ligne1.taux_applique, ligne1.montant_a_retirer, ligne1.profil_version_id) == (
        D("0.8"),
        D(80),
        v1.pk,
    )
    assert (ligne2.taux_applique, ligne2.montant_a_retirer, ligne2.profil_version_id) == (
        D("0.5"),
        D(50),
        p2.pk,
    )
    with pytest.raises(
        DemandeInvalide
    ):  # la dépense de l'accord 1 ne se présente pas sous l'accord 2
        _preparer(
            profils,
            a2,
            [_depense(organisation, projet, a1, cat["serv"], 10, jour=7)],
            date_demande=J(2026, 6, 16),
        )

    # Un avenant sur l'accord 1 crée une version du profil 1 — et ne touche en rien l'accord 2.
    avenant = _avenant(realloc)
    v2 = ProfilDecaissement.objects.get(pk=avenant.profile_version_id)
    assert (v2.accord_id, v2.version) == (a1.pk, 2)
    assert list(ProfilDecaissement.objects.filter(accord=a2).values_list("version", flat=True)) == [
        1
    ]
    p2.refresh_from_db()
    assert (p2.status, p2.valid_to) == ("active", None)
    assert profil_en_vigueur(a2, J(2026, 8, 1)) == p2
    assert Accord.objects.get(pk=a2.pk).montant_initial == D(500)  # montant de l'accord 2 inchangé

    # Une dépense antérieure à l'avenant garde la version qui s'appliquait à sa date.
    assert (
        profil_en_vigueur(a1, J(2026, 6, 15)).pk == v1.pk
        and profil_en_vigueur(a1, J(2026, 8, 1)).pk == v2.pk
    )
    ligne1.refresh_from_db()
    assert (ligne1.profil_version_id, ligne1.montant_a_retirer) == (v1.pk, D(80))

    # Un accès croisé d'une autre organisation est refusé.
    autre = _creer_organisation("AUTRE")
    _poser(autre.id)
    assert Accord.objects.count() == 0
    assert ProfilDecaissement.objects.count() == 0
    assert not Accord.objects.filter(pk=a1.pk).exists()
