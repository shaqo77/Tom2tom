# SIGF — plateforme de gestion financière et de reporting multi-bailleurs

Backend Django + PostgreSQL pour les unités de gestion de projet financées par des bailleurs.
Le domaine est francophone : noms de modèles, de champs, de tests et messages sont en **français**.
Seuls les champs techniques standard restent en anglais (`org_id`, `project_id`, `created_at`).

Documents de référence, à lire avant de toucher à l'architecture :
`01_SPECIFICATION_FONCTIONNELLE.md`, `02_ARCHITECTURE_TECHNIQUE.md`, `03_GUIDE_DEMARRAGE.md`
(conventions, partie B ; règles, partie C), `04_PLAN_LOTS_L0_A_L4.md`, `05_PLAN_LOTS_L5_A_L10.md`.
État actuel : lot **L0** (prototype du moteur d'états). `niveau1_socle/`, `niveau2_profils/`,
`niveau3_config/` sont des dossiers encore vides.

## Commandes (depuis `backend/`)

| But | Commande |
|---|---|
| Vérifier le projet | `./.venv/bin/python manage.py check` |
| Migrations (rôle propriétaire) | `./.venv/bin/python manage.py migrate --settings=config.settings.migrate` |
| Tests | `./.venv/bin/pytest -q` |
| Style | `./.venv/bin/ruff check . && ./.venv/bin/ruff format --check .` |

Base locale : `docker compose -f infra/docker-compose.yml up -d`, puis **une fois** `scripts/bootstrap_db.sh`.
La CI (`.github/workflows/ci.yml`) est la référence : PostgreSQL 16, tables dans `public`, rôle `sigf_app`
avec `CREATEDB` (la suite crée sa propre base de test).

Environ 30 tests exigent une vraie PostgreSQL (`*_bd.py`, `test_isolation`, `test_middleware`,
`test_audit`, deux tests de `test_checks`). Sans base, les tests de logique pure tournent quand même
(formules, assertions, compilateur, dépendances, mapping, conventions).

## Les règles à ne jamais enfreindre

1. Aucun `float` sur un montant (`MontantField`/`TauxField`, `NUMERIC` exact, `Decimal` partout).
2. Aucune modification d'une écriture comptabilisée : on contre-passe.
3. Aucun trou dans la numérotation d'un journal.
4. **Aucun filtre `org_id` écrit à la main.** L'isolation est assurée par la Row-Level Security.
5. Aucune `eval`/`exec` sur une formule utilisateur. Les formules et assertions passent par un langage borné.
6. Aucune écriture dans une période close.
7. Aucune mise à jour d'une configuration déjà utilisée : on crée une nouvelle version (`version`, `valid_from`, `valid_to`).
   Validité en intervalle semi-ouvert `[valid_from, valid_to[` : `valid_to` est **exclu** (guide §B.6).
8. Aucune génération de rapport avec un mapping incomplet.
9. Aucune activation automatique d'une exigence.
10. Aucun `left`/`right` codé en dur dans le CSS (l'arabe viendra).

Les libellés sont du JSONB, jamais `label_fr`/`label_en`. Un test de conventions les interdit.

## Isolation par organisation — ce qui est subtil

- Tout modèle métier hérite de `ModeleOrganisation` (`org_id`). Toute nouvelle table reçoit sa politique
  avec `activer_rls()` (`core/migrations/_rls.py`) dans une migration `RunSQL`.
- **Une seule exception à l'isolation par `org_id` : `organisations_utilisateur`.** Le login doit lire le
  compte avant de connaître l'organisation ; `AUTH_USER_MODEL` est `organisations.Utilisateur` (clé UUID,
  `org_id` nul pour un compte de plateforme, qui ne voit alors aucune donnée métier). L'exception est déclarée
  dans `tests/test_isolation.py` (`TABLES_SANS_ISOLATION`) : ne l'étendez pas sans décision écrite.
  L'organisation elle-même est isolée par sa propre clé `id`.
- Le projet (`project_id`) n'est **pas** isolé par RLS : le tableau de bord multi-projets et la
  consolidation l'interdisent. Il sera cloisonné par habilitation applicative (lot L1).
- `OrganisationScopeMiddleware` ouvre **lui-même** une transaction avant `SET LOCAL app.org_id`.
  `ATOMIC_REQUESTS` n'enveloppe que la vue, pas les middlewares : sans cette transaction, le réglage
  est jeté et la vue ne voit aucune ligne. Ne retirez pas ce `transaction.atomic()`.
- **Les tests d'isolation doivent tourner en `django_db(transaction=True)`.** Sous le mode par défaut,
  pytest-django enveloppe chaque test dans une transaction qui fait survivre un `SET LOCAL` mal placé
  et masque le défaut. Dans ces tests, posez le périmètre avec `SET` (session) et remettez-le avec `RESET`.
- Le schéma applicatif est celui où Django pose réellement ses tables : `public` en CI, `sigf` en
  exploitation (`DB_SCHEMA`). Ne codez jamais `n.nspname = 'public'` ; résolvez-le avec
  `to_regclass('core_auditlog')`, comme `test_toute_table_avec_org_id_a_sa_politique`.
- Deux rôles PostgreSQL : `sigf_owner` (migrations, possède `BYPASSRLS`) et `sigf_app` (application,
  soumis à la RLS). `core/checks.py` refuse de démarrer si le rôle connecté a `BYPASSRLS`/`SUPERUSER`,
  y compris via `config/asgi.py` (un serveur ASGI n'exécute aucun contrôle système sinon).
  `config.settings.migrate` désactive ce contrôle, car le propriétaire doit pouvoir migrer.
- `core_auditlog` est en ajout seul (INSERT/SELECT uniquement pour `sigf_app`), chaîné par empreinte.

## Secrets et environnement

- `backend/.env` n'est pas versionné. **Ne le créez pas avec de vrais identifiants.**
- Ne vous connectez jamais à la base Supabase de production, même en lecture. Pour les tests, utilisez
  une PostgreSQL locale ou jetable, avec les rôles créés par `scripts/bootstrap_db.sh`.
- Ne placez jamais `DATABASE_OWNER_URL` dans `DATABASE_URL`.
- Un rôle applicatif ne reçoit jamais `BYPASSRLS`, et `service_role`/`anon`/`authenticated` n'ont aucun
  droit sur le schéma applicatif.

## Conventions

- Modèle : français, singulier, `PascalCase` (`LigneEcriture`). Champ : français, `snake_case`.
- Test : `test_` + phrase lisible en français (`test_une_ecriture_desequilibree_est_refusee`).
- Les noms de colonnes interpolés dans du SQL passent par une liste blanche ; toutes les valeurs
  sont des paramètres. Aucune expression utilisateur n'est interpolée.
- Python 3.12, ruff (ligne 100). Les migrations sont exclues de ruff.

## Travail en équipe

- Une branche par tâche : `L3-T07-numerotation-sans-trou`. Message de commit : `L3-T07: numérotation sans trou par compteur verrouillé`.
- Un test qui prouve un correctif doit **échouer avant** le correctif : vérifiez-le en restaurant temporairement l'ancien code.
- Une tâche est terminée quand : le code fait ce qui est demandé, un test le prouve (et échouait avant),
  la CI est verte (ruff + pytest + couverture ≥ 80 %), les règles 1, 4 et libellés sont respectées, les
  migrations s'appliquent sur une base vierge, le contrôle de vérification de la tâche a été exécuté.
- Ne contournez jamais la CI et ne poussez jamais sur `main` directement.
