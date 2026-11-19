# APPORTS DES DOSSIERS « BAILLEURS ET CONVENTIONS DE FINANCEMENT »

**Sources examinées :** cahier des charges du module bailleurs et conventions (3ᵉ partie), dossier de conception parties 1 et 2.
**Date :** 12 novembre 2026

> **Résumé.** Ces dossiers confirment notre architecture (moteur paramétrable par convention, versions immuables, version conservée sur l'opération, isolation par organisation, IA qui propose et humain qui valide). Ils n'ajoutent pas de fondation. Ils apportent des garanties que nous n'avions pas posées, listées ci-dessous.

## 1. Retenu, et où c'est appliqué

| Apport | Application |
|---|---|
| Intervalle de validité semi-ouvert `[du, au[` | Guide §B.6 · Architecture §3.1 · décision D-08 |
| Pas de chevauchement de versions actives (`EXCLUDE` sur `daterange`) | Guide §B.6 · Architecture §3.1 et §4bis · L5-T04 |
| Immutabilité des tables enfants d'une version approuvée, par déclencheur | Guide §B.6 · Architecture §3.1 · L5-T04 |
| Réallocation = événement tracé, approbateur ≠ demandeur | Architecture §4bis · L5-T04bis · D-09 |
| Avenant d'accord, effet « avant / après » | L4-T04 · L5-T04bis · Architecture §4bis |
| Version de profil conservée sur l'opération et le résultat de contrôle | L5-T04 · Architecture §4bis |
| Opérateurs de contrôle à jeu fermé, schéma par type de règle | L6-T01 · Spécification §7 |
| Résultat `à vérifier` ; journal de chaque évaluation | L6-T01 · Spécification §7 |
| Dérogation formelle qui n'efface pas le résultat initial | L6-T02 · Architecture §4bis · Spécification §7 |
| Contrôle de complétude avant soumission | L5-T04bis |
| Comparaison de deux versions de configuration | L5-T04bis |
| Tests de concurrence (réallocations, demandes sur un même solde, double approbation, activation) | L4-T06 · L5-T04 · L5-T04bis · L6-T02 · annexe D |
| Test d'isolation « modification de `org_id` » | L1-T02 · contrôle de sortie L4 |
| Statut d'accord `suspendu` | L4-T04 · Spécification §5.3 |
| Rejets et litiges de demandes (`motif`, `reprise_de`) | L4-T06 |
| Types de comptes bancaires, numéro masqué par habilitation | L4-T04 · L9-T05 |
| Consolidation multi-devises sans mélange silencieux | L10-T02 · Spécification §9 |
| Contrôles de risque simples (catégorie proche du plafond, avance ancienne, rejets répétés) | L6-T01 |
| Codes d'erreur stables | L6-T01 |
| Clé de stockage préfixée par `org_id` ; sauvegarde cohérente base + fichiers | Architecture §9.2 |
| Scénario de recette « deux accords, un projet » | Spécification §17 (T17) · L10-T03 |

## 2. Rejeté, avec le motif

| Proposition | Motif |
|---|---|
| Socle Supabase : Auth, RPC, `is_org_member`, politiques `TO authenticated`, Storage | Notre isolation est la RLS sur `app.org_id` posée par le middleware ; `authenticated`, `anon` et `service_role` n'ont aucun droit sur le schéma applicatif. Décision D1. |
| Noms de tables et de colonnes en anglais, `organization_id`, libellés `TEXT` | Conventions du projet : français, `org_id`, libellés JSONB. |
| Table générique `configuration_parameters` (code + JSONB) | Double `requirement.rule` et le profil relationnel ; contredit leur propre règle sur le JSONB. |
| Cycle de vie à 8 statuts | `programmée` = version `active` à `valid_from` futur. Seul `rejeté` avec motif est ajouté. |
| Héritage dynamique bailleur → projet → convention | Crée des modifications silencieuses. La copie indépendante et la proposition de mise à jour suffisent. |
| Menu principal à 11 entrées | Notre écran d'accueil est un tableau d'échéances (§8.2). |
| Plan de migrations 001–015, livrables du prestataire | Notre plan est L0–L10. |
| Module « analyse des risques » | Remplacé par trois contrôles existants (voir ci-dessus). |
| Workflow universel | Circuit borné de 1 à 5 étapes (note 06 §3.2). |

## 3. Reporté

| Sujet | Quand |
|---|---|
| Registre des obligations non financières (audits, visibilité, environnement et social) | V1.5, en réutilisant le calendrier issu du registre, avec `responsable` et `preuve` |
| Assistant de configuration en 10 étapes | Habillage front-end de L5, étapes alignées sur les services existants |
| Outbox transactionnelle | Avec l'API publique (V2) |

## 4. À vérifier avant toute décision

Les formulaires par bailleur et le contenu fonctionnel des chapitres TOM²PRO cités (BAD A1/A2/A3, FIDA 100/104/105, devis-programmes et mémoires du FED, brouillard, rejets et litiges par bailleur) ne reposent que sur le sommaire du manuel. Ils relèvent des profils L5-T06 et L10-T01 et s'ajoutent **par paramétrage**, après lecture du manuel ou des documents contractuels du projet. Les dossiers eux-mêmes le précisent : les mécanismes historiques du FED ne s'appliquent pas automatiquement à tous les instruments actuels de l'Union européenne.

## 5. Incohérences relevées dans les dossiers

- Statuts de convention différents entre la partie 3 (brouillon, en validation, approuvée, active, suspendue, clôturée) et le SQL de la partie 2 (`draft, active, suspended, closed, cancelled`).
- Montants d'exemple différents d'un document à l'autre (8 M + 3 M, 5 M + 3 M, 5 M + 2 M + 3 M). Chiffres fictifs, sans conséquence.

---

*Documents liés : [spécification](01_SPECIFICATION_FONCTIONNELLE.md) · [architecture](02_ARCHITECTURE_TECHNIQUE.md) · [lots L0 à L4](04_PLAN_LOTS_L0_A_L4.md) · [lots L5 à L10](05_PLAN_LOTS_L5_A_L10.md) · [apports du rapport et du manuel](06_APPORTS_RAPPORT_ET_MANUEL.md)*
