"""Activation, versionnement, date d'effet. Voir L5-T04.

Contrôles du plan : deux versions actives qui se chevauchent sont refusées par la base ; une méthode
d'un profil approuvé ne se modifie ni ne se supprime, y compris en SQL direct ; une dépense du 15/06
reste sous V2 quand l'accord passe en V3 en décembre ; l'activation concurrente de deux versions
incompatibles n'en laisse aboutir qu'une ; une exigence modifiée avec effet au 1er janvier 2028
laisse inchangée la configuration d'un trimestre de 2027.
"""

import datetime
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau3_config.models import DocumentReference, Exigence, ProfilDecaissement
from niveau3_config.services.activation import (
    ActivationRefusee,
    ConflitActivation,
    activer_exigence,
    activer_profil,
    rejeter_exigence,
    rejeter_profil,
    resoudre_configuration,
    valider_exigence,
    valider_profil,
)
from niveau3_config.services.decaissement import profil_en_vigueur
from tests.outils_profil import creer_profil
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = datetime.date


@pytest.fixture
def cfg(drf):  # noqa: F811
    """vera valide et paramètre ; dora paramètre seulement."""
    organisation, projet, profils, accord, cat = drf
    vera = Utilisateur.objects.create_user("vera", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id,
        code="VERA",
        label={"fr": "vera"},
        operations=["consulter", "valider", "parametrer"],
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=vera.id, project_id=projet.id, role=role
    )
    profils["vera"] = vera
    document = DocumentReference.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        kind="dfil",
        title="DFIL",
        version="1",
        file_ref="objets/dfil.pdf",
        sha256=hashlib.sha256(b"DFIL").digest(),
    )
    return organisation, projet, profils, accord, cat, document


def _exigence(cfg, version, valid_from, statut="proposed", code="IFR", **champs):
    organisation, projet, _, _, _, document = cfg
    validation = (
        {"validated_by": cfg[2]["vera"].id, "validated_at": "2026-01-05T09:00:00Z"}
        if statut in ("validated", "active")
        else {}
    )
    donnees = {
        "org_id": organisation.id,
        "project_id": projet.id,
        "code": code,
        "document": document,
        "citation": {"annex": "2", "page": 1, "paragraph": "4.2", "quote": "dans les 45 jours"},
        "subject": "Rapport",
        "rule": {"kind": "report"},
        "obligation": "mandatory",
        "valid_from": valid_from,
        "version": version,
        "status": statut,
        "source": "manual",
        "citation_verifiee_sha256": document.sha256,
    }
    return Exigence.objects.create(**donnees | validation | champs)


def _profil(cfg, categorie_cle="serv", **champs):
    organisation, projet, _, accord, cat, _ = cfg
    champs.setdefault("regles", [(cat[categorie_cle], "0.8")])
    return creer_profil(organisation, projet, accord, **champs)


def _vera(cfg):
    return cfg[2]["vera"]


# --- exigences : le cycle ------------------------------------------------------------------


def test_une_exigence_se_valide_puis_sactive_et_chaque_transition_est_tracee(cfg):
    exigence = _exigence(cfg, 1, D(2026, 1, 1))
    valider_exigence(utilisateur=_vera(cfg), exigence=exigence)
    exigence.refresh_from_db()
    assert exigence.status == "validated" and exigence.validated_by == _vera(cfg).id

    activer_exigence(utilisateur=_vera(cfg), exigence=exigence)
    exigence.refresh_from_db()
    assert exigence.status == "active"

    entrees = list(_journal(exigence.id).values_list("action", flat=True))
    assert entrees == ["requirement_validated", "requirement_activated"]
    assert verifier_chaine(cfg[0].id) is None


def _journal(objet_id):
    from core.models import AuditLog

    return AuditLog.objects.filter(object_id=objet_id).order_by("id")


def test_on_ne_saute_pas_la_validation(cfg):
    exigence = _exigence(cfg, 1, D(2026, 1, 1))
    with pytest.raises(ActivationRefusee, match="validée"):
        activer_exigence(utilisateur=_vera(cfg), exigence=exigence)
    exigence.refresh_from_db()
    assert exigence.status == "proposed"


def test_valider_exige_lhabilitation_valider_et_activer_celle_de_parametrer(cfg):
    exigence = _exigence(cfg, 1, D(2026, 1, 1))
    with pytest.raises(PermissionDenied):
        valider_exigence(utilisateur=cfg[2]["dora"], exigence=exigence)  # dora ne valide pas
    valider_exigence(utilisateur=_vera(cfg), exigence=exigence)
    exigence.refresh_from_db()
    with pytest.raises(PermissionDenied):
        activer_exigence(utilisateur=cfg[2]["bruno"], exigence=exigence)  # bruno ne paramètre pas


def test_une_exigence_dont_la_citation_na_pas_ete_verifiee_ne_se_valide_pas(cfg):
    exigence = _exigence(cfg, 1, D(2026, 1, 1))
    Exigence.objects.filter(pk=exigence.pk).update(citation_verifiee_sha256=None)
    exigence.refresh_from_db()
    with pytest.raises(ActivationRefusee, match="citation"):
        valider_exigence(utilisateur=_vera(cfg), exigence=exigence)


def test_un_rejet_exige_un_motif_et_est_definitif(cfg):
    exigence = _exigence(cfg, 1, D(2026, 1, 1))
    with pytest.raises(ActivationRefusee, match="motif"):
        rejeter_exigence(utilisateur=_vera(cfg), exigence=exigence, motif="  ")
    rejeter_exigence(utilisateur=_vera(cfg), exigence=exigence, motif="Citation hors sujet")
    exigence.refresh_from_db()
    assert exigence.status == "rejected"
    with pytest.raises(ActivationRefusee):
        valider_exigence(utilisateur=_vera(cfg), exigence=exigence)
    with pytest.raises(IntegrityError, match="définitive"), transaction.atomic():
        Exigence.objects.filter(pk=exigence.pk).update(status="proposed")


def test_la_contrainte_de_validation_de_l0_est_toujours_la(cfg):
    """Contrôle du plan : le passage en `active` sans validateur reste refusé par la base."""
    exigence = _exigence(cfg, 1, D(2026, 1, 1))
    with pytest.raises(IntegrityError, match="exigence_validation_obligatoire"):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(
                "UPDATE niveau3_config_exigence SET status = 'active' WHERE id = %s",
                [exigence.id],
            )


# --- exigences : versions et date d'effet --------------------------------------------------


def test_une_exigence_modifiee_avec_effet_2028_laisse_inchange_le_troisieme_trimestre_2027(cfg):
    """Contrôle du plan, au niveau de la configuration que toute génération résout."""
    projet = cfg[1]
    v1 = _exigence(cfg, 1, D(2026, 1, 1))
    valider_exigence(utilisateur=_vera(cfg), exigence=v1)
    activer_exigence(utilisateur=_vera(cfg), exigence=v1)
    avant = resoudre_configuration(projet.id, D(2027, 9, 30))
    assert [(c, v) for c, v, _ in avant.exigences] == [("IFR", 1)]

    v2 = _exigence(cfg, 2, D(2028, 1, 1), subject="Rapport (modifié)")
    valider_exigence(utilisateur=_vera(cfg), exigence=v2)
    activer_exigence(utilisateur=_vera(cfg), exigence=v2)

    apres = resoudre_configuration(projet.id, D(2027, 9, 30))
    assert apres == avant and apres.empreinte == avant.empreinte
    # Le jour de l'effet, c'est la nouvelle version (fin de V1 exclue) ; la veille, encore V1.
    assert [v for _, v, _ in resoudre_configuration(projet.id, D(2028, 1, 1)).exigences] == [2]
    assert [v for _, v, _ in resoudre_configuration(projet.id, D(2027, 12, 31)).exigences] == [1]
    v1.refresh_from_db()
    assert v1.status == "active" and v1.valid_to == D(2028, 1, 1)


def test_une_activation_qui_reecrirait_lhistoire_est_refusee(cfg):
    v2 = _exigence(cfg, 2, D(2027, 1, 1), statut="active")
    v3 = _exigence(cfg, 3, D(2026, 6, 1), statut="validated")
    with pytest.raises(ActivationRefusee, match="réécrirait"):
        activer_exigence(utilisateur=_vera(cfg), exigence=v3)
    v2.refresh_from_db()
    assert v2.valid_to is None  # la version en vigueur n'a pas bougé


def test_la_base_refuse_deux_exigences_actives_qui_se_chevauchent(cfg):
    _exigence(cfg, 1, D(2026, 1, 1), statut="active")
    with pytest.raises(IntegrityError, match="exigence_active_sans_chevauchement"):
        with transaction.atomic():
            _exigence(cfg, 2, D(2026, 6, 1), statut="active")


def test_deux_exigences_actives_consecutives_ne_se_chevauchent_pas(cfg):
    """Validité `[valid_from, valid_to[` : la fin est exclue, V2 peut commencer le jour même."""
    _exigence(cfg, 1, D(2026, 1, 1), statut="active", valid_to=D(2026, 7, 1))
    assert _exigence(cfg, 2, D(2026, 7, 1), statut="active").status == "active"
    # Un autre code ne gêne personne.
    assert _exigence(cfg, 1, D(2026, 1, 1), statut="active", code="AUTRE")


def test_une_exigence_validee_ne_change_pas_de_contenu_et_son_statut_ne_recule_pas(cfg):
    exigence = _exigence(cfg, 1, D(2026, 1, 1), statut="validated")
    with pytest.raises(IntegrityError, match="ne se modifie pas"), transaction.atomic():
        Exigence.objects.filter(pk=exigence.pk).update(subject="Autre rubrique")
    with pytest.raises(IntegrityError, match="ne recule pas"), transaction.atomic():
        Exigence.objects.filter(pk=exigence.pk).update(status="proposed")
    # Une exigence proposée reste, elle, modifiable (c'est un brouillon).
    proposee = _exigence(cfg, 2, D(2027, 1, 1))
    Exigence.objects.filter(pk=proposee.pk).update(subject="Reformulée")


# --- profils : cycle, un seul actif, immutabilité ------------------------------------------


def test_un_profil_se_valide_puis_sactive_et_ferme_le_precedent(cfg):
    accord = cfg[3]
    v1 = _profil(cfg, version=1, valid_from=D(2026, 1, 1), statut="active")
    v2 = _profil(cfg, version=2, valid_from=D(2026, 7, 1), statut="draft")
    valider_profil(utilisateur=_vera(cfg), profil=v2)
    activer_profil(utilisateur=_vera(cfg), profil=v2)
    v1.refresh_from_db()
    v2.refresh_from_db()
    assert (v2.status, v1.status, v1.valid_to) == ("active", "active", D(2026, 7, 1))
    assert profil_en_vigueur(accord, D(2026, 6, 30)) == v1
    assert profil_en_vigueur(accord, D(2026, 7, 1)) == v2


def test_une_depense_du_15_juin_garde_v2_quand_laccord_passe_en_v3_en_decembre(cfg):
    accord = cfg[3]
    _profil(cfg, version=1, valid_from=D(2026, 1, 1), valid_to=D(2026, 3, 1), statut="active")
    v2 = _profil(cfg, version=2, valid_from=D(2026, 3, 1), statut="active")
    avant = profil_en_vigueur(accord, D(2026, 6, 15))
    assert avant == v2
    v3 = _profil(cfg, version=3, valid_from=D(2026, 12, 1), statut="draft")
    valider_profil(utilisateur=_vera(cfg), profil=v3)
    activer_profil(utilisateur=_vera(cfg), profil=v3)
    assert profil_en_vigueur(accord, D(2026, 6, 15)).version == 2
    assert profil_en_vigueur(accord, D(2026, 12, 1)).version == 3


def test_la_base_refuse_deux_profils_actifs_qui_se_chevauchent(cfg):
    _profil(cfg, version=1, valid_from=D(2026, 1, 1), statut="active")
    with pytest.raises(IntegrityError, match="profil_actif_sans_chevauchement"):
        with transaction.atomic():
            _profil(cfg, version=2, valid_from=D(2026, 6, 1), statut="active")
    # En SQL direct aussi : une version validée qu'on passerait en actif sans fermer la précédente.
    v2 = _profil(cfg, version=3, valid_from=D(2026, 6, 1), statut="validated")
    with pytest.raises(IntegrityError, match="profil_actif_sans_chevauchement"):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(
                "UPDATE niveau3_config_profildecaissement SET status='active' WHERE id=%s",
                [v2.id],
            )


def test_un_profil_programme_reste_une_version_active_dont_la_date_est_future(cfg):
    accord = cfg[3]
    _profil(cfg, version=1, valid_from=D(2026, 1, 1), statut="active")
    v2 = _profil(cfg, version=2, valid_from=D(2030, 1, 1), statut="validated")
    activer_profil(utilisateur=_vera(cfg), profil=v2)
    assert profil_en_vigueur(accord, D(2026, 6, 1)).version == 1
    assert profil_en_vigueur(accord, D(2030, 1, 1)).version == 2


def test_une_methode_dun_profil_approuve_ne_se_modifie_ni_ne_se_supprime(cfg):
    profil = _profil(cfg, version=1, statut="validated", comptes=[])
    methode = profil.methodes.get()
    for sql in (
        "UPDATE niveau3_config_methodedecaissement SET is_enabled = false WHERE id = %s",
        "DELETE FROM niveau3_config_methodedecaissement WHERE id = %s",
    ):
        with pytest.raises(IntegrityError, match="ne se modifient plus"):
            with transaction.atomic(), connection.cursor() as cur:
                cur.execute(sql, [methode.id])
    regle = profil.regles.get()
    with pytest.raises(IntegrityError, match="ne se modifient plus"), transaction.atomic():
        regle.funding_rate = D(2026, 1, 1).day / 100
        regle.save()
    with pytest.raises(IntegrityError, match="ne se modifient plus"), transaction.atomic():
        profil.methodes.create(org_id=profil.org_id, method="advance", supporting_docs=["soe"])


def test_les_comptes_designes_dun_profil_approuve_sont_figes_aussi(cfg):
    from niveau3_config.models import RegleCompteDesigne

    profil = _profil(cfg, version=1, statut="active")
    assert not RegleCompteDesigne.objects.filter(profil=profil).exists()
    with pytest.raises(IntegrityError, match="ne se modifient plus"), transaction.atomic():
        RegleCompteDesigne.objects.create(
            org_id=profil.org_id,
            profil=profil,
            bank_account=None,
            currency_id="DJF",
            ceiling_kind="variable",
        )


def test_un_brouillon_reste_modifiable_et_les_enfants_suivent_son_cycle(cfg):
    profil = _profil(cfg, version=1, statut="draft")
    methode = profil.methodes.get()
    methode.is_enabled = False
    methode.save()
    methode.delete()
    profil.methodes.create(org_id=profil.org_id, method="advance", supporting_docs=["soe"])
    ProfilDecaissement.objects.filter(pk=profil.pk).update(regime="report_based")


def test_un_profil_approuve_ne_change_pas_ses_parametres_et_ne_se_supprime_pas(cfg):
    profil = _profil(cfg, version=1, statut="active")
    for champs in ({"regime": "report_based"}, {"valid_from": D(2025, 1, 1)}):
        with pytest.raises(IntegrityError, match="ne se modifie pas"), transaction.atomic():
            ProfilDecaissement.objects.filter(pk=profil.pk).update(**champs)
    with (
        pytest.raises(IntegrityError, match="ne se supprime pas|ne se modifient plus"),
        transaction.atomic(),
    ):
        ProfilDecaissement.objects.filter(pk=profil.pk).delete()
    with pytest.raises(IntegrityError, match="ne recule pas"), transaction.atomic():
        ProfilDecaissement.objects.filter(pk=profil.pk).update(status="draft")


def test_la_fin_de_validite_se_pose_une_fois_et_seulement_sur_un_profil_actif(cfg):
    actif = _profil(cfg, version=1, statut="active")
    ProfilDecaissement.objects.filter(pk=actif.pk).update(valid_to=D(2026, 9, 1))
    with pytest.raises(IntegrityError, match="ne se modifie plus"), transaction.atomic():
        ProfilDecaissement.objects.filter(pk=actif.pk).update(valid_to=D(2026, 8, 1))
    valide = _profil(cfg, version=2, valid_from=D(2026, 9, 1), statut="validated")
    with pytest.raises(IntegrityError, match="actif reçoit"), transaction.atomic():
        ProfilDecaissement.objects.filter(pk=valide.pk).update(valid_to=D(2027, 1, 1))


def test_un_profil_rejete_est_definitif_et_le_rejet_est_motive(cfg):
    profil = _profil(cfg, version=1, statut="draft")
    with pytest.raises(ActivationRefusee, match="motif"):
        rejeter_profil(utilisateur=_vera(cfg), profil=profil, motif="")
    rejeter_profil(utilisateur=_vera(cfg), profil=profil, motif="Taux non conforme à l'avenant")
    profil.refresh_from_db()
    assert profil.status == "rejected"
    assert profil.rejection_reason == "Taux non conforme à l'avenant"
    with pytest.raises(ActivationRefusee):
        valider_profil(utilisateur=_vera(cfg), profil=profil)
    with pytest.raises(IntegrityError, match="définitif"), transaction.atomic():
        ProfilDecaissement.objects.filter(pk=profil.pk).update(status="draft")


def test_un_profil_vide_ne_se_valide_pas_et_on_ne_saute_pas_la_validation(cfg):
    organisation, projet, _, accord, _, _ = cfg
    vide = creer_profil(organisation, projet, accord, version=1, methodes=(), statut="draft")
    with pytest.raises(ActivationRefusee, match="méthode"):
        valider_profil(utilisateur=_vera(cfg), profil=vide)
    sans_regle = creer_profil(organisation, projet, accord, version=2, statut="draft")
    with pytest.raises(ActivationRefusee, match="règle"):
        valider_profil(utilisateur=_vera(cfg), profil=sans_regle)
    complet = _profil(cfg, version=3, statut="draft")
    with pytest.raises(ActivationRefusee, match="validé"):
        activer_profil(utilisateur=_vera(cfg), profil=complet)
    with pytest.raises(PermissionDenied):
        valider_profil(utilisateur=cfg[2]["dora"], profil=complet)


def test_une_activation_non_validee_ne_ferme_pas_la_version_en_vigueur(cfg):
    v1 = _profil(cfg, version=1, valid_from=D(2026, 1, 1), statut="active")
    v2 = _profil(cfg, version=2, valid_from=D(2026, 7, 1), statut="draft")
    with pytest.raises(ActivationRefusee):
        activer_profil(utilisateur=_vera(cfg), profil=v2)
    v1.refresh_from_db()
    assert v1.valid_to is None


# --- concurrence ---------------------------------------------------------------------------


def _activer_concurrent(org_id, user_id, profil_id, barriere):
    """Retourne "activee", ou le nom de l'exception du refus : la sérialisation par le verrou de
    l'accord donne un refus net (ActivationRefusee) ; la base (ConflitActivation) n'est que le
    dernier recours."""
    try:
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [str(org_id)])
        barriere.wait()
        utilisateur = Utilisateur.objects.get(pk=user_id)
        activer_profil(utilisateur=utilisateur, profil=ProfilDecaissement.objects.get(pk=profil_id))
        return "activee"
    except ActivationRefusee as refus:
        return type(refus).__name__
    finally:
        connections.close_all()


def test_lactivation_concurrente_de_deux_versions_incompatibles_nen_laisse_aboutir_quune(cfg):
    organisation = cfg[0]
    v1 = _profil(cfg, version=1, valid_from=D(2026, 1, 1), statut="validated")
    v2 = _profil(cfg, version=2, valid_from=D(2026, 1, 1), statut="validated")
    barriere = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futurs = [
            pool.submit(_activer_concurrent, organisation.id, _vera(cfg).id, p.pk, barriere)
            for p in (v1, v2)
        ]
        issues = sorted(f.result() for f in futurs)
    assert issues == ["ActivationRefusee", "activee"]  # refus net, pas échec de la base
    assert ProfilDecaissement.objects.filter(status="active").count() == 1


def test_une_version_qui_raccourcirait_une_version_programmee_est_refusee_nettement(cfg):
    """V1 est programmée jusqu'au 01/12 : V2 au 01/07 la raccourcirait. Refus par le service
    (qui nomme la date), pas seulement par la base."""
    _profil(cfg, version=1, valid_from=D(2026, 1, 1), valid_to=D(2026, 12, 1), statut="active")
    v2 = _profil(cfg, version=2, valid_from=D(2026, 7, 1), statut="validated")
    with pytest.raises(ActivationRefusee, match="programmée jusqu'au 2026-12-01") as refus:
        activer_profil(utilisateur=_vera(cfg), profil=v2)
    assert not isinstance(refus.value, ConflitActivation)


def test_un_profil_approuve_sans_enfant_ne_se_supprime_pas_non_plus(cfg):
    """Sans méthode ni règle pour barrer la route, c'est le profil lui-même qui refuse."""
    profil = _profil(cfg, version=1, statut="active", methodes=(), regles=[])
    with pytest.raises(IntegrityError, match="ne se supprime pas"), transaction.atomic():
        ProfilDecaissement.objects.filter(pk=profil.pk).delete()
    brouillon = _profil(cfg, version=2, statut="draft", methodes=(), regles=[])
    brouillon.delete()  # un brouillon, lui, se supprime


def test_activer_un_profil_exige_lhabilitation_parametrer(cfg):
    v1 = _profil(cfg, version=1, statut="validated")
    with pytest.raises(PermissionDenied):
        activer_profil(utilisateur=cfg[2]["bruno"], profil=v1)  # bruno ne paramètre pas
    v1.refresh_from_db()
    assert v1.status == "validated"


def test_seules_les_versions_actives_composent_la_configuration(cfg):
    for version, statut in enumerate(["proposed", "validated", "rejected", "superseded"], start=1):
        _exigence(cfg, version, D(2026, 1, 1), statut=statut, code=f"X{version}")
    for version, statut in enumerate(["draft", "validated", "rejected"], start=1):
        _profil(cfg, version=version, statut=statut, rejection_reason="non conforme")
    assert resoudre_configuration(cfg[1].id, D(2026, 6, 1)).exigences == ()
    assert resoudre_configuration(cfg[1].id, D(2026, 6, 1)).profils == ()
    actif = _profil(cfg, version=9, statut="active")
    assert [i for _, _, i in resoudre_configuration(cfg[1].id, D(2026, 6, 1)).profils] == [actif.id]
