import uuid

import pytest
from django.db import connection

ORG_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
ORG_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def org_a():
    return ORG_A


@pytest.fixture
def org_b():
    return ORG_B


@pytest.fixture
def poser_org():
    """Pose app.org_id, comme le fait le middleware pour une vraie requête."""

    def _poser(org_id):
        with connection.cursor() as cur:
            cur.execute("SET LOCAL app.org_id = %s", [str(org_id)])

    return _poser


@pytest.fixture
def devises_referentiel():
    """Recharge le référentiel des devises.

    Les tests en `transaction=True` vident toutes les tables après chaque test, y
    compris les données posées par migration. Le référentiel est en lecture
    seule pour l'application : on lève donc, le temps de la recharge, le
    verrou que les migrations lèvent aussi.
    """
    from django.db import transaction

    from niveau1_socle.referentiels.models import Devise
    from niveau1_socle.referentiels.semences import charger

    if not Devise.objects.exists():
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute("SET LOCAL sigf.ecriture_referentiel = 'on'")
            charger(Devise)
