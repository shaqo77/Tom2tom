# ruff: noqa: F811
"""Réallocations et avenants : des événements qui créent une version de profil. Voir L5-T04bis.

Contrôles du plan : une réallocation approuvée crée une nouvelle version et conserve l'ancienne ;
demandeur == approbateur est refusé au serveur ; deux réallocations simultanées sur une même
catégorie laissent un solde exact ; une double approbation concurrente ne crée qu'une version ; un
avenant affiche sa situation avant/après et laisse l'ancienne version intacte.
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
from niveau1_socle.decaissements.models import SoldeCategorie
from niveau1_socle.financements.models import AvenantAccord
from niveau1_socle.financements.services import creer_categorie, situation_avant_apres
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau3_config.models import ProfilDecaissement, Reallocation
from niveau3_config.services.activation import ActivationRefusee
from niveau3_config.services.avenant import enregistrer_avenant
from niveau3_config.services.comparaison import comparer_versions
from niveau3_config.services.decaissement import profil_en_vigueur
from niveau3_config.services.reallocation import (
    ReallocationRefusee,
    SoldeInsuffisant,
    approuver_reallocation,
    demander_reallocation,
    rejeter_reallocation,
)
from tests.outils_profil import creer_profil
from tests.test_activation_bd import cfg  # noqa: F401
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import _accord, _document, cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = datetime.date
M = Decimal
JUIL, AOUT = D(2026, 7, 1), D(2026, 8, 1)


@pytest.fixture
def realloc(cfg):  # noqa: F811
    """Un profil actif (quatre catégories à 100 sur un accord de 1 000) ; victor valide aussi."""
    organisation, projet, profils, accord, cat, _ = cfg
    victor = Utilisateur.objects.create_user("victor", password="x", org_id=organisation.id)
    role = Role.objects.get(org_id=organisation.id, code="VERA")
    Habilitation.objects.create(
        org_id=organisation.id, user_id=victor.id, project_id=projet.id, role=role
    )
    profils["victor"] = victor
    cat["div"] = creer_categorie(
        utilisateur=profils["dora"], accord=accord, code="DIV", label={"fr": "Divers"}, plafond="50"
    )
    v1 = creer_profil(
        organisation,
        projet,
        accord,
        version=1,
        valid_from=D(2026, 1, 1),
        regles=[
            (cat["serv"], "0.8"),
            (cat["biens"], "0.9"),
            (cat["biens_a"], "0.7"),
            (cat["div"], "0.6"),
        ],
    )
    return organisation, projet, profils, accord, cat, v1


def _demander(realloc, montant=30, date=JUIL, par="dora", **champs):
    _, _, profils, accord, cat, _ = realloc
    donnees = {
        "utilisateur": profils[par],
        "accord": accord,
        "source": cat["serv"],
        "cible": cat["biens"],
        "montant": montant,
        "date_effet": date,
        "motif": "Les services coûtent moins que prévu",
    } | champs
    return demander_reallocation(**donnees)


def _alloc(profil, categorie):
    return profil.regles.get(category=categorie).allocation


# --- la demande ----------------------------------------------------------------------------


def test_une_demande_de_reallocation_est_validee_et_ne_change_rien(realloc):
    _, _, profils, accord, cat, v1 = realloc
    r = _demander(realloc)
    assert (r.status, r.demandeur, r.approbateur, r.profil_cree) == (
        "requested",
        profils["dora"].id,
        None,
        None,
    )
    assert ProfilDecaissement.objects.count() == 1 and _alloc(v1, cat["serv"]) == 100
    for champs, message in [
        ({"montant": 0}, "strictement positif"),
        ({"cible": cat["serv"]}, "distinctes"),
        ({"motif": "  "}, "motivée"),
        ({"date_effet": D(2020, 1, 1)}, "Aucun profil"),
    ]:
        with pytest.raises(ReallocationRefusee, match=message):
            _demander(realloc, **champs)


def test_demander_exige_lhabilitation_parametrer(realloc):
    with pytest.raises(PermissionDenied):
        _demander(realloc, par="bruno")


# --- l'approbation -------------------------------------------------------------------------


def test_une_reallocation_approuvee_cree_une_version_et_conserve_lancienne(realloc):
    organisation, _, profils, accord, cat, v1 = realloc
    r = _demander(realloc, montant=30)
    approuver_reallocation(utilisateur=profils["vera"], reallocation=r)

    r.refresh_from_db()
    v1.refresh_from_db()
    v2 = r.profil_cree
    assert (r.status, r.approbateur) == ("approved", profils["vera"].id)
    assert (v2.version, v2.status, v2.valid_from) == (2, "active", JUIL)
    assert (_alloc(v2, cat["serv"]), _alloc(v2, cat["biens"])) == (70, 130)
    # L'ancienne version est conservée, intacte, et close à la date d'effet.
    assert (_alloc(v1, cat["serv"]), _alloc(v1, cat["biens"])) == (100, 100)
    assert (v1.status, v1.valid_to) == ("active", JUIL)
    assert profil_en_vigueur(accord, D(2026, 6, 30)) == v1
    assert profil_en_vigueur(accord, JUIL) == v2
    # Le reste est repris tel quel.
    assert v2.methodes.count() == v1.methodes.count()
    assert v2.regles.get(category=cat["serv"]).funding_rate == M("0.8")
    assert verifier_chaine(organisation.id) is None


def test_le_demandeur_ne_peut_pas_approuver_sa_propre_reallocation(realloc):
    _, _, profils, _, _, _ = realloc
    r = _demander(realloc, par="vera")  # vera paramètre ET valide : elle ne s'approuve pas
    with pytest.raises(ReallocationRefusee, match="distinct"):
        approuver_reallocation(utilisateur=profils["vera"], reallocation=r)
    r.refresh_from_db()
    assert r.status == "requested" and ProfilDecaissement.objects.count() == 1


def test_la_base_refuse_un_approbateur_egal_au_demandeur(realloc):
    _, _, profils, _, _, v1 = realloc
    r = _demander(realloc)
    with pytest.raises(IntegrityError, match="realloc_approbation_complete"):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(
                "UPDATE niveau3_config_reallocation SET status='approved', approbateur=demandeur,"
                " decided_at=now(), profil_cree_id=%s WHERE id=%s",
                [v1.id, r.id],
            )


def test_approuver_exige_valider_et_parametrer(realloc):
    _, _, profils, _, _, _ = realloc
    r = _demander(realloc)
    with pytest.raises(PermissionDenied):
        approuver_reallocation(utilisateur=profils["bruno"], reallocation=r)
    with pytest.raises(PermissionDenied):  # dora paramètre mais ne valide pas
        approuver_reallocation(utilisateur=profils["dora"], reallocation=r)


def test_une_reallocation_est_refusee_quand_le_solde_de_la_source_ne_la_couvre_pas(realloc):
    organisation, _, profils, _, cat, v1 = realloc
    SoldeCategorie.objects.create(org_id=organisation.id, categorie=cat["serv"], utilise=M(60))
    trop = _demander(realloc, montant=41)
    with pytest.raises(SoldeInsuffisant, match="solde 40.*41"):
        approuver_reallocation(utilisateur=profils["vera"], reallocation=trop)
    trop.refresh_from_db()
    assert trop.status == "requested" and ProfilDecaissement.objects.count() == 1
    juste = _demander(realloc, montant=40)  # exactement le solde : accepté
    approuver_reallocation(utilisateur=profils["vera"], reallocation=juste)
    juste.refresh_from_db()
    assert _alloc(juste.profil_cree, cat["serv"]) == 60  # = ce qui est déjà demandé


def test_une_reallocation_decidee_est_definitive(realloc):
    _, _, profils, _, _, _ = realloc
    r = _demander(realloc)
    with pytest.raises(ReallocationRefusee, match="motif"):
        rejeter_reallocation(utilisateur=profils["vera"], reallocation=r, motif="")
    rejeter_reallocation(utilisateur=profils["vera"], reallocation=r, motif="Hors enveloppe")
    r.refresh_from_db()
    assert (r.status, r.motif_rejet) == ("rejected", "Hors enveloppe")
    with pytest.raises(ReallocationRefusee, match="déjà"):
        approuver_reallocation(utilisateur=profils["victor"], reallocation=r)
    for sql in (
        "UPDATE niveau3_config_reallocation SET motif = 'autre' WHERE id = %s",
        "DELETE FROM niveau3_config_reallocation WHERE id = %s",
    ):
        with pytest.raises(IntegrityError, match="ne se modifie plus|ne se supprime pas"):
            with transaction.atomic(), connection.cursor() as cur:
                cur.execute(sql, [r.id])


def test_la_base_refuse_une_reallocation_dune_autre_categorie_daccord(realloc):
    organisation, projet, profils, accord, cat, _ = realloc
    bailleur = accord.bailleur
    autre = _accord(projet, profils, bailleur, "DON-2", devise="DJF", montant_initial="500")
    etrangere = creer_categorie(
        utilisateur=profils["dora"], accord=autre, code="AUTRE", label={"fr": "x"}, plafond="50"
    )
    with pytest.raises(IntegrityError, match="appartiennent à son accord"), transaction.atomic():
        Reallocation.objects.create(
            org_id=organisation.id,
            project_id=projet.id,
            accord=accord,
            source=cat["serv"],
            cible=etrangere,
            montant=M(10),
            devise_id="DJF",
            date_effet=JUIL,
            motif="x",
            demandeur=profils["dora"].id,
        )


# --- concurrence ---------------------------------------------------------------------------


def _approuver_concurrent(org_id, user_id, realloc_id, barriere):
    try:
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [str(org_id)])
        barriere.wait()
        utilisateur = Utilisateur.objects.get(pk=user_id)
        approuver_reallocation(
            utilisateur=utilisateur, reallocation=Reallocation.objects.get(pk=realloc_id)
        )
        return "approuvee"
    except ReallocationRefusee:
        return "refusee"
    finally:
        connections.close_all()


def test_deux_reallocations_simultanees_sur_une_meme_source_nen_laissent_aboutir_quune(realloc):
    organisation, _, profils, accord, cat, _ = realloc
    r1 = _demander(realloc, montant=80, date=JUIL)
    r2 = _demander(realloc, montant=80, date=AOUT)  # 80 + 80 > 100 : une seule peut passer
    barriere = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futurs = [
            pool.submit(_approuver_concurrent, organisation.id, profils[u].id, r.pk, barriere)
            for u, r in (("vera", r1), ("victor", r2))
        ]
        issues = sorted(f.result() for f in futurs)
    assert issues == ["approuvee", "refusee"]
    assert Reallocation.objects.filter(status="approved").count() == 1
    assert ProfilDecaissement.objects.count() == 2  # V1 et une seule nouvelle version
    gagnante = Reallocation.objects.get(status="approved")
    assert _alloc(gagnante.profil_cree, cat["serv"]) == 20  # solde exact : 100 − 80
    assert (
        _alloc(gagnante.profil_cree, cat["serv"]) + _alloc(gagnante.profil_cree, cat["biens"])
        == 200
    )


def test_deux_reallocations_sur_des_categories_distinctes_ne_perdent_aucune_mise_a_jour(realloc):
    """Sans le verrou de l'accord, la seconde copierait un profil devenu périmé et effacerait le
    transfert de la première (aucune catégorie en commun : seul l'accord les sérialise)."""
    organisation, _, profils, accord, cat, _ = realloc
    r1 = _demander(realloc, montant=10, date=JUIL)  # SERV -> BIENS
    r2 = _demander(realloc, montant=5, date=AOUT, source=cat["biens_a"], cible=cat["div"])
    barriere = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futurs = [
            pool.submit(_approuver_concurrent, organisation.id, profils[u].id, r.pk, barriere)
            for u, r in (("vera", r1), ("victor", r2))
        ]
        issues = [f.result() for f in futurs]
    assert "approuvee" in issues
    attendu = {c: M(100) for c in ("serv", "biens", "biens_a", "div")}
    for r, (source, cible) in ((r1, ("serv", "biens")), (r2, ("biens_a", "div"))):
        r.refresh_from_db()
        if r.status == "approved":
            attendu[source] -= r.montant
            attendu[cible] += r.montant
    final = profil_en_vigueur(accord, D(2027, 1, 1))
    assert {c: _alloc(final, cat[c]) for c in attendu} == attendu  # aucun transfert effacé


def test_deux_approbations_simultanees_de_la_meme_reallocation_ne_creent_quune_version(realloc):
    organisation, _, profils, _, _, _ = realloc
    r = _demander(realloc, montant=10)
    barriere = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futurs = [
            pool.submit(_approuver_concurrent, organisation.id, profils[u].id, r.pk, barriere)
            for u in ("vera", "victor")
        ]
        issues = sorted(f.result() for f in futurs)
    assert issues == ["approuvee", "refusee"]
    assert ProfilDecaissement.objects.count() == 2
    assert Reallocation.objects.get(pk=r.pk).profil_cree is not None


# --- avenant -------------------------------------------------------------------------------


def _avenant(realloc, **champs):
    organisation, projet, profils, accord, cat, _ = realloc
    donnees = {
        "utilisateur": profils["vera"],
        "accord": accord,
        "reference": "AV-1",
        "date_avenant": JUIL,
        "document": _document(organisation, projet),
        "montant_revise": M(1200),
        "motif": "Financement additionnel",
        "allocations": {cat["serv"]: M(500), cat["biens"]: M(400)},
        "dates": {"closing_date": D(2028, 12, 31)},
    } | champs
    return enregistrer_avenant(**donnees)


def test_un_avenant_cree_la_nouvelle_version_du_profil_et_laisse_lancienne_intacte(realloc):
    _, _, _, accord, cat, v1 = realloc
    avenant = _avenant(realloc)

    v2 = ProfilDecaissement.objects.get(pk=avenant.profile_version_id)
    v1.refresh_from_db()
    assert (v2.version, v2.status, v2.valid_from, v2.closing_date) == (
        2,
        "active",
        JUIL,
        D(2028, 12, 31),
    )
    assert (_alloc(v2, cat["serv"]), _alloc(v2, cat["biens"])) == (500, 400)
    assert (_alloc(v1, cat["serv"]), v1.closing_date, v1.valid_to) == (100, None, JUIL)
    situation = situation_avant_apres(avenant)
    assert (situation["montant_avant"], situation["montant_apres"], situation["variation"]) == (
        1000,
        1200,
        200,
    )
    assert situation["profile_version_id"] == v2.id
    ecarts = comparer_versions(v1, v2)
    assert set(ecarts.parametres.modifies[0][1]) == {"valid_from", "valid_to", "closing_date"}
    assert {c for c, _ in ecarts.categories.modifies} == {"SERV", "BIENS"}
    assert ecarts.methodes.identiques and not ecarts.methodes.modifies


def test_un_avenant_dont_le_profil_est_incomplet_nest_pas_enregistre(realloc):
    _, _, _, _, cat, _ = realloc
    avant = ProfilDecaissement.objects.count()
    with pytest.raises(ActivationRefusee, match="dépassent le montant de l'accord"):
        _avenant(realloc, montant_revise=M(1000), allocations={cat["serv"]: M(950)})
    assert AvenantAccord.objects.count() == 0  # tout ou rien
    assert ProfilDecaissement.objects.count() == avant


def test_un_avenant_sur_un_accord_sans_profil_est_enregistre_seul(drf):  # noqa: F811
    organisation, projet, profils, accord, _ = drf
    vera = Utilisateur.objects.create_user("vera", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id,
        code="VERA",
        label={"fr": "v"},
        operations=["consulter", "valider", "parametrer"],
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=vera.id, project_id=projet.id, role=role
    )
    avenant = enregistrer_avenant(
        utilisateur=vera,
        accord=accord,
        reference="AV-1",
        date_avenant=JUIL,
        document=_document(organisation, projet),
        montant_revise=M(1500),
    )
    assert avenant.profile_version_id is None and ProfilDecaissement.objects.count() == 0
    with pytest.raises(PermissionDenied, match="valider"):  # dora paramètre mais ne valide pas
        enregistrer_avenant(
            utilisateur=profils["dora"],
            accord=accord,
            reference="AV-2",
            date_avenant=AOUT,
            document=_document(organisation, projet, nom="Avenant 2"),
            montant_revise=M(1600),
        )
    assert AvenantAccord.objects.count() == 1


def test_un_avenant_exige_les_habilitations_parametrer_et_valider(realloc):
    _, _, profils, _, _, _ = realloc
    with pytest.raises(PermissionDenied):
        _avenant(realloc, utilisateur=profils["dora"])


def test_une_seconde_reallocation_a_la_meme_date_est_refusee_nettement(realloc):
    """Deux versions ne prennent pas effet le même jour : la seconde prend une date postérieure."""
    _, _, profils, _, _, _ = realloc
    premiere = _demander(realloc, montant=10, date=JUIL)
    seconde = _demander(realloc, montant=10, date=JUIL)
    approuver_reallocation(utilisateur=profils["vera"], reallocation=premiere)
    with pytest.raises(ReallocationRefusee, match="prend déjà effet le 2026-07-01"):
        approuver_reallocation(utilisateur=profils["victor"], reallocation=seconde)
    assert ProfilDecaissement.objects.count() == 2


def test_un_avenant_est_refuse_quand_aucun_profil_nest_en_vigueur_a_sa_date(realloc):
    _, _, _, _, _, v1 = realloc
    ProfilDecaissement.objects.filter(pk=v1.pk).update(valid_to=D(2026, 3, 1))
    with pytest.raises(ActivationRefusee, match="Aucun profil de décaissement"):
        _avenant(realloc, date_avenant=JUIL)
    assert AvenantAccord.objects.count() == 0


def test_la_base_refuse_une_reallocation_liee_au_profil_dun_autre_accord(realloc):
    organisation, projet, profils, accord, cat, _ = realloc
    autre = _accord(projet, profils, accord.bailleur, "DON-2", devise="DJF", montant_initial="500")
    etranger = creer_profil(organisation, projet, autre, statut="draft", regles=[])
    r = _demander(realloc)
    with pytest.raises(IntegrityError, match="profil de son accord"):
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(
                "UPDATE niveau3_config_reallocation SET status='approved', approbateur=%s, "
                "decided_at=now(), profil_cree_id=%s WHERE id=%s",
                [profils["vera"].id, etranger.id, r.id],
            )


def test_deux_categories_de_devises_differentes_ne_se_reallouent_pas(realloc):
    _, _, profils, accord, cat, _ = realloc
    usd = creer_categorie(
        utilisateur=profils["dora"],
        accord=accord,
        code="USD",
        label={"fr": "x"},
        plafond="10",
        devise="USD",
    )
    with pytest.raises(ReallocationRefusee, match="même devise"):
        _demander(realloc, cible=usd)
