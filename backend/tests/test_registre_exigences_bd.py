"""Le registre des exigences : une citation inventée est refusée. Voir L5-T02.

Contrôle : une citation absente du document est refusée avec ce message exact.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework.exceptions import PermissionDenied

from core.audit import verifier_chaine
from niveau3_config import stockage
from niveau3_config.models import Exigence
from niveau3_config.services.documents import enregistrer_document, remplacer_document
from niveau3_config.services.exigences import (
    MESSAGE_INTROUVABLE,
    CitationIntrouvable,
    CitationInvalide,
    CitationMalPlacee,
    ExigenceInvalide,
    proposer_exigence,
    valider_citation,
)
from tests.outils import connexion_proprietaire
from tests.outils_documents import fabriquer_docx, fabriquer_pdf
from tests.test_cycle_ecriture_bd import _creer_projet, decor  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
DEBUT = datetime.date(2026, 1, 1)
PHRASE = (
    "Le rapport financier intermédiaire est remis dans les 45 jours suivant la fin du trimestre"
)
PAGES = ["Article 1. Objet de l'accord de financement.", f"Article 4.2. {PHRASE}.", "Annexe."]


@pytest.fixture
def base(cadre, settings, tmp_path):  # noqa: F811
    settings.STOCKAGE_DOCUMENTS_ROOT = tmp_path
    organisation, projet, profils, _ = cadre
    return organisation, projet, profils


def _document(profils, projet, contenu, *, title="DFIL", version="1"):
    return enregistrer_document(
        utilisateur=profils["dora"],
        project_id=projet.id,
        kind="dfil",
        title=title,
        version=version,
        contenu=contenu,
    )


def _proposer(profils, projet, document, citation, **champs):
    donnees = {
        "utilisateur": profils["dora"],
        "project_id": projet.id,
        "code": "IFR-TRIM",
        "document": document,
        "citation": citation,
        "subject": "Rapport financier intermédiaire",
        "rule": {"kind": "report"},
        "obligation": "mandatory",
        "valid_from": DEBUT,
        "periodicity": "quarterly",
        "due_offset_days": 45,
    } | champs
    return proposer_exigence(**donnees)


def _citation(**champs):
    return {"annex": "2", "paragraph": "4.2", "quote": "remis dans les 45 jours"} | champs


# --- le contrôle de la tâche ----------------------------------------------------------------


@pytest.mark.parametrize("format_", ["texte", "pdf", "docx"])
def test_une_citation_absente_du_document_est_refusee_avec_le_message_exact(base, format_):
    organisation, projet, profils = base
    contenu = {
        "texte": "\n".join(PAGES).encode(),
        "pdf": fabriquer_pdf(PAGES),
        "docx": fabriquer_docx(PAGES),
    }[format_]
    document = _document(profils, projet, contenu)
    with pytest.raises(CitationIntrouvable) as erreur:
        _proposer(
            profils,
            projet,
            document,
            _citation(quote="remis dans les 90 jours suivant la fin du trimestre"),
        )
    assert str(erreur.value) == "La citation n'a pas été retrouvée dans le document référencé."
    assert str(erreur.value) == MESSAGE_INTROUVABLE
    assert Exigence.objects.count() == 0  # rien n'est enregistré
    # La même citation, juste : acceptée, sur le même document.
    assert _proposer(profils, projet, document, _citation()).status == "proposed"


# --- ce qui est retrouvable -----------------------------------------------------------------


def test_une_citation_juste_est_enregistree_avec_son_empreinte_et_sa_trace(base):
    organisation, projet, profils = base
    document = _document(profils, projet, fabriquer_pdf(PAGES))
    exigence = _proposer(profils, projet, document, _citation(page=2))
    assert (exigence.status, exigence.version, exigence.source) == ("proposed", 1, "manual")
    assert bytes(exigence.citation_verifiee_sha256) == bytes(document.sha256)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT after->>'sha256' FROM core_auditlog WHERE action = 'requirement_proposed'"
        )
        assert cur.fetchone() == (bytes(document.sha256).hex(),)
    assert verifier_chaine(organisation.id) is None


def test_la_typographie_et_les_espaces_ne_font_pas_echouer_une_citation_juste(base):
    organisation, projet, profils = base
    texte = "Article 4.2 — L’agent doit remettre\nle rapport  dans les 45 jours suivants."
    document = _document(profils, projet, texte.encode())
    for quote in (
        "L'agent doit remettre le rapport dans les 45 jours suivants",
        "L’agent   doit remettre le rapport dans les 45 jours suivants.",
        "le rapport dans les 45 jours suivants",
    ):
        valider_citation(document, _citation(quote=quote))


def test_la_casse_et_les_accents_sont_significatifs(base):
    organisation, projet, profils = base
    document = _document(profils, projet, PHRASE.encode())
    for faux in (PHRASE.upper(), PHRASE.replace("é", "e"), PHRASE.replace("remis", "Remis")):
        with pytest.raises(CitationIntrouvable):
            valider_citation(document, _citation(quote=faux))


def test_une_citation_invariable_d_un_mot_pres_est_refusee(base):
    organisation, projet, profils = base
    document = _document(profils, projet, PHRASE.encode())
    with pytest.raises(CitationIntrouvable):
        valider_citation(document, _citation(quote=PHRASE.replace("45", "60")))
    with pytest.raises(CitationIntrouvable):
        valider_citation(document, _citation(quote=PHRASE + " et ses annexes"))  # plus long


# --- la page -------------------------------------------------------------------------------


def test_la_page_citee_est_verifiee_dans_un_pdf(base):
    organisation, projet, profils = base
    document = _document(profils, projet, fabriquer_pdf(PAGES))
    valider_citation(document, _citation(page=2))
    with pytest.raises(CitationMalPlacee, match=r"pas à la page indiquée \(1\)"):
        valider_citation(document, _citation(page=1))
    with pytest.raises(CitationMalPlacee, match="La page 9 n'existe pas"):
        valider_citation(document, _citation(page=9))
    with pytest.raises(CitationMalPlacee, match="La page 0 n'existe pas"):
        valider_citation(document, _citation(page=0))
    valider_citation(
        document, {"quote": "remis dans les 45 jours"} | {"paragraph": "4.2"}
    )  # sans page


def test_la_page_n_est_pas_verifiable_hors_pdf_et_ne_bloque_pas(base):
    organisation, projet, profils = base
    document = _document(profils, projet, PHRASE.encode())
    valider_citation(document, _citation(page=37))  # le texte brut n'a pas de pages


# --- forme de la citation et de l'exigence ---------------------------------------------------


@pytest.mark.parametrize(
    "citation, message",
    [
        ("texte", "est un objet"),
        ({"paragraph": "4.2"}, "extrait exact"),
        ({"paragraph": "4.2", "quote": "  "}, "extrait exact"),
        ({"paragraph": "4.2", "quote": 12}, "extrait exact"),
        ({"quote": "remis dans les 45 jours"}, "un paragraphe ou une page"),
        ({"paragraph": "4.2", "quote": "45 jours"}, "trop court"),
    ],
)
def test_une_citation_mal_formee_est_refusee(base, citation, message):
    organisation, projet, profils = base
    document = _document(profils, projet, PHRASE.encode())
    with pytest.raises(CitationInvalide, match=message):
        valider_citation(document, citation)


@pytest.mark.parametrize(
    "champs, message",
    [
        ({"code": " "}, "code et la rubrique"),
        ({"subject": ""}, "code et la rubrique"),
        ({"obligation": "obligatoire"}, "obligation inconnue"),
        ({"periodicity": "weekly"}, "périodicité inconnue"),
        ({"obligation": "conditional"}, "précise sa condition"),
        ({"source": "assisted"}, "confiance entre 0 et 1"),
        ({"source": "assisted", "confidence": "1.5"}, "confiance entre 0 et 1"),
        ({"confidence": "0.5"}, "n'existe que pour une exigence proposée"),
        ({"rule": "calcul"}, "La règle est un objet"),
        ({"source": "magie"}, "origine inconnue"),
    ],
)
def test_une_exigence_incoherente_est_refusee(base, champs, message):
    organisation, projet, profils = base
    document = _document(profils, projet, PHRASE.encode())
    with pytest.raises(ExigenceInvalide, match=message):
        _proposer(profils, projet, document, _citation(), **champs)
    assert Exigence.objects.count() == 0


def test_une_exigence_conditionnelle_et_une_exigence_assistee_valides(base):
    organisation, projet, profils = base
    document = _document(profils, projet, PHRASE.encode())
    conditionnelle = _proposer(
        profils,
        projet,
        document,
        _citation(),
        code="A",
        obligation="conditional",
        condition_expr="avance > 0",
    )
    assistee = _proposer(
        profils, projet, document, _citation(), code="B", source="assisted", confidence="0.870"
    )
    assert conditionnelle.condition_expr == "avance > 0" and str(assistee.confidence) == "0.870"


def test_un_meme_code_donne_une_nouvelle_version_jamais_une_modification(base):
    organisation, projet, profils = base
    document = _document(profils, projet, PHRASE.encode())
    v1 = _proposer(profils, projet, document, _citation())
    v2 = _proposer(profils, projet, document, _citation())
    assert (v1.version, v2.version) == (1, 2) and v1.pk != v2.pk
    assert Exigence.objects.get(pk=v1.pk).subject == v1.subject


# --- le document ---------------------------------------------------------------------------


def test_on_ne_cite_ni_un_document_remplace_ni_celui_d_un_autre_projet(base):
    organisation, projet, profils = base
    ancien = _document(profils, projet, PHRASE.encode())
    remplacer_document(
        utilisateur=profils["dora"],
        ancien=ancien,
        contenu=(PHRASE + " Avenant.").encode(),
        version="2",
    )
    ancien.refresh_from_db()
    with pytest.raises(ExigenceInvalide, match="est remplacé"):
        _proposer(profils, projet, ancien, _citation())
    autre = _creer_projet(organisation, "P2")
    etranger = Exigence.objects.none()
    from niveau3_config.models import DocumentReference

    document_autre = DocumentReference.objects.create(
        org_id=organisation.id,
        project_id=autre.id,
        kind="dfil",
        title="Autre",
        version="1",
        file_ref="fs://x",
        sha256=b"\x01" * 32,
    )
    with pytest.raises(ExigenceInvalide, match="n'appartient pas au projet"):
        _proposer(profils, projet, document_autre, _citation())
    assert not etranger.exists()


def test_une_citation_ne_se_verifie_pas_sur_un_fichier_modifie(base):
    organisation, projet, profils = base
    document = _document(profils, projet, PHRASE.encode())
    fichier = next(p for p in stockage.racine().rglob("*") if p.is_file())
    fichier.write_bytes((PHRASE + " Ajout en douce.").encode())
    with pytest.raises(CitationInvalide, match="ne correspond plus à son empreinte"):
        _proposer(profils, projet, document, _citation())
    assert Exigence.objects.count() == 0


def test_un_pdf_scanne_est_refuse_avec_la_raison(base):
    organisation, projet, profils = base
    document = _document(profils, projet, fabriquer_pdf(["", ""]))
    with pytest.raises(CitationInvalide, match="aucun texte extractible"):
        _proposer(profils, projet, document, _citation())


def test_proposer_exige_l_habilitation_parametrer(base):
    organisation, projet, profils = base
    document = _document(profils, projet, PHRASE.encode())
    with pytest.raises(PermissionDenied):
        _proposer(profils, projet, document, _citation(), utilisateur=profils["amina"])


# --- la base --------------------------------------------------------------------------------


def test_la_base_refuse_une_citation_mal_structuree_meme_en_sql_direct(base):
    organisation, projet, profils = base
    document = _document(profils, projet, PHRASE.encode())
    exigence = _proposer(profils, projet, document, _citation())
    with connexion_proprietaire() as admin:
        for citation, motif in [
            ('"juste du texte"', "exigence_citation_structuree"),
            ('{"paragraph": "4.2"}', "exigence_citation_structuree"),
            ('{"quote": "   ", "paragraph": "4.2"}', "exigence_citation_structuree"),
            ('{"quote": "extrait suffisant"}', "exigence_citation_structuree"),
            ('{"quote": 12345678901, "paragraph": "4.2"}', "exigence_citation_structuree"),
        ]:
            with pytest.raises(Exception, match=motif):
                admin.execute(
                    "UPDATE niveau3_config_exigence SET citation = %s::jsonb WHERE id = %s",
                    [citation, exigence.pk],
                )


def test_la_base_refuse_condition_et_confiance_incoherentes(base):
    organisation, projet, profils = base
    document = _document(profils, projet, PHRASE.encode())
    exigence = _proposer(profils, projet, document, _citation())
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="exigence_condition_si_conditionnelle"):
            admin.execute(
                "UPDATE niveau3_config_exigence SET obligation = 'conditional' WHERE id = %s",
                [exigence.pk],
            )
        with pytest.raises(Exception, match="exigence_confiance_si_assistee"):
            admin.execute(
                "UPDATE niveau3_config_exigence SET confidence = 0.5 WHERE id = %s", [exigence.pk]
            )
        with pytest.raises(Exception, match="exigence_confiance_si_assistee"):
            admin.execute(
                "UPDATE niveau3_config_exigence SET source = 'assisted', "
                "confidence = 1.5 WHERE id = %s",
                [exigence.pk],
            )


def test_la_base_refuse_une_exigence_active_dont_la_citation_n_a_pas_ete_verifiee(base):
    organisation, projet, profils = base
    document = _document(profils, projet, PHRASE.encode())
    exigence = _proposer(profils, projet, document, _citation())
    with connexion_proprietaire() as admin:
        admin.execute(
            "UPDATE niveau3_config_exigence SET citation_verifiee_sha256 = NULL WHERE id = %s",
            [exigence.pk],
        )  # une proposition peut ne pas l'avoir
        with pytest.raises(Exception, match="citation vérifiée dans le document référencé"):
            admin.execute(
                "UPDATE niveau3_config_exigence SET status = 'active', "
                "validated_by = gen_random_uuid(), validated_at = now() WHERE id = %s",
                [exigence.pk],
            )


def test_la_base_refuse_une_verification_faite_sur_un_autre_texte(base):
    organisation, projet, profils = base
    document = _document(profils, projet, PHRASE.encode())
    exigence = _proposer(profils, projet, document, _citation())
    with connexion_proprietaire() as admin:
        with pytest.raises(Exception, match="vérifiée sur un autre texte"):
            admin.execute(
                "UPDATE niveau3_config_exigence SET citation_verifiee_sha256 = %s WHERE id = %s",
                [b"\x07" * 32, exigence.pk],
            )
