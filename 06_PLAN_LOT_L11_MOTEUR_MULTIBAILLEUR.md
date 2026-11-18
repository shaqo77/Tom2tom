# Lot L11 — Du socle au moteur de gestion financière multibailleur

Ce document complète [`05_PLAN_LOTS_L5_A_L10.md`](05_PLAN_LOTS_L5_A_L10.md). Il part du **questionnaire de
vérification fonctionnelle** (58 questions) passé sur le code après L10 : 19 fonctions opérationnelles,
30 partielles, 9 absentes. Le constat : le socle (grand livre immuable, isolation par organisation,
contrôle budgétaire, profil de décaissement versionné, moteur d'états avec descente, journal d'audit) est
réel, mais plusieurs fonctions **existent sans être branchées**, et le cœur multibailleur (formats de
rapport par bailleur, import Excel, IA documentaire) manque.

## Principes

- Tests d'abord, qui **échouent avant** le correctif ; chaque garantie est vérifiée par une mutation volontaire.
- Une branche par tâche, empilée sur la précédente, avec une note « Réalisation » et ses limites.
- Une fonction n'est « faite » que si elle est **branchée sur le flux réel** (saisie, rapport, tableau de bord).
  Une table, un écran ou un service que seul un test appelle ne comptent pas.
- **Aucune règle de bailleur inventée** : sans le document du bailleur, un profil reste un squelette sourcé.
- Aucune fusion de PR sans accord explicite. Les règles 1 à 10 de `CLAUDE.md` restent intangibles.

## Ce que le diagnostic a établi (état de départ)

| Constat | Conséquence pour le plan |
|---|---|
| `accounting_basis` est stocké mais **aucun code ne le lit**. | A3 : lui donner un effet réel, ou le retirer. |
| La répartition entre bailleurs (`cles.py`, `cofinancement.py`) n'est appelée que par ses tests. | A2 : la brancher à la saisie. |
| Les réglages de devises ne contrôlent que écritures, accords, comptes bancaires et reprises. | A1, A6 : les faire lire par consolidation, taux et budget. |
| Les 22 contrôles de la bibliothèque s'exécutent à la revue, pas à la génération. | A4. |
| L'éligibilité n'est vérifiée que dans le flux de demande de retrait. | A5. |
| Un seul modèle d'état livré (rapprochement du compte désigné). | Phase C. |
| Aucune IA ; l'extraction de texte sert uniquement à vérifier une citation. | Phase E. |
| Presque aucune règle n'est administrable par une API ou un écran. | Phase B. |

## Phase 0 — Débloquer l'existant

| Tâche | Contenu | Preuve de fin |
|---|---|---|
| 0.1 CI | Vérifier le quota ou la facturation GitHub Actions (travaux sans exécuteur depuis ~15 h 20 UTC) ; relancer #86 à #91. | CI verte sur la chaîne. |
| 0.2 Fusion | Fusionner #77 à #91 **dans l'ordre**, avec accord explicite. | `main` à jour. |
| 0.3 Déploiement | Déployer sur Fly depuis le Mac (branche `deploiement-fly`, `DEPLOIEMENT_FLY.md`). | Application en ligne. |

## Phase A — Brancher ce qui existe

| Tâche | Contenu | Preuve de fin | Taille |
|---|---|---|---|
| **A1** | Consolidation du tableau de bord sur la devise de référence **réglée** et le type de taux réglé. Rien de paramétré : le tableau le dit, il ne devine pas. Taux manquant : la ligne est nommée. Puis descente cliquable jusqu'à l'écriture. | Somme consolidée exacte ; écart dit. | M |
| **A2** | **Répartition entre bailleurs câblée à la saisie** : une dépense, une clé de cofinancement, lignes ventilées par accord, total conservé au centime. API et écran. | Test de propriété (somme des parts = montant) ; scénario à 3 bailleurs. | L |
| **A3** | **Base comptable** (caisse, engagement, mixte) : elle change un comportement réel (quelles écritures alimentent les états) ou elle est retirée. | Test montrant la différence entre deux modes. | M |
| **A4** | **Contrôles à la génération** : `publier_rapport` exécute les contrôles bloquants du profil, en plus de la revue go/no-go. | Un rapport est refusé tant qu'un contrôle bloquant échoue. | M |
| **A5** | **Éligibilité au grand livre** : à la validation d'une écriture imputée à un accord (dates, catégorie, dépense hors ligne de budget). Modes bloquant ou avertissement, réglables comme le budget. | Une dépense inéligible est refusée ou signalée à la saisie. | M |
| **A6** | Version de convention portée par chaque écriture ; devises autorisées étendues aux taux et au budget. | Une opération se rattache à sa version de convention. | M |

### Réalisation — A1a (consolidation pilotée par les réglages, côté serveur)

`GET /api/v1/tableau-de-bord/<indicateur>/consolidation/` prend désormais sa **devise de référence** et son **type de taux** dans les réglages de l'organisation ou du projet (`resoudre_reference`, `niveau4_reporting/tableau_de_bord/devises.py`). Un paramètre explicite (`devise_reference`, `type_taux`) l'emporte toujours. La réponse dit d'où vient chaque valeur : `origine = {devise_reference, type_taux}` (`demande`, `projet` ou `organisation`).

- **Rien n'est écrit dans le code** : le défaut « officiel » codé en dur a disparu. Sans réglage ni paramètre, la réponse est `200` avec `consolide: false` et une raison lisible (avant : `422`).
- **Références différentes entre projets du périmètre** (P1 hérite de DJF, P2 règle EUR) : aucun total unique n'a de sens ; la raison nomme chaque projet et sa valeur, et la personne tranche en passant un paramètre.
- **Correction d'un défaut latent** : les taux du référentiel sont exprimés en monnaie de *tenue*. Consolider vers une référence qui n'est pas la monnaie de tenue multipliait par le taux de la devise sans diviser par celui de la référence (résultat faux). La conversion passe maintenant par croisement `montant × taux(devise) / taux(référence)` et exige le taux de la référence.
- Tests : 8 nouveaux dans `test_api_tableau_de_bord_bd.py` (19 en tout, plus 17 de `test_tableau_de_bord_bd.py`) ; les tests existants passent le type de taux explicitement. Mutations détectées : priorité du paramètre, croisement, taux de la référence, détection des références différentes, provenance, « un projet sans réglage », raison du type de taux, arrondi, périmètre, validation du type de taux.
- **Limites** : l'interface (écran de consolidation) et la **descente cliquable** jusqu'à l'écriture (A1b) restent à faire ; le tableau de bord principal n'affiche toujours pas de total consolidé ; la suite complète n'a pas été relancée (suites touchant le tableau de bord, la recette d'architecture, les conventions et le catalogue de messages : vertes) ; CI GitHub toujours en panne.

### Réalisation — A1b (consolidation et descente dans le navigateur)

- **Carte « Total consolidé »** du tableau de bord : on choisit l'indicateur, la devise de référence et le type de taux ; par défaut « selon les réglages ». Elle affiche le total, la méthode, les taux utilisés (avec leur date) et **d'où vient chaque valeur** (« Choisi ici », « Réglage du projet », « Réglage de l'organisation »). Quand le serveur ne consolide pas (rien de réglé, références différentes, taux manquant), l'écran répète sa raison telle quelle et n'affiche aucun montant. Les filtres du tableau (date, statut, projets) suivent jusqu'à la consolidation.
- **Page de descente** `/tableau-de-bord/descente` (adresse partageable : projet, indicateur, jour, élément, écriture) : indicateur → éléments qui le composent, avec un total par devise (contrôle : il retombe sur le chiffre du tableau) → écritures de l'élément → écriture (lignes, pièces). Les éléments qui ne viennent pas du grand livre (accords, lignes de budget, engagements) le disent au lieu d'inventer une écriture. Le nombre de décimales de chaque devise vient du catalogue du serveur, jamais du code.
- **Serveur** : nouvelle route `GET /api/v1/projets/<id>/tableau-de-bord/ecritures/<id>/` (habilitation `consulter`) qui renvoie l'écriture, ses lignes, la **monnaie de base du projet** (donnée du projet, testée avec un projet en USD) et la liste des pièces **sans leurs octets ni leur empreinte** (le scan reste réservé à l'accès auditeur). Une écriture d'un autre projet est introuvable.
- Tests : 4 nouveaux côté serveur (24 dans le fichier), 15 côté navigateur (`Descente.test.tsx`, dont axe) ; 187 tests front verts, typecheck, eslint, build. Mutations détectées (total par devise, éléments sans écriture, conservation du détail dans l'adresse, choix explicite, filtres projets et statut, validation de l'adresse, décimales du catalogue et de la monnaie du projet) ; deux survivantes comblées par des tests.
- **Vérifié dans un vrai navigateur contre le vrai backend** : total consolidé de 5 000 000 USD + 3 000 000 EUR converti par croisement via DJF (8 380 281,69 USD), choix explicite qui l'emporte, descente d'un accord jusqu'à ses éléments avec total par devise. Il a montré un cas utile : le réglage d'un *projet* (type de taux « budget ») pilote le périmètre quand seul ce projet a des montants, et l'écran dit alors clairement qu'aucun taux « budget » n'existe.
- **Limites** : la descente n'est reliée dans le tableau qu'aux colonnes budget, consommé et soldes de la table par projet (les autres indicateurs s'ouvrent par l'adresse) ; la raison « taux manquant » ne dit pas encore quel réglage (projet ou organisation) a imposé le type de taux ; le scan d'une pièce n'est pas ouvrable depuis cet écran ; le parcours E2E n'est pas dans la CI ; CI GitHub toujours en panne.

## Phase B — Administrer sans développeur

APIs et écrans (même méthode que les réglages de devises : API, écran, tests, vérification dans un vrai
navigateur) pour : bailleurs et accords, profils de décaissement, clés de cofinancement, mappings,
contrôles, exigences. Ordre : accords, profils, clés, contrôles.

**Preuve de fin** : un administrateur configure un bailleur de bout en bout dans le navigateur, sans appel
Python (questionnaire, question 14).

## Phase C — Rapports par bailleur

| Tâche | Contenu | Dépend de |
|---|---|---|
| C1 | Modèle **IFR Banque mondiale** livré et rempli depuis le grand livre. | Format officiel du bailleur. |
| C2 | SOE et états d'utilisation des fonds. | Leurs formats. |
| C3 | Périodes de reporting libres (trimestre, semestre) selon l'exigence. | — |
| C4 | **Import d'un modèle Excel** : cellules rattachées aux rubriques par correspondance validée. | Décision de conception (voir plus bas). |
| C5 | Export Excel fidèle : valeurs écrites dans le modèle d'origine, formules et mise en forme conservées. | C4. |
| C6 | Formats UE et BAD. | Leurs documents. |

## Phase D — Profils des bailleurs

Remplir BAD, UE, FIDA, Fonds mondial, BID, ONU, puis AFD, **à partir de leurs documents uniquement**, chaque
règle avec sa citation vérifiée littéralement dans le texte (mécanisme L5-T02). Le mécanisme est livré par
le projet ; le contenu dépend des documents fournis.

## Phase E — IA documentaire

| Tâche | Contenu |
|---|---|
| E1 | Appel à un modèle d'IA, avec journal, coût et traçabilité. |
| E2 | Extraction de règles : toute proposition dont la citation n'est pas retrouvée **littéralement** dans le document est rejetée automatiquement. |
| E3 | Les propositions deviennent des exigences « proposées » ; l'activation reste humaine (règle 9). |
| E4 | Comparaison avenant et convention initiale ; détection de contradictions entre documents. |
| E5 | Évaluation sur de vrais documents, avec mesure de précision publiée. |

## Phase F — Recette multibailleur

Un test automatisé et un parcours navigateur : **un projet, trois bailleurs, une dépense saisie une seule
fois, répartie, trois rapports distincts, aucune intervention manuelle** (questionnaire, questions 55 à 58).
Le parcours navigateur entre dans la CI.

## Transversal

- Écran de changement de mot de passe (l'API existe) ; réinitialisation par courriel et double
  authentification (décisions à prendre) ; pagination et jeton d'API.
- Limiter les déclenchements de la CI pour économiser les minutes.
- T14 (capture hors ligne) : version 2 du plan, toujours non livré.

## Décisions attendues

1. **Base comptable** (A3) : quel comportement exact pour caisse, engagement et mixte ?
2. **Excel** (C4, C5) : conserver les formules du modèle, ou seulement les valeurs ?
3. **IA** (E1) : les documents financiers peuvent-ils être envoyés à un service externe ? Sinon, un modèle hébergé en interne.
4. **Documents des bailleurs** : IFR et SOE de la Banque mondiale en priorité, puis UE, BAD et autres.
5. **Ordre proposé** : A1, A2, A4, A5, A3, puis B, C, D, E, avec F en continu.

## Risques d'incohérence à surveiller pendant ce lot

- Un projet « caisse » traité comme « engagement » (jusqu'à A3).
- Parts de bailleurs saisies à la main qui ne somment pas au total (jusqu'à A2).
- Dépense non couverte par une ligne de budget qui échappe au contrôle ; dépense inéligible comptabilisée (A5).
- Devises autorisées sans taux de change ni contrôle sur le budget (A6).
- Aucune vérification externe tant que la CI est en panne (0.1).

---

*Retour : [guide de démarrage](03_GUIDE_DEMARRAGE.md) · [lots L5 à L10](05_PLAN_LOTS_L5_A_L10.md)*
