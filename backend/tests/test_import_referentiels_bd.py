"""Import du plan comptable depuis Excel ou CSV. Voir L2-T07.

Assistant en trois temps : proposition de correspondance des colonnes, validation
HUMAINE nominative, import rejouable. Rejouer ne crée jamais de doublon ; un
compte déjà présent et différent est signalé en conflit, jamais écrasé.
"""

import csv
import hashlib
import io

import openpyxl
import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from core.audit import verifier_chaine
from niveau1_socle.referentiels.imports import (
    CorrespondanceNonValidee,
    ImportRejete,
    importer_plan_comptable,
    lire_fichier,
    proposer_correspondance,
    simuler_import,
)
from niveau1_socle.referentiels.models import Compte, CorrespondanceImport
from tests.test_organisations_bd import _creer_organisation

pytestmark = pytest.mark.django_db(transaction=True)
Utilisateur = get_user_model()
ENTETES = ["N° compte", "Intitulé", "Libellé (EN)", "Sens"]


def _poser(organisation):
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


def _plan(nombre=800):
    """Plan hiérarchique de `nombre` comptes (800 au plus), parents avant enfants.

    9 classes, 36 groupes, 180 sous-groupes, puis des feuilles. Un plan plus petit
    est un préfixe de celui-ci, donc toujours cohérent (jamais d'enfant sans parent).
    """
    complet = [(str(classe), f"Classe {classe}") for classe in range(1, 10)]
    groupes = [f"{c}{g}" for c in range(1, 10) for g in range(1, 5)]
    sous_groupes = [f"{g}{s}" for g in groupes for s in range(1, 6)]
    complet += [(g, f"Groupe {g}") for g in groupes]
    complet += [(sg, f"Sous-groupe {sg}") for sg in sous_groupes]
    for i in range(800 - len(complet)):
        sg = sous_groupes[i % len(sous_groupes)]
        complet.append((f"{sg}{i // len(sous_groupes) + 1}", f"Compte {sg}{i // 180 + 1}"))
    assert len({code for code, _ in complet}) == 800
    retenus = sorted(complet, key=lambda c: (len(c[0]), c[0]))[:nombre]
    return [
        [code, libelle, f"Account {code}", "C" if code[0] in "17" else "D"]
        for code, libelle in retenus
    ]


def _xlsx(lignes, entetes=ENTETES) -> bytes:
    classeur = openpyxl.Workbook()
    feuille = classeur.active
    feuille.append(entetes)
    for ligne in lignes:
        feuille.append(ligne)
    tampon = io.BytesIO()
    classeur.save(tampon)
    return tampon.getvalue()


def _csv(lignes, entetes=ENTETES, delimiteur=";") -> bytes:
    tampon = io.StringIO()
    ecrivain = csv.writer(tampon, delimiter=delimiteur)
    ecrivain.writerow(entetes)
    ecrivain.writerows(lignes)
    return b"\xef\xbb\xbf" + tampon.getvalue().encode("utf-8")  # BOM, comme Excel


MAPPING = {
    "code": "N° compte",
    "label:fr": "Intitulé",
    "label:en": "Libellé (EN)",
    "sens_normal": "Sens",
}


@pytest.fixture
def decor():
    organisation = _creer_organisation("ORG-A")
    amina = Utilisateur.objects.create_user("amina", password="x", org_id=organisation.id)
    _poser(organisation)
    return organisation, amina


def _correspondance(organisation, amina, *, valider=True, colonnes=None, defauts=None):
    _poser(organisation)
    return CorrespondanceImport.objects.create(
        org_id=organisation.id,
        nom="Export comptable 2026",
        type_referentiel="plan_comptable",
        colonnes=colonnes or MAPPING,
        valeurs_defaut=defauts or {},
        statut="validee" if valider else "proposee",
        validated_by=amina.id if valider else None,
        validated_at=timezone.now() if valider else None,
    )


# --- lecture -----------------------------------------------------------------------------


@pytest.mark.parametrize("fabrique", [_xlsx, _csv], ids=["xlsx", "csv"])
def test_excel_et_csv_donnent_les_memes_lignes(fabrique):
    lignes = [["601", "Achats", "Purchases", "D"], ["701", "Ventes", "Sales", "C"]]
    entetes, rangees = lire_fichier(fabrique(lignes), "plan")
    assert entetes == ENTETES
    assert rangees == [dict(zip(ENTETES, ligne, strict=True)) for ligne in lignes]


def test_un_csv_de_point_virgule_avec_bom_est_lu_comme_celui_dexcel():
    contenu = _csv([["601", "Achats ; fournitures", "Purchases", "D"]], delimiteur=";")
    _, rangees = lire_fichier(contenu, "plan.csv")
    assert rangees[0]["Intitulé"] == "Achats ; fournitures"


def test_les_codes_numeriques_dexcel_restent_des_codes_sans_decimale():
    """Excel enregistre souvent 601 comme le nombre 601.0 : le code reste « 601 »."""
    _, rangees = lire_fichier(_xlsx([[601, "Achats", "Purchases", "D"]]), "plan.xlsx")
    assert rangees[0]["N° compte"] == "601"


# --- proposition de correspondance --------------------------------------------------------


def test_la_correspondance_est_proposee_a_partir_des_en_tetes():
    proposition = proposer_correspondance(
        ["N° compte", "Intitulé", "Libellé (EN)", "Sens", "Notes"]
    )
    assert proposition.colonnes == MAPPING
    assert proposition.non_reconnues == ["Notes"]
    assert proposition.manquantes == []


def test_une_proposition_signale_les_champs_obligatoires_sans_colonne():
    proposition = proposer_correspondance(["Numéro", "Notes"])
    assert proposition.colonnes == {"code": "Numéro"}
    assert set(proposition.manquantes) == {"label:fr", "sens_normal"}


# --- validation humaine -------------------------------------------------------------------


def test_on_nimporte_pas_avec_une_correspondance_non_validee(decor):
    organisation, amina = decor
    correspondance = _correspondance(organisation, amina, valider=False)
    with pytest.raises(CorrespondanceNonValidee):
        importer_plan_comptable(_xlsx(_plan(10)), "p.xlsx", correspondance, utilisateur=amina)
    assert Compte.objects.count() == 0


def test_une_correspondance_validee_exige_un_validateur_nomme_et_date(decor):
    organisation, amina = decor
    with pytest.raises(IntegrityError), transaction.atomic():
        CorrespondanceImport.objects.create(
            org_id=organisation.id,
            nom="X",
            type_referentiel="plan_comptable",
            colonnes=MAPPING,
            statut="validee",
        )


def test_une_correspondance_validee_ne_se_modifie_plus_meme_en_sql_direct(decor):
    organisation, amina = decor
    correspondance = _correspondance(organisation, amina)
    with pytest.raises(IntegrityError, match="validée"), transaction.atomic():
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE referentiels_correspondanceimport SET colonnes = '{}' WHERE id = %s",
                [correspondance.id],
            )


# --- import : le contrôle de la tâche -----------------------------------------------------


def test_un_plan_de_800_comptes_depuis_excel_se_rejoue_sans_aucun_doublon(decor):
    """Contrôle de L2-T07."""
    organisation, amina = decor
    correspondance = _correspondance(organisation, amina)
    fichier = _xlsx(_plan(800))

    premier = importer_plan_comptable(fichier, "plan.xlsx", correspondance, utilisateur=amina)
    assert (premier.crees, premier.inchanges, premier.conflits) == (800, 0, [])
    assert Compte.objects.count() == 800

    rejeu = importer_plan_comptable(fichier, "plan.xlsx", correspondance, utilisateur=amina)
    assert (rejeu.crees, rejeu.inchanges, rejeu.conflits) == (0, 800, [])
    assert Compte.objects.count() == 800
    assert Compte.objects.values("code").distinct().count() == 800


def test_la_hierarchie_et_limputabilite_sont_deduites_du_plan(decor):
    organisation, amina = decor
    correspondance = _correspondance(organisation, amina)
    importer_plan_comptable(_xlsx(_plan(800)), "plan.xlsx", correspondance, utilisateur=amina)

    racine = Compte.objects.get(code="6")
    groupe = Compte.objects.get(code="61")
    assert racine.parent is None and not racine.imputable
    assert groupe.parent_id == racine.id and not groupe.imputable
    feuille = Compte.objects.filter(imputable=True).first()
    assert feuille.parent is not None and len(feuille.code) == 4
    assert not Compte.objects.filter(imputable=True, enfants__isnull=False).exists()
    assert Compte.objects.get(code="7").sens_normal == "credit"
    assert Compte.objects.get(code="611").label == {"fr": "Sous-groupe 611", "en": "Account 611"}


def test_un_compte_deja_present_et_different_est_un_conflit_jamais_ecrase(decor):
    organisation, amina = decor
    correspondance = _correspondance(organisation, amina)
    importer_plan_comptable(
        _xlsx([["6", "Charges", "Expenses", "D"], ["60", "Achats", "Purchases", "D"]]),
        "p.xlsx",
        correspondance,
        utilisateur=amina,
    )

    rapport = importer_plan_comptable(
        _xlsx([["6", "Charges", "Expenses", "D"], ["60", "Achats modifiés", "Purchases", "D"]]),
        "p.xlsx",
        correspondance,
        utilisateur=amina,
    )

    assert (rapport.crees, rapport.inchanges) == (0, 1)
    assert [c.code for c in rapport.conflits] == ["60"]
    assert "label" in rapport.conflits[0].differences
    assert Compte.objects.get(code="60").label["fr"] == "Achats"  # intact


def test_des_lignes_invalides_arretent_tout_et_sont_nommees_avec_leur_numero(decor):
    organisation, amina = decor
    correspondance = _correspondance(organisation, amina)
    fichier = _xlsx(
        [
            ["6", "Charges", "Expenses", "D"],  # ligne 2 : valide
            ["6A1", "Code faux", "Bad", "D"],  # ligne 3 : code non numérique
            ["60", "Achats", "Purchases", "X"],  # ligne 4 : sens inconnu
            ["6", "Doublon", "Dup", "D"],  # ligne 5 : code en double dans le fichier
            ["", "Sans code", "None", "D"],  # ligne 6 : code vide
        ]
    )

    with pytest.raises(ImportRejete) as erreur:
        importer_plan_comptable(fichier, "p.xlsx", correspondance, utilisateur=amina)

    assert {r.ligne: r.raison for r in erreur.value.rejets}.keys() == {3, 4, 5, 6}
    assert Compte.objects.count() == 0  # tout ou rien : la ligne valide n'est pas écrite


def test_la_simulation_ne_modifie_rien_et_annonce_le_resultat_de_limport(decor):
    organisation, amina = decor
    correspondance = _correspondance(organisation, amina)
    fichier = _xlsx(_plan(200))

    simule = simuler_import(fichier, "p.xlsx", correspondance)
    assert (simule.crees, simule.inchanges) == (200, 0)
    assert Compte.objects.count() == 0
    reel = importer_plan_comptable(fichier, "p.xlsx", correspondance, utilisateur=amina)
    assert (reel.crees, reel.inchanges) == (simule.crees, simule.inchanges)


def test_un_sens_par_defaut_de_la_correspondance_remplace_la_colonne_absente(decor):
    organisation, amina = decor
    correspondance = _correspondance(
        organisation,
        amina,
        colonnes={"code": "N° compte", "label:fr": "Intitulé"},
        defauts={"sens_normal": "debit"},
    )
    importer_plan_comptable(
        _xlsx([["6", "Charges", "Expenses", "D"]]), "p.xlsx", correspondance, utilisateur=amina
    )
    assert Compte.objects.get(code="6").sens_normal == "debit"


def test_un_enfant_dun_compte_existant_imputable_est_rejete_proprement(decor):
    organisation, amina = decor
    correspondance = _correspondance(organisation, amina)
    importer_plan_comptable(
        _xlsx([["601", "Achats", "Purchases", "D"]]), "p.xlsx", correspondance, utilisateur=amina
    )
    with pytest.raises(ImportRejete) as erreur:
        importer_plan_comptable(
            _xlsx([["6011", "Détail", "Detail", "D"]]), "p.xlsx", correspondance, utilisateur=amina
        )
    assert "imputable" in erreur.value.rejets[0].raison


def test_limport_est_journalise_avec_lempreinte_du_fichier_et_les_comptes(decor):
    organisation, amina = decor
    correspondance = _correspondance(organisation, amina)
    fichier = _xlsx(_plan(50))

    importer_plan_comptable(fichier, "plan.xlsx", correspondance, utilisateur=amina)

    with connection.cursor() as cur:
        cur.execute(
            "SELECT action, actor_id, after FROM core_auditlog "
            "WHERE action = 'referential_imported'"
        )
        action, acteur, apres = cur.fetchone()
    assert acteur == amina.id
    assert hashlib.sha256(fichier).hexdigest() in apres
    assert '"crees":50' in apres.replace(" ", "")
    assert verifier_chaine(organisation.id) is None


def test_deux_organisations_importent_le_meme_fichier_independamment(decor):
    organisation, amina = decor
    importer_plan_comptable(
        _xlsx(_plan(20)), "p.xlsx", _correspondance(organisation, amina), utilisateur=amina
    )
    autre = _creer_organisation("ORG-B")
    brigitte = Utilisateur.objects.create_user("brigitte", password="x", org_id=autre.id)
    rapport = importer_plan_comptable(
        _xlsx(_plan(20)), "p.xlsx", _correspondance(autre, brigitte), utilisateur=brigitte
    )
    assert (rapport.crees, rapport.inchanges) == (20, 0)
    assert Compte.objects.count() == 20
