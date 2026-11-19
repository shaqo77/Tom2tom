# PLATEFORME INTÉGRÉE DE GESTION FINANCIÈRE ET DE REPORTING MULTI-BAILLEURS

## Spécification fonctionnelle

**Destinataire de référence :** Unité de Gestion de Projet — République de Djibouti
**Nature :** plateforme unique, multi-projets et multi-bailleurs, à socle commun et différences paramétrées
**Version :** 2.0 — 12 novembre 2026
**Remplace :** version 1.0 (spécification orientée modules)

**Documents liés :** [architecture technique](02_ARCHITECTURE_TECHNIQUE.md) · [analyse du produit de référence](ANNEXE_A_VERIFICATION_FACTUELLE.md) · [registre des sources](ANNEXE_B_REGISTRE_DES_SOURCES.md)

> **Principe directeur, repris du cahier des charges de l'UGP :**
> **Mutualiser les données et les traitements. Paramétrer les différences. Ne développer que les fonctionnalités réellement nouvelles.**

---

## 0. DÉCISIONS DE CADRAGE

Cette version intègre le cahier des charges de l'UGP et tranche les arbitrages restés ouverts. Les décisions sont listées ici pour être contestées explicitement si elles ne conviennent pas.

| # | Sujet | Décision | Motif |
|---|---|---|---|
| **D-01** | Structure du produit | **Architecture à quatre niveaux** : socle commun → profil bailleur → configuration projet → moteur de reporting | Adoptée du cahier des charges de l'UGP. Supérieure au découpage par modules : elle sépare ce qui est universel de ce qui varie, donc ce qu'on écrit de ce qu'on paramètre. |
| **D-02** | Référentiel comptable de la v1 | **Plan Comptable Général de Djibouti (2012)** + **plan projet générique**. SYSCOHADA et SYCEBNL deviennent des paquets d'expansion. | **Djibouti n'est pas État membre de l'OHADA.** La version 1.0 de cette spécification en faisait son différenciateur principal : c'était une erreur de contexte. |
| **D-03** | Entités de premier rang | **Organisation ET projet**, tous deux de premier rang | Le cahier des charges exige une « séparation des données et habilitations par organisation et projet ». Le projet n'est pas une simple dimension d'imputation. |
| **D-04** | Multilinguisme et écriture droite-à-gauche | **Interface et moteur d'états conçus pour le RTL dès l'origine. Français et anglais livrés en v1 ; arabe en paquet activable.** | Le support RTL ne peut pas être rétrofité à coût raisonnable ; sa prise en compte en amont coûte peu. La traduction arabe elle-même est différée. Djibouti a l'arabe pour langue officielle et aucun acteur de ce marché ne le propose. |
| **D-05** | Mode d'entrée commercial | **Deux profils de déploiement pris en charge dès la v1** : plateforme complète, ou **couche reporting seule** au-dessus d'un grand livre existant | Le cahier des charges prévoit déjà « l'intégration avec un logiciel comptable existant ». L'import d'écritures est de toute façon requis pour la reprise : le profil « couche reporting » coûte peu de plus et réduit fortement la friction d'adoption. |
| **D-06** | Assistant d'extraction des exigences | **Retenu, en module optionnel, avec garde-fous stricts** (§5.3) | Le cahier des charges le prévoit déjà en substance (§7.3 : « soumettre les exigences extraites automatiquement à la validation d'un responsable financier »). Il fait passer la configuration d'un projet de plusieurs semaines à quelques jours. |
| **D-07** | Périmètre exclu | Paie, RH, stocks, suivi-évaluation des indicateurs : **hors produit**, intégrés par interface | La prolifération de modules satellites chez le produit de référence est une faiblesse, pas un modèle. |
| **D-08** | Garanties de configuration par la base | Pas de chevauchement de versions actives (`EXCLUDE` sur `daterange`), immutabilité des tables enfants d'une version approuvée par déclencheur, intervalle de validité semi-ouvert `[du, au[` | Examen des dossiers « bailleurs et conventions » : ce qui n'est garanti que par le code applicatif finit par être contourné. Voir [`07_APPORTS_DOSSIERS_CONVENTIONS.md`](07_APPORTS_DOSSIERS_CONVENTIONS.md). |
| **D-09** | Réallocations et avenants | Objets propres (`Reallocation`, `AvenantAccord`), chacun créant une **version** du profil ; approbateur distinct du demandeur ; dérogations formelles qui ne réécrivent jamais le résultat d'un contrôle | Même source. La trace du transfert et de son approbation manquait ; le principe « une réallocation crée une version » est inchangé. |

---

## 1. POSITIONNEMENT

### 1.1 Le problème

Une unité de gestion de projets porte simultanément plusieurs financements, de plusieurs bailleurs, chacun avec ses exigences propres — fixées non par une norme générale du bailleur, mais par **les documents contractuels du projet** : accord de financement, lettre de décaissement et d'information financière (DFIL), manuel d'exécution, modèles de rapports annexés.

Les pratiques constatées sont de trois ordres, et toutes trois échouent :

| Pratique | Pourquoi elle échoue |
|---|---|
| **Une application par projet ou par bailleur** | Données dupliquées, écarts entre états, coût multiplié, aucune vision consolidée. |
| **Un progiciel unique, paramétré au cas par cas par un intégrateur** | Le paramétrage n'est ni documenté, ni portable, ni transmissible. Quand il est incomplet, les états sont refaits à la main. |
| **Un logiciel comptable et des classeurs Excel à côté** | Aucune traçabilité du montant publié jusqu'à l'écriture et à la pièce. |

**Le constat documenté le plus parlant** vient d'un audit de clôture d'un projet financé par la Banque mondiale `[SRC:audit:201:2022-02-22]` :

> *« L'UCP utilise un progiciel qui, de fait de problèmes de paramétrage, ne permet pas la préparation de l'état des emplois et ressources […] et le suivi budgétaire de manière automatique. »*
>
> *« Les états financiers annuels du Projet sont élaborés manuellement en fichier Excel, après retraitement des balances et d'autres états extraits du logiciel. »*

Le progiciel n'était pas en cause en tant que tel : **son paramétrage l'était, et personne ne pouvait dire pourquoi il était ainsi.** C'est ce point précis que la plateforme attaque.

### 1.2 Les trois artefacts décisifs

La supériorité ne se joue pas sur le nombre de fonctions. Elle se joue sur **ce que le client peut produire devant son auditeur et son bailleur**. Trois artefacts, qu'aucun produit de ce marché ne fournit aujourd'hui :

#### A — Le dossier de conformité traçable

Chaque rapport publié est accompagné d'un document annexe qui liste, rubrique par rubrique : **l'exigence satisfaite**, **sa source documentaire exacte** (DFIL §4.2, accord art. 12, manuel p. 37), la règle de traitement appliquée, la version de configuration en vigueur et le responsable qui l'a validée.

L'auditeur ne reçoit pas seulement des chiffres : il reçoit **leur justification normative**. Le paramétrage cesse d'être une boîte noire.

#### B — Le rapport scellé et reproductible

Tout rapport publié est scellé : empreinte du jeu de données, version du modèle, version des mappings, paramètres de génération, horodatage, signataire. Le régénérer ultérieurement produit **soit un résultat identique, soit un écart expliqué ligne à ligne avec sa cause**.

C'est la réponse au reproche d'audit le plus destructeur du secteur : des chiffres publiés qu'on ne sait pas re-dériver.

#### C — L'accès auditeur et bailleur

Un accès en lecture seule, **limité dans le temps et dans le périmètre**, pour l'auditeur externe et le spécialiste en gestion financière du bailleur. Il descend d'une cellule d'état jusqu'à l'écriture, puis jusqu'à la pièce justificative scannée. Chaque consultation est journalisée.

L'audit passe d'un exercice d'extraction de plusieurs semaines à du libre-service. Effet secondaire recherché : **le cabinet d'audit devient prescripteur** auprès des autres unités de gestion qu'il audite.

### 1.3 Ce que le produit ne fait pas

Paie et gestion du personnel · gestion de stocks · suivi-évaluation des indicateurs et cadre logique · gestion électronique de documents généraliste · passation de marchés en tant que plateforme d'appel d'offres.

La plateforme **s'y connecte** par interface documentée. Elle ne les remplace pas.

---

## 2. ARCHITECTURE FONCTIONNELLE À QUATRE NIVEAUX

```
┌──────────────────────────────────────────────────────────────────────┐
│  NIVEAU 4 — MOTEUR DE MAPPING ET DE REPORTING                        │
│  Correspondances · calculs · contrôles · génération · scellement     │
│  Produit N présentations à partir des MÊMES données.                 │
├──────────────────────────────────────────────────────────────────────┤
│  NIVEAU 3 — CONFIGURATION DU PROJET                                  │
│  Documents de référence · REGISTRE DES EXIGENCES · activation        │
│  Ce que CE projet-ci doit produire, et en vertu de quel paragraphe.  │
├──────────────────────────────────────────────────────────────────────┤
│  NIVEAU 2 — PROFIL DU BAILLEUR                                       │
│  Bibliothèque d'exigences possibles · modèles · règles · contrôles   │
│  Réutilisable entre projets. N'impose rien automatiquement.          │
├──────────────────────────────────────────────────────────────────────┤
│  NIVEAU 1 — SOCLE COMMUN                                             │
│  Comptabilité · budget · financements · trésorerie · marchés ·       │
│  documents · référentiel analytique · habilitations                  │
│  Noyau stable, identique pour tous les projets et tous les bailleurs.│
└──────────────────────────────────────────────────────────────────────┘
```

**La règle qui fait tenir l'ensemble :** un nouveau projet, un nouveau bailleur ou un nouveau modèle de rapport s'ajoute **par paramétrage des niveaux 2, 3 et 4**. Le niveau 1 ne bouge pas. Si une demande client impose de modifier le niveau 1, c'est soit un vrai manque du socle — à traiter comme tel — soit une erreur de conception du paramétrage.

### 2.1 Un seul découpage, lu de deux façons

Un découpage en trois niveaux est souvent proposé pour ce métier — référentiel du bailleur, configuration du projet, exécution opérationnelle. **Il ne s'oppose pas à celui-ci : c'est le même axe, vu depuis la convention de financement.**

| Découpage « conventions » | Niveau correspondant ici |
|---|---|
| **1. Référentiel du bailleur** — règles générales Banque mondiale, BAD, FIDA, Union européenne | **Niveau 2 — Profil du bailleur** |
| **2. Configuration du projet** — accord, catégories, taux, devises, comptes, méthodes de décaissement, seuils, formulaires, conditions particulières | **Niveau 3 — Configuration du projet**, dont le **profil de décaissement** (§5.3) |
| **3. Exécution opérationnelle** — comptabilisation, contrôle des dépenses, DRF et paiements directs, rapprochements, justificatifs, rapports, audits | **Niveau 1 (socle) + Niveau 4 (reporting)**, en fonctionnement |

> **Décision : ne pas introduire un second vocabulaire.** Deux modèles pour une même structure, c'est deux fois le coût de compréhension et une source permanente de malentendus entre spécification et code. Le découpage en quatre niveaux est conservé, et le **profil de décaissement** lui donne ce qui lui manquait côté conventions.

**Sens de circulation :**
- Le niveau 2 est une **bibliothèque d'exigences possibles**. Il ne s'applique jamais automatiquement.
- Le niveau 3 **active** celles qui s'appliquent au projet, chacune justifiée par un paragraphe d'un document contractuel.
- Le niveau 4 **exécute** ce que le niveau 3 a activé, sur les données du niveau 1.

---

## 3. NIVEAU 1 — SOCLE COMMUN

### 3.1 Organisations, projets, habilitations

**Organisation** : l'entité juridique qui exploite la plateforme (une UGP, un ministère, une ONG). C'est la frontière d'isolation des données.

**Projet** : entité de premier rang, pas une simple dimension. Il porte :
identification et code · dates de démarrage, de clôture et de dernier décaissement · accords de financement et bailleurs associés · unité d'exécution et responsables · exercices comptables ouverts · monnaie de tenue et devises autorisées · statut (`en préparation` → `actif` → `en clôture` → `clôturé`) · documents de référence · configuration et registre des exigences.

**Habilitations** : sur deux axes croisés — **par projet** et **par site/unité d'exécution** — avec des droits par opération (consulter, saisir, valider, comptabiliser, paramétrer, exporter, publier un rapport).

**Séparation des tâches** activée par défaut : un même utilisateur ne peut pas saisir **et** valider la même pièce. C'est une exigence d'audit récurrente des bailleurs.

### 3.2 Référentiel analytique commun

Le cœur du socle. **Chaque opération est classée selon plusieurs dimensions, sans jamais dupliquer l'écriture comptable.**

| Dimension | Nature |
|---|---|
| **Projet** et unité d'exécution | Fixe |
| **Bailleur → accord → source de financement → catégorie de dépenses** | Hiérarchie fixe |
| **Composante → sous-composante → activité** | Hiérarchie, profondeur libre |
| **Ligne budgétaire** | Rattachée au budget actif |
| **Contrat ou marché** | Rattachement optionnel |
| **Compte bancaire** et **devise** | Fixe |
| **Période comptable** | Fixe |
| **Tiers / bénéficiaire** | Fixe |
| **Axes libres** | **4 axes de gestion** et **4 axes auxiliaires**, configurables par organisation |

**Extensibilité.** Les axes libres couvrent les besoins non anticipés (zone géographique, bénéficiaire final, genre, type de dépense, source de contrepartie). Leur signification est définie par organisation, pas codée en dur.

**Tables de correspondance.** Une table relie les codes internes aux **nomenclatures propres de chaque bailleur** et aux rubriques des modèles de reporting. C'est ce qui permet à un plan comptable unique de servir plusieurs bailleurs — voir §6.1.

> **Décision de conception fondatrice.** Une balance analytique, un suivi budgétaire par composante, un tableau d'utilisation des fonds par activité et un état certifié de dépenses par catégorie sont **quatre agrégations de la même table de lignes d'écriture**. Aucune ressaisie, aucun état parallèle, aucun écart possible entre deux restitutions.

### 3.3 Comptabilité générale, auxiliaire et analytique

- Plan comptable multi-exercices, adossé à un **paquet réglementaire** (§11) et adaptable.
- Journaux, tiers, schémas d'écritures prédéfinis, contrepartie automatique.
- **Bascule comptabilité de trésorerie ↔ comptabilité d'engagement**, paramétrable. La configuration réellement observée sur les projets de développement est une **comptabilité de trésorerie avec opérations d'engagement occasionnelles** `[SRC:audit:201]`.
- Grand livre, balances, journaux, lettrage et dé-lettrage.
- **Restitutions analytiques** sur toute combinaison d'axes ; clés de répartition ; ventilation a posteriori (imputation secondaire).
- Immobilisations : fiches comptables et extracomptables, localisation, amortissements, **cofinancement en pourcentage**, cessions, inventaires.
- Exercices et périodes, clôtures mensuelles et annuelles, à-nouveaux.

**Cycle de vie d'une écriture :**

```
brouillon ──valider──▶ validée ──comptabiliser──▶ comptabilisée ──clôture──▶ verrouillée
    │                     │                            │
    └─ supprimable        └─ dévalidation tracée       └─ correction par CONTRE-PASSATION
```

Une écriture comptabilisée est **immuable**. Aucune modification rétroactive, jamais. Toute transition est journalisée : acteur, horodatage, valeurs avant et après.

### 3.4 Gestion budgétaire

- **Budget initial, révisions, réallocations** — chaque version datée, motivée, approuvée et conservée.
- Saisie sur **toute combinaison d'axes** et sur toute maille temporelle (annuelle, trimestrielle, mensuelle).
- Saisie possible dans **toute monnaie**, avec taux de budget distinct du taux comptable.
- **Disponible = budget notifié − engagements non apurés − réalisations comptabilisées.**
- Contrôle du disponible paramétrable **par axe** : `bloquant`, `avertissement` ou `inactif`. Certains bailleurs exigent le blocage, d'autres l'interdisent : la souplesse est obligatoire.
- Analyse des écarts, reliquats, taux d'exécution par composante, catégorie et source.

### 3.5 Financements et conventions

```
Bailleur ─▶ Accord (prêt | don | contrepartie) ─▶ Catégorie de dépenses ─▶ Sous-catégorie
              │                                      (plafond, devise, réallocations)
              ├─▶ Compte désigné (devise, banque, plafond, seuil de réapprovisionnement)
              └─▶ Fonds reçus · avances · justifications
```

- **Demandes de décaissement** : retrait, réapprovisionnement, paiement direct, engagement spécial. Les méthodes autorisées, leurs seuils et leurs pièces justificatives sont portés par le **profil de décaissement du projet** (§5.3), jamais codés en dur.
- **Taux de financement par catégorie** : `montant à retirer = dépense éligible × taux de la catégorie`. Le taux est versionné ; une réallocation ne recalcule jamais les demandes antérieures.
- Suivi des **avances non justifiées** et des délais de justification applicables.
- **Cofinancement** : une dépense ventilée entre plusieurs accords selon des pourcentages.

**Deux exigences non négociables sur le cofinancement :**
1. **La version de la clé appliquée est persistée sur chaque ligne produite.** Un auditeur doit pouvoir reconstituer la répartition telle qu'elle était au jour de l'écriture, même si la clé a changé depuis.
2. **Les arrondis sont déterministes** et le reliquat est affecté à un accord désigné dans la clé — jamais perdu, jamais dupliqué.

### 3.6 Trésorerie

Comptes désignés et comptes opérationnels · mouvements bancaires · **rapprochement bancaire en monnaie de tenue et en devise** · prévisions de trésorerie par période et par axe · disponibilités · **écarts de change** constatés en écritures explicites · état de reconstitution du compte désigné.

### 3.7 Achats, marchés et contrats

- **Plan de passation de marchés** : lignes prévisionnelles, méthodes, seuils, calendrier.
- **Avis de non-objection** : demande, pièces, statut, date de réception, blocage de l'engagement tant que l'avis requis n'est pas obtenu. *C'est un point de friction quotidien sur les projets Banque mondiale ; il appartient au socle, pas à une version ultérieure.*
- Contrats, avenants, garanties et assurances.
- Engagements, décomptes, factures, paiements, **apurement**, soldes contractuels.
- Taux d'exécution physique et financier.

### 3.8 Gestion documentaire

- Archivage des pièces justificatives, classement par **projet / opération / contrat / période / accord**.
- Référencement, versions, habilitations d'accès.
- **Détection des pièces manquantes** par rapport aux exigences configurées : une dépense destinée à un état certifié de dépenses sans sa pièce est signalée **avant** la production du rapport, pas après le rejet.
- Lien bidirectionnel : d'une écriture vers ses pièces, d'une pièce vers ses écritures.
- Journalisation des accès en lecture (exigence de protection des données personnelles, §19.2).

---

## 4. NIVEAU 2 — PROFILS DE BAILLEURS

Un profil est une **bibliothèque d'exigences possibles**, réutilisable entre projets. Il contient :

| Élément | Contenu |
|---|---|
| **Références documentaires** | Directives, manuels de gestion financière, guides de décaissement applicables, avec leur version |
| **Familles d'états** | Rapports financiers intermédiaires, états de ressources et emplois, dépenses par axe, activité et rapprochement du compte désigné, prévisions de trésorerie, demandes de retrait, états annuels |
| **Modèles de rapport** | Structure, rubriques, colonnes, regroupements, formules, formats |
| **Règles de présentation** | Devise, arrondis, signes, ordre des rubriques, mentions obligatoires |
| **Périodicités et délais types** | Par exemple : rapport financier intermédiaire trimestriel, dû sous 45 jours après la fin du trimestre civil `[SRC:bailleur:410]` |
| **Contrôles** | Vérifications propres au bailleur, avec leur niveau de sévérité |
| **Formats d'exportation** | Excel, PDF, et autres formats exigés |
| **Nomenclatures** | Catégories et rubriques propres au bailleur, cibles du mapping |

> **Règle absolue, reprise du cahier des charges de l'UGP :**
> **Un profil n'impose jamais automatiquement ses exigences à un projet.** Il les met à disposition. Ce sont les documents contractuels du projet — DFIL, accord, manuel d'exécution — qui déterminent lesquelles s'appliquent, avec quelle périodicité et selon quel modèle.
>
> Il n'existe pas de « modèle Banque mondiale universel ». Présenter un profil comme tel serait une erreur de conception **et** une faute commerciale.

**Profils livrés en v1 :** Banque mondiale · Banque africaine de développement · Union européenne · FIDA · Fonds mondial · BID · système des Nations unies.
**Ajout d'un profil :** opération de paramétrage, jamais de développement. C'est un critère de recette (§17).

---

## 5. NIVEAU 3 — CONFIGURATION DU PROJET ET REGISTRE DES EXIGENCES

C'est la couche qui distingue cette plateforme de tout ce qui existe sur ce marché.

### 5.1 Documents de référence

Chaque projet enregistre ses documents contractuels, **versionnés** : accord de financement et avenants · DFIL ou instructions de décaissement et d'information financière · manuel d'exécution · plan de travail et budget annuel · modèles de rapports et annexes · instructions complémentaires du bailleur.

Chaque document est archivé, horodaté, et **référençable au paragraphe près**.

### 5.2 Registre des exigences

Toute exigence applicable au projet y est enregistrée, avec :

| Attribut | Contenu |
|---|---|
| **Identifiant** | Code unique, stable dans le temps |
| **Source documentaire** | Document, version, annexe, page, paragraphe |
| **Rubrique concernée** | État ou information à produire |
| **Règle de traitement** | Calcul, agrégation, filtre, présentation attendue |
| **Périodicité et échéance** | Mensuelle, trimestrielle, semestrielle, annuelle, à l'événement |
| **Caractère** | Obligatoire · conditionnel (avec sa condition) · facultatif |
| **Contrôle associé** | Vérification à exécuter, et sa sévérité |
| **Date d'effet et version** | Période à partir de laquelle l'exigence s'applique |
| **Validation** | Responsable ayant approuvé, et date |

**Le registre est l'unité de configuration du produit.** Toute rubrique de rapport, tout contrôle, toute périodicité **dérive d'une exigence enregistrée**. Une configuration sans exigence source est une anomalie que le système signale.

C'est ce qui rend possible le **dossier de conformité traçable** (§1.2 A), et ce qui fait qu'une configuration survit au départ de celui qui l'a faite.

### 5.3 Profil de décaissement du projet

> **Le point le plus souvent sous-estimé de ce métier.** Les méthodes de décaissement et de retrait **varient d'un projet à l'autre, y compris chez un même bailleur à la même période**. Elles sont convenues en fonction du projet, des catégories de dépenses et de la **capacité de l'organisme d'exécution** — et elles peuvent changer **en cours de projet**.
>
> Preuve chiffrée : trois accords de financement de la Banque mondiale fixent le montant minimum de demande respectivement à **20 % du plafond du compte désigné**, à **100 000 USD** et à **200 000 USD**. Même bailleur, trois paramètres différents.
>
> Un produit qui câble les procédures par bailleur ne peut pas suivre cela. C'est précisément ce que fait le produit de référence : **158 pages de son manuel, soit 24 %, sont quatre procédures distinctes, une par bailleur** `[SRC:manuel:601]`.

Le profil de décaissement est l'objet qui porte ces paramètres. Il appartient au projet, pas au bailleur.

#### A — Régime de décaissement

Deux régimes, déterminés par l'évaluation de la capacité de gestion financière de l'organisme d'exécution :

| Régime | Base de justification |
|---|---|
| **Transactionnel** | Dépense par dépense — état certifié de dépenses, ou copies de pièces au-delà d'un seuil |
| **Sur rapport** | Rapport financier intermédiaire — l'avance est reconstituée sur prévisions, justifiée par l'IFR |

**Le régime peut changer en cours de projet**, dans les deux sens : une capacité renforcée fait passer au régime sur rapport, une faiblesse constatée ramène au transactionnel. Le changement porte une date d'effet et **ne modifie jamais les demandes déjà soumises**.

#### B — Méthodes de décaissement autorisées

Ensemble **fermé**, activable méthode par méthode :

| Méthode | Description |
|---|---|
| **Avance** | Versement sur compte désigné, reconstitué par justification |
| **Remboursement** | Remboursement de dépenses déjà payées sur ressources propres |
| **Paiement direct** | Paiement du bailleur directement au fournisseur, prestataire ou entrepreneur |
| **Engagement spécial** | Engagement du bailleur envers une banque, au titre d'une lettre de crédit |

Chaque méthode activée porte ses propres paramètres : pièces justificatives exigées, seuil de documentation complète, montant minimum de demande.

#### C — Paramètres par méthode

| Paramètre | Exemple |
|---|---|
| **Pièces exigées** | État certifié de dépenses · copies de pièces · rapport financier intermédiaire · relevé récapitulatif |
| **Seuil de documentation complète** | Au-delà de ce montant, les copies de pièces remplacent l'état certifié |
| **Montant minimum de demande** | Valeur fixe, **ou** pourcentage du plafond du compte désigné |
| **Pièces particulières** | Garantie bancaire pour une avance ou une retenue · lettre de crédit avec date de validité pour un engagement spécial |

#### D — Comptes désignés

Devise · banque · type · **plafond fixe ou variable** · seuil de déclenchement du réapprovisionnement · méthodes de décaissement rattachées.

Un projet peut en avoir plusieurs — par exemple un par agence d'exécution, comme observé sur un projet audité à deux comptes spéciaux `[SRC:audit:201]`.

#### E — Catégories, allocations et taux de financement

C'est ici que se trouve **la règle de calcul qui manquait à cette spécification** :

```
Montant à retirer = Dépense éligible × Taux de financement de la catégorie
```

| Paramètre par catégorie | Rôle |
|---|---|
| **Allocation** | Plafond de la catégorie, dans la devise de l'accord |
| **Taux de financement** | Pourcentage de la dépense pris en charge — par exemple 100 % hors taxes, ou 80 % |
| **Assiette** | Montant hors taxes ou toutes taxes comprises |
| **Dates d'éligibilité** | Une dépense antérieure à la date d'éligibilité n'est pas finançable |
| **Conditions particulières** | Non-objection préalable requise, plafond par marché, zone éligible |

**Une réallocation modifie allocations et taux : elle crée une nouvelle version du profil, avec date d'effet.** Les demandes antérieures restent calculées aux taux alors en vigueur.

La réallocation est elle-même un **événement tracé** (catégorie source, catégorie cible, montant, demandeur, approbateur distinct, motif, document) qui produit cette version ; l'**avenant** à l'accord est de même un objet daté, lié au document signé et à la version qu'il crée. On peut ainsi afficher la situation d'un accord avant et après un avenant. Un accord peut être **suspendu** : il bloque alors toute nouvelle demande sans être clos.

#### F — Dates et bornes

Date de signature · date d'entrée en vigueur · date d'éligibilité des dépenses · date de clôture · **date limite de décaissement** (période de grâce après clôture, au-delà de laquelle plus aucune demande n'est recevable).

#### G — Versionnement : la réponse à « cela change en cours de projet »

**Toute modification du profil crée une version, avec date d'effet.** Avenant à l'accord, restructuration, changement de régime, révision du plafond, réallocation entre catégories : chacun est une version datée, rattachée à son document source et à son exigence.

Le mécanisme existe déjà et sert ici sans adaptation :

| Besoin | Mécanisme déjà spécifié |
|---|---|
| Retrouver les règles en vigueur à une date | Résolution de la configuration active à la date d'effet (§5.5) |
| Ne pas réécrire le passé | Scellement des rapports publiés (§6.3) |
| Savoir **pourquoi** une règle est ce qu'elle est | Rattachement à l'exigence et à sa citation documentaire (§5.2) |
| Expliquer un écart après coup | Régénération par différentiel (§6.3) |

#### H — Ce que le profil ne fait pas

**Le profil est un jeu de paramètres, pas un langage.** Les méthodes de décaissement forment un ensemble fermé ; on les active et on les paramètre, on ne les programme pas.

Toute demande visant à exprimer une règle qu'aucun paramètre ne couvre passe par les contrôles configurables (§7), jamais par du script. C'est la même discipline que pour le moteur d'états : sans cette limite, le produit devient un environnement de développement que vos clients écrivent et que vous déboguez à leur place.

### 5.4 Assistant d'extraction des exigences

**Module optionnel, activable par organisation.**

L'assistant lit les documents de référence et **propose** un projet de registre : pour chaque exigence détectée, un libellé, une règle de traitement pressentie, une périodicité, et **la citation exacte du passage source avec sa page et son paragraphe**.

**Garde-fous, non négociables :**

| Règle | Raison |
|---|---|
| **Aucune exigence n'est jamais activée automatiquement.** L'assistant propose ; un humain valide. | Une exigence mal lue produit un rapport faux, et le rapport faux engage l'UGP. |
| **Chaque proposition affiche sa citation source et son niveau de confiance.** | Le validateur doit pouvoir vérifier en trois secondes, pas relire le document. |
| **La validation est nominative, datée et tracée.** | C'est le responsable financier qui engage sa signature, pas l'outil. |
| **Le registre reste pleinement éditable et créable à la main.** | L'assistant est un accélérateur, jamais un passage obligé. |
| **Aucun document de projet ne sort de l'environnement de l'organisation sans consentement explicite et journalisé.** | Les accords de financement sont des documents sensibles. |
| **Le produit fonctionne intégralement sans ce module.** | Il ne doit jamais devenir une dépendance critique. |

**Gain visé :** faire passer la configuration d'un projet de plusieurs semaines à quelques jours. C'est précisément ce délai qui, aujourd'hui, fait renoncer les UGP et les ramène à Excel.

### 5.5 Activation, versionnement, date d'effet

- Activer ou désactiver états, rubriques, contrôles et champs **par projet**.
- Associer chaque paramètre à sa source documentaire.
- Conserver **toutes les versions** successives de la configuration.
- Appliquer un changement **à partir d'une date d'effet**, sans toucher au passé.
- **Préserver les rapports historiques avec la configuration utilisée lors de leur validation** — garanti techniquement par le scellement (§6.3).

### 5.6 Le guide de configuration généré

Le système produit automatiquement, depuis le registre, un **document lisible par un humain** : chaque exigence active, sa source, son mapping, ses contrôles, sa périodicité.

Les équipes d'UGP tournent constamment. **C'est là que meurent les installations concurrentes** : le savoir du paramétrage reste chez un consultant de l'intégrateur. Ici, il reste dans le système et s'imprime.

---

## 6. NIVEAU 4 — MOTEUR DE MAPPING ET DE REPORTING

### 6.1 Moteur de correspondances

Couche distincte, placée entre les données et la mise en forme.

```
Compte interne ─┐
Axe analytique ─┼─▶  TABLE DE MAPPING  ─▶  Rubrique du modèle de rapport
Catégorie      ─┤      (versionnée,              (propre au bailleur)
Source de fonds─┘       datée, validée)
```

- Un même plan comptable alimente **N nomenclatures de bailleurs** par N tables de mapping.
- Chaque mapping est **versionné, daté, validé**, et rattaché à son exigence source.
- **Contrôle d'exhaustivité** : tout compte mouvementé non couvert par un mapping actif est signalé avant la génération. C'est ce qui évite la dépense qui disparaît silencieusement d'un rapport.
- Un mapping peut être **conditionnel** (selon la source de financement, la composante ou la période).

C'est cette couche, et elle seule, qui permet de produire des rapports distincts à partir des mêmes données sources — donc d'éviter une application par bailleur.

### 6.2 Moteur d'états

Un état est un **arbre de rubriques**, chacune d'un des trois types :

| Type | Alimentation |
|---|---|
| **Titre** | Structure de présentation |
| **Agrégat** | Sélections de lignes d'écriture : fourchettes de comptes, filtres sur axes, accord, catégorie, site, période, sens — **ou** rubriques de mapping |
| **Calcul** | Formule référençant d'autres rubriques du même état : `R190 = SOMME(R110:R180)`, `R900 = R190 − R290` |

Chaque rubrique porte : code, libellé multilingue, format, signe, condition d'affichage, et éventuellement une **assertion de cohérence** (`R_TOTAL_ACTIF == R_TOTAL_PASSIF`).

**Exigences du moteur :**

1. **Langage de formules restreint et analysé.** Opérateurs arithmétiques, références de rubriques, plages, fonctions d'agrégation déclarées. **Jamais d'évaluation de code arbitraire, jamais de SQL fourni par l'utilisateur.** Sans cette limite, vous passerez vos journées à déboguer les formules de vos clients.
2. **Compilation en requêtes d'agrégation.** Un état entier se résout en une requête, pas en un parcours ligne à ligne.
3. **Sélection avant génération** : projet, bailleur, modèle, période, devise, niveau de détail, périmètre.
4. **Multidevise en sortie** : monnaie de tenue ou devise de reporting, avec le type de taux choisi.
5. **Traçabilité descendante sur toute cellule d'agrégat** : la liste des écritures, puis la pièce.
6. **Assertions bloquantes avant publication** : un état déséquilibré ne peut pas être marqué définitif.
7. **Export et import du modèle en JSON lisible** : le client possède ses modèles.

### 6.3 Scellement et reproductibilité

Tout rapport publié est **scellé** :

```
Rapport publié
├── Valeurs figées
├── Empreinte du jeu de données source
├── Version du modèle d'état
├── Version des mappings utilisés
├── Version de la configuration du projet
├── Paramètres de génération (période, devise, périmètre, taux)
├── Horodatage et signataire
└── Fichiers transmis (Excel, PDF) tels qu'envoyés
```

**Régénérer un rapport scellé produit soit un résultat identique, soit un écart expliqué** : le système indique quelle écriture, quel mapping ou quelle version de configuration a changé, et de combien.

C'est la mise en œuvre technique de l'exigence « les rapports historiques restent reproductibles », et l'un des trois artefacts décisifs (§1.2 B).

### 6.4 Bibliothèques livrées

**États communs :** balance, grand livre, journaux, budget et exécution, ressources reçues, dépenses par axe, trésorerie, rapprochement bancaire, avances, engagements et contrats.

**Modèles spécifiques par bailleur :** rapports financiers intermédiaires, états de ressources et emplois, dépenses par composante / activité / catégorie / source, activité et rapprochement du compte désigné, prévisions de trésorerie et suivi des avances, demandes de retrait et pièces associées, états annuels pour l'audit.

> **Terminologie imposée dans toute l'interface et toute la documentation.**
> **IFR / RFI** — rapport financier intermédiaire (*Interim Financial Report*) · **RSF** — rapport de suivi financier · **SOE / ECD** — état certifié de dépenses (*Statement of Expenditure*) · **DRF** — demande de retrait ou de réapprovisionnement de fonds · **compte désigné** (*Designated Account*) · **TER** — tableau des emplois et ressources · **DFIL** — lettre de décaissement et d'information financière.
>
> Le sigle « IPFR » n'existe dans la terminologie d'aucun bailleur et ne doit jamais apparaître.

---

## 7. CONTRÔLES DE CONFORMITÉ

Configurables, rattachés à une exigence, et classés en **trois niveaux : bloquant · avertissement · information**.

**Bibliothèque livrée :**

| Famille | Contrôles |
|---|---|
| **Codification** | Dépense sans catégorie, sans source de financement, sans composante ou sans axe obligatoire |
| **Budget** | Dépassement de ligne, de catégorie, d'allocation disponible ou de plafond d'accord |
| **Pièces** | Doublon de facture ou de pièce ; pièce manquante pour une dépense destinée à un état certifié |
| **Trésorerie** | Écart de rapprochement non justifié ; solde du compte désigné incohérent avec l'état de reconstitution |
| **Avances** | Avance non justifiée, ou au-delà du délai applicable |
| **Rapport** | Rubrique obligatoire non renseignée ; compte mouvementé non couvert par un mapping ; assertion de cohérence non vérifiée |
| **Cohérence** | Incohérence entre états d'une même période ; incohérence entre deux périodes successives ; rupture de cumul |
| **Éligibilité** | Dépense ne respectant pas les règles d'éligibilité configurées (nature, date, zone, bénéficiaire) |

**Résultats et dérogations.** Un contrôle rend `réussi`, `bloquant`, `avertissement`, `information` ou `à vérifier` (vérification humaine). Une **dérogation** est distincte d'une justification : elle autorise à poursuivre malgré un contrôle bloquant, pour un objet et une durée donnés, par un approbateur habilité autre que le demandeur, et **le résultat initial n'est jamais effacé**. Les conditions des contrôles sont structurées, à jeu d'opérateurs fermé (plan L6-T01) : jamais de SQL ni de script.

### 7.1 La simulation de revue bailleur

Au-delà des contrôles unitaires, un mode **pré-soumission** rejoue sur le rapport en préparation les **motifs de rejet connus du bailleur**, et rend un **avis go / no-go assorti d'une liste d'actions**.

**Indicateur phare du produit : le taux de rapports acceptés au premier envoi.** Mesurable, affiché, et invérifiable chez les concurrents.

---

## 8. WORKFLOW, CALENDRIER ET ARCHIVAGE

### 8.1 Circuit de production

```
1. Extraire les données de la période
2. Générer le rapport selon la configuration ACTIVE à la date d'effet
3. Exécuter les contrôles automatiques
4. Corriger ou justifier chaque anomalie          ← justification tracée et conservée
5. Valider — responsable financier                ← signature nominative
6. Approuver — coordonnateur ou autorité habilitée
7. Exporter et transmettre
8. Archiver LA VERSION EFFECTIVEMENT TRANSMISE    ← scellée
```

Utilisateurs, horodatages, décisions, commentaires et versions sont conservés à chaque étape.

> **Le point 8 n'est pas un détail.** En audit, ce qui compte est ce qui a été envoyé, pas ce qu'on sait régénérer.

### 8.2 Calendrier des obligations

Généré **automatiquement depuis le registre des exigences** : chaque exigence périodique produit ses échéances, avec son délai.

- Les contrôles s'exécutent **avant l'échéance**, pas au moment de la génération.
- Alertes graduées, escalade au coordonnateur, relance.
- **L'écran d'accueil est un tableau d'échéances à feux de signalisation**, pas une arborescence de menus.

Le métier réel d'un responsable administratif et financier est de ne jamais rater une échéance et de ne jamais faire rejeter un rapport. Le produit doit être organisé autour de cela.

---

## 9. TABLEAU DE BORD MULTI-PROJETS

Projets actifs et bailleurs associés · budgets approuvés et révisés · financements reçus · dépenses et taux d'exécution, global et par composante · soldes bancaires et disponibilités · engagements et **avances non justifiées** · **échéances de reporting, rapports en attente, anomalies ouvertes** · taux d'acceptation au premier envoi.

Filtrage par projet, bailleur, période, organisation et unité d'exécution. Chaque indicateur est **cliquable jusqu'au détail**, puis jusqu'à l'écriture.

**Les devises ne se mélangent jamais en silence.** Les montants sont ventilés par devise ; une consolidation dans une devise de référence affiche la méthode, la date et le taux, ou n'est pas produite faute de taux.

---

## 10. ACCÈS AUDITEUR ET BAILLEUR

| Caractéristique | Règle |
|---|---|
| **Portée** | Lecture seule, limitée à un ou plusieurs projets et à une plage de périodes |
| **Durée** | Limitée dans le temps, avec expiration automatique |
| **Capacités** | Consultation des états publiés et scellés · traçabilité descendante jusqu'à l'écriture et à la pièce · consultation du dossier de conformité · export de son périmètre |
| **Interdits** | Aucune écriture, aucune modification de configuration, aucun accès aux autres projets |
| **Traçabilité** | Chaque consultation et chaque export sont journalisés et consultables par l'organisation |
| **Tarification** | **Sièges illimités et gratuits** |

---

## 11. RÉFÉRENTIELS COMPTABLES

Chaque référentiel est un **paquet versionné** — plan de comptes, modèles d'états, contrôles, règles de clôture — **maintenu par l'éditeur**, applicable à une date d'effet, **sans jamais modifier un exercice clos**.

| Paquet | Portée | Version |
|---|---|---|
| **Plan Comptable Général de Djibouti (2012)** | Référentiel national djiboutien, publié par le ministère de l'Économie et des Finances | **v1** |
| **Plan projet de développement** | Comptabilité de trésorerie avec engagements occasionnels, adaptée aux projets financés par des bailleurs. **C'est le référentiel réellement utilisé par les UGP**, indépendamment du plan national. | **v1** |
| **SYSCOHADA / AUDCIF** | Entités à but lucratif des 17 États de l'espace OHADA | Expansion |
| **SYCEBNL** | Entités à but non lucratif de l'espace OHADA. 11ᵉ acte uniforme, **en vigueur depuis le 1ᵉʳ janvier 2024**, avec registre des donateurs (art. 17) et bilan d'ouverture `[SRC:compta:407]` | Expansion |
| **PCG 2005 Madagascar** | Hors espace OHADA et hors OAPI | Expansion |

> **Djibouti n'est pas État membre de l'OHADA.** La version 1.0 de cette spécification faisait du SYCEBNL son différenciateur principal : c'était une erreur de contexte, corrigée ici. SYSCOHADA et SYCEBNL restent des paquets de forte valeur, mais pour le **marché d'expansion**.

**Pourquoi c'est la douve du produit.** Le produit de référence ne revendique la conformité à **aucun référentiel nommé** — « plan comptable adaptable à toute normalisation » `[SRC:editeur:001]`. La conformité est entièrement reportée sur le paramétrage du client. Porter cette maintenance réglementaire est coûteux et récurrent : c'est précisément pourquoi un concurrent qui refuse ce coût ne peut pas suivre.

Chaque paquet est validé par un expert-comptable du référentiel concerné avant publication.

---

## 12. MULTILINGUISME

- **Interface et moteur d'états conçus pour l'écriture droite-à-gauche dès l'origine** (décision D-04). Le rétrofit du RTL coûte cher ; sa prise en compte en amont coûte peu.
- **Français et anglais livrés en v1.** Arabe en paquet de langue activable.
- **Double libellé sur les référentiels** : chaque compte, axe, catégorie et rubrique porte ses libellés dans chaque langue active.
- **La langue de sortie d'un rapport est un paramètre de génération.** Une UGP travaillant en français doit pouvoir produire un rapport en anglais pour son bailleur, à partir du même modèle et des mêmes données.
- Formats de date, de nombre et de devise localisés.

---

## 13. CONNECTIVITÉ ET MODE HORS LIGNE

**Décision : en ligne d'abord, avec capture hors ligne strictement bornée.**

| Option | Verdict |
|---|---|
| Exiger une connexion permanente | **Rejeté** — irréaliste sur le terrain |
| Réplication bidirectionnelle du grand livre | **Rejeté** — sur une comptabilité à numérotation séquentielle et contrôle budgétaire concurrent, la résolution de conflits produit des doublons, des trous de séquence et des soldes irréconciliables |
| **Capture différée sur les écrans de saisie** | **Retenu** |

Concrètement : les écrans de saisie fonctionnent hors ligne avec les référentiels en cache ; les pièces sont mises en file locale avec une **clé d'idempotence** ; la file se synchronise au retour du réseau sans jamais créer de doublon ; **une pièce capturée hors ligne arrive toujours en brouillon**, jamais en comptabilisée. Numérotation, validation, contrôle budgétaire et comptabilisation restent au serveur.

**Exigences de performance en connectivité dégradée** (critères de recette) : poids des pages borné, fonctionnement mesuré sur un lien 3G et sur matériel modeste.

---

## 14. REPRISE DE DONNÉES ET RÉVERSIBILITÉ

### 14.1 Reprise — produit d'appel commercial

Le premier obstacle n'est pas le prix, c'est : *« je ne vais pas ressaisir trois exercices ».*

```
1. Référentiels      plan comptable · tiers · journaux · axes · accords · catégories
                     ▼ assistant de correspondance, sauvegardable et rejouable
2. Soldes d'ouverture balance à la date de bascule, équilibre vérifié
                     ▼
3. Historique        écritures des exercices antérieurs avec leurs imputations
                     ▼
4. Contrôle          rapprochement automatique balance d'origine ↔ balance reprise :
                     écart par compte, par axe, par accord — RAPPORT DE REPRISE SIGNÉ
```

**Critère : une reprise n'est acceptée qu'à écart nul** sur la balance générale et sur le cumul par accord. Un écart non nul bloque la mise en service et est listé ligne à ligne.

La voie est ouverte : les progiciels en place exportent vers Excel, et leurs propres intégrateurs migrent les historiques par fichiers Excel pré-formatés `[SRC:integrateur:104]`.

**Recommandation commerciale : offrir la migration, avec garantie d'écart nul.** C'est le verrou qui retient vos prospects, et chaque migration réalisée rend la suivante plus rapide.

### 14.2 Réversibilité — engagement contractuel

Une organisation obtient à tout moment, **sans intervention de l'éditeur** :
ses données (archive documentée + dépôt restaurable) · son paramétrage complet en JSON lisible · son registre des exigences et son guide de configuration · ses rapports publiés scellés · son journal d'audit.

**Le dictionnaire de données est publié ouvertement**, et la restitution d'un dépôt restaurable sous 48 heures à la résiliation est une **clause contractuelle**, pas une fonctionnalité.

Le modèle économique du produit de référence est exactement l'inverse. Dites-le dans la documentation commerciale.

---

## 15. MODES DE DÉPLOIEMENT

| Profil | Contenu | Usage |
|---|---|---|
| **Plateforme complète** | Socle comptable + les quatre niveaux | Cas nominal |
| **Couche reporting seule** | Niveaux 2, 3 et 4, alimentés par **import d'écritures** depuis le grand livre existant | Entrée à faible friction pour une organisation qui ne peut pas changer de comptabilité immédiatement. Conversion ultérieure vers la plateforme complète sans reprise. |
| **Hébergement souverain** | Installation chez le client ou sur infrastructure nationale, **sans divergence de code** | Exigence fréquente des États et de certains bailleurs sur les données financières publiques |

### 15.1 Modèle économique

| Principe | Règle |
|---|---|
| **Jamais de licence par utilisateur nommé** | Abonnement par organisation + nombre de **projets actifs** |
| **Sièges auditeur et bailleur** | Illimités, gratuits |
| **Croissance non pénalisée** | Ajouter un comptable ou une antenne ne déclenche aucun acte d'achat |
| **Paquets réglementaires** | Inclus et maintenus |
| **Migration depuis l'existant** | Offerte, avec garantie d'écart nul |

Cela inverse frontalement le modèle du produit de référence — licence × projets × topologie × **clés utilisateur facturées à l'unité** `[SRC:integrateur:104]` — et supprime l'objection budgétaire principale.

---

## 16. TRAJECTOIRE DE LIVRAISON

| Lot | Contenu | Résultat vérifiable |
|---|---|---|
| **L0 — Prototype du moteur** | **Moteur d'états + moteur de mapping + registre des exigences**, sur données générées | **Un TER et un IFR produits à partir d'un registre d'exigences, avec mapping versionné.** C'est la pièce la plus difficile : si elle ne tient pas, mieux vaut le savoir à la semaine 6 qu'au mois 9. |
| **L1 — Socle d'organisation** | Organisations, projets, habilitations croisées, exercices et périodes, journal d'audit, isolation | Deux organisations et quatre projets cloisonnés et audités |
| **L2 — Référentiels** | Référentiel analytique, axes configurables, **paquet PCG Djibouti + plan projet**, import des référentiels | Un plan projet opérationnel, importé depuis un existant |
| **L3 — Grand livre** | Saisie multidimensionnelle, schémas d'écritures, validation, comptabilisation, lettrage, rapprochement, à-nouveaux, clôtures | Balance, grand livre et journaux justes sur un exercice complet |
| **L4 — Budget et financements** | Budget multi-axes et versions, disponible, accords, catégories, cofinancement, comptes désignés | Un engagement bloqué sur dépassement, et débloqué par l'option paramétrée |
| **L5 — Configuration et profils** | Documents de référence, registre des exigences, activation, versionnement, **profil Banque mondiale** | Un projet configuré à partir de son DFIL, avec traçabilité au paragraphe |
| **L6 — Production et contrôles** | Contrôles à trois niveaux, workflow de validation, **scellement**, archivage de la version transmise, calendrier des obligations | **Un IFR et son ECD produits, contrôlés, validés, scellés et transmis — sans Excel** |
| **L7 — Dossier de conformité et accès auditeur** | Génération du dossier de conformité, guide de configuration, accès auditeur limité | Un auditeur descend d'une cellule du TER jusqu'à la pièce scannée |
| **L8 — Reprise et réversibilité** | Chaîne de migration, export complet autonome, dictionnaire de données publié | Une base migrée à écart nul, intégralement ré-exportable |
| **L9 — Marchés et trésorerie** | Plan de passation, non-objections, contrats, avenants, décomptes, prévisions de trésorerie | Un engagement bloqué faute d'avis de non-objection |
| **L10 — Multi-bailleurs** | Profils BAD, UE, FIDA, Fonds mondial, BID, SNU · tableau de bord multi-projets | **Deux rapports de bailleurs différents produits à partir des mêmes données** |
| **V2** | Immobilisations · capture hors ligne · assistant d'extraction · paquets OHADA · paquet de langue arabe · API publique | — |

**Jalon de bascule commerciale : fin de L7.** À ce stade, une UGP tient sa comptabilité, suit son budget, produit ses états, justifie ses dépenses et **fait son audit en libre-service**. Tout ce qui suit est de l'élargissement.

---

## 17. TESTS DE RÉCEPTION

Les sept premiers sont repris du cahier des charges de l'UGP : ils testent **l'architecture, pas les fonctionnalités**. Ne les diluez pas en liste de fonctions.

| # | Scénario | Résultat attendu |
|---|---|---|
| **T1** | Création d'un projet | Créer un projet à partir du socle commun, **sans développement spécifique** |
| **T2** | Deux projets, même bailleur | Configurer deux projets Banque mondiale avec composantes, catégories et périodicités **différentes** |
| **T3** | Ajout d'un autre bailleur | Ajouter un profil et un modèle **sans créer une nouvelle application** |
| **T4** | Reporting multi-bailleurs | Produire des rapports distincts **à partir des mêmes données sources**, selon les mappings validés |
| **T5** | Évolution d'une exigence | Modifier une configuration pour une période future **sans altérer les rapports historiques** |
| **T6** | Traçabilité | Remonter d'un montant publié jusqu'aux écritures et aux justificatifs |
| **T7** | Contrôles | Signaler données manquantes, incohérences et dépassements |
| **T8** | **Dossier de conformité** | Produire, pour un rapport publié, la liste de ses exigences avec leur source documentaire au paragraphe |
| **T9** | **Reproductibilité** | Régénérer un rapport scellé d'il y a six mois : résultat identique, **ou** écart expliqué ligne à ligne avec sa cause |
| **T10** | **Accès auditeur** | Un auditeur externe, en accès limité, descend d'une cellule d'état jusqu'à la pièce, sans assistance |
| **T11** | **Exhaustivité du mapping** | Un compte mouvementé non couvert par un mapping actif bloque la génération et est nommé |
| **T12** | **Réversibilité** | Exporter l'intégralité des données et du paramétrage, et les réimporter dans une instance vierge |
| **T13** | **Reprise** | Migrer une base existante à **écart nul** sur la balance et sur le cumul par accord |
| **T14** | **Connectivité dégradée** | Saisir une journée complète sans réseau, synchroniser sans doublon ni trou de séquence |
| **T15** | **Méthodes de décaissement variables** | Configurer trois projets du **même bailleur** avec des régimes, méthodes, seuils et taux de financement **différents**, sans développement spécifique |
| **T16** | **Changement en cours de projet** | Changer le régime de décaissement et réallouer entre catégories à une date d'effet : les demandes antérieures restent calculées aux règles alors en vigueur |

| **T17** | **Deux accords, un projet** | Un projet financé par deux bailleurs par deux accords indépendants : chaque dépense est contrôlée par les règles de **son** accord ; un avenant sur l'un crée une version sans effet sur l'autre ; une dépense antérieure à l'avenant conserve sa version ; un accès croisé d'une autre organisation est refusé |

### Critère d'acceptation d'architecture

> La solution est acceptée **sur le principe d'architecture** si elle démontre qu'un nouveau projet, un nouveau bailleur ou un nouveau modèle de reporting peut être ajouté **par paramétrage**, sans création d'une application distincte et **sans duplication des données comptables**.

---

## 18. RISQUES PRODUIT

| # | Risque | Traitement |
|---|---|---|
| **R1** | **Le moteur d'états et de mapping est sous-estimé.** C'est la pièce la plus difficile et celle qui porte toute la valeur. | **Prototypé en L0, avant le grand livre**, sur données générées. |
| **R2** | **Le registre des exigences est construit après coup** et devient une documentation morte à côté d'une configuration réelle divergente. | Construit **en même temps que le moteur**, en L0/L5. Toute configuration sans exigence source est signalée comme anomalie par le système lui-même. |
| **R3** | **Le moteur de formules devient un langage de programmation.** | Grammaire restreinte et analysée, jamais d'évaluation de code arbitraire. Limite assumée et documentée. |
| **R4** | **Erreurs d'arrondi** sur cofinancement et conversion de devises. | Aucun flottant sur un montant ; arrondis déterministes avec reliquat affecté ; version de clé persistée ; tests de propriété exécutés à chaque livraison. |
| **R5** | **La migration échoue et bloque la vente.** | Chaîne conçue dès L2, livrée en L8, critère d'écart nul, un client pilote migré avant toute commercialisation. |
| **R6** | **Dérive réglementaire.** Paquets non maintenus, conformité qui se dégrade silencieusement. | Paquets datés, validés par un expert-comptable, veille organisée. La maintenance réglementaire est une ligne budgétaire permanente, pas un projet. |
| **R7** | **Le hors-ligne dérape en réplication complète.** | Limite assumée : capture différée seulement. Toute extension passe par une décision explicite. |
| **R8** | **Surpromesse de conformité bailleur.** | **Note de conformité du §19.3 reprise mot pour mot** dans toute documentation commerciale. On promet la traçabilité aux documents du projet, pas une certification. |
| **R9** | **Dépendance à l'assistant d'extraction.** | Module optionnel ; le produit fonctionne intégralement sans lui ; aucune activation automatique. |
| **R10** | **Dérive de périmètre vers paie, stocks et suivi-évaluation.** | Périmètre verrouillé (D-07). Intégration par interface, jamais absorption. |

---

## 19. CONFORMITÉ

### 19.1 Propriété intellectuelle

La conception s'appuie sur un point de droit établi :

> **CJUE, C-406/10, *SAS Institute c/ World Programming*, 2 mai 2012 : ni les fonctionnalités d'un programme, ni le langage de programmation, ni les formats de fichiers de données ne sont protégés par le droit d'auteur.** `[SRC:droit:403]`

**Licite :** reprendre un modèle métier, un découpage fonctionnel, la logique des axes d'analyse, le principe d'un moteur d'états, les formats de fichiers d'échange, et la terminologie du métier — qui appartient aux bailleurs, pas à un éditeur.

**Interdit :** copier du code, reproduire une interface à l'identique, reprendre la documentation d'un éditeur au-delà du droit de citation, utiliser ses marques autrement que pour une référence nominative loyale, décompiler son logiciel.

**Règles de travail imposées à l'équipe :** aucun développeur n'installe, ne décompile ni n'inspecte le binaire d'un produit concurrent ; les spécifications sont rédigées à partir de sources publiques et de la connaissance métier ; le vocabulaire d'interface est celui des bailleurs (TER, DRF, ECD, compte désigné), jamais des libellés propres à un éditeur.

### 19.2 Données personnelles

Le plan de tiers, les bénéficiaires et les pièces justificatives portent des données à caractère personnel.

Cadre applicable : **lois nationales** — seules directement applicables — et, pour les États qui l'ont ratifiée, la **Convention de Malabo** de l'Union africaine sur la cybersécurité et la protection des données à caractère personnel, adoptée le 27 juin 2014 et **entrée en vigueur le 8 juin 2023** `[SRC:droit:406]`.

Exigences produit : minimisation des champs · chiffrement au repos · **journalisation des accès en lecture** aux données de tiers et aux exports · durée de rétention paramétrable par organisation · export et effacement sur demande · registre de traitement par organisation.

### 19.3 Note de conformité — à reprendre sans modification

> *Cette plateforme met en œuvre une architecture fonctionnelle et technique générique. Elle ne constitue pas une certification de conformité à un bailleur particulier. Les obligations effectives, les modèles, les délais et les périodicités doivent être établis à partir des documents contractuels et opérationnels applicables à chaque projet, puis validés par les responsables compétents.*

Cette réserve n'affaiblit pas l'offre : elle la distingue. Ce que le produit garantit n'est pas une conformité abstraite, mais **la traçabilité de chaque chiffre publié jusqu'au paragraphe du document qui l'exige, et jusqu'à la pièce qui le justifie**.

---

## ANNEXE — PARCOURS DE CONFIGURATION D'UN PROJET

```
 1. Créer le projet dans le socle commun
 2. Associer bailleurs et accords de financement
 3. Enregistrer les documents de référence et leurs versions
         ▼  (assistant d'extraction optionnel : propose, ne décide pas)
 4. Identifier les exigences applicables et leurs références documentaires
 5. Sélectionner les modèles de reporting disponibles dans les profils
 6. Configurer composantes, catégories, sources, devises et comptes
 7. Réaliser les mappings entre données internes et rubriques des rapports
 8. Activer les règles et contrôles nécessaires
 9. Exécuter un rapport test et le rapprocher des documents officiels
10. Faire valider la configuration, puis la publier
         ▼
    Le système génère le GUIDE DE CONFIGURATION DU PROJET
    et ouvre le CALENDRIER DES OBLIGATIONS
```

---

*Suite : [dossier d'architecture technique](02_ARCHITECTURE_TECHNIQUE.md).*
