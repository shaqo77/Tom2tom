# ruff: noqa: F811, E501
"""Contrôle de sortie du lot L8 : une base migrée à écart nul, intégralement ré-exportable.

Correspondance entre le contrôle de chaque tâche du plan et le test qui le démontre (le premier
test vérifie que chaque test cité existe). Puis le scénario de bout en bout : reprise signée à
écart nul, rapport publié sur les données reprises, export, suppression de l'organisation,
restauration, rapport régénéré à l'identique.
"""

import datetime
import re
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from niveau1_socle.habilitations.models import Habilitation, Role
from niveau1_socle.reprise.models import RapportReprise, Reprise
from niveau1_socle.reprise.services import (
    controler_reprise,
    reprise_acceptee,
    signer_rapport,
)
from niveau1_socle.reversibilite.restauration import restaurer_archive
from niveau4_reporting.publication.rapports import publier_rapport, regenerer
from tests.outils import connexion_proprietaire
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_export_complet_bd import _archive, _poser, _produire, _supprimer_l_organisation
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_regeneration_bd import MODELE, _mapping
from tests.test_reprise_bd import BALANCE, HISTORIQUE, _balance, _historique, rep  # noqa: F401

DOSSIER = Path(__file__).parent
CORRESPONDANCE = {
    "L8-T01 écart nul sur la balance et le cumul par accord, rapport signé": [
        ("test_reprise_bd", "test_une_reprise_a_ecart_nul_est_controlee_puis_signee"),
        ("test_reprise_bd", "test_une_reprise_de_cinq_cents_ecritures_est_a_ecart_nul"),
        (
            "test_reprise_bd",
            "test_une_reprise_de_cinquante_mille_ecritures_est_a_ecart_nul_et_signee",
        ),
    ],
    "L8-T01 un écart non nul bloque et se liste ligne à ligne": [
        (
            "test_reprise_bd",
            "test_un_ecart_sur_un_compte_refuse_la_reprise_et_se_liste_ligne_a_ligne",
        ),
        (
            "test_reprise_bd",
            "test_un_ecart_sur_le_cumul_par_accord_refuse_meme_si_les_comptes_sont_justes",
        ),
        ("test_reprise_bd", "test_la_base_refuse_de_signer_un_rapport_a_ecart_non_nul"),
    ],
    "L8-T02 trois imports du même fichier : même nombre d'écritures": [
        (
            "test_reprise_bd",
            "test_trois_imports_du_meme_fichier_donnent_le_meme_nombre_d_ecritures",
        ),
        (
            "test_reprise_bd",
            "test_une_piece_modifiee_dans_la_source_est_un_conflit_pas_un_ecrasement_ni_un_doublon",
        ),
    ],
    "L8-T03 exporter, restaurer dans une instance vierge, régénérer à l'identique": [
        (
            "test_export_complet_bd",
            "test_exporter_supprimer_restaurer_puis_regenerer_un_rapport_scelle_donne_le_meme_resultat",
        ),
        ("test_export_complet_bd", "test_une_archive_alteree_est_refusee_avant_toute_ecriture"),
        (
            "test_export_complet_bd",
            "test_le_lien_signe_donne_l_archive_tant_qu_il_est_valable_puis_403",
        ),
    ],
    "L8-T04 le dictionnaire publié est celui des modèles": [
        ("test_dictionnaire", "test_le_dictionnaire_publie_est_celui_que_les_modeles_produisent"),
    ],
}


def test_chaque_controle_du_plan_renvoie_a_un_test_qui_existe():
    manquants = []
    for controle, tests in CORRESPONDANCE.items():
        for fichier, nom in tests:
            source = (DOSSIER / f"{fichier}.py").read_text(encoding="utf-8")
            if not re.search(rf"^def {re.escape(nom)}\(", source, flags=re.MULTILINE):
                manquants.append(f"{controle} -> {fichier}::{nom}")
    assert not manquants, manquants


# --- le scénario de bout en bout ---------------------------------------------------------------

Utilisateur = get_user_model()
D = datetime.date


@pytest.mark.django_db(transaction=True)
def test_une_base_migree_a_ecart_nul_se_reexporte_et_se_restaure_a_l_identique(
    rep, settings, tmp_path
):
    organisation, projet, profils, reprise = rep
    settings.STOCKAGE_DOCUMENTS_ROOT = tmp_path

    # 1. La reprise : balance d'origine, historique rejoué trois fois, écart nul, signature par
    #    une AUTRE personne que celle qui l'a ouverte.
    _balance(rep)
    for _ in range(3):
        _historique(rep)
    rapport_reprise = controler_reprise(utilisateur=profils["dora"], reprise=reprise)
    assert rapport_reprise.accepte and rapport_reprise.nombre_ecritures == 3
    signer_rapport(utilisateur=profils["sonia"], rapport=rapport_reprise)
    assert reprise_acceptee(projet.id)

    # 2. Un rapport publié et scellé SUR LES DONNÉES REPRISES.
    pia = Utilisateur.objects.create_user("pia", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id, code="PIA", label={"fr": "pia"},
        operations=["consulter", "publier", "exporter"],
    )  # fmt: skip
    Habilitation.objects.create(
        org_id=organisation.id, user_id=pia.id, project_id=projet.id, role=role
    )
    profils["pia"] = pia
    table = _mapping(organisation, projet, version=1)
    publie = publier_rapport(
        utilisateur=pia, project_id=projet.id, modele=MODELE,
        params={"fiscal_year": 2026, "current_period": 3}, tables={"WB": table},
        period_from=D(2026, 1, 1), period_to=D(2026, 3, 31),
    )  # fmt: skip
    assert publie.values["R110/QTR"] == "1325.75"  # 1000,50 + 250 + 75,25 : la balance d'origine
    assert regenerer(publie).identique

    # 3. Export complet, suppression de l'organisation, restauration.
    export = _produire(publie, profils)
    archive = _archive(export)
    _supprimer_l_organisation(organisation.id, tmp_path)
    with connexion_proprietaire() as proprietaire:
        restaurer_archive(archive, proprietaire)

    # 4. L'organisation restaurée : la reprise reste acceptée et signée, le rapport se régénère
    #    à l'identique.
    _poser(organisation.id)
    assert reprise_acceptee(projet.id) and Reprise.objects.get().statut == "acceptee"
    signe = RapportReprise.objects.get(pk=rapport_reprise.pk)
    assert signe.signe_nom == "sonia" and signe.accepte
    restaure = type(publie).objects.get(pk=publie.pk)
    assert bytes(restaure.seal) == bytes(publie.seal)
    resultat = regenerer(restaure)
    assert resultat.identique, (resultat.ecarts, resultat.inexpliquee)
