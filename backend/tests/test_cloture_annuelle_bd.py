"""Clôture annuelle et à-nouveaux. Voir L3-T08 (partie b).

Clôturer un exercice reporte, dans une écriture d'à-nouveaux de l'exercice suivant, les soldes
des comptes de bilan (classes 1 à 5) par compte, tiers et accord de financement ; le résultat
(classes 6 et 7) est porté sur un compte donné. Les à-nouveaux sont VERSIONNÉS et se régénèrent
tant que l'exercice d'origine n'est pas verrouillé : l'ancienne écriture est contre-passée, la
nouvelle la remplace. Une écriture comptabilisée ne se modifie jamais.
"""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from niveau1_socle.comptabilite.annuelle import (
    ANouveauxIncoherents,
    ExerciceNonCloturable,
    ExerciceVerrouille,
    calculer_a_nouveaux,
    cloturer_exercice,
)
from niveau1_socle.comptabilite.models import ANouveau, Ecriture
from niveau1_socle.exercices.models import Exercice, Periode
from niveau1_socle.exercices.services import (
    TransitionInterdite,
    cloturer_periode,
    creer_exercice,
    rouvrir_periode,
    verrouiller_periode,
)
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau1_socle.referentiels.comptes import CompteNonImputable
from niveau1_socle.referentiels.models import Compte
from tests.outils import _compte, connexion_proprietaire, creer_piece, id_objet
from tests.test_cycle_ecriture_bd import _poser, decor  # noqa: F401
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
ACCORD = "IDA-1"


def _piece(org, projet, periode, lignes, annee=2026, **champs):
    return creer_piece(org.id, annee, periode, lignes, project_id=projet.id, **champs)


def _exercice(projet, annee=2026):
    return Exercice.objects.get(project_id=projet.id, annee=annee)


def _fermer_toutes_les_periodes(exercice):
    for numero in range(1, 13):
        cloturer_periode(exercice.periodes.get(numero=numero), utilisateur=None)


@pytest.fixture
def exercice_a_cloturer(decor):  # noqa: F811
    """2026 : capital, achat à crédit, vente, règlement partiel. Résultat : bénéfice de 2 000.

    Soldes de bilan attendus : banque 14 000 D, capital 10 000 C, fournisseur FRN-001 (accord
    IDA-1) 2 000 C. Résultat : 2 000 (crédit).
    """
    organisation, projet, profils = decor
    creer_exercice(projet, 2027, utilisateur=None)
    _compte(organisation.id, "101")
    _compte(organisation.id, "120")
    _piece(
        organisation,
        projet,
        1,
        [{"compte": "5211", "debit": "10000"}, {"compte": "101", "credit": "10000"}],
    )
    _piece(
        organisation,
        projet,
        3,
        [
            {"compte": "6011", "debit": "3000", "accord": ACCORD},
            {"compte": "4011", "credit": "3000", "tiers": "FRN-001", "accord": ACCORD},
        ],
    )
    _piece(
        organisation,
        projet,
        4,
        [{"compte": "5211", "debit": "5000"}, {"compte": "7061", "credit": "5000"}],
    )
    _piece(
        organisation,
        projet,
        5,
        [
            {"compte": "4011", "debit": "1000", "tiers": "FRN-001", "accord": ACCORD},
            {"compte": "5211", "credit": "1000"},
        ],
    )
    exercice = _exercice(projet)
    _fermer_toutes_les_periodes(exercice)
    return organisation, projet, profils, exercice


def _lignes_de(ecriture):
    return {
        (
            ligne.account.code,
            ligne.partner.code if ligne.partner else None,
            ligne.agreement_id,
        ): ligne.debit - ligne.credit
        for ligne in ecriture.lignes.select_related("account", "partner")
    }


ATTENDU = {
    ("5211", None, None): Decimal("14000"),
    ("101", None, None): Decimal("-10000"),
    ("4011", "FRN-001", id_objet(ACCORD)): Decimal("-2000"),
    ("120", None, None): Decimal("-2000"),  # le résultat : un bénéfice, au crédit
}


# --- la clôture et ses à-nouveaux ---------------------------------------------------------


def test_cloturer_un_exercice_genere_les_a_nouveaux_de_l_exercice_suivant(exercice_a_cloturer):
    organisation, projet, profils, exercice = exercice_a_cloturer

    resultat = cloturer_exercice(exercice, utilisateur=profils["claire"], compte_resultat="120")

    assert resultat.statut == "genere"
    a_nouveau = resultat.a_nouveau
    assert (a_nouveau.version, a_nouveau.status, a_nouveau.resultat) == (
        1,
        "actif",
        Decimal("2000"),
    )
    ecriture = a_nouveau.ecriture
    assert (ecriture.status, ecriture.journal.code, ecriture.number) == (
        "posted",
        "AN",
        "AN-2027-000001",
    )
    assert (ecriture.exercice.annee, ecriture.periode.numero) == (2027, 1)
    assert ecriture.accounting_date == datetime.date(2027, 1, 1)
    assert _lignes_de(ecriture) == ATTENDU
    assert Exercice.objects.get(pk=exercice.pk).status == "clos"
    assert verifier_chaine(organisation.id) is None


def test_les_comptes_de_resultat_ne_sont_pas_reportes_et_les_soldes_nuls_non_plus(
    exercice_a_cloturer,
):
    _, _, profils, exercice = exercice_a_cloturer
    ecriture = cloturer_exercice(
        exercice, utilisateur=profils["claire"], compte_resultat="120"
    ).a_nouveau.ecriture
    codes = {compte for compte, _, _ in _lignes_de(ecriture)}
    assert codes.isdisjoint({"6011", "7061"})  # classes 6 et 7
    assert len(_lignes_de(ecriture)) == 4


# --- le contrôle de la tâche --------------------------------------------------------------


def test_clôturer_regenerer_comparer_donne_un_resultat_identique(exercice_a_cloturer):
    """Contrôle de L3-T08 (b)."""
    organisation, projet, profils, exercice = exercice_a_cloturer
    premiere = cloturer_exercice(exercice, utilisateur=profils["claire"], compte_resultat="120")
    ecritures_avant = Ecriture.objects.count()

    seconde = cloturer_exercice(exercice, utilisateur=profils["claire"], compte_resultat="120")

    assert seconde.statut == "inchange"
    assert seconde.a_nouveau.pk == premiere.a_nouveau.pk and seconde.a_nouveau.version == 1
    assert Ecriture.objects.count() == ecritures_avant  # rien n'a été écrit
    assert seconde.difference["identique"] is True
    lignes, resultat = calculer_a_nouveaux(exercice, "120")
    assert {(ligne.compte, ligne.tiers, ligne.accord): ligne.montant for ligne in lignes} == ATTENDU
    assert resultat == Decimal("2000")


# --- régénération après correction --------------------------------------------------------


def test_une_correction_apres_cloture_regenere_les_a_nouveaux_en_contrepassant_l_ancien(
    exercice_a_cloturer,
):
    organisation, projet, profils, exercice = exercice_a_cloturer
    v1 = cloturer_exercice(exercice, utilisateur=profils["claire"], compte_resultat="120").a_nouveau
    ancienne = v1.ecriture
    avant = Ecriture.objects.filter(pk=ancienne.pk).values().get()

    # On rouvre juin, on y passe une charge oubliée de 500, on la referme.
    dora = _utilisateur_parametrage(organisation, projet)
    rouvrir_periode(exercice.periodes.get(numero=6), utilisateur=dora, motif="Facture oubliée")
    assert Exercice.objects.get(pk=exercice.pk).status == "ouvert"
    _piece(
        organisation,
        projet,
        6,
        [{"compte": "6011", "debit": "500"}, {"compte": "5211", "credit": "500"}],
    )
    cloturer_periode(exercice.periodes.get(numero=6), utilisateur=None)

    resultat = cloturer_exercice(exercice, utilisateur=profils["claire"], compte_resultat="120")

    assert resultat.statut == "regenere"
    v2 = resultat.a_nouveau
    assert (v2.version, v2.status, v2.resultat) == (2, "actif", Decimal("1500"))
    v1.refresh_from_db()
    assert v1.status == "remplace" and v1.ecriture_annulation is not None
    assert Ecriture.objects.filter(pk=ancienne.pk).values().get() == avant, (
        "L'ANCIENNE A ÉTÉ TOUCHÉE"
    )
    assert v1.ecriture_annulation.reverses_id == ancienne.pk
    assert resultat.difference["identique"] is False
    assert {m[0] for m in resultat.difference["modifiees"]} >= {("5211", None, None)}

    # Effet net dans l'exercice 2027 : l'ancienne et son inverse s'annulent, reste la nouvelle.
    with connection.cursor() as cur:
        cur.execute(
            """SELECT c.code, sum(l.debit - l.credit) FROM comptabilite_ligneecriture l
                 JOIN comptabilite_ecriture e ON e.id = l.entry_id
                 JOIN referentiels_compte c ON c.id = l.account_id
                WHERE e.exercice_id = (SELECT id FROM exercices_exercice
                                        WHERE project_id = %s AND annee = 2027)
                GROUP BY c.code HAVING sum(l.debit - l.credit) <> 0""",
            [projet.id],
        )
        net = dict(cur.fetchall())
    assert net == {
        "5211": Decimal("13500"),
        "101": Decimal("-10000"),
        "4011": Decimal("-2000"),
        "120": Decimal("-1500"),
    }
    assert Exercice.objects.get(pk=exercice.pk).status == "clos"


def test_un_seul_a_nouveau_est_actif_par_exercice(exercice_a_cloturer):
    organisation, projet, profils, exercice = exercice_a_cloturer
    v1 = cloturer_exercice(exercice, utilisateur=profils["claire"], compte_resultat="120").a_nouveau
    with pytest.raises(IntegrityError, match="uq_anouveau_un_actif"), transaction.atomic():
        ANouveau.objects.create(
            org_id=organisation.id,
            project_id=projet.id,
            exercice_source=exercice,
            exercice_cible=v1.exercice_cible,
            version=2,
            status="actif",
            ecriture=v1.ecriture,
            compte_resultat="120",
            resultat=Decimal(0),
            empreinte="x" * 64,
            genere_by=profils["claire"].id,
        )


# --- ce qui empêche la clôture ------------------------------------------------------------


def test_on_ne_cloture_pas_un_exercice_dont_des_periodes_sont_ouvertes(decor):  # noqa: F811
    organisation, projet, profils = decor
    creer_exercice(projet, 2027, utilisateur=None)
    _compte(organisation.id, "120")
    exercice = _exercice(projet)
    cloturer_periode(exercice.periodes.get(numero=1), utilisateur=None)
    with pytest.raises(ExerciceNonCloturable, match="2, 3, 4"):
        cloturer_exercice(exercice, utilisateur=profils["claire"], compte_resultat="120")
    assert Exercice.objects.get(pk=exercice.pk).status == "ouvert"
    assert ANouveau.objects.count() == 0


def test_il_faut_un_exercice_suivant_dont_la_premiere_periode_est_ouverte(decor):  # noqa: F811
    organisation, projet, profils = decor
    _compte(organisation.id, "120")
    exercice = _exercice(projet)
    _fermer_toutes_les_periodes(exercice)
    with pytest.raises(ExerciceNonCloturable, match="exercice suivant"):
        cloturer_exercice(exercice, utilisateur=profils["claire"], compte_resultat="120")

    creer_exercice(projet, 2027, utilisateur=None)
    cloturer_periode(_exercice(projet, 2027).periodes.get(numero=1), utilisateur=None)
    with pytest.raises(ExerciceNonCloturable, match="première période"):
        cloturer_exercice(exercice, utilisateur=profils["claire"], compte_resultat="120")


def test_le_compte_de_resultat_doit_etre_un_compte_imputable(exercice_a_cloturer):
    _, _, profils, exercice = exercice_a_cloturer
    Compte.objects.filter(code="120").update(imputable=False)
    with pytest.raises(CompteNonImputable):
        cloturer_exercice(exercice, utilisateur=profils["claire"], compte_resultat="120")
    assert ANouveau.objects.count() == 0


def test_la_cloture_exige_l_habilitation_comptabiliser(exercice_a_cloturer):
    _, _, profils, exercice = exercice_a_cloturer
    with pytest.raises(PermissionDenied):
        cloturer_exercice(exercice, utilisateur=profils["bruno"], compte_resultat="120")
    assert Exercice.objects.get(pk=exercice.pk).status == "ouvert"


def test_des_classes_non_reportees_avec_un_solde_sont_une_incoherence(exercice_a_cloturer):
    """Les classes 8 et 9 se soldent entre elles ; un solde y fausserait le résultat."""
    organisation, projet, profils, exercice = exercice_a_cloturer
    rouvrir_periode(
        exercice.periodes.get(numero=7),
        utilisateur=_utilisateur_parametrage(organisation, projet),
        motif="Hors bilan",
    )
    _piece(
        organisation,
        projet,
        7,
        [{"compte": "8999", "debit": "70"}, {"compte": "5211", "credit": "70"}],
    )
    cloturer_periode(exercice.periodes.get(numero=7), utilisateur=None)
    with pytest.raises(ANouveauxIncoherents, match="classes 8 et 9"):
        cloturer_exercice(exercice, utilisateur=profils["claire"], compte_resultat="120")
    assert ANouveau.objects.count() == 0


# --- exercice verrouillé, périodes rouvertes ----------------------------------------------


def test_un_exercice_verrouille_ne_regenere_plus_ses_a_nouveaux(exercice_a_cloturer):
    _, _, profils, exercice = exercice_a_cloturer
    cloturer_exercice(exercice, utilisateur=profils["claire"], compte_resultat="120")
    for numero in range(1, 13):
        verrouiller_periode(exercice.periodes.get(numero=numero), utilisateur=None)
    with pytest.raises(ExerciceVerrouille):
        cloturer_exercice(exercice, utilisateur=profils["claire"], compte_resultat="120")


def _utilisateur_parametrage(organisation, projet):
    utilisateur = Utilisateur.objects.create_user("dora", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id,
        code="PARAM",
        label={"fr": "Paramétrage"},
        operations=["consulter", "parametrer"],
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=utilisateur.id, project_id=projet.id, role=role
    )
    return utilisateur


def test_rouvrir_une_periode_exige_un_motif_l_habilitation_et_une_periode_non_verrouillee(
    exercice_a_cloturer,
):
    organisation, projet, profils, exercice = exercice_a_cloturer
    dora = _utilisateur_parametrage(organisation, projet)
    periode = exercice.periodes.get(numero=2)

    with pytest.raises(ValueError, match="motif"):
        rouvrir_periode(periode, utilisateur=dora, motif="  ")
    with pytest.raises(PermissionDenied):
        rouvrir_periode(periode, utilisateur=profils["bruno"], motif="Test")

    rouvrir_periode(periode, utilisateur=dora, motif="Correction")
    assert Periode.objects.get(pk=periode.pk).status == "ouverte"
    with pytest.raises(TransitionInterdite):
        rouvrir_periode(periode, utilisateur=dora, motif="Déjà ouverte")

    cloturer_periode(periode, utilisateur=None)
    verrouiller_periode(periode, utilisateur=None)
    with pytest.raises(TransitionInterdite, match="verrouill"):
        rouvrir_periode(periode, utilisateur=dora, motif="Trop tard")
    with connexion_proprietaire() as admin:  # même le propriétaire : le verrou est définitif
        with pytest.raises(Exception, match="verrouillée"):
            admin.execute(
                "UPDATE exercices_periode SET status = 'ouverte' WHERE id = %s", [periode.pk]
            )


def test_les_a_nouveaux_sont_isoles_par_organisation(exercice_a_cloturer):
    _, _, profils, exercice = exercice_a_cloturer
    cloturer_exercice(exercice, utilisateur=profils["claire"], compte_resultat="120")
    autre = _creer_organisation("ORG-B")
    _poser(autre)
    assert ANouveau.objects.count() == 0


def test_un_a_nouveau_ne_se_supprime_pas_et_ne_se_modifie_pas(exercice_a_cloturer):
    _, _, profils, exercice = exercice_a_cloturer
    a_nouveau = cloturer_exercice(
        exercice, utilisateur=profils["claire"], compte_resultat="120"
    ).a_nouveau
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="ne se supprime pas"):
            admin.execute("DELETE FROM comptabilite_anouveau WHERE id = %s", [a_nouveau.pk])
        with pytest.raises(Exception, match="ne change que pour passer"):
            admin.execute(
                "UPDATE comptabilite_anouveau SET resultat = 1 WHERE id = %s", [a_nouveau.pk]
            )
        with pytest.raises(Exception, match="ne change que pour passer"):
            admin.execute(
                "UPDATE comptabilite_anouveau SET status = 'remplace' WHERE id = %s",
                [a_nouveau.pk],
            )  # sans écriture d'annulation
