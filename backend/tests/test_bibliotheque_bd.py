# ruff: noqa: F811, E501
"""La bibliothèque de contrôles sur une vraie base : installation, pièces, contextes. L6-T01c."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from rest_framework.exceptions import PermissionDenied

from core.erreurs import CodeErreur, ErreurMetier
from niveau1_socle.avances.services import situation_avance
from niveau1_socle.comptabilite.models import Ecriture, LigneEcriture
from niveau1_socle.referentiels.models import Tiers
from niveau4_reporting.controles import bibliotheque as lib
from niveau4_reporting.controles.contextes import (
    contexte_avance,
    contexte_depense,
    facture_en_double,
)
from niveau4_reporting.controles.models import Controle
from niveau4_reporting.controles.services import (
    activer_controle,
    creer_controle,
    evaluer_controle,
    installer_bibliotheque,
    valider_controle,
)
from tests.test_avances_bd import _justifier, _verser
from tests.test_avances_bd import cadre as cadre_avances  # noqa: F401
from tests.test_controles_bd import ctl  # noqa: F401
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_demandes_retrait_bd import _depense, drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_rattachement_bd import cadre_config  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = Decimal
DEBUT = datetime.date(2026, 1, 1)


# --- l'installation : en brouillon, jamais activée -----------------------------------------


def test_la_bibliotheque_s_installe_en_brouillon_et_rien_n_est_active(ctl):
    organisation, projet, profils, _ = ctl
    resultat = installer_bibliotheque(
        utilisateur=profils["dora"], project_id=projet.id, valid_from=DEBUT
    )
    attendus = {d.code for d in lib.livres_avec_risque()}
    assert {c.code for c in resultat.crees} == attendus and resultat.deja_presents == []
    assert set(Controle.objects.values_list("status", flat=True)) == {"draft"}  # règle 9
    assert Controle.objects.count() == len(attendus)
    comparaison = Controle.objects.get(code="COH-CUMUL")
    assert (comparaison.severity, comparaison.type_regle) == ("bloquant", "coherence")
    assert comparaison.expression == lib.PAR_CODE["COH-CUMUL"].expression
    # Tout ce qui est installé est ce qui est livré : expression, applicabilité, action, libellé.
    for d in lib.livres_avec_risque():
        installe = Controle.objects.get(code=d.code)
        assert (installe.expression, installe.applicable_si, installe.parametres) == (
            d.expression,
            d.applicable_si,
            d.parametres,
        ), d.code
        assert (installe.label, installe.action_corrective) == (d.label, d.action_corrective)
        assert (installe.severity, installe.type_regle) == (d.severity, d.type_regle)


def test_installer_deux_fois_ne_recree_rien_et_un_sous_ensemble_est_possible(ctl):
    _, projet, profils, _ = ctl
    premiere = installer_bibliotheque(
        utilisateur=profils["dora"], project_id=projet.id, valid_from=DEBUT,
        codes=["COD-CATEGORIE", "BUD-ACCORD"],
    )  # fmt: skip
    assert sorted(c.code for c in premiere.crees) == ["BUD-ACCORD", "COD-CATEGORIE"]
    seconde = installer_bibliotheque(
        utilisateur=profils["dora"], project_id=projet.id, valid_from=DEBUT,
        codes=["COD-CATEGORIE", "COD-SOURCE"],
    )  # fmt: skip
    assert [c.code for c in seconde.crees] == ["COD-SOURCE"]
    assert seconde.deja_presents == ["COD-CATEGORIE"]
    assert Controle.objects.count() == 3


def test_un_code_inconnu_de_la_bibliotheque_est_refuse_sans_rien_installer(ctl):
    _, projet, profils, _ = ctl
    with pytest.raises(ErreurMetier) as erreur:
        installer_bibliotheque(
            utilisateur=profils["dora"], project_id=projet.id, valid_from=DEBUT,
            codes=["COD-CATEGORIE", "N-EXISTE-PAS"],
        )  # fmt: skip
    assert erreur.value.code is CodeErreur.REGLE_INVALIDE and "N-EXISTE-PAS" in erreur.value.message
    assert Controle.objects.count() == 0


def test_installer_exige_parametrer(ctl):
    _, projet, profils, _ = ctl
    with pytest.raises(PermissionDenied):
        installer_bibliotheque(utilisateur=profils["bruno"], project_id=projet.id, valid_from=DEBUT)
    assert Controle.objects.count() == 0
    # Même quand tout est déjà installé (rien à créer), l'habilitation reste exigée.
    installer_bibliotheque(
        utilisateur=profils["dora"], project_id=projet.id, valid_from=DEBUT, codes=["COD-SOURCE"]
    )
    with pytest.raises(PermissionDenied):
        installer_bibliotheque(
            utilisateur=profils["bruno"],
            project_id=projet.id,
            valid_from=DEBUT,
            codes=["COD-SOURCE"],
        )


def test_un_controle_installe_s_active_puis_s_evalue_comme_n_importe_quel_autre(ctl):
    _, projet, profils, _ = ctl
    installer_bibliotheque(
        utilisateur=profils["dora"], project_id=projet.id, valid_from=DEBUT, codes=["COD-CATEGORIE"]
    )
    controle = Controle.objects.get(code="COD-CATEGORIE")
    valider_controle(utilisateur=profils["vera"], controle=controle)
    controle = activer_controle(utilisateur=profils["vera"], controle=controle)
    ko = evaluer_controle(
        controle, {}, date_operation=datetime.date(2026, 6, 1), objet_type="depense", service="x"
    )
    ok = evaluer_controle(
        controle,
        {"categorie": "BIENS"},
        date_operation=datetime.date(2026, 6, 1),
        objet_type="depense",
        service="x",
    )
    assert (ko.resultat, ok.resultat) == ("bloquant", "reussi")
    assert ko.action_corrective["fr"] == "Imputer la dépense à une catégorie de l'accord"
    assert ko.action_corrective["en"] == "Assign the expense to a category of the agreement"


# --- les règles de pièces, de bout en bout -------------------------------------------------


def _creer_depuis(ctl, definition, **champs):
    _, projet, profils, _ = ctl
    return creer_controle(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code=definition.code,
        label=definition.label,
        type_regle=definition.type_regle,
        severity=definition.severity,
        valid_from=DEBUT,
        expression=definition.expression,
        applicable_si=definition.applicable_si,
        action_corrective=definition.action_corrective,
        parametres=definition.parametres,
        **champs,
    )


def test_une_regle_de_piece_filtre_par_type_rattachement_et_validation_au_journal(ctl):
    _, _, profils, _ = ctl
    brouillon = _creer_depuis(
        ctl, lib.regle_de_piece("PIE-FACTURE", "facture", validee=True, categories=["BIENS"])
    )
    assert brouillon.parametres == {"type_piece": "facture", "validee": True}
    valider_controle(utilisateur=profils["vera"], controle=brouillon)
    controle = activer_controle(utilisateur=profils["vera"], controle=brouillon)

    def evaluer(contexte):
        return evaluer_controle(
            controle,
            contexte,
            date_operation=datetime.date(2026, 6, 1),
            objet_type="depense",
            service="x",
        ).resultat

    ok = {"type": "facture", "rattachee": True, "valide": True}
    assert evaluer({"categorie": "BIENS", "pieces": [ok]}) == "reussi"
    assert evaluer({"categorie": "BIENS", "pieces": [{**ok, "type": "devis"}]}) == "bloquant"
    assert evaluer({"categorie": "BIENS", "pieces": [{**ok, "rattachee": False}]}) == "bloquant"
    assert evaluer({"categorie": "BIENS", "pieces": [{**ok, "valide": False}]}) == "bloquant"
    assert evaluer({"categorie": "SERVICES", "pieces": []}) == "non_applicable"


def test_des_parametres_invalides_sont_refuses_a_l_enregistrement(ctl):
    _, projet, profils, _ = ctl
    with pytest.raises(ErreurMetier) as erreur:
        creer_controle(  # une règle de budget avec des paramètres de pièce
            utilisateur=profils["dora"], project_id=projet.id, code="Z", label={"fr": "z"},
            type_regle="budget", severity="bloquant", valid_from=DEBUT,
            expression={"type_regle": "budget", "conditions": [
                {"champ": "disponible_ligne", "op": "gte", "valeur": "0"}]},
            parametres={"type_piece": "facture"},
        )  # fmt: skip
    assert erreur.value.code is CodeErreur.REGLE_INVALIDE
    assert "seule une règle de pièces" in erreur.value.message
    assert Controle.objects.count() == 0  # rien n'est enregistré


def test_les_parametres_se_figent_a_la_validation(ctl):
    _, _, profils, _ = ctl
    controle = _creer_depuis(ctl, lib.regle_de_piece("PIE-F", "facture"))
    valider_controle(utilisateur=profils["vera"], controle=controle)
    with pytest.raises(IntegrityError, match="ne se modifie pas"):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(
                """UPDATE controles_controle SET parametres = '{"type_piece": "autre"}' WHERE id=%s""",
                [controle.id],
            )


def test_les_parametres_sont_un_objet_json(ctl):
    brouillon = _creer_depuis(ctl, lib.regle_de_piece("PIE-G", "facture"))
    with pytest.raises(IntegrityError, match="controle_parametres_objet"):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(
                "UPDATE controles_controle SET parametres = '[1]' WHERE id = %s", [brouillon.id]
            )


# --- les contextes lus sur les vraies données ----------------------------------------------


def test_le_contexte_d_une_depense_est_lu_sur_sa_ligne_comptable(drf):
    organisation, projet, profils, accord, cat = drf
    ligne_id = _depense(
        organisation, projet, accord, cat["serv"], 100, jour=14, mois=3, statut="draft"
    )
    ligne = LigneEcriture.objects.select_related("entry", "account").get(pk=ligne_id)
    Ecriture.objects.filter(pk=ligne.entry_id).update(document_ref="FAC-2026-14")
    ligne.refresh_from_db()

    ctx = contexte_depense(
        ligne, nature="services", zone="DJ", beneficiaire="SOC-A", methode="reimbursement",
        pieces=[{"type": "facture", "rattachee": True, "valide": True}], destinee_etat_certifie=True,
    )  # fmt: skip
    assert ctx["montant"] == D("100") and isinstance(ctx["montant"], Decimal)
    assert ctx["date"] == datetime.date(2026, 3, 14)
    assert ctx["categorie"] == "SERV" and ctx["source"] == accord.numero
    assert ctx["compte"] == "6011" and ctx["numero_facture"] == "FAC-2026-14"
    assert (ctx["nature"], ctx["zone"], ctx["beneficiaire"], ctx["methode"]) == (
        "services", "DJ", "SOC-A", "reimbursement",
    )  # fmt: skip
    assert ctx["destinee_etat_certifie"] is True and len(ctx["pieces"]) == 1
    assert ctx["facture_en_double"] is False
    assert ctx["axe_1"] is None  # aucun axe sur cette ligne
    assert contexte_depense(ligne, source="AUTRE")["source"] == "AUTRE"


def test_un_doublon_de_facture_est_une_meme_reference_pour_le_meme_tiers(drf):
    organisation, projet, profils, accord, cat = drf
    tiers_a = Tiers.objects.create(
        org_id=organisation.id, code="F-A", nature="fournisseur", nom="A"
    )
    tiers_b = Tiers.objects.create(
        org_id=organisation.id, code="F-B", nature="fournisseur", nom="B"
    )

    def ligne(jour, reference, tiers):
        lid = _depense(organisation, projet, accord, cat["serv"], 100, jour=jour, statut="draft")
        ligne = LigneEcriture.objects.select_related("entry").get(pk=lid)
        Ecriture.objects.filter(pk=ligne.entry_id).update(document_ref=reference)
        LigneEcriture.objects.filter(pk=lid).update(partner=tiers)
        return LigneEcriture.objects.select_related("entry").get(pk=lid)

    premiere = ligne(1, "FAC-1", tiers_a)
    assert facture_en_double(premiere) is False  # seule de sa référence
    seconde = ligne(2, "FAC-1", tiers_a)
    assert facture_en_double(premiere) and facture_en_double(seconde)  # doublon, vu des deux côtés
    autre_tiers = ligne(3, "FAC-1", tiers_b)
    assert facture_en_double(autre_tiers) is False  # même référence, autre fournisseur
    autre_reference = ligne(4, "FAC-2", tiers_a)
    assert facture_en_double(autre_reference) is False
    sans_reference = ligne(5, "", tiers_a)
    assert facture_en_double(sans_reference) is False  # on n'affirme pas un doublon sans référence
    sans_tiers = ligne(6, "FAC-1", None)
    assert facture_en_double(sans_tiers) is False
    assert contexte_depense(premiere)["facture_en_double"] is True


def test_le_contexte_d_une_avance_donne_un_controle_de_delai_juste(cadre_avances):
    organisation, projet, profils, agents = cadre_avances
    avance = _verser(projet, profils, agents, montant="1000", date=datetime.date(2026, 2, 1))
    delai = lib.PAR_CODE["AVA-DELAI"]
    justifiee = lib.PAR_CODE["AVA-NON-JUSTIFIEE"]

    def contexte(date):
        situation = situation_avance(profils["amina"], avance, date)
        return contexte_avance(situation, date)

    pas_echue = contexte(datetime.date(2026, 2, 20))  # délai de 30 jours : échéance le 03/03
    assert (pas_echue["jours_de_retard"], pas_echue["jours_depuis_versement"]) == (0, 19)
    assert pas_echue["delai_applicable_jours"] == 30 and pas_echue["justifiee"] is False
    echue = contexte(datetime.date(2026, 3, 10))
    assert echue["jours_de_retard"] == 7 and echue["montant_justifie"] == D("0")

    from tests.test_bibliotheque_controles import decision

    assert decision(delai, pas_echue).resultat == "reussi"
    assert decision(delai, echue).resultat == "bloquant"
    assert decision(justifiee, echue).resultat == "avertissement"

    _justifier(avance, profils, "1000", datetime.date(2026, 3, 5))
    solde = contexte(datetime.date(2026, 3, 10))
    assert solde["justifiee"] is True and solde["jours_de_retard"] == 0
    assert (
        decision(delai, solde).resultat == "reussi"
        and decision(justifiee, solde).resultat == "reussi"
    )
