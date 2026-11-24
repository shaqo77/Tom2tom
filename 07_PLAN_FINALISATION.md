# 07 — Plan de finalisation du projet SIGF

**Pour qui ?** Une personne qui débute en développement. Chaque tâche dit : *quoi faire, dans quel fichier, avec
quelle commande, comment vérifier, et quand s'arrêter pour demander.* Suivez l'ordre. Ne sautez aucune étape.

**Légende.** ✅ fait · ⏳ à faire, rien ne vous bloque · ⛔ bloqué : il faut un document ou une décision (le plan
vous dit lesquels, et ce qu'il faut faire en attendant).

**La règle d'or : on n'invente rien.** Si un chiffre, un délai, un nom de champ ou une règle d'un bailleur ne figure
pas dans un document que vous avez sous les yeux, vous vous arrêtez et vous demandez. Un profil de bailleur ou un
contrôle faux est pire qu'un profil absent.

Ce document complète `06_PLAN_LOT_L11_MOTEUR_MULTIBAILLEUR.md` (notes « Réalisation » de chaque tâche livrée) et
`CLAUDE.md` (règles du projet). **Lisez `CLAUDE.md` en entier avant de commencer** (15 minutes).

---

## Table des matières

0. Les 10 règles à ne jamais enfreindre
1. Mise en place de votre poste (une seule fois)
2. Comment on travaille : le cycle de chaque tâche
3. État de départ
4. **Lot 0** — Débloquer la CI et fusionner D4 à D9
5. **Lot 1** — Revue de code de L11
6. **Lot 2** — Transversal : mot de passe, pagination, jeton d'API, économie de CI
7. **Lot 3** — BAD : numérotation des demandes, lien dépense → contrat
8. **Lot 4** — Périodes de rapport libres (C3)
9. **Lot 5** — Les écrans d'administration (frontend)
10. **Lot 6** — Recette multibailleur (phase F)
11. **Lot 7** — Remplir un profil de bailleur (procédure) ⛔
12. **Lot 8** — Export des formulaires BAD A1, A2, A3 ⛔
13. **Lot 9** — Import et export Excel fidèles (C4, C5) ⛔
14. **Lot 10** — IA documentaire (phase E) ⛔
15. **Lot 11** — Exploitation
16. Annexes : gabarits de code, pièges connus, glossaire, liste de contrôle d'une PR

---

## 0. Les 10 règles à ne jamais enfreindre

(Extrait de `CLAUDE.md` : elles priment sur tout le reste.)

1. **Aucun `float` sur un montant.** `Decimal` partout, colonnes `NUMERIC`. En JSON, un montant est une *chaîne*
   (`"1250.50"`). En JavaScript, un montant passe par `decimal.js`, jamais par un `number`.
2. Aucune modification d'une écriture comptabilisée : on contre-passe.
3. Aucun trou dans la numérotation d'un journal.
4. **Aucun filtre `org_id` écrit à la main.** L'isolation entre organisations est faite par la base (Row-Level
   Security). Si vous écrivez `.filter(org_id=...)` dans du code métier, vous avez fait une erreur.
5. Aucune `eval`/`exec` sur une formule ou une condition saisie par un utilisateur : on passe par le langage borné.
6. Aucune écriture dans une période close.
7. Aucune modification d'une configuration déjà utilisée : on crée une **nouvelle version** (`version`,
   `valid_from`, `valid_to`). Validité `[valid_from, valid_to[` : `valid_to` est **exclu**.
8. Aucune génération de rapport avec un mapping incomplet.
9. Aucune activation automatique d'une exigence ou d'un contrôle : une personne habilitée active.
10. Aucun `left`/`right` écrit en dur dans le CSS (l'arabe viendra) : utilisez `margin-inline-start`,
    `padding-inline-end`, `text-align: start`, etc.

Et deux conventions : les **libellés** sont des JSON `{"fr": "...", "en": "..."}` (jamais `label_fr`) ; le **domaine
est en français** (modèles, champs, tests, messages).

---

## 1. Mise en place de votre poste (une seule fois)

### 1.1 Outils à installer
`git`, **Python 3.12**, **uv** (gestionnaire d'environnements Python), **Docker**, **Node.js 22**, le client **psql**.

### 1.2 Récupérer le code
```bash
git clone https://github.com/osmanawalehadn007/tom-tom.git
cd tom-tom
git checkout main
```
Le dépôt de travail est `osmanawalehadn007/tom-tom`. (L'ancien dépôt `wilsan007/Tom2pro` n'est plus utilisé.)

### 1.3 Backend : environnement Python
```bash
cd backend
uv venv --python 3.12 .venv
uv pip install -r pyproject.toml --group dev
```

### 1.4 Base de données locale
Depuis la racine du dépôt :
```bash
docker compose -f infra/docker-compose.yml up -d
scripts/bootstrap_db.sh          # une seule fois : crée les rôles sigf_owner et sigf_app
PGPASSWORD=ci psql -h localhost -U sigf_owner -d sigf -v ON_ERROR_STOP=1 -c "
  ALTER ROLE sigf_app CREATEDB;
  GRANT CONNECT ON DATABASE sigf TO sigf_app;
  GRANT USAGE ON SCHEMA public TO sigf_app;
  ALTER DEFAULT PRIVILEGES FOR ROLE sigf_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sigf_app;
  ALTER DEFAULT PRIVILEGES FOR ROLE sigf_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO sigf_app;"
```
(Ce bloc est celui de la CI, voir `.github/workflows/ci.yml`. La suite de tests crée sa propre base `test_sigf`.)

### 1.5 Variables d'environnement (à remettre dans chaque nouveau terminal)
```bash
export SECRET_KEY=ci-only DEBUG=False ALLOWED_HOSTS=localhost
export DATABASE_URL=postgres://sigf_app:ci@localhost:5432/sigf
export DATABASE_OWNER_URL=postgres://sigf_owner:ci@localhost:5432/sigf
```
Ne créez **jamais** un fichier `backend/.env` avec de vrais identifiants. Ne vous connectez **jamais** à la base de
production, même en lecture.

### 1.6 Vérifier que tout marche
Depuis `backend/` :
```bash
./.venv/bin/python manage.py check                              # doit répondre « no issues »
./.venv/bin/python manage.py migrate --settings=config.settings.migrate
./.venv/bin/pytest -q tests/test_conventions.py                  # un petit test pour commencer
./.venv/bin/ruff check . && ./.venv/bin/ruff format --check .    # le style
```
Si une commande échoue ici, **ne continuez pas** : relisez l'étape 1.4 et 1.5.

### 1.7 Frontend
Depuis `frontend/` :
```bash
npm ci
npm run typecheck && npm run lint && npm test && npm run build
```

### 1.8 Deux faits à savoir sur les tests de base de données
* **Ne lancez jamais deux `pytest` en même temps sur la même base** : ils se détruisent mutuellement la base de test
  (`test_sigf`) et vous aurez des dizaines d'erreurs incompréhensibles.
* **La suite complète dure environ 50 minutes.** Pendant le développement, lancez seulement les fichiers qui vous
  concernent : `./.venv/bin/pytest -q --no-cov -p no:cacheprovider tests/test_mon_fichier.py`. La CI lance tout.

---

## 2. Comment on travaille : le cycle de chaque tâche

Faites **une branche par tâche**, avec un nom court et parlant : `L11-E1-ecran-profils`. Les messages de commit sont
en français : `L11-E1: écran de liste des profils de décaissement`.

### 2.1 Les 9 étapes

1. **Créer la branche** depuis `main` à jour : `git checkout main && git pull && git checkout -b <nom>`.
2. **Lire** les fichiers que le plan vous cite, et la note « Réalisation » correspondante dans le plan 06. Cela
   prend 15 à 30 minutes et évite de refaire ce qui existe.
3. **Écrire le test d'abord**, le lancer, **vérifier qu'il échoue** (et pour la bonne raison).
4. **Écrire le code** minimal qui fait passer le test.
5. **Style** : `./.venv/bin/ruff check --fix . && ./.venv/bin/ruff format .` (lignes de 100 caractères au plus).
6. **Lancer les tests concernés** (étape 1.8), puis ceux des modules voisins.
7. **Vérifier par mutation** (voir l'annexe E) : casser volontairement votre code, un endroit à la fois, et vérifier
   que **un test échoue**. Si aucun test n'échoue, il manque un test : ajoutez-le.
8. **Documenter** : ajouter la note « Réalisation » dans `06_PLAN_LOT_L11_MOTEUR_MULTIBAILLEUR.md` (gabarit en annexe
   D), avec les **limites que vous assumez**.
9. **Pousser et ouvrir une pull request**, attendre que la CI soit **verte**, puis fusionner (§2.3).

### 2.2 Définition de « terminé »
Une tâche est terminée seulement si **tout** ceci est vrai :
* le code fait ce que la tâche demande ;
* un test le prouve, **et ce test échouait avant votre code** ;
* `ruff check` et `ruff format --check` sont propres ;
* les règles 1, 4 et la règle des libellés sont respectées ;
* si vous avez ajouté une table : migration + sécurité par organisation (annexe C) + dictionnaire de données
  régénéré (`./.venv/bin/python manage.py generer_dictionnaire`) ;
* tous les messages passent par le catalogue `core/locales/{fr,en}/<domaine>.json` ;
* la note « Réalisation » est écrite ;
* **la CI est verte** sur la pull request.

### 2.3 Pull request, CI, fusion
```bash
git push -u origin <nom-de-branche>
```
Ouvrez la pull request sur GitHub : base `main`, titre = le message de commit, description = ce que vous avez fait,
les limites, et comment vérifier. **La CI** (`.github/workflows/ci.yml`) lance `ruff`, les migrations, **tous** les
tests Python avec la couverture, puis les contrôles du frontend (types, style, tests, construction). Elle prend 40 à
60 minutes.
* **Rouge ?** Ne fusionnez pas. Lisez l'erreur, corrigez, repoussez. Ne **supprimez jamais un test, ne le marquez
  jamais « ignoré »** pour obtenir du vert.
* **Verte ?** Fusionnez avec l'option **« Create a merge commit »** (pas « squash » : les branches empilées en
  dépendent).
* **Ne poussez jamais directement sur `main`.**

### 2.4 Les pièges déjà rencontrés (lisez-les, ils vous feront gagner des heures)
Voir l'annexe F. Les trois plus fréquents :
1. Dans un test d'API, après un appel HTTP, la base « oublie » l'organisation : un `.count()` renvoie **0 même si
   la ligne existe**. Il faut refaire `SET app.org_id = ...` (annexe B). Un test qui vérifie « rien n'a été créé »
   sans cela **passe à vide**.
2. Une action du journal d'audit ne dépasse pas **32 caractères**.
3. Chaque message d'erreur est une clé du catalogue avec **exactement** les paramètres qu'elle utilise ; le test
   `tests/test_catalogue_messages.py` le vérifie.

---

## 3. État de départ

Dépôt de travail : `osmanawalehadn007/tom-tom`.

| Élément | État |
|---|---|
| Lots L0 à L10 (fondations, moteur d'états, contrôles, conformité, reprise, marchés, trésorerie, tableau de bord) | ✅ fusionnés |
| L11 phase A (A1 à A6 : consolidation, répartition entre bailleurs, contrôles à la validation, éligibilité, taux, base comptable) | ✅ fusionnée |
| L11 phase B : B1 clés, B2 accords, B3 documents | ✅ fusionnés (avec D1) |
| D1 (profil BAD v2), B4 (API profils de décaissement), D2 (branchement des contrôles BAD), B5 (API contrôles), D3 (analyse des modèles d'état BAD) | ✅ fusionnés dans `main` (PR #1 à #5) |
| **D4** (suivi des justifications du compte spécial, modèle d'état `BAD_RECONCILIATION_CS`) | ⏳ **PR #6 ouverte, CI rouge** : voir Lot 0 |
| D5 (limites de D4), D6 (documents multipart + téléchargement), D7 (évaluations, dérogations, seuils), D8 (brouillon de profil modifiable), D9 (exception d'audit) | ⏳ branches poussées, **pas de PR** |
| Écrans d'administration, rapports par bailleur, profils des autres bailleurs, IA | ⏳ / ⛔ voir les lots |
| T14 (capture hors ligne), L2-T05/T06 (paquets réglementaires) | **non livrés, volontairement** : ne les commencez pas |

Les branches `D5-compte-special-limites`, `D6-documents-fichiers`, `D7-controles-evaluations`,
`D8-profil-brouillon-modifiable`, `D9-exception-audit-eligibilite` existent sur `origin` ; chacune part de la
précédente (D5 de D4, D6 de D5, etc.).

---

## 4. Lot 0 — Débloquer la CI et fusionner D4 à D9 ⏳ (à faire en premier)

**Pourquoi d'abord ?** Tant que D4 n'est pas fusionné, cinq branches (D5 à D9) restent bloquées derrière lui, et tout
ce que vous écrirez ensuite hérite du problème.

**Le problème.** La pull request n° 6 (`D4-compte-special-justifications`) a échoué deux fois en CI, à l'étape
« Tests » du job backend. Le nom du test en échec est inconnu : les journaux accessibles montrent seulement le
conteneur PostgreSQL. Sur le poste du développeur précédent, les ~300 tests des modules voisins passaient, mais la
suite **complète** n'avait jamais été lancée sur cette branche.

### 4.1 Reproduire l'échec en local
1. `git fetch origin && git checkout D4-compte-special-justifications`.
2. Mettez les variables d'environnement de l'étape 1.5 (avec `DEBUG=False`, comme la CI).
3. Lancez la suite complète **par groupes** (cela évite de tout perdre si l'un plante). Depuis `backend/` :
```bash
ls tests/test_*.py | sort > /tmp/tous.txt
split -n l/6 -d /tmp/tous.txt /tmp/g_
for g in /tmp/g_0*; do
  echo "== $g"
  ./.venv/bin/pytest -q --no-cov -p no:cacheprovider -rf $(cat $g) 2>&1 | grep -aE "^(FAILED|ERROR) | passed| failed"
done
```
Comptez 45 à 60 minutes. Les lignes `FAILED tests/...::test_...` sont ce que vous cherchez.
4. **Si rien n'échoue en local**, lancez la même chose avec la couverture comme la CI :
   `./.venv/bin/pytest -q --cov=. --cov-report=term-missing`. (La CI affiche la couverture mais n'impose aucun
   seuil ; la règle du projet est ≥ 80 %, regardez la ligne `TOTAL`.) Comparez aussi avec la version Python et
   les versions des dépendances de la CI (`uv pip list`).

### 4.2 Pistes, par ordre de probabilité
* **Un test « global » qui énumère quelque chose que D4 a ajouté** : fichiers de catalogue des modèles d'état,
  tables du modèle, routes, clés de messages, `makemigrations --check`. D4 ajoute une table
  (`tresorerie_justificationcomptespecial`), une migration, un modèle d'état
  (`catalogue_modeles/bad_reconciliation_compte_special.json`), une source du moteur, des messages.
  Faites : `./.venv/bin/python manage.py makemigrations --check --dry-run` et
  `./.venv/bin/python manage.py generer_dictionnaire && git status` (le fichier `DICTIONNAIRE_DE_DONNEES.md`
  ne doit pas changer).
* **Un test qui dépend de `DEBUG=False`** ou du rôle `sigf_app` : relancez le test en échec avec exactement les
  variables de l'étape 1.5.
* **Un test concurrent ou sensible à l'heure** (les tests avec des threads, ou qui utilisent `today()`) : relancez-le
  dix fois : `for i in $(seq 10); do ./.venv/bin/pytest -q --no-cov tests/test_x.py::test_y || break; done`.

### 4.3 Corriger
* Corrigez **le code ou le test fautif**, jamais en **supprimant ou ignorant** un test.
* Un test qui supposait « un seul modèle d'état » ou « N tables » se met à jour avec la nouvelle réalité *et vous
  expliquez pourquoi dans le commit*.
* Poussez sur la **même branche** : `git push origin D4-compte-special-justifications`. La CI de la PR n° 6
  repart toute seule. Attendez le vert (≈ 50 min).

### 4.4 Fusionner D4, puis D5 à D9, dans cet ordre
Pour **chaque** branche, dans l'ordre `D4`, `D5-compte-special-limites`, `D6-documents-fichiers`,
`D7-controles-evaluations`, `D8-profil-brouillon-modifiable`, `D9-exception-audit-eligibilite` :

1. Sur GitHub, ouvrez la PR (base `main`, tête = la branche) si elle n'existe pas. Titre = premier message de commit
   de la branche (`git log --oneline main..<branche>`).
2. Attendez la CI **verte**. (Vous pouvez ouvrir les cinq PR d'un coup : leurs CI tournent en parallèle ; fusionnez
   ensuite une par une.)
3. Fusionnez avec **« Create a merge commit »**.
4. Passez à la suivante. Si GitHub annonce un **conflit**, c'est presque toujours dans trois fichiers :
   * `DICTIONNAIRE_DE_DONNEES.md` → ne le fusionnez pas à la main : prenez la version de `main`, puis régénérez :
     `./.venv/bin/python manage.py generer_dictionnaire` et commitez ;
   * `06_PLAN_LOT_L11_MOTEUR_MULTIBAILLEUR.md` → gardez **les deux** notes « Réalisation » ;
   * `CLAUDE.md` → gardez les deux phrases.
   Après résolution, relancez `ruff` et les tests des fichiers concernés, poussez, attendez la CI.
5. Ne faites **aucune** migration « à la main » : deux migrations de numéros identiques dans la même application
   sont un conflit à résoudre en renumérotant la plus récente (`makemigrations --merge` si Django le propose).

### 4.5 Vérification finale du lot
* `main` a une CI verte sur son dernier commit.
* Les six PR sont fusionnées. `git branch -r --no-merged origin/main` ne liste plus D4 à D9.
* Mettez à jour la phrase « Écarts connus » de `CLAUDE.md` (elle dit encore « un seul modèle d'état » dans les anciennes
  versions) pour qu'elle reflète : deux modèles d'état livrés, API des documents, profils de décaissement, contrôles
  et compte spécial.

**Estimation (ordre de grandeur) : 1 à 2 jours, dont l'essentiel est de l'attente de CI.**

---

## 5. Lot 1 — Revue de code de L11 ⏳

**But.** Les lots L6 à L10 avaient chacun révélé une dizaine de défauts lors d'une relecture (PR « revue-corrections »).
L11 (phases A, B, D1 à D9) n'a **pas** eu cette relecture. Vous la faites.

### 5.1 Méthode
1. Créez `REVUE_L11.md` à la racine : un tableau `| N° | Fichier:ligne | Constat | Gravité | Correction | Test |`.
2. Relisez **module par module** avec la liste de contrôle du §5.2. Notez chaque écart, même mineur.
3. Gravité : **importante** = peut donner un mauvais résultat, une fuite entre organisations, une perte de donnée ;
   **moyenne** = message trompeur, validation manquante ; **mineure** = clarté.
4. Corrigez par ordre de gravité, **un constat = un test qui échoue avant, passe après**. Une branche
   `L11-revue-corrections` ; vous pouvez grouper dix corrections dans une PR.

### 5.2 Liste de contrôle (à appliquer à *chaque* fichier d'API et de service)
* **Habilitation.** Chaque vue a-t-elle son `habilite(...)` ou un service qui le fait ? Une lecture sans droit
  renvoie 403 ? Écrivez le test « utilisateur sans droit » (voir `test_sans_habilitation_aucune_lecture_n_est_permise`
  dans `tests/test_api_evaluations_bd.py` comme modèle).
* **Isolation.** Aucun `.filter(org_id=...)` écrit à la main (règle 4). Un objet d'un autre projet ou d'une autre
  organisation → **404**, pas 403 ni 500.
* **Montants.** Aucun `float` ; les montants entrent en **chaîne**, sortent en chaîne ; `NaN` et l'infini refusés.
* **Erreurs.** Une règle violée renvoie `{code, message}` en 422 (409 pour une transition interdite, 403 pour un
  droit, 404 pour l'introuvable). Une contrainte de la base ne doit **jamais** sortir en 500 : traduisez-la
  (voir `_traduire_profil` dans `backend/niveau3_config/api.py`).
* **Messages.** Aucun texte français en dur dans un `raise` ; tout passe par `msg("domaine.cle", ...)` avec les
  paramètres exacts. Les deux langues existent.
* **Tests creux** (le piège n° 1, voir §2.4) : cherchez les tests d'API qui font `...objects.count() == 0` après un
  appel HTTP sans avoir refait `SET app.org_id`. Commande : `grep -n "objects.count()" backend/tests/test_api_*.py`
  puis lisez chaque occurrence ; pour chacune, remplacez par un compteur qui repose l'organisation (annexe B).
* **Concurrence.** Une opération « lire puis écrire » (numérotation, plafond, unicité) a-t-elle un verrou
  (`select_for_update`) ou une contrainte en base ?
* **Journal.** Une action sensible (création, validation, annulation, téléchargement) écrit-elle dans le journal
  (`core.audit.journaliser`) avec une action de **32 caractères au plus** ?
* **Version, pas modification.** Aucune configuration « active » n'est modifiée sur place (règle 7).
* **Documentation.** La note « Réalisation » dit-elle la vérité, y compris ses limites ?

### 5.3 Modules à relire, dans cet ordre
1. `niveau1_socle/financements/` (`api.py`, `cles.py`, `cofinancement.py`) — B1, B2, A2.
2. `niveau1_socle/tresorerie/` (`compte_special.py`, `api.py`, migrations 0003/0004) — D4, D5.
3. `niveau3_config/` (`api.py`, `services/profils_decaissement.py`, `services/decaissement.py`,
   `services/completude.py`, migration 0014) — B3, B4, D6, D8, D9.
4. `niveau4_reporting/controles/` (`api.py`, `depenses.py`, `services.py`) — A4, A5, B5, D7.
5. `niveau2_profils/` (`services/gabarit.py`, `services/citations.py`, `catalogue/bad.json`) — D1, D2.
6. `niveau4_reporting/tableau_de_bord/` — A1.

**Estimation : 3 à 5 jours.**

---

## 6. Lot 2 — Transversal ⏳

### 6.A Changer son mot de passe (écran) ⏳
*L'API existe ; il manque l'écran.*
1. **Lire** : l'API de session dans `backend/niveau1_socle/organisations/api.py` (cherchez `password`), puis
   `frontend/src/shared/session/` et `frontend/src/features/connexion/` (la connexion est votre modèle pour un
   formulaire).
2. **Test d'abord** : `frontend/src/features/connexion/ChangerMotDePasse.test.tsx`. Cas : champs vides refusés ;
   confirmation différente refusée ; mot de passe actuel faux → message du serveur affiché ; succès → message de
   confirmation ; le bouton est désactivé pendant l'envoi.
3. Créez `features/connexion/ChangerMotDePasse.tsx`, ajoutez la route `/mot-de-passe` dans `app/routes.tsx`
   (route protégée, sous `protege`), un lien dans `MiseEnPage.tsx`, les textes dans `i18n/locales/fr.json` et `en.json`.
4. Si l'API n'impose pas de règle de robustesse, **ne l'inventez pas côté écran** : demandez la règle
   (longueur, caractères) puis appliquez-la au serveur (`django.contrib.auth.password_validation`).

### 6.B Pagination ⏳
*Aujourd'hui aucune liste n'est paginée ; certaines (journal des évaluations) sont seulement bornées.*

**Décision de conception (à suivre).** Pour ne **pas casser** le frontend existant, on ne change **pas** la forme
du corps (toujours un tableau JSON). La pagination est **optionnelle** et son état passe par des **en-têtes** :
`?limite=50&decalage=100` ; réponse avec `X-Total-Count`, et `X-Decalage-Suivant` quand il y a une suite.
Sans `limite`, comportement actuel, mais **plafonné** à 500 lignes (au-delà, 422 qui demande de paginer).

1. **Test d'abord** (`backend/tests/test_pagination.py`, logique pure) : un `paginer(queryset, requete)` qui rend les
   bonnes tranches, refuse `limite` ≤ 0 ou > 500, `decalage` < 0, valeurs non entières ; calcule `X-Total-Count`.
2. Créez `backend/core/pagination.py` avec `paginer(queryset, requete) -> (liste, en_tetes)` ; ordre **déterministe
   obligatoire** (le queryset doit déjà être trié par une clé stable : refusez sinon).
3. Dans `core/api.py`, `reponse(donnees, statut=200, en_tetes=None)` ajoute les en-têtes.
4. Appliquez-la aux listes, **une par une**, chacune avec son test : documents, accords, bailleurs, clés, profils de
   décaissement, contrôles, évaluations, dérogations, justifications du compte spécial, taux, demandes de retrait.
5. Notez dans le plan 06 : liste des endpoints paginés et le plafond.

### 6.C Jeton d'API ⏳ (délicat — demandez une relecture avant de fusionner)
**But.** Permettre à un programme (sans navigateur) d'appeler l'API, sans mot de passe, avec les droits d'un utilisateur.
**Contrainte absolue.** **Aucune exception à l'isolation par organisation** : on n'ajoute *pas* de table lisible sans
`org_id`. Le modèle à imiter est **l'accès auditeur** (`niveau4_reporting/publication/`, `auditeur/`) : le jeton est
`<organisation>.<secret>` ; l'organisation (en clair) pose `app.org_id` pour la transaction, *puis* on cherche le
SHA-256 du secret sous la RLS.

1. **Lire** : `backend/niveau4_reporting/publication/auditeur.py` et `vues_auditeur.py` (accès auditeur),
   `OrganisationScopeMiddleware` (cherchez-le avec `grep -rn OrganisationScopeMiddleware backend/`),
   `config/settings/base.py` (`REST_FRAMEWORK`).
2. **Modèle** `JetonApi(ModeleOrganisation)` : `utilisateur` (FK), `libelle`, `prefixe` (8 premiers caractères du
   secret, pour l'affichage), `empreinte` (SHA-256 **du secret**, jamais le secret), `expire_le`, `revoque_le`,
   `dernier_usage`. Migration + `activer_rls` (annexe C). Ajout seul sauf `revoque_le` et `dernier_usage`.
3. **Création** : `POST /api/v1/jetons/` (session obligatoire, pas de jeton pour créer un jeton) → renvoie le jeton
   **une seule fois** (`<org>.<secret>`) ; `GET /api/v1/jetons/` liste sans secret ; `POST .../<id>/revocation/`.
4. **Authentification** : une classe DRF `AuthentificationJeton` lit `Authorization: Bearer <org>.<secret>`, pose
   l'organisation dans la transaction (`SET LOCAL app.org_id`), compare l'empreinte en **temps constant**
   (`hmac.compare_digest`), refuse un jeton révoqué ou expiré, met `dernier_usage` à jour. L'utilisateur
   authentifié est celui du jeton : **ses habilitations s'appliquent** (un jeton n'élargit jamais les droits).
5. **Tests** (obligatoires, tous) : secret faux → 401 ; organisation fausse → 401 ; jeton d'une autre organisation
   ne lit rien de la nôtre (**test d'isolation**, en `transaction=True`) ; jeton expiré/révoqué → 401 ; le secret
   n'apparaît **nulle part** en base (cherchez-le dans `core_auditlog` et dans la table) ; les droits de
   l'utilisateur limitent le jeton ; deux requêtes simultanées ; `Authorization` mal formé → 401 et jamais 500.
6. **Pas de CSRF** pour le jeton (pas de cookie) mais **CSRF conservé** pour la session. Test des deux.

### 6.D Économiser les minutes de CI ⏳
Aujourd'hui `on: [push, pull_request]` lance **deux** CI (une par push, une par PR) pour la même modification.
1. Dans `.github/workflows/ci.yml`, remplacez l'entête par :
```yaml
on:
  pull_request:
  push:
    branches: [main]
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```
2. Vérifiez sur une PR de test : un seul run par push ; un nouveau push annule le run précédent.
3. Ne supprimez **aucune** étape (style, migrations, tests, frontend). Ne retirez pas la couverture.

### 6.E Mot de passe oublié, double authentification ⛔
Décisions attendues (par courriel ? application d'authentification ? obligatoire pour quels rôles ?). **Ne rien
coder avant la décision écrite.** En attendant : documentez dans `06` ce qui manque.

**Estimation du lot 2 : 6 à 10 jours.**

---

## 7. Lot 3 — BAD : numérotation des demandes, lien dépense → contrat ⏳

### 7.0 Ce qui est déjà décidé (ne pas refaire)
**On n'ajoute PAS de types de demande « avance initiale » ni « justification seule ».**
Raison : dans l'application, `reapprovisionnement` veut dire « remboursement » (sémantique Banque mondiale) et
`retrait` veut dire « avance » ; ajouter des types BAD créerait deux vocabulaires pour la même chose. À la place :
* le type BAD d'une demande **se déduit** à l'export (Lot 8) : première avance sur un compte spécial = « avance
  initiale », avances suivantes = « reconstitution », remboursement = « remboursement » ;
* une « justification seule » est **déjà** représentée par `JustificationCompteSpecial` (D4).

### 7.A Numérotation des demandes au format BAD ⏳
**Règle du document** (manuel des décaissements BAD, p. 24-25, citations dans `bad.json`) : numérotation
chronologique, **4 chiffres au plus**, suffixe d'agence de **3 lettres**, suffixe `JUS` pour une justification seule,
un numéro annulé **n'est jamais réattribué**, numérotation **distincte** pour un prêt et pour un don.

1. **Lire** (30 min) : dans `backend/niveau1_socle/decaissements/services.py`, la fonction `preparer_demande` et la
   façon dont `numero` est fabriqué (format actuel `DRF-<numéro d'accord>-<séquence>`) ; le modèle `DemandeRetrait`
   (contrainte `uq_demande_numero`) ; comment la numérotation sans trou du journal est faite (compteur verrouillé,
   règle 3) — c'est le modèle à reproduire.
2. **Conception à suivre.**
   * Ajouter à `Accord` deux champs *facultatifs* : `format_numero_demande` (choix fermé : `standard`, `bad`,
     défaut `standard`) et `suffixe_agence` (3 lettres majuscules, obligatoire si le format est `bad`, contrainte
     base `CHECK`). Un accord est « prêt » ou « don » (champ `nature` existant) : la numérotation `bad` est
     **par accord**, donc distincte entre prêt et don.
   * Un **compteur** par accord (table `CompteurDemande`, RLS, ligne verrouillée à l'attribution), qui **ne
     décroît jamais** : annuler une demande ne rend pas son numéro.
   * Format `bad` : `{séquence sur 4 chiffres}{suffixe agence}` ; au-delà de 9999, refus net.
   * La **règle 7** s'applique : changer `format_numero_demande` d'un accord qui a déjà des demandes est **refusé**.
3. **Tests d'abord** : séquences 0001, 0002… ; annulation puis nouvelle demande → le numéro suivant, pas le
   numéro annulé ; deux accords → deux séquences ; format `standard` inchangé (test de non-régression sur
   `tests/test_demandes_retrait_bd.py`) ; 10 000e demande refusée ; deux préparations simultanées → deux numéros
   différents (test avec threads, voir `tests/test_derogations_bd.py` pour le modèle) ; suffixe invalide refusé.
4. Migration, RLS (annexe C), dictionnaire, API des accords (`financements/api.py` : champs en lecture et écriture
   avec validation), message d'erreur par le catalogue.
5. **Mutation** : retirez le verrou, retirez le « jamais réattribué », vérifiez que des tests échouent.

### 7.B Lier une dépense à un contrat, et deux contrôles ⏳
**But.** Rendre exécutables deux règles BAD que `bad.json` déclare « non branchées » : *une seule devise par
demande* et *même méthode pour toutes les demandes d'un contrat*.
1. **Lire** : `backend/niveau1_socle/marches/models.py` (le contrat, sa devise), `LigneDemande` dans
   `niveau1_socle/decaissements/models.py`.
2. Ajouter `contrat` (clé étrangère facultative vers le contrat) à `LigneDemande`. Une migration, un déclencheur
   « même projet » (modèle : `tresorerie_justifcs_garde` dans la migration 0003 de `niveau1_socle/tresorerie`).
   `preparer_demande(..., lignes=[...])` accepte un contrat par ligne.
3. **Contrôle « une devise par demande »** : toutes les lignes d'une demande ont des contrats de même devise ;
   sinon refus (`ProfilViole`/`DemandeInvalide` selon le cas) avec un message du catalogue nommant les devises.
   Sans contrat sur les lignes, aucun contrôle (état antérieur).
4. **Contrôle « même méthode par contrat »** : si une autre demande vivante (ni annulée ni rejetée) porte déjà des
   lignes du même contrat, la méthode (déduite du type de demande par `METHODE_DU_TYPE` dans
   `niveau3_config/services/decaissement.py`) doit être la même, sauf si la demande porte une **dérogation**
   (réutilisez le mécanisme de dérogation existant, `niveau4_reporting/controles/derogations.py` : ne créez pas
   un deuxième mécanisme).
5. **Tests** : devises différentes refusées ; même devise acceptée ; méthode différente refusée ; même méthode
   acceptée ; demande annulée ne compte plus ; dérogation approuvée lève le refus ; ligne sans contrat inchangée.
6. Mettez à jour `bad.json` : les deux contrôles passent de `non_branche` à `profil_decaissement`/`controle`
   (fichier `backend/niveau2_profils/catalogue/bad.json`, champ `branchement`), et le test
   `tests/test_branchement_controles_bad_bd.py` (qui fixe l'ensemble des contrôles « branchés ») avec eux.

**Estimation du lot 3 : 8 à 12 jours.**

---

## 8. Lot 4 — Périodes de rapport libres (C3) ⏳

**But.** Aujourd'hui, une colonne de rapport est `year_to_date` ou une période fixe ; l'exigence a une périodicité
(mensuelle, trimestrielle, semestrielle, annuelle). On veut produire un état sur **n'importe quelle plage de dates**
(par exemple du 15 janvier au 30 avril).

1. **Lire** (1 h, c'est le cœur du lot) : `backend/niveau4_reporting/moteur/compilateur.py` (comment `period`
   d'une colonne est traduit en SQL), `niveau4_reporting/moteur/formules.py`, et le test
   `tests/test_compilateur*.py` pour voir le format JSON d'un modèle.
2. **Conception à suivre.**
   * Nouveau type de colonne `{"code": "PER", "period": "range"}` qui lit les paramètres `date_debut` et
     `date_fin` (ISO, bornes **incluses**). Les noms des paramètres passent par une **liste blanche**, et les
     valeurs sont des **paramètres SQL**, jamais collées dans le texte SQL (règle de sécurité du projet).
   * Refus net si `date_fin < date_debut`, ou si une date est illisible.
3. **Tests d'abord** : la somme de deux plages contiguës = la plage totale (sur des écritures de test) ; une
   écriture le jour de début et le jour de fin est **comptée** ; un jour avant/après, **non** ; deux plages
   identiques → rapports identiques et même empreinte (le rapport reste scellable et régénérable).
4. Rapport **publié** : les paramètres de plage font partie de ce qui est scellé ; `regenerer(publie)` redonne la
   même chose (modèle : `tests/test_regeneration_bd.py`).
5. Exposez la plage dans l'API de génération existante (cherchez `publier_rapport` dans `niveau4_reporting/`), puis
   dans l'écran du tableau de bord si un sélecteur de période existe.

**Estimation : 4 à 6 jours.**

---

## 9. Lot 5 — Les écrans d'administration (frontend) ⏳

**Constat.** Toute l'administration d'un financement existe **en API** (clés de cofinancement, bailleurs, accords,
catégories, avenants, documents, profils de décaissement, contrôles, évaluations, dérogations, compte spécial, taux).
**Aucun écran** ne s'en sert. Un administrateur ne peut donc rien faire sans appeler l'API à la main. Ce lot construit
les écrans, **un par un**, chacun avec ses tests.

### 9.0 Ce qu'il faut comprendre du frontend avant de commencer (1 à 2 heures de lecture)
Pile : React 19, TypeScript, Vite, **TanStack Router** (routes) et **TanStack Query** (appels et cache), **Vitest** +
Testing Library (tests). Lisez dans cet ordre :
1. `frontend/README.md`.
2. `frontend/src/app/routes.tsx` : comment une route est déclarée (`createRoute`, parent `protege`), comment la
   recherche d'adresse est validée (`validateSearch`). **Le routeur fusionne la recherche brute avec ce que renvoie
   le validateur** : une valeur invalide doit être écrasée par `undefined`.
3. `frontend/src/shared/api/client.ts` : la fonction `appeler<T>(url, { methode, corps })` (gère le jeton CSRF, les
   erreurs `{code, message}`, la session perdue). **N'utilisez jamais `fetch` directement.**
4. `frontend/src/features/devises/` : **c'est votre modèle complet** — `types.ts` (ce que renvoie l'API),
   `api.ts` (les appels), `ReglagesDevises.tsx` (l'écran), `ReglagesDevises.test.tsx` (ses tests), `devises.css`.
5. `frontend/src/shared/ui/` : `Bouton`, `Carte`, `Champ`, `Chargement`, `Message`, `Montant`, `Pastille`,
   `Selecteur`. **Réutilisez-les**, ne recréez pas de composants.
6. `frontend/src/shared/money/montant.ts` (calculs avec `decimal.js`) : **un montant n'est jamais un `number`**
   (règle 1) ; il arrive et repart en chaîne.
7. `frontend/src/test/serveur.ts` et `monter.tsx` : le **faux serveur** et l'aide qui monte l'application complète
   devant lui. Vos tests passent par là (pas de réseau).
8. `frontend/src/i18n/` : les textes sont dans **deux fichiers**, `locales/fr.json` et `locales/en.json` ;
   **aucun texte en dur** dans un composant.

### 9.1 Tâche préalable : apprendre au faux serveur à répondre aux écritures ⏳
Aujourd'hui `serveur.routes` ne gère que des `GET`. Sans cela, vous ne pouvez pas tester un formulaire.
1. Test d'abord, dans un nouveau `frontend/src/test/serveur.test.ts` : une route déclarée pour `POST` répond avec
   le corps voulu et enregistre l'appel dans `serveur.appels` ; un `POST` sans jeton CSRF → 403 ; une session
   perdue → 401 ; une route `PUT`/`DELETE` idem ; une route inconnue → 404.
2. Étendez le type `routes` : `{ methode?: string; motif: RegExp; reponse: (trouve, recherche, corps) => unknown | {statut, corps} }`
   (par défaut `GET`, comportement actuel inchangé : les tests existants doivent rester verts).
3. `npm test` : **tous** les tests existants passent encore.

### 9.2 La recette d'un écran (à répéter pour chaque écran)
Pour chaque écran, dans `frontend/src/features/<nom>/` :
1. **`types.ts`** : recopiez fidèlement la forme des réponses de l'API (lisez la fonction `_xxx` de sérialisation dans
   le fichier `api.py` du backend). Montants et dates : `string`. Ne devinez pas un champ : lisez le serveur.
2. **`api.ts`** : une fonction par appel, avec `appeler<T>`. Aucune logique ici.
3. **Test d'abord** (`<Ecran>.test.tsx`) avec `monter("/chemin", { connecteComme: "amina" })` et le faux serveur.
   Cas minimum : *chargement* (état « en cours »), *liste vide* (message clair), *liste remplie*, *erreur serveur*
   (message `{code, message}` affiché tel quel, jamais « undefined »), *accès sans droit* (403 → message, pas de
   formulaire), *action réussie* (liste rafraîchie), *action refusée* (422 → message du serveur à côté du champ ou
   en haut), *double clic* (un seul appel), *accessibilité* (voir `test/accessibilite.ts` : chaque champ a une
   étiquette, chaque bouton un nom).
4. **Composant** : `useQuery` pour lire, `useMutation` pour écrire ; après une écriture, `invalidateQueries` de la
   clé concernée. Désactivez le bouton pendant l'envoi. Affichez les erreurs du serveur.
5. **Route** dans `app/routes.tsx` (enfant de `protege`) et **lien** dans `MiseEnPage.tsx` (menu « Administration »).
6. **Textes** dans `i18n/locales/fr.json` **et** `i18n/locales/en.json` (mêmes clés : `i18n/index.test.ts` vérifie
   que le français et l'anglais ont exactement les mêmes clés).
7. **CSS** : `<nom>.css`, uniquement des propriétés **logiques** (`margin-inline-start`, `padding-inline`,
   `text-align: start`, `inset-inline-end`) — règle 10. Pas de couleur en dur : utilisez les variables du thème
   (`shared/styles/`).
8. `npm run typecheck && npm run lint && npm test && npm run build` : **tout vert**.
9. Note « Réalisation » dans le plan 06 (limites : « pas de pagination », « pas de recherche »…).

### 9.3 Écran modèle, détaillé de bout en bout : « Profils de décaissement »
C'est le premier écran à faire : il sert de patron pour les autres.

**Données et API (déjà livrées, lisez `backend/niveau3_config/api.py`)**
* `GET  /projets/<projet>/accords/` → liste des accords (pour choisir l'accord).
* `GET  /projets/<projet>/accords/<accord>/profils-decaissement/` → liste (résumé : `id`, `version`, `status`,
  `valid_from`, `regime`…).
* `POST /projets/<projet>/accords/<accord>/profils-decaissement/` → crée un **brouillon**.
* `GET  …/profils-decaissement/<id>/` → détail : `methodes`, `regles`, `comptes`, et pour un brouillon `completude`
  (`complet`, `bloquantes`, `avertissements`).
* `PUT  …/<id>/` remplace tout un **brouillon** ; `DELETE …/<id>/` l'abandonne.
* `POST …/<id>/valider/` (droit *valider*), `…/activer/` (droit *parametrer*), `…/rejeter/` (corps `{motif}`),
  `…/nouvelle-version/` (corps `{valid_from, allocations: {code: montant}, dates: {...}}`),
  `GET …/<id>/comparaison/?avec=<n° de version>`.
* Gabarit BAD : `GET /projets/<projet>/profils-bailleurs/bad/gabarit-decaissement/?date_cloture=AAAA-MM-JJ`.

**Pages**
1. *Liste* : un tableau (version, état avec `Pastille`, effet, régime). Boutons « Nouveau profil » et, pour une
   ligne, « Ouvrir ».
2. *Détail* : trois blocs (méthodes, règles par catégorie, comptes désignés) ; un encadré **complétude** : les
   erreurs bloquantes en rouge **avec leur message**, les avertissements en orange. Boutons selon l'état :
   * brouillon : « Modifier », « Supprimer », « Valider » (désactivé tant que `complet` est faux, mais **le serveur
     reste l'autorité** : affichez son message s'il refuse) ;
   * validé : « Activer », « Rejeter » (saisie obligatoire d'un motif) ;
   * actif : « Créer une nouvelle version » (formulaire : date d'effet, allocations changées).
3. *Formulaire de création/édition* (brouillon) : régime ; jalons (4 dates) ; méthodes (cases à cocher parmi
   `advance`, `reimbursement`, `direct_payment`, `special_commitment`, avec les pièces exigées parmi `soe`,
   `records`, `ifr`, `summary_sheet`) ; règles (une ligne par catégorie de l'accord : allocation, **taux entre 0
   (exclu) et 1**, assiette `taxes_included`/`net_of_taxes`, dates d'éligibilité, case « fin propre à la catégorie »
   avec **avertissement visible** quand la fin dépasse celle de l'accord) ; comptes désignés. Envoyez **tout le
   profil** (`POST` ou `PUT`).
4. *Comparaison* : deux versions côte à côte, les écarts surlignés (`categories.modifies` donne `avant`/`apres`).
5. *Gabarit BAD* (bouton « Pré-remplir depuis le profil BAD », visible si l'accord est d'un bailleur BAD) : demande
   la date de clôture, appelle le gabarit, **pré-remplit seulement** `closing_date`, `disbursement_deadline`,
   `eligibility_date` et propose la règle d'audit ; **ne crée rien tout seul**.

**Tests à écrire (liste minimale, un test par ligne)**
* la liste affiche les versions dans l'ordre et l'état en toutes lettres ;
* « Valider » est désactivé quand `completude.complet` est faux et le message de chaque erreur est affiché ;
* valider puis activer appelle les bonnes URL dans le bon ordre ;
* un 403 sur *valider* affiche « Vous n'êtes pas habilité… » (message du serveur) ;
* un 422 sur création affiche le message du serveur (ex. « Le taux de financement doit être supérieur à 0… ») ;
* le formulaire refuse un taux de `1,5` **avant** l'envoi, et envoie `"0.85"` (chaîne) pour `0,85` ;
* **aucun montant n'est jamais converti en `number`** (test : saisir `0.1` + `0.2` ne produit pas `0.30000000000000004`) ;
* supprimer demande une confirmation ; annuler la confirmation n'appelle rien ;
* la nouvelle version envoie `allocations` indexées par **code** de catégorie ;
* la comparaison surligne `SERVICES` quand son allocation change ;
* le gabarit ne modifie rien tant qu'on n'a pas cliqué « Appliquer ».

### 9.4 Les autres écrans, dans cet ordre
Pour chacun : mêmes étapes que 9.2, mêmes exigences de test. Les URL se lisent dans le `urls.py` du module (ne les
devinez pas).

| # | Écran | Backend à lire | Actions | Droit |
|---|---|---|---|---|
| E2 | **Contrôles** : liste des versions, installation de la bibliothèque (cases à cocher + seuils de risque), création (expression en formulaire guidé : champ, opérateur, valeur — *pas* de texte libre), valider/activer/rejeter | `niveau4_reporting/controles/api.py`, `urls.py` | installer, créer, valider, activer, rejeter | consulter / parametrer / valider |
| E3 | **Évaluations et dérogations** : journal filtrable, détail, trancher, justifier, demander et décider une dérogation, « en attente » d'un objet, dossier de conformité | même dossier | trancher, justifier, déroger | valider / saisir |
| E4 | **Accords et catégories** : accords, catégories (arbre), avenants, statut | `niveau1_socle/financements/api.py`, `urls.py` | créer, changer le statut | parametrer |
| E5 | **Clés de cofinancement** : parts par accord, versions, **somme = 100 % vérifiée à l'écran ET au serveur** | idem | créer, nouvelle version | parametrer |
| E6 | **Documents** : liste, dépôt par glisser-déposer (multipart, jusqu'à 50 Mio, barre de progression), remplacement, téléchargement, contrôle d'intégrité | `niveau3_config/api.py` (`Documents`, `DocumentContenu`) | déposer, remplacer, télécharger | parametrer / consulter |
| E7 | **Compte spécial** : situation à une date (lignes 2 à 7 de l'annexe 9), justifications par demande, annulation motivée, publication du rapport avec note d'écart | `niveau1_socle/tresorerie/api.py` | justifier, annuler, publier | saisir / publier |
| E8 | **Taux de change** : saisie et liste (`/api/v1/taux/`) | `niveau1_socle/referentiels/api.py` | enregistrer | parametrer |
| E9 | **Saisie d'une écriture avec clé de cofinancement** (`"cle"` sur une ligne) | `niveau1_socle/comptabilite/` | saisir | saisir |

Règles propres aux écrans :
* **Le serveur est l'autorité.** L'écran peut désactiver un bouton par commodité, mais il affiche toujours le refus
  du serveur ; ne dupliquez jamais une règle métier côté écran sans test d'équivalence.
* **Jamais de secret ni de numéro de compte complet** à l'écran (l'API ne renvoie que le numéro masqué).
* **Téléchargement** (E6) : ouvrez l'URL `…/contenu/` telle quelle (le serveur impose `attachment`) ; n'essayez
  pas d'afficher un document dans la page.

**Estimation du lot 5 : 25 à 40 jours** (un écran = 2 à 5 jours avec ses tests).

---

## 10. Lot 6 — Recette multibailleur (phase F) ⏳ (première version) / ⛔ (version complète)

**But (questionnaire, questions 55 à 58).** *Un projet, plusieurs bailleurs, une dépense saisie **une seule fois**,
répartie, des rapports distincts par bailleur, **aucune intervention manuelle**.* Un test automatisé, puis un
parcours navigateur dans la CI.

### 10.1 Première version, faisable maintenant ⏳
Elle utilise les états déjà livrés : le rapport de référence **TER**, l'**RFI**, le **rapprochement du compte désigné**
et la **réconciliation BAD du compte spécial**.
1. **Lire** : `backend/tests/test_recette_architecture_bd.py` (le scénario T17 « deux accords, un projet » est votre
   point de départ), `tests/test_saisie_cofinancee_bd.py` (répartition à la saisie), `tests/test_etats_reference_bd.py`.
2. Créez `backend/tests/test_recette_multibailleur_bd.py` avec **un seul** test long, découpé en étapes commentées :
   1. un projet, **deux accords** de deux bailleurs, une clé de cofinancement 60/40 ;
   2. **une** dépense saisie avec `"cle"` : elle est ventilée entre les deux accords (vérifiez les deux
      imputations et que leur somme = la dépense, au centime, avec l'arrondi du projet) ;
   3. un profil de décaissement par accord, des taux différents ;
   4. **deux demandes de retrait**, une par accord, aux montants différents (taux × dépense éligible) ;
   5. **deux (puis trois) rapports distincts** sur **les mêmes données** ; vérifiez que chaque total correspond
      à sa part, et que **les rapports ne se contredisent pas** (la somme des parts = la dépense) ;
   6. **aucune écriture manuelle** entre les étapes : tout passe par les services ou l'API.
3. Ajoutez la vérification d'**isolation** : une seconde organisation ne voit rien (`transaction=True`).

### 10.2 Parcours navigateur ⏳
* Version 1 (faisable) : un **test d'intégration Vitest** (`frontend/src/app/recette.test.tsx`, modèle
  `parcours.test.tsx`) qui déroule : connexion → choix du projet → tableau de bord → consolidation → descente
  d'une cellule jusqu'aux écritures.
* Version 2 (plus tard, ⛔ décision) : un vrai navigateur (Playwright) dans la CI. Ajoutez-le seulement après
  accord : cela allonge la CI.

### 10.3 Version complète ⛔
Elle exige **trois bailleurs ayant chacun son modèle de rapport** (Banque mondiale IFR, BAD, UE). Elle dépend des
Lots 7 à 9 et des documents. En attendant, la première version du §10.1 protège l'essentiel.

**Estimation : version 1 = 6 à 10 jours.**

---

## 11. Lot 7 — Remplir le profil d'un bailleur (procédure) ⛔

**Bloqué tant que vous n'avez pas les documents** du bailleur (voir le tableau ci-dessous). **Sans document, ne
touchez pas au profil** : les squelettes actuels sont volontairement vides de règles.

| Bailleur | Fichier du profil | Documents à obtenir (demandez-les au chargé de projet du bailleur) |
|---|---|---|
| UE | `backend/niveau2_profils/catalogue/union_europeenne.json` | conditions générales des conventions de subvention, guide de gestion financière, modèles de rapport financier et de demande de paiement |
| FIDA | `…/fida.json` | manuel de décaissement des prêts, lettre à l'emprunteur, modèles de demande de retrait et de rapport financier |
| Fonds mondial | `…/fonds_mondial.json` | lignes directrices de gestion financière, modèles de rapport de progrès et de demande de décaissement |
| BID | `…/bid.json` | manuel de décaissement, guide de gestion financière, modèles |
| Nations unies | `…/nations_unies.json` | cadre de reporting financier, modèles de rapport financier |
| AFD | à créer : `…/afd.json` | conditions générales, guide de décaissement, modèles |
| BAD | `…/bad.json` | ✅ fait (v2, 80 citations vérifiées). Reste : lignes directrices plus propres (`GFA01_Guidelines for FG & FA of Proj.pdf`) pour pouvoir citer littéralement ce qui ne l'est pas |

### 11.1 Procédure (suivez-la dans l'ordre)
**Étape 1 — Ranger les documents.** Un dossier **à part**, hors du dépôt : `~/documents-bailleurs/<bailleur>/`. Ne
copiez **jamais** un document de bailleur dans le dépôt (droits d'auteur, confidentialité). Calculez l'empreinte de
chaque PDF : `sha256sum fichier.pdf` (macOS : `shasum -a 256`). Notez : titre exact, date ou version, nombre de
pages, empreinte.

**Étape 2 — Extraire le texte page par page**, avec **la même fonction que l'application** (sinon vos citations ne
seront pas retrouvées par le vérificateur). Depuis `backend/`, avec les variables de l'étape 1.5 :
```python
# extraire.py — à garder HORS du dépôt
import django, sys
django.setup()
from niveau3_config.services.extraction import extraire_pages, normaliser
pages = [normaliser(p) for p in extraire_pages(open(sys.argv[1], "rb").read())]
for n, texte in enumerate(pages, 1):
    open(f"page_{n:03d}.txt", "w", encoding="utf-8").write(texte)
```
`DJANGO_SETTINGS_MODULE=config.settings.dev PYTHONPATH=. ./.venv/bin/python extraire.py doc.pdf`.
**Vérifiez que le texte est lisible.** Si les mots sont hachés (« m onths »), le PDF a une couche texte dégradée :
**ne citez pas littéralement** ce document ; référencez-le sans citation et écrivez-le dans la `note`.

**Étape 3 — Lire, puis relever les règles.** Pour chaque règle, notez : *ce qu'elle impose*, *la page*, *la phrase
exacte* (citation). Ne retenez **que ce que le document dit**. Si le document renvoie à « l'accord de financement »
pour un chiffre (taux, plafond, délai), **ce chiffre n'entre pas dans le profil** : il appartient au projet.

**Étape 4 — Écrire le profil en JSON**, en imitant `bad.json` (c'est le modèle complet). Chaque *élément* a :
`kind` (parmi `document_reference`, `report_family`, `report_template`, `presentation_rule`, `periodicity`,
`check`, `export_format`, `nomenclature`), `code` (unique), `label` (`{fr, en}`), `contenu` (`source` = code
`SRC:...` du registre ; `citations` = `[{source, page, quote}]` ; `note` ; `parametres` éventuels) et, pour un état à
fournir, `exigence` (`subject` bilingue, `rule` `{kind: "report", template: "<CODE>"}`, `obligation: "optional"`).
Contraintes **imposées par les tests** (`tests/test_profils_bailleurs_livres_bd.py`) :
* toutes les obligations sont **`optional`** (le profil *met à disposition*, il n'impose rien) ;
* tout est **bilingue** (`fr` et `en`) ;
* la description contient « n'est pas un modèle universel » et « lorsque requis » (et leurs équivalents anglais) ;
* **aucune périodicité ni décalage en jours n'est livré** sauf si le document le donne **et** que vous le citez
  (exemple : l'IFR de la BAD, trimestriel à 45 jours, cité au manuel de 2014) ;
* un délai exprimé en **mois** ne se convertit **pas** en jours : laissez la périodicité sans décalage.

**Étape 5 — Enregistrer les sources** dans `ANNEXE_B_REGISTRE_DES_SOURCES.md` : une ligne par document
(`SRC:bailleur:4NN`, titre, ce qu'il apporte, **empreinte SHA-256**, date, fiabilité). Reprenez la forme des lignes
`SRC:bailleur:420` à `424` (BAD). Fiabilité **F2** pour un manuel d'orientation non contractuel.

**Étape 6 — Construire le fichier avec un script qui vérifie les citations.** N'écrivez pas les numéros de page
à la main : écrivez un petit script qui, pour chaque citation `(document, phrase)`, **cherche la page** dans le texte
extrait et **s'arrête avec une erreur** si la phrase n'est pas trouvée :
```python
def citer(doc, phrase, pages):                      # pages = {doc: [textes normalisés]}
    q = normaliser(phrase)
    trouvees = [i for i, t in enumerate(pages[doc], 1) if q in t]
    if not trouvees:
        sys.exit(f"CITATION INTROUVABLE : {doc} : {phrase}")
    return {"source": SRC[doc], "page": trouvees[0], "quote": phrase}
```
Si une citation échoue, **raccourcissez-la** à un morceau exact du texte (les césures de ligne la cassent souvent) ;
n'« arrangez » jamais le texte.

**Étape 7 — Vérifier avec la commande du dépôt :**
```bash
DJANGO_SETTINGS_MODULE=config.settings.dev PYTHONPATH=. ./.venv/bin/python manage.py \
  verifier_citations_profil <nom_du_profil> --dossier ~/documents-bailleurs/<bailleur>
```
Elle reconnaît chaque PDF **par son empreinte** et cherche chaque citation **à sa page**. Résultat attendu : « N
citation(s) vérifiée(s) » et code de sortie 0. Un document absent du dossier = citations « non vérifiables »
= **échec** (c'est voulu).

**Étape 8 — Tests.** Copiez `backend/tests/test_profil_bad_bd.py` en `test_profil_<bailleur>_bd.py` et adaptez :
familles attendues, seuls délais livrés, sources du registre, empreintes registre = profil, citations (source
connue, page valide, extrait non vide), paramètres chiffrés attendus, chargement + publication + import (exigences
**proposées** seulement). Puis, dans `tests/test_profils_bailleurs_livres_bd.py`, **retirez le bailleur** des
dictionnaires `PROFILS` et `FORMULAIRES` (ils ne décrivent que les squelettes).

**Étape 9 — Branchement des contrôles.** Pour chaque règle de contrôle du profil, décidez **honnêtement** (modèle :
champ `branchement` de `bad.json`) : appliquée par un contrôle de la bibliothèque (`controle_bibliotheque`), par le
profil de décaissement (`profil_decaissement`), ou **pas appliquée** (`non_branche` + la raison). Ne déclarez
jamais « branché » ce qui ne l'est pas : le test `test_branchement_controles_bad_bd.py` vérifie qu'un contrôle cité
existe.

**Étape 10 — Documentation.** Note « Réalisation » (modèle : D1 dans le plan 06), phrase dans `CLAUDE.md`
(« Le profil X est rempli d'après… »), puis PR.

**Mutations à faire** : changez un numéro de page d'une citation → la commande de l'étape 7 doit échouer ; changez
l'empreinte d'un document → `test_..._empreinte...` doit échouer.

**Estimation : 5 à 10 jours par bailleur** (lecture comprise), une fois les documents en main.

---

## 12. Lot 8 — Export des formulaires BAD A1, A2, A3 ⛔

**Ce qui bloque.** Les formulaires **officiels éditables** (non publics) : à demander au chargé de projet BAD ou via
Client Connection. **Sans eux**, vous pouvez produire un fichier **marqué « non officiel — à reporter sur le
formulaire de la Banque »**, jamais un formulaire présenté comme officiel.

**Ce qui est déjà acquis** (à ne pas redécouvrir) :
* Les rubriques vérifiées du manuel (mars 2020) sont citées dans `bad.json` (éléments `BAD-A1`, `BAD-A2`,
  `BAD-A3`) : type de demande (remboursement, avance initiale du compte spécial, reconstitution, justification
  seule, paiement direct), numéro à 13 chiffres de l'accord, numéro de demande à 4 chiffres ; colonnes de A2
  (montant déjà payé par la Banque, preuve de paiement, cumul, part de la Banque dans le contrat) ; A3 (période
  d'utilisation de l'avance, avance demandée, budget annuel, date d'approbation).
* La donnée source existe : `etat_certifie` d'une `DemandeRetrait` (dépenses par catégorie : pièce, date, montant,
  taux, montant à retirer) — voir `etat_certifie_de` dans `backend/niveau1_socle/decaissements/services.py`.

### 12.1 Conception (à suivre)
1. **Principe** : la *correspondance* entre les colonnes de la demande et les cellules du formulaire est de la
   **donnée** dans le profil de bailleur (`contenu.format_export`), pas du code (critère du projet : ajouter un
   bailleur ne demande aucune ligne de code).
2. **Module** : `backend/niveau4_reporting/formats_bailleur/` avec `export_demande(demande, format) -> bytes`.
   Vérifiez la bibliothèque Excel disponible : `grep -n "openpyxl\|xlsxwriter" backend/pyproject.toml`, et regardez
   comment L6-T05 écrit déjà des fichiers Excel (`backend/niveau4_reporting/publication/exports.py`) ;
   **réutilisez** la même bibliothèque et les mêmes aides.
3. **Type de demande BAD déduit** (voir §7.0) : première avance sur le compte spécial → « avance initiale » ;
   avances suivantes → « reconstitution » ; type `reapprovisionnement` → « remboursement » ; `paiement_direct` →
   « paiement direct ». Écrivez cette fonction **avec ses tests** (un test par cas + le cas ambigu → refus net).
4. **Cumuls de A2** (« déjà payé par la Banque », « cumul ») : calculés par une **requête** sur les demandes
   précédentes de l'accord (statuts soumise/acceptée/contestée/remboursée), jamais saisis.
5. **API** : `GET /projets/<p>/demandes/<id>/export/<format>/` (format = `bad_a1`, `bad_a2`, `bad_a3`), droit
   *consulter*, réponse en pièce jointe, **journalisée**. Le nom de format passe par une **liste blanche**.
6. **Marquage** : sans formulaire officiel, la première ligne de la feuille dit « DOCUMENT NON OFFICIEL ».
7. **Tests** : un fichier de test avec une demande fabriquée ; relire le fichier produit (même bibliothèque) et
   vérifier chaque cellule ; montants en **texte exact** ; demande d'un autre accord → 404 ; sans droit → 403 ;
   format inconnu → 404 ; **aucune formule Excel** avec un montant calculé en flottant.

**Estimation : 8 à 12 jours (hors obtention des formulaires).**

---

## 13. Lot 9 — Import et export Excel fidèles (C4, C5) ⛔

**Décision attendue** : conserver les **formules** du modèle Excel d'un bailleur, ou n'écrire que des **valeurs** ?
*Recommandation* (à confirmer par écrit) : **conserver les formules** et n'écrire que dans des cellules de saisie
désignées ; ne jamais écraser une cellule qui contient une formule.

### 13.1 Si la décision est « conserver les formules »
1. **Modèle de données** (avec RLS, annexe C) : `ModeleExcel` (organisation, projet ou global, nom, `sha256` du
   fichier, version), `CelluleModele` (modèle, feuille, adresse `B12`, rubrique du rapport, colonne), statut
   *brouillon → validé* (**une correspondance non validée ne sert à rien** : règle 7 et 9).
2. **Import (C4)** : l'utilisateur téléverse un `.xlsx` (multipart, voir D6) ; le serveur **analyse** (liste feuilles,
   cellules de saisie vs formules) et propose ; **une personne valide** la correspondance. Les fichiers `.xlsm` (macros)
   sont **refusés**. Le fichier est stocké par son empreinte (réutilisez `niveau3_config/stockage.py`).
3. **Export (C5)** : copie du fichier d'origine, écriture **des seules cellules désignées**, mise en forme intacte,
   rapport **publié** (scellé) comme source. Un test relit le fichier produit et vérifie : valeurs écrites ;
   formules **intactes** ; styles intacts ; cellule désignée contenant une formule → **refus**.
4. **Sécurité** : un fichier Excel est une donnée non fiable : limites de taille, pas d'exécution, pas de lien
   externe suivi, pas de macro. Test avec un fichier piégé fabriqué (liens externes, `.xlsm` renommé en `.xlsx`).
5. Les liens entre le moteur (qui calcule déjà les totaux) et les formules Excel : ajoutez un **contrôle de
   cohérence** — la valeur d'une cellule de total calculée par le moteur doit égaler celle que recalcule Excel ;
   sinon avertissement visible.

### 13.2 Si la décision est « valeurs seulement »
Même chose sans le contrôle des formules : les cellules du modèle reçoivent des valeurs, les formules du modèle
sont **remplacées** par les valeurs calculées. Documentez le choix.

**Estimation : 15 à 25 jours.**

---

## 14. Lot 10 — IA documentaire (phase E) ⛔

**Décision préalable, par écrit** : les documents financiers peuvent-ils être envoyés à un service externe ? Sinon,
quel modèle hébergé en interne ? **Tant que la réponse manque, ne branchez aucun service externe**, même « pour
essayer » (les documents des bailleurs et des projets sont confidentiels).

**Principes non négociables** (déjà posés par le plan) :
* une proposition de l'IA dont la **citation n'est pas retrouvée littéralement** dans le document est **rejetée
  automatiquement** (mécanisme existant : `niveau3_config/services/extraction.py`, `exigences.py`) ;
* les propositions deviennent des exigences **« proposées »** ; l'activation reste **humaine** (règle 9) ;
* tout appel est **journalisé** : modèle, version, empreinte du document, empreinte de la consigne, nombre de
  jetons, coût, durée, résultat.

### 14.1 Tâches
**E1 — Appel à un modèle, avec journal, coût et traçabilité.**
1. Table `AppelIA` (RLS, **ajout seul**) : organisation, projet, utilisateur, `fournisseur`, `modele`,
   `empreinte_consigne`, `empreinte_document`, `jetons_entree`, `jetons_sortie`, `cout` (NUMERIC, jamais float),
   `duree_ms`, `statut`, `erreur`.
2. Module `backend/niveau3_config/services/ia.py` : une fonction `appeler_modele(consigne, document, ...)` derrière
   une **interface** (`FournisseurIA`) avec deux implémentations : `FournisseurFactice` (pour les tests, répond de façon
   déterministe) et le fournisseur réel (selon la décision).
3. **Aucune clé d'API dans le code ni dans le dépôt** : variable d'environnement chargée par la configuration ;
   `check --deploy` refuse de démarrer en production si une fonction IA est activée sans clé.
4. **Plafonds** : taille maximale du document, nombre d'appels par jour et par organisation, **coût maximal**
   configurable. Dépassement → refus net (422), journalisé.
5. Tests : tout avec le fournisseur **factice** ; un test vérifie que le journal est écrit **même si l'appel échoue**
   (sans être annulé par la transaction de la requête : voir le motif utilisé pour `DocumentIntegrite`).

**E2 — Extraction de règles avec vérification littérale.** `proposer_depuis_document(document)` : demande au modèle
des règles **avec leur citation**, puis pour chaque proposition appelle la vérification existante (la citation
doit être retrouvée **mot pour mot**, après normalisation typographique, à la page indiquée). Test : une citation
inventée par le fournisseur factice est rejetée et **comptée** ; une citation exacte est retenue.

**E3 — Propositions → exigences « proposées ».** Réutilisez `proposer_exigence` (`niveau3_config/services/exigences.py`).
Test : aucune proposition n'arrive jamais « active » ; le statut est forcé côté base (déclencheur existant).

**E4 — Comparaison avenant / convention initiale ; contradictions entre documents.** Sortie = une liste de
différences **avec citations vérifiées** des deux côtés ; jamais de conclusion sans citation.

**E5 — Évaluation sur de vrais documents, précision publiée.**
1. Constituez un **jeu de référence** : 10 à 20 documents (fournis par vous, avec accord), pour lesquels une
   personne a écrit **à la main** les règles attendues (avec page et phrase).
2. Écrivez un script `scripts/evaluer_ia.py` qui compare, calcule **précision** (parmi les propositions retenues,
   la part correcte) et **rappel** (parmi les règles attendues, la part retrouvée).
3. **Publiez les chiffres** dans `docs/EVALUATION_IA.md` (date, modèle, version, jeu, scores, cas d'échec).
   N'annoncez jamais « fiable » sans ces chiffres.

**Estimation : 20 à 35 jours, après la décision.**

---

## 15. Lot 11 — Exploitation

À faire par le propriétaire du compte ou l'administrateur (je ne peux pas le faire à votre place) :
1. **Repasser `tom-tom` en privé** si ce n'est pas voulu : GitHub → Settings → General → Danger Zone → Change
   visibility. (Il est public à ce jour.)
2. **Révoquer tous les jetons GitHub** utilisés pendant la migration (GitHub → Settings → Developer settings →
   Personal access tokens). Un jeton a été collé dans une conversation : il est à considérer comme compromis.
3. **Protéger `main`** : Settings → Branches → règle sur `main` : pull request obligatoire, contrôles `backend` et
   `frontend` obligatoires, interdiction du push direct et du force-push.
4. **Secrets** : si vous ajoutez un déploiement ou l'IA, créez les secrets dans Settings → Secrets and variables →
   Actions ; **jamais dans le code**.
5. **Déploiement** (Fly) : il se fait depuis un poste qui a `flyctl` et les droits ; les branches `deploiement-fly`
   et `deploiement-new-tom` contiennent la configuration existante. Procédure : lisez-les, déployez d'abord en
   préproduction, vérifiez `manage.py check --deploy`, lancez les migrations avec le rôle **propriétaire**
   (`config.settings.migrate`), jamais avec le rôle applicatif.
6. **Sauvegardes** : vérifiez que la base de production est sauvegardée et qu'une **restauration** a été essayée
   au moins une fois (le projet sait exporter et restaurer une organisation : lot L8).
7. **Le Mac de l'équipe** n'est pas atteignable depuis les sessions automatiques : tout ce qui nécessite le Mac
   (déploiement, fichiers locaux) se fait à la main.

---

## 16. Ordre d'exécution recommandé et durées

| Ordre | Lot | Dépend de | Durée (jours, ordre de grandeur) |
|---|---|---|---|
| 1 | Lot 0 — débloquer et fusionner D4 à D9 | rien | 1 à 2 |
| 2 | Lot 1 — revue de code L11 | Lot 0 | 3 à 5 |
| 3 | Lot 2.D — économie de CI | Lot 0 | 0,5 |
| 4 | Lot 5.1 — faux serveur + écran « Profils de décaissement » | Lot 0 | 6 à 8 |
| 5 | Lot 2.A à 2.C — mot de passe, pagination, jeton | Lot 1 | 6 à 10 |
| 6 | Lot 5.4 — écrans E2 à E9 | écran modèle | 20 à 30 |
| 7 | Lot 3 — numérotation BAD, lien contrat | Lot 1 | 8 à 12 |
| 8 | Lot 4 — périodes libres | Lot 1 | 4 à 6 |
| 9 | Lot 6.1 — recette multibailleur (version 1) | Lots 0, 1 | 6 à 10 |
| — | Lots 7, 8, 9, 10 | **documents / décisions** | 5-10 par bailleur · 8-12 · 15-25 · 20-35 |
| fin | Lot 11 — exploitation | — | en parallèle, dès le début pour les points 1 à 3 |

Total sans les lots bloqués : environ **60 à 95 jours-développeur**. Avec les lots bloqués : **110 à 200**. Ce sont
des ordres de grandeur pour une personne qui débute ; ne les prenez pas pour des engagements.

### Quand vous êtes bloqué
1. Relisez le **test qui échoue**, ligne par ligne, avant de relire votre code.
2. Cherchez comment le projet a déjà résolu un cas **semblable** (`grep -rn` dans `backend/` et `tests/`) : presque
   tout a un précédent.
3. Si la base se comporte « bizarrement » dans un test d'API : c'est presque sûrement le piège n° 1 (annexe F).
4. Après **une heure** sans progrès, demandez de l'aide en donnant : la commande lancée, la sortie complète, ce
   que vous avez essayé.
5. **Ne contournez jamais** : pas de test supprimé, pas de `--no-verify`, pas de push sur `main`, pas de
   désactivation de la sécurité par organisation.

---

# Annexes

## Annexe A — Commandes de tous les jours

Depuis `backend/` (variables d'environnement de l'étape 1.5 posées) :

| Je veux… | Commande |
|---|---|
| vérifier la configuration | `./.venv/bin/python manage.py check` |
| appliquer les migrations (rôle propriétaire) | `./.venv/bin/python manage.py migrate --settings=config.settings.migrate` |
| créer une migration après avoir changé un modèle | `./.venv/bin/python manage.py makemigrations <application> -n <nom_court>` |
| vérifier qu'il ne manque aucune migration | `./.venv/bin/python manage.py makemigrations --check --dry-run` |
| lancer un fichier de test | `./.venv/bin/pytest -q --no-cov -p no:cacheprovider tests/test_xxx.py` |
| lancer un seul test | `./.venv/bin/pytest -q --no-cov -p no:cacheprovider tests/test_xxx.py::test_yyy` |
| lancer les tests dont le nom contient un mot | `... tests/test_xxx.py -k "mot"` |
| tout lancer, avec couverture (comme la CI) | `./.venv/bin/pytest -q --cov=. --cov-report=term-missing` |
| corriger le style | `./.venv/bin/ruff check --fix . && ./.venv/bin/ruff format .` |
| régénérer le dictionnaire de données | `./.venv/bin/python manage.py generer_dictionnaire` |
| vérifier les citations d'un profil | `./.venv/bin/python manage.py verifier_citations_profil <profil> --dossier <dossier>` |

Depuis `frontend/` : `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`, `npm run dev` (serveur local).

Git : `git status`, `git diff`, `git log --oneline main..HEAD` (ce que ma branche ajoute), `git add -A && git commit -m "..."`,
`git push -u origin <branche>`.

---

## Annexe B — Gabarit d'un test d'API (modèle à copier)

Les tests d'API utilisent l'aide `appeler`, et des fixtures qui fabriquent une organisation, un projet et des
utilisateurs : `cadre` (dora *paramètre*, nadia *paramètre + voir les numéros de compte*), `api` (ajoute amina
*saisir*, bruno *valider*, claire *comptabiliser*, pia *publier*).

```python
# ruff: noqa: F811, E501
"""L'API de <ce que vous faites>. Une phrase : ce qui manquait avant."""

import pytest
from django.db import connection

from tests.test_api_marches_bd import api, appeler      # noqa: F401  (fixtures importées)
from tests.test_cycle_ecriture_bd import decor          # noqa: F401
from tests.test_financements_bd import cadre            # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)    # OBLIGATOIRE pour les tests d'isolation


def _poser(organisation):
    """Après un appel HTTP, la base oublie l'organisation : on la repose avant de lire en base."""
    with connection.cursor() as cur:
        cur.execute("SET app.org_id = %s", [str(organisation.id)])


def _nb(api, modele, **filtres) -> int:
    """Compter EN BASE. Sans _poser, la sécurité par organisation cache tout et on compte toujours 0 :
    un test « rien n'a été créé » passerait à vide (piège n° 1)."""
    _poser(api[0])
    return modele.objects.filter(**filtres).count()


def test_une_ressource_se_cree_et_se_relit(api):
    organisation, projet, profils, _ = api
    r = appeler(profils["dora"], "post", f"/projets/{projet.id}/ressources/", {"nom": "x"})
    assert r.status_code == 201, r.content          # r.content montre l'erreur si ça échoue
    assert r.json()["nom"] == "x"


def test_sans_droit_c_est_403(api):
    _, projet, profils, _ = api
    assert appeler(profils["amina"], "post", f"/projets/{projet.id}/ressources/", {}).status_code == 403


def test_un_corps_invalide_est_refuse_au_format_stable_et_rien_n_est_cree(api):
    _, projet, profils, _ = api
    r = appeler(profils["dora"], "post", f"/projets/{projet.id}/ressources/", {"nom": ""})
    assert r.status_code == 422 and set(r.json()) == {"code", "message"}
    assert _nb(api, Ressource) == 0                 # compte réel grâce à _poser
```
Pour chaque endpoint, écrivez au minimum : succès, **sans droit (403)**, **corps invalide (422 `{code, message}`)**,
**objet introuvable ou d'un autre projet (404)**, **rien n'est créé après un refus**, et si c'est un montant :
`"abc"`, `"NaN"`, un flottant JSON, un négatif.

---

## Annexe C — Gabarit d'une nouvelle table (modèle + migration + sécurité par organisation)

1. **Modèle** : hérite de `ModeleOrganisation` (`from core.models import ModeleOrganisation`) ; montants en
   `MontantField` (`from core.fields import MontantField`) ; contraintes `CheckConstraint` nommées ; **`org_id` est
   déjà fourni par `ModeleOrganisation`**.
2. `./.venv/bin/python manage.py makemigrations <application> -n <nom>` : Django écrit le `CreateModel`.
3. **Ouvrez la migration** et ajoutez, à la fin de `operations`, la sécurité par organisation et vos garde-fous :
```python
from core.migrations._rls import activer_rls, desactiver_rls

TABLE = "<application>_<modele_en_minuscules>"
SQL = """
-- une clé étrangère « même organisation » (référence la contrainte UNIQUE (org_id, id) de l'autre table)
ALTER TABLE <table> ADD CONSTRAINT fk_<nom>_meme_org
  FOREIGN KEY (org_id, <colonne>_id) REFERENCES <autre_table> (org_id, id);
-- déclencheurs : règles que le code ne doit pas pouvoir contourner (ajout seul, même projet, plafond…)
"""
SQL_INVERSE = "ALTER TABLE <table> DROP CONSTRAINT fk_<nom>_meme_org;"

operations = [
    # ... CreateModel généré ...
    migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
    migrations.RunSQL(activer_rls(TABLE), reverse_sql=desactiver_rls(TABLE)),
]
```
   Modèle complet à lire : `backend/niveau1_socle/tresorerie/migrations/0003_justification_compte_special.py`
   (déclencheur de naissance, « ajout seul sauf annulation », plafond).
4. `./.venv/bin/python manage.py makemigrations --check --dry-run` : « No changes detected ».
5. **Dictionnaire** : `./.venv/bin/python manage.py generer_dictionnaire` et commitez `DICTIONNAIRE_DE_DONNEES.md`.
6. `tests/test_isolation.py` vérifie tout seul que votre table a sa politique ; ne l'étendez **pas** pour y
   ajouter une exception (règle 4).
7. **Tests de la base** (en plus de ceux du service) : une tentative directe par l'ORM de violer chaque garde-fou
   doit lever `IntegrityError` (modèle : `test_la_base_refuse_...` dans `tests/test_compte_special_bd.py`).

---

## Annexe D — Gabarit de la note « Réalisation » (dans le plan 06)

```markdown
### Réalisation — <code de la tâche> : <titre court>

`<chemins des fichiers principaux>`, `<tests>` (<nombre> tests). <Une phrase : quelle limite ou quel manque
précédent cette tâche lève.>

- **Ce qui est livré** : <puces factuelles, avec les routes ou fonctions>.
- **Règles tenues** : <règle 4, règle 9… celles qui comptaient ici>.
- **Mutations** : <nombre> détectées ; <les survivantes et ce qu'elles ont fait ajouter>.
- **Limites assumées** : <ce qui n'est PAS fait, honnêtement>.
```
Une note qui ne dit pas ses limites n'est pas acceptée.

---

## Annexe E — Vérifier ses tests par mutation (le script à copier)

**Idée.** Un test qui ne peut pas échouer ne prouve rien. On casse le code **à un seul endroit**, on relance les
tests concernés, et on **exige qu'un test échoue**. S'il passe, la mutation « survit » : il manque un test.

```python
# /tmp/mutrun.py  (hors du dépôt)
import subprocess

PYTEST = "./.venv/bin/pytest"

def run(fichier, mutations, tests, selection):
    """mutations = [(nom, (ancien, nouveau)), ...] ; `ancien` doit exister EXACTEMENT dans le fichier."""
    original = open(fichier).read()
    try:
        for nom, (ancien, nouveau) in mutations:
            assert ancien in original, f"texte absent : {nom}"
            open(fichier, "w").write(original.replace(ancien, nouveau, 1))
            r = subprocess.run([PYTEST, "-q", "--no-cov", "-p", "no:cacheprovider", "-x", tests, "-k", selection],
                               capture_output=True, text=True)
            print("==", nom, "->", r.stdout.strip().splitlines()[-1])   # « 1 failed » = bien
    finally:
        open(fichier, "w").write(original)                              # TOUJOURS restaurer
```
Mutations utiles : supprimer une vérification d'habilitation ; remplacer `<=` par `<` ; supprimer un
`select_for_update` ; retirer une validation ; renvoyer une valeur constante ; échanger deux champs.
**Interdit** : restaurer avec `git checkout <fichier>` (vous perdriez vos modifications non commitées) ; utilisez la
sauvegarde du script ou `cp`. Après les mutations : `git diff --stat` doit être identique à avant.
Certaines mutations sont **équivalentes** (le comportement ne change pas, parce qu'un autre garde-fou fait le même
travail) : notez-les dans la note « Réalisation » au lieu d'ajouter un test artificiel.

---

## Annexe F — Les pièges déjà rencontrés (lisez-les avant de vous énerver)

1. **La base « oublie » l'organisation après un appel HTTP.** Un `.count()` renvoie 0 alors que la ligne existe.
   Faites `SET app.org_id = ...` (annexe B). Un test « rien n'a été créé » sans cela passe à vide.
2. **Action de journal trop longue** : `core_auditlog.action` est limité à **32 caractères**
   (`special_account_justification_recorded` en a 38 : erreur « value too long »).
3. **Messages** : chaque clé du catalogue est utilisée **avec exactement ses paramètres**, existe en `fr` **et** `en`,
   et une clé jamais utilisée est une erreur (`tests/test_catalogue_messages.py`).
4. **Style** : lignes de **100 caractères au plus**, y compris dans les docstrings et les commentaires. Lancez
   `ruff format .` *puis* `ruff check .`. Pas de `lambda` assignée (`def` à la place).
5. **Deux `pytest` en même temps = base de test détruite** : erreurs en cascade (`database "test_sigf" does not
   exist`). Un seul `pytest` à la fois.
6. **PostgreSQL arrêté** : `connection refused`. Relancez-la (`docker compose -f infra/docker-compose.yml up -d`).
7. **Une instance périmée** : après `activer_controle(...)`, utilisez l'objet **retourné**, pas celui que vous aviez
   lu avant (il garde l'ancien statut).
8. **Un accord activé ne se modifie plus** (déclencheur de base) : pour un test qui a besoin d'une date de fin,
   créez un **nouvel** accord avec cette date dès la création.
9. **Deux versions « actives » d'une exigence ne peuvent pas se chevaucher** (contrainte d'exclusion) : dans un test,
   mettez la plus ancienne à l'état `validated`, pas `active`.
10. **Un contrôle s'évalue avec un déclencheur** : `utilisateur=` **ou** `service="nom"`, jamais les deux ni aucun.
11. **Les décimaux** : la base rend `"200.0000"` (4 décimales) alors qu'un calcul en mémoire donne `"0"`.
    Comparez avec `Decimal(...)`, pas avec une chaîne, sauf si le format est le sujet du test.
12. **Les tables « ajout seul »** (journal, soldes de relevé, justifications…) lèvent `IntegrityError` à la
    modification : testez avec `with pytest.raises(IntegrityError), transaction.atomic(): ...`.
13. **La date du jour** : un test ne doit jamais dépendre de « aujourd'hui ». Fixez des dates (`datetime.date(2026, 3, 20)`).
    (Une justification créée « aujourd'hui » était exclue d'un état daté de mars : bug de test réel.)
14. **Mutation qui « ne s'applique pas »** : `ruff format` a reformaté votre texte. Le script de l'annexe E vous
    prévient (`texte absent`) ; copiez le texte **depuis le fichier tel qu'il est maintenant**.
15. **Dictionnaire de données** : toute modification d'un modèle rend `DICTIONNAIRE_DE_DONNEES.md` périmé et fait
    échouer `tests/test_dictionnaire.py` : régénérez-le.
16. **Migrations en conflit** : deux branches qui créent `0004_...` dans la même application → renumérotez la
    plus récente et corrigez sa `dependencies`.
17. **Multipart** : DRF n'accepte du multipart que si la vue déclare `parser_classes = [JSONParser, MultiPartParser, FormParser]`.
18. **Journal en cas d'erreur** : lever une exception annule la transaction de la requête, donc **aussi** le journal
    que vous venez d'écrire. Pour garder une trace d'un refus (altération d'un fichier, par exemple), renvoyez une
    **réponse** normale (409) au lieu de lever.
19. **Deux CI par push** tant que le Lot 2.D n'est pas fait : c'est normal, ne vous en inquiétez pas.
20. **Une session perdue dans les tests du frontend** (401) : vos tests doivent appeler `ouvrirSession(...)`, voir
    `frontend/src/test/monter.tsx`.

---

## Annexe G — Glossaire

* **Accord** : un financement signé avec un bailleur (numéro, devise, montant, dates, catégories, avenants).
* **Avenant** : modification d'un accord ; l'accord ne change jamais, l'avenant porte les nouvelles valeurs.
* **Catégorie** : ligne de ventilation d'un accord, avec son plafond ; peut avoir des sous-catégories.
* **Clé de cofinancement** : la répartition d'une dépense entre plusieurs accords (parts ou poids), versionnée.
* **Compte désigné** (Banque mondiale) / **compte spécial** (BAD) : compte bancaire qui reçoit les avances du
  bailleur ; deux types distincts dans l'application.
* **Contrôle** : une règle évaluée sur une dépense, une demande ou un rapport ; résultat réussi / bloquant /
  avertissement / information / à vérifier. **Dérogation** : autorisation formelle, bornée, de poursuivre malgré un
  résultat bloquant, approuvée par une personne **autre** que le demandeur.
* **Demande de retrait (DRF)** : demande de décaissement adressée au bailleur ; porte des lignes (dépenses) et un
  « état certifié ».
* **Exigence** : une obligation de reporting ou de conformité, **proposée → validée → active**, avec sa citation
  vérifiée dans un document.
* **IFR / RFI** : rapport financier intermédiaire. **SOE** : état certifié des dépenses.
* **Mapping** : table de correspondance entre comptes comptables et rubriques d'un rapport.
* **Modèle d'état** : description (JSON) d'un rapport que le moteur sait produire (colonnes, rubriques, formules).
* **Profil de bailleur** : bibliothèque (JSON) de ce que *peut* demander un bailleur, avec citations ; ne s'applique
  jamais tout seul. **Profil de décaissement** : le paramétrage d'**un accord** (méthodes, taux par catégorie,
  dates, comptes), versionné.
* **RLS (Row-Level Security)** : mécanisme PostgreSQL qui filtre les lignes par organisation ; c'est lui, et non le
  code, qui isole les organisations (règle 4).
* **Version** : une configuration utilisée ne se modifie pas ; on en crée une nouvelle avec une date d'effet.
* **VueMetier** : classe de base des vues d'API du projet (`backend/core/api.py`).

---

## Annexe H — Liste de contrôle avant d'ouvrir une pull request

- [ ] Le **test** que j'ai écrit **échouait avant** mon code (j'ai vérifié).
- [ ] `ruff check .` et `ruff format --check .` sont propres ; `npm run typecheck && npm run lint` aussi si j'ai
      touché au frontend.
- [ ] J'ai lancé les tests de **mon** module **et** ceux des modules voisins.
- [ ] J'ai fait la **vérification par mutation** (annexe E) ; les survivantes sont corrigées ou expliquées.
- [ ] Aucun `float` sur un montant ; aucun `org_id` filtré à la main ; aucun `left`/`right` en CSS.
- [ ] Tous les messages passent par le catalogue, en français **et** en anglais.
- [ ] Nouvelle table : migration + RLS + dictionnaire régénéré (annexe C).
- [ ] Aucun test supprimé, ignoré ou affaibli.
- [ ] Les **tests d'API** reposent l'organisation avant de compter en base (piège n° 1).
- [ ] La note « Réalisation » est écrite, **avec ses limites** (annexe D).
- [ ] `CLAUDE.md` est à jour si l'état du projet a changé.
- [ ] La description de la PR dit : ce que ça fait, ce que ça ne fait pas, comment le vérifier.
- [ ] **La CI est verte** avant la fusion. Fusion par « merge commit ».
