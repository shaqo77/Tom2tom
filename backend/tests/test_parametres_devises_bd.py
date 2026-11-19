# ruff: noqa: F811, E501
"""Réglages de devises par organisation puis par projet : tout est paramétré en base, rien dans le code.

Un réglage est versionné `[valid_from, valid_to[` sans chevauchement, immuable une fois posé, et un
projet surcharge l'organisation champ par champ. Sans réglage, le système le dit : il ne devine rien.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from core.erreurs import ErreurMetier
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau1_socle.referentiels.parametres_devises import (
    devise_autorisee,
    parametrer_devises,
    resoudre_parametres_devises,
)
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
J = datetime.date
DEBUT = J(2026, 1, 1)


def _poser(organisation):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


@pytest.fixture
def cadre(decor):
    """ORG-A (monnaie de tenue DJF), P1 (base DJF) et P2 (base USD) ; dora paramètre P1 et P2."""
    organisation, p1, profils = decor
    p2 = _creer_projet(organisation, "P2", base_currency="USD")
    _poser(organisation)
    admin = Utilisateur.objects.create_user("dora", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id,
        code="ADM",
        label={"fr": "adm"},
        operations=["consulter", "parametrer"],
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=admin.id, project_id=p1.id, role=role
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=admin.id, project_id=p2.id, role=role
    )
    profils["dora"] = admin
    return organisation, p1, p2, profils


def _org(cadre, **champs):
    _, _, _, profils = cadre
    champs.setdefault("date_effet", DEBUT)
    return parametrer_devises(utilisateur=profils["dora"], **champs)


def _projet(cadre, projet, **champs):
    _, _, _, profils = cadre
    champs.setdefault("date_effet", DEBUT)
    return parametrer_devises(utilisateur=profils["dora"], project_id=projet.id, **champs)


# --- résolution : héritage et origine ---------------------------------------------------------


def test_sans_aucun_reglage_rien_n_est_invente(cadre):
    _, p1, _, _ = cadre
    r = resoudre_parametres_devises(p1.id, J(2026, 3, 1))
    assert (r.devise_reference, r.devises_autorisees, r.type_taux) == (None, None, None)
    assert r.origine == {"devise_reference": None, "devises_autorisees": None, "type_taux": None}


def test_un_reglage_d_organisation_vaut_pour_tous_ses_projets(cadre):
    _, p1, p2, _ = cadre
    _org(cadre, devise_reference="EUR", type_taux="officiel")
    for projet in (p1, p2):
        r = resoudre_parametres_devises(projet.id, J(2026, 3, 1))
        assert (r.devise_reference, r.type_taux) == ("EUR", "officiel")
        assert r.origine["devise_reference"] == "organisation"


def test_un_projet_surcharge_champ_par_champ_et_herite_du_reste(cadre):
    _, p1, p2, _ = cadre
    _org(cadre, devise_reference="EUR", type_taux="officiel")
    _projet(cadre, p1, devise_reference="USD")
    r1 = resoudre_parametres_devises(p1.id, J(2026, 3, 1))
    assert (r1.devise_reference, r1.type_taux) == ("USD", "officiel")
    assert (r1.origine["devise_reference"], r1.origine["type_taux"]) == ("projet", "organisation")
    r2 = resoudre_parametres_devises(p2.id, J(2026, 3, 1))  # l'autre projet n'est pas touché
    assert r2.devise_reference == "EUR"


def test_avant_la_date_d_effet_le_reglage_n_existe_pas(cadre):
    _, p1, _, _ = cadre
    _org(cadre, devise_reference="EUR", date_effet=J(2026, 6, 1))
    assert resoudre_parametres_devises(p1.id, J(2026, 5, 31)).devise_reference is None
    assert resoudre_parametres_devises(p1.id, J(2026, 6, 1)).devise_reference == "EUR"


def test_une_nouvelle_version_ferme_la_precedente_et_la_fin_est_exclue(cadre):
    _, p1, _, _ = cadre
    v1 = _org(cadre, devise_reference="EUR", date_effet=DEBUT)
    v2 = _org(cadre, devise_reference="USD", date_effet=J(2026, 7, 1))
    v1.refresh_from_db()
    assert (v1.version, v2.version, v1.valid_to) == (1, 2, J(2026, 7, 1))
    assert resoudre_parametres_devises(p1.id, J(2026, 6, 30)).devise_reference == "EUR"
    assert (
        resoudre_parametres_devises(p1.id, J(2026, 7, 1)).devise_reference == "USD"
    )  # `valid_to` exclu
    assert resoudre_parametres_devises(p1.id, J(2026, 7, 1)).versions["organisation"] == 2


def test_la_fin_d_une_version_est_exclue_meme_sans_version_suivante(cadre):
    """Une version close sans successeur (fermée à la main) ne vaut plus le jour même de sa fin."""
    from niveau1_socle.referentiels.models import ParametreDevises

    _, p1, _, _ = cadre
    _org(cadre, devise_reference="EUR", date_effet=DEBUT)
    ParametreDevises.objects.filter(version=1).update(
        valid_to=J(2026, 7, 1)
    )  # permis : fermer une fois
    assert resoudre_parametres_devises(p1.id, J(2026, 6, 30)).devise_reference == "EUR"
    assert resoudre_parametres_devises(p1.id, J(2026, 7, 1)).devise_reference is None


def test_la_liste_d_un_projet_remplace_celle_de_l_organisation_sans_la_fusionner(cadre):
    _, p1, p2, _ = cadre
    _org(cadre, devises_autorisees=["DJF", "USD", "EUR"])
    _projet(cadre, p1, devises_autorisees=["DJF", "GBP"])
    assert resoudre_parametres_devises(p1.id, J(2026, 3, 1)).devises_autorisees == ("DJF", "GBP")
    assert resoudre_parametres_devises(p2.id, J(2026, 3, 1)).devises_autorisees == (
        "DJF",
        "EUR",
        "USD",
    )


def test_devise_autorisee_sans_liste_tout_le_referentiel_sinon_la_liste(cadre):
    _, p1, _, _ = cadre
    assert devise_autorisee(p1.id, "EUR", J(2026, 3, 1)) is True  # aucune restriction paramétrée
    assert devise_autorisee(p1.id, "ZZZ", J(2026, 3, 1)) is False  # hors référentiel : jamais
    _projet(cadre, p1, devises_autorisees=["DJF", "GBP"])
    assert devise_autorisee(p1.id, "GBP", J(2026, 3, 1)) is True
    assert devise_autorisee(p1.id, "EUR", J(2026, 3, 1)) is False


# --- règles d'intégrité -----------------------------------------------------------------------


def test_une_devise_inconnue_un_type_de_taux_inconnu_ou_rien_du_tout_sont_refuses(cadre):
    with pytest.raises(ErreurMetier, match="QQQ"):
        _org(cadre, devise_reference="QQQ")
    with pytest.raises(ErreurMetier, match="QQQ"):
        _org(cadre, devises_autorisees=["DJF", "QQQ"])
    with pytest.raises(ErreurMetier, match="inventé"):
        _org(cadre, type_taux="inventé")
    with pytest.raises(ErreurMetier, match="Rien à paramétrer"):
        _org(cadre)
    with pytest.raises(ErreurMetier, match="vide"):
        _org(cadre, devises_autorisees=[])


def test_la_liste_est_normalisee_sans_doublon(cadre):
    _, p1, _, _ = cadre
    _org(cadre, devises_autorisees=["usd", "DJF", "USD", " djf "])
    assert resoudre_parametres_devises(p1.id, J(2026, 3, 1)).devises_autorisees == ("DJF", "USD")


def test_la_devise_de_reference_doit_faire_partie_de_la_liste(cadre):
    with pytest.raises(ErreurMetier, match="EUR.*devises autorisées"):
        _org(cadre, devises_autorisees=["DJF", "USD"], devise_reference="EUR")


def test_la_reference_d_un_projet_se_juge_sur_la_liste_effective_heritee_comprise(cadre):
    _org(cadre, devises_autorisees=["DJF", "USD"])
    _, p1, _, _ = cadre
    with pytest.raises(ErreurMetier, match="EUR"):
        _projet(cadre, p1, devise_reference="EUR")  # la liste de l'organisation ne la contient pas
    assert _projet(cadre, p1, devise_reference="USD").devise_reference_id == "USD"


def test_la_liste_doit_contenir_la_monnaie_de_tenue_de_l_organisation(cadre):
    with pytest.raises(ErreurMetier, match=r"monnaie de tenue.*DJF"):
        _org(cadre, devises_autorisees=["USD", "EUR"])


def test_la_liste_ne_peut_pas_exclure_la_monnaie_de_base_d_un_projet_existant(cadre):
    with pytest.raises(ErreurMetier, match=r"P2.*USD"):
        _org(cadre, devises_autorisees=["DJF", "EUR"])  # P2 tient ses comptes en USD
    _, _, p2, _ = cadre
    _projet(cadre, p2, devises_autorisees=["USD", "EUR"])  # P2 a sa propre liste, qui contient USD
    assert _org(cadre, devises_autorisees=["DJF", "EUR"]).version == 1  # alors l'organisation peut


def test_la_liste_d_un_projet_doit_contenir_sa_monnaie_de_base(cadre):
    _, _, p2, _ = cadre
    with pytest.raises(ErreurMetier, match=r"P2.*USD"):
        _projet(cadre, p2, devises_autorisees=["DJF", "EUR"])


def test_une_nouvelle_version_ne_prend_pas_effet_avant_la_precedente(cadre):
    _org(cadre, devise_reference="EUR", date_effet=J(2026, 6, 1))
    with pytest.raises(ErreurMetier, match="après le 2026-06-01"):
        _org(cadre, devise_reference="USD", date_effet=J(2026, 6, 1))
    with pytest.raises(ErreurMetier, match="après le 2026-06-01"):
        _org(cadre, devise_reference="USD", date_effet=J(2026, 1, 1))


# --- habilitation et journal ------------------------------------------------------------------


def test_sans_l_operation_parametrer_rien_ne_se_parametre(cadre):
    _, p1, p2, profils = cadre
    with pytest.raises(PermissionDenied):
        parametrer_devises(utilisateur=profils["amina"], devise_reference="EUR", date_effet=DEBUT)
    with pytest.raises(PermissionDenied):
        parametrer_devises(
            utilisateur=profils["amina"], project_id=p1.id, devise_reference="EUR", date_effet=DEBUT
        )


def test_parametrer_un_projet_exige_parametrer_sur_CE_projet(cadre):
    organisation, p1, _, profils = cadre
    p3 = _creer_projet(organisation, "P3")
    _poser(organisation)
    with pytest.raises(PermissionDenied):  # dora paramètre P1 et P2, pas P3
        parametrer_devises(
            utilisateur=profils["dora"], project_id=p3.id, devise_reference="EUR", date_effet=DEBUT
        )


def test_chaque_reglage_est_journalise_dans_le_journal_chaine(cadre):
    organisation, _, _, _ = cadre
    reglage = _org(cadre, devise_reference="EUR", motif="Reporting au bailleur en euros")
    from core.models import AuditLog

    entree = AuditLog.objects.filter(action="currency_settings_configured").latest("id")
    assert entree.object_id == reglage.id and entree.after["devise_reference"] == "EUR"
    assert verifier_chaine(organisation.id) is None  # la chaîne du journal reste intacte


# --- garde-fous de la base, même en SQL direct ------------------------------------------------


def test_la_base_refuse_de_modifier_un_reglage_pose_ou_de_le_supprimer(cadre):
    _org(cadre, devise_reference="EUR")
    from niveau1_socle.referentiels.models import ParametreDevises

    with pytest.raises(IntegrityError, match="nouvelle version"), transaction.atomic():
        ParametreDevises.objects.filter(version=1).update(devise_reference_id="USD")
    with pytest.raises(IntegrityError, match="nouvelle version"), transaction.atomic():
        ParametreDevises.objects.filter(version=1).delete()


def test_la_fin_d_une_version_se_pose_une_seule_fois_et_ne_se_retire_jamais(cadre):
    from niveau1_socle.referentiels.models import ParametreDevises

    _org(cadre, devise_reference="EUR")
    ParametreDevises.objects.filter(version=1).update(valid_to=J(2026, 7, 1))  # permis, une fois
    with pytest.raises(IntegrityError, match="nouvelle version"), transaction.atomic():
        ParametreDevises.objects.filter(version=1).update(valid_to=J(2026, 9, 1))  # déplacer la fin
    with pytest.raises(IntegrityError, match="nouvelle version"), transaction.atomic():
        ParametreDevises.objects.filter(version=1).update(
            valid_to=None
        )  # rouvrir une version close


def test_la_base_refuse_deux_versions_qui_se_chevauchent(cadre):
    organisation, _, _, _ = cadre
    _org(cadre, devise_reference="EUR")
    from niveau1_socle.referentiels.models import ParametreDevises

    with pytest.raises(IntegrityError, match="chevauch|sans_chevauchement"), transaction.atomic():
        ParametreDevises.objects.create(
            org_id=organisation.id, devise_reference_id="USD", version=2, valid_from=J(2026, 3, 1)
        )


def test_la_base_refuse_une_devise_inconnue_ou_une_liste_vide_dans_une_liste(cadre):
    organisation, _, _, _ = cadre
    from niveau1_socle.referentiels.models import ParametreDevises

    with pytest.raises(IntegrityError, match="inconnue"), transaction.atomic():
        ParametreDevises.objects.create(
            org_id=organisation.id, devises_autorisees=["DJF", "QQQ"], version=1, valid_from=DEBUT
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        ParametreDevises.objects.create(
            org_id=organisation.id, devises_autorisees=[], version=1, valid_from=DEBUT
        )
    with pytest.raises(IntegrityError), transaction.atomic():  # un réglage qui ne règle rien
        ParametreDevises.objects.create(org_id=organisation.id, version=1, valid_from=DEBUT)


def test_les_reglages_sont_isoles_par_organisation(cadre):
    _org(cadre, devise_reference="EUR")
    autre = _creer_organisation("ORG-B")
    _poser(autre)
    from niveau1_socle.referentiels.models import ParametreDevises

    assert ParametreDevises.objects.count() == 0
