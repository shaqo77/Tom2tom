# ruff: noqa: F811
"""La descente du tableau de bord : indicateur → détail par projet → écriture. Voir L10-T02c.

Contrôle du plan : la somme du détail égale exactement le chiffre de l'indicateur, projet par
projet et devise par devise ; et l'écriture atteinte est celle du grand livre.
"""

import datetime
from decimal import Decimal

import pytest
from rest_framework.exceptions import PermissionDenied

from niveau1_socle.avances.models import Avance
from niveau1_socle.avances.services import justifier_avance, verser_avance
from niveau1_socle.budget.models import Engagement
from niveau1_socle.comptabilite.models import LigneEcriture
from niveau1_socle.financements.models import CompteBancaire
from niveau1_socle.referentiels.models import Tiers
from niveau4_reporting.publication.descente import detail_ecriture
from niveau4_reporting.tableau_de_bord import Filtres, detail_indicateur, ecritures_du_detail
from niveau4_reporting.tableau_de_bord.financier import tableau_de_bord
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_rapprochement_bancaire_bd import _ligne as _ligne_banque
from tests.test_tableau_de_bord_bd import JOUR, _poser, parc  # noqa: F401
from tests.test_tresorerie_bd import banque  # noqa: F401

D = datetime.date
pytestmark = pytest.mark.django_db(transaction=True)

CODES = (
    "budget_approuve",
    "budget_initial",
    "financements_accordes",
    "financements_recus",
    "execution_budget",
    "execution_engage",
    "execution_consomme",
    "soldes_comptables",
    "soldes_releves",
    "engagements_ouverts",
    "avances_non_justifiees",
)


def _tdb(parc, **champs):
    organisation, _, _, _, _, profils, _ = parc
    _poser(organisation)
    return tableau_de_bord(utilisateur=profils["amina"], jour=JOUR, filtres=Filtres(**champs))


def test_la_somme_du_detail_egale_l_indicateur_pour_chaque_projet_et_chaque_devise(parc):
    organisation, p1, p2, _, _, profils, _ = parc
    tdb = _tdb(parc)
    _poser(organisation)
    for code in CODES:
        for projet in (p1, p2):
            lignes = detail_indicateur(
                utilisateur=profils["amina"], code=code, project_id=projet.id, jour=JOUR
            )
            somme: dict = {}
            for ligne in lignes:
                somme[ligne.devise] = somme.get(ligne.devise, 0) + ligne.montant
            attendu = {
                d: m for d, m in tdb.indicateurs[code].par_projet.get(projet.id, {}).items() if m
            }
            assert {d: m for d, m in somme.items() if m} == attendu, (code, projet.code)


def test_un_detail_decrit_son_objet_et_sa_devise(parc):
    organisation, p1, p2, _, _, profils, _ = parc
    _poser(organisation)
    comptes = detail_indicateur(
        utilisateur=profils["amina"], code="soldes_comptables", project_id=p2.id, jour=JOUR
    )
    assert [(c.type, c.libelle, c.devise, c.montant) for c in comptes] == [
        ("compte_bancaire", "CB-USD", "USD", Decimal("50"))
    ]
    avances = detail_indicateur(
        utilisateur=profils["amina"], code="avances_non_justifiees", project_id=p2.id, jour=JOUR
    )
    assert [(a.type, a.libelle, a.montant) for a in avances] == [("avance", "AV-1", Decimal("60"))]


def test_un_compte_descend_jusqu_aux_ecritures_dont_la_somme_est_son_solde(parc):
    organisation, p1, p2, _, _, profils, _ = parc
    _poser(organisation)
    (compte,) = detail_indicateur(
        utilisateur=profils["amina"], code="soldes_comptables", project_id=p2.id, jour=JOUR
    )
    ecritures = ecritures_du_detail(
        utilisateur=profils["amina"], detail=compte, project_id=p2.id, jour=JOUR
    )
    assert ecritures and sum(e.montant for e in ecritures) == compte.montant
    # Et l'écriture atteinte est bien celle du grand livre, avec ses lignes.
    atteinte = detail_ecriture(p2.id, ecritures[0].ecriture_id)
    assert atteinte is not None and atteinte.numero == ecritures[0].numero


def test_une_avance_descend_jusqu_a_l_ecriture_de_son_versement(parc):
    organisation, p1, p2, _, _, profils, _ = parc
    _poser(organisation)
    ligne = LigneEcriture.objects.filter(project_id=p2.id).order_by("line_no").first()
    agent = Tiers.objects.get(org_id=organisation.id, code="AG")
    verser_avance(
        utilisateur=profils["amina"], project_id=p2.id, tiers=agent, reference="AV-2",
        montant="500", date_versement=D(2026, 3, 1), ligne_ecriture_id=ligne.pk,
    )  # fmt: skip
    details = detail_indicateur(
        utilisateur=profils["amina"], code="avances_non_justifiees", project_id=p2.id, jour=JOUR
    )
    av2 = next(d for d in details if d.libelle == "AV-2")
    refs = ecritures_du_detail(
        utilisateur=profils["amina"], detail=av2, project_id=p2.id, jour=JOUR
    )
    assert [r.ecriture_id for r in refs] == [ligne.entry_id]
    av1 = next(d for d in details if d.libelle == "AV-1")  # sans ligne comptable : rien d'inventé
    assert (
        ecritures_du_detail(utilisateur=profils["amina"], detail=av1, project_id=p2.id, jour=JOUR)
        == []
    )


def test_un_objet_sans_ecriture_le_dit_au_lieu_d_inventer(parc):
    organisation, p1, p2, _, _, profils, _ = parc
    _poser(organisation)
    (engagement,) = detail_indicateur(
        utilisateur=profils["amina"], code="engagements_ouverts", project_id=p2.id, jour=JOUR
    )
    assert engagement.a_une_ecriture is False
    assert (
        ecritures_du_detail(
            utilisateur=profils["amina"], detail=engagement, project_id=p2.id, jour=JOUR
        )
        == []
    )


def test_la_descente_est_refusee_sur_un_projet_non_consultable(parc):
    organisation, p1, p2, p3, p4, profils, _ = parc
    _poser(organisation)
    with pytest.raises(PermissionDenied):
        detail_indicateur(
            utilisateur=profils["amina"], code="budget_approuve", project_id=p4.id, jour=JOUR
        )


def test_un_code_d_indicateur_inconnu_est_refuse(parc):
    organisation, p1, _, _, _, profils, _ = parc
    _poser(organisation)
    with pytest.raises(KeyError):
        detail_indicateur(utilisateur=profils["amina"], code="inconnu", project_id=p1.id, jour=JOUR)


def _avance(parc, reference, montant, ligne=None):
    organisation, _, p2, _, _, profils, _ = parc
    agent = Tiers.objects.get(org_id=organisation.id, code="AG")
    return verser_avance(
        utilisateur=profils["amina"], project_id=p2.id, tiers=agent, reference=reference,
        montant=montant, date_versement=D(2026, 3, 1),
        ligne_ecriture_id=ligne.pk if ligne else None,
    )  # fmt: skip


def _details(parc, code):
    organisation, _, p2, _, _, profils, _ = parc
    _poser(organisation)
    return detail_indicateur(utilisateur=profils["amina"], code=code, project_id=p2.id, jour=JOUR)


def test_une_avance_soldee_n_est_pas_dans_le_detail(parc):
    organisation, _, p2, _, _, profils, _ = parc
    _poser(organisation)
    agent = Tiers.objects.get(org_id=organisation.id, code="AG")
    avance = Avance.objects.get(project_id=p2.id, reference="AV-1")
    justifier_avance(
        avance, utilisateur=profils["amina"], type="depense", montant="60",
        date_justification=D(2026, 4, 1), reference="PJ-SOLDE",
    )  # fmt: skip
    assert agent and "AV-1" not in [d.libelle for d in _details(parc, "avances_non_justifiees")]


def test_les_ecritures_d_un_compte_s_arretent_au_jour_du_tableau(parc):
    organisation, _, p2, _, _, profils, _ = parc
    _poser(organisation)
    usd = CompteBancaire.objects.get(project_id=p2.id, code="CB-USD")
    _ligne_banque(organisation, p2, usd, 25, jour=10, mois=9)  # postérieure au 30/06
    (compte,) = _details(parc, "soldes_comptables")
    refs = ecritures_du_detail(
        utilisateur=profils["amina"], detail=compte, project_id=p2.id, jour=JOUR
    )
    assert all(r.date <= JOUR for r in refs)
    assert sum(r.montant for r in refs) == compte.montant == Decimal("50")


def test_les_lignes_d_une_meme_ecriture_s_additionnent_et_les_justifications_futures_sont_ecartees(
    parc,
):
    organisation, _, p2, _, _, profils, _ = parc
    _poser(organisation)
    piece = LigneEcriture.objects.filter(project_id=p2.id, account__code="6011").first().entry
    l1, l2 = piece.lignes.order_by("line_no")[:2]
    avance = _avance(parc, "AV-3", "500", l1)
    justifier_avance(
        avance, utilisateur=profils["amina"], type="depense", montant="100",
        date_justification=D(2026, 4, 1), reference="PJ-3", ligne_ecriture_id=l2.pk,
    )  # fmt: skip
    futur = _avance(parc, "AV-4", "500", l1)
    justifier_avance(
        futur, utilisateur=profils["amina"], type="depense", montant="100",
        date_justification=D(2026, 8, 1), reference="PJ-4", ligne_ecriture_id=l2.pk,
    )  # fmt: skip
    details = {d.libelle: d for d in _details(parc, "avances_non_justifiees")}
    (r3,) = ecritures_du_detail(
        utilisateur=profils["amina"], detail=details["AV-3"], project_id=p2.id, jour=JOUR
    )
    assert (
        r3.montant == l1.debit - l1.credit + l2.debit - l2.credit
    )  # les deux lignes s'additionnent
    (r4,) = ecritures_du_detail(
        utilisateur=profils["amina"], detail=details["AV-4"], project_id=p2.id, jour=JOUR
    )
    assert r4.montant == l1.debit - l1.credit  # la justification du 01/08 n'existe pas au 30/06


def test_un_engagement_d_une_annee_future_n_est_pas_dans_le_detail(parc):
    organisation, _, p2, _, _, profils, _ = parc
    _poser(organisation)
    Engagement.objects.create(
        org_id=organisation.id, project_id=p2.id, reference="ENG-2027", annee=2027,
        montant=Decimal("900"),
    )  # fmt: skip
    assert "ENG-2027" not in [d.libelle for d in _details(parc, "engagements_ouverts")]
