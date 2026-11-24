# Dictionnaire de données

Généré depuis les modèles (`python manage.py generer_dictionnaire`). Ne le modifiez pas
à la main : un test échoue si ce fichier n'est plus celui que les modèles produisent.

102 tables. « Isolée » : la table porte `org_id` et sa politique de
sécurité par ligne (RLS). Les contraintes nommées sont contrôlées par la base.

## Index

- [`auth_group`](#auth_group) — auth.Group
- [`auth_permission`](#auth_permission) — auth.Permission
- [`avances_avance`](#avances_avance) — avances.Avance
- [`avances_delaiavance`](#avances_delaiavance) — avances.DelaiAvance
- [`avances_justificationavance`](#avances_justificationavance) — avances.JustificationAvance
- [`budget_controlebudgetaire`](#budget_controlebudgetaire) — budget.ControleBudgetaire
- [`budget_engagement`](#budget_engagement) — budget.Engagement
- [`budget_lignebudget`](#budget_lignebudget) — budget.LigneBudget
- [`budget_soldebudgetaire`](#budget_soldebudgetaire) — budget.SoldeBudgetaire
- [`budget_versionbudget`](#budget_versionbudget) — budget.VersionBudget
- [`comptabilite_anouveau`](#comptabilite_anouveau) — comptabilite.ANouveau
- [`comptabilite_compteur`](#comptabilite_compteur) — comptabilite.Compteur
- [`comptabilite_ecriture`](#comptabilite_ecriture) — comptabilite.Ecriture
- [`comptabilite_journal`](#comptabilite_journal) — comptabilite.Journal
- [`comptabilite_lettrage`](#comptabilite_lettrage) — comptabilite.Lettrage
- [`comptabilite_ligneecriture`](#comptabilite_ligneecriture) — comptabilite.LigneEcriture
- [`comptabilite_ligneschema`](#comptabilite_ligneschema) — comptabilite.LigneSchema
- [`comptabilite_piecejustificative`](#comptabilite_piecejustificative) — comptabilite.PieceJustificative
- [`comptabilite_schemaecriture`](#comptabilite_schemaecriture) — comptabilite.SchemaEcriture
- [`controles_circuit`](#controles_circuit) — controles.Circuit
- [`controles_controle`](#controles_controle) — controles.Controle
- [`controles_decisioncontrole`](#controles_decisioncontrole) — controles.DecisionControle
- [`controles_decisionetape`](#controles_decisionetape) — controles.DecisionEtape
- [`controles_demandevalidation`](#controles_demandevalidation) — controles.DemandeValidation
- [`controles_derogation`](#controles_derogation) — controles.Derogation
- [`controles_etapecircuit`](#controles_etapecircuit) — controles.EtapeCircuit
- [`controles_evaluationcontrole`](#controles_evaluationcontrole) — controles.EvaluationControle
- [`controles_justification`](#controles_justification) — controles.Justification
- [`core_auditlog`](#core_auditlog) — core.AuditLog
- [`decaissements_demanderetrait`](#decaissements_demanderetrait) — decaissements.DemandeRetrait
- [`decaissements_lignedemande`](#decaissements_lignedemande) — decaissements.LigneDemande
- [`decaissements_miseaecart`](#decaissements_miseaecart) — decaissements.MiseAEcart
- [`decaissements_soldeaccord`](#decaissements_soldeaccord) — decaissements.SoldeAccord
- [`decaissements_soldecategorie`](#decaissements_soldecategorie) — decaissements.SoldeCategorie
- [`django_content_type`](#django_content_type) — contenttypes.ContentType
- [`django_session`](#django_session) — sessions.Session
- [`exercices_exercice`](#exercices_exercice) — exercices.Exercice
- [`exercices_periode`](#exercices_periode) — exercices.Periode
- [`financements_accord`](#financements_accord) — financements.Accord
- [`financements_avenantaccord`](#financements_avenantaccord) — financements.AvenantAccord
- [`financements_bailleur`](#financements_bailleur) — financements.Bailleur
- [`financements_categorie`](#financements_categorie) — financements.Categorie
- [`financements_clecofinancement`](#financements_clecofinancement) — financements.CleCofinancement
- [`financements_comptebancaire`](#financements_comptebancaire) — financements.CompteBancaire
- [`financements_compteurdemande`](#financements_compteurdemande) — financements.CompteurDemande
- [`financements_partcle`](#financements_partcle) — financements.PartCle
- [`financements_versioncle`](#financements_versioncle) — financements.VersionCle
- [`habilitations_habilitation`](#habilitations_habilitation) — habilitations.Habilitation
- [`habilitations_role`](#habilitations_role) — habilitations.Role
- [`mapping_rule`](#mapping_rule) — mapping.RegleMapping
- [`mapping_table`](#mapping_table) — mapping.TableMapping
- [`marches_avenantcontrat`](#marches_avenantcontrat) — marches.AvenantContrat
- [`marches_avisnonobjection`](#marches_avisnonobjection) — marches.AvisNonObjection
- [`marches_contrat`](#marches_contrat) — marches.Contrat
- [`marches_decompte`](#marches_decompte) — marches.Decompte
- [`marches_etapeavancement`](#marches_etapeavancement) — marches.EtapeAvancement
- [`marches_garantie`](#marches_garantie) — marches.Garantie
- [`marches_lignepassation`](#marches_lignepassation) — marches.LignePassation
- [`marches_methodepassation`](#marches_methodepassation) — marches.MethodePassation
- [`marches_paiement`](#marches_paiement) — marches.Paiement
- [`marches_pieceavis`](#marches_pieceavis) — marches.PieceAvis
- [`marches_planpassation`](#marches_planpassation) — marches.PlanPassation
- [`niveau2_profils_elementprofil`](#niveau2_profils_elementprofil) — niveau2_profils.ElementProfil
- [`niveau2_profils_profilbailleur`](#niveau2_profils_profilbailleur) — niveau2_profils.ProfilBailleur
- [`niveau3_config_documentreference`](#niveau3_config_documentreference) — niveau3_config.DocumentReference
- [`niveau3_config_echeance`](#niveau3_config_echeance) — niveau3_config.Echeance
- [`niveau3_config_exigence`](#niveau3_config_exigence) — niveau3_config.Exigence
- [`niveau3_config_methodedecaissement`](#niveau3_config_methodedecaissement) — niveau3_config.MethodeDecaissement
- [`niveau3_config_profildecaissement`](#niveau3_config_profildecaissement) — niveau3_config.ProfilDecaissement
- [`niveau3_config_rattachementexigence`](#niveau3_config_rattachementexigence) — niveau3_config.RattachementExigence
- [`niveau3_config_reallocation`](#niveau3_config_reallocation) — niveau3_config.Reallocation
- [`niveau3_config_reglecomptedesigne`](#niveau3_config_reglecomptedesigne) — niveau3_config.RegleCompteDesigne
- [`niveau3_config_reglefinancementcategorie`](#niveau3_config_reglefinancementcategorie) — niveau3_config.RegleFinancementCategorie
- [`organisations_organisation`](#organisations_organisation) — organisations.Organisation
- [`organisations_projet`](#organisations_projet) — organisations.Projet
- [`organisations_utilisateur`](#organisations_utilisateur) — organisations.Utilisateur
- [`publication_accesauditeur`](#publication_accesauditeur) — publication.AccesAuditeur
- [`publication_fichierrapport`](#publication_fichierrapport) — publication.FichierRapport
- [`publication_motifrejet`](#publication_motifrejet) — publication.MotifRejet
- [`publication_rapportpublie`](#publication_rapportpublie) — publication.RapportPublie
- [`publication_simulationrevue`](#publication_simulationrevue) — publication.SimulationRevue
- [`publication_soumissionbailleur`](#publication_soumissionbailleur) — publication.SoumissionBailleur
- [`rapprochement_mouvementreleve`](#rapprochement_mouvementreleve) — rapprochement.MouvementReleve
- [`rapprochement_rapprochement`](#rapprochement_rapprochement) — rapprochement.Rapprochement
- [`referentiels_compte`](#referentiels_compte) — referentiels.Compte
- [`referentiels_correspondanceimport`](#referentiels_correspondanceimport) — referentiels.CorrespondanceImport
- [`referentiels_devise`](#referentiels_devise) — referentiels.Devise
- [`referentiels_parametredevises`](#referentiels_parametredevises) — referentiels.ParametreDevises
- [`referentiels_plandimension`](#referentiels_plandimension) — referentiels.PlanDimension
- [`referentiels_taux`](#referentiels_taux) — referentiels.Taux
- [`referentiels_tiers`](#referentiels_tiers) — referentiels.Tiers
- [`referentiels_valeurdimension`](#referentiels_valeurdimension) — referentiels.ValeurDimension
- [`reprise_lignebalanceorigine`](#reprise_lignebalanceorigine) — reprise.LigneBalanceOrigine
- [`reprise_piecereprise`](#reprise_piecereprise) — reprise.PieceReprise
- [`reprise_rapportreprise`](#reprise_rapportreprise) — reprise.RapportReprise
- [`reprise_reprise`](#reprise_reprise) — reprise.Reprise
- [`reversibilite_exportorganisation`](#reversibilite_exportorganisation) — reversibilite.ExportOrganisation
- [`tresorerie_appariementdemande`](#tresorerie_appariementdemande) — tresorerie.AppariementDemande
- [`tresorerie_justificationcomptespecial`](#tresorerie_justificationcomptespecial) — tresorerie.JustificationCompteSpecial
- [`tresorerie_justificationecart`](#tresorerie_justificationecart) — tresorerie.JustificationEcart
- [`tresorerie_previsiontresorerie`](#tresorerie_previsiontresorerie) — tresorerie.PrevisionTresorerie
- [`tresorerie_soldereleve`](#tresorerie_soldereleve) — tresorerie.SoldeReleve

## auth_group

Modèle `auth.Group`.

Groups are a generic way of categorizing users to apply permissions, or some other label, to those users. A user can belong to any number of groups.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | integer | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `name` | varchar(150) | non |  |  | — |

## auth_permission

Modèle `auth.Permission`.

The permissions system provides a way to assign permissions to specific users and groups of users.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | integer | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `name` | varchar(255) | non |  |  | — |
| `content_type_id` | integer | non |  | `django_content_type.id` | — |
| `codename` | varchar(100) | non |  |  | — |

## avances_avance

Modèle `avances.Avance` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `tiers_id` | uuid | non |  | `referentiels_tiers.id` | — |
| `reference` | varchar(60) | non |  |  | — |
| `libelle` | varchar(255) | non |  |  | — |
| `montant` | numeric(20, 4) | non |  |  | — |
| `date_versement` | date | non |  |  | — |
| `delai_jours` | integer | non |  |  | — |
| `ligne_ecriture_id` | uuid | oui |  |  | — |

Contraintes : `avance_delai_positif` (verification), `avance_montant_positif` (verification), `uq_avance_reference` (unicite)

## avances_delaiavance

Modèle `avances.DelaiAvance` — isolée par organisation.

Le délai de justification d'un projet, en jours. Versionné (`[valid_from, valid_to[`, sans chevauchement) : une avance garde le délai en vigueur le jour de son versement.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `jours` | integer | non |  |  | — |
| `version` | integer | non |  |  | Numéro de version : une configuration utilisée ne se modifie pas, on en crée une. |
| `valid_from` | date | non |  |  | Début de validité, inclus (intervalle semi-ouvert [valid_from, valid_to[). |
| `valid_to` | date | oui |  |  | Fin de validité, EXCLUE ; vide si la ligne est ouverte. |
| `motif` | text | non |  |  | — |

Contraintes : `delaiavance_dates_coherentes` (verification), `delaiavance_jours_positifs` (verification), `uq_delaiavance_version` (unicite)

## avances_justificationavance

Modèle `avances.JustificationAvance` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `avance_id` | uuid | non |  | `avances_avance.id` | — |
| `type` | varchar(13) | non |  |  | — |
| `montant` | numeric(20, 4) | non |  |  | — |
| `date_justification` | date | non |  |  | — |
| `reference` | varchar(100) | non |  |  | — |
| `ligne_ecriture_id` | uuid | oui |  |  | — |

Contraintes : `justificationavance_montant_positif` (verification), `justificationavance_type_ferme` (verification)

## budget_controlebudgetaire

Modèle `budget.ControleBudgetaire` — isolée par organisation.

Le mode de contrôle du disponible pour un axe d'un projet. Voir L4-T03.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `axe` | varchar(10) | non |  |  | — |
| `mode` | varchar(13) | non |  |  | — |
| `version` | integer | non |  |  | Numéro de version : une configuration utilisée ne se modifie pas, on en crée une. |
| `valid_from` | date | non |  |  | Début de validité, inclus (intervalle semi-ouvert [valid_from, valid_to[). |
| `valid_to` | date | oui |  |  | Fin de validité, EXCLUE ; vide si la ligne est ouverte. |
| `motif` | text | non |  |  | — |

Contraintes : `controlebudget_axe_ferme` (verification), `controlebudget_dates_coherentes` (verification), `controlebudget_mode_ferme` (verification), `uq_controlebudget_version` (unicite)

## budget_engagement

Modèle `budget.Engagement` — isolée par organisation.

Une réservation de budget : une dépense décidée, pas encore comptabilisée. Voir L4-T02.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `reference` | varchar(60) | non |  |  | — |
| `libelle` | varchar(255) | non |  |  | — |
| `annee` | smallint | non |  |  | — |
| `periode` | smallint | oui |  |  | — |
| `dim1_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `dim2_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `dim3_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `dim4_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `agreement_id` | uuid | oui |  |  | — |
| `category_id` | uuid | oui |  |  | — |
| `site_id` | uuid | oui |  |  | — |
| `ligne_passation_id` | uuid | oui |  | `marches_lignepassation.id` | — |
| `montant` | numeric(20, 4) | non |  |  | — |
| `apure` | numeric(20, 4) | non |  |  | — |
| `status` | varchar(6) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |

Contraintes : `engagement_apure_borne` (verification), `engagement_montant_positif` (verification), `engagement_periode_bornee` (verification), `engagement_solde_coherent` (verification), `engagement_statut_ferme` (verification), `uq_engagement_reference` (unicite)

## budget_lignebudget

Modèle `budget.LigneBudget` — isolée par organisation.

Un montant sur une combinaison d'axes, pour une année ou une période.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `version_id` | uuid | non |  | `budget_versionbudget.id` | — |
| `annee` | smallint | non |  |  | — |
| `periode` | smallint | oui |  |  | — |
| `dim1_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `dim2_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `dim3_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `dim4_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `agreement_id` | uuid | oui |  |  | — |
| `category_id` | uuid | oui |  |  | — |
| `site_id` | uuid | oui |  |  | — |
| `montant` | numeric(20, 4) | non |  |  | — |
| `devise_id` | varchar(3) | non |  | `referentiels_devise.code` | — |
| `taux_budget` | numeric(20, 10) | non |  |  | — |
| `montant_base` | numeric(20, 4) | non |  |  | — |

Contraintes : `lignebudget_annee_bornee` (verification), `lignebudget_montant_base_positif` (verification), `lignebudget_montant_positif` (verification), `lignebudget_periode_bornee` (verification), `lignebudget_taux_positif` (verification), `uq_lignebudget_combinaison` (unicite)

## budget_soldebudgetaire

Modèle `budget.SoldeBudgetaire` — isolée par organisation.

Le consommé et l'engagé d'une ligne de la version approuvée courante. Voir L4-T02.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `version_id` | uuid | non |  | `budget_versionbudget.id` | — |
| `ligne_id` | uuid | non |  | `budget_lignebudget.id` | — |
| `consomme` | numeric(20, 4) | non |  |  | — |
| `engage` | numeric(20, 4) | non |  |  | — |

## budget_versionbudget

Modèle `budget.VersionBudget` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `numero` | integer | non |  |  | — |
| `type` | varchar(12) | non |  |  | — |
| `status` | varchar(9) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |
| `parent_id` | uuid | oui |  | `budget_versionbudget.id` | — |
| `motif` | text | non |  |  | — |
| `approved_at` | timestamp with time zone | oui |  |  | — |
| `approved_by` | uuid | oui |  |  | — |
| `closed_at` | timestamp with time zone | oui |  |  | — |

Contraintes : `uq_versionbudget_numero` (unicite), `uq_versionbudget_un_brouillon` (unicite), `uq_versionbudget_un_initial` (unicite), `uq_versionbudget_une_courante` (unicite), `versionbudget_approbation_coherente` (verification), `versionbudget_motif_obligatoire` (verification), `versionbudget_parent_coherent` (verification), `versionbudget_statut_ferme` (verification), `versionbudget_type_ferme` (verification)

## comptabilite_anouveau

Modèle `comptabilite.ANouveau` — isolée par organisation.

Une génération des à-nouveaux d'un exercice. Voir L3-T08 (b).

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `exercice_source_id` | uuid | non |  | `exercices_exercice.id` | — |
| `exercice_cible_id` | uuid | non |  | `exercices_exercice.id` | — |
| `version` | integer | non |  |  | Numéro de version : une configuration utilisée ne se modifie pas, on en crée une. |
| `status` | varchar(8) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |
| `ecriture_id` | uuid | non |  | `comptabilite_ecriture.id` | — |
| `ecriture_annulation_id` | uuid | oui |  | `comptabilite_ecriture.id` | — |
| `compte_resultat` | varchar(20) | non |  |  | — |
| `resultat` | numeric(20, 4) | non |  |  | — |
| `empreinte` | varchar(64) | non |  |  | — |
| `genere_at` | timestamp with time zone | non |  |  | — |
| `genere_by` | uuid | oui |  |  | — |

Contraintes : `anouveau_annulation_coherente` (verification), `anouveau_statut_ferme` (verification), `anouveau_version_positive` (verification), `uq_anouveau_un_actif` (unicite), `uq_anouveau_version` (unicite)

## comptabilite_compteur

Modèle `comptabilite.Compteur` — isolée par organisation.

Dernier numéro attribué, par journal et par exercice. Voir L3-T04.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `journal_id` | uuid | non |  | `comptabilite_journal.id` | — |
| `exercice_id` | uuid | non |  | `exercices_exercice.id` | — |
| `dernier` | integer | non |  |  | — |

Contraintes : `compteur_positif` (verification), `uq_compteur_journal_exercice` (unicite)

## comptabilite_ecriture

Modèle `comptabilite.Ecriture` — isolée par organisation.

Une pièce comptable. Le numéro n'est attribué qu'à la comptabilisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `exercice_id` | uuid | non |  | `exercices_exercice.id` | — |
| `periode_id` | uuid | non |  | `exercices_periode.id` | — |
| `journal_id` | uuid | non |  | `comptabilite_journal.id` | — |
| `number` | varchar(40) | oui |  |  | — |
| `accounting_date` | date | non |  |  | — |
| `document_date` | date | oui |  |  | — |
| `document_ref` | varchar(100) | non |  |  | — |
| `label` | varchar(255) | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `status` | varchar(9) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |
| `currency_id` | varchar(3) | non |  | `referentiels_devise.code` | — |
| `fx_rate` | numeric(20, 10) | non |  |  | — |
| `origin` | varchar(8) | non |  |  | — |
| `origin_module` | varchar(32) | oui |  |  | — |
| `origin_ref` | uuid | oui |  |  | — |
| `idempotency_key` | varchar(100) | oui |  |  | — |
| `posted_at` | timestamp with time zone | oui |  |  | — |
| `posted_by` | uuid | oui |  |  | — |
| `reverses_id` | uuid | oui |  | `comptabilite_ecriture.id` | — |
| `schema_id` | uuid | oui |  | `comptabilite_schemaecriture.id` | — |

Contraintes : `ecriture_comptabilisee_numerotee` (verification), `ecriture_contrepassation_coherente` (verification), `ecriture_ne_se_contrepasse_pas` (verification), `ecriture_numero_a_la_comptabilisation` (verification), `ecriture_origine_fermee` (verification), `ecriture_statut_ferme` (verification), `uq_ecriture_idempotence` (unicite), `uq_ecriture_numero` (unicite), `uq_ecriture_une_contrepassation` (unicite)

## comptabilite_journal

Modèle `comptabilite.Journal` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `code` | varchar(20) | non |  |  | — |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `actif` | boolean | non |  |  | — |

Contraintes : `uq_journal_code` (unicite)

## comptabilite_lettrage

Modèle `comptabilite.Lettrage` — isolée par organisation.

Un groupe de lignes de solde nul sur un même compte, un même tiers, un même projet.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `code` | varchar(10) | non |  |  | — |
| `account_id` | uuid | non |  | `referentiels_compte.id` | — |
| `partner_id` | uuid | non |  | `referentiels_tiers.id` | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `status` | varchar(6) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |
| `lettre_at` | timestamp with time zone | non |  |  | — |
| `lettre_by` | uuid | oui |  |  | — |
| `annule_at` | timestamp with time zone | oui |  |  | — |
| `annule_by` | uuid | oui |  |  | — |
| `motif_annulation` | text | oui |  |  | — |

Contraintes : `lettrage_annulation_coherente` (verification), `lettrage_statut_ferme` (verification), `uq_lettrage_code` (unicite)

## comptabilite_ligneecriture

Modèle `comptabilite.LigneEcriture` — isolée par organisation.

Une ligne d'écriture : un compte, un sens, des axes d'analyse.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `entry_id` | uuid | non |  | `comptabilite_ecriture.id` | — |
| `line_no` | smallint | non |  |  | — |
| `account_id` | uuid | non |  | `referentiels_compte.id` | — |
| `partner_id` | uuid | oui |  | `referentiels_tiers.id` | — |
| `dim1_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `dim2_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `dim3_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `dim4_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `aux1_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `aux2_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `aux3_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `aux4_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `site_id` | uuid | oui |  |  | — |
| `agreement_id` | uuid | oui |  |  | — |
| `category_id` | uuid | oui |  |  | — |
| `contract_id` | uuid | oui |  |  | — |
| `bank_account_id` | uuid | oui |  |  | — |
| `cofunding_key_version_id` | uuid | oui |  |  | — |
| `debit` | numeric(20, 4) | non |  |  | — |
| `credit` | numeric(20, 4) | non |  |  | — |
| `currency_id` | varchar(3) | non |  | `referentiels_devise.code` | — |
| `fx_rate` | numeric(20, 10) | non |  |  | — |
| `debit_cur` | numeric(20, 4) | non |  |  | — |
| `credit_cur` | numeric(20, 4) | non |  |  | — |
| `reconciliation_id` | uuid | oui |  |  | — |
| `bank_match_id` | uuid | oui |  |  | — |
| `label` | varchar(255) | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |

Contraintes : `ligne_montants_positifs` (verification), `ligne_numero_positif` (verification), `ligne_un_seul_sens` (verification), `uq_ligne_numero` (unicite)

## comptabilite_ligneschema

Modèle `comptabilite.LigneSchema` — isolée par organisation.

Une ligne de schéma : un compte, un sens, une règle de calcul d'un ensemble fermé.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `schema_id` | uuid | non |  | `comptabilite_schemaecriture.id` | — |
| `rang` | smallint | non |  |  | — |
| `compte_id` | uuid | non |  | `referentiels_compte.id` | — |
| `sens` | varchar(6) | oui |  |  | — |
| `regle` | varchar(16) | non |  |  | — |
| `taux` | numeric(9, 6) | oui |  |  | — |
| `axes` | jsonb | non |  |  | — |

Contraintes : `ligneschema_forme` (verification), `ligneschema_rang_positif` (verification), `ligneschema_regle_fermee` (verification), `uq_ligneschema_rang` (unicite), `uq_ligneschema_une_contrepartie` (unicite)

## comptabilite_piecejustificative

Modèle `comptabilite.PieceJustificative` — isolée par organisation.

Un fichier scanné qui justifie une écriture. Voir L7-T03.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `ecriture_id` | uuid | non |  | `comptabilite_ecriture.id` | — |
| `type_piece` | varchar(24) | non |  |  | — |
| `nom` | varchar(255) | non |  |  | — |
| `file_ref` | varchar(512) | non |  |  | — |
| `sha256` | bytea | non |  |  | Empreinte SHA-256 du contenu : preuve d'intégrité. |
| `taille` | integer | non |  |  | — |
| `ajoutee_par` | uuid | non |  |  | — |

Contraintes : `piece_type_ferme` (verification), `uq_piece_par_ecriture` (unicite)

## comptabilite_schemaecriture

Modèle `comptabilite.SchemaEcriture` — isolée par organisation.

Une pièce type (achat avec TVA, recette…), versionnée comme toute configuration (B.6).

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `code` | varchar(32) | non |  |  | — |
| `version` | integer | non |  |  | Numéro de version : une configuration utilisée ne se modifie pas, on en crée une. |
| `valid_from` | date | non |  |  | Début de validité, inclus (intervalle semi-ouvert [valid_from, valid_to[). |
| `valid_to` | date | oui |  |  | Fin de validité, EXCLUE ; vide si la ligne est ouverte. |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `journal_id` | uuid | oui |  | `comptabilite_journal.id` | — |

Contraintes : `schema_dates_coherentes` (verification), `uq_schema_version` (unicite)

## controles_circuit

Modèle `controles.Circuit` — isolée par organisation.

Le circuit de validation d'un type d'objet, de 1 à 5 étapes. Voir L6-T02b.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `objet_type` | varchar(40) | non |  |  | — |
| `version` | integer | non |  |  | Numéro de version : une configuration utilisée ne se modifie pas, on en crée une. |
| `valid_from` | date | non |  |  | Début de validité, inclus (intervalle semi-ouvert [valid_from, valid_to[). |
| `valid_to` | date | oui |  |  | Fin de validité, EXCLUE ; vide si la ligne est ouverte. |

Contraintes : `uq_circuit_version` (unicite)

## controles_controle

Modèle `controles.Controle` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `code` | varchar(64) | non |  |  | — |
| `version` | integer | non |  |  | Numéro de version : une configuration utilisée ne se modifie pas, on en crée une. |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `type_regle` | varchar(24) | non |  |  | — |
| `severity` | varchar(14) | non |  |  | — |
| `mode` | varchar(12) | non |  |  | — |
| `expression` | jsonb | oui |  |  | — |
| `applicable_si` | jsonb | oui |  |  | — |
| `parametres` | jsonb | non |  |  | — |
| `action_corrective` | jsonb | non |  |  | — |
| `valid_from` | date | non |  |  | Début de validité, inclus (intervalle semi-ouvert [valid_from, valid_to[). |
| `valid_to` | date | oui |  |  | Fin de validité, EXCLUE ; vide si la ligne est ouverte. |
| `status` | varchar(12) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |
| `validated_by` | uuid | oui |  |  | — |
| `validated_at` | timestamp with time zone | oui |  |  | — |

Contraintes : `controle_dates_coherentes` (verification), `controle_expression_selon_mode` (verification), `controle_mode_ferme` (verification), `controle_severite_fermee` (verification), `controle_statut_ferme` (verification), `controle_type_regle_ferme` (verification), `controle_validation_obligatoire` (verification), `uq_controle_version` (unicite)

## controles_decisioncontrole

Modèle `controles.DecisionControle` — isolée par organisation.

La décision d'une personne sur un contrôle à vérifier. En ajout seul.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `evaluation_id` | uuid | non |  | `controles_evaluationcontrole.id` | — |
| `decision` | varchar(14) | non |  |  | — |
| `motif` | text | non |  |  | — |
| `decided_by` | uuid | non |  |  | — |
| `decided_at` | timestamp with time zone | non |  |  | — |

Contraintes : `decision_controle_fermee` (verification), `decision_controle_motivee` (verification)

## controles_decisionetape

Modèle `controles.DecisionEtape` — isolée par organisation.

Une signature nominative sur une étape. En ajout seul ; le rejet est motivé.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `demande_id` | uuid | non |  | `controles_demandevalidation.id` | — |
| `rang` | smallint | non |  |  | — |
| `approuvee` | boolean | non |  |  | — |
| `motif` | text | non |  |  | — |
| `decided_by` | uuid | non |  |  | — |
| `decided_by_nom` | varchar(150) | non |  |  | — |
| `decided_at` | timestamp with time zone | non |  |  | — |

Contraintes : `rejet_motive` (verification), `uq_decision_par_etape` (unicite), `uq_decision_par_personne` (unicite)

## controles_demandevalidation

Modèle `controles.DemandeValidation` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `circuit_id` | uuid | non |  | `controles_circuit.id` | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `objet_type` | varchar(40) | non |  |  | — |
| `objet_id` | uuid | non |  |  | — |
| `contexte` | jsonb | non |  |  | — |
| `date_effet` | date | non |  |  | — |
| `demandeur_id` | uuid | non |  |  | — |
| `statut` | varchar(10) | non |  |  | — |
| `rang_courant` | smallint | oui |  |  | — |

Contraintes : `demandevalidation_rang_selon_statut` (verification), `demandevalidation_statut_ferme` (verification), `uq_demande_en_cours_par_objet` (unicite)

## controles_derogation

Modèle `controles.Derogation` — isolée par organisation.

L'autorisation formelle de poursuivre malgré UN contrôle bloquant, sur UN objet. L6-T02.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `evaluation_id` | uuid | non |  | `controles_evaluationcontrole.id` | — |
| `controle_id` | uuid | non |  | `controles_controle.id` | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `objet_type` | varchar(40) | non |  |  | — |
| `objet_id` | uuid | oui |  |  | — |
| `motif` | text | non |  |  | — |
| `justificatif` | varchar(255) | non |  |  | — |
| `valide_du` | date | non |  |  | — |
| `valide_jusquau` | date | non |  |  | — |
| `statut` | varchar(10) | non |  |  | — |
| `demandeur_id` | uuid | non |  |  | — |
| `approbateur_id` | uuid | oui |  |  | — |
| `decidee_le` | timestamp with time zone | oui |  |  | — |
| `motif_decision` | text | non |  |  | — |

Contraintes : `derogation_approbateur_distinct` (verification), `derogation_decision_coherente` (verification), `derogation_justifiee` (verification), `derogation_motivee` (verification), `derogation_periode_non_vide` (verification), `derogation_statut_ferme` (verification)

## controles_etapecircuit

Modèle `controles.EtapeCircuit` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `circuit_id` | uuid | non |  | `controles_circuit.id` | — |
| `rang` | smallint | non |  |  | — |
| `nom` | jsonb | non |  |  | — |
| `operation` | varchar(24) | non |  |  | — |
| `condition` | jsonb | oui |  |  | — |
| `exige_controles_tranches` | boolean | non |  |  | — |

Contraintes : `etape_rang_de_1_a_5` (verification), `uq_etape_rang` (unicite)

## controles_evaluationcontrole

Modèle `controles.EvaluationControle` — isolée par organisation.

Une ligne du journal : en ajout seul, jamais modifiée ni supprimée.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `controle_id` | uuid | non |  | `controles_controle.id` | — |
| `controle_version` | integer | non |  |  | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `objet_type` | varchar(40) | non |  |  | — |
| `objet_id` | uuid | oui |  |  | — |
| `resultat` | varchar(14) | non |  |  | — |
| `severity` | varchar(14) | non |  |  | — |
| `valeur_constatee` | text | non |  |  | — |
| `valeur_attendue` | text | non |  |  | — |
| `message` | jsonb | non |  |  | — |
| `action_corrective` | jsonb | non |  |  | — |
| `profile_version_id` | uuid | oui |  |  | — |
| `exigence_id` | uuid | oui |  |  | — |
| `exigence_code` | varchar(64) | non |  |  | — |
| `exigence_clause` | varchar(255) | non |  |  | — |
| `evaluee_le` | date | non |  |  | — |
| `declencheur_type` | varchar(12) | non |  |  | — |
| `declencheur_id` | uuid | oui |  |  | — |
| `declencheur_nom` | varchar(64) | non |  |  | — |

Contraintes : `evaluation_declencheur_coherent` (verification), `evaluation_declencheur_ferme` (verification), `evaluation_resultat_ferme` (verification), `evaluation_severite_fermee` (verification)

## controles_justification

Modèle `controles.Justification` — isolée par organisation.

Ce qu'une personne dit d'une anomalie : elle EXPLIQUE, elle n'autorise rien. Ajout seul.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `evaluation_id` | uuid | non |  | `controles_evaluationcontrole.id` | — |
| `texte` | text | non |  |  | — |
| `auteur_id` | uuid | non |  |  | — |
| `auteur_nom` | varchar(150) | non |  |  | — |

Contraintes : `justification_texte_obligatoire` (verification)

## core_auditlog

Modèle `core.AuditLog` — isolée par organisation.

Journal d'audit en ajout seul, chaîné par empreinte.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | bigint | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `occurred_at` | timestamp with time zone | non |  |  | — |
| `actor_id` | uuid | oui |  |  | — |
| `actor_ip` | inet | oui |  |  | — |
| `action` | varchar(32) | non |  |  | — |
| `object_type` | varchar(64) | non |  |  | — |
| `object_id` | uuid | oui |  |  | — |
| `project_id` | uuid | oui |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `before` | jsonb | oui |  |  | — |
| `after` | jsonb | oui |  |  | — |
| `prev_hash` | bytea | oui |  |  | — |
| `hash` | bytea | non |  |  | — |

## decaissements_demanderetrait

Modèle `decaissements.DemandeRetrait` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `accord_id` | uuid | non |  | `financements_accord.id` | — |
| `numero` | varchar(80) | non |  |  | — |
| `type` | varchar(20) | non |  |  | — |
| `status` | varchar(10) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |
| `periode_debut` | date | non |  |  | — |
| `periode_fin` | date | non |  |  | — |
| `montant_total` | numeric(20, 4) | non |  |  | — |
| `profil_version_id` | uuid | oui |  | `niveau3_config_profildecaissement.id` | — |
| `pieces_exigees` | jsonb | non |  |  | — |
| `pieces_fournies` | jsonb | non |  |  | — |
| `reprise_de_id` | uuid | oui |  | `decaissements_demanderetrait.id` | — |
| `motif_rejet` | text | non |  |  | — |
| `motif_contestation` | text | non |  |  | — |
| `soumise_le` | timestamp with time zone | oui |  |  | — |
| `soumise_par` | uuid | oui |  |  | — |
| `cle_idempotence` | varchar(100) | oui |  |  | — |
| `etat_certifie` | jsonb | oui |  |  | — |
| `empreinte_etat` | varchar(64) | non |  |  | — |
| `decidee_le` | timestamp with time zone | oui |  |  | — |
| `decidee_par` | uuid | oui |  |  | — |

Contraintes : `demande_etat_certifie_des_la_soumission` (verification), `demande_montant_positif` (verification), `demande_motif_de_contestation_obligatoire` (verification), `demande_motif_de_rejet_obligatoire` (verification), `demande_pas_sa_propre_reprise` (verification), `demande_periode_coherente` (verification), `demande_statut_ferme` (verification), `demande_type_ferme` (verification), `uq_demande_cle_idempotence` (unicite), `uq_demande_numero` (unicite)

## decaissements_lignedemande

Modèle `decaissements.LigneDemande` — isolée par organisation.

Une dépense justifiée par une demande. Les valeurs sont celles du grand livre à la préparation : la base les vérifie et les recopie, l'appelant ne les dicte pas.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `demande_id` | uuid | non |  | `decaissements_demanderetrait.id` | — |
| `ligne_ecriture_id` | uuid | non |  |  | — |
| `categorie_id` | uuid | non |  | `financements_categorie.id` | — |
| `montant` | numeric(20, 4) | non |  |  | — |
| `montant_a_retirer` | numeric(20, 4) | non |  |  | — |
| `regle_financement_id` | uuid | oui |  | `niveau3_config_reglefinancementcategorie.id` | — |
| `profil_version_id` | uuid | oui |  | `niveau3_config_profildecaissement.id` | — |
| `taux_applique` | numeric(9, 6) | oui |  |  | — |
| `piece` | varchar(100) | non |  |  | — |
| `date_piece` | date | non |  |  | — |
| `contrat_id` | uuid | oui |  | `marches_contrat.id` | — |
| `etat` | varchar(6) | non |  |  | — |

Contraintes : `lignedemande_etat_ferme` (verification), `lignedemande_montant_positif` (verification), `lignedemande_regle_profil_taux_ensemble` (verification), `lignedemande_retrait_dans_la_depense` (verification), `uq_lignedemande_une_demande_en_cours` (unicite), `uq_lignedemande_une_fois` (unicite)

## decaissements_miseaecart

Modèle `decaissements.MiseAEcart` — isolée par organisation.

Une dépense écartée d'une demande, avec son motif : ce qu'on n'a PAS demandé se justifie.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `demande_id` | uuid | non |  | `decaissements_demanderetrait.id` | — |
| `ligne_ecriture_id` | uuid | non |  |  | — |
| `motif` | text | non |  |  | — |

Contraintes : `ecart_motif_obligatoire` (verification), `uq_ecart_une_fois` (unicite)

## decaissements_soldeaccord

Modèle `decaissements.SoldeAccord` — isolée par organisation.

Le montant des demandes en cours sur un accord, face à son montant courant.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `accord_id` | uuid | non |  | `financements_accord.id` | — |
| `utilise` | numeric(20, 4) | non |  |  | — |

Contraintes : `soldeaccord_positif` (verification)

## decaissements_soldecategorie

Modèle `decaissements.SoldeCategorie` — isolée par organisation.

Le montant des demandes en cours sur une catégorie (et ses sous-catégories). Maintenu par la base ; verrouillé (`FOR UPDATE`) par toute soumission, ce qui sérialise les demandes qui se disputent le même disponible.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `categorie_id` | uuid | non |  | `financements_categorie.id` | — |
| `utilise` | numeric(20, 4) | non |  |  | — |

Contraintes : `soldecategorie_positif` (verification)

## django_content_type

Modèle `contenttypes.ContentType`.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | integer | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `app_label` | varchar(100) | non |  |  | — |
| `model` | varchar(100) | non |  |  | — |

## django_session

Modèle `sessions.Session`.

Django provides full support for anonymous sessions. The session framework lets you store and retrieve arbitrary data on a per-site-visitor basis. It stores data on the server side and abstracts the sending and receiving of cookies. Cookies contain a session ID -- not the data itself.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `session_key` | varchar(40) | non | PK |  | — |
| `session_data` | text | non |  |  | — |
| `expire_date` | timestamp with time zone | non |  |  | — |

## exercices_exercice

Modèle `exercices.Exercice` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `annee` | integer | non |  |  | — |
| `date_debut` | date | non |  |  | — |
| `date_fin` | date | non |  |  | — |
| `status` | varchar(8) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |

Contraintes : `exercice_dates_coherentes` (verification), `exercice_statut_ferme` (verification), `uq_exercice_annee` (unicite)

## exercices_periode

Modèle `exercices.Periode` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `exercice_id` | uuid | non |  | `exercices_exercice.id` | — |
| `numero` | smallint | non |  |  | — |
| `date_debut` | date | non |  |  | — |
| `date_fin` | date | non |  |  | — |
| `status` | varchar(11) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |

Contraintes : `periode_dates_coherentes` (verification), `periode_numero_1_12` (verification), `periode_statut_ferme` (verification), `uq_periode_numero` (unicite)

## financements_accord

Modèle `financements.Accord` — isolée par organisation.

Un accord de financement. Le montant COURANT est celui du dernier avenant, sinon le montant initial : l'accord lui-même ne change pas de montant (voir `montant_courant`).

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `bailleur_id` | uuid | non |  | `financements_bailleur.id` | — |
| `numero` | varchar(60) | non |  |  | — |
| `libelle` | varchar(255) | non |  |  | — |
| `nature` | varchar(12) | non |  |  | — |
| `status` | varchar(9) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |
| `devise_id` | varchar(3) | non |  | `referentiels_devise.code` | — |
| `montant_initial` | numeric(20, 4) | non |  |  | — |
| `date_effet` | date | oui |  |  | — |
| `date_fin_eligibilite` | date | oui |  |  | — |
| `date_cloture` | date | oui |  |  | — |
| `date_limite_decaissement` | date | oui |  |  | — |
| `format_numero_demande` | varchar(8) | non |  |  | — |
| `suffixe_agence` | varchar(3) | non |  |  | — |

Contraintes : `accord_dates_0` (verification), `accord_dates_1` (verification), `accord_dates_2` (verification), `accord_dates_3` (verification), `accord_dates_4` (verification), `accord_dates_5` (verification), `accord_format_numero_coherent` (verification), `accord_montant_positif` (verification), `accord_nature_fermee` (verification), `accord_statut_ferme` (verification), `uq_accord_numero` (unicite)

## financements_avenantaccord

Modèle `financements.AvenantAccord` — isolée par organisation.

Un avenant : il PORTE la nouvelle valeur, il ne modifie jamais l'accord en place.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `accord_id` | uuid | non |  | `financements_accord.id` | — |
| `reference` | varchar(60) | non |  |  | — |
| `date_avenant` | date | non |  |  | — |
| `document_id` | uuid | non |  | `niveau3_config_documentreference.id` | — |
| `montant_revise` | numeric(20, 4) | non |  |  | — |
| `motif` | text | non |  |  | — |
| `profile_version_id` | uuid | oui |  |  | — |

Contraintes : `avenant_montant_positif` (verification), `uq_avenant_reference` (unicite)

## financements_bailleur

Modèle `financements.Bailleur` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `code` | varchar(32) | non |  |  | — |
| `nom` | varchar(255) | non |  |  | — |
| `pays` | varchar(2) | non |  |  | — |
| `actif` | boolean | non |  |  | — |

Contraintes : `bailleur_pays_iso2` (verification), `uq_bailleur_code` (unicite)

## financements_categorie

Modèle `financements.Categorie` — isolée par organisation.

Catégorie de dépenses d'un accord, avec ses sous-catégories (`parent`).

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `accord_id` | uuid | non |  | `financements_accord.id` | — |
| `code` | varchar(32) | non |  |  | — |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `parent_id` | uuid | oui |  | `financements_categorie.id` | — |
| `plafond` | numeric(20, 4) | oui |  |  | — |
| `devise_id` | varchar(3) | non |  | `referentiels_devise.code` | — |

Contraintes : `categorie_pas_son_propre_parent` (verification), `categorie_plafond_positif` (verification), `uq_categorie_code` (unicite)

## financements_clecofinancement

Modèle `financements.CleCofinancement` — isolée par organisation.

Une clé de répartition d'une dépense entre accords (cofinancement). Voir L4-T05.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `code` | varchar(32) | non |  |  | — |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |

Contraintes : `uq_clecofinancement_code` (unicite)

## financements_comptebancaire

Modèle `financements.CompteBancaire` — isolée par organisation.

Un compte bancaire du projet. Le NUMÉRO COMPLET n'est lisible que d'une habilitation dédiée (`voir_numero_compte`) et chaque lecture est journalisée ; partout ailleurs, `numero_masque`.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `accord_id` | uuid | oui |  | `financements_accord.id` | — |
| `code` | varchar(32) | non |  |  | — |
| `libelle` | varchar(255) | non |  |  | — |
| `type` | varchar(12) | non |  |  | — |
| `devise_id` | varchar(3) | non |  | `referentiels_devise.code` | — |
| `banque` | varchar(120) | non |  |  | — |
| `numero` | varchar(64) | non |  |  | — |
| `plafond` | numeric(20, 4) | oui |  |  | — |
| `seuil_reapprovisionnement` | numeric(20, 4) | oui |  |  | — |
| `actif` | boolean | non |  |  | — |

Contraintes : `comptebancaire_plafond_positif` (verification), `comptebancaire_seuil_positif` (verification), `comptebancaire_seuil_sous_plafond` (verification), `comptebancaire_type_ferme` (verification), `uq_comptebancaire_code` (unicite), `uq_comptebancaire_numero` (unicite)

## financements_compteurdemande

Modèle `financements.CompteurDemande` — isolée par organisation.

La dernière séquence attribuée à une demande d'un accord au format `bad`. Lot 3-A.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `accord_id` | uuid | non |  | `financements_accord.id` | — |
| `derniere_sequence` | integer | non |  |  | — |

Contraintes : `compteur_demande_borne` (verification)

## financements_partcle

Modèle `financements.PartCle` — isolée par organisation.

La part d'un accord dans une version de clé. Les parts d'une version somment EXACTEMENT à 1 (vérifié par la base au COMMIT) : la dernière est calculée par différence, jamais par division.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `version_id` | uuid | non |  | `financements_versioncle.id` | — |
| `accord_id` | uuid | non |  | `financements_accord.id` | — |
| `share` | numeric(12, 10) | non |  |  | — |

Contraintes : `partcle_part_dans_0_1` (verification), `uq_partcle_accord` (unicite)

## financements_versioncle

Modèle `financements.VersionCle` — isolée par organisation.

Une version d'une clé : validité `[valid_from, valid_to[`, sans chevauchement pour une clé.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `cle_id` | uuid | non |  | `financements_clecofinancement.id` | — |
| `version` | integer | non |  |  | Numéro de version : une configuration utilisée ne se modifie pas, on en crée une. |
| `valid_from` | date | non |  |  | Début de validité, inclus (intervalle semi-ouvert [valid_from, valid_to[). |
| `valid_to` | date | oui |  |  | Fin de validité, EXCLUE ; vide si la ligne est ouverte. |
| `rounding_residual_agreement_id` | uuid | non |  | `financements_accord.id` | — |
| `motif` | text | non |  |  | — |

Contraintes : `uq_versioncle_version` (unicite), `versioncle_dates_coherentes` (verification)

## habilitations_habilitation

Modèle `habilitations.Habilitation` — isolée par organisation.

Un utilisateur tient un rôle sur un projet, éventuellement limité à un site.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `user_id` | uuid | non |  |  | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `site` | varchar(20) | oui |  |  | — |
| `role_id` | uuid | non |  | `habilitations_role.id` | — |

Contraintes : `habilitation_site_non_vide` (verification), `uq_habilitation` (unicite)

## habilitations_role

Modèle `habilitations.Role` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `code` | varchar(32) | non |  |  | — |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `operations` | jsonb | non |  |  | — |

Contraintes : `uq_role_code` (unicite)

## mapping_rule

Modèle `mapping.RegleMapping` — isolée par organisation.

Première règle prioritaire dont tous les critères correspondent.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `table_id` | uuid | non |  | `mapping_table.id` | — |
| `priority` | integer | non |  |  | — |
| `match` | jsonb | non |  |  | — |
| `target_code` | varchar(64) | non |  |  | — |
| `condition_expr` | text | oui |  |  | — |

Contraintes : `uq_mapping_regle_priorite` (unicite)

## mapping_table

Modèle `mapping.TableMapping` — isolée par organisation.

Une version d'une nomenclature bailleur pour un projet.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | oui |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `donor_profile_id` | uuid | non |  |  | — |
| `code` | varchar(64) | non |  |  | — |
| `version` | integer | non |  |  | Numéro de version : une configuration utilisée ne se modifie pas, on en crée une. |
| `valid_from` | date | non |  |  | Début de validité, inclus (intervalle semi-ouvert [valid_from, valid_to[). |
| `valid_to` | date | oui |  |  | Fin de validité, EXCLUE ; vide si la ligne est ouverte. |
| `status` | varchar(16) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |
| `validated_by` | uuid | oui |  |  | — |
| `validated_at` | timestamp with time zone | oui |  |  | — |

Contraintes : `mapping_dates_coherentes` (verification), `mapping_validation_obligatoire` (verification), `uq_mapping_version` (unicite)

## marches_avenantcontrat

Modèle `marches.AvenantContrat` — isolée par organisation.

Un avenant : il PORTE la nouvelle valeur (montant total, date de fin), en ajout seul.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `contrat_id` | uuid | non |  | `marches_contrat.id` | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `numero` | smallint | non |  |  | — |
| `date_effet` | date | non |  |  | — |
| `montant` | numeric(20, 4) | non |  |  | — |
| `date_fin` | date | non |  |  | — |
| `motif` | text | non |  |  | — |
| `avis_id` | uuid | oui |  | `marches_avisnonobjection.id` | — |
| `cree_par` | uuid | non |  |  | — |

Contraintes : `avenant_numero_positif` (verification), `avenantcontrat_montant_positif` (verification), `avenantcontrat_motive` (verification), `uq_avenant_numero` (unicite)

## marches_avisnonobjection

Modèle `marches.AvisNonObjection` — isolée par organisation.

Une demande d'avis de non-objection sur une ligne du plan, et sa réponse. Voir L9-T02.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `ligne_id` | uuid | non |  | `marches_lignepassation.id` | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `objet` | varchar(12) | non |  |  | — |
| `statut` | varchar(8) | non |  |  | — |
| `date_demande` | date | non |  |  | — |
| `date_decision` | date | oui |  |  | — |
| `reference_bailleur` | varchar(120) | non |  |  | — |
| `motif` | text | non |  |  | — |
| `demande_par` | uuid | non |  |  | — |
| `decide_par` | uuid | oui |  |  | — |

Contraintes : `avis_decision_coherente` (verification), `avis_objet_ferme` (verification), `avis_refus_motive` (verification), `avis_statut_ferme` (verification)

## marches_contrat

Modèle `marches.Contrat` — isolée par organisation.

Le contrat conclu pour une ligne du plan. Voir L9-T03.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `ligne_id` | uuid | non |  | `marches_lignepassation.id` | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `reference` | varchar(60) | non |  |  | — |
| `tiers_id` | uuid | non |  | `referentiels_tiers.id` | — |
| `objet` | varchar(255) | non |  |  | — |
| `montant_initial` | numeric(20, 4) | non |  |  | — |
| `devise` | varchar(3) | non |  |  | — |
| `date_signature` | date | non |  |  | — |
| `date_debut` | date | non |  |  | — |
| `date_fin_initiale` | date | non |  |  | — |

Contraintes : `contrat_montant_positif` (verification), `contrat_periode_coherente` (verification), `uq_contrat_reference` (unicite)

## marches_decompte

Modèle `marches.Decompte` — isolée par organisation.

Un décompte (situation) présenté sur un contrat. Voir L9-T04.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `contrat_id` | uuid | non |  | `marches_contrat.id` | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `numero` | smallint | non |  |  | — |
| `date_decompte` | date | non |  |  | — |
| `montant_brut` | numeric(20, 4) | non |  |  | — |
| `retenue` | numeric(20, 4) | non |  |  | — |
| `avancement_physique` | numeric(6, 2) | non |  |  | — |
| `facture_reference` | varchar(60) | non |  |  | — |
| `facture_date` | date | oui |  |  | — |
| `soumis_par` | uuid | non |  |  | — |
| `statut` | varchar(8) | non |  |  | — |
| `decide_par` | uuid | oui |  |  | — |
| `date_decision` | date | oui |  |  | — |
| `engagement_id` | uuid | oui |  | `budget_engagement.id` | — |
| `montant_apure` | numeric(20, 4) | oui |  |  | — |
| `motif_rejet` | text | non |  |  | — |

Contraintes : `decompte_avancement_borne` (verification), `decompte_brut_positif` (verification), `decompte_decision_coherente` (verification), `decompte_numero_positif` (verification), `decompte_retenue_bornee` (verification), `decompte_statut_ferme` (verification), `uq_decompte_numero` (unicite)

## marches_etapeavancement

Modèle `marches.EtapeAvancement` — isolée par organisation.

Une étape franchie par une ligne, avec sa date et son auteur. En ajout seul.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `ligne_id` | uuid | non |  | `marches_lignepassation.id` | — |
| `statut` | varchar(9) | non |  |  | — |
| `date_effet` | date | non |  |  | — |
| `note` | text | non |  |  | — |
| `par` | uuid | non |  |  | — |

Contraintes : `etape_annulation_motivee` (verification), `etape_statut_ferme` (verification), `uq_etape_une_fois` (unicite)

## marches_garantie

Modèle `marches.Garantie` — isolée par organisation.

Une garantie ou assurance attachée à un contrat, avec son échéance. Voir L9-T03.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `contrat_id` | uuid | non |  | `marches_contrat.id` | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `type_garantie` | varchar(16) | non |  |  | — |
| `emetteur` | varchar(255) | non |  |  | — |
| `reference` | varchar(60) | non |  |  | — |
| `montant` | numeric(20, 4) | non |  |  | — |
| `devise` | varchar(3) | non |  |  | — |
| `date_emission` | date | non |  |  | — |
| `date_echeance` | date | non |  |  | — |
| `statut` | varchar(8) | non |  |  | — |
| `date_cloture` | date | oui |  |  | — |
| `note_cloture` | text | non |  |  | — |

Contraintes : `garantie_appel_motive` (verification), `garantie_cloture_coherente` (verification), `garantie_montant_positif` (verification), `garantie_periode_coherente` (verification), `garantie_statut_ferme` (verification), `garantie_type_ferme` (verification), `uq_garantie_reference` (unicite)

## marches_lignepassation

Modèle `marches.LignePassation` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `plan_id` | uuid | non |  | `marches_planpassation.id` | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `reference` | varchar(40) | non |  |  | — |
| `libelle` | varchar(255) | non |  |  | — |
| `montant_prevu` | numeric(20, 4) | non |  |  | — |
| `devise` | varchar(3) | non |  |  | — |
| `methode_id` | uuid | non |  | `marches_methodepassation.id` | — |
| `non_objection_requise` | boolean | non |  |  | — |
| `categorie_id` | uuid | oui |  |  | — |
| `date_lancement_prevue` | date | non |  |  | — |
| `date_attribution_prevue` | date | non |  |  | — |
| `date_signature_prevue` | date | non |  |  | — |
| `statut` | varchar(9) | non |  |  | — |

Contraintes : `ligne_calendrier_ordonne` (verification), `ligne_montant_positif` (verification), `lignepassation_statut_ferme` (verification), `uq_lignepassation_reference` (unicite)

## marches_methodepassation

Modèle `marches.MethodePassation` — isolée par organisation.

Une méthode de passation, pour une plage de montants `[seuil_min, seuil_max[`, versionnée.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `code` | varchar(32) | non |  |  | — |
| `version` | integer | non |  |  | Numéro de version : une configuration utilisée ne se modifie pas, on en crée une. |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `devise` | varchar(3) | non |  |  | — |
| `seuil_min` | numeric(20, 4) | non |  |  | — |
| `seuil_max` | numeric(20, 4) | oui |  |  | — |
| `exige_non_objection` | boolean | non |  |  | — |
| `valid_from` | date | non |  |  | Début de validité, inclus (intervalle semi-ouvert [valid_from, valid_to[). |
| `valid_to` | date | oui |  |  | Fin de validité, EXCLUE ; vide si la ligne est ouverte. |

Contraintes : `methode_plage_non_vide` (verification), `methode_seuil_min_positif` (verification), `methode_validite_coherente` (verification), `uq_methodepassation_version` (unicite)

## marches_paiement

Modèle `marches.Paiement` — isolée par organisation.

Un paiement sur un décompte certifié, en ajout seul, avec son écriture au grand livre.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `decompte_id` | uuid | non |  | `marches_decompte.id` | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `reference` | varchar(60) | non |  |  | — |
| `date_paiement` | date | non |  |  | — |
| `montant` | numeric(20, 4) | non |  |  | — |
| `enregistre_par` | uuid | non |  |  | — |
| `ecriture_id` | uuid | oui |  | `comptabilite_ecriture.id` | — |

Contraintes : `paiement_montant_positif` (verification), `uq_paiement_reference` (unicite)

## marches_pieceavis

Modèle `marches.PieceAvis` — isolée par organisation.

Un fichier joint à un avis (demande envoyée, réponse reçue), en ajout seul.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `avis_id` | uuid | non |  | `marches_avisnonobjection.id` | — |
| `nature` | varchar(8) | non |  |  | — |
| `nom` | varchar(255) | non |  |  | — |
| `file_ref` | varchar(512) | non |  |  | — |
| `sha256` | bytea | non |  |  | Empreinte SHA-256 du contenu : preuve d'intégrité. |
| `taille` | integer | non |  |  | — |
| `ajoutee_par` | uuid | non |  |  | — |

Contraintes : `pieceavis_nature_fermee` (verification), `uq_pieceavis_par_avis` (unicite)

## marches_planpassation

Modèle `marches.PlanPassation` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `code` | varchar(40) | non |  |  | — |
| `nom` | varchar(200) | non |  |  | — |
| `date_debut` | date | non |  |  | — |
| `date_fin` | date | non |  |  | — |
| `cree_par` | uuid | non |  |  | — |

Contraintes : `plan_periode_coherente` (verification), `uq_planpassation_code` (unicite)

## niveau2_profils_elementprofil

Modèle `niveau2_profils.ElementProfil` — isolée par organisation.

Un élément de la bibliothèque. S'il porte une `exigence`, l'importer en propose une.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `profil_id` | uuid | non |  | `niveau2_profils_profilbailleur.id` | — |
| `kind` | varchar(24) | non |  |  | — |
| `code` | varchar(64) | non |  |  | — |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `contenu` | jsonb | non |  |  | — |
| `exigence` | jsonb | oui |  |  | — |
| `position` | integer | non |  |  | — |

Contraintes : `element_profil_type_ferme` (verification), `uq_element_profil` (unicite)

## niveau2_profils_profilbailleur

Modèle `niveau2_profils.ProfilBailleur` — isolée par organisation.

Un profil, versionné : une fois publié, il ne change plus (on en publie une version).

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `bailleur_id` | uuid | oui |  | `financements_bailleur.id` | — |
| `code` | varchar(64) | non |  |  | — |
| `version` | integer | non |  |  | Numéro de version : une configuration utilisée ne se modifie pas, on en crée une. |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `description` | jsonb | non |  |  | — |
| `status` | varchar(10) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |
| `published_by` | uuid | oui |  |  | — |
| `published_at` | timestamp with time zone | oui |  |  | — |

Contraintes : `profil_bailleur_publication_tracee` (verification), `profil_bailleur_statut_ferme` (verification), `uq_profil_bailleur_version` (unicite)

## niveau3_config_documentreference

Modèle `niveau3_config.DocumentReference` — isolée par organisation.

Document contractuel du projet. L'empreinte fige ce que la citation vise.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `kind` | varchar(32) | non |  |  | — |
| `title` | varchar(255) | non |  |  | — |
| `version` | varchar(32) | non |  |  | Numéro de version : une configuration utilisée ne se modifie pas, on en crée une. |
| `issued_on` | date | oui |  |  | — |
| `file_ref` | varchar(512) | non |  |  | — |
| `sha256` | bytea | non |  |  | Empreinte SHA-256 du contenu : preuve d'intégrité. |
| `superseded_by_id` | uuid | oui |  | `niveau3_config_documentreference.id` | — |

Contraintes : `documentreference_type_ferme` (verification)

## niveau3_config_echeance

Modèle `niveau3_config.Echeance` — isolée par organisation.

Une échéance de remise, générée depuis une exigence périodique ACTIVE. Voir L6-T06.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `exigence_id` | uuid | non |  | `niveau3_config_exigence.id` | — |
| `periode_debut` | date | non |  |  | — |
| `periode_fin` | date | non |  |  | — |
| `date_echeance` | date | non |  |  | — |
| `statut` | varchar(12) | non |  |  | — |
| `rapport_id` | uuid | oui |  |  | — |
| `remise_le` | timestamp with time zone | oui |  |  | — |
| `remise_par` | uuid | oui |  |  | — |

Contraintes : `echeance_periode_coherente` (verification), `echeance_remise_tracee` (verification), `echeance_statut_ferme` (verification), `uq_echeance_exigence_periode` (unicite)

## niveau3_config_exigence

Modèle `niveau3_config.Exigence` — isolée par organisation.

Une exigence du registre, versionnée, avec sa source documentaire.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `code` | varchar(64) | non |  |  | — |
| `donor_profile_id` | uuid | oui |  |  | — |
| `document_id` | uuid | non |  | `niveau3_config_documentreference.id` | — |
| `citation` | jsonb | non |  |  | — |
| `subject` | varchar(255) | non |  |  | — |
| `rule` | jsonb | non |  |  | — |
| `periodicity` | varchar(16) | oui |  |  | — |
| `due_offset_days` | integer | oui |  |  | — |
| `obligation` | varchar(16) | non |  |  | — |
| `condition_expr` | text | oui |  |  | — |
| `valid_from` | date | non |  |  | Début de validité, inclus (intervalle semi-ouvert [valid_from, valid_to[). |
| `valid_to` | date | oui |  |  | Fin de validité, EXCLUE ; vide si la ligne est ouverte. |
| `version` | integer | non |  |  | Numéro de version : une configuration utilisée ne se modifie pas, on en crée une. |
| `status` | varchar(16) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |
| `source` | varchar(16) | non |  |  | — |
| `confidence` | numeric(4, 3) | oui |  |  | — |
| `validated_by` | uuid | oui |  |  | — |
| `validated_at` | timestamp with time zone | oui |  |  | — |
| `citation_verifiee_sha256` | bytea | oui |  |  | — |

Contraintes : `exigence_dates_coherentes` (verification), `exigence_obligation_fermee` (verification), `exigence_origine_fermee` (verification), `exigence_periodicite_fermee` (verification), `exigence_statut_ferme` (verification), `exigence_validation_obligatoire` (verification), `uq_exigence_version` (unicite)

## niveau3_config_methodedecaissement

Modèle `niveau3_config.MethodeDecaissement` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `profil_id` | uuid | non |  | `niveau3_config_profildecaissement.id` | — |
| `method` | varchar(20) | non |  |  | — |
| `is_enabled` | boolean | non |  |  | — |
| `supporting_docs` | varchar(16)[] | non |  |  | — |
| `full_doc_threshold` | numeric(20, 4) | oui |  |  | — |
| `min_application_amount` | numeric(20, 4) | oui |  |  | — |
| `min_application_pct_of_ceiling` | numeric(9, 6) | oui |  |  | — |

Contraintes : `methode_ensemble_ferme` (verification), `methode_minimum_positif` (verification), `methode_pieces_ensemble_ferme` (verification), `methode_pourcentage_borne` (verification), `methode_seuil_documentation_positif` (verification), `methode_un_seul_minimum` (verification), `uq_methode_par_profil` (unicite)

## niveau3_config_profildecaissement

Modèle `niveau3_config.ProfilDecaissement` — isolée par organisation.

Ce qui varie d'un projet à l'autre chez un même bailleur : régime, dates, méthodes, seuils, comptes désignés, taux de financement par catégorie. Versionné avec date d'effet.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `accord_id` | uuid | non |  | `financements_accord.id` | — |
| `version` | integer | non |  |  | Numéro de version : une configuration utilisée ne se modifie pas, on en crée une. |
| `valid_from` | date | non |  |  | Début de validité, inclus (intervalle semi-ouvert [valid_from, valid_to[). |
| `valid_to` | date | oui |  |  | Fin de validité, EXCLUE ; vide si la ligne est ouverte. |
| `regime` | varchar(20) | non |  |  | — |
| `effectiveness_date` | date | oui |  |  | — |
| `eligibility_date` | date | oui |  |  | — |
| `closing_date` | date | oui |  |  | — |
| `disbursement_deadline` | date | oui |  |  | — |
| `requirement_id` | uuid | oui |  | `niveau3_config_exigence.id` | — |
| `status` | varchar(12) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |
| `rejection_reason` | text | non |  |  | — |
| `validated_by` | uuid | oui |  |  | — |
| `validated_at` | timestamp with time zone | oui |  |  | — |

Contraintes : `profil_dates_coherentes` (verification), `profil_jalons_0` (verification), `profil_jalons_1` (verification), `profil_jalons_2` (verification), `profil_jalons_3` (verification), `profil_regime_ferme` (verification), `profil_rejet_motive` (verification), `profil_statut_ferme` (verification), `profil_validation_obligatoire` (verification), `uq_profil_version` (unicite)

## niveau3_config_rattachementexigence

Modèle `niveau3_config.RattachementExigence` — isolée par organisation.

Relie un objet de configuration à l'exigence qui le justifie.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `exigence_id` | uuid | non |  | `niveau3_config_exigence.id` | — |
| `target_type` | varchar(32) | non |  |  | — |
| `target_id` | uuid | non |  |  | — |

Contraintes : `rattachement_type_cible_ferme` (verification), `uq_rattachement_exigence` (unicite)

## niveau3_config_reallocation

Modèle `niveau3_config.Reallocation` — isolée par organisation.

Un transfert de montant d'une catégorie à une autre : un ÉVÉNEMENT, pas une modification.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `accord_id` | uuid | non |  | `financements_accord.id` | — |
| `source_id` | uuid | non |  | `financements_categorie.id` | — |
| `cible_id` | uuid | non |  | `financements_categorie.id` | — |
| `montant` | numeric(20, 4) | non |  |  | — |
| `devise_id` | varchar(3) | non |  | `referentiels_devise.code` | — |
| `date_effet` | date | non |  |  | — |
| `motif` | text | non |  |  | — |
| `document_id` | uuid | oui |  | `niveau3_config_documentreference.id` | — |
| `status` | varchar(10) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |
| `demandeur` | uuid | non |  |  | — |
| `approbateur` | uuid | oui |  |  | — |
| `decided_at` | timestamp with time zone | oui |  |  | — |
| `motif_rejet` | text | non |  |  | — |
| `profil_cree_id` | uuid | oui |  | `niveau3_config_profildecaissement.id` | — |

Contraintes : `realloc_approbation_complete` (verification), `realloc_demandee_sans_decision` (verification), `realloc_montant_positif` (verification), `realloc_rejet_motive` (verification), `realloc_source_differente_cible` (verification), `realloc_statut_ferme` (verification)

## niveau3_config_reglecomptedesigne

Modèle `niveau3_config.RegleCompteDesigne` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `profil_id` | uuid | non |  | `niveau3_config_profildecaissement.id` | — |
| `bank_account_id` | uuid | non |  | `financements_comptebancaire.id` | — |
| `currency_id` | varchar(3) | non |  | `referentiels_devise.code` | — |
| `ceiling_kind` | varchar(8) | non |  |  | — |
| `ceiling_amount` | numeric(20, 4) | oui |  |  | — |
| `replenishment_threshold_pct` | numeric(9, 6) | oui |  |  | — |

Contraintes : `regle_compte_plafond_coherent` (verification), `regle_compte_plafond_ferme` (verification), `regle_compte_plafond_positif` (verification), `regle_compte_seuil_borne` (verification), `uq_regle_compte` (unicite)

## niveau3_config_reglefinancementcategorie

Modèle `niveau3_config.RegleFinancementCategorie` — isolée par organisation.

Allocation ET taux de financement d'une catégorie, versionnés avec le profil.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `profil_id` | uuid | non |  | `niveau3_config_profildecaissement.id` | — |
| `category_id` | uuid | non |  | `financements_categorie.id` | — |
| `allocation` | numeric(20, 4) | non |  |  | — |
| `funding_rate` | numeric(9, 6) | non |  |  | — |
| `tax_basis` | varchar(16) | non |  |  | — |
| `eligibility_from` | date | oui |  |  | — |
| `eligibility_to` | date | oui |  |  | — |
| `requires_prior_review` | boolean | non |  |  | — |
| `max_per_contract` | numeric(20, 4) | oui |  |  | — |
| `fin_propre_a_la_categorie` | boolean | non |  |  | — |

Contraintes : `regle_allocation_positive` (verification), `regle_assiette_fermee` (verification), `regle_eligibilite_coherente` (verification), `regle_fin_propre_exige_une_fin` (verification), `regle_plafond_contrat_positif` (verification), `regle_taux_dans_0_1` (verification), `uq_regle_categorie` (unicite)

## organisations_organisation

Modèle `organisations.Organisation`.

L'entité juridique qui exploite la plateforme. Son `id` EST l'`org_id`.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `code` | varchar(32) | non |  |  | — |
| `raison_sociale` | varchar(255) | non |  |  | — |
| `pays` | varchar(2) | non |  |  | — |
| `monnaie_tenue` | varchar(3) | non |  |  | — |
| `langues_actives` | jsonb | non |  |  | — |
| `separation_des_taches` | boolean | non |  |  | — |

Contraintes : `organisation_monnaie_iso3` (verification), `organisation_pays_iso2` (verification)

## organisations_projet

Modèle `organisations.Projet` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `code` | varchar(32) | non |  |  | — |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `start_date` | date | oui |  |  | — |
| `closing_date` | date | oui |  |  | — |
| `last_disbursement_date` | date | oui |  |  | — |
| `base_currency` | varchar(3) | non |  |  | — |
| `accounting_basis` | varchar(24) | non |  |  | — |
| `status` | varchar(16) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |

Contraintes : `projet_base_comptable_fermee` (verification), `projet_dates_coherentes` (verification), `projet_devise_iso3` (verification), `projet_statut_ferme` (verification), `uq_projet_code` (unicite)

## organisations_utilisateur

Modèle `organisations.Utilisateur` — isolée par organisation.

Compte utilisateur, rattaché à UNE organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `password` | varchar(128) | non |  |  | — |
| `last_login` | timestamp with time zone | oui |  |  | — |
| `is_superuser` | boolean | non |  |  | Précise que l’utilisateur possède toutes les permissions sans les assigner explicitement. |
| `username` | varchar(150) | non |  |  | Requis. 150 caractères maximum. Uniquement des lettres, nombres et les caractères « @ », « . », « + », « - » et « _ ». |
| `first_name` | varchar(150) | non |  |  | — |
| `last_name` | varchar(150) | non |  |  | — |
| `email` | varchar(254) | non |  |  | — |
| `is_staff` | boolean | non |  |  | Précise si l’utilisateur peut se connecter à ce site d'administration. |
| `is_active` | boolean | non |  |  | Précise si l’utilisateur doit être considéré comme actif. Décochez ceci plutôt que de supprimer le compte. |
| `date_joined` | timestamp with time zone | non |  |  | — |
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `org_id` | uuid | oui |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `langue` | varchar(2) | non |  |  | — |

Contraintes : `utilisateur_langue_geree` (verification)

## publication_accesauditeur

Modèle `publication.AccesAuditeur` — isolée par organisation.

L'accès d'un auditeur externe : projets nommés, plage de périodes, lecture seule. L7-T02.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `nom` | varchar(200) | non |  |  | — |
| `project_ids` | jsonb | non |  |  | — |
| `period_from` | date | non |  |  | — |
| `period_to` | date | non |  |  | — |
| `jeton_hash` | bytea | non |  |  | — |
| `expire_le` | timestamp with time zone | non |  |  | — |
| `cree_par` | uuid | non |  |  | — |
| `revoque_le` | timestamp with time zone | oui |  |  | — |
| `revoque_par` | uuid | oui |  |  | — |

Contraintes : `acces_auditeur_plage_coherente` (verification), `acces_auditeur_revocation_tracee` (verification), `uq_acces_auditeur_jeton` (unicite)

## publication_fichierrapport

Modèle `publication.FichierRapport` — isolée par organisation.

Un fichier produit pour un rapport publié, avec son empreinte. Ajout seul. Voir L6-T05.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `rapport_id` | uuid | non |  | `publication_rapportpublie.id` | — |
| `nature` | varchar(8) | non |  |  | — |
| `format` | varchar(8) | non |  |  | — |
| `langue` | varchar(8) | non |  |  | — |
| `nom` | varchar(200) | non |  |  | — |
| `contenu` | bytea | non |  |  | — |
| `sha256` | varchar(64) | non |  |  | Empreinte SHA-256 du contenu : preuve d'intégrité. |
| `taille` | integer | non |  |  | — |
| `produit_par` | uuid | non |  |  | — |

Contraintes : `fichier_format_ferme` (verification), `fichier_nature_fermee` (verification), `uq_fichier_rapport_nature_format_langue` (unicite)

## publication_motifrejet

Modèle `publication.MotifRejet` — isolée par organisation.

Un motif pour lequel un bailleur a déjà rejeté (ou rejetterait) un rapport. L6-T07.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `code` | varchar(64) | non |  |  | — |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `controle_code` | varchar(64) | non |  |  | — |
| `source` | text | non |  |  | — |
| `actif` | boolean | non |  |  | — |

Contraintes : `uq_motifrejet_code` (unicite)

## publication_rapportpublie

Modèle `publication.RapportPublie` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `template_code` | varchar(64) | non |  |  | — |
| `template_version` | integer | oui |  |  | — |
| `modele` | jsonb | non |  |  | — |
| `period_from` | date | non |  |  | — |
| `period_to` | date | non |  |  | — |
| `params` | jsonb | non |  |  | — |
| `config_version` | jsonb | non |  |  | — |
| `mapping_versions` | jsonb | non |  |  | — |
| `dataset_hash` | bytea | non |  |  | — |
| `values` | jsonb | non |  |  | — |
| `seal` | bytea | non |  |  | — |
| `published_by` | uuid | non |  |  | — |
| `published_at` | timestamp with time zone | non |  |  | — |

Contraintes : `rapport_periode_coherente` (verification)

## publication_simulationrevue

Modèle `publication.SimulationRevue` — isolée par organisation.

Le résultat d'une simulation de revue bailleur, gardé tel quel. Ajout seul.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `objet_type` | varchar(40) | non |  |  | — |
| `objet_id` | uuid | oui |  |  | — |
| `date_effet` | date | non |  |  | — |
| `avis` | varchar(12) | non |  |  | — |
| `constats` | jsonb | non |  |  | — |
| `lancee_par` | uuid | non |  |  | — |

Contraintes : `simulation_avis_ferme` (verification)

## publication_soumissionbailleur

Modèle `publication.SoumissionBailleur` — isolée par organisation.

Un envoi réel d'un rapport au bailleur et son issue. Alimente l'indicateur phare.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `template_code` | varchar(64) | non |  |  | — |
| `period_to` | date | non |  |  | — |
| `numero_envoi` | smallint | non |  |  | — |
| `rapport_id` | uuid | oui |  |  | — |
| `simulation_id` | uuid | oui |  | `publication_simulationrevue.id` | — |
| `envoyee_le` | date | non |  |  | — |
| `resultat` | varchar(12) | non |  |  | — |
| `motif_rejet` | text | non |  |  | — |
| `decidee_le` | date | oui |  |  | — |
| `saisie_par` | uuid | non |  |  | — |

Contraintes : `soumission_issue_coherente` (verification), `soumission_numero_pos` (verification), `soumission_resultat_ferme` (verification), `uq_soumission_envoi` (unicite)

## rapprochement_mouvementreleve

Modèle `rapprochement.MouvementReleve` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `compte_id` | uuid | non |  | `financements_comptebancaire.id` | — |
| `reference` | varchar(100) | non |  |  | — |
| `date_operation` | date | non |  |  | — |
| `libelle` | varchar(255) | non |  |  | — |
| `montant` | numeric(20, 4) | non |  |  | — |
| `taux` | numeric(20, 10) | non |  |  | — |
| `montant_base` | numeric(20, 4) | non |  |  | — |
| `rapprochement_id` | uuid | oui |  | `rapprochement_rapprochement.id` | — |

Contraintes : `mouvement_montant_non_nul` (verification), `mouvement_taux_positif` (verification), `uq_mouvement_reference` (unicite)

## rapprochement_rapprochement

Modèle `rapprochement.Rapprochement` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `compte_id` | uuid | non |  | `financements_comptebancaire.id` | — |
| `code` | varchar(12) | non |  |  | — |
| `status` | varchar(6) | non |  |  | Statut du cycle de vie de la ligne (ensemble fermé, contrôlé par la base). |
| `rapproche_at` | timestamp with time zone | non |  |  | — |
| `rapproche_by` | uuid | oui |  |  | — |
| `ecart_change` | numeric(20, 4) | non |  |  | — |
| `ecriture_ecart_id` | uuid | oui |  | `comptabilite_ecriture.id` | — |
| `ecriture_ecart_annulation_id` | uuid | oui |  | `comptabilite_ecriture.id` | — |
| `annule_at` | timestamp with time zone | oui |  |  | — |
| `annule_by` | uuid | oui |  |  | — |
| `motif_annulation` | text | non |  |  | — |

Contraintes : `rapprochement_annulation_coherente` (verification), `rapprochement_ecart_a_son_ecriture` (verification), `rapprochement_statut_ferme` (verification), `uq_rapprochement_code` (unicite)

## referentiels_compte

Modèle `referentiels.Compte` — isolée par organisation.

Compte du plan comptable d'une organisation. Voir L2-T02.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `code` | varchar(20) | non |  |  | — |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `classe` | smallint | non |  |  | — |
| `sens_normal` | varchar(6) | non |  |  | — |
| `imputable` | boolean | non |  |  | — |
| `actif` | boolean | non |  |  | — |
| `parent_id` | uuid | oui |  | `referentiels_compte.id` | — |
| `paquet_id` | uuid | oui |  |  | — |

Contraintes : `compte_classe_1_9` (verification), `compte_code_numerique` (verification), `compte_pas_son_propre_parent` (verification), `compte_sens_ferme` (verification), `uq_compte_code` (unicite)

## referentiels_correspondanceimport

Modèle `referentiels.CorrespondanceImport` — isolée par organisation.

Correspondance colonnes du fichier -> champs du référentiel. Voir L2-T07.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `nom` | varchar(100) | non |  |  | — |
| `type_referentiel` | varchar(20) | non |  |  | — |
| `colonnes` | jsonb | non |  |  | — |
| `valeurs_defaut` | jsonb | non |  |  | — |
| `statut` | varchar(8) | non |  |  | — |
| `validated_by` | uuid | oui |  |  | — |
| `validated_at` | timestamp with time zone | oui |  |  | — |

Contraintes : `correspondance_statut_ferme` (verification), `correspondance_type_ferme` (verification), `correspondance_validation_obligatoire` (verification), `uq_correspondance_nom` (unicite)

## referentiels_devise

Modèle `referentiels.Devise`.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `code` | varchar(3) | non | PK |  | — |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `decimales` | smallint | non |  |  | — |

Contraintes : `devise_code_iso3` (verification), `devise_decimales_bornees` (verification)

## referentiels_parametredevises

Modèle `referentiels.ParametreDevises` — isolée par organisation.

Les réglages de devises d'une organisation, ou d'un projet qui les surcharge.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | oui |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `devise_reference_id` | varchar(3) | oui |  | `referentiels_devise.code` | — |
| `devises_autorisees` | varchar(3)[] | oui |  |  | — |
| `type_taux` | varchar(16) | oui |  |  | — |
| `version` | integer | non |  |  | Numéro de version : une configuration utilisée ne se modifie pas, on en crée une. |
| `valid_from` | date | non |  |  | Début de validité, inclus (intervalle semi-ouvert [valid_from, valid_to[). |
| `valid_to` | date | oui |  |  | Fin de validité, EXCLUE ; vide si la ligne est ouverte. |
| `motif` | text | non |  |  | — |

Contraintes : `parametredevises_dates_coherentes` (verification), `parametredevises_regle_quelque_chose` (verification), `parametredevises_type_taux_ferme` (verification), `uq_parametredevises_version_organisation` (unicite), `uq_parametredevises_version_projet` (unicite)

## referentiels_plandimension

Modèle `referentiels.PlanDimension` — isolée par organisation.

Plan d'axe : relie un EMPLACEMENT fixe (1 à 4) au plan métier que l'organisation y place.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `kind` | varchar(10) | non |  |  | — |
| `slot` | smallint | non |  |  | — |
| `code` | varchar(32) | non |  |  | — |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `is_mandatory` | boolean | non |  |  | — |

Contraintes : `plandimension_slot` (verification), `plandimension_type_ferme` (verification), `uq_plandimension_code` (unicite), `uq_plandimension_emplacement` (unicite)

## referentiels_taux

Modèle `referentiels.Taux` — isolée par organisation.

Unités de monnaie de tenue de l'organisation pour une unité de `devise`.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `devise_id` | varchar(3) | non |  | `referentiels_devise.code` | — |
| `date` | date | non |  |  | — |
| `taux` | numeric(20, 10) | non |  |  | — |
| `type_taux` | varchar(16) | non |  |  | — |
| `source` | varchar(255) | non |  |  | — |

Contraintes : `taux_strictement_positif` (verification), `taux_type_ferme` (verification), `uq_taux_jour_type` (unicite)

## referentiels_tiers

Modèle `referentiels.Tiers` — isolée par organisation.

Tiers : fournisseur, bénéficiaire, personnel… Donnée personnelle (L2-T04).

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `code` | varchar(20) | non |  |  | — |
| `nature` | varchar(12) | non |  |  | — |
| `nom` | varchar(255) | non |  |  | — |
| `identification` | jsonb | non |  |  | — |
| `coordonnees_bancaires` | jsonb | oui |  |  | — |
| `actif` | boolean | non |  |  | — |
| `retention_until` | date | oui |  |  | — |
| `anonymise_le` | timestamp with time zone | oui |  |  | — |

Contraintes : `tiers_nature_ferme` (verification), `uq_tiers_code` (unicite)

## referentiels_valeurdimension

Modèle `referentiels.ValeurDimension` — isolée par organisation.

Valeur d'un plan d'axe, hiérarchique (composante > activité > tâche).

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `plan_id` | uuid | non |  | `referentiels_plandimension.id` | — |
| `parent_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `code` | varchar(20) | non |  |  | — |
| `label` | jsonb | non |  |  | Libellé multilingue : objet JSON {"fr": …, "en": …}. |
| `is_postable` | boolean | non |  |  | — |
| `is_active` | boolean | non |  |  | — |

Contraintes : `uq_valeurdimension_code` (unicite), `valeurdimension_pas_son_propre_parent` (verification)

## reprise_lignebalanceorigine

Modèle `reprise.LigneBalanceOrigine` — isolée par organisation.

Une ligne de la balance d'origine (celle du progiciel quitté), agrégée par clé.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `reprise_id` | uuid | non |  | `reprise_reprise.id` | — |
| `compte` | varchar(20) | non |  |  | — |
| `accord` | varchar(60) | non |  |  | — |
| `axe1` | varchar(20) | non |  |  | — |
| `debit` | numeric(20, 4) | non |  |  | — |
| `credit` | numeric(20, 4) | non |  |  | — |

Contraintes : `balance_origine_positive` (verification), `uq_balance_origine_cle` (unicite)

## reprise_piecereprise

Modèle `reprise.PieceReprise` — isolée par organisation.

Une pièce de l'historique source et l'écriture qu'elle a produite.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `reprise_id` | uuid | non |  | `reprise_reprise.id` | — |
| `cle` | varchar(64) | non |  |  | — |
| `contenu_sha256` | bytea | non |  |  | — |
| `ecriture_id` | uuid | non |  |  | — |

Contraintes : `uq_piece_reprise_cle` (unicite)

## reprise_rapportreprise

Modèle `reprise.RapportReprise` — isolée par organisation.

Le rapport du contrôle d'une reprise : écarts ligne à ligne, signature nominative.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `reprise_id` | uuid | non |  | `reprise_reprise.id` | — |
| `accepte` | boolean | non |  |  | — |
| `ecart_general` | numeric(20, 4) | non |  |  | — |
| `ecart_accords` | numeric(20, 4) | non |  |  | — |
| `nombre_ecritures` | integer | non |  |  | — |
| `ecarts` | jsonb | non |  |  | — |
| `contenu_sha256` | bytea | non |  |  | — |
| `signe_par` | uuid | oui |  |  | — |
| `signe_nom` | varchar(150) | non |  |  | — |
| `signe_le` | timestamp with time zone | oui |  |  | — |

Contraintes : `rapport_reprise_signature_complete` (verification), `rapport_reprise_signe_seulement_si_accepte` (verification)

## reprise_reprise

Modèle `reprise.Reprise` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `nom` | varchar(200) | non |  |  | — |
| `date_bascule` | date | non |  |  | — |
| `devise` | varchar(3) | non |  |  | — |
| `mode` | varchar(10) | oui |  |  | — |
| `statut` | varchar(10) | non |  |  | — |
| `balance_sha256` | bytea | oui |  |  | — |
| `cree_par` | uuid | non |  |  | — |

Contraintes : `reprise_mode_ferme` (verification), `reprise_statut_ferme` (verification)

## reversibilite_exportorganisation

Modèle `reversibilite.ExportOrganisation` — isolée par organisation.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `demandeur_id` | uuid | non |  |  | — |
| `statut` | varchar(9) | non |  |  | — |
| `produit_le` | timestamp with time zone | oui |  |  | — |
| `file_ref` | varchar(512) | non |  |  | — |
| `sha256` | varchar(64) | non |  |  | Empreinte SHA-256 du contenu : preuve d'intégrité. |
| `taille` | bigint | oui |  |  | — |
| `nombre_tables` | integer | oui |  |  | — |
| `erreur` | text | non |  |  | — |

Contraintes : `export_pret_complet` (verification), `export_statut_ferme` (verification)

## tresorerie_appariementdemande

Modèle `tresorerie.AppariementDemande` — isolée par organisation.

Un encaissement du relevé apparié à une demande de retrait. Voir L9-T05.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `mouvement_id` | uuid | non |  | `rapprochement_mouvementreleve.id` | — |
| `demande_id` | uuid | non |  | `decaissements_demanderetrait.id` | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `apparie_par` | uuid | non |  |  | — |
| `annule_at` | timestamp with time zone | oui |  |  | — |
| `annule_par` | uuid | oui |  |  | — |
| `motif_annulation` | text | non |  |  | — |

Contraintes : `appariement_annulation_coherente` (verification), `uq_appariement_un_mouvement_une_demande` (unicite)

## tresorerie_justificationcomptespecial

Modèle `tresorerie.JustificationCompteSpecial` — isolée par organisation.

Des dépenses justifiées à la Banque sous une demande, pour un compte spécial. Voir L11-D4.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `compte_id` | uuid | non |  | `financements_comptebancaire.id` | — |
| `demande_id` | uuid | non |  | `decaissements_demanderetrait.id` | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `montant` | numeric(20, 4) | non |  |  | — |
| `date_soumission` | date | non |  |  | — |
| `saisie_par` | uuid | non |  |  | — |
| `annule_at` | timestamp with time zone | oui |  |  | — |
| `annule_par` | uuid | oui |  |  | — |
| `motif_annulation` | text | non |  |  | — |

Contraintes : `justifcs_annulation_coherente` (verification), `justifcs_montant_positif` (verification), `uq_justifcs_une_par_demande` (unicite)

## tresorerie_justificationecart

Modèle `tresorerie.JustificationEcart` — isolée par organisation.

L'explication d'une partie de l'écart d'un état de reconstitution. Ajout seul.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `compte_id` | uuid | non |  | `financements_comptebancaire.id` | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `date_debut` | date | non |  |  | — |
| `date_fin` | date | non |  |  | — |
| `cible` | varchar(10) | non |  |  | — |
| `montant` | numeric(20, 4) | non |  |  | — |
| `explication` | text | non |  |  | — |
| `saisie_par` | uuid | non |  |  | — |

Contraintes : `justifecart_cible_fermee` (verification), `justifecart_expliquee` (verification), `justifecart_montant_non_nul` (verification), `justifecart_periode` (verification)

## tresorerie_previsiontresorerie

Modèle `tresorerie.PrevisionTresorerie` — isolée par organisation.

Une prévision d'encaissements et de décaissements, pour un mois et un axe. Ajout seul.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `devise` | varchar(3) | non |  |  | — |
| `annee` | smallint | non |  |  | — |
| `mois` | smallint | non |  |  | — |
| `axe_id` | uuid | oui |  | `referentiels_valeurdimension.id` | — |
| `revision` | smallint | non |  |  | — |
| `encaissements` | numeric(20, 4) | non |  |  | — |
| `decaissements` | numeric(20, 4) | non |  |  | — |
| `motif` | text | non |  |  | — |
| `etablie_par` | uuid | non |  |  | — |

Contraintes : `prevision_mois` (verification), `prevision_positive` (verification), `prevision_revision` (verification), `prevision_revision_motivee` (verification), `uq_prevision_revision_axe` (unicite), `uq_prevision_revision_sans_axe` (unicite)

## tresorerie_soldereleve

Modèle `tresorerie.SoldeReleve` — isolée par organisation.

Le solde de clôture d'un jour, tel que le relevé de la banque le donne. Ajout seul.

| Colonne | Type | Null | Clé | Relation | Description |
|---|---|---|---|---|---|
| `id` | uuid | non | PK |  | Identifiant unique (UUID) de la ligne. |
| `created_at` | timestamp with time zone | non |  |  | Date et heure de création de la ligne. |
| `created_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui a créé la ligne. |
| `updated_at` | timestamp with time zone | non |  |  | Date et heure de la dernière modification. |
| `updated_by` | uuid | oui |  |  | Identifiant de l'utilisateur qui l'a modifiée en dernier. |
| `org_id` | uuid | non |  |  | Organisation propriétaire : l'isolation des données repose dessus (RLS). |
| `compte_id` | uuid | non |  | `financements_comptebancaire.id` | — |
| `project_id` | uuid | non |  |  | Projet auquel la ligne se rattache (cloisonné par habilitation). |
| `date_solde` | date | non |  |  | — |
| `solde` | numeric(20, 4) | non |  |  | — |
| `reference` | varchar(100) | non |  |  | — |
| `saisi_par` | uuid | non |  |  | — |

Contraintes : `uq_soldereleve_jour` (unicite)
