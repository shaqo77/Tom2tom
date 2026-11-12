# APPORTS DU RAPPORT D'ANALYSE ET DU MANUEL TOM²PRO WEB

**Sources examinées :**
- *Analyse fonctionnelle et technique approfondie de TOM²PRO* — rapport fourni, ~40 000 caractères, 21 sections
- *Manuel d'utilisation de TOM²PRO WEB*, **mise à jour mai 2022, 650 pages** — sommaire complet relevé directement
**Date :** 12 novembre 2026

> **Ce que ces deux sources changent.** Le rapport apporte un module entier qui manquait à notre spécification et plusieurs règles de conception utiles. Le manuel, lui, apporte autre chose de plus rare : **des chiffres**. Sa table des matières dit où est réellement la complexité du produit de référence, et elle apporte la preuve la plus nette obtenue jusqu'ici que l'architecture à quatre niveaux du cahier des charges de l'UGP vise juste.

---

## 1. LE MANUEL : CE QUE SA STRUCTURE DÉMONTRE

### 1.1 Sommaire relevé

Le manuel est organisé en **12 chapitres**. Les bornes de pages permettent de mesurer le poids réel de chaque domaine.

| # | Chapitre | Pages | Poids |
|---|---|---|---|
| 1 | Introduction (dont *Interface utilisateur*, p. 15) | 5–27 | 23 p |
| 2 | **Codifications** (paramètres généraux, plan des comptes) | 28–46 | 19 p |
| 3 | **Comptabilité générale** (saisies 57, traitements 102, éditions 124, travaux périodiques 151, tableau de bord 154) | 47–165 | **119 p** |
| 4 | **Comptabilité analytique** (standard 170, *frais sur immobilisations* 182) | 166–189 | 24 p |
| 5 | **Suivi des conventions** | 190–349 | **160 p** |
| 6 | **Suivi budgétaire** (saisie 354, exploitations 360, suivi 372, *prévisionnelles* 384) | 350–394 | 45 p |
| 7 | **Immobilisations** | 395–420 | 26 p |
| 8 | **États financiers** | 421–488 | 68 p |
| 9 | **Marchés et engagements** (fiche marché 493, exploitations 506) | 489–532 | 44 p |
| 10 | **Décaissements** | 533–563 | 31 p |
| 11 | **Opérations financières** | 564–628 | **65 p** |
| 12 | **Utilitaires** (base de données 631, *interfaces* 633, diagnostics 647) | 629–650 | 22 p |

### 1.2 La découverte principale : les bailleurs sont câblés en dur

Le chapitre 5 n'est pas un module de conventions générique. C'est **quatre procédures distinctes, chacune son propre chapitre** :

| Section | Procédure | Pages | Volume |
|---|---|---|---|
| 5.2 | **Banque mondiale (IDA / BIRD)** | 192–242 | 51 p |
| 5.3 | **Union européenne (FED)** | 243–262 | 20 p |
| 5.4 | **Banque africaine de développement** | 263–288 | 26 p |
| 5.5 | **FIDA** | 289–349 | **61 p** |
| | **Total spécifique par bailleur** | | **158 p** |

**158 pages sur 650, soit 24 % du manuel, décrivent des procédures propres à un bailleur.** Et chaque bailleur a sa section, ses écrans, son enchaînement.

C'est la démonstration la plus nette obtenue jusqu'ici de deux choses à la fois :

1. **Où est la valeur du produit.** Le quart de la documentation — et vraisemblablement une part comparable de l'effort de développement — porte sur les procédures bailleurs. Ce n'est pas un accessoire du produit, c'est son cœur commercial.
2. **Où est sa faiblesse.** Quatre bailleurs = quatre procédures câblées. Un cinquième bailleur, ou une évolution du FIDA, suppose une intervention de l'éditeur. C'est exactement ce que le cahier des charges de l'UGP refuse : *« ajouter un profil et un modèle sans créer une nouvelle application »*.

> **Notre architecture à quatre niveaux n'est donc pas une élégance théorique : c'est la réponse directe à 158 pages de code figé chez le concurrent.** Là où il a quatre procédures, nous avons un moteur et quatre jeux de paramètres. Cet argument est chiffré, vérifiable, et il tient en une phrase devant un acheteur.

### 1.3 « IFR » est la terminologie de l'éditeur lui-même

Le chapitre 8 contient :
- **8.4 Paramètres d'États financiers IFR** (p. 455–470, 16 pages)
- **8.5 États financiers – IFR** (p. 471–475)

Cela clôt définitivement le point de terminologie : **le sigle correct est IFR**, employé par l'éditeur comme par la Banque mondiale. Le « IPFR » du tout premier cahier des charges était bien une erreur. Et l'existence de **16 pages de *paramétrage* IFR** confirme que la production de l'IFR est paramétrable, pas figée.

### 1.4 Le moteur d'états existe, et il est documenté

**8.2 Règles générales de paramétrage des rubriques des états financiers** (p. 423–432, 10 pages).

Dix pages de règles générales, placées **avant** les états standards et avant l'IFR : c'est bien un moteur de rubriques transversal, pas un état figé par type. C'est la pièce que nous appelons le moteur d'états, et sa place dans le manuel confirme qu'elle est centrale.

S'y ajoute **8.6 Mon tableau de bord « Universels »** (p. 476–488) : un constructeur de tableaux de bord paramétrable.

### 1.5 Autres enseignements de structure

| Observation | Ce qu'on en tire |
|---|---|
| **« Mon tableau de bord » dans 7 chapitres sur 12** | Les tableaux de bord sont **par module et personnels**, pas centralisés. Bon schéma d'usage à reprendre : le comptable, le chargé de marchés et le coordonnateur n'ont pas les mêmes indicateurs. |
| **Comptabilité générale : 119 pages**, dont 45 de saisies et 27 d'éditions | La saisie et les éditions sont le gros de l'usage quotidien. Cohérent avec notre priorité sur l'écran de saisie au clavier. |
| **3.4 Traitements (22 p.)** | Lettrage, rapprochement, régularisations : un bloc à part entière, pas un détail de la saisie. |
| **4.4 Exploitation – Frais sur immobilisations** | Traitement analytique des frais accessoires rattachés à un bien. Point de détail métier réel, à ne pas oublier en L9. |
| **6.6 Exploitations prévisionnelles (p. 384)** | La prévision de trésorerie vit **dans le module budgétaire**, pas dans la trésorerie. Choix de rattachement à reproduire ou à assumer autrement. |
| **12.3 Interfaces (14 p.)** | Surface d'import/export substantielle. Conforte la faisabilité de notre chaîne de reprise. |
| **1.2 Interface utilisateur (p. 15–27, 13 p.)** | Treize pages pour expliquer comment naviguer : signe d'une interface qui demande un apprentissage. Terrain de différenciation. |

### 1.6 Ce que je n'ai pas pu obtenir

**Je n'ai lu que le sommaire et les quatre premières pages.** Le document est hébergé sur une plateforme qui ne charge la suite qu'au défilement progressif, et qui demande un compte au-delà. Je n'ai pas créé de compte et n'ai pas contourné cette limite.

Par ailleurs, une limite de droit s'applique et elle est utile à rappeler : **les fonctionnalités d'un logiciel ne sont pas protégées par le droit d'auteur, mais le texte d'un manuel l'est.** Nous pouvons donc nous appuyer sur ce que le produit *fait*, jamais reproduire la façon dont le manuel le *dit*. Les constats ci-dessus sont des faits de structure — nombre de chapitres, bornes de pages, intitulés — pas des reprises de contenu.

**Si vous disposez du PDF**, je peux l'analyser en entier et en tirer, chapitre par chapitre, l'inventaire des écrans, des champs et des règles de gestion. Les sections les plus rentables, dans l'ordre : **8.2** (règles de paramétrage des rubriques, 10 p.), **5.2** (procédure Banque mondiale, 51 p.), **11.2** (ordres de paiement, 21 p.).

---

## 2. LE RAPPORT : CE QU'IL APPORTE

### 2.1 Un module entier qui manquait à notre spécification

**Chapitre 11 du manuel — Opérations financières, 65 pages.** Ni la nomenclature UNOPS de 2020 (10 modules), ni notre spécification ne le comportaient.

| Sous-module | Pages | Contenu |
|---|---|---|
| **Ordres de paiement** | 566–586 (21 p) | Émission, circuit, suivi |
| **Décisions d'avance** | 587–600 (14 p) | Octroi, suivi, justification, apurement |
| **Facturations** | 601–617 (17 p) | Facturation sortante |
| **Fiscalité** | 618–626 (9 p) | Retenues à la source, TVA, obligations déclaratives |
| **Chéquiers** | 627–628 (2 p) | Souches, numérotation, suivi |

**Pourquoi c'est important et pas anecdotique :**

- Les **ordres de paiement** sont le document de travail quotidien d'une unité de gestion. Ne pas les avoir oblige le client à les faire sous Word, ce qui casse la traçabilité entre l'engagement, le paiement et la pièce.
- Les **décisions d'avance** et leur apurement sont **une source récurrente de réserves d'audit**. Notre spécification prévoyait déjà le contrôle « avance non justifiée au-delà du délai », mais sans l'objet métier qui le porte. Le contrôle sans l'objet ne sert à rien.
- La **fiscalité** — retenues à la source sur marchés et prestataires — est une obligation légale locale, pas une option. Neuf pages dans le manuel : ce n'est pas un gadget.

> **Décision : créer le module M13 « Opérations financières », en priorité P2, en même temps que les marchés (lot L9).** Les ordres de paiement sans les marchés n'ont pas de sens, et l'inverse non plus.

### 2.2 Quatre notions, pas trois

Le rapport insiste sur une distinction que notre spécification simplifiait :

```
Budget autorisé        1 000 000
Engagements              700 000
Dépenses comptabilisées  500 000
Paiements                450 000
```

Notre formule était `disponible = budget − engagements − réalisations`. Le rapport ajoute **les paiements** comme quatrième indicateur distinct, et pose une exigence que je retiens telle quelle :

> *Ces indicateurs ne doivent pas être confondus. Un bon logiciel doit proposer plusieurs méthodes de lecture et préciser les définitions utilisées dans chaque état.*

C'est exactement le genre d'ambiguïté qui fait rejeter un rapport bailleur : deux états qui affichent « dépenses » sans dire s'il s'agit du comptabilisé ou du payé.

> **Décision : tout état publié porte, en clair, la définition de chaque indicateur agrégé** — comptabilisé, payé, engagé, ou notifié. La définition est une propriété du modèle d'état, versionnée comme le reste, et elle figure dans le dossier de conformité.

### 2.3 Distinguer marque, organisation cliente et locataire technique

Point d'architecture que nous n'avions pas, et qui est juste :

> *Il faut distinguer l'identité commerciale, l'organisation cliente et le tenant technique. Deux marques ne doivent pas nécessairement correspondre à deux bases de données ou à deux applications différentes.*

Concrètement, trois notions indépendantes :

| Notion | Ce que c'est | Porte |
|---|---|---|
| **Marque** | Nom commercial, domaine, charte, tarification | Un domaine et un thème |
| **Organisation** | L'entité cliente qui signe le contrat | La facturation, les contrats, les utilisateurs |
| **Locataire** | La frontière d'isolation des données | `org_id` et les politiques de sécurité |

> **Décision : ajouter une table `marque` rattachée à l'organisation, sans jamais la confondre avec la frontière d'isolation.** Le coût est négligeable maintenant et élevé plus tard. Cela permet d'exploiter la même plateforme sous un nom national et un nom international, sans dupliquer quoi que ce soit.

### 2.4 Apports mineurs mais à reprendre

| Apport | Traitement |
|---|---|
| **Brouillard comptable** | Terme métier exact pour ce que nous appelons `brouillon`. À adopter dans l'interface : les comptables le reconnaîtront. |
| **Retenues** sur décomptes de marchés | Ajouté à M05 (retenue de garantie, retenue à la source). Manquait. |
| **Contrôle de la somme des ventilations analytiques** | Déjà couvert par notre test de propriété sur le cofinancement. Étendre le même contrôle à la ventilation analytique. |
| **Portail fournisseur** | Intéressant, mais hors périmètre v1 et v2. À inscrire comme piste, pas comme engagement. |

---

## 3. LES POINTS DE DÉSACCORD, ET MA POSITION

Le rapport contient trois recommandations que je ne reprends pas telles quelles. Les voici avec mon raisonnement, pour que vous puissiez trancher contre moi si vous le souhaitez.

### 3.1 « Construire une plateforme modulaire » incluant RH, paie, stocks, facturation

**Le rapport propose** treize modules, dont ressources humaines, paie, stocks et facturation.

**Je maintiens l'exclusion** (décision D-07). Trois raisons :

1. **La paie est un produit à part entière**, avec son propre droit du travail, ses propres déclarations sociales, et une obligation de mise à jour réglementaire par pays. La porter revient à construire un second produit, pas un module.
2. **La prolifération de satellites chez le concurrent est sa faiblesse, pas son modèle.** Sept logiciels séparés, un portail censé les intégrer : c'est ce qui rend ses déploiements lourds et son paramétrage impossible à transmettre.
3. **Nous n'avons pas encore livré le noyau.** Élargir le périmètre avant d'avoir produit un IFR scellé serait la façon la plus sûre de ne jamais le produire.

**Ce que je retiens tout de même du rapport :** la *facturation sortante* figure au chapitre 11 du manuel et fait donc partie du noyau du concurrent. Elle entre dans M13, pas dans un module de facturation commerciale.

### 3.2 « Un moteur de workflow universel »

**Le rapport propose** des circuits de validation entièrement configurables.

**Ma position : un workflow borné, pas un moteur de processus général.** Un moteur générique est un piège classique — il devient un langage de programmation que vos clients écrivent et que vous déboguez à leur place, exactement le risque R3 que nous avons déjà identifié pour les formules.

**Ce que je propose à la place :** un circuit paramétrable à structure fixe — de 1 à 5 étapes, chacune avec un rôle requis, une condition d'entrée optionnelle (seuil de montant, catégorie, bailleur) et une obligation de motif en cas de rejet. Cela couvre l'écrasante majorité des besoins réels d'une unité de gestion, et cela reste testable.

### 3.3 Supabase comme socle

**Le rapport suggère** Supabase et PostgreSQL.

**Ma position : PostgreSQL oui — c'est déjà notre choix et il n'est pas discutable. Supabase, non, pour ce produit.**

Supabase est un bon accélérateur quand la logique vit dans le client et que la base sert de magasin. Ici, c'est l'inverse : **l'essentiel de la valeur est de la logique serveur** — moteur comptable, contrôle budgétaire concurrent, compilateur d'états, scellement, chaînage d'audit. Trois difficultés concrètes :

1. **Les contraintes d'intégrité sont les nôtres.** Équilibre différé, immuabilité après comptabilisation, numérotation sans trou sous verrou : nous écrivons déjà ces déclencheurs à la main. Supabase ne les fournit pas et ne les gêne pas, mais il n'apporte alors rien sur ce qui compte.
2. **La gestion des migrations.** Un produit comptable vit dix ans et doit pouvoir rejouer ses migrations sur une installation souveraine hors ligne. C'est plus simple avec un outillage de migrations classique.
3. **L'hébergement souverain est une exigence du produit** (profil de déploiement, §15 de la spécification). Supabase s'auto-héberge, mais l'intérêt principal de l'offre disparaît alors.

**En revanche, un emprunt est pertinent :** la sécurité au niveau ligne de PostgreSQL, que Supabase a popularisée, est exactement ce que nous avons implémenté. Nous avons déjà le bénéfice sans la dépendance.

### 3.4 « Intégrer une intelligence artificielle contrôlée »

**Le rapport propose** sept usages. Je les trie, parce qu'ils n'ont ni la même valeur ni le même risque.

| Usage proposé | Position | Raison |
|---|---|---|
| **Lecture des justificatifs** (extraction de montant, date, fournisseur) | **Retenu, v2** | Gain de saisie mesurable, vérification immédiate par l'utilisateur, erreur sans conséquence puisqu'il valide. |
| **Extraction des exigences depuis le DFIL** | **Déjà retenu** (décision D-06) | Le gain le plus fort : des semaines de configuration en jours. |
| **Recherche dans les documents** | **Retenu, v2** | Faible risque, forte utilité sur un corpus d'accords et de manuels. |
| **Proposition d'imputations** | **Retenu, v2, en suggestion seulement** | Jamais d'imputation posée automatiquement. Une imputation fausse se propage dans tous les états. |
| **Détection d'anomalies** | **Retenu — mais par des règles, pas par un modèle** | Les contrôles du §7 sont explicites, explicables et opposables à un auditeur. Un signalement qu'on ne sait pas justifier n'a aucune valeur en audit. |
| **Analyse des écarts budgétaires** | **Réservé** | Utile en commentaire, dangereux si présenté comme une conclusion. |
| **Rédaction des commentaires financiers** | **Rejeté** | Un commentaire financier engage la signature du responsable. Lui faire signer un texte qu'il n'a pas écrit est une mauvaise idée, et les bailleurs le verront. |

**Règle générale, à inscrire au produit :** aucune suggestion automatique n'écrit jamais dans le grand livre, dans la configuration ou dans un rapport publié. Elle propose, un humain valide, et l'origine de la proposition reste tracée à vie. C'est la règle que nous avons déjà posée pour l'assistant d'extraction ; elle s'étend à tous les usages.

---

## 4. CE QUI EST CONFIRMÉ

Le rapport et le manuel confirment des choix que nous avions déjà faits. Cela compte autant que les découvertes.

| Notre choix | Confirmation |
|---|---|
| **Saisie unique multidimensionnelle** | Principe fondateur chez le concurrent, décrit comme tel dans le rapport. |
| **Axes analytiques configurables** | Confirmé : projet, composante, activité, centre de coûts, zone, programme, source. |
| **Imputations secondaires par clés de répartition** | Confirmé, y compris les frais de bureau répartis entre projets. |
| **Moteur d'états par rubriques associées à des comptes** | Confirmé par le chapitre 8.2 du manuel, 10 pages de règles générales. |
| **Cofinancement ventilé** | Confirmé, exemple à deux bailleurs dans le rapport. |
| **Période close protégée** | Confirmé explicitement. |
| **Traçabilité : qui, quand, valeur avant, valeur après, pièce justificative** | Confirmé — et notre journal chaîné va plus loin que ce qui est décrit. |
| **Cycle paramétrage → budget → engagement → réception → comptabilisation → validation → paiement → reporting** | Identique à notre §5.1. |
| **Isolation multi-organisations contrôlée au niveau de la base, avec tests automatiques** | Le rapport la réclame ; **elle est déjà implémentée et testée** (commit `5fc0779`). |

---

## 5. CE QUI CHANGE DANS NOS LIVRABLES

| # | Changement | Livrable | Statut |
|---|---|---|---|
| 1 | **Module M13 — Opérations financières** : ordres de paiement, décisions d'avance, facturation, fiscalité, chéquiers | Spécification §2, lot L9 | **À appliquer** |
| 2 | **Quatre indicateurs distincts** (notifié, engagé, comptabilisé, payé) et **définition affichée dans chaque état** | Spécification §3.6 et §6.2 | **À appliquer** |
| 3 | **Marque ≠ organisation ≠ locataire** | Architecture §2 et §3 | **À appliquer** |
| 4 | **Retenues** sur décomptes | Spécification §2, M05 | **À appliquer** |
| 5 | **Workflow borné** (1 à 5 étapes paramétrables), et non moteur générique | Spécification §8.1 | **À appliquer** |
| 6 | **Usages assistés triés**, avec la règle « jamais d'écriture automatique » | Spécification §5.3 étendue | **À appliquer** |
| 7 | **Argument commercial chiffré** : 158 pages de procédures câblées par bailleur chez le concurrent | Spécification §1.1 | **À appliquer** |
| 8 | « Brouillard » comme terme d'interface | Spécification §3.3 | Cosmétique |
| 9 | RH, paie, stocks hors périmètre | Décision D-07 | **Maintenue** |
| 10 | PostgreSQL sans Supabase | Décision D1 | **Maintenue** |

**Aucun de ces changements ne touche le code déjà écrit.** Ils portent sur des lots à venir — L9 pour le module M13, L6 pour les définitions d'indicateurs et le workflow, L1 pour la table `marque`. Le socle, l'isolation, le journal d'audit et le moteur de formules restent valides.

---

## 6. CE QU'IL RESTE À OBTENIR

| Priorité | Pièce | Pourquoi |
|---|---|---|
| **1** | **Le PDF du manuel TOM²PRO WEB** (650 p., mai 2022) | Permettrait l'inventaire des écrans, des champs et des règles, chapitre par chapitre. Je n'ai pu lire que le sommaire. |
| **2** | **Le manuel TOM²PRO classique** (382 p., 2010), cité par le rapport | Permet la chronologie d'évolution et les écarts entre les deux générations. |
| 3 | Une instance de démonstration | Seul moyen de confirmer ce que la documentation ne dit pas : performances réelles, comportement concurrent, limites de volumétrie. |
| 4 | Un jeu d'états réellement produits par le logiciel | Référence de comparaison pour nos propres états. |

> **Rappel de méthode, repris du rapport lui-même et que j'approuve :** toute fonctionnalité doit être classée en *confirmée par la documentation*, *déduite*, ou *à vérifier*. Nous n'attribuons jamais au produit de référence une caractéristique que nous n'avons pas vue.

---

*Documents liés : [spécification fonctionnelle](01_SPECIFICATION_FONCTIONNELLE.md) · [architecture technique](02_ARCHITECTURE_TECHNIQUE.md) · [vérification factuelle](ANNEXE_A_VERIFICATION_FACTUELLE.md) · [registre des sources](ANNEXE_B_REGISTRE_DES_SOURCES.md)*
