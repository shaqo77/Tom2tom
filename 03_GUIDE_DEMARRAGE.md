# GUIDE DE DÉMARRAGE — SEMAINE 0

**Pour qui :** tout développeur rejoignant le projet, y compris junior.
**Objectif :** partir d'une machine vide et arriver à un projet qui tourne, testé, avec l'intégration continue verte.
**Durée visée :** une journée.

> **Comment lire ce guide.** Chaque étape porte un numéro, une commande à copier, et un **contrôle** à vérifier avant de passer à la suivante. Si un contrôle échoue, **ne continuez pas** : corrigez d'abord. Les conventions de la partie B sont obligatoires — elles ne sont pas des préférences de style, ce sont les règles qui empêchent de produire des chiffres faux.

---

# PARTIE A — MONTER L'ENVIRONNEMENT

## A.1 Prérequis machine

| Outil | Version | Vérification |
|---|---|---|
| Python | 3.12+ | `python3 --version` |
| Node.js | 20+ | `node --version` |
| Docker + Compose | récent | `docker compose version` |
| Git | récent | `git --version` |
| `uv` (gestion des dépendances Python) | récent | `uv --version` |

Installer `uv` si absent :

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Contrôle A.1 :** les cinq commandes répondent sans erreur.

## A.2 Créer le dépôt

```bash
mkdir -p ~/Projects/sigf && cd ~/Projects/sigf && git init
```

## A.3 Structure des dossiers

Créez exactement cette arborescence. **Elle reflète les quatre niveaux de l'architecture** : un développeur doit pouvoir dire, en regardant un fichier, à quel niveau il appartient.

```
sigf/
├── backend/
│   ├── config/                  # réglages Django, URLs, WSGI/ASGI
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── dev.py
│   │   │   └── prod.py
│   │   ├── urls.py
│   │   └── asgi.py
│   ├── core/                    # transversal : Money, modèles de base, RLS, audit
│   │   ├── models.py
│   │   ├── fields.py
│   │   ├── middleware.py
│   │   ├── audit.py
│   │   └── migrations/
│   ├── niveau1_socle/           # NIVEAU 1 — socle commun
│   │   ├── organisations/       #   organisations, projets, utilisateurs, habilitations
│   │   ├── referentiels/        #   plans, axes, comptes, tiers, devises, exercices
│   │   ├── comptabilite/        #   écritures, lettrage, rapprochement, clôtures
│   │   ├── budget/              #   budgets, versions, disponible
│   │   ├── financements/        #   bailleurs, accords, catégories, DRF, comptes désignés
│   │   ├── tresorerie/          #   comptes bancaires, mouvements, prévisions
│   │   ├── marches/             #   plan de passation, non-objections, contrats
│   │   └── documents/           #   pièces justificatives, classement
│   ├── niveau2_profils/         # NIVEAU 2 — profils de bailleurs
│   ├── niveau3_config/          # NIVEAU 3 — documents de référence, exigences
│   ├── niveau4_reporting/       # NIVEAU 4 — mapping, moteur d'états, scellement
│   │   ├── mapping/
│   │   ├── moteur/              #   analyseur de formules, compilateur SQL
│   │   └── publication/         #   scellement, dossier de conformité
│   ├── paquets/                 # paquets réglementaires (PCG Djibouti, plan projet…)
│   ├── tests/
│   ├── manage.py
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/                 # routage, mise en page
│   │   ├── features/            # un dossier par domaine métier
│   │   ├── shared/              # composants, hooks, utilitaires
│   │   └── i18n/                # traductions + prise en charge droite-à-gauche
│   ├── package.json
│   └── vite.config.ts
├── infra/
│   ├── docker-compose.yml
│   └── sql/                     # SQL que Django ne sait pas exprimer (RLS, déclencheurs)
├── docs/
├── .github/workflows/ci.yml
└── README.md
```

```bash
cd ~/Projects/sigf
mkdir -p backend/{config/settings,core/migrations,tests,paquets}
mkdir -p backend/niveau1_socle/{organisations,referentiels,comptabilite,budget,financements,tresorerie,marches,documents}
mkdir -p backend/niveau2_profils backend/niveau3_config
mkdir -p backend/niveau4_reporting/{mapping,moteur,publication}
mkdir -p frontend/src/{app,features,shared,i18n}
mkdir -p infra/sql docs .github/workflows
```

**Contrôle A.3 :** `find . -type d -not -path '*/.git/*' | sort` affiche l'arborescence ci-dessus.

## A.4 Base de données en conteneur

`infra/docker-compose.yml` :

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: sigf
      POSTGRES_USER: sigf_owner
      POSTGRES_PASSWORD: dev_only_change_me
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sigf_owner -d sigf"]
      interval: 5s
      retries: 10

  minio:                      # stockage objet pour les pièces justificatives
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: sigf
      MINIO_ROOT_PASSWORD: dev_only_change_me
    ports: ["9000:9000", "9001:9001"]
    volumes: ["miniodata:/data"]

volumes:
  pgdata:
  miniodata:
```

```bash
cd infra && docker compose up -d && cd ..
```

**Contrôle A.4 :** `docker compose -f infra/docker-compose.yml ps` montre `db` en état `healthy`.

### A.4.1 Le rôle applicatif — étape à ne pas sauter

L'application **ne doit jamais** se connecter avec le propriétaire des tables. C'est ce qui rend l'isolation des organisations réellement étanche.

```bash
scripts/bootstrap_db.sh
```

Le script lit `backend/.env`, se connecte avec le rôle propriétaire et
exécute `infra/sql/00_bootstrap_roles.sql` : création du schéma applicatif
`sigf`, du rôle `sigf_app`, et des privilèges par défaut qui rendront
lisibles au rôle applicatif les tables que les migrations créeront ensuite.
Il est rejouable sans dommage et aligne le mot de passe du rôle applicatif
sur celui de `DATABASE_URL` — une seule source, donc pas de désaccord
possible entre les deux.

Il s'exécute **avant la première migration**, puisque `core.0002` retire des
droits à `sigf_app` et que `core.0004` échoue explicitement si le rôle manque.

| Rôle | Usage | Jamais utilisé pour |
|---|---|---|
| `sigf_owner` | Migrations uniquement | Servir les requêtes de l'application |
| `sigf_app` | Toutes les requêtes de l'application | Exécuter des migrations |

> **Pourquoi.** Le propriétaire d'une table contourne les politiques de sécurité au niveau ligne, sauf si l'on force explicitement. Nous forçons **et** nous utilisons un rôle non propriétaire : deux barrières plutôt qu'une.

**Contrôle A.4.1 :** `psql -U sigf_app -d sigf -c "select current_user"` répond `sigf_app`.

### A.4.2 Si la base est hébergée sur Supabase

Rien ne change au socle : Supabase est un PostgreSQL managé, et la sécurité au
niveau ligne que nous employons y est native. Deux précautions s'imposent
néanmoins, et elles sont la raison d'être du schéma `sigf`.

Sur une instance Supabase, le schéma `public` est **servi par l'API REST au
rôle anonyme**, dont la clé est publiée au navigateur ; et tout objet que le
propriétaire y crée reçoit automatiquement tous les droits pour ce rôle. Les
tables techniques de Django — sessions, utilisateurs — n'ont aucune politique
d'isolation : les laisser dans `public` reviendrait à les publier. On pose donc
`DB_SCHEMA=sigf`, et l'API ne voit plus rien. Le rôle `service_role`, qui
contourne la sécurité au niveau ligne, est révoqué du schéma par `core.0004`.

L'accès direct `db.<ref>.supabase.co` n'a plus d'adresse IPv4 : on passe par le
pooler en mode session (port 5432), qui préfixe le rôle de la référence du
projet — `sigf_app.<ref>`. Le mode transaction (port 6543) convient au service
mais pas aux migrations.

```bash
# backend/.env
DB_SCHEMA=sigf
DB_SSLMODE=require
DATABASE_URL=postgres://sigf_app.<ref>:<mdp>@aws-1-<region>.pooler.supabase.com:5432/postgres
DATABASE_OWNER_URL=postgres://postgres.<ref>:<mdp>@aws-1-<region>.pooler.supabase.com:5432/postgres
```

**Contrôle A.4.2 :** une requête sur l'API publique répond `404` pour chacune
des tables, qu'elle porte ou non une politique d'isolation :

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  "https://<ref>.supabase.co/rest/v1/moteur_ligneecriture?select=*" \
  -H "apikey: <clé anonyme>"
```

## A.5 Projet Django

`backend/pyproject.toml` :

```toml
[project]
name = "sigf"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "django>=5.0",
  "djangorestframework>=3.15",
  "psycopg[binary]>=3.1",
  "django-environ>=0.11",
  "procrastinate[django]>=2.0",
  "openpyxl>=3.1",
  "pydantic>=2.6",
]

[dependency-groups]
dev = [
  "pytest>=8", "pytest-django>=4.8", "pytest-cov>=5",
  "hypothesis>=6",          # tests de propriété sur les montants
  "model-bakery>=1.17",
  "ruff>=0.4", "mypy>=1.9",
]

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings.dev"
python_files = "test_*.py"
addopts = "--strict-markers"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "S", "DJ"]
```

```bash
cd backend
uv sync
uv run django-admin startproject config .   # réutilise le dossier config/ créé plus haut
```

**Contrôle A.5 :** `uv run python manage.py --version` affiche une version 5.x.

## A.6 Réglages

`backend/config/settings/base.py` :

```python
import environ
from pathlib import Path
from decimal import DefaultContext, setcontext, ROUND_HALF_UP

BASE_DIR = Path(__file__).resolve().parent.parent.parent
env = environ.Env()

# --- Règle monétaire globale : arrondi explicite, jamais implicite ---
DefaultContext.prec = 28
DefaultContext.rounding = ROUND_HALF_UP
setcontext(DefaultContext)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.staticfiles",
    "rest_framework", "procrastinate.contrib.django",
    "core",
    "niveau1_socle.organisations", "niveau1_socle.referentiels",
    "niveau1_socle.comptabilite", "niveau1_socle.budget",
    "niveau1_socle.financements", "niveau1_socle.tresorerie",
    "niveau1_socle.marches", "niveau1_socle.documents",
    "niveau2_profils", "niveau3_config",
    "niveau4_reporting.mapping", "niveau4_reporting.moteur",
    "niveau4_reporting.publication",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.OrganisationScopeMiddleware",   # <= pose app.org_id
]

DATABASES = {"default": env.db("DATABASE_URL")}

# Chaque requête HTTP est UNE transaction.
# Obligatoire : « SET LOCAL » ne vit que le temps d'une transaction.
DATABASES["default"]["ATOMIC_REQUESTS"] = True

USE_TZ = True
LANGUAGE_CODE = "fr"
LANGUAGES = [("fr", "Français"), ("en", "English"), ("ar", "العربية")]
```

`backend/.env` (jamais versionné) :

```
SECRET_KEY=dev-only-not-a-real-secret
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://sigf_app:dev_only_change_me@localhost:5432/sigf
DATABASE_OWNER_URL=postgres://sigf_owner:dev_only_change_me@localhost:5432/sigf
```

```bash
printf '.env\n__pycache__/\n*.pyc\nnode_modules/\n.venv/\n' > ../.gitignore
```

**Contrôle A.6 :** `uv run python manage.py check` ne signale aucune erreur.

## A.7 Intégration continue

`.github/workflows/ci.yml` :

```yaml
name: CI
on: [push, pull_request]
jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: sigf
          POSTGRES_USER: sigf_owner
          POSTGRES_PASSWORD: ci
        options: >-
          --health-cmd pg_isready --health-interval 5s --health-retries 10
        ports: ["5432:5432"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
        working-directory: backend
      - run: uv run ruff check .
        working-directory: backend
      - run: uv run ruff format --check .
        working-directory: backend
      - run: uv run pytest --cov=. --cov-fail-under=80
        working-directory: backend
        env:
          SECRET_KEY: ci
          DATABASE_URL: postgres://sigf_owner:ci@localhost:5432/sigf
```

**Contrôle A.7 :** premier `git push` → le job passe au vert.

---

# PARTIE B — CONVENTIONS OBLIGATOIRES

> Ces huit règles ne sont pas négociables. Chacune correspond à une façon connue de produire des chiffres faux dans un logiciel comptable. En cas de doute, demandez : **ne contournez jamais.**

## B.1 L'argent

**Règle : aucun montant ne touche jamais un `float`.** Ni en base, ni en Python, ni en JSON, ni en JavaScript.

```python
# backend/core/fields.py
from django.db import models

class MontantField(models.DecimalField):
    """Montant monétaire. 20 chiffres, 4 décimales. Utiliser PARTOUT."""
    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 20)
        kwargs.setdefault("decimal_places", 4)
        super().__init__(**kwargs)

class TauxField(models.DecimalField):
    """Taux de change. Précision supérieure : une conversion ne doit pas perdre."""
    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 20)
        kwargs.setdefault("decimal_places", 10)
        super().__init__(**kwargs)
```

| À faire | À ne jamais faire |
|---|---|
| `MontantField()` | `models.FloatField()` sur un montant |
| `Decimal("12.50")` | `12.50` dans du code qui touche un montant |
| `montant.quantize(CENTIME, ROUND_HALF_UP)` | `round(montant, 2)` |
| Sérialiser en **chaîne** : `{"debit": "1250.0000"}` | `{"debit": 1250.0}` — JavaScript perdrait la précision |

Côté front, les montants arrivent en chaîne et sont manipulés avec une bibliothèque décimale, jamais avec `Number`.

**Garde-fou automatique** — ajoutez ce test dès maintenant :

```python
# backend/tests/test_conventions.py
import ast, pathlib

def test_aucun_float_sur_un_montant():
    """Interdit FloatField dans tout le backend."""
    fautes = []
    for f in pathlib.Path(".").rglob("*.py"):
        if ".venv" in str(f) or "/tests/" in str(f):
            continue
        arbre = ast.parse(f.read_text())
        for n in ast.walk(arbre):
            if isinstance(n, ast.Attribute) and n.attr == "FloatField":
                fautes.append(f"{f}:{n.lineno}")
    assert not fautes, f"FloatField interdit : {fautes}"
```

## B.2 Les libellés multilingues

**Règle : jamais de colonne par langue.**

```python
label = models.JSONField()   # {"fr": "Caisse", "en": "Cash", "ar": "الصندوق"}
```

Jamais `label_fr`, `label_en`. Ajouter une langue ne doit jamais demander de migration.

## B.3 Le périmètre d'organisation

**Règle : tout modèle métier hérite de `ModeleOrganisation`.**

```python
# backend/core/models.py
import uuid
from django.db import models

class ModeleBase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.UUIDField(null=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.UUIDField(null=True)
    class Meta:
        abstract = True

class ModeleOrganisation(ModeleBase):
    """Tout modèle métier hérite de celui-ci. Sans exception."""
    org_id = models.UUIDField(db_index=True)
    class Meta:
        abstract = True
```

**N'écrivez jamais `WHERE org_id = ...` à la main.** C'est la base qui s'en charge (B.4). Un filtre écrit à la main est un filtre qu'on peut oublier.

## B.4 L'isolation par la base

Pour chaque table portant `org_id`, une migration ajoute la politique de sécurité :

```python
# backend/core/migrations/_rls.py
def activer_rls(nom_table: str) -> str:
    return f"""
    ALTER TABLE {nom_table} ENABLE ROW LEVEL SECURITY;
    ALTER TABLE {nom_table} FORCE  ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS org_isolation ON {nom_table};
    CREATE POLICY org_isolation ON {nom_table}
      USING      (org_id = current_setting('app.org_id', true)::uuid)
      WITH CHECK (org_id = current_setting('app.org_id', true)::uuid);
    """
```

Et le middleware qui pose la variable, pour chaque requête :

```python
# backend/core/middleware.py
from django.db import connection

class OrganisationScopeMiddleware:
    """Pose app.org_id pour la transaction de la requête.

    ATOMIC_REQUESTS=True garantit qu'une transaction est ouverte :
    SET LOCAL ne survit pas au-delà, ce qui est exactement voulu.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        org_id = getattr(getattr(request, "user", None), "org_id", None)
        if org_id:
            with connection.cursor() as cur:
                cur.execute("SET LOCAL app.org_id = %s", [str(org_id)])
        return self.get_response(request)
```

> **Pourquoi `SET LOCAL` et pas `SET`.** Django réutilise les connexions. Un `SET` persisterait sur la connexion et la requête suivante, servie à **un autre utilisateur**, hériterait de l'organisation précédente. `SET LOCAL` meurt avec la transaction.

**Le test d'isolation**, à écrire dès le premier modèle et à ne jamais retirer :

```python
# backend/tests/test_isolation.py
import pytest, uuid
from django.db import connection

@pytest.mark.django_db
def test_une_organisation_ne_voit_pas_les_donnees_dune_autre(deux_organisations):
    org_a, org_b = deux_organisations
    with connection.cursor() as cur:
        cur.execute("SET LOCAL app.org_id = %s", [str(org_a.id)])
        cur.execute("SELECT count(*) FROM referentiels_compte WHERE org_id = %s",
                    [str(org_b.id)])
        assert cur.fetchone()[0] == 0, "FUITE DE DONNÉES ENTRE ORGANISATIONS"
```

## B.5 L'immuabilité

**Règle : une écriture comptabilisée ne se modifie jamais.** Aucune exception, aucun mode administrateur. Une correction est une **contre-passation** : une nouvelle écriture, de sens inverse, qui référence l'originale.

C'est imposé par un déclencheur de base de données (lot L3), pas par du code applicatif. Le code applicatif s'oublie.

## B.6 Le versionnement

Tout objet de configuration — plan, axe, clé de répartition, mapping, modèle d'état, exigence — porte `version`, `valid_from`, `valid_to`.

**On ne met jamais à jour un objet déjà utilisé : on crée une nouvelle version.** Sinon un état produit en 2026 cesse d'être reproductible en 2029.

**Convention de dates : intervalle semi-ouvert `[valid_from, valid_to[`.** `valid_from` est inclus, `valid_to` est exclu, et `valid_to` nul signifie « sans fin ». Une configuration valable du 1ᵉʳ janvier 2026 au 1ᵉʳ janvier 2027 couvre toute l'année 2026, et la version suivante commence le 1ᵉʳ janvier 2027 sans trou ni chevauchement d'un jour. Cette convention vaut pour **toute** table versionnée ; les dates contractuelles d'un accord (signature, clôture, date limite de décaissement) restent des dates calendaires inclusives, nommées comme telles.

**Pas de chevauchement, garanti par la base.** Pour toute configuration qui ne doit avoir qu'une version active à la fois, on pose une contrainte `EXCLUDE USING gist` (extension `btree_gist`) sur la clé fonctionnelle et `daterange(valid_from, valid_to, '[)')`. Le code applicatif s'oublie ; la base non.

**Une version non modifiable l'est par déclencheur.** Les tables enfants d'une configuration (règles, méthodes, comptes, taux) portent un `BEFORE UPDATE OR DELETE` qui refuse la modification dès que la version parente n'est plus en `draft` — y compris par un accès direct à la base.

## B.7 Le nommage

| Élément | Convention | Exemple |
|---|---|---|
| Modèle Django | français, singulier, `PascalCase` | `LigneEcriture` |
| Table | préfixe de l'application | `comptabilite_ligneecriture` |
| Champ | français, `snake_case` | `montant_devise` |
| Champ technique partagé | anglais si standard | `org_id`, `created_at` |
| Service | verbe à l'infinitif | `comptabiliser_ecriture()` |
| Test | `test_` + phrase lisible en français | `test_une_ecriture_desequilibree_est_refusee` |

Le domaine est francophone, la terminologie est celle des bailleurs. Un expert-comptable doit pouvoir lire un nom de modèle et le comprendre.

## B.8 Le travail en équipe

- **Une branche par tâche**, nommée `L3-T07-numerotation-sans-trou`.
- **Une revue obligatoire** avant fusion.
- **Message de commit** : `L3-T07: numérotation sans trou par compteur verrouillé`.
- **Intégration continue verte obligatoire** avant fusion. Jamais de contournement.

### Définition de « terminé »

Une tâche n'est terminée que si **les sept points** sont vrais :

```
[ ] 1. Le code fait ce que la tâche demande
[ ] 2. Un test automatisé le prouve, et il échouait avant
[ ] 3. L'intégration continue est verte (ruff + pytest + couverture ≥ 80 %)
[ ] 4. Aucun float sur un montant, aucun libellé mono-langue,
       aucun filtre org_id écrit à la main
[ ] 5. Les migrations s'appliquent sur une base vierge
[ ] 6. Le contrôle de vérification écrit dans la tâche a été exécuté
[ ] 7. Un collègue a relu et approuvé
```

---

# PARTIE C — LES DIX RÈGLES À NE JAMAIS ENFREINDRE

Affichez-les au mur de l'équipe.

| # | Règle | Ce qui arrive si on l'enfreint |
|---|---|---|
| 1 | **Aucun `float` sur un montant** | Des écarts au centime qui apparaissent six mois plus tard dans un état bailleur |
| 2 | **Aucune modification d'une écriture comptabilisée** | L'audit est perdu : plus rien n'est opposable |
| 3 | **Aucun trou dans la numérotation d'un journal** | L'auditeur présume une écriture supprimée |
| 4 | **Aucun filtre `org_id` écrit à la main** | Un oubli = fuite de données entre deux organisations |
| 5 | **Aucune `eval` sur une formule utilisateur** | Exécution de code arbitraire sur votre serveur |
| 6 | **Aucune écriture dans une période close** | L'état déjà transmis au bailleur devient faux rétroactivement |
| 7 | **Aucune mise à jour d'une configuration déjà utilisée** | Les rapports historiques cessent d'être reproductibles |
| 8 | **Aucune génération de rapport avec un mapping incomplet** | Une dépense disparaît silencieusement du rapport |
| 9 | **Aucune activation automatique d'une exigence** | Un rapport faux est produit, et il engage l'UGP |
| 10 | **Aucun `left`/`right` codé en dur dans le CSS** | L'arabe sera impossible à ajouter sans tout refaire |

---

**Étape suivante :** [plan de développement, lots L0 à L4](04_PLAN_LOTS_L0_A_L4.md).
