# Backend SIGF — commandes

## Prérequis

La base tourne en conteneur :

```bash
docker compose -f ../infra/docker-compose.yml up -d
```

Puis, **une seule fois avant la première migration**, amorcer le cluster
(schéma applicatif et rôle applicatif) :

```bash
../scripts/bootstrap_db.sh
```

Cette étape est rejouable sans dommage. Elle crée ce que les migrations
supposent déjà présent : le schéma qui les accueille et le rôle `sigf_app`
auquel elles retirent des droits.

## Commandes courantes

| But | Commande (depuis `backend/`) |
|---|---|
| Vérifier le projet | `./.venv/bin/python manage.py check` |
| **Appliquer les migrations** | `./.venv/bin/python manage.py migrate --settings=config.settings.migrate` |
| Créer une migration | `./.venv/bin/python manage.py makemigrations <app>` |
| Générer des données de test | `./.venv/bin/python manage.py generer_donnees --lignes 200000 --purger` |
| Tests | `./.venv/bin/pytest -q` |
| Tests + couverture | `./.venv/bin/pytest -q --cov=core --cov=niveau4_reporting --cov-report=term` |
| Style | `./.venv/bin/ruff check . && ./.venv/bin/ruff format .` |

## Rejouer le contrôle de performance L0-T05

Depuis `backend/`, générer exactement 200 000 lignes dans le périmètre du TER :

```bash
./.venv/bin/python manage.py generer_donnees \
  --lignes 200000 --organisation A --projet 1 --purger
```

Puis, depuis la racine du dépôt :

```bash
backend/.venv/bin/python scripts/mesurer_ter.py
```

Le script échoue si le périmètre ne contient pas exactement 200 000 lignes,
si le TER exécute plus d'une requête, ou si aucune des trois mesures ne passe
sous 3 secondes. Les règles de mapping sont matérialisées avant la mesure :
la sélection de configuration ne doit pas être confondue avec l'agrégation.

## Les deux rôles PostgreSQL

| Rôle | Usage | Jamais pour |
|---|---|---|
| `sigf_owner` | Migrations (`--settings=config.settings.migrate`) | Servir l'application |
| `sigf_app` | Toutes les requêtes de l'application | Exécuter des migrations |

L'application n'a aucun droit de création et subit les politiques d'isolation.
C'est ce qui rend le cloisonnement entre organisations réellement étanche.

Un troisième rôle mérite d'être nommé pour être écarté : sur un hébergement
Supabase, `service_role` **contourne** la sécurité au niveau ligne. Lui ouvrir
le schéma applicatif annulerait l'isolation d'un seul GRANT, sans qu'aucun
test applicatif ne s'en aperçoive. La migration `core.0004` le révoque.

## Héberger la base sur Supabase

Une instance Supabase est un PostgreSQL managé : le socle du projet ne change
pas. Deux points demandent de l'attention.

**Le schéma `public` y est public.** L'API REST de Supabase sert `public` au
rôle anonyme, dont la clé est distribuée au navigateur, et tout objet créé par
le propriétaire y reçoit automatiquement tous les droits pour ce rôle. Les
tables techniques de Django — sessions, utilisateurs — n'ont aucune politique
d'isolation et n'y ont donc pas leur place. Le schéma applicatif est `sigf`
(`DB_SCHEMA=sigf`), que l'API n'expose pas.

**L'accès direct n'est plus joignable en IPv4.** On passe par le pooler en
mode session (port 5432), qui préfixe le rôle de la référence du projet :
`sigf_app.<ref>`. Le mode transaction (port 6543) conviendrait au service,
mais pas aux migrations.

```bash
# backend/.env — voir .env.example pour le détail
DB_SCHEMA=sigf
DB_SSLMODE=require
DATABASE_URL=postgres://sigf_app.<ref>:<mdp>@aws-1-<region>.pooler.supabase.com:5432/postgres
DATABASE_OWNER_URL=postgres://postgres.<ref>:<mdp>@aws-1-<region>.pooler.supabase.com:5432/postgres
```

Puis `../scripts/bootstrap_db.sh`, puis la migration habituelle.

La suite de tests, elle, crée sa propre base : elle demande un cluster sur
lequel le rôle applicatif a le droit `CREATEDB`, ce qui n'est pas le cas d'une
instance Supabase. On la lance donc contre la base locale, en surchargeant les
variables d'environnement :

```bash
DATABASE_URL=postgres://sigf_app:dev_only_change_me@localhost:5432/sigf \
DATABASE_OWNER_URL=postgres://sigf_owner:dev_only_change_me@localhost:5432/sigf \
DB_SCHEMA= DB_SSLMODE= ./.venv/bin/pytest -q
```

## Poser le contexte d'organisation

Toute requête s'exécute dans le périmètre d'une organisation. Le middleware
`core.middleware.OrganisationScopeMiddleware` pose `app.org_id` pour la
transaction de chaque requête HTTP. En script ou en commande :

```python
with connection.cursor() as cur:
    cur.execute("SET app.org_id = %s", [str(org_id)])
```

Sans cela, **aucune ligne n'est visible ni insérable** — c'est le défaut sûr.
