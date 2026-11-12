"""Versionnement, exhaustivité et isolation du mapping. Voir L0-T04."""

import datetime
import uuid

import pytest
from django.db import connection
from django.utils import timezone

from niveau4_reporting.mapping.models import RegleMapping, TableMapping
from niveau4_reporting.mapping.resolveur import (
    MappingIncomplet,
    MappingIndisponible,
    comptes_non_mappes,
    construire_cas_sql,
    table_active,
    verifier_exhaustivite,
)
from tests.outils import creer_ligne

pytestmark = pytest.mark.django_db(transaction=True)
DATE_REFERENCE = datetime.date(2026, 3, 31)
DONOR_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
PROJECT_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")


def _poser_org(org_id):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])


def _table(
    org_id,
    *,
    version=1,
    status="active",
    valid_from=datetime.date(2026, 1, 1),
    valid_to=None,
):
    return TableMapping.objects.create(
        org_id=org_id,
        project_id=PROJECT_ID,
        donor_profile_id=DONOR_ID,
        code="WB-TER",
        version=version,
        valid_from=valid_from,
        valid_to=valid_to,
        status=status,
        validated_by=uuid.uuid4() if status in {"validated", "active"} else None,
        validated_at=timezone.now() if status in {"validated", "active"} else None,
    )


def _regle(table, priority, match, target_code="R100"):
    return RegleMapping.objects.create(
        org_id=table.org_id,
        table=table,
        priority=priority,
        match=match,
        target_code=target_code,
    )


def _ligne(org_id, compte, *, debit="100.0000", dim1="COMP-A"):
    return creer_ligne(
        org_id,
        compte,
        2026,
        1,
        debit=debit,
        accord="IDA-6789",
        categorie="CAT-1",
        site="SIEGE",
        dim1=dim1,
    )


def _periode():
    return {
        "project_id": PROJECT_ID,
        "fiscal_year": 2026,
        "period_from": 1,
        "period_to": 3,
        "date_effet": DATE_REFERENCE,
    }


def test_la_premiere_regle_qui_correspond_gagne(org_a):
    _poser_org(org_a)
    table = _table(org_a)
    _regle(table, 100, {"accounts": [["6000", "6999"]]}, "R_GENERAL")
    _regle(table, 10, {"accounts": [["6011", "6011"]], "dim1": ["COMP-A"]}, "R_PRECIS")
    _ligne(org_a, "6011", dim1="COMP-A")
    _ligne(org_a, "6011", dim1="COMP-B")
    cas, params = construire_cas_sql(table.regles.all())

    with connection.cursor() as cur:
        cur.execute(
            f"SELECT dim1, {cas} FROM moteur_ligneecriture ORDER BY dim1",
            params,
        )
        assert cur.fetchall() == [("COMP-A", "R_PRECIS"), ("COMP-B", "R_GENERAL")]


def test_la_version_active_est_celle_applicable_a_la_date(org_a):
    _poser_org(org_a)
    v1 = _table(org_a, version=1, valid_from=datetime.date(2025, 1, 1))
    v2 = _table(org_a, version=2, valid_from=datetime.date(2026, 1, 1))
    _table(org_a, version=3, status="draft", valid_from=datetime.date(2024, 1, 1))

    commun = {"code": "WB-TER", "donor_profile_id": DONOR_ID, "project_id": PROJECT_ID}
    assert table_active(**commun, date_effet=datetime.date(2025, 6, 30)) == v1
    assert table_active(**commun, date_effet=DATE_REFERENCE) == v2
    with pytest.raises(MappingIndisponible):
        table_active(**commun, date_effet=datetime.date(2024, 12, 31))


def test_la_fin_de_validite_est_exclue_et_les_versions_se_succedent_sans_trou(org_a):
    """Intervalle semi-ouvert [valid_from, valid_to[ : guide §B.6.

    V1 couvre toute l'année 2025 (fin = 1er janvier 2026, exclu) ; V2 commence
    le 1er janvier 2026. Le 1er janvier 2026 appartient à V2 et à elle seule.
    """
    _poser_org(org_a)
    v1 = _table(
        org_a,
        version=1,
        valid_from=datetime.date(2025, 1, 1),
        valid_to=datetime.date(2026, 1, 1),
    )
    v2 = _table(org_a, version=2, valid_from=datetime.date(2026, 1, 1))

    commun = {"code": "WB-TER", "donor_profile_id": DONOR_ID, "project_id": PROJECT_ID}
    assert table_active(**commun, date_effet=datetime.date(2025, 12, 31)) == v1
    assert table_active(**commun, date_effet=datetime.date(2026, 1, 1)) == v2


def test_une_version_close_nest_plus_applicable_a_sa_date_de_fin(org_a):
    _poser_org(org_a)
    table = _table(
        org_a,
        valid_from=datetime.date(2025, 1, 1),
        valid_to=datetime.date(2026, 1, 1),
    )
    commun = {"code": "WB-TER", "donor_profile_id": DONOR_ID, "project_id": PROJECT_ID}
    with pytest.raises(MappingIndisponible):
        table_active(**commun, date_effet=datetime.date(2026, 1, 1))
    with pytest.raises(MappingIndisponible):
        comptes_non_mappes(
            table,
            {
                "project_id": PROJECT_ID,
                "fiscal_year": 2026,
                "date_effet": datetime.date(2026, 1, 1),
            },
        )


def test_un_intervalle_de_validite_vide_est_refuse(org_a):
    """valid_to == valid_from ne couvre aucun jour : refusé par la base."""
    from django.db import IntegrityError

    _poser_org(org_a)
    with pytest.raises(IntegrityError):
        _table(
            org_a,
            valid_from=datetime.date(2026, 1, 1),
            valid_to=datetime.date(2026, 1, 1),
        )


def test_un_compte_mouvemente_non_couvert_est_nomme(org_a):
    _poser_org(org_a)
    table = _table(org_a)
    _regle(table, 10, {"accounts": [["6000", "6279"]]})
    _ligne(org_a, "6011")
    _ligne(org_a, "6281")
    _ligne(org_a, "9999", debit="0.0000")

    assert comptes_non_mappes(table, _periode()) == ["6281"]
    with pytest.raises(MappingIncomplet, match="6281") as erreur:
        verifier_exhaustivite(table, _periode())
    assert erreur.value.comptes == ("6281",)


def test_lexhaustivite_tient_compte_des_axes_pas_seulement_du_compte(org_a):
    _poser_org(org_a)
    table = _table(org_a)
    _regle(table, 10, {"accounts": [["6281", "6281"]], "dim1": ["COMP-A"]})
    _ligne(org_a, "6281", dim1="COMP-A")
    _ligne(org_a, "6281", dim1="COMP-B")

    assert comptes_non_mappes(table, _periode()) == ["6281"]

    _regle(table, 20, {"accounts": [["6281", "6281"]], "dim1": ["COMP-B"]})
    verifier_exhaustivite(table, _periode())
    assert comptes_non_mappes(table, _periode()) == []


def test_une_table_dune_autre_organisation_est_invisible(org_a, org_b):
    _poser_org(org_b)
    _table(org_b)
    _poser_org(org_a)

    with pytest.raises(MappingIndisponible):
        table_active(
            code="WB-TER",
            donor_profile_id=DONOR_ID,
            project_id=PROJECT_ID,
            date_effet=DATE_REFERENCE,
        )
