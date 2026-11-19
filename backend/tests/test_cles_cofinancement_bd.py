"""Clés de cofinancement : versions, ventilation, lignes produites. Voir L4-T05.

Le contrôle de propriété (conservation du total) est dans `test_cofinancement.py` ; ici, la clé
telle que la base la garde et telle que les écritures la citent.
"""

import datetime
import random
import uuid
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from niveau1_socle.comptabilite.models import LigneEcriture
from niveau1_socle.comptabilite.services import (
    comptabiliser_ecriture,
    contre_passer,
    saisir_ecriture,
    valider_ecriture,
)
from niveau1_socle.financements.cles import (
    CleInvalide,
    creer_cle,
    creer_version_cle,
    lignes_ventilees,
    ventiler_montant,
    version_en_vigueur,
)
from niveau1_socle.financements.models import Accord, CleCofinancement, PartCle, VersionCle
from niveau1_socle.financements.services import changer_statut_accord
from tests.outils import connexion_proprietaire
from tests.test_cycle_ecriture_bd import _creer_projet, _poser, decor  # noqa: F401
from tests.test_financements_bd import _accord, _activer, cadre  # noqa: F401
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
D = Decimal
JAN = datetime.date(2026, 1, 1)


@pytest.fixture
def cles(cadre):  # noqa: F811
    """Trois accords actifs du même bailleur sur le projet, et une clé « CHARGES »."""
    organisation, projet, profils, bailleur = cadre
    accords = {
        nom: _activer(_accord(projet, profils, bailleur, nom), profils)
        for nom in ("IDA", "GOV", "UE")
    }
    cle = creer_cle(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code="CHARGES",
        label={"fr": "Charges communes"},
    )
    return organisation, projet, profils, accords, cle


def _version(profils, cle, accords, poids, porteur="GOV", debut=JAN, motif=""):
    return creer_version_cle(
        utilisateur=profils["dora"],
        cle=cle,
        poids={accords[nom]: p for nom, p in poids.items()},
        porteur=accords[porteur],
        valid_from=debut,
        motif=motif,
    )


def _accord_etranger(organisation, projet, bailleur):
    """Un accord d'un AUTRE projet de l'organisation (créé hors service, sans habilitation)."""
    return Accord.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        bailleur=bailleur,
        numero="ETR",
        nature="don",
        devise_id="USD",
        montant_initial=1,
    )


# --- la clé telle que la base la garde ------------------------------------------------------


def test_les_parts_stockees_somment_exactement_a_un_la_derniere_par_difference(cles):
    _, _, profils, accords, cle = cles
    # Ordre d'entrée volontairement désordonné : le résultat ne doit pas en dépendre.
    version = _version(profils, cle, accords, {"UE": 1, "IDA": 1, "GOV": 1})
    parts = {p.accord.numero: p.share for p in version.parts.select_related("accord")}
    assert sorted(parts.values()) == [D("0.3333333333"), D("0.3333333333"), D("0.3333333334")]
    assert sum(parts.values()) == D(1)
    assert parts["UE"] == D("0.3333333334")  # accords triés par numéro : le dernier absorbe


def test_ventiler_un_montant_dans_la_devise_conserve_le_total(cles):
    _, _, profils, accords, cle = cles
    version = _version(profils, cle, accords, {"IDA": 60, "GOV": 30, "UE": 10})
    # Franc de Djibouti : pas de décimale, le reliquat va au porteur (GOV).
    djf = {a.numero: m for a, m in ventiler_montant(version, "1001", "DJF")}
    assert djf == {"GOV": D("301"), "IDA": D("600"), "UE": D("100")}
    assert sum(djf.values()) == D(1001)
    usd = {a.numero: m for a, m in ventiler_montant(version, "100.01", "USD")}
    assert sum(usd.values()) == D("100.01") and usd["IDA"] == D("60.00")
    # Le montant doit être exprimable dans la devise.
    with pytest.raises(ValueError, match="multiple du pas"):
        ventiler_montant(version, "100.5", "DJF")


def test_mille_ventilations_aleatoires_sur_une_cle_stockee_conservent_le_total(cles):
    _, _, profils, accords, cle = cles
    hasard = random.Random(7)
    for devise in ("DJF", "USD"):
        version = _version(
            profils,
            cle,
            accords,
            {
                "IDA": hasard.randint(1, 99),
                "GOV": hasard.randint(1, 99),
                "UE": hasard.randint(1, 99),
            },
            porteur=hasard.choice(["IDA", "GOV", "UE"]),
            debut=datetime.date(2026 if devise == "DJF" else 2027, 1, 1),
        )
        for _ in range(500):
            montant = D(hasard.randint(1, 10**9)) / (1 if devise == "DJF" else 100)
            assert sum(m for _, m in ventiler_montant(version, montant, devise)) == montant


def test_changer_de_cle_clot_la_version_en_cours_et_en_ouvre_une_autre(cles):
    _, _, profils, accords, cle = cles
    v1 = _version(profils, cle, accords, {"IDA": 70, "GOV": 30}, debut=datetime.date(2026, 1, 1))
    v2 = _version(
        profils,
        cle,
        accords,
        {"IDA": 50, "GOV": 50},
        debut=datetime.date(2026, 7, 1),
        motif="Avenant 1",
    )
    v1.refresh_from_db()
    assert (v1.version, v2.version, v1.valid_to) == (1, 2, datetime.date(2026, 7, 1))
    assert version_en_vigueur(cle, datetime.date(2026, 6, 30)).pk == v1.pk
    assert version_en_vigueur(cle, datetime.date(2026, 7, 1)).pk == v2.pk
    assert version_en_vigueur(cle, datetime.date(2025, 12, 31)) is None
    with pytest.raises(CleInvalide, match="après le 2026-07-01"):
        _version(profils, cle, accords, {"IDA": 1, "GOV": 1}, debut=datetime.date(2026, 7, 1))


def test_une_version_de_cle_est_refusee_si_elle_est_incoherente(cles):
    organisation, projet, profils, accords, cle = cles
    with pytest.raises(CleInvalide, match="porteur"):
        creer_version_cle(
            utilisateur=profils["dora"],
            cle=cle,
            poids={accords["IDA"]: 1},
            porteur=accords["GOV"],
            valid_from=JAN,
        )
    with pytest.raises(CleInvalide, match="au moins une part"):
        creer_version_cle(
            utilisateur=profils["dora"], cle=cle, poids={}, porteur=accords["GOV"], valid_from=JAN
        )
    with pytest.raises(PermissionDenied):
        creer_version_cle(
            utilisateur=profils["amina"],
            cle=cle,
            poids={accords["IDA"]: 1},
            porteur=accords["IDA"],
            valid_from=JAN,
        )
    changer_statut_accord(accords["UE"], "clos", utilisateur=profils["dora"], motif="Fin")
    with pytest.raises(CleInvalide, match="clos"):
        _version(profils, cle, accords, {"IDA": 1, "UE": 1}, porteur="IDA")
    autre_projet = _creer_projet(organisation, "P2")
    etranger = _accord_etranger(organisation, autre_projet, accords["IDA"].bailleur)
    with pytest.raises(CleInvalide, match="n'appartient pas au projet"):
        creer_version_cle(
            utilisateur=profils["dora"],
            cle=cle,
            poids={accords["IDA"]: 1, etranger: 1},
            porteur=accords["IDA"],
            valid_from=JAN,
        )
    assert VersionCle.objects.count() == 0


def test_la_base_refuse_des_parts_qui_ne_somment_pas_exactement_a_un(cles):
    organisation, projet, profils, accords, cle = cles
    base_version = (
        "INSERT INTO financements_versioncle (id, created_at, updated_at, org_id, cle_id, version, "
        "valid_from, rounding_residual_agreement_id, motif) "
        "VALUES (%s, now(), now(), %s, %s, 1, '2026-01-01', %s, '')"
    )
    base_part = (
        "INSERT INTO financements_partcle (id, created_at, updated_at, org_id, version_id, "
        "accord_id, share) VALUES (gen_random_uuid(), now(), now(), %s, %s, %s, %s)"
    )
    for parts, porteur, message in [
        ([("IDA", "0.6"), ("GOV", "0.4000000001")], "IDA", "sommer exactement à 1"),
        ([("IDA", "0.6"), ("GOV", "0.3999999999")], "IDA", "sommer exactement à 1"),
        ([("IDA", "1")], "GOV", "porteur d'arrondi"),
    ]:
        with connexion_proprietaire() as admin:
            admin.autocommit = False
            vid = uuid.uuid4()
            admin.execute(base_version, [vid, organisation.id, cle.pk, accords[porteur].pk])
            for nom, part in parts:
                admin.execute(base_part, [organisation.id, vid, accords[nom].pk, part])
            with pytest.raises(Exception, match=message):
                admin.commit()  # contrainte différée : vérifiée au COMMIT
    with connexion_proprietaire() as admin:  # une version sans aucune part
        admin.autocommit = False
        admin.execute(base_version, [uuid.uuid4(), organisation.id, cle.pk, accords["IDA"].pk])
        with pytest.raises(Exception, match="au moins une part"):
            admin.commit()
    assert VersionCle.objects.count() == 0


def test_la_base_refuse_un_accord_d_un_autre_projet_dans_une_cle(cles):
    organisation, projet, profils, accords, cle = cles
    autre_projet = _creer_projet(organisation, "P2")
    etranger = _accord_etranger(organisation, autre_projet, accords["IDA"].bailleur)
    with connexion_proprietaire() as admin:
        admin.autocommit = False
        vid = uuid.uuid4()
        admin.execute(
            "INSERT INTO financements_versioncle (id, created_at, updated_at, org_id, cle_id, "
            "version, valid_from, rounding_residual_agreement_id, motif) "
            "VALUES (%s, now(), now(), %s, %s, 1, '2026-01-01', %s, '')",
            [vid, organisation.id, cle.pk, accords["IDA"].pk],
        )
        for accord, part in ((accords["IDA"], "0.5"), (etranger, "0.5")):
            admin.execute(
                "INSERT INTO financements_partcle (id, created_at, updated_at, org_id, version_id, "
                "accord_id, share) VALUES (gen_random_uuid(), now(), now(), %s, %s, %s, %s)",
                [organisation.id, vid, accord.pk, part],
            )
        with pytest.raises(Exception, match="projet de la clé"):
            admin.commit()


def test_deux_versions_d_une_meme_cle_ne_se_chevauchent_pas(cles):
    organisation, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 1, "GOV": 1}, debut=datetime.date(2026, 1, 1))
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="chevauchement"):
            admin.execute(
                "INSERT INTO financements_versioncle (id, created_at, updated_at, org_id, cle_id, "
                "version, valid_from, rounding_residual_agreement_id, motif) "
                "VALUES (gen_random_uuid(), now(), now(), %s, %s, 9, '2026-03-01', %s, '')",
                [organisation.id, cle.pk, accords["IDA"].pk],
            )


# --- les lignes produites citent la version de clé ----------------------------------------


def _charge(projet, profils, version, montant, devise="DJF", date=datetime.date(2026, 3, 10)):
    lignes = lignes_ventilees(version, montant=montant, devise=devise, compte="6011")
    lignes.append({"compte": "5211", "credit": str(montant)})
    return saisir_ecriture(
        utilisateur=profils["amina"],
        project_id=projet.id,
        journal="OD",
        date_comptable=date,
        libelle="Charge commune",
        lignes=lignes,
        devise=devise,
    )


def test_chaque_ligne_produite_porte_son_accord_et_la_version_de_cle(cles):
    organisation, projet, profils, accords, cle = cles
    version = _version(profils, cle, accords, {"IDA": 60, "GOV": 30, "UE": 10})
    ecriture = _charge(projet, profils, version, "1001")
    charges = ecriture.lignes.filter(account__code="6011")
    assert {ligne.agreement_id: ligne.debit for ligne in charges} == {
        accords["IDA"].pk: D(600),
        accords["GOV"].pk: D(301),
        accords["UE"].pk: D(100),
    }
    assert {ligne.cofunding_key_version_id for ligne in charges} == {version.pk}
    assert ecriture.lignes.get(account__code="5211").cofunding_key_version_id is None
    assert sum(ligne.debit for ligne in charges) == D(1001)  # le total est celui de la dépense

    valider_ecriture(ecriture, utilisateur=profils["bruno"])
    posee = comptabiliser_ecriture(ecriture, utilisateur=profils["claire"])
    assert posee.status == "posted"


def test_une_part_nulle_ne_produit_pas_de_ligne_mais_le_total_reste_conserve(cles):
    _, projet, profils, accords, cle = cles
    version = _version(profils, cle, accords, {"IDA": 99, "GOV": 1, "UE": 1}, porteur="IDA")
    lignes = lignes_ventilees(version, montant="1", devise="DJF", compte="6011")
    assert [(ligne["agreement_id"], ligne["debit"]) for ligne in lignes] == [
        (accords["IDA"].pk, "1")
    ]


def test_modifier_la_cle_rend_pas_l_historique_inexplicable(cles):
    organisation, projet, profils, accords, cle = cles
    v1 = _version(profils, cle, accords, {"IDA": 70, "GOV": 30}, debut=datetime.date(2026, 1, 1))
    mars = _charge(projet, profils, v1, "1000", date=datetime.date(2026, 3, 10))
    v2 = _version(profils, cle, accords, {"IDA": 50, "GOV": 50}, debut=datetime.date(2026, 7, 1))
    aout = _charge(projet, profils, v2, "1000", date=datetime.date(2026, 8, 10))
    assert {
        ligne.cofunding_key_version_id for ligne in mars.lignes.filter(account__code="6011")
    } == {v1.pk}
    assert {
        ligne.cofunding_key_version_id for ligne in aout.lignes.filter(account__code="6011")
    } == {v2.pk}
    # Chaque ligne se réexplique avec les parts de SA version, pas celles d'aujourd'hui.
    for ecriture, version in ((mars, v1), (aout, v2)):
        parts = {p.accord_id: p.share for p in version.parts.all()}
        for ligne in ecriture.lignes.filter(account__code="6011"):
            assert ligne.debit == (D(1000) * parts[ligne.agreement_id]).quantize(D(1))
    assert verifier_chaine(organisation.id) is None


def test_la_contrepassation_garde_la_reference_a_la_version_de_cle(cles):
    organisation, projet, profils, accords, cle = cles
    version = _version(profils, cle, accords, {"IDA": 60, "GOV": 40})
    ecriture = _charge(projet, profils, version, "500")
    valider_ecriture(ecriture, utilisateur=profils["bruno"])
    comptabiliser_ecriture(ecriture, utilisateur=profils["claire"])
    inverse = contre_passer(ecriture, utilisateur=profils["amina"])
    assert {
        ligne.cofunding_key_version_id for ligne in inverse.lignes.filter(account__code="6011")
    } == {version.pk}
    valider_ecriture(inverse, utilisateur=profils["bruno"])  # le miroir exact inclut la clé


def test_une_version_utilisee_ne_change_plus_ni_ses_parts_ni_ne_se_supprime(cles):
    organisation, projet, profils, accords, cle = cles
    version = _version(profils, cle, accords, {"IDA": 60, "GOV": 40})
    libre = _version(profils, cle, accords, {"IDA": 1, "GOV": 1}, debut=datetime.date(2027, 1, 1))
    _charge(projet, profils, version, "500")
    part = version.parts.first()
    with connexion_proprietaire() as admin:
        for requete, params in [
            ("UPDATE financements_partcle SET share = 0.5 WHERE id = %s", [part.pk]),
            ("DELETE FROM financements_partcle WHERE id = %s", [part.pk]),
            ("UPDATE financements_versioncle SET motif = 'x' WHERE id = %s", [version.pk]),
            ("DELETE FROM financements_versioncle WHERE id = %s", [version.pk]),
        ]:
            with pytest.raises(Exception, match="utilisée par des écritures"):
                admin.execute(requete, params)
        # La clôture de sa validité reste permise ; une version inutilisée n'est pas figée.
        admin.execute("UPDATE financements_versioncle SET motif = 'ok' WHERE id = %s", [libre.pk])
    assert PartCle.objects.filter(version=version).count() == 2


def test_une_ligne_ne_peut_citer_qu_une_version_de_cle_de_son_organisation(cles):
    organisation, projet, profils, accords, cle = cles
    ecriture = _charge(projet, profils, _version(profils, cle, accords, {"IDA": 1, "GOV": 1}), "10")
    ligne = ecriture.lignes.filter(account__code="6011").first()
    with pytest.raises(IntegrityError, match="fk_ligne_version_cle"), transaction.atomic():
        LigneEcriture.objects.filter(pk=ligne.pk).update(cofunding_key_version_id=uuid.uuid4())


def test_les_cles_sont_isolees_par_organisation(cles):
    organisation, projet, profils, accords, cle = cles
    _version(profils, cle, accords, {"IDA": 1, "GOV": 1})
    autre = _creer_organisation("ORG-B")
    _poser(autre)
    for modele in (CleCofinancement, VersionCle, PartCle):
        assert modele.objects.count() == 0, modele
