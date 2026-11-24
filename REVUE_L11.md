# Revue de code de L11 (Lot 1 du plan 07)

**État : premier passage, automatisé. La relecture module par module du §5.3 n'est PAS terminée.**
Ce qui a été contrôlé mécaniquement sur `niveau1_socle`, `niveau2_profils`, `niveau3_config`,
`niveau4_reporting` et `core` : filtres `org_id` écrits à la main, `float`, texte français en dur dans
un `raise`, longueur des actions du journal (≤ 32), tests d'API « creux », traitement des montants
(`NaN`/infini), vues d'API sans habilitation.

| N° | Fichier | Constat | Gravité | Correction | Test |
|---|---|---|---|---|---|
| 1 | `core/api.py` | Une `IntegrityError`/`DataError` qu'un service ne traduit pas sortait en **500** (règle du plan §5.2). | moyenne | Filet dans `gestionnaire_exceptions` : 422 `{code, message}`, nom de la contrainte seulement, pas de détail SQL ; retour arrière de la transaction. | `tests/test_gestionnaire_integrite.py` |
| 2 | `niveau1_socle/referentiels/api.py` (`ParametresOrganisation.get`, `HistoriqueOrganisation.get`, `TauxDeChange.get`) | Lectures au niveau de l'organisation sans `habilite(...)` : tout compte de l'organisation peut les lire. L'isolation entre organisations tient (RLS) ; c'est une question de droit de lecture interne. | à décider | **Non corrigé** : décision de produit (qui peut lire les taux et les réglages de devises ?). | — |
| 3 | `tests/test_api_evaluations_bd.py` (~l. 507) | L'assertion `Controle.count() == 1 or … == 0` est trop lâche : elle accepterait un contrôle installé à tort. | mineure | **Non corrigé** : à resserrer en comparant au nombre initial. | — |

## Vérifié, sans écart
* Aucun filtre `org_id` écrit à la main hors migrations et tests.
* Aucun `float` : les seuls `float` du code lèvent une erreur s'ils en reçoivent un.
* Les `raise` à texte en dur sont des erreurs de programmation (`TypeError`, `BibliothequeInvalide`), pas des messages d'utilisateur.
* Les actions du journal tiennent en 32 caractères.
* `core/metier.decimal` refuse `NaN`, l'infini et les `float`.

## Reste à faire (non lu)
Relecture des six modules du §5.3 : concurrence (`select_for_update`), « version, pas modification »
(`reallocation.py`, `profils_decaissement.py:191`, `activation.py:71`, `profils.py:168` font des `save()`
à examiner), habilitations de chaque vue, exactitude des notes « Réalisation ».
