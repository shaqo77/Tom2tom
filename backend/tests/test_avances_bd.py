"""Suivi des avances. Voir L4-T07.

Une avance non justifiée au-delà du délai est ce que contrôle le lot L6 : ce lot fournit la liste,
les délais applicables (versionnés) et les alertes.
"""

import datetime
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from niveau1_socle.avances.models import Avance, DelaiAvance, JustificationAvance
from niveau1_socle.avances.services import (
    AvanceInvalide,
    alertes,
    avances_non_justifiees_au_dela_du_delai,
    delai_applicable,
    encours_par_tiers,
    justifier_avance,
    parametrer_delai,
    situation_avance,
    suivi,
    verser_avance,
)
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau1_socle.referentiels.models import Tiers
from tests.outils import connexion_proprietaire
from tests.test_cycle_ecriture_bd import _poser, decor  # noqa: F401
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = Decimal
JAN = datetime.date(2026, 1, 1)


@pytest.fixture
def cadre(decor):  # noqa: F811
    """amina saisit, claire consulte seulement ; dora paramètre ; deux agents (tiers)."""
    organisation, projet, profils = decor
    for nom, operations in {"dora": ["consulter", "parametrer"], "lecteur": ["consulter"]}.items():
        utilisateur = Utilisateur.objects.create_user(nom, password="x", org_id=organisation.id)
        role = Role.objects.create(
            org_id=organisation.id, code=nom.upper(), label={"fr": nom}, operations=operations
        )
        Habilitation.objects.create(
            org_id=organisation.id, user_id=utilisateur.id, project_id=projet.id, role=role
        )
        profils[nom] = utilisateur
    # amina doit aussi consulter pour lire le suivi qu'elle alimente.
    agents = {
        code: Tiers.objects.create(org_id=organisation.id, code=code, nature="personnel", nom=code)
        for code in ("AGENT-1", "AGENT-2")
    }
    parametrer_delai(utilisateur=profils["dora"], project_id=projet.id, jours=30, date_effet=JAN)
    return organisation, projet, profils, agents


def _verser(
    projet,
    profils,
    agents,
    reference="AV-1",
    montant="1000",
    date=datetime.date(2026, 2, 1),
    agent="AGENT-1",
    **champs,
):
    return verser_avance(
        utilisateur=profils["amina"],
        project_id=projet.id,
        tiers=agents[agent],
        reference=reference,
        montant=montant,
        date_versement=date,
        **champs,
    )


def _justifier(avance, profils, montant, date, type="depense", reference="PJ-1"):
    return justifier_avance(
        avance,
        utilisateur=profils["amina"],
        type=type,
        montant=montant,
        date_justification=date,
        reference=reference,
    )


# --- délai applicable -----------------------------------------------------------------------


def test_le_delai_est_versionne_et_une_avance_garde_celui_de_son_versement(cadre):
    organisation, projet, profils, agents = cadre
    av_janvier = _verser(projet, profils, agents, "AV-J", date=datetime.date(2026, 2, 1))
    assert av_janvier.delai_jours == 30
    v2 = parametrer_delai(
        utilisateur=profils["dora"],
        project_id=projet.id,
        jours=45,
        date_effet=datetime.date(2026, 3, 1),
        motif="Nouvel accord",
    )
    av_mars = _verser(projet, profils, agents, "AV-M", date=datetime.date(2026, 3, 15))
    assert av_mars.delai_jours == 45
    av_janvier.refresh_from_db()
    assert av_janvier.delai_jours == 30  # l'avance de février garde 30 jours
    # Une avance versée AVANT l'entrée en vigueur du nouveau délai, mais saisie après, prend
    # le délai en vigueur à SA date de versement, pas le plus récent.
    av_antidatee = _verser(projet, profils, agents, "AV-A", date=datetime.date(2026, 2, 15))
    assert av_antidatee.delai_jours == 30
    v1 = DelaiAvance.objects.get(version=1)
    assert v1.valid_to == datetime.date(2026, 3, 1) and v2.valid_to is None
    assert delai_applicable(projet.id, datetime.date(2026, 2, 28)).jours == 30
    assert delai_applicable(projet.id, datetime.date(2026, 3, 1)).jours == 45
    assert delai_applicable(projet.id, datetime.date(2025, 12, 31)) is None


def test_sans_delai_parametre_on_ne_devine_pas_un_delai(decor):  # noqa: F811
    organisation, projet, profils = decor
    agent = Tiers.objects.create(org_id=organisation.id, code="A", nature="personnel", nom="A")
    with pytest.raises(AvanceInvalide, match="Aucun délai"):
        verser_avance(
            utilisateur=profils["amina"],
            project_id=projet.id,
            tiers=agent,
            reference="X",
            montant="10",
            date_versement=JAN,
        )
    avance = verser_avance(
        utilisateur=profils["amina"],
        project_id=projet.id,
        tiers=agent,
        reference="X",
        montant="10",
        date_versement=JAN,
        delai_jours=15,
    )
    assert avance.delai_jours == 15  # délai précisé : accepté


def test_parametrer_le_delai_exige_l_habilitation_et_des_valeurs_valides(cadre):
    organisation, projet, profils, agents = cadre
    with pytest.raises(PermissionDenied):
        parametrer_delai(
            utilisateur=profils["amina"],
            project_id=projet.id,
            jours=10,
            date_effet=datetime.date(2026, 6, 1),
        )
    for jours in (0, -3):
        with pytest.raises(AvanceInvalide, match="strictement positif"):
            parametrer_delai(
                utilisateur=profils["dora"],
                project_id=projet.id,
                jours=jours,
                date_effet=datetime.date(2026, 6, 1),
            )
    with pytest.raises(AvanceInvalide, match="après le 2026-01-01"):
        parametrer_delai(
            utilisateur=profils["dora"], project_id=projet.id, jours=10, date_effet=JAN
        )


def test_la_base_garde_les_delais(cadre):
    organisation, projet, profils, agents = cadre
    delai = DelaiAvance.objects.get()
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="ne se supprime pas"):
            admin.execute("DELETE FROM avances_delaiavance WHERE id = %s", [delai.pk])
        with pytest.raises(Exception, match="clôture de sa validité"):
            admin.execute("UPDATE avances_delaiavance SET jours = 1 WHERE id = %s", [delai.pk])
        with pytest.raises(Exception, match="chevauchement"):
            admin.execute(
                "INSERT INTO avances_delaiavance (id, created_at, updated_at, org_id, project_id, "
                "jours, version, valid_from, motif) "
                "VALUES (gen_random_uuid(), now(), now(), %s, %s, 10, 9, '2026-06-01', '')",
                [organisation.id, projet.id],
            )


# --- verser, justifier ----------------------------------------------------------------------


def test_verser_une_avance_calcule_l_echeance_et_refuse_les_valeurs_invalides(cadre):
    organisation, projet, profils, agents = cadre
    avance = _verser(projet, profils, agents, date=datetime.date(2026, 2, 1))
    s = situation_avance(profils["lecteur"], avance, datetime.date(2026, 2, 1))
    assert s.echeance == datetime.date(2026, 3, 3) and s.reste == D(1000)
    for champs, message in [
        ({"montant": "0"}, "strictement positif"),
        ({"montant": "-5"}, "strictement positif"),
        ({"reference": " "}, "référence"),
        ({"delai_jours": 0}, "strictement positif"),
    ]:
        with pytest.raises(AvanceInvalide, match=message):
            _verser(projet, profils, agents, **({"reference": "Z"} | champs))
    with pytest.raises(PermissionDenied):
        verser_avance(
            utilisateur=profils["lecteur"],
            project_id=projet.id,
            tiers=agents["AGENT-1"],
            reference="Q",
            montant="1",
            date_versement=JAN,
        )
    with pytest.raises(IntegrityError, match="uq_avance_reference"), transaction.atomic():
        _verser(projet, profils, agents)  # même référence


def test_justifier_par_depenses_puis_remboursement_solde_l_avance(cadre):
    organisation, projet, profils, agents = cadre
    avance = _verser(projet, profils, agents)
    _justifier(avance, profils, "600", datetime.date(2026, 2, 10), reference="FAC-1")
    s = situation_avance(profils["lecteur"], avance, datetime.date(2026, 2, 20))
    assert (s.justifie_depenses, s.reste, s.niveau) == (D(600), D(400), "en_cours")
    _justifier(
        avance, profils, "400", datetime.date(2026, 2, 25), type="remboursement", reference=""
    )
    s = situation_avance(profils["lecteur"], avance, datetime.date(2026, 2, 28))
    assert (s.justifie_remboursements, s.reste, s.niveau, s.jours_de_retard) == (
        D(400),
        D(0),
        "soldee",
        0,
    )
    assert verifier_chaine(organisation.id) is None


def test_on_ne_justifie_pas_plus_que_l_avance_et_une_depense_exige_une_piece(cadre):
    organisation, projet, profils, agents = cadre
    avance = _verser(projet, profils, agents)
    _justifier(avance, profils, "900", datetime.date(2026, 2, 10))
    with pytest.raises(AvanceInvalide, match="reste 100"):
        _justifier(avance, profils, "101", datetime.date(2026, 2, 11), reference="PJ-2")
    with pytest.raises(AvanceInvalide, match="pièce"):
        _justifier(avance, profils, "50", datetime.date(2026, 2, 11), reference=" ")
    with pytest.raises(AvanceInvalide, match="strictement positif"):
        _justifier(avance, profils, "0", datetime.date(2026, 2, 11))
    with pytest.raises(AvanceInvalide, match="type"):
        _justifier(avance, profils, "5", datetime.date(2026, 2, 11), type="don")
    with pytest.raises(PermissionDenied):
        justifier_avance(
            avance,
            utilisateur=profils["lecteur"],
            type="depense",
            montant="1",
            date_justification=datetime.date(2026, 2, 11),
            reference="x",
        )
    assert JustificationAvance.objects.count() == 1


def test_la_base_refuse_une_justification_excessive_ou_anterieure_au_versement(cadre):
    organisation, projet, profils, agents = cadre
    avance = _verser(projet, profils, agents)
    base = (
        "INSERT INTO avances_justificationavance (id, created_at, updated_at, org_id, avance_id, "
        "type, montant, date_justification, reference) "
        "VALUES (gen_random_uuid(), now(), now(), %s, %s, 'depense', %s, %s, 'P')"
    )
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="dépasseraient l'avance"):
            admin.execute(base, [organisation.id, avance.pk, 1001, "2026-02-10"])
        with pytest.raises(Exception, match="ne précède pas le versement"):
            admin.execute(base, [organisation.id, avance.pk, 10, "2026-01-31"])
        admin.execute(base, [organisation.id, avance.pk, 1000, "2026-02-10"])  # pile le montant


def test_une_avance_et_ses_justifications_sont_en_ajout_seul(cadre):
    organisation, projet, profils, agents = cadre
    avance = _verser(projet, profils, agents)
    justification = _justifier(avance, profils, "100", datetime.date(2026, 2, 10))
    with connexion_proprietaire() as admin:
        for requete, cible in [
            ("UPDATE avances_avance SET montant = 1 WHERE id = %s", avance.pk),
            ("DELETE FROM avances_avance WHERE id = %s", avance.pk),
            ("UPDATE avances_justificationavance SET montant = 1 WHERE id = %s", justification.pk),
            ("DELETE FROM avances_justificationavance WHERE id = %s", justification.pk),
        ]:
            with pytest.raises(Exception, match="ajout seul"):
                admin.execute(requete, [cible])
    assert Avance.objects.get().montant == D(1000)


# --- échéances, retard, alertes -------------------------------------------------------------


def test_le_niveau_d_une_avance_suit_l_echeance_le_retard_et_le_preavis(cadre):
    organisation, projet, profils, agents = cadre
    avance = _verser(projet, profils, agents, date=datetime.date(2026, 2, 1))  # échéance 3 mars
    lecteur = profils["lecteur"]

    def s(jour):
        return situation_avance(lecteur, avance, jour)

    assert s(datetime.date(2026, 2, 10)).niveau == "en_cours"
    assert s(datetime.date(2026, 2, 24)).niveau == "a_echeance"  # 7 jours avant
    assert s(datetime.date(2026, 3, 3)).niveau == "a_echeance"  # le jour même : pas encore échue
    echue = s(datetime.date(2026, 3, 4))
    assert (echue.niveau, echue.jours_de_retard) == ("echue", 1)
    assert s(datetime.date(2026, 3, 13)).jours_de_retard == 10
    # Une justification TARDIVE solde l'avance, mais le passé reste lisible : à la veille de la
    # justification, l'avance était bien échue.
    _justifier(avance, profils, "1000", datetime.date(2026, 3, 20))
    assert s(datetime.date(2026, 3, 19)).niveau == "echue"
    assert s(datetime.date(2026, 3, 20)).niveau == "soldee"


def test_le_suivi_a_une_date_ignore_les_justifications_posterieures(cadre):
    organisation, projet, profils, agents = cadre
    avance = _verser(projet, profils, agents, date=datetime.date(2026, 2, 1))  # échéance 3 mars
    _justifier(avance, profils, "1000", datetime.date(2026, 3, 20))
    lecteur = profils["lecteur"]
    avant = {s.avance.reference: s for s in suivi(lecteur, projet.id, datetime.date(2026, 3, 10))}
    assert (avant["AV-1"].reste, avant["AV-1"].niveau) == (D(1000), "echue")
    assert [
        r.avance.reference
        for r in avances_non_justifiees_au_dela_du_delai(
            lecteur, projet.id, datetime.date(2026, 3, 10)
        )
    ] == ["AV-1"]
    apres = suivi(lecteur, projet.id, datetime.date(2026, 3, 20))
    assert (apres[0].reste, apres[0].niveau) == (D(0), "soldee")


def test_les_avances_non_justifiees_au_dela_du_delai_pour_le_controle_de_l6(cadre):
    organisation, projet, profils, agents = cadre
    en_retard = _verser(projet, profils, agents, "AV-RETARD", "500", datetime.date(2026, 1, 5))
    partielle = _verser(
        projet, profils, agents, "AV-PARTIELLE", "800", datetime.date(2026, 1, 10), agent="AGENT-2"
    )
    _justifier(partielle, profils, "300", datetime.date(2026, 1, 20))
    soldee = _verser(projet, profils, agents, "AV-SOLDEE", "100", datetime.date(2026, 1, 8))
    _justifier(soldee, profils, "100", datetime.date(2026, 1, 9))
    recente = _verser(projet, profils, agents, "AV-RECENTE", "100", datetime.date(2026, 3, 10))
    futur = _verser(projet, profils, agents, "AV-FUTURE", "100", datetime.date(2026, 6, 1))

    jour = datetime.date(2026, 3, 15)
    lecteur = profils["lecteur"]
    retards = avances_non_justifiees_au_dela_du_delai(lecteur, projet.id, jour)
    assert [(r.avance.reference, r.reste, r.jours_de_retard) for r in retards] == [
        ("AV-RETARD", D(500), 39),  # échue le 4 février
        ("AV-PARTIELLE", D(500), 34),  # 800 - 300, échue le 9 février
    ]
    assert futur.reference not in {r.avance.reference for r in suivi(lecteur, projet.id, jour)}
    assert {s.avance.reference: s.niveau for s in suivi(lecteur, projet.id, jour)} == {
        "AV-RETARD": "echue",
        "AV-PARTIELLE": "echue",
        "AV-RECENTE": "en_cours",
        "AV-SOLDEE": "soldee",
    }
    assert encours_par_tiers(lecteur, projet.id, jour) == {"AGENT-1": D(600), "AGENT-2": D(500)}
    assert recente and en_retard


def test_les_alertes_distinguent_l_echue_et_l_a_venir(cadre):
    organisation, projet, profils, agents = cadre
    _verser(projet, profils, agents, "AV-ECHUE", "500", datetime.date(2026, 1, 5))
    _verser(
        projet, profils, agents, "AV-BIENTOT", "200", datetime.date(2026, 2, 10), agent="AGENT-2"
    )
    _verser(projet, profils, agents, "AV-LOIN", "200", datetime.date(2026, 3, 1))
    liste = alertes(profils["lecteur"], projet.id, datetime.date(2026, 3, 5))
    assert [(a.niveau, a.situation.avance.reference) for a in liste] == [
        ("echue", "AV-ECHUE"),
        ("a_echeance", "AV-BIENTOT"),
    ]
    assert "échue depuis 29 jour(s)" in liste[0].message and "500" in liste[0].message
    assert "avant le 2026-03-12" in liste[1].message
    # Un préavis plus large ajoute l'avance lointaine ; un préavis nul retire celle à venir.
    assert len(alertes(profils["lecteur"], projet.id, datetime.date(2026, 3, 5), preavis=40)) == 3
    assert len(alertes(profils["lecteur"], projet.id, datetime.date(2026, 3, 5), preavis=0)) == 1


def test_le_suivi_exige_l_habilitation_consulter(cadre):
    organisation, projet, profils, agents = cadre
    inconnu = Utilisateur.objects.create_user("eve", password="x", org_id=organisation.id)
    avance = _verser(projet, profils, agents)
    with pytest.raises(PermissionDenied):
        suivi(inconnu, projet.id, JAN)
    with pytest.raises(PermissionDenied):
        alertes(inconnu, projet.id, JAN)
    with pytest.raises(PermissionDenied):
        situation_avance(inconnu, avance, JAN)


# --- concurrence ----------------------------------------------------------------------------


def _justifier_en_concurrence(org_id, user_id, avance_id, barriere):
    try:
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [str(org_id)])
        barriere.wait()
        utilisateur = Utilisateur.objects.get(pk=user_id)
        avance = Avance.objects.get(pk=avance_id)
        justifier_avance(
            avance,
            utilisateur=utilisateur,
            type="depense",
            montant="100",
            date_justification=datetime.date(2026, 2, 10),
            reference="PJ",
        )
        return "ok"
    except AvanceInvalide:
        return "refusee"
    finally:
        connections.close_all()


def test_dix_justifications_simultanees_ne_depassent_jamais_l_avance(cadre):
    organisation, projet, profils, agents = cadre
    avance = _verser(projet, profils, agents, montant="300")
    barriere = threading.Barrier(10)
    with ThreadPoolExecutor(max_workers=10) as pool:
        futurs = [
            pool.submit(
                _justifier_en_concurrence, organisation.id, profils["amina"].id, avance.pk, barriere
            )
            for _ in range(10)
        ]
        issues = [f.result() for f in futurs]
    assert sorted(issues) == ["ok"] * 3 + ["refusee"] * 7
    assert sum(j.montant for j in JustificationAvance.objects.all()) == D(300)
    assert situation_avance(profils["lecteur"], avance, datetime.date(2026, 2, 11)).reste == D(0)


# --- isolation ------------------------------------------------------------------------------


def test_les_avances_sont_isolees_par_organisation(cadre):
    organisation, projet, profils, agents = cadre
    avance = _verser(projet, profils, agents)
    _justifier(avance, profils, "10", datetime.date(2026, 2, 10))
    autre = _creer_organisation("ORG-B")
    _poser(autre)
    for modele in (DelaiAvance, Avance, JustificationAvance):
        assert modele.objects.count() == 0, modele
