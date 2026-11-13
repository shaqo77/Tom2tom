# ruff: noqa: F811
"""Profils de bailleurs : une bibliothèque, jamais une obligation. Voir L5-T05.

Contrôle du plan : importer un profil dans un projet ne produit AUCUNE exigence active.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from niveau1_socle.habilitations.models import Habilitation, Role
from niveau2_profils.models import ElementProfil, ProfilBailleur
from niveau2_profils.services.profils import (
    ProfilInvalide,
    ajouter_element,
    creer_profil_bailleur,
    importer_profil,
    publier_profil,
)
from niveau3_config.models import Exigence
from niveau3_config.services.activation import (
    ActivationRefusee,
    activer_exigence,
    valider_exigence,
)
from niveau3_config.services.documents import remplacer_document
from niveau3_config.services.exigences import (
    CitationIntrouvable,
    ExigenceInvalide,
    etayer_exigence,
)
from tests.outils_documents import fabriquer_pdf
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_registre_exigences_bd import PAGES, _document, base  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
RFI = {
    "subject": "Rapport financier intermédiaire",
    "rule": {"kind": "report", "template": "IFR"},
    "periodicity": "quarterly",
    "due_offset_days": 45,
}


def _profil_publie(profils, *, code="IDA", elements=None, publier=True, **champs):
    profil = creer_profil_bailleur(
        utilisateur=profils["dora"], code=code, label={"fr": "Banque mondiale"}, **champs
    )
    elements = elements or [
        ("periodicity", "RFI-TRIM", RFI),
        ("check", "CTRL-COHERENCE", {"subject": "Cohérence des totaux", "obligation": "optional"}),
        ("export_format", "PDF", None),
    ]
    for position, (kind, code_element, exigence) in enumerate(elements):
        ajouter_element(
            utilisateur=profils["dora"],
            profil=profil,
            kind=kind,
            code=code_element,
            label={"fr": code_element},
            contenu={"note": "lorsque requis"},
            exigence=exigence,
            position=position,
        )
    return publier_profil(utilisateur=profils["dora"], profil=profil) if publier else profil


def _document_projet(profils, projet, contenu=None):
    return _document(profils, projet, contenu or fabriquer_pdf(PAGES))


@pytest.fixture
def vera(base):
    """vera valide et paramètre : elle mène une exigence importée jusqu'à l'activation."""
    organisation, projet, profils = base
    utilisateur = Utilisateur.objects.create_user("vera", password="x", org_id=organisation.id)
    role = Role.objects.create(
        org_id=organisation.id,
        code="VERA",
        label={"fr": "vera"},
        operations=["consulter", "valider", "parametrer"],
    )
    Habilitation.objects.create(
        org_id=organisation.id, user_id=utilisateur.id, project_id=projet.id, role=role
    )
    return utilisateur


# --- le contrôle de la tâche ---------------------------------------------------------------


def test_importer_un_profil_ne_produit_aucune_exigence_active(base):
    """LA règle absolue : le profil met à disposition, il n'impose rien."""
    organisation, projet, profils = base
    profil = _profil_publie(profils)
    document = _document_projet(profils, projet)

    resultat = importer_profil(
        utilisateur=profils["dora"], profil=profil, project_id=projet.id, document=document
    )

    assert Exigence.objects.filter(status="active").count() == 0
    assert Exigence.objects.filter(status="validated").count() == 0
    assert set(Exigence.objects.values_list("status", flat=True)) == {"proposed"}
    assert sorted(e.code for e in resultat.creees) == ["CTRL-COHERENCE", "RFI-TRIM"]
    importee = Exigence.objects.get(code="RFI-TRIM")
    assert importee.donor_profile_id == profil.id
    assert (importee.periodicity, importee.due_offset_days) == ("quarterly", 45)
    assert importee.citation["quote"].startswith("À étayer")  # ne se fait pas passer pour sourcée
    assert importee.citation_verifiee_sha256 is None
    assert verifier_chaine(organisation.id) is None


@pytest.mark.parametrize("statut", ["active", "validated"])
def test_la_base_refuse_une_exigence_issue_dun_profil_qui_ne_nait_pas_proposee(base, vera, statut):
    """Aucun chemin, y compris direct, ne crée une exigence issue d'un profil autrement."""
    organisation, projet, profils = base
    profil = _profil_publie(profils)
    document = _document_projet(profils, projet)
    with pytest.raises(IntegrityError, match="naît « proposed »"), transaction.atomic():
        Exigence.objects.create(
            org_id=organisation.id,
            project_id=projet.id,
            code="X",
            donor_profile_id=profil.id,
            document=document,
            citation={"quote": "dans les 45 jours", "paragraph": "4.2"},
            subject="x",
            rule={},
            obligation="mandatory",
            valid_from="2026-01-01",
            version=1,
            status=statut,
            source="manual",
            validated_by=vera.id,
            validated_at="2026-01-05T09:00:00Z",
            citation_verifiee_sha256=document.sha256,
        )


def test_un_profil_non_publie_ne_se_met_pas_a_disposition(base):
    organisation, projet, profils = base
    brouillon = _profil_publie(profils, publier=False)
    document = _document_projet(profils, projet)
    with pytest.raises(ProfilInvalide, match="publié"):
        importer_profil(
            utilisateur=profils["dora"], profil=brouillon, project_id=projet.id, document=document
        )
    with pytest.raises(IntegrityError, match="profil publié"), transaction.atomic():
        Exigence.objects.create(  # même en SQL direct : le profil doit être publié
            org_id=organisation.id,
            project_id=projet.id,
            code="X",
            donor_profile_id=brouillon.id,
            document=document,
            citation={"quote": "dans les 45 jours", "paragraph": "4.2"},
            subject="x",
            rule={},
            obligation="mandatory",
            valid_from="2026-01-01",
            version=1,
            status="proposed",
            source="manual",
        )
    assert Exigence.objects.count() == 0


# --- de la proposition à l'activation : toujours par un humain -----------------------------


def test_une_exigence_importee_ne_sactive_quapres_avoir_ete_etayee_par_le_document(base, vera):
    organisation, projet, profils = base
    profil = _profil_publie(profils)
    document = _document_projet(profils, projet)
    importer_profil(
        utilisateur=profils["dora"], profil=profil, project_id=projet.id, document=document
    )
    exigence = Exigence.objects.get(code="RFI-TRIM")

    with pytest.raises(ActivationRefusee, match="citation"):
        valider_exigence(utilisateur=vera, exigence=exigence)  # rien dans le document ne l'étaye
    with pytest.raises(CitationIntrouvable):
        etayer_exigence(
            utilisateur=vera,
            exigence=exigence,
            citation={"paragraph": "4.2", "quote": "remis dans les 90 jours suivant le trimestre"},
        )

    etayer_exigence(
        utilisateur=vera,
        exigence=exigence,
        citation={"annex": "2", "paragraph": "4.2", "quote": "remis dans les 45 jours"},
    )
    exigence.refresh_from_db()
    assert bytes(exigence.citation_verifiee_sha256) == bytes(document.sha256)
    assert exigence.status == "proposed"  # étayer n'active rien
    valider_exigence(utilisateur=vera, exigence=exigence)
    activer_exigence(utilisateur=vera, exigence=exigence)
    exigence.refresh_from_db()
    assert exigence.status == "active"


def test_on_nentaye_quune_exigence_proposee_et_il_faut_parametrer(base, vera):
    organisation, projet, profils = base
    profil = _profil_publie(profils)
    importer_profil(
        utilisateur=profils["dora"],
        profil=profil,
        project_id=projet.id,
        document=_document_projet(profils, projet),
    )
    exigence = Exigence.objects.get(code="RFI-TRIM")
    citation = {"paragraph": "4.2", "quote": "remis dans les 45 jours"}
    with pytest.raises(PermissionDenied):
        etayer_exigence(utilisateur=profils["bruno"], exigence=exigence, citation=citation)
    etayer_exigence(utilisateur=vera, exigence=exigence, citation=citation)
    valider_exigence(utilisateur=vera, exigence=exigence)
    exigence.refresh_from_db()
    with pytest.raises(ExigenceInvalide, match="proposée"):
        etayer_exigence(utilisateur=vera, exigence=exigence, citation=citation)


# --- importer deux fois, dans deux projets -------------------------------------------------


def test_importer_deux_fois_ne_duplique_rien_et_la_base_le_garantit(base):
    organisation, projet, profils = base
    profil = _profil_publie(profils)
    document = _document_projet(profils, projet)
    importer_profil(
        utilisateur=profils["dora"], profil=profil, project_id=projet.id, document=document
    )
    seconde = importer_profil(
        utilisateur=profils["dora"], profil=profil, project_id=projet.id, document=document
    )
    assert seconde.creees == [] and sorted(seconde.deja_proposees) == ["CTRL-COHERENCE", "RFI-TRIM"]
    assert Exigence.objects.count() == 2
    modele = Exigence.objects.get(code="RFI-TRIM")
    with pytest.raises(IntegrityError, match="uq_exigence_importee_en_attente"):
        with transaction.atomic():
            Exigence.objects.create(
                org_id=organisation.id,
                project_id=projet.id,
                code="RFI-TRIM",
                donor_profile_id=profil.id,
                document=document,
                citation=modele.citation,
                subject="doublon",
                rule={},
                obligation="mandatory",
                valid_from="2026-01-01",
                version=2,
                status="proposed",
                source="manual",
            )


def test_un_profil_se_reutilise_dun_projet_a_lautre_sans_changer(base):
    organisation, projet, profils = base
    second = _creer_projet(organisation, "P2")
    role = Role.objects.get(org_id=organisation.id, code="DORA")
    Habilitation.objects.create(
        org_id=organisation.id, user_id=profils["dora"].id, project_id=second.id, role=role
    )
    profil = _profil_publie(profils)
    for p in (projet, second):
        importer_profil(
            utilisateur=profils["dora"],
            profil=profil,
            project_id=p.id,
            document=_document_projet(profils, p),
        )
    assert Exigence.objects.filter(project_id=projet.id).count() == 2
    assert Exigence.objects.filter(project_id=second.id).count() == 2
    assert set(Exigence.objects.values_list("status", flat=True)) == {"proposed"}


def test_on_ne_met_pas_a_disposition_sur_un_projet_ou_un_document_qui_nest_pas_le_sien(base):
    organisation, projet, profils = base
    profil = _profil_publie(profils)
    document = _document_projet(profils, projet)
    with pytest.raises(PermissionDenied):
        importer_profil(
            utilisateur=profils["bruno"], profil=profil, project_id=projet.id, document=document
        )
    autre = _creer_projet(organisation, "P3")
    with pytest.raises(PermissionDenied):  # dora n'est pas habilitée sur P3
        importer_profil(
            utilisateur=profils["dora"], profil=profil, project_id=autre.id, document=document
        )
    remplace = remplacer_document(
        utilisateur=profils["dora"],
        ancien=document,
        contenu=fabriquer_pdf(PAGES + ["Annexe 2."]),
        version="2",
    )
    with pytest.raises(ProfilInvalide, match="remplacé"):
        importer_profil(
            utilisateur=profils["dora"], profil=profil, project_id=projet.id, document=document
        )
    assert importer_profil(
        utilisateur=profils["dora"], profil=profil, project_id=projet.id, document=remplace
    ).creees


# --- la bibliothèque : création, publication, immutabilité ---------------------------------


def test_creer_et_publier_exigent_lhabilitation_parametrer(base):
    organisation, projet, profils = base
    with pytest.raises(PermissionDenied):
        creer_profil_bailleur(utilisateur=profils["bruno"], code="X", label={"fr": "x"})
    profil = _profil_publie(profils, publier=False)
    with pytest.raises(PermissionDenied):
        publier_profil(utilisateur=profils["bruno"], profil=profil)
    with pytest.raises(PermissionDenied):
        ajouter_element(
            utilisateur=profils["bruno"], profil=profil, kind="check", code="Z", label={"fr": "z"}
        )


@pytest.mark.parametrize(
    "champs, message",
    [
        ({"kind": "script"}, "type d'élément inconnu"),
        ({"code": " "}, "obligatoires"),
        ({"label": {}}, "obligatoires"),
        ({"exigence": {"subject": " "}}, "rubrique"),
        ({"exigence": {"subject": "x", "obligation": "souhaitable"}}, "obligation inconnue"),
        ({"exigence": {"subject": "x", "periodicity": "hebdo"}}, "périodicité inconnue"),
        ({"exigence": {"subject": "x", "obligation": "conditional"}}, "condition"),
        ({"exigence": {"subject": "x", "magie": 1}}, "inconnus"),
        ({"exigence": ["x"]}, "objet"),
    ],
)
def test_un_element_invalide_est_refuse(base, champs, message):
    _, _, profils = base
    profil = _profil_publie(profils, publier=False)
    donnees = {"kind": "check", "code": "NEW", "label": {"fr": "n"}} | champs
    with pytest.raises(ProfilInvalide, match=message):
        ajouter_element(utilisateur=profils["dora"], profil=profil, **donnees)


def test_un_profil_publie_ne_change_plus_y_compris_en_sql_direct(base):
    from django.db import connection

    _, _, profils = base
    profil = _profil_publie(profils)
    with pytest.raises(ProfilInvalide, match="déjà publié"):
        publier_profil(utilisateur=profils["dora"], profil=profil)
    with pytest.raises(ProfilInvalide, match="plus d'élément"):
        ajouter_element(
            utilisateur=profils["dora"], profil=profil, kind="check", code="Z", label={"fr": "z"}
        )
    element = profil.elements.first()
    for sql, params, message in [
        ("UPDATE niveau2_profils_elementprofil SET code='X' WHERE id=%s", [element.id], "éléments"),
        ("DELETE FROM niveau2_profils_elementprofil WHERE id=%s", [element.id], "éléments"),
        (
            "UPDATE niveau2_profils_profilbailleur SET description='x' WHERE id=%s",
            [profil.id],
            "ne se modifie pas",
        ),
        (
            "DELETE FROM niveau2_profils_profilbailleur WHERE id=%s",
            [profil.id],
            "ne se supprime pas",
        ),
    ]:
        with pytest.raises(IntegrityError, match=message):
            with transaction.atomic(), connection.cursor() as cur:
                cur.execute(sql, params)


def test_un_brouillon_se_modifie_et_une_nouvelle_version_se_publie_a_cote(base):
    _, _, profils = base
    v1 = _profil_publie(profils)
    v2 = _profil_publie(profils, version=2, elements=[("check", "NOUVEAU", None)])
    assert (v1.status, v2.status, v2.version) == ("published", "published", 2)
    with pytest.raises(IntegrityError, match="uq_profil_bailleur_version"), transaction.atomic():
        creer_profil_bailleur(utilisateur=profils["dora"], code="IDA", label={"fr": "x"}, version=2)
    vide = creer_profil_bailleur(utilisateur=profils["dora"], code="VIDE", label={"fr": "v"})
    with pytest.raises(ProfilInvalide, match="aucun élément"):
        publier_profil(utilisateur=profils["dora"], profil=vide)


def test_la_base_refuse_un_profil_publie_sans_trace_et_un_element_hors_ensemble(base):
    organisation, _, profils = base
    with pytest.raises(IntegrityError, match="profil_bailleur_publication_tracee"):
        with transaction.atomic():
            ProfilBailleur.objects.create(
                org_id=organisation.id, code="Z", label={"fr": "z"}, status="published"
            )
    profil = _profil_publie(profils, publier=False)
    with pytest.raises(IntegrityError, match="element_profil_type_ferme"), transaction.atomic():
        ElementProfil.objects.create(
            org_id=organisation.id, profil=profil, kind="script", code="s", label={"fr": "s"}
        )
    with pytest.raises(IntegrityError, match="element_profil_objets_json"), transaction.atomic():
        ElementProfil.objects.create(
            org_id=organisation.id,
            profil=profil,
            kind="check",
            code="t",
            label={"fr": "t"},
            contenu=["pas", "un", "objet"],
        )
