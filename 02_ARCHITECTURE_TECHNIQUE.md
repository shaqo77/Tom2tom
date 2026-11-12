# PLATEFORME MULTI-BAILLEURS — DOSSIER D'ARCHITECTURE TECHNIQUE

**Suite de :** [spécification fonctionnelle](01_SPECIFICATION_FONCTIONNELLE.md)
**Version :** 2.0 — 12 novembre 2026 · remplace la version 1.0
**Contraintes :** multi-organisations et multi-projets natif · architecture à quatre niveaux · déploiement Djibouti puis Afrique francophone · connectivité intermittente · hébergement souverain possible

---

## 1. STACK RECOMMANDÉE

| Couche | Choix | Justification |
|---|---|---|
| **Base de données** | **PostgreSQL 16+** | Le seul choix défendable. `NUMERIC` exact pour les montants, **Row-Level Security** native pour l'isolation, contraintes différées pour l'équilibre des écritures, `JSONB` indexable pour les configurations et modèles d'états, partitionnement, restauration à un instant donné, export logique par organisation. |
| **Backend** | **Python 3.12 · Django 5 · Django REST Framework** | Voir §1.1. |
| **Front** | **React + TypeScript**, TanStack Query et Router, grille de données performante | La saisie comptable est un usage clavier intensif sur grille dense. C'est le seul écran qui justifie vraiment une application monopage, et il le justifie entièrement. |
| **Tâches de fond** | **Procrastinate** (file adossée à PostgreSQL) | Évite d'introduire Redis ou RabbitMQ en v1 : une composante de moins à exploiter, et des garanties transactionnelles héritées de la base. |
| **Documents** | `openpyxl` (XLSX) · **Typst** ou WeasyPrint (PDF) | Les états bailleurs se livrent en Excel et en PDF scellé. Typst gère nativement le droite-à-gauche. |
| **Lecture de documents** | `pypdf` + couche d'extraction (module optionnel §7) | Registre des exigences assisté. |
| **Authentification** | OIDC — **Keycloak** auto-hébergé ou fournisseur managé | Double authentification obligatoire sur les rôles de validation. Pas de gestion de mots de passe écrite à la main. |
| **Exécution** | Conteneurs · PostgreSQL managé avec PITR · stockage objet compatible S3 pour les pièces | Même image en SaaS et en hébergement souverain. |

### 1.1 Pourquoi Django côté serveur

Les trois risques dominants sont, dans l'ordre : **la justesse monétaire**, **le moteur d'états et de mapping**, et **le volume de référentiels et de configuration**.

- **Justesse monétaire.** Python possède `decimal.Decimal` en bibliothèque standard, avec contrôle explicite du contexte d'arrondi, relié nativement à `NUMERIC` par Django. En TypeScript, il n'existe pas de type décimal natif : rien n'empêche un développeur d'écrire `a + b` sur deux montants et d'introduire une erreur de flottant qui ne se verra qu'au centième, six mois plus tard, dans un état bailleur. **Sur un produit comptable, ce risque s'élimine par le choix de l'outil, pas par la revue de code.**
- **Volume de configuration.** Le registre des exigences, les profils de bailleurs, les mappings versionnés et les référentiels représentent une surface considérable de création-lecture-modification hiérarchique et versionnée. L'ORM, les migrations et DRF y font gagner un temps important.
- **Moteur d'états.** Égalité : dans les deux cas, on écrit un analyseur de formules et un compilateur vers SQL.

**Le choix inverse — TypeScript et NestJS — reste légitime si l'équipe est déjà TypeScript et sans profondeur Python.** Le gain d'un langage unique entre le front et le back est réel, à condition d'investir dès le premier jour dans un type `Money` dédié et une règle de lint interdisant `number` sur tout montant.

> **Le choix est réversible à coût faible tant que le moteur comptable n'est pas écrit — c'est-à-dire jusqu'au début de L3. Après, il ne l'est plus.**

### 1.2 Ce qu'il ne faut pas faire

- **Ni ERP générique à adapter, ni plateforme à faible code.** Le cœur de valeur — imputation multidimensionnelle, mapping versionné, moteur d'états, registre des exigences — n'existe dans aucun produit générique, et le contourner coûte plus cher que de l'écrire.
- **Pas de microservices en v1.** Un monolithe modulaire, découpé selon les quatre niveaux. La comptabilité est transactionnelle par nature : répartir un grand livre entre plusieurs bases est une erreur coûteuse et difficile à défaire.
- **Pas de NoSQL pour le grand livre.** Équilibre des écritures, contrôle budgétaire concurrent et agrégations d'états exigent transactions et jointures.
- **Pas d'ORM pour le moteur d'états.** Les états s'écrivent en SQL généré et maîtrisé. L'ORM sert au CRUD, pas à l'agrégation analytique.
- **Pas de système de greffons ni de scripts clients en v1.** Cela tue la capacité à faire évoluer le produit.

---

## 2. ISOLATION : ORGANISATION ET PROJET

### 2.1 Deux frontières, deux mécanismes

Le cahier des charges exige une « séparation des données et habilitations **par organisation et projet** ». Ce sont deux problèmes de nature différente, traités différemment.

| Frontière | Nature | Mécanisme |
|---|---|---|
| **Organisation** | Frontière d'**isolation**. Deux organisations ne doivent jamais se voir, sous aucune circonstance, y compris en cas de requête mal écrite. | **Row-Level Security PostgreSQL**, imposée par la base |
| **Projet** | Frontière d'**habilitation**. Au sein d'une organisation, les utilisateurs voient certains projets ; la consolidation multi-projets est un besoin légitime. | **Contrôle applicatif** sur périmètre d'habilitation, vérifié au serveur à chaque requête |

```sql
ALTER TABLE journal_entry_line ENABLE ROW LEVEL SECURITY;
ALTER TABLE journal_entry_line FORCE  ROW LEVEL SECURITY;

CREATE POLICY org_isolation ON journal_entry_line
  USING      (org_id = current_setting('app.org_id')::uuid)
  WITH CHECK (org_id = current_setting('app.org_id')::uuid);
```

L'application ouvre chaque transaction par `SET LOCAL app.org_id = '…'`, dérivé **du jeton d'authentification et jamais d'un paramètre de requête**.

**Pourquoi la RLS et pas un simple filtre.** Un `WHERE org_id = ?` oublié dans une requête sur trois cents, c'est une fuite de données financières entre deux organisations. La RLS déplace la garantie dans la base : même une requête mal écrite ne voit rien d'autre que son organisation.

**Pourquoi le projet n'est pas traité par RLS.** Parce que le tableau de bord multi-projets, la consolidation et les contrôles de cohérence inter-projets sont des besoins fonctionnels. Une politique RLS par projet les rendrait impossibles ou forcerait à la contourner — et une politique de sécurité qu'on contourne ne protège plus rien.

### 2.2 Alternatives écartées

| Option | Verdict |
|---|---|
| Un schéma PostgreSQL par organisation | Export trivial, isolation très visible, mais migrations lentes et fragiles sur des centaines de schémas. **Écarté pour le SaaS, retenu pour l'hébergement souverain mono-organisation** (§9.3). |
| Une base par organisation | Exploitation intenable à l'échelle visée. Écarté. |
| Filtre applicatif seul | Une seule requête mal écrite suffit. Écarté. |

---

## 3. MODÈLE DE DONNÉES — SOCLE

### 3.1 Règles transversales

| Règle | Mise en œuvre |
|---|---|
| **Tout montant est exact** | `NUMERIC(20,4)` en base, `Decimal` en application. **Aucun montant ne transite jamais par un flottant**, y compris en JSON : les montants sont sérialisés en chaînes. |
| **Toute table porte `org_id`** | `uuid NOT NULL`, présent dans chaque index et chaque clé étrangère composite. |
| **Les tables de flux portent `project_id`** | Périmètre d'habilitation et dimension de restitution. |
| **Toute table porte sa trace** | `created_at`, `created_by`, `updated_at`, `updated_by`. |
| **Les référentiels et configurations sont versionnés** | `version`, `valid_from`, `valid_to`. Jamais de mise à jour destructive d'un objet déjà utilisé. |
| **Les libellés sont multilingues** | `label` JSONB : `{"fr": …, "en": …, "ar": …}`. Jamais de colonne `label_fr`. |
| **Rien n'est supprimé** | Désactivation sur les référentiels, contre-passation sur les écritures, archivage sur les configurations. |

### 3.2 Projets et référentiel analytique

```sql
CREATE TABLE project (
  id uuid PRIMARY KEY, org_id uuid NOT NULL,
  code text NOT NULL, label jsonb NOT NULL,
  start_date date, closing_date date, last_disbursement_date date,
  base_currency_id uuid NOT NULL REFERENCES currency,  -- monnaie de tenue
  accounting_basis text NOT NULL
      CHECK (accounting_basis IN ('cash','accrual','cash_with_commitments')),
  status text NOT NULL
      CHECK (status IN ('preparing','active','closing','closed')),
  UNIQUE (org_id, code)
);

-- Registre des axes : relie un emplacement fixe (1..4) au plan métier
-- que l'organisation y a placé. Souplesse métier sans modèle générique.
CREATE TABLE dimension_plan (
  id uuid PRIMARY KEY, org_id uuid NOT NULL,
  kind text NOT NULL CHECK (kind IN ('gestion','auxiliaire')),
  slot smallint NOT NULL CHECK (slot BETWEEN 1 AND 4),
  code text NOT NULL, label jsonb NOT NULL,
  is_mandatory boolean NOT NULL DEFAULT false,
  UNIQUE (org_id, kind, slot)
);

CREATE TABLE dimension_value (        -- hiérarchique : composante > activité > tâche
  id uuid PRIMARY KEY, org_id uuid NOT NULL,
  plan_id uuid NOT NULL REFERENCES dimension_plan,
  parent_id uuid REFERENCES dimension_value,
  code text NOT NULL, label jsonb NOT NULL,
  is_postable boolean NOT NULL DEFAULT true,   -- seules les feuilles sont imputables
  is_active   boolean NOT NULL DEFAULT true,
  UNIQUE (org_id, plan_id, code)
);
```

**Pourquoi quatre emplacements fixes et non une table d'imputations variable.** Un modèle clé-valeur serait plus souple mais interdirait l'indexation efficace et les contraintes d'intégrité — or **chaque état agrège sur ces colonnes**. Les emplacements sont fixes dans le schéma ; **leur signification est configurable par organisation**. On obtient la souplesse métier sans payer le coût d'un modèle générique.

### 3.3 Le grand livre

```sql
CREATE TABLE journal_entry (
  id uuid PRIMARY KEY, org_id uuid NOT NULL, project_id uuid NOT NULL,
  fiscal_year_id uuid NOT NULL, period_id uuid NOT NULL,
  journal_id uuid NOT NULL,
  number text,                    -- attribué à la comptabilisation, SANS TROU
  accounting_date date NOT NULL, document_date date, document_ref text,
  label text NOT NULL,
  status text NOT NULL CHECK (status IN ('draft','validated','posted','locked')),
  currency_id uuid NOT NULL, fx_rate numeric(20,10) NOT NULL DEFAULT 1,
  origin text NOT NULL,           -- saisie | import | offline | reversal | module
  origin_module text, origin_ref uuid, idempotency_key text,
  posted_at timestamptz, posted_by uuid,
  reverses_id uuid REFERENCES journal_entry,
  UNIQUE (org_id, journal_id, fiscal_year_id, number),
  UNIQUE (org_id, idempotency_key)
);

CREATE TABLE journal_entry_line (
  id uuid PRIMARY KEY, org_id uuid NOT NULL, project_id uuid NOT NULL,
  entry_id uuid NOT NULL REFERENCES journal_entry ON DELETE CASCADE,
  line_no smallint NOT NULL,

  account_id uuid NOT NULL REFERENCES account,
  partner_id uuid REFERENCES partner,                 -- tiers / bénéficiaire

  dim1_id uuid, dim2_id uuid, dim3_id uuid, dim4_id uuid,   -- axes de gestion
  aux1_id uuid, aux2_id uuid, aux3_id uuid, aux4_id uuid,   -- axes auxiliaires

  site_id        uuid REFERENCES site,                -- unité d'exécution
  agreement_id   uuid REFERENCES funding_agreement,   -- accord de financement
  category_id    uuid REFERENCES funding_category,    -- catégorie de dépenses
  contract_id    uuid REFERENCES contract,            -- marché / contrat
  bank_account_id uuid REFERENCES bank_account,
  cofunding_key_version_id uuid REFERENCES cofunding_key_version,

  debit  numeric(20,4) NOT NULL DEFAULT 0 CHECK (debit  >= 0),   -- monnaie de tenue
  credit numeric(20,4) NOT NULL DEFAULT 0 CHECK (credit >= 0),
  currency_id uuid NOT NULL, fx_rate numeric(20,10) NOT NULL,    -- devise d'origine
  debit_cur  numeric(20,4) NOT NULL DEFAULT 0,
  credit_cur numeric(20,4) NOT NULL DEFAULT 0,

  reconciliation_id uuid, bank_match_id uuid, label text,
  CHECK (debit = 0 OR credit = 0)
);
```

### 3.4 Les quatre contraintes qui ne se négocient pas

**1 — Une écriture est équilibrée.** Contrainte différée, vérifiée à la validation de la transaction :

```sql
CREATE CONSTRAINT TRIGGER trg_entry_balanced
  AFTER INSERT OR UPDATE OR DELETE ON journal_entry_line
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION assert_entry_balanced();
-- SUM(debit) = SUM(credit) sur l'écriture, en monnaie de tenue
```

**2 — Une écriture comptabilisée est immuable.** Déclencheur `BEFORE UPDATE OR DELETE` rejetant toute modification dès que `status IN ('posted','locked')`, **doublé du retrait des droits `UPDATE` et `DELETE`** au rôle applicatif. Correction exclusivement par contre-passation (`reverses_id`).

**3 — La numérotation est sans trou.** Une séquence PostgreSQL produit des trous en cas d'annulation de transaction, ce qu'un auditeur refuse. On utilise un **compteur par journal et par exercice**, incrémenté sous `pg_advisory_xact_lock`, **au moment de la comptabilisation seulement** — jamais à la création du brouillon.

**4 — Une période close est inviolable.** Déclencheur vérifiant le statut de la période à chaque insertion ou modification. Aucune écriture rétroactive, aucune exception administrateur.

### 3.5 Cofinancement — l'arithmétique

```sql
CREATE TABLE cofunding_key_version (
  id uuid PRIMARY KEY, org_id uuid NOT NULL,
  key_id uuid NOT NULL, version int NOT NULL,
  valid_from date NOT NULL, valid_to date,
  rounding_residual_agreement_id uuid NOT NULL   -- qui porte le reliquat
);
CREATE TABLE cofunding_key_share (
  version_id uuid REFERENCES cofunding_key_version,
  agreement_id uuid NOT NULL, category_id uuid,
  share numeric(9,6) NOT NULL CHECK (share > 0)  -- Σ = 1.000000, vérifié
);
```

**Algorithme déterministe :**
1. `montant × part` pour chaque accord, arrondi au centième inférieur.
2. Reliquat = `montant − Σ des parts arrondies`.
3. Reliquat affecté **intégralement** à l'accord désigné dans la version de clé.
4. **`cofunding_key_version_id` persisté sur chaque ligne produite.**

Le point 4 est ce qui permet, trois ans plus tard, de reconstituer la répartition telle qu'elle était au jour de l'écriture. Sans lui, toute modification ultérieure d'une clé rend l'historique inexplicable — et l'audit impossible.

### 3.6 Journal d'audit infalsifiable

```sql
CREATE TABLE audit_log (
  id bigserial PRIMARY KEY, org_id uuid NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor_id uuid NOT NULL, actor_ip inet,
  action text NOT NULL,       -- create|update|post|reverse|publish|export|read|login
  object_type text NOT NULL, object_id uuid, project_id uuid,
  before jsonb, after jsonb,
  prev_hash bytea, hash bytea NOT NULL   -- SHA-256(prev_hash || contenu)
);
```

**En ajout seul** : les droits `UPDATE` et `DELETE` ne sont accordés à personne, pas même au rôle applicatif. Le **chaînage par empreinte** rend toute altération détectable, y compris par un administrateur de base. C'est ce qui rend le journal opposable à un auditeur externe.

Les **accès en lecture** aux données de tiers et les **exports** y sont également consignés — exigence de protection des données personnelles.

---

## 4. MODÈLE DE DONNÉES — REGISTRE DES EXIGENCES

C'est la pièce qui distingue le produit. Elle doit être traitée comme une structure de premier rang, pas comme une table de documentation.

```sql
CREATE TABLE reference_document (
  id uuid PRIMARY KEY, org_id uuid NOT NULL, project_id uuid NOT NULL,
  kind text NOT NULL,          -- financing_agreement | dfil | implementation_manual
                               -- | awp_budget | report_template | instruction
  title text NOT NULL, version text, issued_on date,
  file_ref text NOT NULL,      -- stockage objet
  sha256 bytea NOT NULL,       -- le document cité est exactement celui-ci
  superseded_by uuid REFERENCES reference_document
);

CREATE TABLE requirement (
  id uuid PRIMARY KEY, org_id uuid NOT NULL, project_id uuid NOT NULL,
  code text NOT NULL,                       -- stable dans le temps
  donor_profile_id uuid REFERENCES donor_profile,   -- origine bibliothèque, si applicable

  -- Source documentaire : l'attribut qui fait toute la valeur
  document_id uuid NOT NULL REFERENCES reference_document,
  citation jsonb NOT NULL,     -- { "annex":"2", "page":37, "paragraph":"4.2",
                               --   "quote":"…texte exact…" }

  subject text NOT NULL,                    -- rubrique ou information à produire
  rule jsonb NOT NULL,                      -- calcul, agrégation, filtre, présentation
  periodicity text,                         -- monthly|quarterly|semiannual|annual|event
  due_offset_days int,                      -- ex. 45 jours après la fin de période
  obligation text NOT NULL
      CHECK (obligation IN ('mandatory','conditional','optional')),
  condition_expr text,                      -- si conditionnel

  valid_from date NOT NULL, valid_to date, version int NOT NULL,
  status text NOT NULL
      CHECK (status IN ('proposed','validated','active','superseded','rejected')),
  source text NOT NULL CHECK (source IN ('manual','assisted')),
  confidence numeric(4,3),                  -- si proposée par l'assistant
  validated_by uuid, validated_at timestamptz,
  UNIQUE (org_id, project_id, code, version)
);

-- Tout objet de configuration se rattache à l'exigence qui le justifie.
CREATE TABLE requirement_binding (
  requirement_id uuid NOT NULL REFERENCES requirement,
  target_type text NOT NULL,   -- report_template | report_row | mapping | control | field
  target_id uuid NOT NULL,
  PRIMARY KEY (requirement_id, target_type, target_id)
);
```

**La règle qui donne sa valeur au modèle :** tout objet de configuration actif — rubrique de rapport, mapping, contrôle, périodicité — **doit** posséder au moins un `requirement_binding`. Un objet actif sans exigence source est signalé par le système comme anomalie de configuration.

C'est ce qui rend le **dossier de conformité** (§6) générable automatiquement, et ce qui empêche la configuration de redevenir une boîte noire.

---

## 5. MOTEUR DE MAPPING ET D'ÉTATS

### 5.1 Mapping

```sql
CREATE TABLE mapping_table (
  id uuid PRIMARY KEY, org_id uuid NOT NULL, project_id uuid,
  donor_profile_id uuid NOT NULL, code text NOT NULL,
  version int NOT NULL, valid_from date NOT NULL, valid_to date,
  status text CHECK (status IN ('draft','validated','active','superseded')),
  validated_by uuid, validated_at timestamptz
);

CREATE TABLE mapping_rule (
  id uuid PRIMARY KEY, table_id uuid NOT NULL REFERENCES mapping_table,
  priority int NOT NULL,                 -- la première règle qui correspond gagne
  match jsonb NOT NULL,                  -- { "accounts": [["60","62"]],
                                         --   "dim1": ["COMP-A"], "agreement": "..." }
  target_code text NOT NULL,             -- rubrique du bailleur
  condition_expr text                    -- mapping conditionnel
);
```

**Contrôle d'exhaustivité, obligatoire avant toute génération :** tout compte mouvementé sur la période, non couvert par une règle active, **bloque la génération et est nommé**. C'est ce qui évite la dépense qui disparaît silencieusement d'un rapport — l'erreur la plus coûteuse de ce métier.

### 5.2 Modèle d'état

Un état est un document JSONB versionné, exportable tel quel :

```jsonc
{
  "code": "IFR-1A", "version": 3, "valid_from": "2026-01-01",
  "label": { "fr": "Rapport financier intermédiaire — Emplois et ressources",
             "en": "Interim Financial Report — Sources and Uses" },
  "requirements": ["REQ-0042", "REQ-0043"],
  "columns": [
    { "code": "QTR",   "period": "current_quarter" },
    { "code": "YTD",   "period": "year_to_date" },
    { "code": "CUMUL", "period": "inception_to_date" }
  ],
  "rows": [
    { "code": "R100", "type": "heading",
      "label": { "fr": "RESSOURCES", "en": "SOURCES OF FUNDS" } },
    { "code": "R110", "type": "aggregate",
      "label": { "fr": "Fonds reçus du bailleur" },
      "select": { "mapping": "WB-IFR-1A", "target": "FUNDS_RECEIVED",
                  "filters": { "agreement": "$param.agreement" } } },
    { "code": "R190", "type": "computed", "formula": "SUM(R110:R180)" },
    { "code": "R900", "type": "computed", "formula": "R190 - R290",
      "assert": "R900 == BALANCE('5')" }
  ]
}
```

### 5.3 Chaîne d'évaluation

```
Modèle JSON + configuration active à la date d'effet
   └─▶ Analyse des formules ──▶ arbre syntaxique (langage restreint)
          └─▶ Graphe de dépendances ──▶ tri topologique
                 └─▶ Résolution des mappings ──▶ prédicats de sélection
                        └─▶ Compilation en UNE requête d'agrégation
                               └─▶ Évaluation des formules en Decimal, dans l'ordre
                                      └─▶ Assertions ──▶ publication ou blocage
                                             └─▶ SCELLEMENT
```

**Règles non négociables :**
- **Langage de formules restreint et analysé** : opérateurs arithmétiques, références de rubriques, plages (`R110:R180`), fonctions d'agrégation déclarées. **Jamais `eval`, jamais `exec`, jamais de SQL fourni par l'utilisateur.**
- **Un état produit une requête, pas N.**
- **Toute cellule d'agrégat conserve son prédicat**, ce qui permet de rejouer la sélection et d'afficher les écritures sous-jacentes.
- **Un état publié est figé** (§6).

### 5.4 Performance

| Mesure | Détail |
|---|---|
| **Index de couverture** | `(org_id, project_id, fiscal_year_id, account_id, dim1_id, agreement_id)` et variantes selon les axes réellement utilisés par les états livrés |
| **Partitionnement** | `journal_entry_line` partitionnée par `fiscal_year_id` au-delà de quelques millions de lignes |
| **Soldes pré-agrégés** | Table de soldes par compte × axes × période, maintenue transactionnellement à la comptabilisation, **et recalculable intégralement**. Une tâche nocturne recalcule et signale toute divergence. La traçabilité descendante retourne toujours aux lignes. |
| **Cibles** | Balance et TER sur un exercice de 200 000 écritures : **moins de 3 secondes**. Rapport financier intermédiaire complet : **moins de 10 secondes**. À mesurer dès L0, sur données générées. |

---

## 6. SCELLEMENT ET REPRODUCTIBILITÉ

```sql
CREATE TABLE published_report (
  id uuid PRIMARY KEY, org_id uuid NOT NULL, project_id uuid NOT NULL,
  template_id uuid NOT NULL, template_version int NOT NULL,
  period_from date NOT NULL, period_to date NOT NULL,
  params jsonb NOT NULL,              -- devise, périmètre, type de taux, langue
  config_version int NOT NULL,        -- version de configuration projet
  mapping_versions jsonb NOT NULL,    -- { "WB-IFR-1A": 3, ... }
  dataset_hash bytea NOT NULL,        -- empreinte des lignes retenues
  values jsonb NOT NULL,              -- valeurs figées, rubrique par rubrique
  files jsonb NOT NULL,               -- fichiers transmis + leurs empreintes
  seal bytea NOT NULL,                -- empreinte de l'ensemble
  published_at timestamptz NOT NULL, published_by uuid NOT NULL,
  transmitted_at timestamptz, transmitted_to text
);
```

**Régénération.** Rejouer un rapport scellé produit :
- soit un **résultat identique** — l'empreinte concorde ;
- soit un **écart expliqué** : le système compare les lignes retenues, les versions de mapping et les versions de configuration, et produit un **différentiel nommant la cause** (écriture ajoutée ou contre-passée, mapping modifié, exigence révisée) et son montant.

**C'est la seule façon de tenir l'exigence « les rapports historiques restent reproductibles ».** Un système qui se contente de régénérer à la demande ne la tient pas : il produit silencieusement un autre chiffre.

**Dossier de conformité.** Généré depuis `published_report` joint à `requirement_binding` et `requirement` : pour chaque rubrique, l'exigence satisfaite, sa citation documentaire exacte, la règle appliquée, le validateur. Exporté en PDF, scellé avec le rapport.

---

## 7. ASSISTANT D'EXTRACTION — ARCHITECTURE ET GARDE-FOUS

Module **optionnel**, activable par organisation. Le produit fonctionne intégralement sans lui.

```
Document de référence (PDF)
   └─▶ Extraction du texte avec repères de page et de paragraphe
          └─▶ Segmentation en passages candidats
                 └─▶ Analyse ──▶ exigences PROPOSÉES
                        │         (libellé, règle pressentie, périodicité,
                        │          CITATION EXACTE page + paragraphe, confiance)
                        └─▶ File de validation humaine
                               ├── acceptée ──▶ requirement (status 'validated')
                               ├── modifiée ──▶ requirement (status 'validated')
                               └── rejetée  ──▶ conservée, status 'rejected'
```

| Garde-fou | Mise en œuvre technique |
|---|---|
| **Aucune activation automatique** | `status` ne peut jamais passer de `proposed` à `active` sans passer par `validated`, et la transition exige `validated_by` non nul. Contrainte en base, pas règle applicative. |
| **Citation obligatoire** | `citation` est `NOT NULL` et doit contenir un extrait littéral retrouvable dans le document, vérifié à l'enregistrement. |
| **Document figé** | `reference_document.sha256` garantit que la citation renvoie exactement au document analysé. |
| **Traçabilité de l'origine** | `source = 'assisted'` et `confidence` persistés à vie, visibles dans le dossier de conformité. |
| **Confidentialité** | Aucun document de projet ne quitte l'environnement de l'organisation sans **consentement explicite, journalisé, révocable**. En hébergement souverain, traitement entièrement local ou module désactivé. |
| **Réversibilité** | Le registre reste intégralement créable et modifiable à la main. |

> L'assistant fait gagner des jours de lecture. **Il ne décide rien.** Une exigence mal lue produit un rapport faux, et le rapport faux engage l'UGP, pas l'outil.

---

## 8. SÉCURITÉ

| Domaine | Mise en œuvre |
|---|---|
| **Authentification** | OIDC ; **double authentification obligatoire** pour validation, comptabilisation, publication et paramétrage. Sessions courtes, jetons révocables. |
| **Autorisation** | Rôles par organisation ; droits par **projet × site × opération** (consulter, saisir, valider, comptabiliser, paramétrer, exporter, publier). Contrôle au serveur sur chaque requête — l'interface masque, elle ne protège pas. |
| **Séparation des tâches** | Un même utilisateur ne peut pas saisir **et** valider la même pièce. Paramétrable, **activé par défaut**. |
| **Isolation** | RLS PostgreSQL sur `org_id` (§2.1). `app.org_id` dérivé du jeton, jamais d'un paramètre client. Test automatisé de tentative d'accès croisé sur **chaque** table. |
| **Accès auditeur** | Jeton à portée et durée limitées : projets nommés, plage de périodes, lecture seule, expiration automatique. Chaque consultation et chaque export journalisés et visibles par l'organisation. |
| **Chiffrement** | TLS en transit ; chiffrement au repos des volumes, du stockage objet et des sauvegardes. |
| **Pièces justificatives** | Type vérifié, taille bornée, analyse antivirale, stockage objet hors du serveur applicatif, accès par lien signé à durée limitée. |
| **Secrets** | Jamais en dépôt ni en variable d'image ; coffre dédié. |
| **Dépendances** | Analyse de vulnérabilités en intégration continue ; délai de correction défini contractuellement. |

---

## 9. EXPLOITATION

### 9.1 Mode hors ligne

Périmètre strictement borné : **la capture de pièces, et rien d'autre.**

```
Poste en antenne, sans réseau
├── Référentiels en cache local : comptes, tiers, axes, accords, catégories
├── Saisie ──▶ file locale, chaque pièce portant une CLÉ D'IDEMPOTENCE
└── Retour du réseau
       └─▶ envoi séquentiel ──▶ écritures créées en « brouillon »
              ├── clé déjà vue ──▶ ignorée, aucun doublon (contrainte UNIQUE)
              └── référentiel obsolète ──▶ rejet, motif affiché, correction locale
```

**Jamais délégué au client :** numérotation, validation, contrôle budgétaire, comptabilisation. Une pièce capturée hors ligne entre toujours en `brouillon`.

### 9.2 Sauvegarde et restauration

PostgreSQL managé avec **restauration à un instant donné**, rétention 30 jours minimum · **export logique quotidien par organisation**, chiffré, conservé séparément · **restauration testée chaque trimestre** sur environnement distinct, chronométrée et consignée.

> Une sauvegarde jamais restaurée n'est pas une sauvegarde.

### 9.3 Hébergement souverain

Installation chez le client ou sur infrastructure nationale, **sans divergence de code** :
conteneurs avec PostgreSQL inclus · **un schéma unique par installation** — c'est le cas où le schéma par organisation devient le bon choix · mises à jour par image versionnée, migrations idempotentes, retour arrière documenté · **aucune dépendance à un service en ligne de l'éditeur pour fonctionner**, uniquement pour les paquets réglementaires, eux-mêmes téléchargeables hors ligne.

### 9.4 Profil « couche reporting seule »

Même code, socle comptable désactivé. Les écritures proviennent d'un **import normalisé** depuis le grand livre existant, selon le même format que la chaîne de reprise.

Conséquences techniques : l'import doit être **idempotent et rejouable** ; les écritures importées sont marquées `origin = 'import'` et non modifiables ; les contrôles d'exhaustivité du mapping s'appliquent à l'identique. Le passage ultérieur à la plateforme complète ne demande **aucune reprise** : les données sont déjà en place.

### 9.5 Paquets réglementaires

Un paquet — plan de comptes, modèles d'états, contrôles, règles de clôture — est **versionné et daté**. Son application :
1. ne modifie **jamais** un exercice clos ;
2. prend effet à une date choisie par l'organisation ;
3. préserve les adaptations locales : un modèle dupliqué par le client reçoit les mises à jour de son original sous forme de **proposition**, jamais d'écrasement.

### 9.6 Observabilité

Journaux structurés corrélés par requête, organisation et projet · métriques : latence par point d'entrée, durée de génération des états, profondeur de la file de tâches, divergences de soldes pré-agrégés, échecs de synchronisation hors ligne · **alertes sur toute divergence d'intégrité**.

---

## 10. INTERNATIONALISATION

| Exigence | Mise en œuvre |
|---|---|
| **Droite-à-gauche dès l'origine** | Mise en page logique (propriétés `inline-start`/`inline-end`), jamais `left`/`right` codés en dur. Moteur PDF gérant nativement le RTL. **Vérifié par un test de rendu en pseudo-locale RTL dès L0**, bien avant toute traduction arabe. |
| **Libellés multilingues** | `JSONB` partout, jamais de colonnes par langue. |
| **Langue de sortie d'un rapport** | **Paramètre de génération**, persisté dans `published_report.params`. Une UGP francophone produit un rapport en anglais pour son bailleur, à partir du même modèle et des mêmes données. |
| **Formats** | Date, nombre, devise et séparateurs localisés, indépendamment de la langue d'interface. |
| **Paquet de langue** | L'arabe s'ajoute comme paquet, sans modification du code. |

> Le rétrofit du droite-à-gauche coûte cher et touche toute l'interface. Sa prise en compte en amont coûte peu. C'est la raison pour laquelle la décision D-04 se prend maintenant et pas plus tard.

---

## 11. QUALITÉ ET TESTS

Sur un produit comptable, la stratégie de test fait partie de l'architecture.

| Niveau | Contenu |
|---|---|
| **Propriétés monétaires** | Tests de propriété : une ventilation de cofinancement conserve toujours le total exact ; une conversion aller-retour ne crée ni ne détruit de montant ; **aucune opération monétaire ne passe par un flottant** (vérifié par analyse statique). |
| **États de référence** | Chaque modèle livré a un jeu de données figé et un **résultat attendu versionné**. Toute modification du moteur qui change un chiffre fait échouer la construction. C'est la garantie de non-régression du reporting bailleur. |
| **Reproductibilité** | Un rapport scellé, régénéré, rend soit l'identique, soit un différentiel correct. Testé automatiquement sur un corpus de rapports historiques. |
| **Intégrité du grand livre** | Vérification continue : écritures équilibrées, aucune écriture comptabilisée modifiée, **aucun trou de numérotation**, soldes pré-agrégés égaux au recalcul complet. |
| **Isolation** | Test automatisé tentant, **pour chaque table**, de lire les données d'une autre organisation. Échec attendu, systématiquement. |
| **Exhaustivité du mapping** | Un compte mouvementé non mappé bloque la génération et est nommé. |
| **Charge** | Jeux générés à 10⁴, 10⁵ et 10⁶ écritures ; temps de balance, de TER, de rapport financier intermédiaire et de clôture ; 25 utilisateurs en saisie concurrente. |
| **Connectivité dégradée** | Parcours de saisie mesuré sur lien bridé et matériel modeste ; poids des pages borné en critère de recette. |
| **Reprise** | Rejeu d'une migration de référence, critère d'**écart nul**. |

---

## 12. DÉCISIONS D'ARCHITECTURE

| # | Décision | Alternative écartée | Coût d'un retour arrière |
|---|---|---|---|
| **D1** | PostgreSQL | MySQL, NoSQL | Prohibitif |
| **D2** | Django / Python | NestJS / TypeScript | **Faible jusqu'au début de L3**, élevé ensuite |
| **D3** | Monolithe modulaire | Microservices | Faible — la modularité permet d'extraire plus tard |
| **D4** | Organisation isolée par RLS, projet par habilitation applicative | RLS sur le projet, schéma par organisation | Moyen |
| **D5** | Quatre emplacements d'axes fixes, configurables | Imputations clé-valeur | Élevé |
| **D6** | Mapping en couche distincte et versionnée | Mapping intégré au modèle d'état | Élevé |
| **D7** | Registre des exigences comme unité de configuration | Configuration libre, documentation à côté | **Très élevé** — c'est le différenciateur |
| **D8** | Rapports scellés, régénération par différentiel | Régénération à la demande | Moyen |
| **D9** | États compilés en SQL, formules en langage restreint | Évaluation en mémoire, formules libres | Moyen |
| **D10** | Hors ligne limité à la capture | Réplication bidirectionnelle | Faible — c'est une restriction, pas un engagement |
| **D11** | Numérotation sans trou par compteur verrouillé | Séquence PostgreSQL | Faible |
| **D12** | Journal d'audit en ajout seul, chaîné | Journal modifiable | Moyen |
| **D13** | Droite-à-gauche pris en compte dès l'origine | Ajout ultérieur | **Élevé** |
| **D14** | Assistant d'extraction optionnel, sans activation automatique | Extraction intégrée au flux nominal | Faible |
| **D15** | Export complet comme fonction produit et clause contractuelle | Export sur demande à l'éditeur | Faible techniquement — mais c'est l'engagement commercial central |

---

*Référence fonctionnelle : [`01_SPECIFICATION_FONCTIONNELLE.md`](01_SPECIFICATION_FONCTIONNELLE.md). Les constats sur les produits existants, et leurs sources, figurent en [`ANNEXE_A`](ANNEXE_A_VERIFICATION_FACTUELLE.md) et [`ANNEXE_B`](ANNEXE_B_REGISTRE_DES_SOURCES.md).*
