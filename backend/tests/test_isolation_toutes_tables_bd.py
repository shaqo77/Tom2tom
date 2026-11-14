"""L'isolation vérifiée sur TOUTES les tables. Contrôle de sortie des fondations.

Deux cases du contrôle de sortie le demandent :
- « Isolation : test d'accès croisé en échec sur TOUTES les tables » ;
- « UPDATE de org_id vers une autre organisation refusé sur toutes les tables ».

1. STRUCTUREL, sur chaque table (aucune donnée requise) : la politique est unique, vaut pour toute
   commande, et son USING et son WITH CHECK sont IDENTIQUES au filtre d'organisation. USING
   cloisonne ce qu'on lit et ce qu'on modifie ; WITH CHECK refuse toute ligne dont `org_id`
   sortirait du périmètre : un INSERT pour une autre organisation, un UPDATE de `org_id` vers
   une autre.
2. COMPORTEMENTAL, sur chaque table peuplée par un scénario qui touche tout le projet : l'autre
   organisation ne voit AUCUNE ligne, une lecture sans périmètre non plus, et déplacer une ligne
   vers l'autre organisation est refusé (les lignes gardent leur `org_id`, vérifié hors RLS).
   Les tables que le scénario ne peuple pas sont NOMMÉES, avec la raison : une nouvelle table non
   peuplée ne passe pas sans qu'on s'en explique.
"""

import datetime
import hashlib
import uuid
from decimal import Decimal

import pytest
from django.db import connection

from niveau1_socle.avances.services import justifier_avance, parametrer_delai, verser_avance
from niveau1_socle.budget.controle import parametrer_controle
from niveau1_socle.budget.engagements import creer_engagement
from niveau1_socle.budget.services import ajouter_ligne, approuver_version, creer_version
from niveau1_socle.decaissements.services import preparer_demande, soumettre_demande
from niveau1_socle.financements.cles import creer_cle, creer_version_cle
from niveau1_socle.financements.services import (
    creer_avenant,
    creer_compte_bancaire,
)
from niveau1_socle.rapprochement.services import importer_mouvements, rapprocher
from niveau1_socle.referentiels.models import Tiers
from niveau2_profils.services.profils import ajouter_element, creer_profil_bailleur
from niveau3_config.models import Echeance, Exigence, Reallocation
from niveau4_reporting.controles.circuit import creer_circuit, decider_etape, ouvrir_demande
from niveau4_reporting.controles.derogations import (
    decider_derogation,
    demander_derogation,
    justifier,
)
from niveau4_reporting.controles.services import (
    activer_controle,
    creer_controle,
    evaluer_controle,
    trancher,
    valider_controle,
)
from niveau4_reporting.publication.models import (
    FichierRapport,
    MotifRejet,
    RapportPublie,
    SimulationRevue,
    SoumissionBailleur,
)
from tests.outils import connexion_proprietaire
from tests.outils_profil import creer_profil
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import DEBUT, FIN, _depense, drf  # noqa: F401
from tests.test_financements_bd import _document, cadre  # noqa: F401
from tests.test_isolation import TABLES_SANS_ISOLATION
from tests.test_organisations_bd import _creer_organisation
from tests.test_rapprochement_bancaire_bd import _ligne, _mouvement

pytestmark = pytest.mark.django_db(transaction=True)
D = Decimal
# Le filtre d'organisation tel que PostgreSQL le rend (voir `activer_rls`, core/migrations/_rls.py).
FILTRE = "({col} = (NULLIF(current_setting('app.org_id'::text, true), ''::text))::uuid)"


def _tables_a_org_id():
    with connection.cursor() as cur:
        cur.execute(
            """SELECT c.relname FROM pg_class c
                 JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'org_id'
                                    AND NOT a.attisdropped
                WHERE c.relkind = 'r'
                  AND c.relnamespace = (SELECT relnamespace FROM pg_class
                                         WHERE oid = to_regclass('core_auditlog'))
                ORDER BY 1"""
        )
        tables = [r[0] for r in cur.fetchall() if r[0] not in TABLES_SANS_ISOLATION]
    # L'organisation elle-même est isolée par sa propre clé `id`.
    return tables + ["organisations_organisation"]


def _colonne(table):
    return "id" if table == "organisations_organisation" else "org_id"


# --- 1. structurel, toutes les tables ------------------------------------------------------


def test_la_politique_de_chaque_table_est_exactement_le_filtre_d_organisation():
    tables = _tables_a_org_id()
    assert len(tables) > 45  # le garde-fou ne doit pas devenir muet si la requête change
    with connection.cursor() as cur:
        cur.execute(
            """SELECT p.tablename, p.policyname, p.cmd, p.permissive, p.qual, p.with_check
                 FROM pg_policies p
                WHERE p.schemaname = (SELECT n.nspname FROM pg_class c
                                        JOIN pg_namespace n ON n.oid = c.relnamespace
                                       WHERE c.oid = to_regclass('core_auditlog'))"""
        )
        politiques: dict[str, list] = {}
        for table, nom, cmd, permissive, qual, with_check in cur.fetchall():
            politiques.setdefault(table, []).append((nom, cmd, permissive, qual, with_check))
    ecarts = []
    for table in tables:
        attendu = FILTRE.format(col=_colonne(table))
        liste = politiques.get(table, [])
        if len(liste) != 1:
            ecarts.append(f"{table} : {len(liste)} politique(s) au lieu d'une")
            continue
        nom, cmd, permissive, qual, with_check = liste[0]
        if (nom, cmd, permissive) != ("org_isolation", "ALL", "PERMISSIVE"):
            ecarts.append(f"{table} : politique {nom}/{cmd}/{permissive}")
        if qual != attendu:
            ecarts.append(f"{table} : USING = {qual}")
        if with_check != attendu:
            ecarts.append(f"{table} : WITH CHECK = {with_check}")
    assert not ecarts, "\n".join(ecarts)


def test_aucune_table_isolee_n_est_ouverte_au_role_applicatif_sans_politique():
    """RLS FORCÉE sur chaque table : même le propriétaire de la table la subit."""
    with connection.cursor() as cur:
        cur.execute(
            """SELECT relname FROM pg_class
                WHERE relname = ANY(%s) AND NOT (relrowsecurity AND relforcerowsecurity)""",
            [_tables_a_org_id()],
        )
        assert cur.fetchall() == []


# --- 2. comportemental, tables peuplées -----------------------------------------------------

# Tables que le scénario ci-dessous ne peuple pas, avec la raison : leurs propres tests
# d'isolation (une ligne par table, `test_*_sont_isolees_par_organisation`) les couvrent.
NON_PEUPLEES = {
    "comptabilite_anouveau": "il faut un exercice clos (test_cloture_annuelle_bd)",
    "comptabilite_lettrage": "test_lettrage_bd",
    "comptabilite_schemaecriture": "test_schemas_ecriture_bd",
    "comptabilite_ligneschema": "test_schemas_ecriture_bd",
    "mapping_table": "test_mapping_bd, test_compilateur_bd",
    "mapping_rule": "test_mapping_bd, test_compilateur_bd",
    "niveau3_config_rattachementexigence": "test_exigences_bd",
    "referentiels_correspondanceimport": "test_import_referentiels_bd",
    "referentiels_taux": "test_devises_taux_bd",
}


def _peupler(organisation, projet, profils, accord, categories):
    """Un scénario qui touche budget, cofinancement, avances, demandes et comptes bancaires."""
    amina, bruno, dora = profils["amina"], profils["bruno"], profils["dora"]
    # Budget approuvé, engagement, contrôle budgétaire.
    version = creer_version(utilisateur=amina, project_id=projet.id, type="initial")
    ajouter_ligne(
        version,
        utilisateur=amina,
        annee=2026,
        montant="5000",
        devise="DJF",
        axes={"dim1": "COMP-A"},
    )
    approuver_version(version, utilisateur=bruno)
    parametrer_controle(
        utilisateur=dora,
        project_id=projet.id,
        axe="dim1",
        mode="bloquant",
        date_effet=datetime.date(2020, 1, 1),
    )
    creer_engagement(
        utilisateur=amina,
        project_id=projet.id,
        reference="E1",
        annee=2026,
        montant="100",
        axes={"dim1": "COMP-A"},
    )
    # Clé de cofinancement.
    cle = creer_cle(utilisateur=dora, project_id=projet.id, code="CLE", label={"fr": "Clé"})
    creer_version_cle(
        utilisateur=dora,
        cle=cle,
        poids={accord: 1},
        porteur=accord,
        valid_from=datetime.date(2026, 1, 1),
    )
    # Avenant, compte bancaire.
    creer_avenant(
        utilisateur=dora,
        accord=accord,
        reference="AV-1",
        date_avenant=datetime.date(2026, 3, 1),
        document=_document(organisation, projet),
        montant_revise="1200",
    )
    compte = creer_compte_bancaire(
        utilisateur=dora,
        project_id=projet.id,
        code="CB",
        type="designe",
        devise="DJF",
        banque="BCD",
        numero="DJ-0000-1",
        accord=accord,
    )
    # Relevé et rapprochement bancaire.
    claire = profils["claire"]
    ligne_bancaire = _ligne(organisation, projet, compte, 100)
    (mouvement,) = importer_mouvements(
        utilisateur=claire, compte=compte, mouvements=[_mouvement(compte, "R1", "100")]
    )[0]
    rapprocher(utilisateur=claire, compte=compte, lignes=[ligne_bancaire], mouvements=[mouvement])
    # Avances.
    agent = Tiers.objects.create(org_id=organisation.id, code="AG", nature="personnel", nom="AG")
    parametrer_delai(utilisateur=dora, project_id=projet.id, jours=30, date_effet=DEBUT)
    avance = verser_avance(
        utilisateur=amina,
        project_id=projet.id,
        tiers=agent,
        reference="AV",
        montant="100",
        date_versement=DEBUT,
    )
    justifier_avance(
        avance,
        utilisateur=amina,
        type="depense",
        montant="40",
        date_justification=DEBUT,
        reference="PJ",
    )
    # Demande de retrait, avec mise à l'écart.
    a = _depense(organisation, projet, accord, categories["serv"], 50)
    b = _depense(organisation, projet, accord, categories["serv"], 30)
    demande = preparer_demande(
        utilisateur=amina,
        accord=accord,
        type="reapprovisionnement",
        periode_debut=DEBUT,
        periode_fin=FIN,
        lignes=[a],
        ecarts={b: "Justificatif manquant"},
    )
    soumettre_demande(demande, utilisateur=bruno)
    # Profil de décaissement (créé en dernier : il changerait les demandes préparées après lui).
    creer_profil(
        organisation,
        projet,
        accord,
        regles=[(categories["serv"], "0.8")],
        comptes=[{"compte": compte, "plafond": D(1000)}],
        methodes=[{"method": "reimbursement", "supporting_docs": ["soe"]}],
    )
    Reallocation.objects.create(  # une demande de réallocation (L5-T04bis)
        org_id=organisation.id,
        project_id=projet.id,
        accord=accord,
        source=categories["serv"],
        cible=categories["biens"],
        montant=D(10),
        devise_id="DJF",
        date_effet=datetime.date(2026, 7, 1),
        motif="Test d'isolation",
        demandeur=dora.id,
    )
    controle = creer_controle(  # un contrôle, son évaluation et sa décision (L6-T01b)
        utilisateur=dora,
        project_id=projet.id,
        code="REVUE",
        label={"fr": "Revue des pièces"},
        type_regle="pieces",
        severity="bloquant",
        valid_from=datetime.date(2026, 1, 1),
        manuel=True,
    )
    controle = valider_controle(utilisateur=profils["bruno"], controle=controle)
    controle = activer_controle(utilisateur=dora, controle=controle)
    evaluation = evaluer_controle(
        controle,
        {},
        date_operation=datetime.date(2026, 6, 1),
        objet_type="depense",
        service="isolation",
    )
    trancher(utilisateur=profils["bruno"], evaluation=evaluation, decision="conforme", motif="Vu")
    RapportPublie.objects.create(  # un rapport publié et scellé (L6-T04)
        org_id=organisation.id,
        project_id=projet.id,
        template_code="TER",
        modele={"code": "TER"},
        period_from=datetime.date(2026, 1, 1),
        period_to=datetime.date(2026, 3, 31),
        values={"R110/QTR": "1"},
        dataset_hash=b"\x01" * 32,
        seal=b"\x02" * 32,
        published_by=dora.id,
        published_at=datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC),
    )
    FichierRapport.objects.create(  # un fichier de rapport avec son empreinte (L6-T05)
        org_id=organisation.id,
        rapport=RapportPublie.objects.get(project_id=projet.id),
        format="pdf",
        langue="fr",
        nom="TER.pdf",
        contenu=b"%PDF",
        sha256=hashlib.sha256(b"%PDF").hexdigest(),
        taille=4,
        produit_par=dora.id,
    )
    exigence = Exigence.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        code="RFI",
        document=_document(organisation, projet, "Accord de financement"),
        citation={"paragraph": "4.2", "quote": "remis dans les 45 jours"},
        subject="RFI",
        rule={},
        periodicity="quarterly",
        due_offset_days=45,
        obligation="mandatory",
        valid_from=datetime.date(2026, 1, 1),
        version=1,
        source="manual",
    )
    Echeance.objects.create(  # une échéance du calendrier des obligations (L6-T06)
        org_id=organisation.id,
        project_id=projet.id,
        exigence=exigence,
        periode_debut=datetime.date(2026, 1, 1),
        periode_fin=datetime.date(2026, 3, 31),
        date_echeance=datetime.date(2026, 5, 15),
    )
    MotifRejet.objects.create(  # un motif de rejet connu, une simulation et un envoi (L6-T07)
        org_id=organisation.id,
        project_id=projet.id,
        code="M1",
        label={"fr": "m", "en": "m"},
        controle_code="REVUE",
    )
    simulation = SimulationRevue.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        objet_type="rapport",
        date_effet=datetime.date(2026, 6, 1),
        avis="go",
        constats=[],
        lancee_par=dora.id,
    )
    SoumissionBailleur.objects.create(
        org_id=organisation.id,
        project_id=projet.id,
        template_code="TER",
        period_to=datetime.date(2026, 3, 31),
        numero_envoi=1,
        simulation=simulation,
        envoyee_le=datetime.date(2026, 5, 10),
        saisie_par=dora.id,
    )
    # Justification, dérogation et circuit de validation (L6-T02).
    justifier(utilisateur=amina, evaluation=evaluation, texte="Pièces attendues du fournisseur")
    depassement = creer_controle(
        utilisateur=dora,
        project_id=projet.id,
        code="PLAFOND",
        label={"fr": "Plafond", "en": "Ceiling"},
        type_regle="budget",
        severity="bloquant",
        valid_from=datetime.date(2026, 1, 1),
        expression={
            "type_regle": "budget",
            "conditions": [{"champ": "depense_cumulee", "op": "lte", "valeur": "1000"}],
        },
    )
    depassement = activer_controle(
        utilisateur=dora,
        controle=valider_controle(utilisateur=profils["bruno"], controle=depassement),
    )
    bloque = evaluer_controle(
        depassement,
        {"montant": D(10), "depense_cumulee": D(5000)},
        date_operation=datetime.date(2026, 6, 1),
        objet_type="depense",
        service="isolation",
    )
    derogation = demander_derogation(
        utilisateur=amina,
        evaluation=bloque,
        motif="Urgence",
        justificatif="NO-1",
        valide_du=datetime.date(2026, 6, 1),
        valide_jusquau=datetime.date(2026, 7, 1),
    )
    decider_derogation(
        utilisateur=profils["bruno"], derogation=derogation, approuver=True, motif="Vu"
    )
    creer_circuit(
        utilisateur=dora,
        project_id=projet.id,
        objet_type="depense",
        valid_from=datetime.date(2026, 1, 1),
        etapes=[{"nom": {"fr": "Validation", "en": "Validation"}, "operation": "valider"}],
    )
    demande = ouvrir_demande(
        utilisateur=amina,
        project_id=projet.id,
        objet_type="depense",
        objet_id=uuid.uuid4(),
        date_effet=datetime.date(2026, 6, 1),
    )
    decider_etape(utilisateur=profils["bruno"], demande=demande, rang=1, approuver=True)
    bibliotheque = creer_profil_bailleur(
        utilisateur=dora, code="IDA", label={"fr": "Banque mondiale"}
    )
    ajouter_element(  # un profil de bailleur et son élément (L5-T05)
        utilisateur=dora,
        profil=bibliotheque,
        kind="periodicity",
        code="RFI",
        label={"fr": "RFI trimestriel"},
        exigence={"subject": "RFI", "periodicity": "quarterly", "due_offset_days": 45},
    )


def _compter(cur, table):
    cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608  (noms issus du catalogue)
    return cur.fetchone()[0]


def test_l_autre_organisation_ne_voit_rien_et_rien_ne_se_deplace_vers_elle(drf):  # noqa: F811
    organisation, projet, profils, accord, categories = drf
    _peupler(organisation, projet, profils, accord, categories)
    autre = _creer_organisation("ORG-B")  # pose aussi son périmètre ; on revient sur A ensuite
    tables = _tables_a_org_id()
    assert {t for t in NON_PEUPLEES} <= set(tables), "table inconnue dans NON_PEUPLEES"

    # Ce que l'organisation A possède réellement, hors RLS (connexion propriétaire).
    with connexion_proprietaire() as admin:
        possede = {}
        for table in tables:
            col = _colonne(table)
            possede[table] = admin.execute(
                f"SELECT count(*) FROM {table} WHERE {col} = %s",  # noqa: S608
                [organisation.id],
            ).fetchone()[0]
    peuplees = {t for t, n in possede.items() if n > 0}
    vides = set(tables) - peuplees
    assert vides == set(NON_PEUPLEES), (
        f"Tables vides non déclarées : {sorted(vides - set(NON_PEUPLEES))} ; "
        f"déclarées mais peuplées : {sorted(set(NON_PEUPLEES) - vides)}"
    )

    with connection.cursor() as cur:
        # A) L'organisation B ne voit AUCUNE ligne de A, sur aucune table.
        cur.execute("SET app.org_id = %s", [str(autre.id)])
        visibles_par_b = {t: _compter(cur, t) for t in tables}
        # B) Sans périmètre, rien n'est visible : défaut sûr.
        cur.execute("RESET app.org_id")
        sans_perimetre = {t: _compter(cur, t) for t in tables}
    for table in tables:
        propres_a_b = 1 if table == "organisations_organisation" else 0  # B se voit elle-même
        assert visibles_par_b[table] == propres_a_b, f"{table} fuit vers l'autre organisation"
        assert sans_perimetre[table] == 0, f"{table} visible sans périmètre"

    # C) Depuis A, déplacer une ligne vers B est refusé, sur chaque table peuplée.
    refus = {}
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])
        for table in sorted(peuplees):
            col = _colonne(table)
            try:
                cur.execute(f"UPDATE {table} SET {col} = %s", [autre.id])  # noqa: S608
            except Exception as erreur:  # noqa: BLE001 : le motif exact varie selon la table
                refus[table] = str(erreur).splitlines()[0]
            else:
                refus[table] = None
    acceptes = sorted(t for t, motif in refus.items() if motif is None)
    assert not acceptes, f"Déplacement vers une autre organisation ACCEPTÉ : {acceptes}"
    with connexion_proprietaire() as admin:  # vérité hors RLS : rien n'a changé d'organisation
        for table in peuplees:
            col = _colonne(table)
            chez_b = admin.execute(
                f"SELECT count(*) FROM {table} WHERE {col} = %s",
                [autre.id],  # noqa: S608
            ).fetchone()[0]
            attendu_b = 1 if table == "organisations_organisation" else 0
            assert chez_b == attendu_b, f"{table} : {chez_b} ligne(s) chez B"
            assert (
                admin.execute(
                    f"SELECT count(*) FROM {table} WHERE {col} = %s",
                    [organisation.id],  # noqa: S608
                ).fetchone()[0]
                == possede[table]
            )
