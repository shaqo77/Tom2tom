"""Exercices et périodes : calendrier, clôture, verrouillage. Voir L1-T04.

Le contrôle « une période close refuse l'ouverture d'une écriture » est une
contrainte du grand livre : il est posé et testé en L3-T03. Ici, on prouve que
la période close existe, qu'elle est irréversible une fois verrouillée, et que
la clôture refuse tant qu'un contrôle de clôture signale des écritures en
brouillon (le contrôle réel est enregistré par L3).
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction

from core.audit import verifier_chaine
from niveau1_socle.exercices import services
from niveau1_socle.exercices.models import Exercice, Periode
from niveau1_socle.exercices.services import (
    ClotureImpossible,
    TransitionInterdite,
    cloturer_periode,
    creer_exercice,
    verrouiller_periode,
)
from tests.test_organisations_bd import _creer_organisation, _creer_projet

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()


def _poser(org_id):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(org_id)])


@pytest.fixture
def decor():
    organisation = _creer_organisation("ORG-A")
    projet = _creer_projet(organisation, "P1")
    amina = Utilisateur.objects.create_user("amina", password="x", org_id=organisation.id)
    _poser(organisation.id)
    return organisation, projet, amina


@pytest.fixture(autouse=True)
def _verifications_isolees():
    """Chaque test part d'un registre de contrôles de clôture vide."""
    avant = list(services.VERIFICATIONS_DE_CLOTURE)
    services.VERIFICATIONS_DE_CLOTURE.clear()
    yield
    services.VERIFICATIONS_DE_CLOTURE[:] = avant


def test_un_exercice_porte_douze_periodes_contigues_et_ouvertes(decor):
    organisation, projet, amina = decor
    exercice = creer_exercice(projet, 2028, utilisateur=amina)  # 2028 est bissextile

    periodes = list(exercice.periodes.order_by("numero"))
    assert [p.numero for p in periodes] == list(range(1, 13))
    assert periodes[0].date_debut == datetime.date(2028, 1, 1)
    assert periodes[1].date_fin == datetime.date(2028, 2, 29)
    assert periodes[11].date_fin == datetime.date(2028, 12, 31)
    assert all(
        precedente.date_fin + datetime.timedelta(days=1) == suivante.date_debut
        for precedente, suivante in zip(periodes, periodes[1:], strict=False)
    )
    assert {p.status for p in periodes} == {"ouverte"}
    assert exercice.status == "ouvert"


def test_deux_exercices_dun_meme_projet_ne_se_chevauchent_pas(decor):
    """Garanti par la base (contrainte d'exclusion), pas par le service."""
    organisation, projet, amina = decor
    creer_exercice(projet, 2026, utilisateur=amina)
    with pytest.raises(IntegrityError), transaction.atomic():
        Exercice.objects.create(
            org_id=organisation.id,
            project_id=projet.id,
            annee=2099,
            date_debut=datetime.date(2026, 6, 1),
            date_fin=datetime.date(2027, 5, 31),
        )
    creer_exercice(projet, 2027, utilisateur=amina)  # contigu : accepté


def test_les_memes_dates_existent_dans_un_autre_projet_et_une_autre_organisation(decor):
    organisation, projet, amina = decor
    autre_projet = _creer_projet(organisation, "P2")
    _poser(organisation.id)
    creer_exercice(projet, 2026, utilisateur=amina)
    creer_exercice(autre_projet, 2026, utilisateur=amina)

    autre = _creer_organisation("ORG-B")
    projet_b = _creer_projet(autre, "P1")
    _poser(autre.id)
    creer_exercice(projet_b, 2026, utilisateur=None)


def test_cloturer_une_periode_la_ferme_et_journalise_la_decision(decor):
    organisation, projet, amina = decor
    exercice = creer_exercice(projet, 2026, utilisateur=amina)
    periode = exercice.periodes.get(numero=1)

    cloturer_periode(periode, utilisateur=amina)

    periode.refresh_from_db()
    assert periode.status == "close"
    with connection.cursor() as cur:
        cur.execute(
            "SELECT action, object_type, actor_id FROM core_auditlog "
            "WHERE object_id = %s ORDER BY id",
            [str(periode.id)],
        )
        assert cur.fetchall() == [("period_closed", "periode", amina.id)]
    assert verifier_chaine(organisation.id) is None


def test_la_cloture_refuse_tant_quun_controle_signale_des_ecritures_en_brouillon(decor):
    organisation, projet, amina = decor
    periode = creer_exercice(projet, 2026, utilisateur=amina).periodes.get(numero=1)
    services.VERIFICATIONS_DE_CLOTURE.append(
        lambda p: "3 écritures en brouillon" if p.numero == 1 else None
    )

    with pytest.raises(ClotureImpossible, match="3 écritures en brouillon") as erreur:
        cloturer_periode(periode, utilisateur=amina)

    assert erreur.value.raisons == ["3 écritures en brouillon"]
    periode.refresh_from_db()
    assert periode.status == "ouverte"
    # La période 2, sans brouillon, se clôture.
    cloturer_periode(periode.exercice.periodes.get(numero=2), utilisateur=amina)


def test_une_periode_close_ne_se_cloture_pas_deux_fois(decor):
    organisation, projet, amina = decor
    periode = creer_exercice(projet, 2026, utilisateur=amina).periodes.get(numero=1)
    cloturer_periode(periode, utilisateur=amina)
    with pytest.raises(TransitionInterdite):
        cloturer_periode(periode, utilisateur=amina)


def test_on_ne_verrouille_que_ce_qui_est_close_et_le_verrou_est_definitif(decor):
    organisation, projet, amina = decor
    periode = creer_exercice(projet, 2026, utilisateur=amina).periodes.get(numero=1)
    with pytest.raises(TransitionInterdite):
        verrouiller_periode(periode, utilisateur=amina)  # encore ouverte

    cloturer_periode(periode, utilisateur=amina)
    verrouiller_periode(periode, utilisateur=amina)
    periode.refresh_from_db()
    assert periode.status == "verrouillee"

    # Le verrou tient même contre un SQL direct : c'est la base qui le garantit.
    for statut in ("ouverte", "close"):
        with pytest.raises(IntegrityError, match="verrouillée"), transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE exercices_periode SET status = %s WHERE id = %s",
                    [statut, periode.id],
                )


def test_la_base_refuse_de_verrouiller_une_periode_ouverte_en_sql_direct(decor):
    organisation, projet, amina = decor
    periode = creer_exercice(projet, 2026, utilisateur=amina).periodes.get(numero=1)
    with pytest.raises(IntegrityError, match="close"), transaction.atomic():
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE exercices_periode SET status = 'verrouillee' WHERE id = %s",
                [periode.id],
            )


@pytest.mark.parametrize(
    "champs",
    [
        {"numero": 13},
        {"numero": 0},
        {"status": "suspendue"},
        {"date_fin": datetime.date(2025, 12, 31)},  # avant le début
    ],
)
def test_les_ensembles_fermes_et_les_bornes_des_periodes_sont_contraints_en_base(decor, champs):
    organisation, projet, amina = decor
    exercice = creer_exercice(projet, 2026, utilisateur=amina)
    donnees = {
        "org_id": organisation.id,
        "exercice": exercice,
        "numero": 99,
        "date_debut": datetime.date(2026, 1, 1),
        "date_fin": datetime.date(2026, 1, 31),
        "status": "ouverte",
    }
    donnees.update(champs)
    if "numero" not in champs:
        donnees["numero"] = 5  # un numéro valide et libre : seul le champ testé est fautif
        Periode.objects.filter(exercice=exercice, numero=5).delete()
    with pytest.raises(IntegrityError), transaction.atomic():
        Periode.objects.create(**donnees)


def test_un_exercice_est_isole_par_organisation(decor):
    organisation, projet, amina = decor
    creer_exercice(projet, 2026, utilisateur=amina)
    _creer_organisation("ORG-B")  # pose le périmètre de B
    assert Exercice.objects.count() == 0
    assert Periode.objects.count() == 0
