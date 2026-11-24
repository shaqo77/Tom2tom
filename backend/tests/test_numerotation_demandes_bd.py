"""Revue L11 (constat 4) : la numérotation d'une demande de retrait est sérialisée.

`count() + 1` lu puis écrit sans verrou donne le même numéro à deux demandes préparées en même
temps ; l'une échouait alors sur la contrainte d'unicité. Le numéro se prend sous un verrou
consultatif de l'accord, comme celui des rapprochements.
"""

import pytest
from django.db import connection, transaction

from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import _depense, _preparer, drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def _verrou_pris(cle: str) -> bool:
    """La session courante tient-elle le verrou consultatif de cette clé ?"""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_locks, (SELECT hashtextextended(%s, 0) AS h) k "
            "WHERE locktype = 'advisory' AND pid = pg_backend_pid() AND granted "
            "AND classid = ((k.h >> 32) & 4294967295)::oid "
            "AND objid = (k.h & 4294967295)::oid",
            [cle],
        )
        return cur.fetchone()[0] > 0


def test_preparer_une_demande_prend_un_verrou_sur_l_accord_avant_de_numeroter(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    depense = _depense(organisation, projet, accord, cat["serv"], 50)
    cle = f"demande_retrait:{accord.pk}"
    with transaction.atomic():
        assert not _verrou_pris(cle)
        demande = _preparer(profils, accord, [depense])
        assert _verrou_pris(cle)
    assert demande.numero == "DRF-DON-1-001"


def test_les_numeros_se_suivent_sans_trou_ni_doublon(drf):  # noqa: F811
    organisation, projet, profils, accord, cat = drf
    numeros = []
    for _ in range(3):
        depense = _depense(organisation, projet, accord, cat["serv"], 10)
        numeros.append(_preparer(profils, accord, [depense]).numero)
    assert numeros == ["DRF-DON-1-001", "DRF-DON-1-002", "DRF-DON-1-003"]
