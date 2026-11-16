# ruff: noqa: F811, E501
"""Le plan de passation : méthodes à seuils, lignes prévisionnelles, avancement. Voir L9-T01.

Contrôles du plan : le moteur refuse une méthode dont le seuil ne couvre pas le montant, l'avancement
ne saute ni ne recule, et ce que la base garantit (triggers) ne dépend pas du service.
"""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from rest_framework.exceptions import PermissionDenied

from core.erreurs import CodeErreur, ErreurMetier
from core.models import AuditLog
from niveau1_socle.marches.models import (
    EtapeAvancement,
    LignePassation,
    MethodePassation,
    StatutLigne,
)
from niveau1_socle.marches.plan import (
    ajouter_ligne,
    avancer_ligne,
    creer_plan,
    definir_methode,
    lignes_en_retard,
    methodes_applicables,
    modifier_ligne_prevue,
    replanifier,
    synthese,
)
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
D = Decimal
J = datetime.date
Utilisateur = get_user_model()


@pytest.fixture
def pas(cadre):
    """Trois méthodes aux seuils posés par le projet (aucune valeur par défaut n'existe)."""
    organisation, projet, profils, _ = cadre
    dora, amina = profils["dora"], profils["amina"]
    for code, bas, haut, avis in (
        ("COT", "0", "50000", False),
        ("AON", "50000", "500000", False),
        ("AOI", "500000", None, True),
    ):
        definir_methode(
            utilisateur=dora,
            project_id=projet.id,
            code=code,
            label={"fr": code, "en": code},
            devise="USD",
            seuil_min=bas,
            seuil_max=haut,
            exige_non_objection=avis,
            valid_from=J(2026, 1, 1),
        )
    plan = creer_plan(
        utilisateur=amina,
        project_id=projet.id,
        code="PPM-2026",
        nom="Plan de passation 2026",
        date_debut=J(2026, 1, 1),
        date_fin=J(2026, 12, 31),
    )
    return organisation, projet, profils, plan


def _ligne(pas, reference="M-001", montant="120000", methode="AON", **champs):
    _, _, profils, plan = pas
    donnees = {
        "utilisateur": profils["amina"],
        "plan": plan,
        "reference": reference,
        "libelle": "Fourniture de véhicules",
        "montant_prevu": montant,
        "devise": "USD",
        "methode_code": methode,
        "date_lancement_prevue": J(2026, 3, 1),
        "date_attribution_prevue": J(2026, 5, 1),
        "date_signature_prevue": J(2026, 6, 1),
    } | champs
    return ajouter_ligne(**donnees)


def test_une_methode_dont_le_seuil_ne_couvre_pas_le_montant_est_refusee(pas):
    with pytest.raises(ErreurMetier) as e:
        _ligne(pas, montant="700000", methode="AON")
    assert e.value.code == CodeErreur.REGLE_INVALIDE
    assert "AOI" not in str(e.value) and "[50000" in str(e.value)
    assert not LignePassation.objects.exists()


def test_le_seuil_maximal_est_exclu_et_le_minimal_inclus(pas):
    _, projet, _, _ = pas
    jour = J(2026, 3, 1)
    assert [m.code for m in methodes_applicables(projet.id, "49999.99", "USD", jour)] == ["COT"]
    assert [m.code for m in methodes_applicables(projet.id, "50000", "USD", jour)] == ["AON"]
    assert [m.code for m in methodes_applicables(projet.id, "500000", "USD", jour)] == ["AOI"]
    assert methodes_applicables(projet.id, "100", "EUR", jour) == []


def test_une_ligne_garde_l_exigence_d_avis_de_sa_methode(pas):
    petite = _ligne(pas, "M-001", "10000", "COT")
    grosse = _ligne(pas, "M-002", "900000", "AOI")
    assert petite.non_objection_requise is False
    assert grosse.non_objection_requise is True
    assert synthese(utilisateur=pas[2]["amina"], plan=pas[3])["non_objection_requise"] == 1


def test_une_nouvelle_version_de_methode_ferme_la_precedente_sans_toucher_aux_lignes(pas):
    _, projet, profils, _ = pas
    ligne = _ligne(pas, montant="120000", methode="AON")
    v2 = definir_methode(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code="AON",
        label={"fr": "AON", "en": "NCB"},
        devise="USD",
        seuil_min="80000",
        seuil_max="500000",
        valid_from=J(2026, 7, 1),
    )
    v1 = MethodePassation.objects.get(project_id=projet.id, code="AON", version=1)
    assert v2.version == 2 and v1.valid_to == J(2026, 7, 1)
    ligne.refresh_from_db()
    assert ligne.methode_id == v1.id  # la ligne garde la version sous laquelle elle a été prévue
    with pytest.raises(ErreurMetier):  # une version ne remonte pas dans le passé
        definir_methode(
            utilisateur=profils["dora"],
            project_id=projet.id,
            code="AON",
            label={"fr": "AON", "en": "NCB"},
            devise="USD",
            seuil_min="0",
            valid_from=J(2026, 7, 1),
        )


def test_la_base_refuse_deux_versions_de_methode_qui_se_chevauchent(pas):
    _, projet, _, _ = pas
    v1 = MethodePassation.objects.get(project_id=projet.id, code="COT")
    with pytest.raises(IntegrityError), transaction.atomic():
        MethodePassation.objects.create(
            org_id=v1.org_id,
            project_id=projet.id,
            code="COT",
            version=2,
            label={"fr": "x", "en": "x"},
            devise="USD",
            seuil_min=0,
            valid_from=J(2026, 6, 1),
        )


def test_le_contenu_d_une_methode_ne_se_modifie_pas(pas):
    _, projet, _, _ = pas
    methode = MethodePassation.objects.get(project_id=projet.id, code="COT")
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        MethodePassation.objects.filter(pk=methode.pk).update(seuil_max=D("999999"))


def test_une_ligne_avance_etape_par_etape_et_garde_sa_trace(pas):
    ligne = _ligne(pas)
    amina = pas[2]["amina"]
    for statut, jour in (
        ("lance", J(2026, 3, 2)),
        ("attribue", J(2026, 5, 3)),
        ("signe", J(2026, 6, 4)),
    ):
        ligne = avancer_ligne(utilisateur=amina, ligne=ligne, statut=statut, date_effet=jour)
    assert ligne.statut == StatutLigne.SIGNE
    etapes = list(EtapeAvancement.objects.filter(ligne=ligne).order_by("created_at"))
    assert [e.statut for e in etapes] == ["prevu", "lance", "attribue", "signe"]
    assert all(e.par == amina.id for e in etapes[1:])


def test_une_etape_ne_se_saute_pas_ni_ne_recule_dans_le_temps(pas):
    ligne = _ligne(pas)
    amina = pas[2]["amina"]
    with pytest.raises(ErreurMetier) as e:
        avancer_ligne(utilisateur=amina, ligne=ligne, statut="attribue", date_effet=J(2026, 4, 1))
    assert e.value.code == CodeErreur.TRANSITION_INTERDITE
    ligne = avancer_ligne(utilisateur=amina, ligne=ligne, statut="lance", date_effet=J(2026, 4, 1))
    with pytest.raises(ErreurMetier):
        avancer_ligne(utilisateur=amina, ligne=ligne, statut="attribue", date_effet=J(2026, 3, 1))


def test_une_annulation_exige_un_motif_et_une_ligne_signee_ne_change_plus(pas):
    amina = pas[2]["amina"]
    ligne = _ligne(pas, "M-001")
    with pytest.raises(ErreurMetier):
        avancer_ligne(utilisateur=amina, ligne=ligne, statut="annule", date_effet=J(2026, 3, 2))
    ligne = avancer_ligne(
        utilisateur=amina,
        ligne=ligne,
        statut="annule",
        date_effet=J(2026, 3, 2),
        note="Besoin abandonné",
    )
    assert ligne.statut == StatutLigne.ANNULE
    with pytest.raises(ErreurMetier):
        avancer_ligne(utilisateur=amina, ligne=ligne, statut="lance", date_effet=J(2026, 3, 3))
    signee = _ligne(pas, "M-002")
    for statut, jour in (
        ("lance", J(2026, 3, 2)),
        ("attribue", J(2026, 5, 3)),
        ("signe", J(2026, 6, 4)),
    ):
        signee = avancer_ligne(utilisateur=amina, ligne=signee, statut=statut, date_effet=jour)
    with pytest.raises(ErreurMetier):
        avancer_ligne(
            utilisateur=amina, ligne=signee, statut="annule", date_effet=J(2026, 6, 5), note="x"
        )


def test_la_base_refuse_un_retour_en_arriere_et_la_suppression(pas):
    ligne = _ligne(pas)
    avancer_ligne(
        utilisateur=pas[2]["amina"], ligne=ligne, statut="lance", date_effet=J(2026, 3, 2)
    )
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        LignePassation.objects.filter(pk=ligne.pk).update(statut="prevu")
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        LignePassation.objects.filter(pk=ligne.pk).update(montant_prevu=D("1"))
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        LignePassation.objects.filter(pk=ligne.pk).delete()
    with pytest.raises(Exception), transaction.atomic():  # noqa: B017
        EtapeAvancement.objects.filter(ligne=ligne).delete()


def test_le_montant_et_la_methode_ne_changent_plus_apres_le_lancement(pas):
    amina = pas[2]["amina"]
    ligne = _ligne(pas)
    ligne = modifier_ligne_prevue(utilisateur=amina, ligne=ligne, montant_prevu="130000")
    assert ligne.montant_prevu == D("130000.0000") or ligne.montant_prevu == D("130000")
    avancer_ligne(utilisateur=amina, ligne=ligne, statut="lance", date_effet=J(2026, 3, 2))
    with pytest.raises(ErreurMetier) as e:
        modifier_ligne_prevue(utilisateur=amina, ligne=ligne, montant_prevu="140000")
    assert e.value.code == CodeErreur.TRANSITION_INTERDITE


def test_changer_de_methode_sur_une_ligne_prevue_relit_l_exigence_d_avis(pas):
    amina = pas[2]["amina"]
    ligne = _ligne(pas, "M-001", "120000", "AON")
    ligne = modifier_ligne_prevue(
        utilisateur=amina, ligne=ligne, montant_prevu="600000", methode_code="AOI"
    )
    assert ligne.methode.code == "AOI" and ligne.non_objection_requise is True
    with pytest.raises(ErreurMetier):  # le montant doit rester couvert par la méthode
        modifier_ligne_prevue(utilisateur=amina, ligne=ligne, montant_prevu="100")


def test_replanifier_exige_un_motif_le_trace_et_refuse_une_ligne_close(pas):
    amina = pas[2]["amina"]
    ligne = _ligne(pas)
    nouvelles = {
        "date_lancement_prevue": J(2026, 4, 1),
        "date_attribution_prevue": J(2026, 6, 1),
        "date_signature_prevue": J(2026, 7, 1),
    }
    with pytest.raises(ErreurMetier):
        replanifier(utilisateur=amina, ligne=ligne, motif=" ", **nouvelles)
    ligne = replanifier(
        utilisateur=amina, ligne=ligne, motif="Avis tardif du bailleur", **nouvelles
    )
    assert ligne.date_signature_prevue == J(2026, 7, 1)
    entree = AuditLog.objects.filter(action="procurement_line_rescheduled").get()
    assert entree.after["motif"] == "Avis tardif du bailleur"
    assert entree.before["signature"] == "2026-06-01"
    with pytest.raises(ErreurMetier):  # dates désordonnées
        replanifier(
            utilisateur=amina,
            ligne=ligne,
            motif="x",
            **(nouvelles | {"date_signature_prevue": J(2026, 5, 1)}),
        )
    with pytest.raises(ErreurMetier):  # hors période du plan
        replanifier(
            utilisateur=amina,
            ligne=ligne,
            motif="x",
            **(nouvelles | {"date_signature_prevue": J(2027, 1, 1)}),
        )


def test_les_retards_listent_l_etape_attendue_du_plus_ancien_au_plus_recent(pas):
    amina = pas[2]["amina"]
    _ligne(pas, "M-001", date_lancement_prevue=J(2026, 2, 1))
    en_cours = _ligne(pas, "M-002", date_lancement_prevue=J(2026, 3, 1))
    avancer_ligne(utilisateur=amina, ligne=en_cours, statut="lance", date_effet=J(2026, 3, 1))
    _ligne(
        pas,
        "M-003",
        date_lancement_prevue=J(2026, 9, 1),
        date_attribution_prevue=J(2026, 10, 1),
        date_signature_prevue=J(2026, 11, 1),
    )
    retards = lignes_en_retard(utilisateur=amina, project_id=pas[1].id, jour=J(2026, 6, 10))
    assert [(r.ligne.reference, r.etape_attendue, r.jours) for r in retards] == [
        ("M-001", "lance", 129),
        ("M-002", "attribue", 40),
    ]


def test_la_synthese_ne_melange_pas_les_devises(pas):
    amina = pas[2]["amina"]
    _ligne(pas, "M-001", "120000")
    s = synthese(utilisateur=amina, plan=pas[3])
    assert s["par_statut"] == {("prevu", "USD"): D("120000")}
    assert s["par_methode"] == {("AON", "USD"): D("120000")}


def test_une_devise_differente_de_celle_de_la_methode_est_refusee(pas):
    with pytest.raises(ErreurMetier):
        _ligne(pas, devise="EUR")


def test_les_habilitations_sont_exigees(pas):
    _, projet, profils, plan = pas
    with pytest.raises(PermissionDenied):  # amina saisit mais ne paramètre pas
        definir_methode(
            utilisateur=profils["amina"],
            project_id=projet.id,
            code="X",
            label={"fr": "x", "en": "x"},
            devise="USD",
            seuil_min="0",
            valid_from=J(2026, 1, 1),
        )
    with pytest.raises(PermissionDenied):  # dora paramètre mais ne saisit pas
        _ligne(pas, utilisateur=profils["dora"])


def test_un_plan_et_une_reference_ne_se_dupliquent_pas(pas):
    _, projet, profils, _ = pas
    with pytest.raises(ErreurMetier):
        creer_plan(
            utilisateur=profils["amina"],
            project_id=projet.id,
            code="PPM-2026",
            nom="Doublon",
            date_debut=J(2026, 1, 1),
            date_fin=J(2026, 12, 31),
        )
    _ligne(pas, "M-001")
    with pytest.raises(ErreurMetier):
        _ligne(pas, "M-001")
    assert connection.vendor == "postgresql"


def test_les_bornes_de_la_methode_valent_aussi_pour_une_ligne(pas):
    with pytest.raises(ErreurMetier):  # 500 000 sort de la plage [50 000, 500 000[ de l'AON
        _ligne(pas, "M-001", "500000", "AON")
    with pytest.raises(ErreurMetier):  # 49 999,99 est sous le seuil minimal de l'AON
        _ligne(pas, "M-002", "49999.99", "AON")
    assert _ligne(pas, "M-003", "50000", "AON").methode.code == "AON"
    assert _ligne(pas, "M-004", "499999.99", "AON").methode.code == "AON"


def test_une_ligne_n_est_pas_en_retard_le_jour_meme_de_l_echeance(pas):
    amina = pas[2]["amina"]
    _ligne(pas, "M-001", date_lancement_prevue=J(2026, 3, 1))
    assert lignes_en_retard(utilisateur=amina, project_id=pas[1].id, jour=J(2026, 3, 1)) == []
    assert len(lignes_en_retard(utilisateur=amina, project_id=pas[1].id, jour=J(2026, 3, 2))) == 1
