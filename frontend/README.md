# SIGF — frontend

React 19 + TypeScript strict, Vite, TanStack Router et Query, `decimal.js`, i18next.

## Commandes (depuis `frontend/`)

| But | Commande |
|---|---|
| Installer | `npm ci` |
| Développer (API Django sur le port 8000 proxifiée sous `/api`) | `npm run dev` |
| Types | `npm run typecheck` |
| Style | `npm run lint` |
| Tests | `npm test` |
| Construire | `npm run build` |

`?langue=pseudo` (développement seulement) active la pseudo-langue droite-à-gauche, qui allonge les textes et
inverse le sens d'écriture : elle sert à traquer ce qui casserait en arabe.

## Règles

1. **Un montant est une chaîne.** Jamais `Number`, jamais `parseFloat` (le lint l'interdit) : tout passe par
   `shared/money/montant.ts` (`decimal.js`). L'arrondi est celui du serveur (à la moitié, en s'éloignant de zéro).
2. **Aucun `left`/`right` en CSS** : propriétés logiques (`margin-inline-start`, `inset-inline-end`…). Un test le vérifie.
3. **Aucun libellé en dur** : tout passe par `t("domaine.cle")`, français et anglais à parité. Un test le vérifie.
4. **Les couleurs sont des jetons** (`shared/styles/tokens.css`) ; chaque paire texte/fond doit atteindre 4,5:1 (test).
   Neutres froids pour l'information, accents vifs pour l'action et les états. Thèmes clair et sombre.
5. **La couleur ne porte jamais seule le sens** : un message dit son type en toutes lettres.
6. **L'interface masque, elle ne protège pas** : chaque action est revérifiée au serveur.
7. Un composant n'est livré qu'avec ses tests d'accessibilité (axe) et vérifié dans un vrai navigateur.
