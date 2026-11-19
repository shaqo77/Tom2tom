"""Le rattachement des objets de configuration à leurs exigences. Voir L5-T03.

La règle : tout objet de configuration actif a au moins une exigence source active. Un objet actif
sans exigence source est une anomalie de configuration, signalée par le système lui-même.
"""

import datetime
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from niveau3_config.models import Exigence, RattachementExigence
from niveau3_config.services import rattachement as module_rattachement
from niveau3_config.services.documents import enregistrer_document
from niveau3_config.services.exigences import proposer_exigence
from niveau3_config.services.rattachement import (
    ConfigurationOrpheline,
    RattachementInvalide,
    SourceCible,
    detecter_configuration_orpheline,
    enregistrer_cible,
    exiger_configuration_sans_orphelin,
    rattacher,
)
from niveau4_reporting.mapping.models import TableMapping
from tests.outils import connexion_proprietaire
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
DEBUT = datetime.date(2026, 1, 1)
PHRASE = (
    "Le rapport financier intermédiaire est remis dans les 45 jours suivant la fin du trimestre"
)


@pytest.fixture
def cadre_config(cadre, settings, tmp_path):  # noqa: F811
    settings.STOCKAGE_DOCUMENTS_ROOT = tmp_path
    organisation, projet, profils, _ = cadre
    document = enregistrer_document(
        utilisateur=profils["dora"],
        project_id=projet.id,
        kind="dfil",
        title="DFIL",
        version="1",
        contenu=PHRASE.encode(),
    )
    return organisation, projet, profils, document


def _exigence(cadre_config, code="IFR", *, statut="active", valid_from=DEBUT, valid_to=None):
    organisation, projet, profils, document = cadre_config
    exigence = proposer_exigence(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code=code,
        document=document,
        citation={"paragraph": "4.2", "quote": "remis dans les 45 jours"},
        subject=code,
        rule={},
        obligation="mandatory",
        valid_from=valid_from,
    )
    if statut in ("validated", "active"):
        Exigence.objects.filter(pk=exigence.pk).update(
            status=statut, validated_by=uuid.uuid4(), validated_at=timezone.now(), valid_to=valid_to
        )
    elif statut in ("superseded", "rejected"):
        Exigence.objects.filter(pk=exigence.pk).update(status=statut)
    exigence.refresh_from_db()
    return exigence


def _mapping(cadre_config, code="WB-TER", *, statut="active", projet=None, valid_to=None):
    organisation, projet_courant, profils, document = cadre_config
    return TableMapping.objects.create(
        org_id=organisation.id,
        project_id=(projet or projet_courant).id,
        donor_profile_id=uuid.uuid4(),
        code=code,
        version=1,
        valid_from=DEBUT,
        valid_to=valid_to,
        status=statut,
        **(
            {"validated_by": uuid.uuid4(), "validated_at": timezone.now()}
            if statut in ("validated", "active")
            else {}
        ),
    )


def _rattacher(cadre_config, exigence, mapping, type_="mapping"):
    return rattacher(
        utilisateur=cadre_config[2]["dora"],
        exigence=exigence,
        target_type=type_,
        target_id=mapping.pk,
    )


@pytest.fixture
def projet_configure(cadre_config):
    """Un projet dont toute la configuration active a son exigence source."""
    exigence = _exigence(cadre_config)
    mapping = _mapping(cadre_config)
    _rattacher(cadre_config, exigence, mapping)
    return cadre_config[1]


# --- le contrôle de la tâche ----------------------------------------------------------------


def test_aucun_objet_actif_sans_exigence_source(projet_configure):
    orphelins = detecter_configuration_orpheline(projet_configure.id, DEBUT)
    assert not orphelins, f"Configuration sans exigence source : {orphelins}"
    exiger_configuration_sans_orphelin(projet_configure.id, DEBUT)  # ne lève rien


def test_un_objet_actif_sans_rattachement_est_signale_par_le_systeme(cadre_config):
    organisation, projet, profils, _ = cadre_config
    mapping = _mapping(cadre_config)
    orphelins = detecter_configuration_orpheline(projet.id, DEBUT)
    assert [(o.target_type, o.target_id, o.libelle, str(o.raison)) for o in orphelins] == [
        ("mapping", mapping.pk, "WB-TER v1", "aucun rattachement")
    ]
    with pytest.raises(ConfigurationOrpheline, match="mapping WB-TER v1 \\(aucun rattachement\\)"):
        exiger_configuration_sans_orphelin(projet.id, DEBUT)


# --- ce qui justifie, ce qui ne justifie pas ----------------------------------------------


@pytest.mark.parametrize("statut", ["proposed", "validated"])
def test_une_exigence_non_active_ne_justifie_pas_un_objet_actif(cadre_config, statut):
    mapping = _mapping(cadre_config)
    _rattacher(cadre_config, _exigence(cadre_config, statut=statut), mapping)
    (orphelin,) = detecter_configuration_orpheline(cadre_config[1].id, DEBUT)
    assert str(orphelin.raison) == "rattaché seulement à des exigences non actives ou hors validité"


def test_une_exigence_hors_de_sa_validite_ne_justifie_plus(cadre_config):
    mapping = _mapping(cadre_config)
    exigence = _exigence(cadre_config, valid_to=datetime.date(2026, 7, 1))
    _rattacher(cadre_config, exigence, mapping)
    projet = cadre_config[1]
    assert detecter_configuration_orpheline(projet.id, datetime.date(2026, 6, 30)) == []
    (orphelin,) = detecter_configuration_orpheline(projet.id, datetime.date(2026, 7, 1))
    assert str(orphelin.raison).startswith("rattaché seulement")  # valid_to est exclu


def test_il_suffit_d_une_exigence_active_parmi_plusieurs(cadre_config):
    mapping = _mapping(cadre_config)
    _rattacher(cadre_config, _exigence(cadre_config, "A", statut="proposed"), mapping)
    assert detecter_configuration_orpheline(cadre_config[1].id, DEBUT) != []
    _rattacher(cadre_config, _exigence(cadre_config, "B"), mapping)
    assert detecter_configuration_orpheline(cadre_config[1].id, DEBUT) == []


def test_seuls_les_objets_actifs_du_projet_comptent(cadre_config):
    organisation, projet, profils, _ = cadre_config
    for statut in ("draft", "validated", "superseded"):
        _mapping(cadre_config, code=f"M-{statut}", statut=statut)
    autre = _creer_projet(organisation, "P2")
    _mapping(cadre_config, code="AUTRE", projet=autre)
    assert detecter_configuration_orpheline(projet.id, DEBUT) == []
    assert [o.libelle for o in detecter_configuration_orpheline(autre.id, DEBUT)] == ["AUTRE v1"]


def test_un_objet_pas_encore_valable_ou_deja_ferme_n_est_pas_actif_a_la_date(cadre_config):
    _mapping(cadre_config, valid_to=datetime.date(2026, 3, 1))
    projet = cadre_config[1]
    assert len(detecter_configuration_orpheline(projet.id, datetime.date(2026, 2, 28))) == 1
    assert detecter_configuration_orpheline(projet.id, datetime.date(2026, 3, 1)) == []
    assert detecter_configuration_orpheline(projet.id, datetime.date(2025, 12, 31)) == []


# --- rattacher ------------------------------------------------------------------------------


def test_rattacher_est_idempotent_et_trace(cadre_config):
    organisation, projet, profils, _ = cadre_config
    exigence, mapping = _exigence(cadre_config), _mapping(cadre_config)
    r1 = _rattacher(cadre_config, exigence, mapping)
    r2 = _rattacher(cadre_config, exigence, mapping)
    assert r1.pk == r2.pk and RattachementExigence.objects.count() == 1
    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM core_auditlog WHERE action = 'requirement_bound'")
        assert cur.fetchone() == (1,)


def test_on_ne_rattache_qu_un_objet_existant_du_meme_projet(cadre_config):
    organisation, projet, profils, _ = cadre_config
    exigence = _exigence(cadre_config)
    autre = _creer_projet(organisation, "P2")
    etranger = _mapping(cadre_config, projet=autre)
    with pytest.raises(RattachementInvalide, match="n'existe pas dans le projet"):
        _rattacher(cadre_config, exigence, etranger)
    with pytest.raises(RattachementInvalide, match="n'existe pas dans le projet"):
        rattacher(
            utilisateur=profils["dora"],
            exigence=exigence,
            target_type="mapping",
            target_id=uuid.uuid4(),
        )
    with pytest.raises(RattachementInvalide, match="type de cible inconnu"):
        rattacher(
            utilisateur=profils["dora"],
            exigence=exigence,
            target_type="sortilege",
            target_id=uuid.uuid4(),
        )
    assert RattachementExigence.objects.count() == 0


@pytest.mark.parametrize("statut", ["superseded", "rejected"])
def test_une_exigence_remplacee_ou_rejetee_ne_justifie_plus(cadre_config, statut):
    mapping = _mapping(cadre_config)
    with pytest.raises(RattachementInvalide, match=f"est {statut}"):
        _rattacher(cadre_config, _exigence(cadre_config, statut=statut), mapping)


def test_un_type_non_branche_est_accepte_sans_verification_d_existence(cadre_config):
    exigence = _exigence(cadre_config)
    identifiant = uuid.uuid4()
    rattachement = rattacher(
        utilisateur=cadre_config[2]["dora"],
        exigence=exigence,
        target_type="report_row",
        target_id=identifiant,
    )
    assert rattachement.target_id == identifiant


def test_rattacher_exige_l_habilitation_parametrer(cadre_config):
    exigence, mapping = _exigence(cadre_config), _mapping(cadre_config)
    with pytest.raises(PermissionDenied):
        rattacher(
            utilisateur=cadre_config[2]["amina"],
            exigence=exigence,
            target_type="mapping",
            target_id=mapping.pk,
        )


# --- extension : les autres types d'objets (lot L6) ----------------------------------------


def test_un_nouveau_type_d_objet_se_branche_sur_la_regle(cadre_config):
    organisation, projet, profils, _ = cadre_config
    controle_id = uuid.uuid4()
    precedent = module_rattachement.SOURCES.get("control")
    enregistrer_cible(
        "control",
        SourceCible(
            lister_actifs=lambda project_id, date: [(controle_id, "Avance non justifiée")],
            existe=lambda project_id, target_id: target_id == controle_id,
        ),
    )
    try:
        (orphelin,) = detecter_configuration_orpheline(projet.id, DEBUT)
        assert (orphelin.target_type, orphelin.libelle) == ("control", "Avance non justifiée")
        rattacher(
            utilisateur=profils["dora"],
            exigence=_exigence(cadre_config),
            target_type="control",
            target_id=controle_id,
        )
        assert detecter_configuration_orpheline(projet.id, DEBUT) == []
    finally:
        if precedent is None:
            module_rattachement.SOURCES.pop("control")
        else:
            module_rattachement.SOURCES["control"] = precedent
    with pytest.raises(ValueError, match="type de cible inconnu"):
        enregistrer_cible("autre", SourceCible(lambda *a: [], lambda *a: True))


# --- la commande ----------------------------------------------------------------------------


def test_la_commande_echoue_s_il_y_a_un_orphelin_et_reussit_sinon(cadre_config, capsys):
    organisation, projet, profils, _ = cadre_config
    arguments = {
        "organisation": str(organisation.id),
        "projet": str(projet.id),
        "date": "2026-02-01",
    }
    call_command("verifier_configuration", **arguments)  # rien d'actif : rien à signaler
    mapping = _mapping(cadre_config)
    with pytest.raises(CommandError, match="1 objet"):
        call_command("verifier_configuration", **arguments)
    _rattacher(cadre_config, _exigence(cadre_config), mapping)
    call_command("verifier_configuration", **arguments)


# --- la base --------------------------------------------------------------------------------


def test_un_rattachement_est_en_ajout_seul_pour_tout_role(cadre_config):
    exigence, mapping = _exigence(cadre_config), _mapping(cadre_config)
    rattachement = _rattacher(cadre_config, exigence, mapping)
    with connexion_proprietaire() as admin:
        for requete in (
            "UPDATE niveau3_config_rattachementexigence SET target_id = gen_random_uuid() "
            "WHERE id = %s",
            "DELETE FROM niveau3_config_rattachementexigence WHERE id = %s",
        ):
            with pytest.raises(Exception, match="ajout seul"):
                admin.execute(requete, [rattachement.pk])


@pytest.mark.parametrize("statut", ["superseded", "rejected"])
def test_la_base_refuse_un_rattachement_a_une_exigence_remplacee_ou_rejetee(cadre_config, statut):
    organisation = cadre_config[0]
    exigence = _exigence(cadre_config, statut=statut)
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match=f"exigence {statut} ne justifie plus"):
            admin.execute(
                "INSERT INTO niveau3_config_rattachementexigence (id, created_at, updated_at, "
                "org_id, exigence_id, target_type, target_id) "
                "VALUES (gen_random_uuid(), now(), now(), %s, %s, 'mapping', gen_random_uuid())",
                [organisation.id, exigence.pk],
            )
