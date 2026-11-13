"""Lettrage : un groupe de lignes de solde nul sur un même compte de tiers. Voir L3-T07 (a).

Lettrer n'est pas écrire : c'est marquer des lignes déjà comptabilisées, qui restent
immuables. Seul le marqueur `reconciliation_id` change. Le dé-lettrage est tracé et le
lettrage dé-lettré reste en base (son code n'est jamais réutilisé).
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import psycopg
import pytest
from django.db import IntegrityError, connection, connections, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from niveau1_socle.comptabilite.lettrage import LettrageImpossible, delettrer, lettrer
from niveau1_socle.comptabilite.models import Lettrage, LigneEcriture
from niveau1_socle.exercices.models import Periode
from niveau1_socle.exercices.services import cloturer_periode
from tests.outils import connexion_proprietaire, creer_piece
from tests.test_cycle_ecriture_bd import _poser, decor  # noqa: F401
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)


def _facture(org, projet, montant="1000", tiers="FRN-001", **champs):
    """Facture fournisseur comptabilisée : la ligne 4011 est au crédit du tiers."""
    return creer_piece(
        org.id,
        2026,
        champs.pop("periode", 3),
        [
            {"compte": "6011", "debit": montant},
            {"compte": "4011", "credit": montant, "tiers": tiers},
        ],
        project_id=projet.id,
        **champs,
    )


def _reglement(org, projet, montant="1000", tiers="FRN-001", **champs):
    """Règlement : la ligne 4011 est au débit du tiers."""
    return creer_piece(
        org.id,
        2026,
        champs.pop("periode", 4),
        [
            {"compte": "4011", "debit": montant, "tiers": tiers},
            {"compte": "5211", "credit": montant},
        ],
        project_id=projet.id,
        **champs,
    )


def _ligne_tiers(ecriture):
    return ecriture.lignes.get(account__code="4011")


def _audit_lettrage():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT action, actor_id FROM core_auditlog WHERE object_type = 'lettrage' ORDER BY id"
        )
        return cur.fetchall()


def _instantane(lignes):
    return [
        LigneEcriture.objects.filter(pk=ligne.pk).values().get()
        for ligne in sorted(lignes, key=lambda x: x.pk)
    ]


# --- le contrôle de la tâche --------------------------------------------------------------


def test_lettrer_puis_delettrer_laisse_les_lignes_dans_leur_etat_initial(decor):  # noqa: F811
    """Contrôle de L3-T07 (a) : et les deux opérations sont au journal d'audit."""
    organisation, projet, profils = decor
    lignes = [
        _ligne_tiers(_facture(organisation, projet)),
        _ligne_tiers(_reglement(organisation, projet)),
    ]
    avant = _instantane(lignes)

    lettrage = lettrer(lignes, utilisateur=profils["claire"])
    marqueurs = LigneEcriture.objects.filter(pk__in=[x.pk for x in lignes])
    assert {ligne.reconciliation_id for ligne in marqueurs} == {lettrage.pk}
    assert lettrage.status == "actif"

    delettrer(lettrage, utilisateur=profils["claire"], motif="Erreur de rapprochement")
    assert _instantane(lignes) == avant, "LES LIGNES NE SONT PAS REVENUES À LEUR ÉTAT INITIAL"

    assert _audit_lettrage() == [
        ("lettering_created", profils["claire"].id),
        ("lettering_cancelled", profils["claire"].id),
    ]
    assert verifier_chaine(organisation.id) is None


def test_le_lettrage_garde_sa_trace_et_son_code_nest_jamais_reutilise(decor):  # noqa: F811
    organisation, projet, profils = decor
    f1, r1 = (
        _ligne_tiers(_facture(organisation, projet)),
        _ligne_tiers(_reglement(organisation, projet)),
    )
    f2, r2 = (
        _ligne_tiers(_facture(organisation, projet, "50", periode=5)),
        _ligne_tiers(_reglement(organisation, projet, "50", periode=6)),
    )

    premier = lettrer([f1, r1], utilisateur=profils["claire"])
    assert premier.code == "AA"
    delettrer(premier, utilisateur=profils["claire"], motif="Test")
    second = lettrer([f1, r1], utilisateur=profils["claire"])  # on peut relettrer les mêmes lignes
    troisieme = lettrer([f2, r2], utilisateur=profils["claire"])

    assert (second.code, troisieme.code) == ("AB", "AC")
    premier.refresh_from_db()
    assert (premier.status, premier.annule_by, premier.motif_annulation) == (
        "annule",
        profils["claire"].id,
        "Test",
    )
    assert Lettrage.objects.count() == 3


# --- ce qu'on ne lettre pas ---------------------------------------------------------------


def test_un_groupe_non_solde_est_refuse_avec_l_ecart(decor):  # noqa: F811
    organisation, projet, profils = decor
    lignes = [
        _ligne_tiers(_facture(organisation, projet, "1000")),
        _ligne_tiers(_reglement(organisation, projet, "999.99")),
    ]
    with pytest.raises(LettrageImpossible, match="0.01"):
        lettrer(lignes, utilisateur=profils["claire"])
    assert LigneEcriture.objects.filter(reconciliation_id__isnull=False).count() == 0


def test_les_lignes_d_un_lettrage_portent_sur_le_meme_compte_tiers_et_projet(decor):  # noqa: F811
    organisation, projet, profils = decor
    facture = _ligne_tiers(_facture(organisation, projet))
    autre_tiers = _ligne_tiers(_reglement(organisation, projet, tiers="FRN-002"))
    with pytest.raises(LettrageImpossible, match="même tiers"):
        lettrer([facture, autre_tiers], utilisateur=profils["claire"])

    autre_compte = creer_piece(
        organisation.id,
        2026,
        4,
        [
            {"compte": "4012", "debit": "1000", "tiers": "FRN-001"},
            {"compte": "5211", "credit": "1000"},
        ],
        project_id=projet.id,
    ).lignes.get(account__code="4012")
    with pytest.raises(LettrageImpossible, match="même compte"):
        lettrer([facture, autre_compte], utilisateur=profils["claire"])

    sans_tiers = creer_piece(
        organisation.id,
        2026,
        4,
        [{"compte": "4011", "debit": "1000"}, {"compte": "5211", "credit": "1000"}],
        project_id=projet.id,
    ).lignes.get(account__code="4011")
    with pytest.raises(LettrageImpossible, match="tiers"):
        lettrer([facture, sans_tiers], utilisateur=profils["claire"])


def test_on_ne_lettre_ni_une_ligne_seule_ni_une_ligne_deja_lettree(decor):  # noqa: F811
    organisation, projet, profils = decor
    f, r = (
        _ligne_tiers(_facture(organisation, projet)),
        _ligne_tiers(_reglement(organisation, projet)),
    )
    with pytest.raises(LettrageImpossible, match="au moins deux"):
        lettrer([f], utilisateur=profils["claire"])

    lettrer([f, r], utilisateur=profils["claire"])
    with pytest.raises(LettrageImpossible, match="déjà lettrée"):
        lettrer([f, r], utilisateur=profils["claire"])


@pytest.mark.parametrize("statut", ["draft", "validated"])
def test_on_ne_lettre_que_des_lignes_comptabilisees(decor, statut):  # noqa: F811
    organisation, projet, profils = decor
    facture = _ligne_tiers(_facture(organisation, projet))
    brouillon = _ligne_tiers(_reglement(organisation, projet, statut=statut))
    with pytest.raises(LettrageImpossible, match="comptabilisées"):
        lettrer([facture, brouillon], utilisateur=profils["claire"])


def test_en_devise_le_groupe_doit_aussi_etre_solde_dans_la_devise(decor):  # noqa: F811
    organisation, projet, profils = decor
    facture = creer_piece(
        organisation.id,
        2026,
        3,
        [
            {"compte": "6011", "debit": "1000"},
            {"compte": "4011", "credit": "1000", "credit_cur": "10", "tiers": "FRN-001"},
        ],
        project_id=projet.id,
        devise="USD",
        taux="100",
    )
    reglement = creer_piece(
        organisation.id,
        2026,
        4,
        [
            {"compte": "4011", "debit": "1000", "debit_cur": "9.5", "tiers": "FRN-001"},
            {"compte": "5211", "credit": "1000"},
        ],
        project_id=projet.id,
        devise="USD",
        taux="100",
    )
    with pytest.raises(LettrageImpossible, match="devise"):
        lettrer([_ligne_tiers(facture), _ligne_tiers(reglement)], utilisateur=profils["claire"])


# --- habilitation -------------------------------------------------------------------------


def test_lettrer_exige_l_habilitation_comptabiliser(decor):  # noqa: F811
    organisation, projet, profils = decor
    lignes = [
        _ligne_tiers(_facture(organisation, projet)),
        _ligne_tiers(_reglement(organisation, projet)),
    ]
    with pytest.raises(PermissionDenied):
        lettrer(lignes, utilisateur=profils["bruno"])  # bruno ne peut que valider
    lettrage = lettrer(lignes, utilisateur=profils["claire"])
    with pytest.raises(PermissionDenied):
        delettrer(lettrage, utilisateur=profils["bruno"], motif="Non")


def test_le_delettrage_exige_un_motif_et_ne_se_fait_qu_une_fois(decor):  # noqa: F811
    organisation, projet, profils = decor
    lignes = [
        _ligne_tiers(_facture(organisation, projet)),
        _ligne_tiers(_reglement(organisation, projet)),
    ]
    lettrage = lettrer(lignes, utilisateur=profils["claire"])
    with pytest.raises(LettrageImpossible, match="motif"):
        delettrer(lettrage, utilisateur=profils["claire"], motif="  ")
    delettrer(lettrage, utilisateur=profils["claire"], motif="Correction")
    with pytest.raises(LettrageImpossible, match="déjà annulé"):
        delettrer(lettrage, utilisateur=profils["claire"], motif="Encore")


# --- le lettrage ne rouvre pas la comptabilité --------------------------------------------


def test_lettrer_reste_possible_en_periode_close_sans_rouvrir_les_lignes(decor):  # noqa: F811
    organisation, projet, profils = decor
    facture, reglement = _facture(organisation, projet), _reglement(organisation, projet)
    for numero in (3, 4):
        cloturer_periode(Periode.objects.get(exercice__annee=2026, numero=numero), utilisateur=None)

    lettrage = lettrer(
        [_ligne_tiers(facture), _ligne_tiers(reglement)], utilisateur=profils["claire"]
    )
    assert lettrage.status == "actif"

    # Mais rien d'autre ne bouge sur une ligne comptabilisée.
    with pytest.raises(IntegrityError, match="comptabilisée"), transaction.atomic():
        LigneEcriture.objects.filter(pk=_ligne_tiers(facture).pk).update(label="Falsifiée")
    with pytest.raises(IntegrityError, match="comptabilisée"), transaction.atomic():
        LigneEcriture.objects.filter(pk=_ligne_tiers(facture).pk).update(
            reconciliation_id=lettrage.pk, debit=Decimal("1")
        )


# --- garanties posées en base -------------------------------------------------------------


def test_la_base_refuse_un_lettrage_pose_sans_le_service(decor):  # noqa: F811
    """Un groupe non soldé, ou partiel, est refusé au COMMIT, quel que soit l'appelant."""
    organisation, projet, profils = decor
    f = _ligne_tiers(_facture(organisation, projet, "1000"))
    r = _ligne_tiers(_reglement(organisation, projet, "900"))
    lettrage = Lettrage.objects.create(
        org_id=organisation.id,
        code="ZZ",
        account=f.account,
        partner=f.partner,
        project_id=projet.id,
        status="actif",
        lettre_by=profils["claire"].id,
    )
    with pytest.raises(IntegrityError, match="pas soldé"):
        with transaction.atomic():
            LigneEcriture.objects.filter(pk__in=[f.pk, r.pk]).update(reconciliation_id=lettrage.pk)
    with pytest.raises(IntegrityError, match="au moins deux"):
        with transaction.atomic():
            LigneEcriture.objects.filter(pk=f.pk).update(reconciliation_id=lettrage.pk)
    with pytest.raises(IntegrityError, match="violates foreign key|lettrage"):
        with transaction.atomic():
            LigneEcriture.objects.filter(pk=f.pk).update(reconciliation_id=uuid.uuid4())


def test_la_base_refuse_un_delettrage_partiel(decor):  # noqa: F811
    organisation, projet, profils = decor
    lignes = [
        _ligne_tiers(_facture(organisation, projet)),
        _ligne_tiers(_reglement(organisation, projet)),
    ]
    lettrer(lignes, utilisateur=profils["claire"])
    with pytest.raises(IntegrityError, match="au moins deux"):
        with transaction.atomic():
            LigneEcriture.objects.filter(pk=lignes[0].pk).update(reconciliation_id=None)
    assert LigneEcriture.objects.filter(reconciliation_id__isnull=False).count() == 2


def test_un_lettrage_ne_se_modifie_ni_ne_se_supprime_hors_annulation(decor):  # noqa: F811
    organisation, projet, profils = decor
    lignes = [
        _ligne_tiers(_facture(organisation, projet)),
        _ligne_tiers(_reglement(organisation, projet)),
    ]
    lettrage = lettrer(lignes, utilisateur=profils["claire"])

    with pytest.raises(IntegrityError, match="lettrage"), transaction.atomic():
        Lettrage.objects.filter(pk=lettrage.pk).update(code="XX")
    with pytest.raises(IntegrityError, match="lettrage"), transaction.atomic():
        Lettrage.objects.filter(pk=lettrage.pk).delete()
    with pytest.raises(IntegrityError, match="motif|annul"), transaction.atomic():
        Lettrage.objects.filter(pk=lettrage.pk).update(status="annule")  # sans qui, quand, pourquoi
    with connexion_proprietaire() as admin:  # même le propriétaire
        with pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="lettrage"):
            admin.execute("DELETE FROM comptabilite_lettrage WHERE id = %s", [lettrage.pk])


def test_les_lettrages_sont_isoles_par_organisation(decor):  # noqa: F811
    organisation, projet, profils = decor
    lignes = [
        _ligne_tiers(_facture(organisation, projet)),
        _ligne_tiers(_reglement(organisation, projet)),
    ]
    lettrer(lignes, utilisateur=profils["claire"])
    autre = _creer_organisation("ORG-B")
    _poser(autre)
    assert Lettrage.objects.count() == 0


def test_deux_lettrages_simultanes_des_memes_lignes_n_en_laissent_qu_un(decor):  # noqa: F811
    organisation, projet, profils = decor
    ids = [
        _ligne_tiers(_facture(organisation, projet)).pk,
        _ligne_tiers(_reglement(organisation, projet)).pk,
    ]
    barriere = threading.Barrier(2)
    resultats = []

    def tenter():
        try:
            with connection.cursor() as cur:
                cur.execute("SET app.org_id = %s", [str(organisation.id)])
            barriere.wait()
            lettrer(list(LigneEcriture.objects.filter(pk__in=ids)), utilisateur=profils["claire"])
            resultats.append("ok")
        except LettrageImpossible:
            resultats.append("refus")
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        for tache in [pool.submit(tenter), pool.submit(tenter)]:
            tache.result()

    assert sorted(resultats) == ["ok", "refus"]
    assert Lettrage.objects.filter(status="actif").count() == 1
