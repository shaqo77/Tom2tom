# ruff: noqa: F811, E501
"""Contrôle de sortie du lot L6 : un rapport produit, contrôlé, validé, scellé, exporté, remis, et
rejouable. Voir l'annexe D du plan.

Correspondance entre le contrôle de chaque tâche du plan et le test qui le démontre (le premier
test de ce fichier vérifie que chaque test cité existe : la table ne peut pas pourrir en silence).
Puis un scénario de bout en bout : chaque étape est faite par un humain habilité, aucune par
l'administrateur.
"""

import datetime
import re
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from niveau1_socle.avances.services import situation_avance
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau3_config.models import Exigence
from niveau3_config.services.calendrier import generer_calendrier, marquer_remise
from niveau4_reporting.controles.circuit import creer_circuit, decider_etape, ouvrir_demande
from niveau4_reporting.controles.services import (
    activer_controle,
    installer_bibliotheque,
    valider_controle,
)
from niveau4_reporting.publication.exports import exporter_rapport, lire_fichier
from niveau4_reporting.publication.rapports import publier_rapport, regenerer
from niveau4_reporting.publication.revue import (
    enregistrer_envoi,
    enregistrer_issue,
    enregistrer_motif,
    simuler_revue,
    taux_acceptation_premier_envoi,
)
from tests.test_avances_bd import _justifier, _verser
from tests.test_avances_bd import cadre as cadre_avances  # noqa: F401
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import _document
from tests.test_regeneration_bd import MODELE, _mapping, _piece

DOSSIER = Path(__file__).parent
CORRESPONDANCE = {
    "L6-T01 condition hors schéma ou opérateur inconnu refusés à l'enregistrement": [
        (
            "test_controles_bd",
            "test_une_condition_hors_schema_ou_un_operateur_inconnu_est_refuse_a_l_enregistrement",
        ),
        (
            "test_controles_conditions",
            "test_une_condition_hors_schema_ou_operateur_inconnu_est_refusee",
        ),
    ],
    "L6-T01 contrôle à vérifier non tranché : on n'avance pas": [
        (
            "test_controles_bd",
            "test_un_controle_a_verifier_non_tranche_interdit_d_avancer",
        ),
    ],
    "L6-T01 pièce du mauvais type ou non rattachée refusée comme absente": [
        (
            "test_bibliotheque_controles",
            "test_une_piece_du_mauvais_type_ou_non_rattachee_est_refusee_comme_absente",
        ),
    ],
    "L6-T01 chaque évaluation laisse une ligne de journal avec la version du profil": [
        (
            "test_controles_bd",
            "test_chaque_evaluation_laisse_une_ligne_de_journal_complete",
        ),
        (
            "test_controles_bd",
            "test_la_version_du_profil_de_decaissement_est_notee_dans_le_journal",
        ),
    ],
    "L6-T01 chaque contrôle livré se déclenche, et pas à tort": [
        (
            "test_bibliotheque_controles",
            "test_chaque_controle_livre_se_declenche_quand_il_le_doit",
        ),
        (
            "test_bibliotheque_controles",
            "test_chaque_controle_livre_ne_se_declenche_pas_a_tort",
        ),
    ],
    "L6-T02 dérogation par son propre demandeur refusée": [
        (
            "test_derogations_bd",
            "test_un_demandeur_ne_peut_pas_approuver_sa_propre_derogation",
        ),
    ],
    "L6-T02 dérogation expirée ou hors périmètre : le contrôle bloque de nouveau": [
        (
            "test_derogations_bd",
            "test_une_derogation_expiree_ou_pas_encore_valable_ne_couvre_pas",
        ),
        (
            "test_derogations_bd",
            "test_une_derogation_ne_couvre_ni_un_autre_objet_ni_un_autre_controle",
        ),
    ],
    "L6-T02 résultat initial bloquant toujours lisible après dérogation": [
        (
            "test_derogations_bd",
            "test_une_derogation_approuvee_leve_le_blocage_sans_effacer_le_resultat_initial",
        ),
    ],
    "L6-T02 deux approbations concurrentes : une seule prend effet": [
        (
            "test_derogations_bd",
            "test_deux_approbations_concurrentes_une_seule_prend_effet",
        ),
        (
            "test_circuit_validation_bd",
            "test_deux_signatures_concurrentes_de_la_meme_etape_une_seule_prend_effet",
        ),
    ],
    "L6-T02 contrôle bloquant non traité : étape de validation inaccessible au serveur": [
        (
            "test_circuit_validation_bd",
            "test_un_controle_bloquant_non_traite_rend_l_etape_de_validation_inaccessible",
        ),
    ],
    "L6-T03 sceller, modifier le périmètre, re-sceller : empreintes différentes": [
        (
            "test_scellement",
            "test_ajouter_une_ecriture_dans_le_perimetre_change_l_empreinte_du_jeu_et_le_scellement",
        ),
    ],
    "L6-T04 l'écriture ajoutée est nommée avec son montant": [
        (
            "test_regeneration_bd",
            "test_une_ecriture_ajoutee_apres_la_publication_est_nommee_avec_son_montant",
        ),
        (
            "test_regeneration_bd",
            "test_un_rapport_publie_se_rejoue_a_l_identique",
        ),
    ],
    "L6-T05 le fichier lu a exactement l'empreinte enregistrée": [
        (
            "test_exports_rapport_bd",
            "test_le_fichier_lu_a_exactement_l_empreinte_enregistree",
        ),
    ],
    "L6-T06 exigence trimestrielle à 45 jours : quatre échéances aux bonnes dates": [
        (
            "test_calendrier_bd",
            "test_une_exigence_trimestrielle_a_45_jours_genere_les_quatre_echeances_aux_bonnes_dates",
        ),
    ],
    "L6-T07 avance échue : no-go qui nomme l'avance et le retard": [
        (
            "test_revue_bailleur_bd",
            "test_une_avance_non_justifiee_au_dela_du_delai_donne_no_go_et_nomme_l_avance_et_le_retard",
        ),
    ],
    "Annexe D assertion fausse : publication bloquée": [
        (
            "test_regeneration_bd",
            "test_une_assertion_fausse_bloque_la_publication",
        ),
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


# --- le scénario de bout en bout -----------------------------------------------------------

Utilisateur = get_user_model()
D = datetime.date
ACTEURS = {
    "pia": ["consulter", "publier", "exporter"],  # responsable des rapports
    "lea": ["consulter", "valider"],  # responsable financier
    "coord": ["consulter", "publier"],  # coordonnateur
    "bruno_v": ["consulter", "valider"],  # valide les contrôles
}


@pytest.mark.django_db(transaction=True)
def test_un_rapport_est_produit_controle_valide_scelle_exporte_remis_puis_rejoue(cadre_avances):
    organisation, projet, profils, agents = cadre_avances
    for nom, operations in ACTEURS.items():
        u = Utilisateur.objects.create_user(nom, password="x", org_id=organisation.id)
        role = Role.objects.create(
            org_id=organisation.id, code=nom.upper(), label={"fr": nom}, operations=operations
        )
        Habilitation.objects.create(
            org_id=organisation.id, user_id=u.id, project_id=projet.id, role=role
        )
        profils[nom] = u
    dora, amina = profils["dora"], profils["amina"]

    # 1. Configuration : contrôles de la bibliothèque (jamais actifs d'office), exigence, circuit.
    installes = installer_bibliotheque(
        utilisateur=dora, project_id=projet.id, valid_from=D(2026, 1, 1),
        codes=["AVA-DELAI", "AVA-NON-JUSTIFIEE"],
    )  # fmt: skip
    assert all(c.status == "draft" for c in installes.crees)  # règle 9
    for controle in installes.crees:
        valider_controle(utilisateur=profils["bruno_v"], controle=controle)
        activer_controle(utilisateur=dora, controle=controle)
    enregistrer_motif(
        utilisateur=dora, project_id=projet.id, code="AVANCES-ANCIENNES",
        label={"fr": "Avances anciennes non apurées", "en": "Old unsettled advances"},
        controle_code="AVA-DELAI", source="Lettre de rejet de 2025",
    )  # fmt: skip
    document = _document(organisation, projet, "Accord de financement")
    exigence = Exigence.objects.create(
        org_id=organisation.id, project_id=projet.id, code="RFI",
        document=document, citation_verifiee_sha256=document.sha256,
        citation={"paragraph": "4.2", "quote": "remis dans les 45 jours"},
        subject="Rapport financier intermédiaire", rule={}, periodicity="quarterly",
        due_offset_days=45, obligation="mandatory", valid_from=D(2026, 1, 1), version=1,
        source="manual", status="active", validated_by=dora.id, validated_at=timezone.now(),
    )  # fmt: skip
    creer_circuit(
        utilisateur=dora, project_id=projet.id, objet_type="rapport", valid_from=D(2026, 1, 1),
        etapes=[
            {
                "nom": {"fr": "Validation du responsable financier", "en": "Finance validation"},
                "operation": "valider",
                "exige_controles_tranches": True,
            },
            {
                "nom": {"fr": "Approbation du coordonnateur", "en": "Coordinator approval"},
                "operation": "publier",
            },
        ],
    )  # fmt: skip

    # 2. Le calendrier : quatre échéances, la première le 15 mai.
    calendrier = generer_calendrier(utilisateur=dora, project_id=projet.id, annee=2026)
    premiere = min(calendrier.creees, key=lambda e: e.periode_fin)
    assert len(calendrier.creees) == 4 and premiere.date_echeance == D(2026, 5, 15)
    assert premiere.exigence_id == exigence.id

    # 3. Les données : une avance qui traîne, des écritures du trimestre, un mapping.
    avance = _verser(projet, profils, agents, reference="AV-1", montant="1000", date=D(2026, 2, 1))
    table = _mapping(organisation, projet, version=1)
    for montant in ("100", "50.10"):
        _piece(organisation, projet, "6011", "5211", montant)

    # 4. La revue simulée dit NO-GO, nomme l'avance et son retard, et connaît le motif de rejet.
    avant = simuler_revue(
        utilisateur=profils["pia"], project_id=projet.id, date_effet=D(2026, 5, 1)
    )
    assert avant.avis == "no_go"
    delai = next(c for c in avant.constats if c["controle"] == "AVA-DELAI")
    assert "AV-1" in delai["message"]["fr"] and "jour(s) de retard" in delai["message"]["fr"]
    assert delai["motif_connu"]["code"] == "AVANCES-ANCIENNES"

    # 5. On justifie l'avance : la revue passe.
    _justifier(avance, profils, "1000", D(2026, 4, 15))
    apres = simuler_revue(
        utilisateur=profils["pia"], project_id=projet.id, date_effet=D(2026, 5, 1)
    )
    assert (apres.avis, apres.constats) == ("go", [])
    assert situation_avance(amina, avance, D(2026, 5, 1)).reste == 0

    # 6. Publication : rapport scellé, rejouable à l'identique.
    rapport = publier_rapport(
        utilisateur=profils["pia"], project_id=projet.id, modele=MODELE,
        params={"fiscal_year": 2026, "current_period": 3, "devise": "USD"},
        tables={"WB": table}, period_from=D(2026, 1, 1), period_to=D(2026, 3, 31),
        config_version={"exigence_RFI": exigence.version},
    )  # fmt: skip
    assert rapport.values["R110/QTR"] == "150.1"
    assert regenerer(rapport).identique

    # 7. Validation : l'étape 1 par le responsable financier, l'étape 2 par le coordonnateur.
    demande = ouvrir_demande(
        utilisateur=amina, project_id=projet.id, objet_type="rapport", objet_id=rapport.id,
        date_effet=D(2026, 5, 2),
    )  # fmt: skip
    decider_etape(utilisateur=profils["lea"], demande=demande, rang=1, approuver=True)
    decider_etape(utilisateur=profils["coord"], demande=demande, rang=2, approuver=True)
    assert demande.statut == "approuvee"

    # 8. Export : l'empreinte du fichier lu est celle qui est enregistrée.
    for format in ("xlsx", "pdf"):
        fichier = exporter_rapport(utilisateur=profils["pia"], rapport=rapport, format=format)
        assert lire_fichier(utilisateur=profils["pia"], fichier=fichier)

    # 9. Remise au bailleur : l'échéance est remise, le premier envoi est accepté.
    marquer_remise(utilisateur=profils["pia"], echeance=premiere, rapport_id=rapport.id)
    envoi = enregistrer_envoi(
        utilisateur=profils["pia"], project_id=projet.id, template_code="TER",
        period_to=D(2026, 3, 31), envoyee_le=D(2026, 5, 10), rapport_id=rapport.id,
        simulation=apres,
    )  # fmt: skip
    enregistrer_issue(
        utilisateur=profils["pia"], soumission=envoi, accepte=True, decidee_le=D(2026, 5, 20)
    )
    indicateur = taux_acceptation_premier_envoi(
        utilisateur=profils["pia"], project_id=projet.id, du=D(2026, 5, 1), au=D(2026, 5, 31)
    )
    assert (indicateur.acceptes, indicateur.decides, indicateur.taux) == (1, 1, Decimal(1))

    # 10. Plus tard, une écriture arrive dans la période : le rejeu NOMME la pièce et le montant.
    tardive = _piece(organisation, projet, "6011", "5211", "75.25")
    rejeu = regenerer(rapport)
    assert not rejeu.identique
    cause = next(c for c in rejeu.causes if c.compte == "6011")
    assert (cause.ecriture, cause.montant) == (tardive.number, Decimal("75.25"))
    # Le rapport remis, lui, n'a pas bougé.
    rapport.refresh_from_db()
    assert rapport.values["R110/QTR"] == "150.1"
    assert uuid.UUID(str(rapport.id))
