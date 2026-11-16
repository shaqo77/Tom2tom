# ruff: noqa: F811, E501
"""L'état « rapprochement du compte désigné », branché sur le moteur d'états. Voir L9-T05.

Le moteur sait lire, en plus du grand livre, une SOURCE EXTERNE déclarée (ici le relevé bancaire, les
appariements aux demandes et les justifications). Le rapport se publie, se scelle et se régénère
comme les autres ; une assertion bloque la publication tant qu'un écart n'est pas justifié.
"""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from niveau1_socle.habilitations.models import Habilitation, Role
from niveau1_socle.tresorerie.services import enregistrer_solde_releve, justifier_ecart
from niveau4_reporting.modeles_etats import modele_rapprochement_compte_designe
from niveau4_reporting.moteur.assertions import AssertionsViolees
from niveau4_reporting.moteur.compilateur import ModeleEtatInvalide, generer
from niveau4_reporting.moteur.sources_externes import SourceIncomplete
from niveau4_reporting.publication.models import RapportPublie
from niveau4_reporting.publication.rapports import publier_rapport, regenerer
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_tresorerie_bd import DEBUT, FIN, _importer, _scenario, banque  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
J = datetime.date
D = Decimal
Utilisateur = get_user_model()


def _params(projet, **champs):
    return {
        "fiscal_year": 2026,
        "current_period": 3,
        "compte_designe": "CD-DJF",
        "date_debut": DEBUT.isoformat(),
        "date_fin": FIN.isoformat(),
        "project_id": str(projet.id),
    } | champs


@pytest.fixture
def etat(banque):
    """Le scénario de trésorerie, clôture enregistrée au relevé : l'état est complet et sans écart."""
    organisation, projet, profils, designe, _ = banque
    _scenario(banque)
    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=designe, date_solde=FIN, solde="1200"
    )
    pia = Utilisateur.objects.create_user("pia", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id, code="PIA", label={"fr": "p"}, operations=["consulter", "publier"]
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=pia.id, project_id=projet.id, role=role
    )
    profils["pia"] = pia
    return banque


def _publier(etat, **params):
    organisation, projet, profils, _, _ = etat
    return publier_rapport(
        utilisateur=profils["pia"], project_id=projet.id, modele=modele_rapprochement_compte_designe(),
        params=_params(projet, **params), tables={}, period_from=DEBUT, period_to=FIN,
    )  # fmt: skip


def test_le_moteur_produit_l_etat_de_reconstitution_depuis_la_source_externe(etat):
    projet = etat[1]
    produit = generer(modele_rapprochement_compte_designe(), {}, _params(projet))
    v = {code: valeurs["PER"] for code, valeurs in produit.valeurs.items()}
    assert (v["R110"], v["R120"], v["R130"], v["R140"]) == (D("1000"), D("300"), D("50"), D("150"))
    assert v["R150"] == D("1200") == v["R160"] and v["R170"] == 0 and v["R180"] == 0
    assert v["R190"] == D("1200") and v["R200"] == 0 and v["R210"] == 0


def test_le_rapport_se_publie_se_scelle_et_se_regenere_a_l_identique(etat):
    publie = _publier(etat)
    assert len(bytes(publie.seal)) == 32 and publie.values["R150/PER"] == "1200"
    assert regenerer(publie).identique
    assert publie.mapping_versions == {}  # aucun mapping : tout vient de la source externe


def test_un_ecart_non_justifie_bloque_la_publication_puis_la_justification_la_debloque(etat):
    organisation, projet, profils, designe, _ = etat
    # Un mouvement importé de plus, que le relevé de clôture (1 200) ne contient pas : le calculé
    # monte à 1 205 ; l'écart de relevé (−5) et l'écart avec le grand livre (−5) sont à justifier.
    _importer(profils, designe, ("EXTRA", J(2026, 3, 20), "5"))
    with pytest.raises(AssertionsViolees) as e:
        _publier(etat)
    assert {c.rubrique for c in e.value.violations} == {"R180", "R210"}
    assert not RapportPublie.objects.exists()
    base = {"compte": designe, "date_debut": DEBUT, "date_fin": FIN, "montant": "-5"}
    justifier_ecart(
        utilisateur=profils["bruno"],
        cible="releve",
        explication="Virement reçu après la clôture",
        **base,
    )
    with pytest.raises(AssertionsViolees) as e:  # l'écart avec le grand livre reste à expliquer
        _publier(etat)
    assert {c.rubrique for c in e.value.violations} == {"R210"}
    justifier_ecart(
        utilisateur=profils["bruno"],
        cible="comptable",
        explication="Écriture non encore passée",
        **base,
    )
    publie = _publier(etat)
    assert (publie.values["R180/PER"], publie.values["R210/PER"]) == ("0", "0")
    assert (
        publie.values["R170/PER"] == "-5" and publie.values["R200/PER"] == "-5"
    )  # les écarts restent affichés


def test_sans_solde_d_ouverture_ou_de_cloture_le_rapport_est_refuse(etat):
    organisation, projet, profils, designe, _ = etat
    with pytest.raises(SourceIncomplete) as e:
        _publier(etat, date_debut="2026-03-01", date_fin="2026-03-31")  # pas de relevé au 28/02
    assert "ouverture" in str(e.value)
    assert not RapportPublie.objects.exists()


def test_un_mouvement_arrive_apres_la_publication_bloque_la_regeneration_puis_se_nomme_une_fois_justifie(
    etat,
):
    organisation, projet, profils, designe, _ = etat
    publie = _publier(etat)
    _importer(profils, designe, ("TARDIF", J(2026, 3, 25), "40"))
    with pytest.raises(
        AssertionsViolees
    ):  # le rapport publié ne change pas ; sa régénération est bloquée
        regenerer(publie)
    assert publie.values["R150/PER"] == "1200"
    base = {"compte": designe, "date_debut": DEBUT, "date_fin": FIN, "montant": "-40"}
    justifier_ecart(
        utilisateur=profils["bruno"], cible="releve", explication="Virement tardif", **base
    )
    justifier_ecart(
        utilisateur=profils["bruno"], cible="comptable", explication="Écriture à passer", **base
    )
    resultat = regenerer(publie)
    assert not resultat.identique
    assert {(e.rubrique, e.nouveau - e.ancien) for e in resultat.ecarts} == {
        ("R130", D("40")), ("R150", D("40")), ("R170", D("-40")), ("R200", D("-40")),
    }  # fmt: skip


def test_le_numero_du_compte_n_apparait_dans_aucune_donnee_du_rapport(etat):
    publie = _publier(etat)
    contenu = f"{publie.values}{publie.params}{publie.modele}{publie.config_version}"
    assert "DJ21" not in contenu and "8877" not in contenu


def test_une_source_ou_une_rubrique_externe_inconnue_est_refusee_a_la_compilation(etat):
    projet = etat[1]
    base = modele_rapprochement_compte_designe()
    inconnue = {
        **base,
        "rows": [{"code": "X", "type": "external", "source": "inconnue", "item": "ouverture"}],
    }
    with pytest.raises(ModeleEtatInvalide):
        generer(inconnue, {}, _params(projet))
    mauvaise = {
        **base,
        "rows": [
            {"code": "X", "type": "external", "source": "compte_designe", "item": "n_importe_quoi"}
        ],
    }
    with pytest.raises(ModeleEtatInvalide):
        generer(mauvaise, {}, _params(projet))
    sans_source = {**base, "rows": [{"code": "X", "type": "external", "item": "ouverture"}]}
    with pytest.raises(ModeleEtatInvalide):
        generer(sans_source, {}, _params(projet))


def test_un_compte_inconnu_ou_non_designe_est_refuse(etat):
    projet = etat[1]
    with pytest.raises(ModeleEtatInvalide):
        generer(
            modele_rapprochement_compte_designe(), {}, _params(projet, compte_designe="INCONNU")
        )
    with pytest.raises(ModeleEtatInvalide):
        generer(
            modele_rapprochement_compte_designe(), {}, _params(projet, date_debut="pas-une-date")
        )


def test_un_compte_qui_n_est_pas_un_compte_designe_est_refuse_par_la_source(etat):
    from niveau1_socle.financements.services import creer_compte_bancaire

    _, projet, profils, _, _ = etat
    creer_compte_bancaire(
        utilisateur=profils["dora"], project_id=projet.id, code="CO-1", type="operationnel",
        devise="DJF", banque="BCD", numero="OP-1",
    )  # fmt: skip
    with pytest.raises(ModeleEtatInvalide) as e:
        generer(modele_rapprochement_compte_designe(), {}, _params(projet, compte_designe="CO-1"))
    assert "CO-1" in str(e.value)
