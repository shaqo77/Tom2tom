# Plateforme intégrée de gestion financière et de reporting multi-bailleurs

Dossier de conception et plan de développement d'une application web de gestion financière et de reporting pour unités de gestion de projets financés par des bailleurs.

**Contexte de référence :** Unité de Gestion de Projet — République de Djibouti
**État :** spécification et plan complets. Le développement n'a pas commencé.

---

## Les documents, dans l'ordre de lecture

### Pour décider

| Fichier | Contenu |
|---|---|
| **[01_SPECIFICATION_FONCTIONNELLE.md](01_SPECIFICATION_FONCTIONNELLE.md)** | **Le produit.** Architecture à quatre niveaux, socle commun, profils de bailleurs, registre des exigences, moteur de reporting, contrôles, workflow, référentiels comptables, trajectoire en 11 lots, 14 tests de réception. |
| **[02_ARCHITECTURE_TECHNIQUE.md](02_ARCHITECTURE_TECHNIQUE.md)** | **La construction.** Stack, modèle de données SQL, isolation des organisations, scellement des rapports, assistant d'extraction, sécurité, exploitation, 15 décisions d'architecture avec leur coût de retour arrière. |

### Pour construire

| Fichier | Contenu |
|---|---|
| **[03_GUIDE_DEMARRAGE.md](03_GUIDE_DEMARRAGE.md)** | **Semaine 0.** D'une machine vide à un projet qui tourne, testé, intégration continue verte. Puis les 8 conventions obligatoires et les 10 règles à ne jamais enfreindre. |
| **[04_PLAN_LOTS_L0_A_L4.md](04_PLAN_LOTS_L0_A_L4.md)** | **Fondations.** Prototype du moteur, socle d'organisation, référentiels, grand livre, budget et financements. 40 tâches, avec code et contrôle de vérification. |
| **[05_PLAN_LOTS_L5_A_L10.md](05_PLAN_LOTS_L5_A_L10.md)** | **Métier et différenciation.** Registre des exigences, production et scellement, dossier de conformité, accès auditeur, reprise, marchés, multi-bailleurs. Plus les annexes front-end, hors ligne, mise en production. |

### Vos données vous appartiennent

| Fichier | Contenu |
|---|---|
| **[DICTIONNAIRE_DE_DONNEES.md](DICTIONNAIRE_DE_DONNEES.md)** | **Le schéma, publié ouvertement** : chaque table, chaque colonne, son type, ses relations et ses contraintes, généré depuis le code (un test échoue s'il vieillit). Ce n'est pas un document réservé aux clients : c'est la moitié de la réversibilité. |

### Matériau de base

| Fichier | Contenu |
|---|---|
| [ANNEXE_A_VERIFICATION_FACTUELLE.md](ANNEXE_A_VERIFICATION_FACTUELLE.md) | Analyse vérifiée du produit de référence TOM²Pro : 32 affirmations passées au crible des sources primaires, failles structurelles documentées, repères de prix réels. |
| [ANNEXE_B_REGISTRE_DES_SOURCES.md](ANNEXE_B_REGISTRE_DES_SOURCES.md) | 40 sources cotées par fiabilité, avec leur apport et les pièces restant à obtenir. |
| `CAHIER_DES_CHARGES_RETRO-INGENIERIE_TOM2PRO_v2.0.md` | **Caduc.** Produit au début du travail, sur un cadrage qui n'était pas le bon. Ses deux annexes, elles, ont été conservées. Dites-le si vous voulez qu'il soit supprimé ou archivé. |

---

## Le principe

> **Mutualiser les données et les traitements. Paramétrer les différences. Ne développer que les fonctionnalités réellement nouvelles.**

```
┌────────────────────────────────────────────────────────────┐
│  NIVEAU 4 — MOTEUR DE MAPPING ET DE REPORTING              │
│  N présentations à partir des MÊMES données                │
├────────────────────────────────────────────────────────────┤
│  NIVEAU 3 — CONFIGURATION DU PROJET                        │
│  Documents de référence · REGISTRE DES EXIGENCES           │
├────────────────────────────────────────────────────────────┤
│  NIVEAU 2 — PROFIL DU BAILLEUR                             │
│  Bibliothèque réutilisable — n'impose rien automatiquement │
├────────────────────────────────────────────────────────────┤
│  NIVEAU 1 — SOCLE COMMUN                                   │
│  Comptabilité · budget · financements · trésorerie ·       │
│  marchés · documents · référentiel analytique              │
└────────────────────────────────────────────────────────────┘
```

Un nouveau projet, un nouveau bailleur ou un nouveau modèle de rapport s'ajoute **par paramétrage**. Le socle ne bouge pas.

---

## Ce qui distingue le produit

Pas le nombre de fonctions — **ce que le client peut produire devant son auditeur et son bailleur**. Trois artefacts qu'aucun produit de ce marché ne fournit :

1. **Le dossier de conformité traçable.** Chaque rubrique d'un rapport publié est rattachée à l'exigence qui l'impose, avec sa source documentaire au paragraphe près. Le paramétrage cesse d'être une boîte noire.
2. **Le rapport scellé et reproductible.** Régénérer un rapport d'il y a six mois rend soit l'identique, soit un écart expliqué ligne à ligne avec sa cause.
3. **L'accès auditeur direct.** Lecture seule, limitée dans le temps et le périmètre, avec descente d'une cellule d'état jusqu'à la pièce scannée.

**Et un modèle économique inversé :** abonnement par organisation et par projet actif, jamais par utilisateur nommé ; sièges auditeur et bailleur gratuits ; migration offerte avec garantie d'écart nul ; export complet en un clic et restitution sous 48 heures garantie contractuellement.

---

## Décisions déjà prises

| # | Sujet | Décision |
|---|---|---|
| D-01 | Structure | Architecture à quatre niveaux |
| D-02 | Référentiel v1 | **Plan Comptable Général de Djibouti (2012)** + plan projet générique. *Djibouti n'est pas membre de l'OHADA :* SYSCOHADA et SYCEBNL deviennent des paquets d'expansion |
| D-03 | Entités | Organisation **et** projet de premier rang |
| D-04 | Langues | Droite-à-gauche pris en compte dès l'origine ; FR/EN en v1, arabe en paquet |
| D-05 | Déploiement | Plateforme complète **ou** couche reporting seule au-dessus d'un grand livre existant |
| D-06 | Assistant d'extraction | Retenu, optionnel, sans aucune activation automatique |
| D-07 | Périmètre exclu | Paie, RH, stocks, suivi-évaluation — intégrés, jamais absorbés |
| D2 | Stack | PostgreSQL + Django + React. **Réversible jusqu'au début du lot L3**, pas après |

---

## Calendrier indicatif

Pour **deux développeurs**. Le front se construit en parallèle, lot par lot.

| Lot | Contenu | Durée | Cumul |
|---|---|---|---|
| L0 | Prototype du moteur d'états, de mapping et d'exigences | 4 sem. | 4 |
| L1 | Socle d'organisation : isolation, projets, habilitations, audit | 3 sem. | 7 |
| L2 | Référentiels et paquet comptable | 3 sem. | 10 |
| L3 | Grand livre | 5 sem. | 15 |
| L4 | Budget et financements | 4 sem. | 19 |
| L5 | Configuration et registre des exigences | 4 sem. | 23 |
| L6 | Production, contrôles, scellement, calendrier | 5 sem. | 28 |
| L7 | Dossier de conformité et accès auditeur | 3 sem. | **31** |
| L8 | Reprise et réversibilité | 3 sem. | 34 |
| L9 | Marchés, non-objections, trésorerie | 4 sem. | 38 |
| L10 | Multi-bailleurs et tableau de bord | 3 sem. | 41 |

**Bascule commerciale : fin de L7**, soit environ 31 semaines. À ce stade, une unité de gestion tient sa comptabilité, suit son budget, produit ses états, justifie ses dépenses et **fait son audit en libre-service**.

---

## Par où commencer, concrètement

1. Lire le [guide de démarrage](03_GUIDE_DEMARRAGE.md) et exécuter les contrôles **A.1 à A.7**. Compter une journée.
2. Afficher au mur les **dix règles à ne jamais enfreindre** (guide, partie C).
3. Attaquer **L0 — le prototype du moteur**, avant le grand livre.

> **Pourquoi le moteur avant la comptabilité.** C'est contre-intuitif, et c'est délibéré. Le moteur d'états et de mapping est la pièce la plus difficile et celle qui porte toute la valeur. S'il ne tient pas, toute la trajectoire est à revoir — mieux vaut le découvrir à la semaine 4 qu'au mois 9.

**Critère de sortie de L0 :** un TER et un rapport financier intermédiaire produits à partir d'un registre d'exigences, avec mapping versionné et traçabilité descendante jusqu'aux lignes, en moins de 3 secondes sur 200 000 écritures.
