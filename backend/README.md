# Backend SIGF — commandes

## Prérequis

La base tourne en conteneur :

```bash
docker compose -f ../infra/docker-compose.yml up -d
```

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

## Les deux rôles PostgreSQL

| Rôle | Usage | Jamais pour |
|---|---|---|
| `sigf_owner` | Migrations (`--settings=config.settings.migrate`) | Servir l'application |
| `sigf_app` | Toutes les requêtes de l'application | Exécuter des migrations |

L'application n'a aucun droit de création et subit les politiques d'isolation.
C'est ce qui rend le cloisonnement entre organisations réellement étanche.

## Poser le contexte d'organisation

Toute requête s'exécute dans le périmètre d'une organisation. Le middleware
`core.middleware.OrganisationScopeMiddleware` pose `app.org_id` pour la
transaction de chaque requête HTTP. En script ou en commande :

```python
with connection.cursor() as cur:
    cur.execute("SET app.org_id = %s", [str(org_id)])
```

Sans cela, **aucune ligne n'est visible ni insérable** — c'est le défaut sûr.
