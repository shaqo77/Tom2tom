"""Schémas d'écritures versionnés, immuables une fois utilisés. Voir L3-T06."""

import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied

from niveau1_socle.comptabilite.models import Ecriture, Journal, LigneSchema, SchemaEcriture
from niveau1_socle.comptabilite.schemas import (
    SchemaIncoherent,
    SchemaIntrouvable,
    generer_lignes_du_schema,
    saisir_depuis_schema,
    schema_applicable,
)
from niveau1_socle.comptabilite.services import (
    EcritureInvalide,
    comptabiliser_ecriture,
    saisir_ecriture,
    valider_ecriture,
)
from niveau1_socle.referentiels.comptes import CompteNonImputable
from niveau1_socle.referentiels.models import Compte
from tests.outils import _compte
from tests.test_cycle_ecriture_bd import JOUR, _poser, decor  # noqa: F401
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)

ACHAT = [
    {"compte": "6011", "sens": "debit", "regle": "base", "axes": {"dim1": "COMP-A"}},
    {"compte": "4452", "sens": "debit", "regle": "taux", "taux": "0.18"},
    {"compte": "4011", "sens": None, "regle": "solde"},
]


def _schema(organisation, code="ACHAT", version=1, debut="2026-01-01", fin=None, lignes=ACHAT):
    _compte(organisation.id, "4452")
    _compte(organisation.id, "4011")
    schema = SchemaEcriture.objects.create(
        org_id=organisation.id,
        journal=Journal.objects.get(code="OD"),
        code=code,
        version=version,
        valid_from=datetime.date.fromisoformat(debut),
        valid_to=datetime.date.fromisoformat(fin) if fin else None,
        label={"fr": "Achat avec TVA", "en": "Purchase with VAT"},
    )
    for rang, ligne in enumerate(lignes, start=1):
        LigneSchema.objects.create(
            org_id=organisation.id,
            schema=schema,
            rang=rang,
            compte=Compte.objects.get(code=ligne["compte"]),
            sens=ligne.get("sens"),
            regle=ligne["regle"],
            taux=Decimal(ligne["taux"]) if ligne.get("taux") else None,
            axes=ligne.get("axes", {}),
        )
    return schema


def _depuis_schema(projet, utilisateur, **champs):
    donnees = {
        "utilisateur": utilisateur,
        "project_id": projet.id,
        "code_schema": "ACHAT",
        "montant": Decimal("1000"),
        "date_comptable": JOUR,
        "libelle": "Facture fournisseur",
    } | champs
    return saisir_depuis_schema(**donnees)


# --- le schéma alimente la saisie ---------------------------------------------------------


def test_un_schema_alimente_la_saisie_et_la_piece_suit_le_circuit_normal(decor):  # noqa: F811
    organisation, projet, profils = decor
    schema = _schema(organisation)

    ecriture = _depuis_schema(projet, profils["amina"])

    lignes = {
        ligne.account.code: (ligne.debit, ligne.credit)
        for ligne in ecriture.lignes.select_related("account")
    }
    assert lignes == {
        "6011": (Decimal("1000"), 0),
        "4452": (Decimal("180"), 0),
        "4011": (0, Decimal("1180")),
    }
    assert ecriture.schema_id == schema.pk
    assert ecriture.lignes.get(account__code="6011").dim1.code == "COMP-A"

    valider_ecriture(ecriture, utilisateur=profils["bruno"])
    comptabiliser_ecriture(ecriture, utilisateur=profils["claire"])
    assert Ecriture.objects.get(pk=ecriture.pk).number == "OD-2026-000001"


def test_les_lignes_generees_se_retouchent_avant_d_etre_enregistrees(decor):  # noqa: F811
    """Le schéma ne remplace pas la saisie : c'est une proposition modifiable."""
    organisation, projet, profils = decor
    _schema(organisation)
    _, lignes = generer_lignes_du_schema("ACHAT", JOUR, Decimal("1000"), "DJF")

    lignes[1]["debit"] = "170"  # l'utilisateur corrige la TVA, sans toucher à la contrepartie
    with pytest.raises(EcritureInvalide, match="déséquilibrée"):
        saisir_ecriture(
            utilisateur=profils["amina"],
            project_id=projet.id,
            journal="OD",
            date_comptable=JOUR,
            libelle="Facture retouchée",
            lignes=lignes,
        )
    assert Ecriture.objects.count() == 0


def test_la_saisie_depuis_un_schema_garde_ses_garde_fous(decor):  # noqa: F811
    organisation, projet, profils = decor
    _schema(organisation)
    with pytest.raises(PermissionDenied):
        _depuis_schema(projet, profils["bruno"])  # bruno ne peut que valider

    Compte.objects.filter(code="4452").update(imputable=False)
    with pytest.raises(CompteNonImputable):
        _depuis_schema(projet, profils["amina"])
    assert Ecriture.objects.count() == 0


def test_un_schema_incoherent_est_refuse_a_la_generation(decor):  # noqa: F811
    organisation, projet, profils = decor
    _schema(
        organisation,
        lignes=[{"compte": "6011", "sens": "debit", "regle": "base"}] * 1
        + [{"compte": "4011", "sens": None, "regle": "solde"}],
    )
    with pytest.raises(SchemaIncoherent, match="nul après arrondi"):
        _depuis_schema(projet, profils["amina"], montant=Decimal("0.1"))  # DJF : 0 décimale


# --- versions -----------------------------------------------------------------------------


def test_le_schema_applicable_est_celui_en_vigueur_a_la_date_comptable(decor):  # noqa: F811
    organisation, projet, profils = decor
    v1 = _schema(organisation, version=1, debut="2026-02-01", fin="2026-07-01")
    nouvelles = [dict(ligne) for ligne in ACHAT]
    nouvelles[1]["taux"] = "0.10"
    v2 = _schema(organisation, version=2, debut="2026-07-01", lignes=nouvelles)

    assert schema_applicable("ACHAT", datetime.date(2026, 6, 30)) == v1
    assert schema_applicable("ACHAT", datetime.date(2026, 7, 1)) == v2  # début inclus, fin exclue
    with pytest.raises(SchemaIntrouvable, match="2026-01-15"):
        schema_applicable("ACHAT", datetime.date(2026, 1, 15))
    with pytest.raises(SchemaIntrouvable):
        schema_applicable("INCONNU", JOUR)

    avant = _depuis_schema(projet, profils["amina"], date_comptable=datetime.date(2026, 3, 15))
    apres = _depuis_schema(projet, profils["amina"], date_comptable=datetime.date(2026, 9, 15))
    assert (avant.schema_id, apres.schema_id) == (v1.pk, v2.pk)
    assert avant.lignes.get(account__code="4452").debit == Decimal("180")  # 18 %
    assert apres.lignes.get(account__code="4452").debit == Decimal("100")  # 10 %


def test_deux_versions_dun_meme_schema_ne_se_chevauchent_pas(decor):  # noqa: F811
    organisation, _, _ = decor
    _schema(organisation, version=1, debut="2026-01-01", fin="2026-07-01")
    with pytest.raises(IntegrityError, match="schema_sans_chevauchement"), transaction.atomic():
        _schema(organisation, version=2, debut="2026-06-01")
    _schema(organisation, version=2, debut="2026-07-01")  # contigu : accepté
    _schema(organisation, code="RECETTE", version=1, debut="2026-01-01")  # autre schéma


# --- immuabilité une fois utilisé ---------------------------------------------------------


def test_un_schema_utilise_ne_se_modifie_plus_on_en_cree_une_version(decor):  # noqa: F811
    organisation, projet, profils = decor
    schema = _schema(organisation)
    ligne = schema.lignes.get(rang=2)

    # Tant qu'aucune écriture ne l'a utilisé, il se corrige.
    LigneSchema.objects.filter(pk=ligne.pk).update(taux=Decimal("0.17"))
    LigneSchema.objects.filter(pk=ligne.pk).update(taux=Decimal("0.18"))

    _depuis_schema(projet, profils["amina"])

    with pytest.raises(IntegrityError, match="déjà utilisé"), transaction.atomic():
        LigneSchema.objects.filter(pk=ligne.pk).update(taux=Decimal("0.20"))
    with pytest.raises(IntegrityError, match="déjà utilisé"), transaction.atomic():
        LigneSchema.objects.filter(pk=ligne.pk).delete()
    with pytest.raises(IntegrityError, match="déjà utilisé"), transaction.atomic():
        LigneSchema.objects.create(
            org_id=organisation.id,
            schema=schema,
            rang=9,
            compte=ligne.compte,
            sens="debit",
            regle="base",
        )
    with pytest.raises(IntegrityError, match="déjà utilisé"), transaction.atomic():
        SchemaEcriture.objects.filter(pk=schema.pk).update(label={"fr": "Autre"})
    assert LigneSchema.objects.get(pk=ligne.pk).taux == Decimal("0.18")

    # On peut en revanche clore sa validité pour lui substituer une nouvelle version.
    SchemaEcriture.objects.filter(pk=schema.pk).update(valid_to=datetime.date(2026, 7, 1))


# --- contraintes de forme -----------------------------------------------------------------


@pytest.mark.parametrize(
    "champs",
    [
        {"regle": "formule", "sens": "debit"},  # ensemble fermé
        {"regle": "taux", "sens": "debit", "taux": None},  # taux obligatoire
        {"regle": "taux", "sens": "debit", "taux": Decimal("0")},  # strictement positif
        {"regle": "base", "sens": "debit", "taux": Decimal("0.1")},  # seul `taux` porte un taux
        {"regle": "solde", "sens": "debit"},  # la contrepartie déduit son sens
        {"regle": "base", "sens": None},  # sens obligatoire
        {"regle": "base", "sens": "neutre"},
        {"regle": "base", "sens": "debit", "rang": 0},
    ],
)
def test_la_forme_dune_ligne_de_schema_est_contrainte_en_base(decor, champs):  # noqa: F811
    organisation, _, _ = decor
    schema = _schema(organisation, lignes=[{"compte": "6011", "sens": "debit", "regle": "base"}])
    donnees = {
        "org_id": organisation.id,
        "schema": schema,
        "rang": 5,
        "compte": Compte.objects.get(code="6011"),
        "sens": "debit",
        "regle": "base",
        "taux": None,
    } | champs
    with pytest.raises(IntegrityError), transaction.atomic():
        LigneSchema.objects.create(**donnees)


def test_un_schema_na_quune_contrepartie_automatique(decor):  # noqa: F811
    organisation, _, _ = decor
    schema = _schema(organisation)  # a déjà sa ligne `solde`
    with pytest.raises(IntegrityError, match="uq_ligneschema_une_contrepartie"):
        with transaction.atomic():
            LigneSchema.objects.create(
                org_id=organisation.id,
                schema=schema,
                rang=9,
                compte=Compte.objects.get(code="4011"),
                regle="solde",
            )


def test_les_schemas_sont_isoles_par_organisation(decor):  # noqa: F811
    organisation, _, _ = decor
    _schema(organisation)
    autre = _creer_organisation("ORG-B")
    _poser(autre)
    assert SchemaEcriture.objects.count() == 0 and LigneSchema.objects.count() == 0
    with pytest.raises(SchemaIntrouvable):
        schema_applicable("ACHAT", JOUR)
