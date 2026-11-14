# ruff: noqa: F811
"""Le profil Banque mondiale, livré comme donnée. Voir L5-T06.

« Lorsque requis » : aucun élément n'est présenté comme universel ; le DFIL du projet décide.
Ajouter un profil est un fichier de catalogue, jamais du développement.
"""

import io
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.exceptions import PermissionDenied

from niveau2_profils.models import MENTION_LORSQUE_REQUIS, ElementProfil, TypeElement
from niveau2_profils.services.catalogue import (
    DOSSIER,
    charger_profil,
    lire_profil_livre,
    profils_livres,
)
from niveau2_profils.services.presentation import AVERTISSEMENT, presenter_profil
from niveau2_profils.services.profils import _valider_exigence_type, importer_profil
from niveau3_config.models import Exigence
from tests.outils_documents import fabriquer_pdf
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_registre_exigences_bd import PAGES, _document, base  # noqa: F401

FAMILLES = {
    "RFI",
    "RESSOURCES-EMPLOIS",
    "DEPENSES-AXES",
    "COMPTE-DESIGNE",
    "TRESORERIE-AVANCES",
    "DEMANDES-RETRAIT",
    "ETATS-AUDIT",
}


# --- le fichier de catalogue (logique pure) ------------------------------------------------


def test_le_catalogue_livre_le_profil_banque_mondiale():
    assert "banque_mondiale" in profils_livres()
    donnees = lire_profil_livre("banque_mondiale")
    assert donnees["code"] == "BANQUE_MONDIALE"
    familles = {e["code"] for e in donnees["elements"] if e["kind"] == "report_family"}
    assert familles == FAMILLES  # les sept familles d'états du plan


def test_le_profil_ne_se_presente_pas_comme_universel():
    donnees = lire_profil_livre("banque_mondiale")
    assert "n'est pas un modèle universel" in donnees["description"]
    assert "lorsque requis" in donnees["description"]
    assert "n'est pas un modèle universel" in AVERTISSEMENT


def test_chaque_element_du_catalogue_est_valide_et_rien_nest_impose():
    donnees = lire_profil_livre("banque_mondiale")
    for element in donnees["elements"]:
        assert element["kind"] in TypeElement.values, element["code"]
        assert isinstance(element["label"], dict) and element["label"]
        if element.get("exigence") is not None:
            _valider_exigence_type(element["exigence"])
            # Le profil met à disposition : aucune exigence livrée n'est obligatoire d'office.
            assert element["exigence"]["obligation"] == "optional", element["code"]


def test_le_seul_delai_livre_est_celui_de_lida_pour_le_rfi():
    donnees = lire_profil_livre("banque_mondiale")
    avec_delai = {
        e["code"]: (e["exigence"].get("periodicity"), e["exigence"].get("due_offset_days"))
        for e in donnees["elements"]
        if e.get("exigence")
        and (e["exigence"].get("periodicity") or e["exigence"].get("due_offset_days"))
    }
    # 45 jours après la fin de chaque trimestre civil ; aucun autre délai n'est inventé.
    assert avec_delai == {"RFI": ("quarterly", 45)}


def test_chaque_fichier_du_catalogue_est_un_json_lisible():
    for chemin in DOSSIER.glob("*.json"):
        assert json.loads(chemin.read_text(encoding="utf-8"))["elements"], chemin.name


def test_lire_un_profil_inconnu_est_refuse_en_listant_les_disponibles():
    with pytest.raises(FileNotFoundError, match="banque_mondiale"):
        lire_profil_livre("inexistant")


# --- le chargement -------------------------------------------------------------------------

pytestmark_bd = pytest.mark.django_db(transaction=True)


@pytestmark_bd
def test_charger_le_profil_cree_un_brouillon_complet_et_ne_le_recree_pas(base):
    _, _, profils = base
    profil = charger_profil(utilisateur=profils["dora"], nom="banque_mondiale")
    assert (profil.status, profil.code, profil.version) == ("draft", "BANQUE_MONDIALE", 1)
    assert profil.elements.count() == len(lire_profil_livre("banque_mondiale")["elements"])
    assert charger_profil(utilisateur=profils["dora"], nom="banque_mondiale").pk == profil.pk
    assert ElementProfil.objects.count() == profil.elements.count()


@pytestmark_bd
def test_charger_exige_lhabilitation_parametrer(base):
    _, _, profils = base
    with pytest.raises(PermissionDenied):
        charger_profil(utilisateur=profils["bruno"], nom="banque_mondiale")


@pytestmark_bd
def test_chaque_element_presente_porte_la_mention_lorsque_requis(base):
    _, _, profils = base
    profil = charger_profil(utilisateur=profils["dora"], nom="banque_mondiale", publier=True)
    vue = presenter_profil(profil)
    assert vue["avertissement"] == AVERTISSEMENT
    assert len(vue["elements"]) == profil.elements.count() > 0
    assert {e["mention"] for e in vue["elements"]} == {MENTION_LORSQUE_REQUIS}
    assert {e["code"] for e in vue["elements"] if e["type"] == "report_family"} == FAMILLES
    assert all(element.mention == "lorsque requis" for element in profil.elements.all())
    assert presenter_profil(profil, langue="en")["libelle"] == "World Bank (IDA)"


@pytestmark_bd
def test_importer_le_profil_banque_mondiale_ne_produit_que_des_propositions(base):
    organisation, projet, profils = base
    profil = charger_profil(utilisateur=profils["dora"], nom="banque_mondiale", publier=True)
    resultat = importer_profil(
        utilisateur=profils["dora"],
        profil=profil,
        project_id=projet.id,
        document=_document(profils, projet, fabriquer_pdf(PAGES)),
    )
    assert sorted(e.code for e in resultat.creees) == sorted(FAMILLES)
    assert set(Exigence.objects.values_list("status", flat=True)) == {"proposed"}
    rfi = Exigence.objects.get(code="RFI")
    assert (rfi.periodicity, rfi.due_offset_days, rfi.obligation) == ("quarterly", 45, "optional")


# --- la commande ---------------------------------------------------------------------------


@pytestmark_bd
def test_la_commande_charge_le_profil_et_refuse_un_utilisateur_inconnu(base):
    organisation, _, profils = base
    sortie = io.StringIO()
    call_command(
        "charger_profil_bailleur",
        "banque_mondiale",
        organisation=str(organisation.id),
        utilisateur="dora",
        stdout=sortie,
    )
    assert "BANQUE_MONDIALE v1 (draft)" in sortie.getvalue()
    with pytest.raises(CommandError, match="Utilisateur introuvable"):
        call_command(
            "charger_profil_bailleur",
            "banque_mondiale",
            organisation=str(organisation.id),
            utilisateur="fantome",
        )
