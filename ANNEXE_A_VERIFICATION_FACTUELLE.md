# ANNEXE A — RAPPORT DE VÉRIFICATION FACTUELLE DU CAHIER DES CHARGES v1.0

**Objet :** audit d'exactitude, affirmation par affirmation, du document *« Cahier des charges — rétro-ingénierie fonctionnelle et technique du logiciel TOM²Pro », version 1.0*.
**Date de l'audit :** 12 novembre 2026
**Méthode :** recherche en sources ouvertes, lecture directe des sources primaires (site éditeur, avis de marchés UNGM/Banque mondiale/BAD, rapports d'audit publiés par la Banque mondiale, propositions techniques d'intégrateurs, textes OHADA/OAPI/UE).
**Échelle de verdict :** `CONFIRMÉ` · `CONFIRMÉ AVEC RÉSERVE` · `À NUANCER` · `NON VÉRIFIÉ` · `ERRONÉ`

> **Lecture rapide — ce qui change réellement le projet**
>
> 1. **Le SGBD n'est plus une inconnue.** TOM²PRO fonctionne « en client/serveur sous SQL Serveur en environnement Windows » (source primaire 2013). La phase 3 doit partir de cette hypothèse forte, pas de zéro. → *gain : ~15 JH, et ouverture d'une voie d'extraction directe.*
> 2. **La liste des 10 modules est établie par source primaire** (clarification UNOPS, mai 2020) et recoupée par une proposition d'intégrateur de 2013. Le périmètre M01–M10 de la v1.0 est exact *en contenu* mais doit adopter la nomenclature de l'éditeur.
> 3. **Le fondement juridique de la v1.0 est incomplet et mal rattaché.** Il manque l'arrêt CJUE *SAS Institute c/ World Programming* qui, à lui seul, dé-risque 90 % du projet ; et l'OHADA est invoqué à tort en matière de propriété intellectuelle et de données personnelles (c'est l'OAPI et la Convention de Malabo).
> 4. **L'audit PAZH est daté de 2 ans d'erreur** (exercice 2020, rapport de février 2022, pas « exercice 2018 ») — mais son contenu est confirmé *mot pour mot*, et il livre un fait plus fort que celui allégué : les états financiers annuels sont **reconstruits à la main sous Excel**.
> 5. **Le repère de prix de la v1.0 (84 M MGA) n'est pas sourçable.** Cinq points de prix publics et vérifiables le remplacent, et révèlent un modèle de licence par **clés utilisateur** que la v1.0 ignorait.
> 6. **Deux produits de la gamme sont mal nommés** : `Tom²Conso` n'existe pas dans la gamme publiée ; `TOM²GRH` existe et manque au périmètre.

---

## A.1 — Identité du produit et de l'éditeur (§1.1 de la v1.0)

| # | Affirmation v1.0 | Verdict | Constat vérifié |
|---|------------------|---------|-----------------|
| 1 | TOM²Pro est un SIGF édité par la société TOMATE | **CONFIRMÉ** | L'éditeur publie la gamme sous la marque TOMATE. Mention portée au bilan d'un projet audité : « Logiciel de gestion intégré TOMPRO nécessaire au suivi comptable des activités du Projet ». |
| 2 | Raison sociale et siège de l'éditeur | **NON VÉRIFIÉ** | Le site ne publie **ni forme juridique, ni siège social, ni année de création**. Il revendique « plus de 25 années d'expérience », sans date. Une source tierce mentionne une « S.A.S TOMATE ». → *À établir formellement en P0 : c'est la contrepartie juridique du projet.* |
| 3 | Déploiement massif en Afrique francophone | **CONFIRMÉ AVEC RÉSERVE** | Le déploiement réel est largement attesté par des documents de bailleurs (Gabon, Congo, Tchad, Mali, Madagascar, Guinée, Haïti, Burkina Faso, RDC, Niger, Sénégal). En revanche les volumes — « plus de 2 000 installations », « plus de 40 pays », « plus de 50 partenaires agréés » — sont **auto-déclarés par l'éditeur** et n'ont aucune confirmation indépendante. Ne pas les citer comme des faits. |
| 4 | Liste des bailleurs : BM, BAD, UE, FIDA, Fonds mondial, BID, GAFSP, SNU, Expertise France | **À NUANCER** | L'éditeur revendique : « Banque Mondiale, Union Européenne, Banque Africaine de Développement, Système des Nations-Unies : FIDA, Global Funds, BID ». Il cite aussi le PNUD. **GAFSP, AFD et Expertise France ne sont revendiqués nulle part** et n'ont pas été retrouvés. Retirer ou marquer `[HYP]`. |
| 5 | Couvre codification → budget → engagement → comptabilisation → reporting | **CONFIRMÉ** | Recoupé par deux sources primaires indépendantes (voir §A.3). |
| 6 | Distribué via intégrateurs certifiés ; ex. AGOSOFT (CI), EasyTech Africa (Gabon), SOFTWELL (Madagascar) | **CONFIRMÉ AVEC RÉSERVE** | Le modèle est confirmé : « Nos logiciels sont uniquement disponibles à travers un réseau de distributeurs », avec une certification **« TechExpert » attribuée et renouvelée annuellement**. AGOSOFT (Côte d'Ivoire, activité depuis 1999) et SOFTWELL (Madagascar) sont confirmés ; **EasyTech Africa (Gabon) n'a pas été retrouvé**. Partenaires confirmés supplémentaires à ajouter au corpus : 2DBC (Sénégal, depuis 2004), ACECA International (Burkina Faso), AE2C (Mali), ACW (Tunisie), AZ Consulting (Sénégal), CE.S.I (Niger), CIFOPE Afrique (Mali), MICROSYS (Burkina Faso), DISS (France — intégrateur sur zone Haïti). |
| 7 | Deux générations : client lourd (Windows/macOS) et TOM²Pro WEB | **À NUANCER — important** | **(a) macOS :** il n'existe pas de version macOS native. Le site précise « Sous Parallels Desktop / Boot Camp / Windows », c'est-à-dire du Windows émulé. Le périmètre « desktop » est donc **mono-plateforme Windows**. **(b) Version WEB :** son existence est confirmée par trois sources indépendantes de 2024-2025 (appel d'offres Caritas Africa du 2 juillet 2025 portant explicitement sur « les versions web des produits logiciels TOMATE » ; formation PADS Burkina Faso de décembre 2024 sur « la version web du logiciel TOM2PRO » ; marché Banque mondiale à Madagascar de « migration du logiciel TOM2PRO en version web »). **(c) Fait notable :** le site de l'éditeur **ne mentionne la version WEB nulle part**, et affiche encore des prérequis « Windows 10, 8, 7, Vista, XP ». Le canal commercial réel (intégrateurs, appels d'offres) est donc en avance sur la documentation publique de l'éditeur. → *Conséquence pour le projet : la documentation publique ne suffira pas pour la version WEB ; l'accès doit être négocié avec un intégrateur dès P0.* |

---

## A.2 — Problèmes constatés motivant la rétro-ingénierie (§1.2 de la v1.0)

### A.2.1 Verrouillage fournisseur — `CONFIRMÉ, mais la formulation est trop absolue`

L'affirmation « les acquisitions se font quasi systématiquement par entente directe » est **étayée par des marchés nommément identifiables** :

| Marché | Procédure | Montant publié |
|--------|-----------|----------------|
| Congo — projet PATN (Banque mondiale), réf. `CG-PATN-0018-F-ED-2023` : acquisition TOM2PRO, installation, paramétrage, formation, assistance, maintenance | **Entente directe avec la société TOMATE** | 20 308 193 FCFA |
| Congo — fourniture, installation TOMPRO et mise en réseau | **Entente directe avec la société TOMATE** | 10 745 447 FCFA |
| Tchad — UGP PDMFI/FJ (BAD) : acquisition TOM2Pro, mise en place, formation | **Entente directe** | non publié |
| Madagascar — migration TOM2PRO en version web (Banque mondiale) | **Direct Selection** (attribué à SOFTWELL CONSULTING) | 27 556 USD |

**Mais deux contre-exemples imposent de nuancer** : la maintenance TOM2Pro fait l'objet de mises en concurrence ouvertes (Tchad, Mali), et l'avis UNOPS pour la Guinée était une demande de cotation en lots. **Le verrou porte sur l'acquisition initiale et le paramétrage, pas sur la maintenance.** C'est une nuance opérationnellement décisive : elle indique où le marché est contestable et où il ne l'est pas.

> **Reformulation proposée pour la v2.0 :** *« L'acquisition initiale et le paramétrage sont fréquemment passés par entente directe avec l'éditeur ou par sélection directe d'un intégrateur agréé, procédure documentée dans plusieurs marchés financés par la Banque mondiale et la BAD. La maintenance, elle, est parfois mise en concurrence, mais les cahiers des charges exigent une expérience préalable sur les logiciels TOMATE, ce qui restreint de fait la concurrence au réseau agréé. »*

### A.2.2 « Formats de sortie propriétaires empêchant la portabilité » — `À NUANCER — l'argument est mal posé`

C'est **le point le plus discutable de la v1.0**, et il affaiblit le dossier parce qu'il est réfutable en une phrase par l'éditeur.

Les sources primaires établissent exactement l'inverse sur les exports :
- Module `Utilitaires` (description UNOPS) : « Maintenance de la base de données, **importations et exportations des données**, sauvegarde et restitution des bases de données ».
- Module `Suivi budgétaire` (proposition DISS 2013) : « **Tous les rapports peuvent être exportés vers MS-Excel.** »
- Les migrations de données *entrantes* se font par fichiers Excel pré-formatés (importation des exercices 2008-2013 d'un projet haïtien).

**Le verrouillage réel est ailleurs**, et il est plus solide à démontrer :
1. **Le paramétrage**, qui porte toute la valeur métier (plans de gestion, rubriques d'états, formules bailleurs) et n'est pas réputé exportable.
2. **La base de données**, dont le schéma n'est pas documenté publiquement.
3. **Le modèle de licence par clés utilisateur** (voir §A.6), qui lie le coût à la croissance de l'organisation.
4. **La compétence**, concentrée dans un réseau d'intégrateurs certifiés annuellement par l'éditeur.

> **Action v2.0 :** remplacer l'argument « formats propriétaires » par « non-portabilité du paramétrage et du schéma de données », et faire de la **démonstration de la complétude (ou de l'incomplétude) des exports** un objectif de test explicite de la phase 2, et non un présupposé.

### A.2.3 L'audit PAZH Gabon — `ERRONÉ sur la date, CONFIRMÉ et renforcé sur le fond`

| Élément | v1.0 | Réalité vérifiée |
|---------|------|------------------|
| Cabinet | « Grant Thornton » | **Delta Grant Thornton**, membre de Grant Thornton International Ltd, société d'expertise comptable agréée CEMAC n° SEC 61, Libreville. Signataire : Adrien Degbey, expert-comptable agréé CEMAC n° EC 312. |
| Exercice | « exercice 2018 » | **Exercice clos le 31 décembre 2020.** Rapport daté du **22 février 2022**. Audit de clôture (achèvement du projet fixé au 30 avril 2020). |
| Projet | « PAZH Gabon » | Projet d'appui à la gestion durable des zones humides critiques du Gabon, **don TF 016689-GA**, Banque mondiale / FEM. |
| Opinion | non précisée | **Opinion non modifiée (sans réserve)**, assortie de paragraphes d'observations. |

**Le constat de fond est confirmé mot pour mot** — et il est même plus sévère que ce qu'en disait la v1.0 :

> « L'UCP utilise un progiciel qui, de fait de problèmes de paramétrage, **ne permet pas la préparation de l'état des emplois et ressources** […] **et le suivi budgétaire de manière automatique.** »

> Note 1.8, *Paramétrage du logiciel d'exploitation Tom2Pro* : « les états financiers annuels du Projet sont **élaborés manuellement en fichier Excel**, après retraitement des balances et d'autres états extraits du logiciel TOM2 PRO. »

**Trois nuances que la v1.0 omet et qui doivent figurer en v2.0 :**

1. **L'audit impute la défaillance à la version acquise, pas au produit.** Note 1.8 : « **la version de TOM2 PRO acquise par le Projet** ne produit pas automatiquement les états financiers classiques du genre (Bilan, compte de résultat et les autres états annexes) ». C'est donc un problème de **périmètre de licence et de paramétrage**, pas un défaut intrinsèque démontré. Présenter l'inverse exposerait la maîtrise d'ouvrage à une contestation légitime de l'éditeur.
2. **Le rapport se contredit** : la note 1.8 affirme que le logiciel produit bien « le Tableau emplois, le tableau d'utilisation des fonds, le tableau du suivi budgétaire », tandis que les points de contrôle interne disent qu'il ne permet pas de préparer l'état des emplois et ressources automatiquement. **Cette contradiction est elle-même une donnée** : elle suggère que la capacité existe mais n'était pas activée/paramétrée. C'est exactement ce que la phase 2 doit trancher par le test.
3. **Les recommandations détaillées sur le logiciel ne sont pas dans le rapport public** : elles figurent dans une « lettre de contrôle interne adressée au Coordonnateur de l'UCP », non publiée. → *Pièce à demander en P1.*

**Fait connexe à fort intérêt :** le même rapport établit que la comptabilité du projet est **une comptabilité de trésorerie** « tenue selon les règles du plan comptable OHADA […] adaptées aux projets et programmes de développement, avec, à titre occasionnel, des opérations d'engagement ». Le module `Comptabilité générale` de l'éditeur confirme ce choix : « sur la base d'une comptabilité d'engagement **ou** d'une comptabilité de trésorerie ». **La bascule trésorerie/engagement est donc une option de paramétrage structurante** — elle n'apparaît pas dans la v1.0 et doit devenir une règle de gestion prioritaire à reconstituer.

### A.2.4 Obsolescence et trajectoire technique — `OPINION à requalifier en faits`

« Obsolescence perçue » n'est pas opposable. Deux faits vérifiés la remplacent avantageusement :
- Le site de l'éditeur affiche en 2026 des prérequis incluant **Windows XP, Vista, 7 et 8** — tous en fin de support.
- Des marchés publics de **« migration du logiciel TOM2PRO en version web »** sont passés par des unités de gestion de projets, ce qui atteste une trajectoire de migration engagée côté clients.

« Incertitude sur la base de données » est **en partie levée** : voir §A.4.

---

## A.3 — Périmètre fonctionnel (§4.1 de la v1.0) — `CONFIRMÉ, à renommer`

Le découpage M01–M10 de la v1.0 est **exact en contenu**. Il doit toutefois adopter la nomenclature de l'éditeur, désormais établie par **deux sources primaires indépendantes et concordantes à sept ans d'écart** :

| # | Nomenclature éditeur (clarification UNOPS, 19 mai 2020) | Nomenclature intégrateur (proposition DISS, sept. 2013) | Correspondance v1.0 |
|---|---|---|---|
| 1 | **Codifications** — « définitions des paramètres généraux, des plans de gestion (comptable, budgétaire, analytique, géographique et autres…) » | **Paramètres** — « identification et saisie des cinq plans utilisés par le projet (plan financier, plan analytique, plan budgétaire, plan géographique et le plan comptable) » | M01 |
| 2 | **Comptabilité générale** — « comptabilité d'engagement **ou** de trésorerie ; édition des états comptables (compte, balance, grand-livre) ; traitement comptable (rapprochement bancaire, lettrage) » | **Comptabilité générale et auxiliaire** — « interface principale de saisie des données **qui alimente tous les autres modules** » | M02 |
| 3 | **Comptabilité analytique** — « suivi des réalisations suivant le découpage analytique du projet et/ou du cadre logique » | **Comptabilité analytique** — « édition des états analytiques basés sur les cinq plans » | M03 |
| 4 | **Budget et suivi budgétaire** — « programmation (saisie) et suivi du budget » | **Suivi budgétaire** — « le budget peut être configuré à partir d'une combinaison des cinq plans. Les rapports budgétaires tiennent compte des engagements. Tous les rapports peuvent être exportés vers MS-Excel. » | M04 |
| 5 | **Suivi des conventions de financement** — « production des mémoires de justification des dépenses ou de réapprovisionnement du compte spécial et définition des tableaux de suivi du financement » | **Suivi des conventions de financement** — « élabore les états de demande de retrait de fonds, demande de paiement direct **au format des différents bailleurs**. Il donne la situation des accords de crédit et de dons. » | M06 |
| 6 | **États financiers** — « paramétrage des états financiers standards (bilan, compte de résultat, tableau Emplois Ressources) ; paramétrage et édition des **états RSF (rapports de suivi financier) suivant le format bailleur (TER et tableau d'utilisation des fonds par activités)** et production de tableaux de bord » | **États financiers** — « production des états financiers standards et des **états de suivi financier du FIDA** » | M08 |
| 7 | **Gestion des immobilisations** — « suivi des actifs, production des tableaux d'inventaire, des tableaux d'amortissements » | **Gestion des immobilisations** — « identification et suivi des immobilisations par localisation » | M09 |
| 8 | **Gestion des décaissements** — « suivi budgétaire basé sur les décaissements et production des états de reporting » | **États de décaissements** — « comparaison entre le budget et le montant décaissé » | M07 |
| 9 | **Marchés et engagements** — « suivi financier des contrats et engagements : saisie des contrats et bons de commande, production des états de synthèse et des fiches de marchés, apurement des engagements » | **Marchés et engagements** — « gestion des contrats intégrée à la comptabilité générale afin de donner la situation des engagements (montants facturés, payés et soldes) » | M05 |
| 10 | **Utilitaires** — « maintenance de la base de données, importations et exportations des données, sauvegarde et restitution des bases de données, mise à jour du système » | **Utilitaires** — « contrôle des outils de sauvegarde de la base de données et de la gestion des droits d'accès des utilisateurs » | M10 |

**Écarts à corriger dans la v1.0 :**

| Point | Verdict | Correction |
|---|---|---|
| « Jusqu'à 4 plans de gestion et 4 plans auxiliaires » | **CONFIRMÉ** | Formulation exacte de l'éditeur. Cohérent avec les « cinq plans » de 2013 = plan comptable + 4 axes de gestion. |
| Module `M09 Immobilisations` traité comme module de plein exercice | **CONFIRMÉ** | Confirmé comme module autonome par les deux sources primaires. *(Le site commercial le présente seulement comme une option de saisie — c'est le site qui est réducteur, pas la v1.0.)* |
| `Tom²Conso` (M12) | **ERRONÉ / NON VÉRIFIÉ** | N'apparaît dans **aucune** source. La gamme publiée comprend 7 logiciels : Tom²Pro, Tom²Paie, Tom²EtatsFin, Tom²Monitoring, Tom²Projet, Tom²Marché, Tom²Stock — regroupés dans la suite **Tom²Portail**. La consolidation multi-sites est une **fonction**, pas un produit. → Supprimer. |
| `TOM²GRH` | **MANQUANT** | Produit confirmé par l'appel d'offres Caritas Africa du 2 juillet 2025, distinct de TOM²PAIE. → Ajouter au périmètre M12. |
| `Tom²EtatsFin` | **CONFIRMÉ** | Nom exact de l'éditeur : « Tom²EtatsFin — Production des États Financiers ». L'appel d'offres Caritas le nomme `TOM²ETATSFINANCIERS`. |
| `Tom²Portail` | **MANQUANT** | C'est **la plateforme d'intégration** elle-même : « conception modulaire et évolutive construite sur une plateforme commune », « intégration totale de tous les modules à travers le système TomPortail ». C'est **l'objet technique central pour la question de l'interopérabilité** et il est absent de la v1.0. → Ajouter comme module M11bis. |

---

## A.4 — Architecture technique — `L'INCONNUE PRINCIPALE EST LEVÉE`

La v1.0 traite le SGBD comme une inconnue totale (livrable D3.3, « rapport d'identification SGBD », 25 JH d'ingénieur données en P4). **Une source primaire la documente :**

> « **TOM²PRO fonctionne en client/serveur sous SQL Serveur en environnement Windows.** »
> — Proposition technique et financière DISS pour l'UCP MARNDR/FIDA, Haïti, 16 septembre 2013.

Recoupements et limites :
- **Cohérent** avec le module `Utilitaires` (« maintenance de la base de données, sauvegarde et restitution des bases de données ») et avec les prérequis Windows affichés par l'éditeur.
- **Limite 1 :** source de 2013. Elle ne vaut pas pour les versions actuelles ni pour la version WEB. → Statut : **`HYP-FORTE`**, à confirmer par observation en phase 3, pas à redécouvrir.
- **Limite 2 :** le site de l'éditeur ne nomme **aucun** SGBD, et ne mentionne ni WinDev/WEBDEV ni aucune technologie. L'atelier de développement reste inconnu.

**Autres éléments d'architecture établis, absents de la v1.0 :**

| Élément | Source | Portée |
|---|---|---|
| **Consolidation multi-sites par transfert de fichiers**, et non par réplication SGBD : module `Utilitaires` de TOMMONITORING = « le transfert de données entre antennes et l'UGP et la communication avec le logiciel de gestion comptable et financière » | DISS 2013 | Répond directement à la question ouverte du §9.1 de la v1.0 (« réplication ? fusion de fichiers ? base centrale ? »). Statut `HYP-FORTE`. |
| **Déclinaisons de licence par topologie** : « Mono-site, multisites centralisé ou décentralisé (avec des outils de consolidation) » ; « Mono-projet ou multi-projets » ; « Version light, complète ou spécialisée » | Éditeur | Le périmètre fonctionnel **dépend de la licence achetée** — ce qui explique le constat de l'audit PAZH (A.2.3). |
| **Multilinguisme plus large qu'annoncé** : « français, anglais, portugais, autres langues facilement implémentées selon les besoins » | Éditeur | La v1.0 (NF01) ne prévoit que le double libellé français/anglais. |
| **Traçabilité native revendiquée** : « stockage de l'historique des manipulations » ; « accès personnalisé (login et mot de passe) » | Éditeur | Donne un point de départ au test NF07. |
| **Concurrence réelle observée** : 10 accès simultanés (Guinée, UNOPS 2020) ; 16 clés utilisateur pour 10 financiers répartis sur 4 sites + siège (Haïti 2013) | UNOPS, DISS | Calibre la volumétrie des tests NF05 bien mieux que le « 5 utilisateurs et plus » de la v1.0. |

---

## A.5 — Cadre juridique (§3.1 de la v1.0) — `INCOMPLET et PARTIELLEMENT MAL RATTACHÉ`

### A.5.1 Ce qui est exact

| Affirmation | Verdict |
|---|---|
| Art. L.122-6-1 CPI — décompilation licite si indispensable à l'interopérabilité, par une personne ayant licitement accès, limitée aux informations nécessaires | **CONFIRMÉ** |
| Directive 2009/24/CE sur la protection juridique des programmes d'ordinateur | **CONFIRMÉ** (art. 5 §3 : observation, étude, test ; art. 6 : décompilation) |
| Nécessité d'analyser le CLUF | **CONFIRMÉ, mais à compléter** — voir ci-dessous |

### A.5.2 Ce qui manque — et qui change la nature du projet

**1. L'arrêt qui dé-risque l'essentiel du projet est absent.**

CJUE, **C-406/10, *SAS Institute Inc. c/ World Programming Ltd*, 2 mai 2012** : **les fonctionnalités d'un programme, le langage de programmation et les formats de fichiers de données ne sont pas protégés par le droit d'auteur** sur les programmes d'ordinateur.

C'est **le fondement juridique direct de l'intégralité des phases 1, 2, 3 et 5** de ce cahier des charges. Il signifie que reconstituer par observation les fonctionnalités, les règles de gestion, le modèle de données et les gabarits d'états **n'est pas une contrefaçon** — et ce, indépendamment de toute exception de décompilation. La v1.0, en traitant l'ensemble du projet sous le régime restrictif de l'exception de décompilation, **surestime massivement son propre risque juridique** et s'impose des contraintes (et des coûts) disproportionnées.

**2. La nullité d'ordre public des clauses contraires est absente.**

L'article L.122-6-1 CPI dispose que **« toute stipulation contraire aux dispositions prévues aux II, III et IV du présent article est nulle et non avenue »**. Autrement dit : une clause de CLUF interdisant l'observation, l'étude et le test du fonctionnement du programme (II et III) ou la décompilation aux fins d'interopérabilité (IV) **est inopposable en droit français**. La v1.0 présente l'analyse du CLUF comme susceptible de bloquer le projet ; en réalité, elle doit surtout servir à **identifier les clauses nulles** et à documenter cette nullité.

**3. L'arrêt sur la correction d'erreurs est absent.**

CJUE, **C-13/20, *Top System SA c/ État belge*, 6 octobre 2021** : l'acquéreur légitime d'un programme peut le décompiler, en tout ou partie, **pour corriger des erreurs affectant son fonctionnement** — y compris en désactivant une fonction défectueuse. Fondement : **l'article 5 de la directive, et non son article 6**. Le régime est donc distinct de celui de l'interopérabilité et **ne subit pas les conditions restrictives de l'article 6**. Pertinent si le projet retient l'option (b) « capacité autonome de migration/extraction des données ».

**4. L'OHADA est invoqué à tort, deux fois.**

| Affirmation v1.0 | Verdict | Correction |
|---|---|---|
| « Droit OHADA […] sur la protection des données » | **ERRONÉ** | L'OHADA est un droit **des affaires** (actes uniformes : sociétés, sûretés, comptabilité, procédures collectives…). Elle **ne traite ni de la propriété intellectuelle ni des données personnelles**. |
| Propriété intellectuelle du logiciel dans les pays de déploiement | **MAL RATTACHÉ** | Le cadre pertinent est l'**OAPI** — **Accord de Bangui, Annexe VII** (propriété littéraire et artistique), révisé par l'**Accord de Bamako du 14 décembre 2015**, en vigueur depuis le **20 novembre 2020**. L'Annexe VII fixe une **norme minimale** ; l'article 5 de l'Accord précise que les droits restent **des droits nationaux indépendants**, soumis à la législation de chaque État. → L'analyse doit donc être faite **pays par pays**, sur la loi nationale, pas sur un texte régional unique. |
| « lois type Malabo Convention de l'UA » | **CONFIRMÉ, à dater** | Convention de l'Union africaine sur la cybersécurité et la protection des données à caractère personnel, **adoptée le 27 juin 2014**, **entrée en vigueur le 8 juin 2023**. À compléter par les lois nationales, seules directement applicables. |

**5. Madagascar est hors de tous ces cadres — et le document s'en contredit.**

La v1.0 cite Madagascar à trois reprises (SOFTWELL, FIDA DEFIS, licence en MGA) **et** affirme au §4.3 que le référentiel comptable est « SYSCOHADA, SYCEBNL ». Or **Madagascar n'est membre ni de l'OHADA, ni de l'OAPI**. Son référentiel comptable est le **Plan Comptable Général 2005 (PCG 2005)**. Le périmètre « référentiels comptables » doit donc être élargi, ou Madagascar sorti du périmètre.

### A.5.3 Ce qui est exact mais mérite d'être renforcé

Le **SYCEBNL** : **CONFIRMÉ** sur tous les points.
- 11ᵉ Acte uniforme de l'OHADA, **adopté à Niamey le 22 décembre 2022**, publié au Journal officiel de l'OHADA le **22 février 2023**, **entré en vigueur le 1ᵉʳ janvier 2024**.
- Il comble un vide : l'article 5 de l'AUDCIF **exclut** les entités à but non lucratif du champ du SYSCOHADA.
- Obligations nouvelles à intégrer au périmètre fonctionnel : **registre des donateurs obligatoire (art. 17)**, dispositions pénales (art. 24 à 27, transposition nationale inégale), **bilan d'ouverture** à la date d'entrée en vigueur.

> **Point d'audit majeur, absent de la v1.0 :** **l'éditeur ne revendique nulle part la conformité SYSCOHADA ou SYCEBNL.** Son site dit seulement : « Formats des tableaux (bilan, compte de résultat, tableau des emplois et ressources) **conformes aux normalisations comptables généralement reconnues** » et « **Plan comptable adaptable à toute normalisation** ». La conformité réglementaire est donc **entièrement reportée sur le paramétrage client**. C'est précisément le mécanisme qui a produit la défaillance constatée au Gabon. **Ce constat devrait figurer au §1.2 de la v2.0 comme motivation principale du projet** — il est bien plus solide que l'argument des « formats propriétaires ».

---

## A.6 — Coûts et modèle de licence (§17 de la v1.0)

### A.6.1 Le repère de la v1.0 — `NON VÉRIFIÉ`

> « une licence nationale TOM²Pro a été constatée à ≈ 84 millions MGA (≈ 17–19 kUSD) hors intégration »

**Ce chiffre n'a pas pu être retrouvé.** Aucune source publique ne mentionne une « licence nationale » TOM²Pro à Madagascar ni le montant de 84 000 000 MGA. La seule donnée malgache approchante est un contrat SOFTWELL de **19 430 000** (devise non précisée dans la source) pour l'acquisition, l'installation et la formation TOMPRO, mentionné dans un rapport de supervision FIDA de décembre 2013. → **Retirer, ou citer la pièce d'origine.**

### A.6.2 Points de prix vérifiables qui le remplacent

| Contexte | Objet | Montant | Équivalent indicatif |
|---|---|---|---|
| **Haïti, 2013** (FIDA/PPI-II & III, intégrateur DISS) | Licence TOM²PRO *Biprojets, Multi-sites, Multi-utilisateurs* — siège | **10 000 € HT** | — |
| idem | Licence TOM²PRO *Biprojets, Mono-site, Multi-utilisateurs* — régions | **4 × 1 000 € HT** | — |
| idem | **Clés utilisateurs** | **16 × 200 € HT = 3 200 €** | — |
| idem | Sous-total logiciels (TOM²PRO + TOMMONITORING, remise éditeur 10 % déduite) | **25 700 € HT** | — |
| idem | Maintenance des logiciels sur 3 ans | **15 % = 3 855 €** | — |
| idem | Paramétrage et formation (60 J/H à 650 €/j) | **39 000 € HT** | — |
| **Gabon, projet PAZH** | TOMPRO immobilisé au bilan (immobilisation incorporelle) | **19 577 288 FCFA** | ≈ 30 k € |
| **Congo, PATN (BM), 2023** | Acquisition + installation + paramétrage + formation + assistance + maintenance, entente directe TOMATE | **20 308 193 FCFA** | ≈ 31 k € |
| **Congo** | Fourniture + installation TOMPRO + mise en réseau, entente directe TOMATE | **10 745 447 FCFA** | ≈ 16 k € |
| **Madagascar (BM)** | Migration TOM2PRO en version web, sélection directe SOFTWELL CONSULTING | **27 556 USD** | ≈ 25 k € |

### A.6.3 Le modèle de licence — `DÉCOUVERTE, absente de la v1.0`

La décomposition haïtienne révèle une structure tarifaire à **quatre dimensions multiplicatives** :

```
Coût licence = f( nb de projets ) × f( topologie : mono-site / multi-sites ) × f( nb de clés utilisateur ) + maintenance (% du sous-total logiciels)
```

avec, en 2013 : un **rapport 10:1 entre licence siège multi-sites (10 000 €) et licence régionale mono-site (1 000 €)**, et des **clés utilisateur facturées à l'unité (200 €)**.

**Trois conséquences pour le projet :**
1. Le §9.1 de la v1.0 (« mécanismes de licence et d'activation ») doit chercher **un mécanisme de clés par utilisateur**, pas seulement une clé produit globale. Cela oriente concrètement l'observation.
2. Le coût **croît avec la décentralisation et l'effectif** — c'est l'argument économique le plus fort du dossier coût-bénéfice, et la v1.0 ne l'exploite pas.
3. L'affirmation « TCO sur 5 ans = 3 à 5 fois la licence » reste **NON DÉMONTRÉE**, mais elle est **plausible et minorée** : dans le seul cas haïtien documenté, les prestations de mise en place (39 000 €) représentent déjà **1,5 fois** le coût des logiciels (25 700 €), **avant** toute maintenance, migration ou formation ultérieure. → Reformuler en « au moins 2,5 fois la licence dès la première année dans le seul cas entièrement documenté », et faire du calcul du TCO un livrable chiffré de J0.

---

## A.7 — Corpus documentaire (§6.1 et Annexe C de la v1.0)

| Source citée | Verdict | Observation |
|---|---|---|
| Manuel d'utilisation TOM²Pro WEB (≈ 650 p.) | **PARTIELLEMENT CONFIRMÉ** | Un « Manuel d'utilisation de Tom Pro Web » existe et circule en ligne. **La pagination de ~650 pages n'est pas vérifiée.** Ne pas la citer comme un fait. |
| Manuel de formation TomPro (desktop) | **CONFIRMÉ** | Un « Manuel de formation Tom²Pro » complet circule publiquement (navigation, saisies, modifications, paramétrage général). |
| **« TDR GABAC (déc. 2025) : spécifications détaillées des 10 modules + paie + RH »** | **ERRONÉ — à remplacer** | Le GABAC a bien lancé un appel d'offres pour un ERP (comptabilité générale, projets, passation de marchés, RH) — **mais en 2015**, avec dépôt au 30 septembre 2015, et **sans mention de TOMPRO**. Aucun document GABAC de 2025 relatif à TOMPRO n'a été retrouvé. **La source primaire réellement disponible pour la liste des 10 modules est l'avis UNOPS `RFQ/2020/14559` (UNGM n° 108162, Guinée, mai 2020) et sa republication `RFQ/2020/14883` (UNGM n° 108937).** |
| Rapport d'audit PAZH Gabon | **CONFIRMÉ, à redater** | Voir §A.2.3. Référence exacte à porter au registre. |
| Audit FIDA DEFIS Madagascar | **PARTIELLEMENT CONFIRMÉ** | Le rapport de supervision FIDA de décembre 2013 documente le paramétrage TOMPRO, l'harmonisation du plan comptable entre agences d'exécution et unités, et un contrat SOFTWELL. Le rapport de supervision de février 2022 documente des écarts entre registre des immobilisations, comptabilité et inventaire physique. **Le « coût de licence » annoncé n'y figure pas.** |
| GAFSP (PIEJR Mali) | **NON VÉRIFIÉ** | Aucune source retrouvée. |
| UNGM | **CONFIRMÉ** | Trois avis identifiés — voir Annexe B. |
| Expertise France | **NON VÉRIFIÉ** | Aucune source retrouvée. |

**Sources nouvelles à verser au corpus** (détail en Annexe B) : la clarification UNOPS du 19 mai 2020 (liste des 10 modules), la proposition DISS de septembre 2013 (architecture SQL Server, modèle de licence, modules), l'appel d'offres Caritas Africa du 2 juillet 2025 (version WEB, TOM²GRH), les marchés d'entente directe du Congo et du Tchad, le marché de migration web de Madagascar, les fiches produits de l'éditeur, et la fiche Tom²Portail.

---

## A.8 — Incohérences internes de la v1.0 (hors exactitude factuelle)

| § | Incohérence | Correction v2.0 |
|---|---|---|
| §15 vs §9.2 | §15 impose des VM « réseau **sans sortie Internet** » ; §9.2 prévoit l'« observation réseau » des API de la version WEB — laquelle suppose un serveur d'application joignable. | Distinguer **réseau de laboratoire instrumenté** (segment isolé d'Internet, avec serveur d'application, proxy d'inspection TLS sur matériel de test, capture) et **poste d'analyse hors ligne**. |
| §4.3 vs §1.1 | Le périmètre annonce les référentiels SYSCOHADA/SYCEBNL, mais cite Madagascar — hors OHADA. | Ajouter le PCG 2005 malgache, ou sortir Madagascar du périmètre. |
| §2.2 (OS2) | Cible « ≥ 95 % des entités principales » sans définir « entité principale ». | Définir la population de référence (les entités du tronc commun §8.2) avant de mesurer un taux. |
| §7.4 (D2.2) | « ≥ 300 règles de gestion attendues » — nombre non étayé. | Conserver comme **cible indicative**, et conditionner la recette à la **couverture** (toute règle de gestion rattachée à un écran et à un test), pas au volume. |
| §12.2 | Critère de sortie « rejeu réussi » par un tiers. | **Excellent critère — à conserver tel quel.** C'est le meilleur élément de la v1.0. |
| §13.2 | 460 JH, sans ligne pour l'obtention des accès (licences desktop **et** WEB) ni pour la négociation avec un intégrateur. | Ajouter une charge P0 dédiée ; c'est le chemin critique réel (risque R2). |
| §2.3 / §3.2 | La « salle blanche » est imposée dès que l'objectif est un redéveloppement. | Conserver, mais **restreindre son périmètre** : à la lumière de *SAS c/ WPL*, les spécifications fonctionnelles issues de l'observation ne sont pas des éléments protégés. La séparation stricte ne s'impose qu'aux éventuels livrables issus d'une décompilation. Économie de coût et de délai significative. |

---

## A.9 — Synthèse quantifiée

| Catégorie | Nombre | Affirmations concernées |
|---|---|---|
| **CONFIRMÉ** | 14 | Identité produit/éditeur, 10 modules, 4+4 plans, SYCEBNL 2024, L.122-6-1, directive 2009/24, entente directe, constat d'audit PAZH (fond), distribution par intégrateurs, immobilisations comme module, export Excel, traçabilité native, multi-sites, critère de rejeu |
| **CONFIRMÉ AVEC RÉSERVE** | 3 | Volumes d'installation (auto-déclarés), réseau d'intégrateurs (un nom non vérifié), manuel WEB (pagination non vérifiée) |
| **À NUANCER** | 5 | macOS, liste des bailleurs, « formats propriétaires », « quasi systématiquement » (entente directe), obsolescence |
| **NON VÉRIFIÉ** | 6 | Raison sociale de l'éditeur, 84 M MGA, TCO 3–5×, GAFSP/PIEJR, Expertise France, EasyTech Africa |
| **ERRONÉ** | 4 | Exercice de l'audit PAZH (2018 → 2020), TDR GABAC 2025 (→ 2015, sans TOMPRO), rattachement OHADA pour la PI et les données personnelles, produit `Tom²Conso` |
| **MANQUANT (ajout nécessaire)** | 7 | CJUE *SAS c/ WPL*, CJUE *Top System*, nullité des clauses contraires, OAPI/Bangui, SGBD SQL Server, modèle de licence par clés, produits TOM²GRH et Tom²Portail |

**Appréciation d'ensemble.** La v1.0 est **structurellement solide et largement exacte sur le fond métier** : le découpage fonctionnel, le modèle d'entités, la méthode en boîte noire, la traçabilité des preuves et le critère de recette par rejeu sont tous pertinents et se vérifient contre les sources primaires. Ses faiblesses sont concentrées sur trois points, tous corrigeables : **l'appareil de sources** (citations approximatives ou non retrouvées, ce qui fragilise un document destiné à fonder un marché public), **le cadre juridique** (incomplet au point de surestimer le risque du projet et d'en gonfler le coût), et **l'état de l'art technique** (plusieurs inconnues déclarées sont en réalité documentées, ce qui permet de réduire la charge et de concentrer l'effort là où il est réellement nécessaire).
