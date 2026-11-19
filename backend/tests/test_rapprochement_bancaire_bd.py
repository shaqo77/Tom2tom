"""Rapprochement bancaire. Voir L3-T07 (partie b).

Rapprochement en monnaie de tenue ET en devise, avec les écarts de change en écritures explicites.
Contrôle (même esprit que le lettrage) : rapprocher puis annuler laisse les lignes et les
mouvements dans leur état initial, et les deux opérations sont au journal d'audit.
"""

import datetime
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, connections
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from niveau1_socle.comptabilite.models import Ecriture, Journal, LigneEcriture
from niveau1_socle.exercices.models import Exercice
from niveau1_socle.exercices.services import ClotureImpossible, cloturer_periode
from niveau1_socle.financements.models import CompteBancaire
from niveau1_socle.financements.services import creer_compte_bancaire
from niveau1_socle.rapprochement.models import MouvementReleve, Rapprochement
from niveau1_socle.rapprochement.services import (
    RapprochementImpossible,
    ReleveInvalide,
    annuler_rapprochement,
    etat_de_rapprochement,
    importer_mouvements,
    rapprocher,
)
from tests.outils import _compte, connexion_proprietaire
from tests.test_cycle_ecriture_bd import _poser, decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = Decimal
GAIN, PERTE = "766", "666"


@pytest.fixture
def banque(cadre):  # noqa: F811
    """Un compte en franc de Djibouti et un compte en dollars ; claire comptabilise."""
    organisation, projet, profils, bailleur = cadre
    for code in (GAIN, PERTE, "7061"):
        _compte(organisation.id, code)
    djf = creer_compte_bancaire(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code="CB-DJF",
        type="operationnel",
        devise="DJF",
        banque="BCD",
        numero="DJ-1",
    )
    usd = creer_compte_bancaire(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code="CB-USD",
        type="designe",
        devise="USD",
        banque="BCD",
        numero="DJ-2",
    )
    return organisation, projet, profils, djf, usd


def _ligne(organisation, projet, compte, montant, *, base=None, jour=10, mois=2, statut="posted"):
    """Une ligne de grand livre sur le compte bancaire. `montant` : devise du compte (positif =
    encaissement) ; `base` : sa valeur en monnaie de tenue à l'écriture (par défaut, égale)."""
    montant = D(str(montant))
    base = montant if base is None else D(str(base))
    etrangere = compte.devise_id != "DJF"
    exercice = Exercice.objects.get(project_id=projet.id, annee=2026)
    periode = exercice.periodes.get(numero=mois)
    journal, _ = Journal.objects.get_or_create(
        org_id=organisation.id, code="BQ", defaults={"label": {"fr": "Banque"}}
    )
    from django.db import transaction

    with transaction.atomic():
        ecriture = Ecriture.objects.create(
            org_id=organisation.id,
            project_id=projet.id,
            exercice=exercice,
            periode=periode,
            journal=journal,
            accounting_date=datetime.date(2026, mois, jour),
            label="Banque",
            status="draft",
            currency_id=compte.devise_id,
            fx_rate=D(1),
            origin="saisie",
        )
        commun = {
            "org_id": organisation.id,
            "project_id": projet.id,
            "entry": ecriture,
            "currency_id": compte.devise_id,
            "fx_rate": (abs(base) / abs(montant)) if etrangere else D(1),
        }
        sens_banque = {"debit": base} if montant > 0 else {"credit": -base}
        cur_banque = {"debit_cur": montant} if montant > 0 else {"credit_cur": -montant}
        ligne = LigneEcriture.objects.create(
            line_no=1,
            account=_compte(organisation.id, "5211"),
            bank_account_id=compte.pk,
            **sens_banque,
            **(cur_banque if etrangere else {}),
            **commun,
        )
        LigneEcriture.objects.create(
            line_no=2,
            account=_compte(organisation.id, "7061" if montant > 0 else "6011"),
            **({"credit": base} if montant > 0 else {"debit": -base}),
            **commun,
        )
    if statut != "draft":
        from django.utils import timezone

        Ecriture.objects.filter(pk=ecriture.pk).update(
            status="posted", posted_at=timezone.now(), posted_by=uuid.uuid4()
        )
    return ligne


def _mouvement(compte, reference, montant, *, jour=11, mois=2, taux=None):
    return {
        "reference": reference,
        "date": datetime.date(2026, mois, jour),
        "montant": montant,
        "libelle": f"Relevé {reference}",
        **({"taux": taux} if taux is not None else {}),
    }


def _importer(profils, compte, *mouvements):
    nouveaux, _ = importer_mouvements(
        utilisateur=profils["claire"], compte=compte, mouvements=list(mouvements)
    )
    return nouveaux


def _rapprocher(profils, compte, lignes, mouvements, **champs):
    return rapprocher(
        utilisateur=profils["claire"], compte=compte, lignes=lignes, mouvements=mouvements, **champs
    )


def _instantane(ligne):
    valeurs = LigneEcriture.objects.filter(pk=ligne.pk).values().get()
    valeurs.pop("bank_match_id")
    valeurs.pop("updated_at", None)
    return valeurs


# --- import du relevé ---------------------------------------------------------------------


def test_importer_un_releve_est_rejouable_sans_doublon(banque):
    organisation, projet, profils, djf, usd = banque
    releve = [_mouvement(djf, "R1", "1000"), _mouvement(djf, "R2", "-250")]
    nouveaux, ignores = importer_mouvements(
        utilisateur=profils["claire"], compte=djf, mouvements=releve
    )
    assert (len(nouveaux), ignores) == (2, 0)
    nouveaux, ignores = importer_mouvements(
        utilisateur=profils["claire"], compte=djf, mouvements=releve + [_mouvement(djf, "R3", "5")]
    )
    assert (len(nouveaux), ignores) == (1, 2)
    assert MouvementReleve.objects.filter(compte=djf).count() == 3
    with pytest.raises(ReleveInvalide, match="d'autres valeurs"):
        importer_mouvements(
            utilisateur=profils["claire"], compte=djf, mouvements=[_mouvement(djf, "R1", "1001")]
        )


@pytest.mark.parametrize(
    "mouvement, message",
    [
        ({"reference": " ", "date": datetime.date(2026, 2, 1), "montant": "1"}, "référence"),
        ({"reference": "X", "date": datetime.date(2026, 2, 1), "montant": "0"}, "montant nul"),
        (
            {"reference": "X", "date": datetime.date(2026, 2, 1), "montant": "1", "taux": "0"},
            "taux non positif",
        ),
        (
            {"reference": "X", "date": datetime.date(2026, 2, 1), "montant": "1", "taux": "2"},
            "pas de taux",
        ),
    ],
)
def test_un_mouvement_invalide_est_refuse_sur_un_compte_en_monnaie_de_tenue(
    banque, mouvement, message
):
    organisation, projet, profils, djf, usd = banque
    with pytest.raises(ReleveInvalide, match=message):
        importer_mouvements(utilisateur=profils["claire"], compte=djf, mouvements=[mouvement])
    assert MouvementReleve.objects.count() == 0


def test_la_meme_reference_deux_fois_dans_un_import_est_refusee(banque):
    organisation, projet, profils, djf, usd = banque
    with pytest.raises(ReleveInvalide, match="deux fois"):
        _importer(profils, djf, _mouvement(djf, "R1", "1"), _mouvement(djf, "R1", "2"))


def test_le_montant_valorise_d_un_mouvement_en_devise_est_arrondi_a_la_monnaie_de_tenue(banque):
    organisation, projet, profils, djf, usd = banque
    (m,) = _importer(profils, usd, _mouvement(usd, "U1", "100.55", taux="177.5"))
    assert m.montant_base == D("17848")  # 100,55 × 177,5 = 17 847,625 -> franc sans décimale


# --- rapprocher ---------------------------------------------------------------------------


def test_rapprocher_une_ligne_et_un_mouvement_en_monnaie_de_tenue(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, djf, 1000)
    (m,) = _importer(profils, djf, _mouvement(djf, "R1", "1000"))
    avant = _instantane(ligne)

    r = _rapprocher(profils, djf, [ligne], [m])

    assert (r.code, r.status, r.ecart_change, r.ecriture_ecart_id) == (
        "R00001",
        "actif",
        D(0),
        None,
    )
    ligne.refresh_from_db(), m.refresh_from_db()
    assert ligne.bank_match_id == r.pk and m.rapprochement_id == r.pk
    assert _instantane(ligne) == avant  # rien d'autre n'a bougé : la ligne reste immuable
    assert not Ecriture.objects.filter(origin_module="rapprochement").exists()  # pas d'écart


def test_un_rapprochement_peut_apparier_plusieurs_lignes_a_un_mouvement(banque):
    organisation, projet, profils, djf, usd = banque
    l1 = _ligne(organisation, projet, djf, 600)
    l2 = _ligne(organisation, projet, djf, 400, jour=12)
    (m,) = _importer(profils, djf, _mouvement(djf, "VIR", "1000"))
    r = _rapprocher(profils, djf, [l1, l2], [m])
    assert LigneEcriture.objects.filter(bank_match_id=r.pk).count() == 2


def test_un_groupe_non_solde_en_devise_est_refuse_avec_tous_les_motifs(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, djf, 1000)
    autre_compte = _ligne(organisation, projet, usd, 100, base=17700)
    (m,) = _importer(profils, djf, _mouvement(djf, "R1", "999"))
    with pytest.raises(RapprochementImpossible) as erreur:
        _rapprocher(profils, djf, [ligne, autre_compte], [m])
    texte = str(erreur.value)
    assert "n'est pas celle de ce compte" in texte and "pas en DJF" not in texte
    with pytest.raises(RapprochementImpossible, match="écart -1"):
        _rapprocher(profils, djf, [ligne], [m])
    with pytest.raises(RapprochementImpossible, match="au moins une ligne et un mouvement"):
        _rapprocher(profils, djf, [], [m])
    assert Rapprochement.objects.count() == 0


def test_on_ne_rapproche_ni_un_brouillon_ni_deux_fois(banque):
    organisation, projet, profils, djf, usd = banque
    brouillon = _ligne(organisation, projet, djf, 50, statut="draft")
    ligne = _ligne(organisation, projet, djf, 100)
    m1, m2 = _importer(profils, djf, _mouvement(djf, "A", "100"), _mouvement(djf, "B", "100"))
    with pytest.raises(RapprochementImpossible, match="lignes comptabilisées"):
        _rapprocher(profils, djf, [brouillon], [m1])
    _rapprocher(profils, djf, [ligne], [m1])
    with pytest.raises(RapprochementImpossible, match="déjà rapprochée"):
        _rapprocher(profils, djf, [ligne], [m2])
    ligne2 = _ligne(organisation, projet, djf, 100, jour=13)
    with pytest.raises(RapprochementImpossible, match="déjà rapproché"):
        _rapprocher(profils, djf, [ligne2], [m1])


def test_rapprocher_en_periode_close_reste_possible(banque):
    organisation, projet, profils, djf, usd = banque
    from tests.outils import fermer_sans_controle

    ligne = _ligne(organisation, projet, djf, 100, mois=3)
    (m,) = _importer(profils, djf, _mouvement(djf, "R1", "100", mois=3))
    fermer_sans_controle(3)
    assert _rapprocher(profils, djf, [ligne], [m]).status == "actif"  # comme le lettrage


# --- les écarts de change en écritures explicites ---------------------------------------------


def test_un_ecart_de_change_favorable_devient_une_ecriture_explicite(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, usd, 1000, base=177000)  # comptabilisé à 177
    (m,) = _importer(profils, usd, _mouvement(usd, "U1", "1000", taux="177.5"))  # relevé à 177,5
    assert m.montant_base == D(177500)

    r = _rapprocher(profils, usd, [ligne], [m], compte_gain_change=GAIN, compte_perte_change=PERTE)

    assert r.ecart_change == D(500)
    ecart = Ecriture.objects.get(pk=r.ecriture_ecart_id)
    assert (ecart.status, ecart.journal.code, ecart.origin, ecart.origin_module) == (
        "posted",
        "CHG",
        "module",
        "rapprochement",
    )
    assert ecart.number.startswith("CHG-2026-")
    bancaire = ecart.lignes.get(account__code="5211")
    resultat = ecart.lignes.get(account__code=GAIN)
    assert (bancaire.debit, bancaire.credit, bancaire.debit_cur, bancaire.credit_cur) == (
        D(500),
        D(0),
        D(0),
        D(0),
    )  # une revalorisation : aucun montant en devise
    assert (resultat.credit, resultat.debit) == (D(500), D(0))
    # La ligne d'écart fait partie du groupe : Σ grand livre = Σ relevé, en devise ET en base.
    groupe = LigneEcriture.objects.filter(bank_match_id=r.pk)
    assert groupe.count() == 2
    assert sum(li.debit - li.credit for li in groupe) == D(177500)
    assert sum(li.debit_cur - li.credit_cur for li in groupe) == D(1000)
    assert verifier_chaine(organisation.id) is None


def test_un_ecart_de_change_defavorable_va_en_perte(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, usd, 1000, base=177000)
    (m,) = _importer(profils, usd, _mouvement(usd, "U1", "1000", taux="176.8"))
    r = _rapprocher(profils, usd, [ligne], [m], compte_gain_change=GAIN, compte_perte_change=PERTE)
    assert r.ecart_change == D(-200)
    ecart = Ecriture.objects.get(pk=r.ecriture_ecart_id)
    assert ecart.lignes.get(account__code="5211").credit == D(200)
    assert ecart.lignes.get(account__code=PERTE).debit == D(200)


def test_un_ecart_sans_compte_de_change_ou_en_periode_close_est_refuse(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, usd, 1000, base=177000)
    (m,) = _importer(profils, usd, _mouvement(usd, "U1", "1000", taux="177.5"))
    with pytest.raises(RapprochementImpossible, match="compte_gain_change"):
        _rapprocher(profils, usd, [ligne], [m], compte_perte_change=PERTE)
    from tests.outils import fermer_sans_controle

    fermer_sans_controle(2)
    with pytest.raises(Exception, match="période"):
        _rapprocher(profils, usd, [ligne], [m], compte_gain_change=GAIN)
    ligne.refresh_from_db()
    assert (
        ligne.bank_match_id is None
        and not Ecriture.objects.filter(origin_module="rapprochement").exists()
    )  # rien n'a survécu à l'échec


def test_pas_d_ecart_de_change_quand_les_valorisations_concordent(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, usd, 1000, base=177500)
    (m,) = _importer(profils, usd, _mouvement(usd, "U1", "1000", taux="177.5"))
    r = _rapprocher(profils, usd, [ligne], [m])  # aucun compte de change requis
    assert r.ecart_change == D(0) and r.ecriture_ecart_id is None


def test_la_base_refuse_un_groupe_non_solde_en_monnaie_de_tenue_sans_ecart_explicite(banque):
    """Même sans passer par le service : l'écart de change ne se glisse pas en silence."""
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, usd, 1000, base=177000)
    (m,) = _importer(profils, usd, _mouvement(usd, "U1", "1000", taux="177.5"))
    with connexion_proprietaire() as admin:
        admin.autocommit = False
        rid = uuid.uuid4()
        admin.execute(
            """INSERT INTO rapprochement_rapprochement (id, created_at, updated_at, org_id,
                   project_id, compte_id, code, status, rapproche_at, ecart_change,
                   motif_annulation)
               VALUES (%s, now(), now(), %s, %s, %s, 'RX', 'actif', now(), 0, '')""",
            [rid, organisation.id, projet.id, usd.pk],
        )
        admin.execute(
            "UPDATE comptabilite_ligneecriture SET bank_match_id = %s WHERE id = %s",
            [rid, ligne.pk],
        )
        admin.execute(
            "UPDATE rapprochement_mouvementreleve SET rapprochement_id = %s WHERE id = %s",
            [rid, m.pk],
        )
        with pytest.raises(Exception, match="monnaie de tenue : grand livre 177000.*relevé 177500"):
            admin.commit()


def test_la_base_refuse_un_groupe_non_solde_en_devise(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, usd, 1000, base=177000)
    (m,) = _importer(profils, usd, _mouvement(usd, "U1", "999", taux="177"))
    with connexion_proprietaire() as admin:
        admin.autocommit = False
        rid = uuid.uuid4()
        admin.execute(
            """INSERT INTO rapprochement_rapprochement (id, created_at, updated_at, org_id,
                   project_id, compte_id, code, status, rapproche_at, ecart_change,
                   motif_annulation)
               VALUES (%s, now(), now(), %s, %s, %s, 'RX', 'actif', now(), 0, '')""",
            [rid, organisation.id, projet.id, usd.pk],
        )
        admin.execute(
            "UPDATE comptabilite_ligneecriture SET bank_match_id = %s WHERE id = %s",
            [rid, ligne.pk],
        )
        admin.execute(
            "UPDATE rapprochement_mouvementreleve SET rapprochement_id = %s WHERE id = %s",
            [rid, m.pk],
        )
        with pytest.raises(Exception, match="pas soldé en devise"):
            admin.commit()


# --- annuler : le contrôle de la tâche ------------------------------------------------------


def test_rapprocher_puis_annuler_laisse_lignes_et_mouvements_dans_leur_etat_initial(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, usd, 1000, base=177000)
    (m,) = _importer(profils, usd, _mouvement(usd, "U1", "1000", taux="177.5"))
    avant_ligne = LigneEcriture.objects.filter(pk=ligne.pk).values().get()
    avant_mouvement = MouvementReleve.objects.filter(pk=m.pk).values().get()

    r = _rapprocher(profils, usd, [ligne], [m], compte_gain_change=GAIN)
    with pytest.raises(RapprochementImpossible, match="motif"):
        annuler_rapprochement(r, utilisateur=profils["claire"], motif=" ")
    annuler_rapprochement(r, utilisateur=profils["claire"], motif="Mauvais appariement")

    assert LigneEcriture.objects.filter(pk=ligne.pk).values().get() == avant_ligne
    assert MouvementReleve.objects.filter(pk=m.pk).values().get() == avant_mouvement
    assert (r.status, r.motif_annulation, r.annule_by) == (
        "annule",
        "Mauvais appariement",
        profils["claire"].id,
    )
    # L'écriture d'écart n'est jamais supprimée : elle est contre-passée, le net est nul.
    assert r.ecriture_ecart_annulation_id is not None
    inverse = Ecriture.objects.get(pk=r.ecriture_ecart_annulation_id)
    assert (inverse.status, inverse.reverses_id) == ("posted", r.ecriture_ecart_id)
    net = sum(
        li.debit - li.credit
        for li in LigneEcriture.objects.filter(entry_id__in=[r.ecriture_ecart_id, inverse.pk])
    )
    assert net == D(0)
    assert LigneEcriture.objects.filter(bank_match_id__isnull=False).count() == 0
    with connection.cursor() as cur:
        cur.execute(
            "SELECT action FROM core_auditlog WHERE action IN "
            "('bank_movements_imported', 'bank_reconciled', 'bank_unreconciled') ORDER BY id"
        )
        assert [a for (a,) in cur.fetchall()] == [
            "bank_movements_imported",
            "bank_reconciled",
            "bank_unreconciled",
        ]
    assert verifier_chaine(organisation.id) is None


def test_apres_annulation_les_lignes_se_rapprochent_a_nouveau_sous_un_nouveau_code(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, djf, 100)
    (m,) = _importer(profils, djf, _mouvement(djf, "R1", "100"))
    r1 = _rapprocher(profils, djf, [ligne], [m])
    annuler_rapprochement(r1, utilisateur=profils["claire"], motif="Test")
    with pytest.raises(RapprochementImpossible, match="déjà annulé"):
        annuler_rapprochement(r1, utilisateur=profils["claire"], motif="Encore")
    r2 = _rapprocher(profils, djf, [ligne], [m])
    assert (r1.code, r2.code) == ("R00001", "R00002")  # un code n'est jamais réutilisé


def test_annuler_exige_une_periode_ouverte_pour_la_contrepassation_de_l_ecart(banque):
    organisation, projet, profils, djf, usd = banque
    from tests.outils import fermer_sans_controle

    ligne = _ligne(organisation, projet, usd, 1000, base=177000)
    (m,) = _importer(profils, usd, _mouvement(usd, "U1", "1000", taux="177.5"))
    r = _rapprocher(profils, usd, [ligne], [m], compte_gain_change=GAIN)
    fermer_sans_controle(2)
    with pytest.raises(Exception, match="période"):
        annuler_rapprochement(r, utilisateur=profils["claire"], motif="Test")
    r.refresh_from_db()
    assert r.status == "actif"  # tout ou rien
    annuler_rapprochement(
        r, utilisateur=profils["claire"], motif="Test", date_comptable=datetime.date(2026, 4, 2)
    )
    assert r.status == "annule"


# --- l'état de rapprochement ----------------------------------------------------------------


def test_l_etat_de_rapprochement_retrouve_le_solde_comptable_depuis_celui_de_la_banque(banque):
    organisation, projet, profils, djf, usd = banque
    # Rapprochés : un encaissement de 1 000 et un paiement de 300.
    l_enc = _ligne(organisation, projet, djf, 1000, jour=3)
    l_pay = _ligne(organisation, projet, djf, -300, jour=5)
    # En suspens au grand livre : un chèque émis de 120 pas encore débité par la banque.
    _ligne(organisation, projet, djf, -120, jour=20)
    m_enc, m_pay, m_frais = _importer(
        profils,
        djf,
        _mouvement(djf, "E1", "1000", jour=4),
        _mouvement(djf, "P1", "-300", jour=6),
        _mouvement(djf, "FRAIS", "-15", jour=25),
    )  # en suspens au relevé : frais non comptabilisés
    _rapprocher(profils, djf, [l_enc], [m_enc])
    _rapprocher(profils, djf, [l_pay], [m_pay])

    etat = etat_de_rapprochement(
        profils["claire"], djf, datetime.date(2026, 2, 28), solde_ouverture=0
    )
    assert etat.solde_releve == D(685)  # 1000 − 300 − 15
    assert etat.solde_comptable == D(580)  # 1000 − 300 − 120
    assert [m.reference for m in etat.mouvements_en_suspens] == ["FRAIS"]
    assert [montant for _, montant in etat.lignes_en_suspens] == [D(-120)]
    assert etat.ecart == D(0) and etat.justifie  # 685 = 580 + 120 − 15


def test_un_ecart_non_explique_rend_l_etat_non_justifie(banque):
    organisation, projet, profils, djf, usd = banque
    _ligne(organisation, projet, djf, 500)  # une ligne comptabilisée dont le relevé ne dit rien
    _importer(profils, djf, _mouvement(djf, "X", "480"))
    etat = etat_de_rapprochement(profils["claire"], djf, datetime.date(2026, 2, 28))
    # 480 (relevé) contre 500 (grand livre) : la ligne et le mouvement sont tous deux en suspens
    # et ne se compensent pas ; l'écart non expliqué n'est pas masqué.
    assert etat.ecart == D(0)  # expliqué : 480 = 500 − 500 + 480
    assert etat.total_lignes_en_suspens == D(500) and etat.total_mouvements_en_suspens == D(480)
    inconnu = etat_de_rapprochement(
        profils["claire"], djf, datetime.date(2026, 2, 28), solde_ouverture=-50
    )
    assert inconnu.ecart == D(-50) and not inconnu.justifie  # une ouverture mal saisie se voit


def test_l_etat_en_devise_compte_dans_la_devise_du_compte(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, usd, 1000, base=177000)
    (m,) = _importer(profils, usd, _mouvement(usd, "U1", "1000", taux="177.5"))
    _rapprocher(profils, usd, [ligne], [m], compte_gain_change=GAIN)
    etat = etat_de_rapprochement(profils["claire"], usd, datetime.date(2026, 2, 28))
    # 1 000 dollars de chaque côté, et la ligne d'écart (0 dollar) ne fausse pas le solde en devise.
    assert (etat.devise, etat.solde_releve, etat.solde_comptable) == ("USD", D(1000), D(1000))
    assert etat.justifie and etat.lignes_en_suspens == [] and etat.mouvements_en_suspens == []


# --- la clôture mensuelle -------------------------------------------------------------------


def test_un_mouvement_non_rapproche_bloque_la_cloture_de_sa_periode(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, djf, 100, mois=3, jour=10)
    (m,) = _importer(profils, djf, _mouvement(djf, "R1", "100", mois=3, jour=11))
    periode = Exercice.objects.get(project_id=projet.id).periodes.get(numero=3)
    with pytest.raises(
        ClotureImpossible, match=r"Mouvements de relevé non rapprochés : CB-DJF \(1\)"
    ):
        cloturer_periode(periode, utilisateur=None)
    _rapprocher(profils, djf, [ligne], [m])
    assert cloturer_periode(periode, utilisateur=None).status == "close"


def test_une_ligne_en_suspens_au_grand_livre_ne_bloque_pas_la_cloture(banque):
    organisation, projet, profils, djf, usd = banque
    _ligne(organisation, projet, djf, -120, mois=3)  # chèque en circulation : normal
    periode = Exercice.objects.get(project_id=projet.id).periodes.get(numero=3)
    assert cloturer_periode(periode, utilisateur=None).status == "close"


def test_un_mouvement_posterieur_a_la_periode_ne_bloque_pas_sa_cloture(banque):
    organisation, projet, profils, djf, usd = banque
    _importer(profils, djf, _mouvement(djf, "TARD", "10", mois=5))
    periode = Exercice.objects.get(project_id=projet.id).periodes.get(numero=3)
    assert cloturer_periode(periode, utilisateur=None).status == "close"


# --- concurrence, droits, base --------------------------------------------------------------


def _rapprocher_en_concurrence(org_id, user_id, compte_id, ligne_id, mouvement_id, barriere):
    try:
        with connection.cursor() as cur:
            cur.execute("SET app.org_id = %s", [str(org_id)])
        barriere.wait()
        rapprocher(
            utilisateur=Utilisateur.objects.get(pk=user_id),
            compte=CompteBancaire.objects.get(pk=compte_id),
            lignes=[ligne_id],
            mouvements=[mouvement_id],
        )
        return "ok"
    except RapprochementImpossible:
        return "refuse"
    finally:
        connections.close_all()


def test_deux_rapprochements_simultanes_des_memes_lignes_n_en_laissent_qu_un(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, djf, 100)
    m1, m2 = _importer(profils, djf, _mouvement(djf, "A", "100"), _mouvement(djf, "B", "100"))
    barriere = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futurs = [
            pool.submit(
                _rapprocher_en_concurrence,
                organisation.id,
                profils["claire"].id,
                djf.pk,
                ligne.pk,
                m.pk,
                barriere,
            )
            for m in (m1, m2)
        ]
        assert sorted(f.result() for f in futurs) == ["ok", "refuse"]
    assert Rapprochement.objects.filter(status="actif").count() == 1


def test_les_droits_sont_verifies(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, djf, 100)
    (m,) = _importer(profils, djf, _mouvement(djf, "R1", "100"))
    for sans_droit in ("amina", "bruno", "dora"):
        with pytest.raises(PermissionDenied):
            rapprocher(utilisateur=profils[sans_droit], compte=djf, lignes=[ligne], mouvements=[m])
        with pytest.raises(PermissionDenied):
            importer_mouvements(utilisateur=profils[sans_droit], compte=djf, mouvements=[])
    r = _rapprocher(profils, djf, [ligne], [m])
    with pytest.raises(PermissionDenied):
        annuler_rapprochement(r, utilisateur=profils["amina"], motif="x")
    inconnu = Utilisateur.objects.create_user("eve", password="x", org_id=organisation.id)
    with pytest.raises(PermissionDenied):
        etat_de_rapprochement(inconnu, djf, datetime.date(2026, 2, 28))


def test_la_base_garde_les_mouvements_et_les_rapprochements(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, djf, 100)
    (m,) = _importer(profils, djf, _mouvement(djf, "R1", "100"))
    r = _rapprocher(profils, djf, [ligne], [m])
    with connexion_proprietaire() as admin:
        for requete, cible, motif in [
            ("DELETE FROM rapprochement_mouvementreleve WHERE id = %s", m.pk, "ne se supprime pas"),
            (
                "UPDATE rapprochement_mouvementreleve SET montant = 1 WHERE id = %s",
                m.pk,
                "ne change que par son rapprochement",
            ),
            ("DELETE FROM rapprochement_rapprochement WHERE id = %s", r.pk, "on l'annule"),
            (
                "UPDATE rapprochement_rapprochement SET code = 'Z' WHERE id = %s",
                r.pk,
                "ne change que par son annulation",
            ),
        ]:
            with pytest.raises(Exception, match=motif):
                admin.execute(requete, [cible])
        # Libérer le mouvement seul, sans la ligne : le groupe n'a plus de mouvement.
        admin.autocommit = False
        admin.execute(
            "UPDATE rapprochement_mouvementreleve SET rapprochement_id = NULL WHERE id = %s", [m.pk]
        )
        with pytest.raises(Exception, match="au moins une ligne du grand livre et un mouvement"):
            admin.commit()
    annuler_rapprochement(r, utilisateur=profils["claire"], motif="Test")
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="annulé est figé"):
            admin.execute(
                "UPDATE rapprochement_rapprochement SET motif_annulation = 'x' WHERE id = %s",
                [r.pk],
            )


def test_la_base_refuse_de_remettre_des_lignes_dans_un_rapprochement_annule(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, djf, 100)
    (m,) = _importer(profils, djf, _mouvement(djf, "R1", "100"))
    r = _rapprocher(profils, djf, [ligne], [m])
    annuler_rapprochement(r, utilisateur=profils["claire"], motif="Test")
    with connexion_proprietaire() as admin:
        admin.autocommit = False
        admin.execute(
            "UPDATE comptabilite_ligneecriture SET bank_match_id = %s WHERE id = %s",
            [r.pk, ligne.pk],
        )
        admin.execute(
            "UPDATE rapprochement_mouvementreleve SET rapprochement_id = %s WHERE id = %s",
            [r.pk, m.pk],
        )
        with pytest.raises(Exception, match="rapprochement est annulé"):
            admin.commit()


def test_un_mouvement_et_son_compte_sont_du_meme_projet(banque):
    organisation, projet, profils, djf, usd = banque
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="même projet"):
            admin.execute(
                """INSERT INTO rapprochement_mouvementreleve (id, created_at, updated_at, org_id,
                       project_id, compte_id, reference, date_operation, libelle, montant, taux,
                       montant_base)
                   VALUES (gen_random_uuid(), now(), now(), %s, gen_random_uuid(), %s, 'Z',
                           '2026-02-01', '', 10, 1, 10)""",
                [organisation.id, djf.pk],
            )


def test_les_rapprochements_sont_isoles_par_organisation(banque):
    organisation, projet, profils, djf, usd = banque
    ligne = _ligne(organisation, projet, djf, 100)
    (m,) = _importer(profils, djf, _mouvement(djf, "R1", "100"))
    _rapprocher(profils, djf, [ligne], [m])
    autre = _creer_organisation("ORG-B")
    _poser(autre)
    assert Rapprochement.objects.count() == 0 and MouvementReleve.objects.count() == 0
