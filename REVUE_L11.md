# Revue de code de L11 (Lot 1 du plan 07)

**État : deuxième passage. Relu : les `save()` de configuration, les numérotations, les habilitations des API. La relecture ligne à ligne de tous les modules du §5.3 n'est PAS terminée.**
Ce qui a été contrôlé mécaniquement sur `niveau1_socle`, `niveau2_profils`, `niveau3_config`,
`niveau4_reporting` et `core` : filtres `org_id` écrits à la main, `float`, texte français en dur dans
un `raise`, longueur des actions du journal (≤ 32), tests d'API « creux », traitement des montants
(`NaN`/infini), vues d'API sans habilitation.

| N° | Fichier | Constat | Gravité | Correction | Test |
|---|---|---|---|---|---|
| 1 | `core/api.py` | Une `IntegrityError`/`DataError` qu'un service ne traduit pas sortait en **500** (règle du plan §5.2). | moyenne | Filet dans `gestionnaire_exceptions` : 422 `{code, message}`, nom de la contrainte seulement, pas de détail SQL ; retour arrière de la transaction. | `tests/test_gestionnaire_integrite.py` |
| 2 | `niveau1_socle/referentiels/api.py` (`ParametresOrganisation.get`, `HistoriqueOrganisation.get`, `TauxDeChange.get`) | Lectures au niveau de l'organisation sans `habilite(...)` : tout compte de l'organisation peut les lire. L'isolation entre organisations tient (RLS) ; c'est une question de droit de lecture interne. | à décider | **Non corrigé** : décision de produit (qui peut lire les taux et les réglages de devises ?). | — |
| 3 | `tests/test_api_evaluations_bd.py` (~l. 507) | L'assertion `Controle.count() == 1 or … == 0` est trop lâche : elle accepterait un contrôle installé à tort. | mineure | **Non corrigé** : à resserrer en comparant au nombre initial. | — |
| 4 | `niveau1_socle/decaissements/services.py` (`preparer_demande`) | Le numéro `DRF-<accord>-<n>` venait de `count() + 1` lu sans verrou : deux préparations simultanées sur un accord prenaient le même numéro, l'une échouait sur `uq_demande_numero` (500 avant le constat 1). | importante | Verrou consultatif par accord (`pg_advisory_xact_lock`) avant le décompte, comme le rapprochement. | `tests/test_numerotation_demandes_bd.py` |
| 5 | `niveau3_config/services/versions.py` (`nouvelle_version`) | Numéro de version = `max + 1` sans verrou local. La contrainte `uq_profil_version` empêche tout doublon ; une course donne désormais un 422 (constat 1), pas un doublon. | mineure | **Non corrigé** : protégé par la contrainte. | — |
| 6 | `niveau1_socle/financements/api.py` (`Bailleurs.get`) | Même remarque que le constat 2 : liste des bailleurs lisible par tout compte de l'organisation. | à décider | **Non corrigé** (décision de produit). | — |

## Vérifié, sans écart
* Aucun filtre `org_id` écrit à la main hors migrations et tests.
* Aucun `float` : les seuls `float` du code lèvent une erreur s'ils en reçoivent un.
* Les `raise` à texte en dur sont des erreurs de programmation (`TypeError`, `BibliothequeInvalide`), pas des messages d'utilisateur.
* Les actions du journal tiennent en 32 caractères.
* Les `save()` de `activation.py`, `reallocation.py`, `profils_decaissement.py` (brouillon seulement) et `profils.py` sont sous `select_for_update` ou sur un brouillon verrouillé : pas de modification sur place d'une configuration active.
* Autres numérotations (`rapprochement`, `plan`, `revue`, `controles`) : verrou présent.
* `core/metier.decimal` refuse `NaN`, l'infini et les `float`.

## Reste à faire (non lu)
Relecture ligne à ligne des modules `niveau4_reporting/controles/`, `niveau4_reporting/tableau_de_bord/`
et `niveau2_profils/`; exactitude des notes « Réalisation » (non vérifiée une par une).
