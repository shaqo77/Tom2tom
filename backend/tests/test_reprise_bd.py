# ruff: noqa: F811, E501
"""La chaîne de reprise : balance d'origine, soldes d'ouverture ou historique, contrôle, signature,
import idempotent. Voir L8-T01 et L8-T02.

Contrôles du plan : écart nul sur la balance générale ET sur le cumul par accord, sinon la reprise
est refusée et l'écart listé ; trois imports du même fichier donnent le même nombre d'écritures.
"""

import datetime
import os
import time
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.erreurs import CodeErreur, ErreurMetier
from niveau1_socle.comptabilite.models import Ecriture, LigneEcriture
from niveau1_socle.exercices.models import Periode
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau1_socle.reprise.models import (
    LigneBalanceOrigine,
    PieceReprise,
    RapportReprise,
    Reprise,
)
from niveau1_socle.reprise.services import (
    controler_reprise,
    generer_soldes_ouverture,
    importer_balance_origine,
    importer_historique,
    ouvrir_reprise,
    reprise_acceptee,
    signer_rapport,
)
from tests.outils import _compte, _valeur_axe, assurer_devises
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import _accord, cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = Decimal
BASCULE = "2026-03-31"

# Trois pièces d'historique : deux dépenses imputées à un accord et un axe, un paiement.
HISTORIQUE = """journal;piece;date;compte;libelle;debit;credit;tiers;accord;axe1
OD;P001;2026-01-15;6011;Fournitures;1000,50;0;;IDA-6789;COMP-A
OD;P001;2026-01-15;5211;Fournitures;0;1000,50;;;
OD;P002;2026-02-10;6011;Carburant;250;0;;IDA-6789;COMP-A
OD;P002;2026-02-10;5211;Carburant;0;250;;;
OD;P003;2026-03-05;6011;Entretien;75,25;0;;;
OD;P003;2026-03-05;5211;Entretien;0;75,25;;;
"""
# La balance d'origine correspondante : 6011 = 1325,75 dont 1250,50 sur l'accord ; 5211 = -1325,75.
BALANCE = """compte;debit;credit;accord;axe1
6011;1250,50;0;IDA-6789;COMP-A
6011;75,25;0;;
5211;0;1325,75;;
"""


@pytest.fixture
def rep(cadre):
    organisation, projet, profils, bailleur = cadre
    assurer_devises()
    _valeur_axe(organisation.id, "COMP-A")
    _compte(organisation.id, "6011")
    _compte(organisation.id, "5211")
    sonia = Utilisateur.objects.create_user("sonia", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id, code="SONIA", label={"fr": "s"}, operations=["consulter", "valider"]
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=sonia.id, project_id=projet.id, role=role
    )
    profils["sonia"] = sonia
    _accord(projet, profils, bailleur, "IDA-6789")
    reprise = ouvrir_reprise(
        utilisateur=profils["dora"],
        project_id=projet.id,
        nom="Bascule TOM2PRO",
        date_bascule=datetime.date(2026, 3, 31),
    )
    return organisation, projet, profils, reprise


def _balance(rep, contenu=BALANCE):
    _, _, profils, reprise = rep
    return importer_balance_origine(
        utilisateur=profils["dora"],
        reprise=reprise,
        contenu=contenu.encode(),
        nom_fichier="balance.csv",
    )


def _historique(rep, contenu=HISTORIQUE):
    _, _, profils, reprise = rep
    return importer_historique(
        utilisateur=profils["dora"],
        reprise=reprise,
        contenu=contenu.encode(),
        nom_fichier="hist.csv",
    )


def _nb_ecritures():
    return Ecriture.objects.filter(origin="import").count()


# --- la balance d'origine ----------------------------------------------------------------------


def test_la_balance_d_origine_se_charge_equilibree(rep):
    assert _balance(rep) == 3
    assert LigneBalanceOrigine.objects.count() == 3
    assert rep[3].balance_sha256 is not None or Reprise.objects.get().balance_sha256 is not None


@pytest.mark.parametrize(
    ("contenu", "attendu"),
    [
        ("compte;debit;credit\n6011;100;0\n5211;0;90\n", "déséquilibrée"),
        ("compte;debit;credit\n9999;100;0\n5211;0;100\n", "9999"),
        ("compte;debit;credit;accord\n6011;100;0;INCONNU\n5211;0;100;\n", "INCONNU"),
        ("compte;debit;credit;axe1\n6011;100;0;ZZZ\n5211;0;100;\n", "ZZZ"),
        ("compte;debit;credit\n6011;abc;0\n5211;0;100\n", "illisible"),
        ("compte;debit;credit\n6011;-5;0\n5211;0;-5\n", "négatif"),
        ("compte;montant\n6011;100\n", "obligatoires"),
        ("compte;debit;credit\n", "aucune ligne"),
    ],
)
def test_une_balance_invalide_est_refusee_sans_rien_ecrire_et_les_lignes_sont_nommees(
    rep, contenu, attendu
):
    with pytest.raises(ErreurMetier, match=attendu):
        _balance(rep, contenu)
    assert LigneBalanceOrigine.objects.count() == 0


def test_rejouer_la_meme_balance_ne_change_rien_et_une_autre_est_refusee(rep):
    _balance(rep)
    _balance(rep)
    assert LigneBalanceOrigine.objects.count() == 3
    with pytest.raises(ErreurMetier) as e:
        _balance(rep, "compte;debit;credit\n6011;1;0\n5211;0;1\n")
    assert e.value.code == CodeErreur.TRANSITION_INTERDITE


# --- l'historique et le contrôle à écart nul ---------------------------------------------------


def test_une_reprise_a_ecart_nul_est_controlee_puis_signee(rep):
    organisation, projet, profils, reprise = rep
    _balance(rep)
    resultat = _historique(rep)
    assert (resultat.creees, resultat.deja_presentes) == (3, 0)
    ecritures = Ecriture.objects.filter(origin="import").order_by("accounting_date")
    assert [e.status for e in ecritures] == ["posted"] * 3 and all(e.number for e in ecritures)
    assert (
        LigneEcriture.objects.filter(agreement_id__isnull=False).count() == 2
    )  # imputations reprises

    rapport = controler_reprise(utilisateur=profils["dora"], reprise=reprise)
    assert rapport.accepte and rapport.ecart_general == 0 and rapport.ecart_accords == 0
    assert rapport.nombre_ecritures == 3 and rapport.ecarts == []
    assert Reprise.objects.get().statut == "controlee" and not reprise_acceptee(projet.id)

    signe = signer_rapport(utilisateur=profils["sonia"], rapport=rapport)
    assert (signe.signe_nom, Reprise.objects.get().statut) == ("sonia", "acceptee")
    assert reprise_acceptee(projet.id)


def test_un_ecart_sur_un_compte_refuse_la_reprise_et_se_liste_ligne_a_ligne(rep):
    _, _, profils, reprise = rep
    _balance(
        rep, BALANCE.replace("75,25", "85,25").replace("1325,75", "1335,75")
    )  # +10 sur 6011 et 5211
    _historique(rep)
    rapport = controler_reprise(utilisateur=profils["dora"], reprise=reprise)
    assert not rapport.accepte and rapport.ecart_general == D("20")  # 10 sur 6011 + 10 sur 5211
    comptes = {e["cle"]: e for e in rapport.ecarts if e["dimension"] == "compte"}
    assert comptes["6011"]["ecart"] == "-10.0000" and comptes["5211"]["ecart"] == "10.0000"
    assert Reprise.objects.get().statut == "refusee"
    with pytest.raises(ErreurMetier, match="écart non nul"):
        signer_rapport(utilisateur=profils["sonia"], rapport=rapport)
    assert not reprise_acceptee(reprise.project_id)


def test_un_ecart_sur_le_cumul_par_accord_refuse_meme_si_les_comptes_sont_justes(rep):
    _, _, profils, reprise = rep
    # Mêmes soldes par compte, mais 75,25 imputés à l'accord dans la source : les comptes collent, l'accord non.
    _balance(
        rep, "compte;debit;credit;accord;axe1\n6011;1325,75;0;IDA-6789;COMP-A\n5211;0;1325,75;;\n"
    )
    _historique(rep)
    rapport = controler_reprise(utilisateur=profils["dora"], reprise=reprise)
    assert rapport.ecart_general == 0 and rapport.ecart_accords == D(
        "150.50"
    )  # 75,25 de part et d'autre
    assert not rapport.accepte
    accords = {e["cle"]: e["ecart"] for e in rapport.ecarts if e["dimension"] == "accord"}
    assert accords == {"IDA-6789": "-75.2500", "": "75.2500"}


def test_un_ecart_d_axe_est_liste_mais_ne_bloque_pas(rep):
    _, _, profils, reprise = rep
    # Comptes et accord justes ; l'axe : la source met tout hors axe.
    _balance(
        rep,
        "compte;debit;credit;accord;axe1\n6011;1250,50;0;IDA-6789;\n6011;75,25;0;;\n5211;0;1325,75;;\n",
    )
    _historique(rep)
    rapport = controler_reprise(utilisateur=profils["dora"], reprise=reprise)
    assert rapport.accepte and {e["dimension"] for e in rapport.ecarts} == {"axe1"}


def test_les_soldes_d_ouverture_generent_une_ecriture_et_se_controlent(rep):
    _, _, profils, reprise = rep
    _balance(rep)
    generer_soldes_ouverture(utilisateur=profils["dora"], reprise=reprise)
    generer_soldes_ouverture(utilisateur=profils["dora"], reprise=reprise)  # idempotent
    assert _nb_ecritures() == 1
    rapport = controler_reprise(utilisateur=profils["dora"], reprise=reprise)
    assert rapport.accepte and rapport.nombre_ecritures == 1


def test_les_deux_modes_s_excluent(rep):
    _, _, profils, reprise = rep
    _balance(rep)
    _historique(rep)
    with pytest.raises(ErreurMetier, match="historique"):
        generer_soldes_ouverture(utilisateur=profils["dora"], reprise=Reprise.objects.get())


def test_sans_balance_ou_sans_ecriture_on_ne_controle_pas(rep):
    _, _, profils, reprise = rep
    with pytest.raises(ErreurMetier):
        controler_reprise(utilisateur=profils["dora"], reprise=reprise)
    _balance(rep)
    with pytest.raises(ErreurMetier, match="Aucune écriture"):
        controler_reprise(utilisateur=profils["dora"], reprise=Reprise.objects.get())


# --- la signature ------------------------------------------------------------------------------


def _rapport_accepte(rep):
    _, _, profils, reprise = rep
    _balance(rep)
    _historique(rep)
    return controler_reprise(utilisateur=profils["dora"], reprise=reprise)


def test_celui_qui_ouvre_la_reprise_ne_la_signe_pas(rep):
    organisation, projet, profils, reprise = rep
    rapport = _rapport_accepte(rep)
    role = Role.objects.create(
        org_id=organisation.id, code="DV", label={"fr": "d"}, operations=["parametrer", "valider"]
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=profils["dora"].id, project_id=projet.id, role=role
    )
    with pytest.raises(ErreurMetier) as e:
        signer_rapport(utilisateur=profils["dora"], rapport=rapport)
    assert e.value.code == CodeErreur.APPROBATION_REQUISE
    with pytest.raises(PermissionDenied):
        signer_rapport(utilisateur=profils["amina"], rapport=rapport)


def test_un_rapport_signe_est_definitif_et_la_base_le_garde(rep):
    _, _, profils, reprise = rep
    rapport = _rapport_accepte(rep)
    signer_rapport(utilisateur=profils["sonia"], rapport=rapport)
    with pytest.raises(ErreurMetier) as e:
        signer_rapport(utilisateur=profils["sonia"], rapport=rapport)
    assert e.value.code == CodeErreur.TRANSITION_INTERDITE
    for modele, champs in (
        (RapportReprise, {"ecart_general": D("1")}),
        (RapportReprise, {"signe_nom": "autre"}),
        (Reprise, {"nom": "autre", "statut": "en_cours"}),
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            modele.objects.update(**champs)
    with pytest.raises(IntegrityError), transaction.atomic():
        Reprise.objects.all().delete()
    with pytest.raises(ErreurMetier, match="acceptée"):
        _historique(rep, HISTORIQUE.replace("P001", "P009"))


def test_la_base_refuse_de_signer_un_rapport_a_ecart_non_nul(rep):
    _, _, profils, reprise = rep
    _balance(rep, BALANCE.replace("1325,75", "1335,75").replace("75,25", "85,25"))
    _historique(rep)
    rapport = controler_reprise(utilisateur=profils["dora"], reprise=reprise)
    with pytest.raises(IntegrityError), transaction.atomic():
        RapportReprise.objects.filter(pk=rapport.pk).update(
            signe_par=profils["sonia"].id, signe_nom="sonia", signe_le=timezone.now()
        )


def test_seul_le_dernier_rapport_se_signe(rep):
    _, _, profils, reprise = rep
    premier = _rapport_accepte(rep)
    controler_reprise(utilisateur=profils["dora"], reprise=Reprise.objects.get())
    with pytest.raises(ErreurMetier, match="plus récent"):
        signer_rapport(utilisateur=profils["sonia"], rapport=premier)


# --- l'import idempotent (L8-T02) --------------------------------------------------------------


def test_trois_imports_du_meme_fichier_donnent_le_meme_nombre_d_ecritures(rep):
    _balance(rep)
    comptes = []
    for _ in range(3):
        _historique(rep)
        comptes.append(
            (_nb_ecritures(), LigneEcriture.objects.count(), PieceReprise.objects.count())
        )
    assert comptes == [(3, 6, 3)] * 3
    numeros = list(Ecriture.objects.filter(origin="import").values_list("number", flat=True))
    assert len(set(numeros)) == 3  # aucun trou ni doublon de numérotation


def test_un_fichier_complete_n_ajoute_que_les_pieces_nouvelles(rep):
    _historique(rep)
    plus = (
        HISTORIQUE
        + "OD;P004;2026-03-20;6011;Nouveau;10;0;;;\nOD;P004;2026-03-20;5211;Nouveau;0;10;;;\n"
    )
    resultat = _historique(rep, plus)
    assert (resultat.creees, resultat.deja_presentes) == (1, 3)
    assert _nb_ecritures() == 4


def test_une_piece_modifiee_dans_la_source_est_un_conflit_pas_un_ecrasement_ni_un_doublon(rep):
    _historique(rep)
    modifie = HISTORIQUE.replace("1000,50", "1000,60")
    with pytest.raises(ErreurMetier, match="contenu différent"):
        _historique(rep, modifie)
    assert _nb_ecritures() == 3
    assert not LigneEcriture.objects.filter(debit=D("1000.60")).exists()


def test_deux_reprises_n_ont_pas_les_memes_cles(rep):
    organisation, projet, profils, reprise = rep
    _historique(rep)
    autre = ouvrir_reprise(
        utilisateur=profils["dora"],
        project_id=projet.id,
        nom="Seconde",
        date_bascule=reprise.date_bascule,
    )
    importer_historique(
        utilisateur=profils["dora"], reprise=autre, contenu=HISTORIQUE.encode(), nom_fichier="h.csv"
    )
    assert (
        _nb_ecritures() == 6
    )  # deux reprises distinctes : deux jeux, chacun idempotent pour lui-même


# --- tout ou rien -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ancien", "nouveau", "attendu"),
    [
        (
            "OD;P003;2026-03-05;5211;Entretien;0;75,25",
            "OD;P003;2026-03-05;5211;Entretien;0;70",
            "déséquilibrée",
        ),
        ("2026-03-05", "2026-04-05", "après la date de bascule"),
        ("2026-03-05", "2031-03-05", "aucune période"),
        ("OD;P003", "XX;P003", "journal « XX » inconnu"),
        ("5211;Entretien", "7777;Entretien", "7777"),
        (
            "OD;P003;2026-03-05;6011;Entretien;75,25;0",
            "OD;P003;2026-03-05;6011;Entretien;75,25;5",
            "débit et crédit",
        ),
    ],
)
def test_une_erreur_arrete_tout_l_import_et_nomme_ses_causes(rep, ancien, nouveau, attendu):
    contenu = HISTORIQUE.replace(ancien, nouveau)
    with pytest.raises(ErreurMetier, match=attendu):
        _historique(rep, contenu)
    assert _nb_ecritures() == 0 and PieceReprise.objects.count() == 0  # même les pièces valides


def test_une_periode_close_refuse_l_import(rep):
    Periode.objects.filter(exercice__annee=2026, numero=2).update(status="close")
    with pytest.raises(ErreurMetier, match="pas ouverte"):
        _historique(rep)
    assert _nb_ecritures() == 0


def test_une_ligne_illisible_est_nommee_avec_son_numero(rep):
    with pytest.raises(ErreurMetier, match="ligne 4"):
        _historique(
            rep,
            HISTORIQUE.replace(
                "OD;P002;2026-02-10;6011;Carburant;250", "OD;P002;2026-02-10;6011;Carburant;deux"
            ),
        )
    assert _nb_ecritures() == 0


def test_la_correspondance_de_colonnes_permet_un_export_aux_en_tetes_differents(rep):
    _, _, profils, reprise = rep
    source = "Jrn;N° pièce;Date;Cpt;Débit;Crédit\nOD;X1;2026-01-05;6011;50;0\nOD;X1;2026-01-05;5211;0;50\n"
    resultat = importer_historique(
        utilisateur=profils["dora"], reprise=reprise, contenu=source.encode(), nom_fichier="s.csv",
        correspondance={"journal": "Jrn", "piece": "N° pièce", "date": "Date", "compte": "Cpt", "debit": "Débit", "credit": "Crédit"},
    )  # fmt: skip
    assert resultat.creees == 1


def test_les_habilitations_sont_exigees(rep):
    organisation, projet, profils, reprise = rep
    with pytest.raises(PermissionDenied):
        importer_historique(
            utilisateur=profils["amina"],
            reprise=reprise,
            contenu=HISTORIQUE.encode(),
            nom_fichier="h.csv",
        )
    with pytest.raises(PermissionDenied):
        ouvrir_reprise(
            utilisateur=profils["amina"],
            project_id=projet.id,
            nom="x",
            date_bascule=reprise.date_bascule,
        )


# --- le volume ---------------------------------------------------------------------------------


def _gros_fichier(n):
    lignes = ["journal;piece;date;compte;libelle;debit;credit;tiers;accord;axe1"]
    for i in range(n):
        jour = f"2026-{1 + i % 3:02d}-{1 + i % 28:02d}"
        montant = f"{100 + i % 900},{i % 100:02d}"
        accord = "IDA-6789" if i % 2 == 0 else ""
        lignes.append(f"OD;G{i:06d};{jour};6011;Dépense {i};{montant};0;;{accord};COMP-A")
        lignes.append(f"OD;G{i:06d};{jour};5211;Dépense {i};0;{montant};;;")
    return "\n".join(lignes) + "\n"


def _balance_du_gros_fichier(n):
    net = {"accord": D(0), "libre": D(0)}
    for i in range(n):
        m = D(f"{100 + i % 900}.{i % 100:02d}")
        net["accord" if i % 2 == 0 else "libre"] += m
    return (
        "compte;debit;credit;accord;axe1\n"
        f"6011;{net['accord']};0;IDA-6789;COMP-A\n"
        f"6011;{net['libre']};0;;COMP-A\n"
        f"5211;0;{net['accord'] + net['libre']};;\n"
    )


def _reprise_volumineuse(rep, n):
    _, _, profils, reprise = rep
    _balance(rep, _balance_du_gros_fichier(n))
    debut = time.perf_counter()
    resultat = _historique(rep, _gros_fichier(n))
    duree_import = time.perf_counter() - debut
    assert resultat.creees == n
    debut = time.perf_counter()
    rapport = controler_reprise(utilisateur=profils["dora"], reprise=Reprise.objects.get())
    assert rapport.accepte and rapport.nombre_ecritures == n and rapport.ecarts == []
    return duree_import, time.perf_counter() - debut


def test_une_reprise_de_cinq_cents_ecritures_est_a_ecart_nul(rep):
    duree_import, duree_controle = _reprise_volumineuse(rep, int(os.environ.get("N_REPRISE", 500)))
    print(f"\nimport {duree_import:.1f} s, contrôle {duree_controle:.1f} s")


@pytest.mark.skipif(not os.environ.get("RUN_LENT"), reason="50 000 écritures : RUN_LENT=1")
def test_une_reprise_de_cinquante_mille_ecritures_est_a_ecart_nul_et_signee(rep):
    duree_import, duree_controle = _reprise_volumineuse(rep, 50_000)
    rapport = RapportReprise.objects.get()
    signer_rapport(utilisateur=rep[2]["sonia"], rapport=rapport)
    print(f"\n50 000 écritures : import {duree_import:.0f} s, contrôle {duree_controle:.0f} s")
    assert reprise_acceptee(rep[1].id)
