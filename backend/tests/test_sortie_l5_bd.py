# ruff: noqa: F811
"""Contrôle de sortie du lot L5 : un projet configuré à partir de son DFIL, avec traçabilité au
paragraphe.

Correspondance entre le contrôle de chaque tâche du plan et le test qui le démontre (le premier
test de ce fichier vérifie que chaque test cité existe : la table ne peut pas pourrir en silence) :

- L5-T01 deux fois le même fichier = même empreinte ; un octet modifié = signalé
- L5-T02 une citation absente du document est refusée avec le message exact
- L5-T03 aucun objet actif sans exigence source
- L5-T03bis trois projets d'un bailleur, régime au 01/07, réallocation sans recalcul, date
  d'éligibilité, minimum de demande, seuil de documentation
- L5-T04 version 2028 sans effet sur 2027 ; chevauchement refusé par la base ; méthode figée en SQL
  direct ; dépense du 15/06 sous V2 ; activation concurrente
- L5-T04bis réallocation, auto-approbation, concurrence, avenant, profil incomplet, comparaison
- L5-T05 importer un profil ne produit aucune exigence active
- L5-T06 « lorsque requis » sur chaque élément ; un seul délai livré
- L5-T07 le guide dit pourquoi chaque élément existe

Puis le scénario de bout en bout : du DFIL téléversé au guide, chaque étape par un humain habilité.
"""

import datetime
import re
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from niveau1_socle.habilitations.models import Habilitation, Role
from niveau2_profils.services.catalogue import charger_profil
from niveau2_profils.services.profils import importer_profil
from niveau3_config.models import Exigence
from niveau3_config.services.activation import (
    activer_exigence,
    resoudre_configuration,
    valider_exigence,
)
from niveau3_config.services.exigences import (
    CitationIntrouvable,
    etayer_exigence,
    proposer_exigence,
)
from niveau3_config.services.guide import generer_guide
from niveau3_config.services.rattachement import exiger_configuration_sans_orphelin, rattacher
from tests.outils_documents import fabriquer_pdf
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_rattachement_bd import _mapping
from tests.test_registre_exigences_bd import PAGES, _document, base  # noqa: F401

DOSSIER = Path(__file__).parent
CORRESPONDANCE = {
    "L5-T01 même empreinte": [
        (
            "test_documents_reference_bd",
            "test_le_meme_fichier_deux_fois_donne_la_meme_empreinte_et_un_seul_document",
        ),
        (
            "test_documents_reference_bd",
            "test_un_fichier_modifie_d_un_octet_a_une_autre_empreinte_et_le_systeme_le_signale",
        ),
    ],
    "L5-T02 citation absente refusée": [
        (
            "test_registre_exigences_bd",
            "test_une_citation_absente_du_document_est_refusee_avec_le_message_exact",
        ),
    ],
    "L5-T03 aucun objet actif sans source": [
        ("test_rattachement_bd", "test_aucun_objet_actif_sans_exigence_source"),
        (
            "test_rattachement_bd",
            "test_un_objet_actif_sans_rattachement_est_signale_par_le_systeme",
        ),
    ],
    "L5-T03bis profil de décaissement": [
        (
            "test_profil_decaissement_bd",
            "test_trois_projets_du_meme_bailleur_coexistent_avec_des_minimums_differents",
        ),
        (
            "test_profil_decaissement_bd",
            "test_changer_de_regime_au_premier_juillet_laisse_inchangees_les_demandes_du_semestre",
        ),
        (
            "test_profil_decaissement_bd",
            "test_une_reallocation_qui_change_un_taux_ne_recalcule_aucune_demande_anterieure",
        ),
        (
            "test_profil_decaissement_bd",
            "test_une_depense_anterieure_a_la_date_d_eligibilite_est_refusee_en_nommant_la_date",
        ),
        (
            "test_profil_decaissement_bd",
            "test_une_demande_inferieure_au_minimum_est_bloquee_en_nommant_le_seuil",
        ),
        (
            "test_profil_decaissement_bd",
            "test_une_depense_au_dela_du_seuil_exige_les_copies_de_pieces_et_non_l_etat_certifie",
        ),
    ],
    "L5-T04 activation et versionnement": [
        (
            "test_activation_bd",
            "test_une_exigence_modifiee_avec_effet_2028_laisse_inchange_le_troisieme_trimestre_2027",
        ),
        ("test_activation_bd", "test_la_base_refuse_deux_profils_actifs_qui_se_chevauchent"),
        (
            "test_activation_bd",
            "test_une_methode_dun_profil_approuve_ne_se_modifie_ni_ne_se_supprime",
        ),
        (
            "test_activation_bd",
            "test_une_depense_du_15_juin_garde_v2_quand_laccord_passe_en_v3_en_decembre",
        ),
        (
            "test_activation_bd",
            "test_lactivation_concurrente_de_deux_versions_incompatibles_nen_laisse_aboutir_quune",
        ),
    ],
    "L5-T04bis réallocations, avenants, complétude": [
        (
            "test_reallocation_bd",
            "test_une_reallocation_approuvee_cree_une_version_et_conserve_lancienne",
        ),
        ("test_reallocation_bd", "test_le_demandeur_ne_peut_pas_approuver_sa_propre_reallocation"),
        (
            "test_reallocation_bd",
            "test_deux_reallocations_simultanees_sur_une_meme_source_nen_laissent_aboutir_quune",
        ),
        (
            "test_reallocation_bd",
            "test_deux_approbations_simultanees_de_la_meme_reallocation_ne_creent_quune_version",
        ),
        (
            "test_reallocation_bd",
            "test_un_avenant_cree_la_nouvelle_version_du_profil_et_laisse_lancienne_intacte",
        ),
        ("test_completude_comparaison_bd", "test_chaque_manque_bloquant_est_nomme"),
        (
            "test_completude_comparaison_bd",
            "test_la_comparaison_detecte_identiques_modifies_ajoutes_et_supprimes",
        ),
    ],
    "L5-T05 un profil n'impose rien": [
        ("test_profils_bailleurs_bd", "test_importer_un_profil_ne_produit_aucune_exigence_active"),
    ],
    "L5-T06 profil Banque mondiale": [
        (
            "test_profil_banque_mondiale_bd",
            "test_chaque_element_presente_porte_la_mention_lorsque_requis",
        ),
        (
            "test_profil_banque_mondiale_bd",
            "test_le_seul_delai_livre_est_celui_de_lida_pour_le_rfi",
        ),
    ],
    "L5-T07 le guide dit pourquoi": [
        ("test_guide_configuration_bd", "test_le_guide_dit_pourquoi_chaque_element_existe"),
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
CITATION_JUSTE = {"annex": "2", "page": 2, "paragraph": "4.2", "quote": "remis dans les 45 jours"}


@pytest.mark.django_db(transaction=True)
def test_un_projet_est_configure_a_partir_de_son_dfil_avec_tracabilite_au_paragraphe(base):
    organisation, projet, profils = base
    dora = profils["dora"]
    vera = Utilisateur.objects.create_user("vera", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id,
        code="VERA",
        label={"fr": "vera"},
        operations=["consulter", "valider", "parametrer"],
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=vera.id, project_id=projet.id, role=role
    )

    # 1. Le DFIL entre dans le système, avec son empreinte.
    dfil = _document(profils, projet, fabriquer_pdf(PAGES))
    assert len(bytes(dfil.sha256)) == 32

    # 2. Le profil Banque mondiale se met à disposition : il ne produit que des PROPOSITIONS.
    profil = charger_profil(utilisateur=dora, nom="banque_mondiale", publier=True)
    importer_profil(utilisateur=dora, profil=profil, project_id=projet.id, document=dfil)
    assert Exigence.objects.filter(status="active").count() == 0
    assert Exigence.objects.filter(status="proposed").count() == 7

    # 3. Une citation inventée est refusée ; une citation juste étaye la proposition.
    rfi = Exigence.objects.get(code="RFI")
    with pytest.raises(CitationIntrouvable):
        etayer_exigence(
            utilisateur=vera,
            exigence=rfi,
            citation=CITATION_JUSTE | {"quote": "remis dans les 90 jours"},
        )
    etayer_exigence(utilisateur=vera, exigence=rfi, citation=CITATION_JUSTE)

    # 4. Un humain habilité la valide, puis l'active : rien n'est automatique.
    valider_exigence(utilisateur=vera, exigence=rfi)
    activer_exigence(utilisateur=vera, exigence=rfi)
    rfi.refresh_from_db()
    assert rfi.status == "active" and rfi.validated_by == vera.id

    # 5. Ce que l'exigence justifie : un mapping actif, rattaché ; plus aucun objet orphelin.
    contexte = (organisation, projet, profils, dfil)
    mapping = _mapping(contexte, "WB-RFI")
    with pytest.raises(Exception, match="WB-RFI"):
        exiger_configuration_sans_orphelin(projet.id, D.today())  # actif mais sans source
    rattacher(utilisateur=dora, exigence=rfi, target_type="mapping", target_id=mapping.pk)
    exiger_configuration_sans_orphelin(projet.id, D.today())

    # 6. Traçabilité : toute exigence active renvoie à un paragraphe d'un document daté, vérifié.
    for active in Exigence.objects.filter(status="active"):
        assert bytes(active.citation_verifiee_sha256) == bytes(active.document.sha256)
        assert active.citation.get("paragraph") and active.citation.get("quote")
        assert active.validated_by and active.validated_at

    # 7. Une version prenant effet en 2028 ne change pas la configuration de 2027.
    avant = resoudre_configuration(projet.id, D(2027, 9, 30))
    v2 = proposer_exigence(
        utilisateur=dora,
        project_id=projet.id,
        code="RFI",
        document=dfil,
        citation=CITATION_JUSTE,
        subject="Rapport financier intermédiaire (révisé)",
        rule={"kind": "report"},
        obligation="mandatory",
        valid_from=D(2028, 1, 1),
        periodicity="quarterly",
        due_offset_days=30,
    )
    valider_exigence(utilisateur=vera, exigence=v2)
    activer_exigence(utilisateur=vera, exigence=v2)
    assert resoudre_configuration(projet.id, D(2027, 9, 30)) == avant

    # 8. Le guide : un comptable y lit POURQUOI, sans connaître le logiciel.
    from tests.test_guide_configuration_bd import _texte

    texte = _texte(generer_guide(utilisateur=dora, project_id=projet.id, date=D(2027, 9, 30)))
    assert "RFI (version 1)" in texte and "§ 4.2" in texte
    assert "« remis dans les 45 jours »" in texte and "Validée par vera" in texte
    assert "Mapping : WB-RFI v1" in texte
    assert "RFI (version 2)" not in texte  # la version de 2028 ne s'applique pas encore
    assert "Ces exigences ne sont PAS appliquées" in texte  # les six autres propositions
