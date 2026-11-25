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

### Réalisation — A2 (la répartition entre bailleurs câblée à la saisie)

`saisir_ecriture` accepte désormais, sur une ligne, `"cle": "<code de la clé>"` à la place d'un accord. Elle remplace cette ligne par **une ligne par accord** de la version de la clé **en vigueur à la date comptable** (`developper_cles`, `niveau1_socle/financements/cles.py`), chacune portant son accord et `cofunding_key_version_id`. L'appelant dit « cette charge suit la clé CHARGES » ; il ne calcule plus aucune part.

- **Une seule règle de calcul** : la saisie appelle le même `ventiler_montant` que le service existant (parts normalisées, arrondi vers zéro, reliquat au porteur désigné). Un test prouve que saisie et `lignes_ventilees` donnent les mêmes lignes.
- **Chaque montant à son pas** : les montants de tenue sont arrondis au pas de la monnaie de tenue de l'organisation (aucune décimale pour le franc de Djibouti), les montants en devise au pas de la devise de l'écriture ; le total de chacun est conservé (test de propriété sur 15 montants tirés au hasard, plus un cas en USD).
- **Refus nommés** : clé inconnue ou d'un autre projet, aucune version en vigueur à la date (avant la première version), ligne qui désigne à la fois une clé et un accord, montant non exprimable dans la monnaie. Un accord de la clé qui n'est plus actif ne reçoit rien (contrôle existant, désormais atteint par la clé). Les lignes de l'appelant ne sont pas modifiées ; une part nulle après arrondi ne produit pas de ligne.
- **Version à la date** : une écriture de mars et une écriture d'août suivent chacune la version de clé de leur date (règle 7 : les anciennes versions restent).
- Tests : 15 dans `test_saisie_cofinancee_bd.py` (les 15 tests de `test_cles_cofinancement_bd.py` restent verts). Mutations détectées : refus clé+accord, clé inconnue, absence de version, filtre par projet, pas de la devise, part nulle, version portée par la ligne, choix de la version à la date ; une survivante équivalente (la garde « aucune ligne ne porte de clé » n'est qu'un raccourci).
- **Limites** : il n'existe aucune route HTTP ni écran de **saisie** d'écriture (la saisie se fait par le service ; l'écran est l'écran L3 non construit) ni d'API de gestion des clés (phase B) ; la clé n'est pas encore acceptée dans les schémas d'écriture (`saisir_depuis_schema`) ; la ventilation porte sur les lignes que l'appelant désigne, elle n'est pas appliquée d'office à toute dépense d'un projet cofinancé ; les accords de la clé sont ceux de ses parts (aucun contrôle de couverture par le profil de décaissement) ; CI GitHub toujours en panne.

### Réalisation — A4 (les contrôles de dépense à la validation d'une écriture)

À la validation d'une écriture, chaque **charge** (côté débit d'un compte budgété, comme le contrôle budgétaire) est passée aux contrôles **actifs** de codification et de pièces (`niveau4_reporting/controles/depenses.py`). Un résultat bloquant, ou « à vérifier » non tranché, refuse la validation (`CONTROLE_BLOQUANT`) ; un avertissement la laisse passer et se lit sur `ecriture.avertissements_controles`. Avant, la bibliothèque de contrôles n'était évaluée nulle part sur le grand livre : un contrôle « dépense sans catégorie » pouvait être actif sans rien arrêter.

- **Point d'accroche, pas de dépendance montante** : le grand livre (`niveau1_socle`) n'importe pas le module de contrôles ; il expose `enregistrer_controle_a_la_validation`, auquel `controles/apps.py` s'abonne au démarrage.
- **Évaluations écrites avant la transaction de validation** : un refus ne les efface pas (journal en ajout seul), sinon un contrôle « à vérifier » ne pourrait jamais être tranché. Droits (`valider`), séparation des tâches et statut « brouillon » sont vérifiés d'abord : un utilisateur sans droit, l'auteur de la pièce ou une écriture déjà validée ne déclenchent aucune évaluation.
- **Un contrôle « à vérifier » n'est pas réévalué** tant que sa dernière évaluation sur la ligne attend ou porte une décision humaine (`sauf` dans `evaluer_tous`) ; un contrôle bloquant, lui, est réévalué après correction de la ligne (« bloquant » puis « réussi »).
- **Aucune activation d'office** (règle 9) : sans contrôle actif, rien ne change ; un contrôle installé en brouillon n'est pas évalué ; un contrôle pas encore en vigueur à la date de la dépense non plus.
- Tests : 13 dans `test_controles_depenses_bd.py`. Mutations détectées (types de règle, sélection des charges, réévaluation, date d'opération, droits, abonnement, avertissements) ; une survivante équivalente en pratique (`>= 0` au lieu de `> 0` dans la sélection des charges : un compte budgété n'a pas de ligne à montant net nul). **Suite backend complète : 1 793 réussis, 1 ignoré, 0 échec**.
- **Limites** : seuls les types « codification » et « pièces » sont évalués (le budget garde son propre mécanisme ; l'éligibilité est l'objet de A5 ; trésorerie, rapport et cohérence n'ont pas de contexte construit) ; nature, zone et bénéficiaire ne sont pas portés par le grand livre, donc les contrôles qui les utilisent ne sont pas applicables ; les pièces sont toutes tenues pour rattachées et valides (le grand livre n'a pas de notion de validité d'une pièce) ; les contrôles ne s'exécutent qu'à la validation, pas à la saisie ni à la comptabilisation ; aucune route HTTP de validation n'existe encore ; CI GitHub toujours en panne.

### Réalisation — A5 (l'éligibilité à la validation d'une écriture)

Une dépense imputée à un accord doit tomber dans sa **fenêtre d'éligibilité**. Avant, l'éligibilité n'était vérifiée que dans le flux de demande de retrait ; une dépense hors période se comptabilisait sans un mot et n'était repérée qu'au moment de la justifier au bailleur.

- **Une seule règle de calcul** (`fenetre_d_eligibilite`, `niveau3_config/services/decaissement.py`), bornes **incluses**, aucune date inventée : début = le plus tardif des débuts connus (date d'éligibilité du profil en vigueur à la date de la dépense, début d'éligibilité de la catégorie) ; fin = la plus précoce des fins connues (fin d'éligibilité de l'accord, fin de la catégorie). Une sous-catégorie hérite de la fenêtre de sa catégorie (`regle_pour`). Sans borne connue, rien ne restreint.
- **Branchée sur le mécanisme de A4** : la validation évalue le type « éligibilité » avec un contexte enrichi (`date_debut_eligibilite`, `date_fin_eligibilite` et le booléen `dans_periode_eligibilite`, calculé côté serveur : le langage de conditions ne sait pas comparer deux champs, et ses deux champs de dates n'étaient lus par aucun code). Contrôle livré : **`ELIG-PERIODE-ACCORD`** (bloquant, applicable seulement avec un accord). Comme tout contrôle : activation par une personne habilitée (règle 9), sévérité modifiable en avertissement, un projet sans contrôle actif ne change pas.
- **Correction après la suite complète** : la première version construisait le contexte d'éligibilité pour chaque charge **même sans contrôle actif**, et lisait l'accord sans tolérer son absence : `test_controle_budgetaire_bd` (accord inconnu du grand livre) échouait. Le contexte est maintenant **paresseux** (`evaluer_tous` accepte une fonction, appelée seulement s'il existe un contrôle actif à évaluer ; partagée entre types de règle) et un accord illisible rend le contrôle non applicable au lieu de lever. `test_bibliotheque_controles` exigeait en outre des cas de test et une sévérité écrite à part pour chaque contrôle livré : `ELIG-PERIODE-ACCORD` les a désormais.
- Tests : 14 dans `test_eligibilite_depenses_bd.py` (fenêtre pure, bornes incluses, accord, catégorie, sous-catégorie, sans accord, sans borne, sans contrôle actif). Mutations détectées (début et fin, bornes, héritage de catégorie, présence d'un accord, type évalué, profil à la date, applicabilité du contrôle livré). Suites ciblées vertes ; suite complète relancée après correction.
- **Limites** : seules les dates sont contrôlées (nature, zone et bénéficiaires exclus restent des modèles de la bibliothèque que le grand livre ne peut pas alimenter) ; la date d'effet de l'accord n'est pas une borne (la rétroactivité est portée par la date d'éligibilité du profil) ; la fin d'éligibilité de l'accord est tenue pour **incluse**, comme celle de la catégorie : à confirmer avec le texte de chaque accord ; contrôle à la validation seulement ; CI GitHub toujours en panne.

### Réalisation — A6 (les taux de change s'enregistrent ; le budget respecte les devises autorisées)

**Constat** : aucun service n'enregistrait un taux de change. Ils n'entraient que par des tests ou du SQL direct, alors que la consolidation du tableau de bord (A1) en dépend. Et une ligne de budget pouvait être saisie dans une devise que les réglages n'autorisent pas.

- **`enregistrer_taux`** (`niveau1_socle/referentiels/taux.py`) : habilitation `parametrer` ; le taux est un **nombre exact strictement positif écrit en chiffres** (jamais un `float`, ni exposant, ni NaN) ; type de taux et devise connus (refusés **avec leur propre message** : la base les refuserait aussi, mais avec un message trompeur « déjà enregistré ») ; **la monnaie de tenue n'a pas de taux** (il vaut 1 par définition) ; la devise doit être autorisée par la liste de l'organisation **à la date du taux** ; un taux du même jour et du même type **ne s'écrase pas** ; journal d'audit `rate_recorded` avec sa source.
- **API** `GET/POST /api/v1/taux/` : lecture filtrable par devise et par type, la plus récente d'abord (500 au plus), taux en chaîne ; enregistrement refusé en 403 sans l'habilitation, en 422 au format `{code, message}` sinon.
- **Budget** : `ajouter_ligne` refuse une devise non autorisée, selon la liste applicable au **début de la période budgétée** (le 1er janvier de l'année pour un budget annuel).
- **Correction après la suite complète** : le contrôle de devise du budget construisait la date de la période avant la validation de la ligne ; une période de 13 levait une erreur de date brute au lieu de « période comprise entre 1 et 12 » (`test_budget_bd` l'a révélé). Le contrôle se fait maintenant après la validation, et une année hors bornes est laissée à la base (1900 à 2200). Un test dédié échoue avec l'ancien ordre.
- Tests : 20 dans `test_taux_enregistres_bd.py` et 4 de plus côté API. Mutations détectées (habilitation, float et exposant, type et devise inconnus, monnaie de tenue, liste autorisée et sa date, doublon, journal, filtres, ordre, contrôle du budget et sa date). Suite complète relancée avant la PR.
- **Limites** : aucun **écran** de saisie des taux (l'API existe) ; pas de correction d'un taux saisi par erreur le même jour (la règle « jamais écrasé » impose d'enregistrer à une autre date : à décider) ; pas d'import en lot (fichier de la banque centrale) ; le contrôle des devises autorisées ne porte pas encore sur les budgets révisés (`modifier_ligne` ne change pas la devise) ; CI GitHub toujours en panne.

### Réalisation — A3 (la base comptable a un effet réel, et un seul)

**Décision (tranchée sans avis de l'utilisateur, à sa demande : « la meilleure manière optimale »).** `accounting_basis` était stocké et verrouillé après la première écriture, mais aucun code ne le lisait : une promesse que rien ne tenait. Deux issues étaient possibles : le retirer, ou lui donner un effet. Je l'ai gardé avec **un effet que le modèle de données peut vraiment tenir**, plutôt que d'inventer une conversion caisse/engagement que rien ne soutient :

| Valeur | Effet dans l'application |
|---|---|
| `cash` (caisse pure) | le projet **ne réserve pas de budget** : `creer_engagement` est **refusé**, avec un message qui dit quoi faire |
| `cash_with_commitments` (caisse avec engagements) | les engagements sont permis et **réduisent le disponible** |
| `accrual` (engagement) | idem |

- **Pourquoi pas plus** : la reconnaissance d'une charge reste la **date de l'écriture, saisie par les utilisateurs** (un projet en caisse enregistre ses charges au paiement, un projet en engagement à la facture). Le système ne convertit rien et ne le prétend pas. Convertir automatiquement demanderait un lien entre chaque charge et son paiement bancaire que le modèle n'a pas. Entre `cash_with_commitments` et `accrual`, le système ne distingue donc rien : la différence est celle de la saisie.
- **Pourquoi pas le retrait** : la colonne est requise à la création d'un projet, verrouillée par déclencheur, et un retrait demande une migration sur une table centrale pour supprimer une information que les bailleurs demandent de toute façon de déclarer.
- **Le tableau de bord dit la base de chaque projet** (`projets[].base_comptable`), pour qu'un rapport ou un écran puisse l'afficher.
- Le réglage étant **figé après la première écriture** (déclencheur existant, testé), l'effet ne peut pas être contourné en changeant de base en cours de route.
- Tests : 5 dans `test_base_comptable_bd.py` (+1 côté tableau de bord). Mutations détectées (contrôle retiré, valeur de base inversée, comparaison inversée). Suite complète relancée avant la PR.
- **Limites** : pas d'écran qui affiche la base (l'API la donne) ; aucun rapport ne la porte encore dans ses métadonnées ; un projet en caisse qui a déjà des engagements les garde (seule la création est refusée) ; si les bailleurs imposent une vraie reconnaissance à l'encaissement, il faudra relier charges et paiements : travail à part, non engagé.

## Phase B — Administrer sans développeur

### Réalisation — B1 (API des clés de cofinancement)

Un administrateur règle la répartition entre bailleurs **sans développeur**, puis la saisie s'en sert (A2). Avant, créer une clé et ses versions n'était possible que par appel de service Python.

- `GET/POST /api/v1/projets/<id>/cles-cofinancement/` : liste des clés avec la **version en vigueur à `?jour=`** (début inclus, fin exclue ; `null` avant la première version) ; création d'une clé (code et libellés par langue obligatoires).
- `GET /api/v1/projets/<id>/cles-cofinancement/<clé>/` : la clé et **toutes ses versions**, la plus récente d'abord, chacune avec ses parts.
- `POST …/<clé>/versions/` : une version à partir de `parts` (`{"numéro d'accord": poids}`), `porteur` (l'accord qui absorbe le reliquat d'arrondi), `valid_from`, `motif`. Les accords se désignent par leur **numéro**, jamais par un identifiant interne. Les poids sont des nombres exacts strictement positifs écrits en chiffres (jamais un flottant, un exposant ou du texte) ; les parts rendues sont des chaînes décimales qui somment **exactement** à 1. La version en cours est close à la date d'effet, l'ancienne reste lisible (règle 7).
- Lecture : habilitation `consulter` ; écriture : `parametrer`, contrôlée par les services (403 sinon). Une clé s'adresse par son projet : celle d'un autre projet est introuvable (404), même pour qui a des droits sur les deux.
- **Refus lisibles au lieu de pannes** : un code de clé déjà pris (la base le refusait par une erreur d'intégrité brute, donc un 500) devient un 422 `{code, message}` ; les erreurs de clé et de ventilation du service sont désormais traduites en 422 par le gestionnaire commun.
- Tests : 21 dans `test_api_cles_bd.py`, dont le **parcours complet** (la clé réglée par HTTP ventile la saisie d'une écriture). Mutations détectées (habilitations, cloisonnement par projet, ordres de tri, validation des libellés et des poids, accord inconnu, traduction des erreurs, statut 201, parts en flottant, repli du doublon) ; une survivante équivalente a été retirée (le contrôle du porteur est refait par le service). Suite complète relancée avant la PR.
- **Limites** : pas d'écran (API seulement) ; une version ne se corrige pas, on en ouvre une autre (règle 7) ; la clé ne se supprime pas ; l'API ne vérifie pas que les accords de la clé couvrent la catégorie de la dépense (la saisie le fait à l'usage : accord actif) ; accords, profils de décaissement et contrôles restent à exposer (B2 et suivantes).


APIs et écrans (même méthode que les réglages de devises : API, écran, tests, vérification dans un vrai
navigateur) pour : bailleurs et accords, profils de décaissement, clés de cofinancement, mappings,
contrôles, exigences. Ordre : accords, profils, clés, contrôles.

**Preuve de fin** : un administrateur configure un bailleur de bout en bout dans le navigateur, sans appel
Python (questionnaire, question 14).

### Réalisation — B2 (API des bailleurs, accords, catégories et avenants)

Un administrateur configure un financement **de bout en bout sans développeur** : bailleur, accord, statut, catégories, avenants. Avant, tout passait par des appels de service Python ; et plusieurs refus (code déjà pris, montant négatif, dates incohérentes, pays trop long, devise inconnue) sortaient en **erreur serveur brute**.

- `GET/POST /api/v1/bailleurs/` ; `GET/POST /api/v1/projets/<id>/accords/` ; `GET …/accords/<id>/` (l'accord, ses catégories rangées racines d'abord, ses avenants, le montant initial **et** le montant courant) ; `POST …/statut/` ; `POST …/categories/` ; `POST …/avenants/`.
- Les bailleurs se désignent par leur **code**, les catégories parentes par leur **code dans l'accord**. Montants en chaînes exactes (jamais de flottant, de texte illisible, de NaN) ; un avenant rend sa situation avant/après et la variation ; l'accord ne change jamais de montant (l'avenant le porte).
- **Refus lisibles** : toutes les contraintes de la base connues (doublon de bailleur, d'accord, de catégorie, d'avenant ; montant négatif ; six paires de dates) deviennent un 422 `{code, message}` qui nomme la valeur ; la devise, la nature et le pays sont vérifiés **avant** la base (une clé étrangère ne se contrôle qu'en fin de requête, un pays trop long lève une erreur de données) ; une transition de statut interdite est un 409, comme ailleurs. Le gestionnaire commun traduit désormais `FinancementInvalide` et `AccordNonActif` en 422.
- Lecture : `consulter` ; écriture : `parametrer` (les bailleurs, propres à l'organisation : « paramétrer quelque part ») ; un accord s'adresse par son projet (404 sinon).
- Tests : 38 dans `test_api_accords_bd.py`, dont le **parcours complet** (accord configuré par HTTP : refusé à l'imputation tant qu'il n'est pas actif, accepté ensuite). Mutations détectées (vérifications de bailleur, nature, devise, pays, parent, habilitations, cloisonnement par projet, traduction de chaque contrainte, ordre des catégories, réponse 201, rechargement des montants) ; une survivante équivalente : l'inexistence d'un document d'avenant est aussi refusée par le service.
- **Limites** : pas d'écran ; **aucune API de dépôt de document** : un avenant désigne un `document_id` déjà enregistré (l'enregistrement d'un document se fait par service) : c'est la prochaine brique (B3) ; l'avenant n'ouvre pas encore la version du profil de décaissement correspondante (service `enregistrer_avenant` du niveau 3, non exposé) ; pas de modification d'un accord brouillon ni de suppression ; comptes bancaires non exposés.

### Réalisation — B3 (API des documents de référence)

Un administrateur dépose lui-même les documents que les avenants et les exigences citent (accord de financement, lettre de décaissement, manuel…), **sans développeur**. Avant, un avenant ne pouvait désigner qu'un document déjà déposé par un appel de service.

- `GET/POST /api/v1/projets/<id>/documents/` : liste ; dépôt avec les octets en **base64**. Le dépôt est **idempotent** (mêmes octets, même type, titre et version : le même document, **200** au lieu de **201**) ; des octets différents sous les mêmes type, titre et version sont **refusés** (« un document modifié est une nouvelle version »).
- `POST …/<doc>/remplacement/` : la nouvelle version chaîne l'ancienne (`remplace_par`), qui n'est jamais touchée ; la réponse liste les **exigences qui citaient l'ancien texte**, à revérifier.
- `GET …/<doc>/integrite/` : relit le fichier stocké et le compare à l'empreinte. Un fichier **altéré ou disparu n'est pas une erreur de requête** mais la réponse (`integre: false` et le problème) : le service journalise le constat avant de lever, et une réponse d'erreur l'aurait **annulé avec la transaction** de la requête (un test vérifie que la trace reste dans le journal d'audit).
- **La référence de stockage est interne** : jamais rendue, seule l'empreinte SHA-256 l'est.
- Lecture et intégrité : `consulter` ; dépôt et remplacement : `parametrer` ; un document s'adresse par son projet (404 sinon). Le gestionnaire commun traduit `DocumentInvalide` en 422.
- Tests : 23 dans `test_api_documents_bd.py`, dont le **parcours complet** (un document déposé par HTTP sert de pièce à un avenant, B2). Mutations détectées (référence de stockage non exposée, chaînage, 200/201, cloisonnement, habilitation de lecture, tri, exigences à revérifier, intégrité en réponse normale, dates, traduction des erreurs) ; une première survivante (la liste des exigences à revérifier, sans exigence dans les tests) a été comblée.
- **Limites** : le corps d'une requête ne dépasse pas **10 Mo** (`DATA_UPLOAD_MAX_MEMORY_SIZE`), donc un fichier d'environ 7 Mo en base64 : un manuel volumineux demandera un dépôt par morceaux ou par envoi de fichier (multipart), non fait ; pas de téléchargement du fichier (seulement ses métadonnées et son empreinte) ; pas d'écran ; pas de suppression (un document ne se supprime pas, on le remplace) ; les types de document sont ceux du modèle (six) ; CI GitHub toujours en panne.

### Réalisation — B4 : API des profils de décaissement

`niveau3_config/api.py` (+ `urls.py`), `niveau3_config/services/profils_decaissement.py`, catalogue
`profils_decaissement.json`, `tests/test_api_profils_decaissement_bd.py` (42 tests). Sous
`/api/v1/projets/<projet>/accords/<accord>/profils-decaissement/` : liste et création, lecture
(méthodes, règles par catégorie, comptes désignés, complétude du brouillon), `valider`, `activer`,
`rejeter`, `nouvelle-version` (allocations et jalons changés), `comparaison?avec=<version>`.

- **Même profil que les services** : le profil créé par l'API pilote la règle de calcul existante
  (`profil_en_vigueur`, `montant_a_retirer`) ; un test le prouve de bout en bout.
- **Cycle inchangé** : brouillon → validé (`valider`) → actif (`parametrer`), jamais de saut d'étape ;
  un profil actif ne se modifie pas, on crée une version. Catégories et comptes se désignent par leur
  CODE, résolus dans l'accord et le projet.
- **Refus précis** : chaque contrainte de la base (taux dans ]0, 1], deux minimums, plafond incohérent,
  jalons dans le désordre, doublons) sort en 422 `{code, message}` nommant la règle, jamais en 500.
- **Test corrigé en cours de route** : après un appel HTTP, `app.org_id` est remis à zéro ; mes premières
  assertions « rien n'est créé » comptaient 0 *parce que la RLS cachait tout*. Elles lisent maintenant la
  base avec l'organisation reposée (`_nb`), et six mutations (habilitations, correspondance des erreurs,
  traduction d'une contrainte, validation d'une méthode, complétude) sont détectées.
- **Limites assumées** : pas d'écran ; une règle ou un compte d'un brouillon ne se modifie pas
  individuellement (on rejette ou on recrée) ; `exigence` ne se désigne que par code, version validée ou
  active la plus récente ; les pièces exigées et les méthodes restent des ensembles fermés (migration).

### Réalisation — B5 : API des contrôles

`niveau4_reporting/controles/{api.py,urls.py}`, catalogue `controles_api.json`,
`tests/test_api_controles_bd.py` (34 tests). Sous `/api/v1/projets/<projet>/controles/` : liste (filtres
`code`, `status`), création, lecture, `valider`, `activer`, `rejeter` ; `bibliotheque/` (les contrôles
livrés et ceux déjà installés) et `bibliotheque/installer/` (installation en BROUILLON, `codes` facultatif).

- **Règle 9 tenue** : installer ne crée que des brouillons ; il faut une personne qui valide (`valider`)
  puis une qui active (`parametrer`). Un test déroule le parcours HTTP complet et prouve qu'un contrôle
  installé et activé par l'API refuse ensuite la validation d'une dépense sans catégorie (A4).
- **Langage borné (règle 5)** : l'expression d'un contrôle est vérifiée à la création par le langage de
  conditions ; un champ ou un opérateur hors schéma (`eval`…), un type de règle incohérent ou un
  contrôle automatique sans expression sont refusés en 422 `{code, message}`.
- **Cycle** : brouillon → validé → actif, pas de saut (409 `TRANSITION_INTERDITE`), rejet avec motif,
  nouvelle version = nouveau contrôle qui ferme le précédent à sa date d'effet.
- **Limites assumées** : pas d'écran ; la modification d'un contrôle se fait par nouvelle version ; les
  évaluations, décisions et dérogations restent sans API ; les contrôles de risque de la bibliothèque
  s'installent aux seuils par défaut (pas encore paramétrables à l'installation).

### Analyse — D3 : les modèles d'état BAD (A1, A2, A3, réconciliation du compte spécial)

**Décision : aucun modèle n'est livré dans ce lot, et c'est voulu.** Le moteur d'états produit des
tableaux de MONTANTS agrégés depuis le grand livre ou une source externe déclarée ; il ne produit pas de
formulaire d'identification ni de liste de pièces. Livrer un modèle qui a l'air d'un formulaire de la
Banque sans en contenir les rubriques serait inventer. Voici, formulaire par formulaire, ce que les
documents de la BAD exigent (pages vérifiées du manuel des décaissements, mars 2020), ce qui existe
et ce qui manque.

| Formulaire | Ce que la BAD y met (citations du profil BAD) | Ce qui existe déjà | Ce qui manque |
|---|---|---|---|
| **A1** — demande de décaissement | type de demande (remboursement, avance initiale, reconstitution, justification seule, paiement direct), numéro à 13 chiffres de l'accord, numéro de demande à 4 chiffres chronologique | `DemandeRetrait` : numéro (libre), type (retrait, réapprovisionnement, paiement direct, engagement spécial), accord, période | « avance initiale » et « justification seule » n'existent pas comme types ; le numéro n'est pas contrôlé (voir D2) ; pas de signataires autorisés |
| **A2** — état récapitulatif des dépenses (SOE) | numéro de demande, montant déjà payé par la Banque, preuve de paiement, cumul, part de la Banque dans le contrat | `etat_certifie` de la demande : dépenses par catégorie, pièce, date, montant, taux, montant à retirer | lien dépense → contrat et fournisseur ; « déjà payé par la Banque » (cumul des demandes précédentes) ; cumul courant |
| **A3** — activités budgétisées estimées | période d'utilisation de l'avance, avance demandée, budget annuel, date d'approbation | budget par catégorie (L4), date de décision de la demande | période d'utilisation, estimation par activité |
| **Réconciliation du compte spécial** (annexe 9) — **livrée par D4** | avances versées au compte, solde de clôture, justification jointe, dépenses déjà justifiées à la Banque, écart à expliquer | état du compte désigné : solde de clôture du relevé, avances reçues PAR PÉRIODE | cumul des avances DEPUIS L'OUVERTURE ; notion de « justification soumise à la Banque » par numéro de demande ; la source du moteur refuse tout compte qui n'est pas de type désigné (le compte spécial de la BAD est un autre type) |

**Ce qu'un modèle partiel aurait de trompeur** : avec l'existant on pourrait afficher « avances de la
période » et « solde de clôture », mais pas le cumul ni les justifications ; le « montant à justifier »
qui en sortirait serait faux dès que le compte a un solde d'ouverture. On ne l'a pas livré.

**Deux voies, à décider** (aucune n'est commencée) :
1. **Export au format bailleur d'une demande** : une fonction qui rend `etat_certifie` dans la mise en
   page A1/A2 de la BAD (Excel), la correspondance des colonnes vivant dans le profil de bailleur (donnée,
   pas du code). Les formulaires officiels de la BAD (Excel ou Word) sont nécessaires : l'annexe du manuel
   n'en donne qu'un exemple imprimé.
2. **Suivi des justifications du compte spécial** : ajouter le cumul des avances depuis l'ouverture et
   les justifications soumises à la Banque, puis un modèle `BAD_RECONCILIATION_CS` branché sur le moteur.

### Réalisation — D4 : suivi des justifications du compte spécial et réconciliation BAD

`niveau1_socle/tresorerie/{models.py,compte_special.py,api.py,urls.py}` (+ migration 0003),
`niveau4_reporting/moteur/source_compte_special.py`, modèle `BAD_RECONCILIATION_CS`
(`catalogue_modeles/bad_reconciliation_compte_special.json`), `tests/test_compte_special_bd.py` (35) et
`tests/test_api_compte_special_bd.py` (17). Ce que D3 listait comme manquant est maintenant là :

- **`JustificationCompteSpecial`** : « dépenses justifiées à la Banque sous la demande n° X », pour un
  compte de type SPÉCIAL. Ajout seul ; seule l'annulation (une fois, motivée) change une ligne. La base
  vérifie : compte spécial, même projet, même accord que le compte, demande SOUMISE à la Banque, jamais
  plus que ce que la demande retire, une seule justification vivante par demande.
- **Situation à une date** : avances cumulées DEPUIS L'OUVERTURE (seuls les encaissements appariés à une
  demande, appariements annulés exclus), solde du relevé, justification de la demande en cours (ligne 4)
  séparée des justifications précédentes (ligne 5). Un solde de relevé absent rend la situation
  INCOMPLÈTE : aucun écart n'est inventé.
- **Modèle d'état `BAD_RECONCILIATION_CS`** (lignes 2 à 7 de l'annexe 9, en montants) sur la source
  externe `compte_special`, publiable, scellé et régénérable comme les autres. L'écart n'est pas une
  assertion bloquante : le manuel demande de l'expliquer dans une note, pas de le rendre nul.
- **API** : `comptes/<id>/justifications-banque/` (liste, création), `justifications-banque/<id>/annulation/`,
  `comptes/<id>/situation-compte-special/?date=&demande=`, `comptes/<id>/rapport-compte-special/`.
- **Limites assumées** : le modèle d'état ne rend que des montants — pas le détail demande par demande
  du formulaire imprimé, ni la note d'explication de l'écart ; la justification est une SAISIE (elle
  n'est pas déduite automatiquement des lignes de la demande) ; une demande ne peut être justifiée
  qu'une fois soumise, donc la « demande en cours » doit l'être avant l'état ; la devise du compte est
  celle de la demande (aucune conversion) ; A1, A2 et A3 restent non livrés (voir D3).
- **Mutations** : quinze mutations (service, déclencheurs de la base, source, API) détectées ; une seule
  équivalente, l'habilitation `publier` de l'API que le service de publication impose déjà.

### Réalisation — D5a : limites de D4 levées

`niveau1_socle/tresorerie/{compte_special.py,api.py}`, migration 0004, tests ajoutés à
`tests/test_compte_special_bd.py` (43) et `tests/test_api_compte_special_bd.py` (21). Cinq limites de D4 :

- **Justification « saisie à la main »** : sans montant, la justification porte sur tout ce que la demande
  retire (`retrait_de_la_demande`). La saisie reste possible pour une justification PARTIELLE. Une demande
  qui ne retire rien (annulée) refuse le défaut.
- **« La demande en cours doit être soumise »** : la justification de la demande en cours (ligne 4) peut
  maintenant porter sur une demande encore PRÉPARÉE, comme le formulaire qui l'accompagne. La ligne 5 ne
  compte que des demandes soumises à la Banque ; une demande préparée non désignée, rejetée ou annulée
  reste LISTÉE dans le détail, marquée « non comptée », et l'écart l'explique. Rejeter une demande déjà
  justifiée la retire du total.
- **Détail demande par demande** : `situation-compte-special` rend la liste des justifications
  (demande, montant, date, en cours ?, comptée ?) ; c'est le détail des lignes 4 et 5 du formulaire
  imprimé, que le modèle d'état (des montants agrégés) ne peut pas porter.
- **Note qui explique l'écart** : `rapport-compte-special` accepte `note_ecart` (4 000 caractères au plus),
  gardée avec le rapport publié et donc SCELLÉE avec lui (la note change le sceau) ; elle n'entre dans
  aucun calcul.
- **Conversion de devise** : le compte et l'accord de la demande doivent avoir la MÊME devise, au service
  (message qui nomme les deux devises) et à la base (déclencheur). Aucune conversion n'est tentée : une
  conversion exigerait de choisir un taux, et le manuel n'en impose aucun.
- **Mutations** : onze mutations (service, déclencheur, API) détectées ; deux gardes de la base ont été
  éprouvées par une mutation sémantique, pas seulement par l'échec de la migration.
- **Reste** : le modèle d'état lui-même ne rend toujours que des montants agrégés (voir D4).

### Réalisation — D6 : documents, dépôt jusqu'à 50 Mio et téléchargement vérifié

`niveau3_config/{api.py,urls.py}`, `tests/test_api_documents_fichiers_bd.py` (16). Deux limites de B3 :

- **« Corps ≤ 10 Mo »** : le dépôt (et le remplacement) accepte désormais un envoi MULTIPART (champs `kind`,
  `title`, `version`, `issued_on` et le fichier `fichier`) jusqu'à la taille maximale du service, 50 Mio ;
  le JSON en base64 reste possible (environ 7 Mo). Même fichier par l'un ou l'autre : même document
  (idempotent d'un mode à l'autre). Au-delà de 50 Mio : refus net en 422.
- **« Pas de téléchargement »** : `GET …/documents/<id>/contenu/`. L'empreinte est vérifiée AVANT de servir ;
  un fichier altéré ou disparu n'est jamais servi (409 `DOCUMENT_ALTERE`, constat journalisé et non annulé).
  Le fichier est toujours une PIÈCE JOINTE (`attachment`, `nosniff`, `CSP: sandbox`, empreinte en
  `Digest`) : un document déposé reste une donnée non fiable. Son type vient de ses octets (PDF reconnu à
  sa signature), jamais de ce qu'il prétend être ; son nom est nettoyé (aucun `/`, guillemet ni saut de
  ligne). Chaque téléchargement est journalisé.
- **Limites assumées** : le fichier est lu en mémoire (jusqu'à 50 Mio) ; pas de reprise de transfert ni de
  téléversement par morceaux ; un reverse proxy placé devant l'application doit lui-même autoriser
  50 Mio.

### Réalisation — D7 : évaluations, décisions, dérogations et seuils de risque par API

`niveau4_reporting/controles/{api.py,urls.py,services.py}`, catalogues `controles.json` et
`controles_api.json`, `tests/test_api_evaluations_bd.py` (32). Trois limites de B5 :

- **« Évaluations, décisions, dérogations sans API »** : sous `/projets/<projet>/` :
  `evaluations-controles/` (le journal, du plus récent au plus ancien, filtrable par résultat, contrôle,
  type et identifiant d'objet, BORNÉ à 200 lignes) et `evaluations-controles/<id>/` (détail : décisions,
  justifications, dérogations) ; `…/decision/` (trancher un contrôle « à vérifier », `valider`),
  `…/justification/` (`saisir`), `…/derogation/` (demander, `saisir`) ; `derogations/` (liste, filtre
  `statut`) et `derogations/<id>/decision/` (approuver ou refuser, `valider`, jamais par le demandeur) ;
  `controles-en-attente/` (ce qui empêche d'avancer pour un objet, à une date) ;
  `dossier-conformite-objet/` (le fil d'un objet : le résultat « bloquant » initial reste lisible, suivi de
  la dérogation). Le journal reste en AJOUT SEUL : l'API ne modifie jamais une évaluation.
- **« Contrôles de risque aux seuils par défaut »** : `bibliotheque/installer/` accepte `seuils`
  (`RIS-CATEGORIE-SEUIL` : pourcentage exact de 0 à 100 en chaîne ; `RIS-AVANCE-NON-APUREE` : jours entiers
  ≥ 1 ; `RIS-REJETS-REPETES` : entier ≥ 0). Jamais un flottant, un booléen ni un texte illisible ; un seuil
  pour un autre contrôle, ou pour un contrôle qu'on n'installe pas, est refusé et rien n'est installé.
- **Toujours la règle 9** : installer ne crée que des brouillons, avec le seuil choisi ; il faut une
  personne qui valide puis une qui active.
- **Mutations** : douze (filtres, tri, borne, booléen, seuils) détectées.
- **Reste** : pas d'écran ; la modification d'un contrôle reste une nouvelle version ; les fabriques
  d'éligibilité et de pièces de la bibliothèque (période, nature, zone, bénéficiaires exclus) s'écrivent
  toujours par la création d'un contrôle avec son expression, pas par un formulaire dédié.

### Réalisation — D8 : un brouillon de profil de décaissement se modifie et s'abandonne

`niveau3_config/{api.py,services/profils_decaissement.py}`, tests ajoutés à
`tests/test_api_profils_decaissement_bd.py` (58). Limite de B4 : « une règle ou un compte d'un brouillon ne
se modifie pas individuellement ».

- **Choix** : `PUT …/profils-decaissement/<id>/` remplace TOUT le contenu d'un brouillon, d'un bloc, avec
  les mêmes règles et les mêmes refus qu'à la création. Corriger une règle ou un compte à l'unité aurait
  exigé des états intermédiaires invalides (allocations dépassant l'accord, compte sans catégorie…) ; le
  remplacement est ATOMIQUE : une erreur au milieu laisse l'ancien brouillon intact. L'identifiant, la
  version et l'accord ne changent pas.
- `DELETE` abandonne un brouillon ; la version suivante reprend le numéro (aucune version fantôme). Un
  profil validé, actif, remplacé ou rejeté ne se modifie ni ne se supprime : 422 qui renvoie à la nouvelle
  version, en plus du refus de la base. Habilitation `parametrer`, les deux actes sont journalisés.
- Une liste facultative (`comptes`) vide ou absente veut dire « aucun » : un remplacement peut retirer tous
  les comptes.
- **Exigence source** : désormais couverte par des tests (la plus récente version validée ou active d'un
  code ; une exigence seulement proposée ne justifie rien ; le remplacement peut la changer ou la retirer).
- **Mutations** : treize détectées ; une survivante au départ (l'exigence non reportée) a donné les tests
  ci-dessus.
- **Reste** : la désignation de l'exigence par son code reste voulue (c'est ce que voit un administrateur) ;
  pas d'écran.

### Réalisation — D9 : l'exception d'éligibilité des frais d'audit (fin propre d'une catégorie)

`niveau3_config/{models.py,migrations/0014,services/decaissement.py,services/completude.py,api.py}`,
`niveau2_profils/{services/gabarit.py,catalogue/bad.json}`, tests dans `test_eligibilite_depenses_bd.py`,
`test_api_profils_decaissement_bd.py` (64) et `test_branchement_controles_bad_bd.py`. Limite de D2 :
« l'exception dépenses d'audit jusqu'à 6 mois après la clôture n'est pas modélisée ».

- **Constat** : la fenêtre d'éligibilité retient la fin la plus PRÉCOCE entre l'accord et la catégorie
  (décision de A5, testée). Une catégorie ne pouvait donc que resserrer la fin, jamais l'étendre : la
  règle de la BAD (frais d'audit éligibles 6 mois après la clôture, DH p.23) était inexprimable.
- **Choix** : plutôt que d'inverser la règle générale (qui aurait élargi silencieusement l'éligibilité
  de tous les bailleurs), un CHOIX EXPLICITE sur la règle de catégorie : `fin_propre_a_la_categorie`
  (faux par défaut). Vrai, la fin de la catégorie prime sur celle de l'accord ; elle doit exister (la base
  l'impose) ; elle ne touche pas le début. Reprise par une nouvelle version, lisible et comparable.
- **Visible, pas silencieux** : tant que le profil est un brouillon, la complétude signale par un
  AVERTISSEMENT (`fin_categorie_apres_accord`) toute fin propre postérieure à celle de l'accord ; il ne
  bloque pas, la personne qui valide le justifie. Une fin égale à celle de l'accord n'est pas signalée.
- **Gabarit BAD** : il suggère la règle (`regles_suggerees` : rôle `frais_d_audit`, fin = clôture + 6 mois,
  fin propre) ; il ne sait pas quelle catégorie du projet porte ce rôle, l'administrateur l'applique à la
  bonne. Le jalon de décaissement n'est pas touché.
- **Mutations** : douze détectées (une survivante, la borne de l'avertissement, a donné un cas de test).
- **Limites assumées** : l'exception vaut pour le contrôle de validation d'une écriture
  (`ELIG-PERIODE-ACCORD`) ; la préparation d'une demande ne contrôle déjà que la fin de la catégorie, pas
  celle de l'accord, donc elle est cohérente ; aucune catégorie n'est marquée « audit » dans le modèle :
  le rôle reste porté par le CHOIX de l'administrateur.

### Réalisation — D2 : branchement des contrôles BAD

`niveau2_profils/{services/gabarit.py,api.py,urls.py}`, `bad.json` (champ `branchement` sur les douze
contrôles), `tests/test_branchement_controles_bad_bd.py` (21 tests). Le profil BAD dit désormais, pour
chaque règle de contrôle, COMMENT elle est appliquée :

- **Quatre règles sont appliquées** par ce qui existe : dates d'éligibilité (jalon `eligibility_date` du
  profil de décaissement + contrôle `ELIG-PERIODE-ACCORD`), allocations par catégorie (règles du profil +
  `BUD-ALLOCATION`, `BUD-CATEGORIE`, `COD-CATEGORIE`), délai de soumission (`disbursement_deadline`,
  contrôlé à la préparation d'une demande), pièces du remboursement (méthodes du profil +
  `PIE-ETAT-CERTIFIE`).
- **Huit règles ne sont appliquées par rien**, et le disent avec leur raison (bilingue) : une seule devise
  par demande, numérotation (4 chiffres, suffixes), coordonnées du paiement direct, même méthode par
  contrat, conditions de reconstitution du compte spécial (50 % / 100 %, 6 mois), usage du compte
  spécial, audit annuel (un délai en mois), signataires. Cause commune : le modèle n'a pas le champ
  (une demande ne porte ni devise ni contrat ; son numéro est libre).
- **Gabarit** : `GET /projets/<p>/profils-bailleurs/<nom>/gabarit-decaissement/?date_cloture=…` calcule ce
  que le profil énonce — pour la BAD, `disbursement_deadline` = clôture + 4 mois (dernier jour du mois si
  besoin) —, liste les contrôles de la bibliothèque et les règles non branchées, et nomme ce qui reste à
  décider (régime, catégories, taux, comptes, pièces). Il ne crée rien ; l'administrateur soumet le corps
  à l'API de B4. Un test déroule gabarit → profil actif → demande acceptée le dernier jour, refusée le lendemain.
- **Limites assumées** : aucun contrôle de la bibliothèque n'est ajouté ni activé (règle 9) ; l'exception
  « dépenses d'audit jusqu'à 6 mois après la clôture » n'est pas modélisée ; le gabarit dérive un seul
  jalon ; les profils squelettes n'ont aucun branchement.

### Réalisation — D1 : profil BAD d'après les documents de la Banque

Cinq documents de la BAD ont été lus (manuel des décaissements 03/2020, lignes directrices de rapports et
d'audit non datées, manuel de gestion financière 04/2014, lignes directrices de gestion financière 2019,
format du PCR 2009). `niveau2_profils/catalogue/bad.json` passe de squelette à **version 2** : 31 éléments
(documents de référence identifiés par SHA-256, nomenclatures des méthodes/types de demande/devises, dix
familles d'états, douze contrôles avec leurs paramètres chiffrés), **80 citations** littérales avec page.
Registre : `SRC:bailleur:420` à `424` (fiabilité F2 : le manuel dit n'être « ni contractuel ni juridique »).

- **Vérifiable** : `manage.py verifier_citations_profil bad --dossier <dossier des PDF>` reconnaît chaque PDF
  par empreinte et cherche chaque extrait à sa page ; un document absent rend ses citations *non
  vérifiables* (échec, sauf `--tolerer-absents`). Exécuté sur les cinq PDF fournis : 80 / 80.
- **Seul délai chiffré livré** : IFR trimestriel, 45 jours (manuel 2014). Les états audités (« six mois ») sont
  annuels **sans décalage en jours** : un délai en mois n'est pas converti. Toutes les exigences restent
  `optional` ; l'import ne crée que des exigences proposées (règle 9).
- **Divergence relevée** : les anciennes lignes directrices disent « trois mois » pour les états intermédiaires,
  le manuel de 2014 « 45 jours » ; le format se convient à l'évaluation du projet, l'accord prime.
- **Limites assumées** : les documents ne donnent ni montants, ni taux de financement, ni catégories (propres
  à l'accord et à la lettre de décaissement) ; ils n'imposent ni FIFO ni méthode de taux de change ; les
  lignes directrices non datées ont une couche texte dégradée, lues mais jamais citées littéralement ;
  les contrôles du profil sont des **descriptions paramétrées** : aucun n'est encore branché sur la
  bibliothèque de contrôles exécutés à la validation. Les modèles d'état (`BAD_A1`…) n'existent pas encore.

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

### Réalisation — Lot 2-B : pagination optionnelle des listes
`core/pagination.py` (`paginer`, plafond 500) et `core.api.reponse_liste`. Le corps reste un tableau JSON ;
`?limite=` (1 à 500) et `?decalage=` (≥ 0) ; en-têtes `X-Total-Count` et, s'il y a une suite,
`X-Decalage-Suivant`. Sans `limite` : la liste entière jusqu'à 500 lignes, au-delà un refus 422 demande
de paginer. Un queryset non trié est une erreur de programmation (`TypeError`).
**Listes paginées :** bailleurs, accords d'un projet, taux de change (les taux étaient tronqués en silence à 500).
**Listes NON encore paginées (à faire, une par une avec son test) :** clés de cofinancement, documents de
référence, profils de décaissement, contrôles, évaluations, dérogations, justifications du compte spécial,
demandes de retrait, listes de marchés et de trésorerie. Elles restent non bornées.
Tests : `test_pagination.py` (logique), `test_api_pagination_bd.py`, `test_api_pagination_financements_bd.py` ;
mutation vérifiée (sans la limite, les 4 tests d'API échouent).

### Réalisation — Lot 2-C : jeton d'API
Un programme appelle l'API sans mot de passe : `Authorization: Bearer <organisation>.<secret>`, comme l'accès
auditeur (l'organisation, en clair, pose `app.org_id` pour la transaction, PUIS on cherche sous la RLS ; aucune
exception à l'isolation). Table `organisations_jetonapi` (migrations 0006/0007) : empreinte SHA-256 du secret
(jamais le secret), préfixe de 8 caractères, expiration, révocation, dernier usage ; RLS ; un déclencheur interdit
toute modification hors `revoque_le` (une fois) et `dernier_usage`, et toute suppression.
API : `POST /api/v1/jetons/` (session obligatoire ; `libelle`, `duree_jours` 1 à 365 ; le jeton n'est rendu qu'UNE
fois), `GET /api/v1/jetons/` (les siens, sans secret), `POST /api/v1/jetons/<id>/revocation/` (idempotent ; le
jeton d'autrui est introuvable). Le jeton agit avec les droits de son propriétaire : les habilitations
s'appliquent comme en session. Pas de CSRF pour un jeton (aucun cookie), CSRF conservé pour la session.
Journal : `api_token_created`, `api_token_revoked`. Un jeton refusé rend toujours 401 `{code, message}`
(`NON_AUTHENTIFIE`, `WWW-Authenticate: Bearer`), jamais 500 ni le `{"detail"}` de DRF (même changement de forme
pour l'accès auditeur).
Tests : `test_jetons_api_bd.py` (21) ; 7 mutations tuées (comparaison d'empreinte, révocation, expiration,
propriétaire inactif, création par jeton, révocation d'autrui, dernier usage) ; table ajoutée au test d'isolation.
**Limites assumées :** la comparaison en temps constant porte sur les jetons de même préfixe, pas sur la recherche
du préfixe ; la « deuxième requête simultanée » n'est pas testée avec de vrais fils ; le dernier usage n'est écrit
qu'une fois par minute au plus ; aucune limitation de débit sur les essais de jeton ; pas d'écran de gestion des
jetons ; un jeton n'est pas lié à des projets ou des opérations précis (il a TOUS les droits de son propriétaire) ;
pas de rotation. **À faire relire avant l'exploitation** (plan 07 §6.C).

### Réalisation — Lot 3-A : numérotation des demandes au format BAD
Règle du manuel des décaissements BAD (p. 24-25) : numérotation chronologique de 4 chiffres au plus, suffixe
d'agence de 3 lettres, un numéro annulé n'est jamais réattribué, une suite distincte par accord (prêt, don).
`Accord.format_numero_demande` (`standard` par défaut, ou `bad`) et `Accord.suffixe_agence` (3 lettres majuscules,
obligatoire en `bad`, interdit en `standard`) ; table `CompteurDemande` (un compteur par accord, ligne verrouillée à
l'attribution, déclencheur : ne décroît jamais, ne se supprime pas) ; le numéro `bad` est `{séquence sur 4 chiffres}
{suffixe}` (par exemple `0001ADB`), refus net au-delà de 9999. Le format `standard` (`DRF-<accord>-<n>`) ne change pas.
Règle 7 : le format ne se change plus dès qu'une demande existe (service ET déclencheur de base ; la garde de l'accord
activé laisse passer ces deux colonnes seulement). API : `numerotation` sur chaque accord (lecture) et
`POST /projets/<id>/accords/<id>/numerotation/` (`parametrer`, 422 au format `{code, message}`, 403 sans droit).
**Changement de contrainte :** `uq_demande_numero` devient unique PAR ACCORD (`org_id, accord, numero`) : deux accords
au format BAD ont chacun leur suite « 0001ABC ». Le format standard, qui contient le numéro d'accord, n'est pas touché.
Tests : `test_numerotation_bad_bd.py` (17, dont deux préparations simultanées sur de vrais fils),
`test_numerotation_demandes_bd.py` (numérotation `standard` sérialisée par un verrou par accord, constat 4 de la revue),
3 tests d'API ; 5 mutations tuées (verrous, plafond, format, gel après demandes, validation du suffixe).
**Limites assumées :** le type BAD d'une demande (avance initiale, reconstitution, remboursement) se déduira à
l'export (Lot 8) ; la justification seule reste une `JustificationCompteSpecial` (pas de suffixe `JUS` pour l'instant) ;
un accord déjà utilisé en `standard` ne peut pas passer en `bad` (règle 7) : l'accord doit être configuré AVANT sa
première demande ; la contrainte d'unicité par accord ne se retrouve pas dans l'export Excel.

### Réalisation — Lot 3-B : lier une dépense à un contrat, « une seule devise par demande » (partie livrée)
`LigneDemande.contrat` (clé étrangère facultative vers `marches.Contrat`) et `preparer_demande(..., contrats={ligne:
contrat})`. Un déclencheur de base impose que le contrat soit du MÊME projet que la demande (le service le refuse
déjà ; le témoin du test prouve que le refus de base vient bien du contrat). **Contrôle « une devise par demande »
(manuel BAD, p. 25) :** les contrats d'une demande sont dans une seule devise ; refus 422 qui nomme les devises ;
sans contrat, rien n'est contrôlé (état antérieur). Le profil BAD déclare désormais ce contrôle et le contrôle de
numérotation comme appliqués par un nouveau type de branchement `service_decaissement` (la fonction citée existe,
vérifié par test). Tests : `test_contrat_demande_bd.py` (8), `test_branchement_controles_bad_bd.py` mis à jour ;
4 mutations tuées (devises, enregistrement, projet du contrat, ligne étrangère).
**NON LIVRÉ — « même méthode pour toutes les demandes d'un contrat » (`BAD-CTRL-METHODE-PAR-CONTRAT`) :** il reste
`non_branche`, et son texte le dit. Raison : une dérogation (`Derogation`) ne s'attache qu'à l'évaluation d'un
contrôle de la bibliothèque, sur un objet. Il faut donc (1) un contrôle de bibliothèque évalué à la préparation
sur l'objet « contrat », avec un champ de contexte « méthode identique à celle des demandes vivantes du contrat » ;
(2) que l'évaluation bloquante survive au refus de la préparation (aujourd'hui l'exception défait la transaction,
donc l'évaluation à laquelle la dérogation se rattacherait disparaît) ; (3) que la préparation consulte
`controles_en_attente`. C'est un chantier de plusieurs jours qui touche le schéma des règles, le catalogue de la
bibliothèque (20 contrôles figés par des tests) et le circuit de dérogation : je ne l'ai pas fait à la hâte.
**Limites :** le contrat n'est pas encore proposé par l'API HTTP des demandes (il n'y en a pas) ; une demande dont
les dépenses ne portent aucun contrat n'est pas contrôlée.

### Réalisation — Lot 4 : périodes de rapport libres
Un état peut porter une colonne `{"code": "PER", "period": "range"}` : elle lit les paramètres `plage_debut` et
`plage_fin` (texte ISO `AAAA-MM-JJ` ou objet `date`, **bornes incluses**) et somme les lignes dont la date comptable
(`accounting_date`, déjà exposée par la vue `moteur_ligneecriture` : aucune migration) est dans la plage. Les noms de
paramètres sont une liste blanche de deux ; leurs valeurs sont des paramètres SQL. Refus net (`ModeleEtatInvalide`) :
fin avant début, date illisible (y compris un horodatage, un entier ou une chaîne piégée), un seul des deux paramètres,
une colonne de plage sans paramètres, une plage mélangée à une autre période de colonne dans le même état. Le jeu de
données scellé est borné par la plage elle-même (`project_id = … AND accounting_date BETWEEN … AND …`), donc une
écriture postérieure DANS la plage est nommée par la régénération et une écriture hors plage ne la dérange pas. Publication :
la période du rapport doit être la plage demandée (`rapports.periode_hors_plage`) ; les dates se scellent en texte ISO.
**Écart avec le plan 07 :** les paramètres s'appellent `plage_debut`/`plage_fin`, pas `date_debut`/`date_fin` : ces
deux noms servent déjà aux sources externes de trésorerie (compte désigné et compte spécial), et les réutiliser aurait
fait basculer ces états en « plage libre ».
Tests : `test_periodes_libres_bd.py` (20) : somme de deux plages contiguës = plage totale, bornes (veille, lendemain),
refus, scellé identique pour deux plages identiques et différent pour une autre, nommage d'une écriture postérieure ;
7 mutations tuées.
**Limites assumées :** une plage ne se mélange pas à une colonne de période d'exercice (un état « période + cumul » reste
à construire) ; aucune API HTTP générale ne publie un rapport (seul l'état du compte désigné a la sienne) : la plage
s'utilise par `publier_rapport(params={"plage_debut": …, "plage_fin": …})` ; le mapping applicable est celui que
l'appelant passe (on ne choisit pas encore la version de mapping « à la date de fin de plage ») ; pas de sélecteur de
période dans l'écran du tableau de bord.

### Réalisation — Lot 5, écran E4a : accords (consultation, statut, numérotation)
Route `/accords?projet=&accord=` (menu « Accords »). Liste des accords d'un projet (numéro, bailleur, nature, statut en toutes
lettres, montant courant en chaîne) ; détail : dates clés, catégories de dépenses (la sous-catégorie dit « sous <parent> » et est
décalée), avenants, numérotation des demandes de retrait. Avec le droit de paramétrer : changer le statut (nouveau statut +
motif ; le serveur reste l'autorité des transitions, elles ne sont PAS dupliquées à l'écran : un refus 409 est affiché tel quel)
et régler la numérotation (standard ou BAD ; le suffixe de 3 lettres MAJUSCULES est vérifié avant l'envoi, le format standard
n'envoie aucun suffixe ; le refus du serveur « a déjà des demandes » s'affiche). Sans le droit, aucune action n'est proposée.
Tests : `Accords.test.tsx` (18) ; 9 mutations tuées. 222 tests, typage, lint passent.
**NON LIVRÉ (reste de l'écran E4) :** création d'un accord, d'une catégorie et d'un avenant. Limites : pas de pagination ; les
bailleurs ne sont pas listés à part (leur code figure sur chaque accord).

### Réalisation — Lot 5, écran E8 : taux de change
Route `/taux-de-change` (menu « Taux de change »). Liste des taux les plus récents d'abord, filtrable par devise et par type
(les filtres partent au serveur ; la liste est bornée à 200 lignes par `?limite=`, et l'écran le dit quand la limite est
atteinte) ; formulaire d'enregistrement (devise du catalogue sans la monnaie de tenue, date, type, taux, source facultative)
visible seulement avec le droit de paramétrer sur un projet. Le taux est une CHAÎNE décimale : la virgule est acceptée et
convertie en point, mais ni `0`, ni négatif, ni exposant (`1e3`), ni deux points ne partent ; la précision n'est jamais passée
par un `number` (`0.1000000000000000001` part intact) ; la date est exigée avant l'envoi ; le refus du serveur (taux déjà
enregistré ce jour) s'affiche tel quel sans effacer la saisie ; un double clic n'envoie qu'un taux.
Tests : `TauxDeChange.test.tsx` (20) ; 8 mutations tuées (nombre, zéro, exposant, virgule, date, double clic, droit,
message serveur). 223 tests, typage, lint et build passent.
**Limites :** pas de modification ni de suppression d'un taux (le serveur n'en offre pas : on enregistre un autre taux) ;
pas de saisie en lot ; pas d'import de fichier ; 200 taux affichés au plus.

### Réalisation — Lot 5, écran E1a : profils de décaissement (consultation et décisions)
Route `/profils-decaissement?projet=&accord=&profil=` (menu « Profils de décaissement »). Choix du projet puis de
l'accord ; liste des versions (état en toutes lettres, régime, effet) ; détail d'une version : dates clés, méthodes (et
pièces exigées), règles par catégorie (taux et allocations en CHAÎNES, jamais en `number`), comptes désignés, et pour un
brouillon l'encadré de complétude (points bloquants et avertissements, message du serveur tel quel). Actions : Valider
(désactivé tant que le brouillon est incomplet, le serveur restant l'autorité et son refus affiché), Activer, Rejeter
(motif obligatoire avant tout envoi), Supprimer le brouillon (confirmation en deux temps). Sans le droit, aucune action
n'est proposée et l'écran le dit. Un double clic n'envoie qu'une demande. Le faux serveur sait répondre aux écritures
(tâche 9.1) et peut retarder une réponse.
Tests : `ProfilsDecaissement.test.tsx` (15) ; 7 mutations tuées (validation d'un incomplet, double clic, motif, confirmation,
message serveur masqué, droits, taux converti en nombre). Les 219 tests, le typage, le lint et la construction passent.
**NON LIVRÉ dans cette tranche (reste de l'écran E1) :** le formulaire de création et d'édition d'un brouillon (régime,
jalons, méthodes, règles, comptes, taux validé avant envoi), « Créer une nouvelle version », la comparaison de deux
versions et le pré-remplissage depuis le gabarit BAD. Limites : pas de pagination ni de recherche dans la liste ; les
droits affichés suivent `valider` (valider, rejeter) et `parametrer` (activer, supprimer) comme le serveur.

---

*Retour : [guide de démarrage](03_GUIDE_DEMARRAGE.md) · [lots L5 à L10](05_PLAN_LOTS_L5_A_L10.md)*
