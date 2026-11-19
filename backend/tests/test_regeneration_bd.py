"""Publication scellée et régénération par différentiel. Voir L6-T04.

Contrôle du plan : publier un rapport, ajouter une écriture dans la période, régénérer : le
différentiel NOMME l'écriture ajoutée et son montant. Plus : l'identique reste identique, un modèle
ou un mapping postérieur ne change pas le rejeu, un rapport publié ne se modifie pas, une assertion
fausse bloque la publication.
"""

import datetime
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from niveau1_socle.habilitations.models import Habilitation, Role
from niveau4_reporting.mapping.models import RegleMapping, TableMapping
from niveau4_reporting.moteur.assertions import AssertionsViolees
from niveau4_reporting.publication.models import RapportPublie
from niveau4_reporting.publication.rapports import (
    comparer_valeurs,
    publier_rapport,
    regenerer,
)
from tests.outils import connexion_proprietaire, creer_piece
from tests.test_cycle_ecriture_bd import decor  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = Decimal
DONOR = uuid.UUID("33333333-3333-3333-3333-333333333333")
MODELE = {
    "code": "TER",
    "version": 3,
    "columns": [
        {"code": "QTR", "period": "current_quarter"},
        {"code": "YTD", "period": "year_to_date"},
    ],
    "rows": [
        {"code": "T100", "type": "heading"},
        {"code": "R110", "type": "aggregate", "select": {"mapping": "WB", "target": "CHARGES"}},
        {"code": "R120", "type": "aggregate", "select": {"mapping": "WB", "target": "TRESORERIE"}},
        {"code": "R190", "type": "computed", "formula": "R110 + R120"},
    ],
}


@pytest.fixture
def pub(decor):  # noqa: F811
    organisation, projet, profils = decor
    u = Utilisateur.objects.create_user("pia", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id, code="PIA", label={"fr": "pia"}, operations=["consulter", "publier"]
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=u.id, project_id=projet.id, role=role
    )
    profils["pia"] = u
    table = _mapping(organisation, projet, version=1)
    for montant in ("100", "50.10"):
        _piece(organisation, projet, "6011", "5211", montant)
    return organisation, projet, profils, table


def _mapping(organisation, projet, version, valid_from=datetime.date(2026, 1, 1), valid_to=None):
    table = TableMapping.objects.create(
        org_id=organisation.id, project_id=projet.id, donor_profile_id=DONOR, code="WB",
        version=version, valid_from=valid_from, valid_to=valid_to, status="active",
        validated_by=uuid.uuid4(), validated_at=timezone.now(),
    )  # fmt: skip
    for priorite, comptes, cible in (
        (10, [["6000", "6279"]], "CHARGES"),
        (20, [["5200", "5299"]], "TRESORERIE"),
        (90, [["8999", "8999"]], "CONTREPARTIE"),
    ):
        RegleMapping.objects.create(
            org_id=organisation.id, table=table, priority=priorite,
            match={"accounts": comptes}, target_code=cible,
        )  # fmt: skip
    return table


def _piece(organisation, projet, debit, credit, montant, periode=2, **champs):
    return creer_piece(
        organisation.id, 2026, periode,
        [{"compte": debit, "debit": montant}, {"compte": credit, "credit": montant}],
        project_id=projet.id, **champs,
    )  # fmt: skip


def _publier(pub, **champs):
    organisation, projet, profils, table = pub
    donnees = {
        "utilisateur": profils["pia"],
        "project_id": projet.id,
        "modele": MODELE,
        "params": {"fiscal_year": 2026, "current_period": 3},
        "tables": {"WB": table},
        "period_from": datetime.date(2026, 1, 1),
        "period_to": datetime.date(2026, 3, 31),
        "config_version": {"profil": 4},
    } | champs
    return publier_rapport(**donnees)


def test_un_rapport_publie_se_rejoue_a_l_identique(pub):
    rapport = _publier(pub)
    assert len(bytes(rapport.seal)) == 32
    assert rapport.values["R110/QTR"] == "150.1"
    assert rapport.mapping_versions["WB"]["version"] == 1
    resultat = regenerer(rapport)
    assert resultat.identique and not resultat.ecarts and not resultat.causes


def test_une_ecriture_ajoutee_apres_la_publication_est_nommee_avec_son_montant(pub):
    organisation, projet, profils, table = pub
    rapport = _publier(pub)
    nouvelle = _piece(organisation, projet, "6011", "5211", "75.25")  # arrivée après la publication
    resultat = regenerer(rapport)
    assert not resultat.identique
    ecart = next(e for e in resultat.ecarts if (e.rubrique, e.colonne) == ("R110", "QTR"))
    assert (ecart.ancien, ecart.nouveau, ecart.difference) == (D("150.1"), D("225.35"), D("75.25"))
    # Elle est NOMMÉE : son numéro de pièce, son compte, son montant.
    cause = next(c for c in resultat.causes if c.compte == "6011")
    assert (cause.ecriture, cause.montant) == (nouvelle.number, D("75.25"))
    assert cause.contre_passation_de is None
    assert not resultat.inexpliquee
    assert {c.ecriture for c in resultat.causes} == {nouvelle.number}  # et elle seule


def test_une_contre_passation_posterieure_est_signalee_avec_la_piece_contre_passee(pub):
    organisation, projet, profils, table = pub
    origine = _piece(organisation, projet, "6011", "5211", "40")
    rapport = _publier(pub)
    contre = creer_piece(
        organisation.id, 2026, 2,
        [{"compte": "6011", "credit": "40"}, {"compte": "5211", "debit": "40"}],
        project_id=projet.id, reverses=origine,
    )  # fmt: skip
    resultat = regenerer(rapport)
    assert not resultat.identique
    cause = next(c for c in resultat.causes if c.compte == "6011")
    assert (cause.ecriture, cause.montant, cause.contre_passation_de) == (
        contre.number,
        D("-40"),
        origine.number,
    )
    ecart = next(e for e in resultat.ecarts if (e.rubrique, e.colonne) == ("R110", "YTD"))
    assert ecart.difference == D("-40")


def test_un_ecart_sans_ecriture_nouvelle_est_signale_comme_inexplique(pub):
    rapport = _publier(pub)
    with connexion_proprietaire() as proprietaire:  # un administrateur qui contourne la base
        proprietaire.execute("SET session_replication_role = replica")
        proprietaire.execute(
            "UPDATE comptabilite_ligneecriture SET debit = debit + 1 WHERE debit > 0 "
            "AND account_id = (SELECT id FROM referentiels_compte WHERE code = '6011' LIMIT 1) "
            "AND id = (SELECT id FROM comptabilite_ligneecriture WHERE debit > 0 AND account_id = "
            "(SELECT id FROM referentiels_compte WHERE code = '6011' LIMIT 1) LIMIT 1)"
        )
    resultat = regenerer(rapport)
    assert not resultat.identique and resultat.inexpliquee and resultat.causes == []


def test_un_mapping_postérieur_ne_change_pas_le_rejeu(pub):
    organisation, projet, profils, table = pub
    rapport = _publier(pub)
    TableMapping.objects.filter(pk=table.pk).update(
        valid_to=datetime.date(2026, 6, 1), status="superseded"
    )
    _mapping(organisation, projet, version=2, valid_from=datetime.date(2026, 6, 1))
    assert regenerer(rapport).identique  # le rejeu utilise la version D'ALORS


def test_un_rapport_publie_ne_se_modifie_ni_ne_se_supprime(pub):
    rapport = _publier(pub)
    with pytest.raises(IntegrityError), transaction.atomic():
        RapportPublie.objects.filter(pk=rapport.pk).update(values={"R110/QTR": "0"})
    with pytest.raises(IntegrityError), transaction.atomic():
        RapportPublie.objects.filter(pk=rapport.pk).delete()


def test_seul_un_publieur_habilite_publie(pub):
    organisation, projet, profils, table = pub
    with pytest.raises(PermissionDenied):
        _publier(pub, utilisateur=profils["amina"])
    assert RapportPublie.objects.count() == 0


def test_une_assertion_fausse_bloque_la_publication(pub):
    rows = [dict(r) for r in MODELE["rows"]]
    rows[3]["assert"] = "R190 == R110 + 1"  # volontairement fausse
    faux = {**MODELE, "rows": rows}
    with pytest.raises(AssertionsViolees):
        _publier(pub, modele=faux)
    assert RapportPublie.objects.count() == 0


def test_comparer_valeurs_voit_ajouts_retraits_et_modifications():
    ecarts = comparer_valeurs(
        {"A/Q": "1", "B/Q": "2", "C/Q": "3"}, {"A/Q": "1.0", "B/Q": "5", "D/Q": "4"}
    )
    assert [(e.rubrique, e.ancien, e.nouveau) for e in ecarts] == [
        ("B", D(2), D(5)),
        ("C", D(3), None),
        ("D", None, D(4)),
    ]
