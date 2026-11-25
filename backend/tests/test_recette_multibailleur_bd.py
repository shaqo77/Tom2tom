# ruff: noqa: F811, E501
"""Recette multibailleur, première version (L6) : UN projet, DEUX bailleurs, une dépense saisie UNE SEULE
fois, ventilée, deux demandes de retrait aux montants différents, des rapports par accord qui ne se
contredisent pas, et une seconde organisation qui ne voit rien. Aucune écriture manuelle entre les étapes :
tout passe par l'API ou par les services.

Questionnaire, questions 55 à 58. Le test est UN SEUL test long, découpé en étapes commentées : la valeur
de la recette est de montrer la chaîne entière, pas des morceaux.
"""

import datetime
import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone

from niveau1_socle.comptabilite.models import Ecriture, LigneEcriture
from niveau1_socle.decaissements.models import DemandeRetrait
from niveau1_socle.financements.cles import creer_cle
from niveau1_socle.financements.models import Accord
from niveau1_socle.financements.services import creer_bailleur, creer_categorie
from niveau4_reporting.mapping.models import RegleMapping, TableMapping
from niveau4_reporting.moteur.compilateur import generer
from tests.outils_profil import creer_profil
from tests.test_api_marches_bd import appeler
from tests.test_cles_cofinancement_bd import _version
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import _preparer
from tests.test_financements_bd import _accord, _activer, cadre  # noqa: F401
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
D = Decimal
J = datetime.date

# Le TER livré : R110 = toutes les charges, R210 = les charges d'UN accord (paramètre `agreement`).
TER = {
    "code": "TER",
    "version": 1,
    "columns": [{"code": "CUMUL", "period": "inception_to_date"}],
    "rows": [
        {
            "code": "R110",
            "type": "aggregate",
            "select": {"mapping": "RECETTE", "target": "CHARGES"},
        },
        {
            "code": "R210",
            "type": "aggregate",
            "select": {
                "mapping": "RECETTE",
                "target": "CHARGES",
                "filters": {"agreement": "$param.agreement"},
            },
        },
    ],
}


def _poser(org_id):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])


def _mapping(organisation, projet):
    """La nomenclature du rapport : les charges (classe 6) et la trésorerie (classe 5)."""
    table = TableMapping.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        donor_profile_id=uuid.uuid4(),
        code="RECETTE",
        version=1,
        valid_from=J(2026, 1, 1),
        status="active",
        validated_by=uuid.uuid4(),
        validated_at=timezone.now(),
    )
    for priorite, cible, plage in (
        (10, "CHARGES", ["6000", "6999"]),
        (20, "TRESORERIE", ["5200", "5399"]),
    ):
        RegleMapping.objects.create(
            org_id=organisation.id,
            table=table,
            priority=priorite,
            match={"accounts": [plage]},
            target_code=cible,
        )
    return {"RECETTE": list(table.regles.all())}


# Le même modèle SANS le filtre d'accord : le rapport global du projet.
TER_GLOBAL = {**TER, "rows": TER["rows"][:1]}


def _rapport(projet, regles, accord=None):
    parametres = {"fiscal_year": 2026, "current_period": 3, "project_id": projet.id}
    if accord is None:
        return generer(TER_GLOBAL, regles, parametres)
    return generer(TER, regles, {**parametres, "agreement": str(accord.pk)})


def _saisir(profils, projet, montant):
    """UNE dépense, saisie UNE fois, par l'API : une clé de cofinancement et une catégorie par code."""
    r = appeler(
        profils["amina"],
        "post",
        f"/projets/{projet.id}/ecritures/",
        {
            "journal": "OD",
            "date_comptable": "2026-03-10",
            "libelle": "Prestation commune",
            "lignes": [
                {"compte": "6011", "debit": montant, "cle": "CHARGES", "categorie": "SERV"},
                {"compte": "5211", "credit": montant},
            ],
        },
    )
    assert r.status_code == 201, r.content
    e = r.json()
    assert (
        appeler(
            profils["bruno"], "post", f"/projets/{projet.id}/ecritures/{e['id']}/valider/"
        ).status_code
        == 200
    )
    posted = appeler(
        profils["claire"], "post", f"/projets/{projet.id}/ecritures/{e['id']}/comptabiliser/"
    )
    assert posted.status_code == 200 and posted.json()["status"] == "posted", posted.content
    return posted.json()


def test_recette_multibailleur_une_depense_deux_bailleurs_des_rapports_coherents(cadre):
    organisation, projet, profils, bailleur1 = cadre
    dora = profils["dora"]

    # 1. Un projet, DEUX accords de DEUX bailleurs, et une clé de cofinancement 60/40.
    a1 = _activer(
        _accord(projet, profils, bailleur1, "IDA-1", devise="DJF", montant_initial="100000"),
        profils,
    )
    bailleur2 = creer_bailleur(
        utilisateur=dora, code="BAD", nom="Banque africaine de développement"
    )
    a2 = _activer(
        _accord(projet, profils, bailleur2, "BAD-1", devise="DJF", montant_initial="100000"),
        profils,
    )
    assert a1.bailleur_id != a2.bailleur_id
    serv1 = creer_categorie(
        utilisateur=dora, accord=a1, code="SERV", label={"fr": "Services"}, plafond="100000"
    )
    serv2 = creer_categorie(
        utilisateur=dora, accord=a2, code="SERV", label={"fr": "Services"}, plafond="100000"
    )
    cle = creer_cle(
        utilisateur=dora, project_id=projet.id, code="CHARGES", label={"fr": "Charges communes"}
    )
    version = _version(profils, cle, {"A1": a1, "A2": a2}, {"A1": 60, "A2": 40}, porteur="A1")

    # 3. (avant la saisie, car elles décident ce que chaque accord rembourse) Un profil par accord, des taux DIFFÉRENTS.
    creer_profil(organisation, projet, a1, regles=[(serv1, "0.8")])
    creer_profil(organisation, projet, a2, regles=[(serv2, "0.5")])

    # 2. UNE dépense de 1 000, saisie UNE fois, puis une seconde de 1 001 pour éprouver l'arrondi.
    _poser(organisation.id)
    avant = Ecriture.objects.count()
    pleine = _saisir(profils, projet, "1000")
    arrondie = _saisir(profils, projet, "1001")
    _poser(organisation.id)  # l'appel HTTP a remis le périmètre à zéro
    assert (
        Ecriture.objects.count() == avant + 2
    )  # deux pièces saisies, pas une de plus : rien n'est dupliqué

    def part(piece, accord):
        return sum(
            D(x["debit"])
            for x in piece["lignes"]
            if x["compte"] == "6011" and x["accord"] == accord.numero
        )

    # La ventilation conserve la dépense AU CENTIME (ici au franc : DJF n'a pas de centimes) …
    assert (part(pleine, a1), part(pleine, a2)) == (D(600), D(400))
    assert part(arrondie, a1) + part(arrondie, a2) == D(1001)
    assert part(arrondie, a2) == D(
        400
    )  # 40 % de 1 001 = 400,4 → 400 ; le porteur (IDA) absorbe le reliquat
    assert part(arrondie, a1) == D(601)
    # … chaque ligne ventilée porte la version de clé et la catégorie DE SON accord.
    lignes = LigneEcriture.objects.filter(entry_id=pleine["id"], account__code="6011")
    assert {x.agreement_id: x.category_id for x in lignes} == {a1.pk: serv1.pk, a2.pk: serv2.pk}
    assert {x.cofunding_key_version_id for x in lignes} == {version.pk}

    # 4. DEUX demandes de retrait, une par accord, sur la dépense de 1 000, aux montants DIFFÉRENTS.
    ligne_a1 = lignes.get(agreement_id=a1.pk)
    ligne_a2 = lignes.get(agreement_id=a2.pk)
    demande1 = _preparer(profils, a1, [ligne_a1.id], date_demande=J(2026, 3, 20))
    demande2 = _preparer(profils, a2, [ligne_a2.id], date_demande=J(2026, 3, 20))
    assert (demande1.lignes.get().taux_applique, demande1.lignes.get().montant_a_retirer) == (
        D("0.8"),
        D(480),
    )
    assert (demande2.lignes.get().taux_applique, demande2.lignes.get().montant_a_retirer) == (
        D("0.5"),
        D(200),
    )
    assert demande1.montant_total != demande2.montant_total
    # La liste des demandes du projet (API) les montre toutes les deux, chacune sous son accord.
    liste = appeler(profils["amina"], "get", f"/projets/{projet.id}/demandes-retrait/").json()
    _poser(organisation.id)
    assert {(d["accord"], d["montant_total"]) for d in liste} == {
        ("IDA-1", "480.0000"),
        ("BAD-1", "200.0000"),
    }

    # 5. Trois rapports sur les MÊMES données : un par accord, plus le global. Ils ne se contredisent pas.
    regles = _mapping(organisation, projet)
    global_ = _rapport(projet, regles)
    rapport1 = _rapport(projet, regles, a1)
    rapport2 = _rapport(projet, regles, a2)
    assert global_["R110"]["CUMUL"] == D(2001)  # la dépense, toutes saisies confondues
    assert rapport1["R210"]["CUMUL"] == D(1201)  # 600 + 601
    assert rapport2["R210"]["CUMUL"] == D(800)  # 400 + 400
    assert rapport1["R210"]["CUMUL"] != rapport2["R210"]["CUMUL"]  # des rapports DISTINCTS …
    assert (
        rapport1["R210"]["CUMUL"] + rapport2["R210"]["CUMUL"] == global_["R110"]["CUMUL"]
    )  # … qui se recoupent
    assert (
        rapport1["R110"]["CUMUL"] == rapport2["R110"]["CUMUL"] == global_["R110"]["CUMUL"]
    )  # même base

    # 6. L'isolation : une AUTRE organisation ne voit rien de tout cela.
    autre = _creer_organisation("AUTRE")
    _poser(autre.id)
    try:
        assert Accord.objects.count() == 0
        assert Ecriture.objects.count() == 0
        assert DemandeRetrait.objects.count() == 0
        with connection.cursor() as cur:
            cur.execute("SELECT count(*) FROM moteur_ligneecriture")
            assert cur.fetchone()[0] == 0
    finally:
        with connection.cursor() as cur:  # le périmètre d'un test ne survit pas à ce test
            cur.execute("RESET app.org_id")
