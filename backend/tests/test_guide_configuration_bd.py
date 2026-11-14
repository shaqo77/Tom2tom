# ruff: noqa: F811
"""Le guide de configuration généré. Voir L5-T07.

Contrôle du plan : le guide d'un projet configuré est lisible par un comptable qui n'a jamais vu le
logiciel, et lui permet de dire POURQUOI chaque rubrique existe.
"""

import datetime
import hashlib
import io
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from core.models import AuditLog
from niveau1_socle.financements.services import creer_categorie
from niveau3_config.models import Exigence
from niveau3_config.services.guide import construire_guide, generer_guide, rendre_pdf
from tests.outils_profil import creer_profil
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_financements_bd import _accord, _activer, cadre  # noqa: F401
from tests.test_rattachement_bd import _exigence, _mapping, _rattacher, cadre_config  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
D = datetime.date
DATE = D(2027, 9, 30)


def _texte(octets: bytes) -> str:
    brut = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(octets)).pages)
    return " ".join(brut.split())  # un retour à la ligne ne change pas ce que lit le comptable


def _valider_par(exigence, utilisateur, **champs):
    Exigence.objects.filter(pk=exigence.pk).update(
        validated_by=utilisateur.id, validated_at=timezone.now(), **champs
    )
    exigence.refresh_from_db()
    return exigence


@pytest.fixture
def projet_configure(cadre_config):
    """Une exigence active (RFI trimestriel à 45 jours) qui justifie un mapping, un profil de
    décaissement en vigueur, une proposition en attente et un mapping sans source."""
    organisation, projet, profils, document = cadre_config
    rfi = _valider_par(
        _exigence(cadre_config, "RFI", statut="proposed"),
        profils["dora"],
        status="active",
        periodicity="quarterly",
        due_offset_days=45,
        subject="Rapport financier intermédiaire",
    )
    mapping = _mapping(cadre_config, "WB-TER")
    _rattacher(cadre_config, rfi, mapping)
    _mapping(cadre_config, "WB-ORPHELIN")  # actif, sans exigence source
    _exigence(cadre_config, "AUDIT", statut="proposed")
    return organisation, projet, profils, document, rfi


@pytest.fixture
def avec_profil(projet_configure):
    organisation, projet, profils, document, rfi = projet_configure
    from niveau1_socle.financements.models import Bailleur

    bailleur = Bailleur.objects.get(code="IDA")  # créé par la fixture `cadre`
    accord = _activer(
        _accord(projet, profils, bailleur, "IDA-6789", devise="USD", montant_initial="1000000"),
        profils,
    )
    categorie = creer_categorie(
        utilisateur=profils["dora"], accord=accord, code="BIENS", label={"fr": "Biens"}
    )
    creer_profil(
        organisation,
        projet,
        accord,
        regles=[(categorie, "0.8")],
        methodes=[{"method": "reimbursement", "supporting_docs": ["soe", "records"]}],
        eligibility_date=D(2026, 3, 1),
    )
    return projet_configure


# --- le contrôle de la tâche ---------------------------------------------------------------


def test_le_guide_dit_pourquoi_chaque_element_existe(avec_profil):
    """Lu seul, sans connaître le logiciel : quoi, d'où, qui, quand, pour quoi."""
    organisation, projet, profils, document, rfi = avec_profil
    texte = _texte(generer_guide(utilisateur=profils["dora"], project_id=projet.id, date=DATE))

    # Quoi, et selon quel calendrier.
    assert "RFI (version 1) — Rapport financier intermédiaire" in texte
    assert "Périodicité : trimestrielle ; délai : 45 jours après la fin de la période" in texte
    assert "Nature : obligatoire" in texte
    # D'où : le document du projet et le passage exact.
    assert "Source : " in texte and document.title in texte
    assert "§ 4.2" in texte and "« remis dans les 45 jours »" in texte
    # Qui l'a validée, et quand.
    assert f"Validée par dora, le {timezone.now().date():%d/%m/%Y} ;" in texte  # jj/mm/aaaa
    # Ce qu'elle justifie : le mapping, nommé.
    assert "Mapping : WB-TER v1" in texte
    # Le profil de décaissement en vigueur, lisible.
    assert "Accord IDA-6789 — version 1" in texte
    assert "régime de décaissement : sur transactions" in texte
    assert "Méthode : remboursement — pièces exigées : état certifié des dépenses, copies" in texte
    assert "catégorie BIENS : 80 % (taxes comprises) ; allocation 100,00" in texte
    assert "début d'éligibilité des dépenses : 01/03/2026" in texte


def test_une_proposition_nest_pas_une_exigence_appliquee(avec_profil):
    organisation, projet, profils, document, rfi = avec_profil
    texte = _texte(generer_guide(utilisateur=profils["dora"], project_id=projet.id, date=DATE))
    actives, reste = texte.split("2. Profils de décaissement")
    assert "AUDIT" not in actives  # la proposition n'est pas parmi les exigences actives
    assert "Ces exigences ne sont PAS appliquées" in reste
    assert "AUDIT — AUDIT (proposée)" in reste


def test_une_exigence_validee_mais_pas_encore_active_est_listee_en_attente(avec_profil):
    organisation, projet, profils, document, rfi = avec_profil
    validee = _exigence((organisation, projet, profils, document), "ARCH", statut="proposed")
    _valider_par(validee, profils["dora"], status="validated")
    texte = _texte(generer_guide(utilisateur=profils["dora"], project_id=projet.id, date=DATE))
    actives, reste = texte.split("2. Profils de décaissement")
    assert "ARCH" not in actives and "ARCH — ARCH (validée)" in reste
    assert "Propositions en attente (2)" in texte


def test_ce_qui_na_pas_de_source_est_signale_au_lecteur(avec_profil):
    organisation, projet, profils, document, rfi = avec_profil
    texte = _texte(generer_guide(utilisateur=profils["dora"], project_id=projet.id, date=DATE))
    assert "Points d'attention (1)" in texte
    assert "Mapping « WB-ORPHELIN v1 » : aucun rattachement" in texte


def test_un_projet_sans_configuration_donne_un_guide_vide_mais_valide(cadre_config):
    organisation, projet, profils, document = cadre_config
    texte = _texte(generer_guide(utilisateur=profils["dora"], project_id=projet.id, date=DATE))
    assert "Aucune exigence n'est active à cette date." in texte
    assert "Aucun profil de décaissement n'est en vigueur à cette date." in texte
    assert "Toute la configuration active a son exigence source." in texte


# --- déterminisme et date d'effet ----------------------------------------------------------


def test_le_guide_est_deterministe_et_independant_dune_version_a_venir(avec_profil):
    organisation, projet, profils, document, rfi = avec_profil
    avant = generer_guide(utilisateur=profils["dora"], project_id=projet.id, date=DATE)
    assert generer_guide(utilisateur=profils["dora"], project_id=projet.id, date=DATE) == avant

    v2 = _valider_par(
        _exigence(
            (organisation, projet, profils, document),
            "RFI",
            statut="proposed",
            valid_from=D(2028, 1, 1),
        ),
        profils["dora"],
        subject="Rapport (modifié)",
    )
    Exigence.objects.filter(pk=rfi.pk).update(valid_to=D(2028, 1, 1))  # V1 est close avant V2
    Exigence.objects.filter(pk=v2.pk).update(status="active", version=2)

    # La configuration résolue au 30/09/2027 (ce qui s'applique) n'a pas bougé : même empreinte.
    # Le guide ne gagne qu'une information vraie : la fin de validité désormais connue de V1.
    empreinte = construire_guide(projet.id, DATE).empreinte_configuration
    assert empreinte in _texte(avant)
    apres_meme_date = _texte(
        generer_guide(utilisateur=profils["dora"], project_id=projet.id, date=DATE)
    )
    assert " au 01/01/2028 (exclu)" in apres_meme_date
    assert apres_meme_date.replace(" au 01/01/2028 (exclu)", "") == _texte(avant)
    apres = _texte(
        generer_guide(utilisateur=profils["dora"], project_id=projet.id, date=D(2028, 1, 1))
    )
    assert "RFI (version 2)" in apres and "RFI (version 1)" not in apres


def test_lempreinte_de_la_configuration_est_celle_du_guide(avec_profil):
    organisation, projet, profils, document, rfi = avec_profil
    guide = construire_guide(projet.id, DATE)
    assert guide.empreinte_configuration in _texte(rendre_pdf(guide))
    assert [e.code for e in guide.exigences] == ["RFI"]
    assert len(guide.profils) == 1 and len(guide.en_attente) == 1 and len(guide.anomalies) == 1


# --- habilitation, journal, commande -------------------------------------------------------


def test_generer_exige_lhabilitation_consulter(avec_profil):
    organisation, projet, profils, document, rfi = avec_profil
    inconnu = Utilisateur.objects.create_user("zoe", password="x", org_id=organisation.id)
    with pytest.raises(PermissionDenied):
        generer_guide(utilisateur=inconnu, project_id=projet.id, date=DATE)


def test_la_generation_est_journalisee_avec_lempreinte_du_pdf(avec_profil):
    organisation, projet, profils, document, rfi = avec_profil
    contenu = generer_guide(utilisateur=profils["dora"], project_id=projet.id, date=DATE)
    entree = AuditLog.objects.get(action="configuration_guide_generated")
    assert entree.after["sha256"] == hashlib.sha256(contenu).hexdigest()
    assert entree.after["date"] == "2027-09-30"
    assert verifier_chaine(organisation.id) is None


def test_la_commande_ecrit_le_pdf_et_refuse_un_utilisateur_inconnu(avec_profil, tmp_path):
    organisation, projet, profils, document, rfi = avec_profil
    sortie = tmp_path / "guide.pdf"
    call_command(
        "generer_guide_configuration",
        organisation=str(organisation.id),
        projet=str(projet.id),
        utilisateur="dora",
        date="2027-09-30",
        sortie=str(sortie),
    )
    assert "RFI (version 1)" in _texte(sortie.read_bytes())
    with pytest.raises(CommandError, match="Utilisateur introuvable"):
        call_command(
            "generer_guide_configuration",
            organisation=str(organisation.id),
            projet=str(projet.id),
            utilisateur="fantome",
            sortie=str(tmp_path / "x.pdf"),
        )


def test_les_details_rares_sont_lisibles(avec_profil):
    """Exigence conditionnelle issue d'un profil de bailleur, citation avec annexe et page,
    montants à la française, compte désigné plafonné, profil à fin de validité connue."""
    from niveau1_socle.financements.models import Accord
    from niveau1_socle.financements.services import creer_compte_bancaire
    from niveau2_profils.services.profils import (
        ajouter_element,
        creer_profil_bailleur,
        publier_profil,
    )
    from niveau3_config.models import ProfilDecaissement

    organisation, projet, profils, document, rfi = avec_profil
    # Une exigence conditionnelle, venue d'un profil de bailleur publié, étayée puis activée.
    bibliotheque = creer_profil_bailleur(
        utilisateur=profils["dora"], code="BIB", label={"fr": "Bibliothèque"}
    )
    ajouter_element(
        utilisateur=profils["dora"],
        profil=bibliotheque,
        kind="check",
        code="X",
        label={"fr": "x"},
    )
    publier_profil(utilisateur=profils["dora"], profil=bibliotheque)
    conditionnelle = Exigence.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        code="SEUIL",
        donor_profile_id=bibliotheque.id,
        document=document,
        citation={"annex": "2", "page": 3, "paragraph": "5.1", "quote": "au-delà du seuil"},
        subject="Documentation au-delà du seuil",
        rule={},
        obligation="conditional",
        condition_expr="si la dépense dépasse le seuil",
        valid_from=D(2026, 1, 1),
        version=1,
        source="manual",
        status="proposed",
    )
    Exigence.objects.filter(pk=conditionnelle.pk).update(
        status="active",
        validated_by=profils["dora"].id,
        validated_at=timezone.now(),
        citation_verifiee_sha256=document.sha256,
    )
    # Un compte désigné plafonné et une allocation à sept chiffres.
    accord = Accord.objects.get(numero="IDA-6789")
    compte = creer_compte_bancaire(
        utilisateur=profils["dora"],
        project_id=projet.id,
        code="CD",
        type="designe",
        devise="USD",
        banque="BCD",
        numero="DJ-0000-2",
        accord=accord,
    )
    profil = ProfilDecaissement.objects.get(accord=accord)
    nouveau = creer_profil(
        organisation,
        projet,
        accord,
        version=2,
        valid_from=D(2027, 1, 1),
        statut="draft",
        regles=[(profil.regles.get().category, "0.9", {"allocation": Decimal("1234567.5")})],
        comptes=[{"compte": compte, "plafond": Decimal("2500000"), "devise": "USD"}],
    )
    ProfilDecaissement.objects.filter(pk=profil.pk).update(valid_to=D(2027, 1, 1))
    ProfilDecaissement.objects.filter(pk=nouveau.pk).update(
        status="active", validated_by=profils["dora"].id, validated_at=timezone.now()
    )

    texte = _texte(generer_guide(utilisateur=profils["dora"], project_id=projet.id, date=DATE))
    assert "Nature : conditionnelle — condition : si la dépense dépasse le seuil" in texte
    assert "issue d'un profil de bailleur, étayée par le document du projet" in texte
    assert "annexe 2, page 3, § 5.1 : « au-delà du seuil »" in texte
    assert "saisie pour ce projet" in texte  # l'autre exigence, saisie à la main
    # À la date du guide (30/09/2027), V2 est en vigueur ; V1 l'était un an plus tôt.
    assert "Accord IDA-6789 — version 2" in texte
    assert "90 % (taxes comprises) ; allocation 1 234 567,50" in texte
    assert "Compte désigné, plafond 2 500 000,00 USD" in texte
    en_2026 = _texte(
        generer_guide(utilisateur=profils["dora"], project_id=projet.id, date=D(2026, 9, 30))
    )
    assert "Accord IDA-6789 — version 1" in en_2026
    assert "(taxes comprises) ; allocation 100,00" in en_2026
    assert "au 01/01/2027 (exclu)" in en_2026  # la fin de validité de V1 est dite au lecteur


def test_le_guide_en_anglais_est_rendu_dans_la_langue_demandee(avec_profil):
    """Même configuration, même date : le texte change de langue, pas les faits."""
    organisation, projet, profils, document, rfi = avec_profil
    fr = _texte(generer_guide(utilisateur=profils["dora"], project_id=projet.id, date=DATE))
    en = _texte(
        generer_guide(utilisateur=profils["dora"], project_id=projet.id, date=DATE, langue="en")
    )
    assert fr != en
    assert "Configuration guide" in en or "configuration guide" in en.lower()
    assert "Guide de configuration" in fr
    assert "RFI" in en and "RFI" in fr
