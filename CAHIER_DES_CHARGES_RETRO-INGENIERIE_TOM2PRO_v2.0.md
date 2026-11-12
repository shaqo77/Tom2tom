# CAHIER DES CHARGES — RÉTRO-INGÉNIERIE FONCTIONNELLE ET TECHNIQUE DU LOGICIEL TOM²PRO

**Projet :** analyse de rétro-ingénierie du système d'information de gestion financière (SIGF) TOM²PRO, édité par TOMATE, en vue de ☐ migration · ☐ interopérabilité · ☐ audit technique · ☐ développement d'une solution alternative *(cocher une ou plusieurs options ; la décision est prise au jalon J0 sur la base de l'analyse coût-bénéfice §17.4)*

**Version :** 2.0 — révision majeure
**Date :** 12 novembre 2026
**Remplace :** version 1.0
**Statut :** projet pour validation en comité de pilotage
**Diffusion :** restreinte — maîtrise d'ouvrage, maîtrise d'œuvre, conseil juridique

**Annexes séparées :**
- [`ANNEXE_A_VERIFICATION_FACTUELLE.md`](ANNEXE_A_VERIFICATION_FACTUELLE.md) — audit d'exactitude de la v1.0, affirmation par affirmation
- [`ANNEXE_B_REGISTRE_DES_SOURCES.md`](ANNEXE_B_REGISTRE_DES_SOURCES.md) — corpus documentaire constitué et pièces à obtenir

---

## SOMMAIRE

0. Ce qui change par rapport à la version 1.0
1. Contexte et justification
2. Objectifs du projet
3. Cadre juridique, éthique et conformité
4. Périmètre de la rétro-ingénierie
5. Méthodologie générale et phases
6. Phase 1 — Analyse documentaire
7. Phase 2 — Rétro-ingénierie fonctionnelle (boîte noire)
8. Phase 3 — Rétro-ingénierie du modèle de données
9. Phase 4 — Rétro-ingénierie technique (architecture, licence, formats)
10. Phase 5 — Rétro-ingénierie des règles métier bailleurs
11. Spécifications non fonctionnelles à reconstituer
12. Livrables et critères d'acceptation
13. Planning, jalons et charges estimées
14. Équipe projet et compétences requises
15. Environnement de travail et moyens
16. Gestion des risques
17. Budget et analyse coût-bénéfice
18. Annexes

---

## 0. CE QUI CHANGE PAR RAPPORT À LA VERSION 1.0

La version 1.0 était structurellement juste : son découpage fonctionnel, son modèle d'entités, sa méthode en boîte noire et son critère de recette par rejeu se vérifient tous contre les sources primaires. Cette révision ne la refait pas — elle la **corrige sur les faits**, la **complète sur le droit**, et **réduit son périmètre d'incertitude** en y injectant l'état de l'art réellement établi.

| # | Changement | Effet |
|---|---|---|
| **1** | **Le droit applicable est refondé.** Ajout de l'arrêt CJUE *SAS Institute c/ World Programming* (C-406/10, 02/05/2012) : fonctionnalités, langage et **formats de fichiers de données ne sont pas protégés** par le droit d'auteur. Ajout de la nullité d'ordre public des clauses de CLUF contraires (L.122-6-1 CPI). Ajout de *Top System* (C-13/20). | **Les phases 1, 2, 3 et 5 — soit l'essentiel du projet — ne relèvent pas de l'exception de décompilation et ne sont pas des actes de contrefaçon.** La salle blanche intégrale et l'avis juridique bloquant généralisé de la v1.0 étaient surdimensionnés. Économie : ~8 JH de conseil juridique et plusieurs semaines de délai. |
| **2** | **Rattachement juridique corrigé.** L'OHADA ne couvre ni la propriété intellectuelle ni les données personnelles. Substitution par l'**OAPI** (Accord de Bangui, Annexe VII, rév. Bamako 2015 en vigueur depuis le 20/11/2020) en analyse **pays par pays**, et par la **Convention de Malabo** (en vigueur le 08/06/2023) plus les lois nationales. | Évite un avis juridique fondé sur un corpus inapplicable. |
| **3** | **Le SGBD n'est plus une inconnue.** Source primaire 2013 : « TOM²PRO fonctionne **en client/serveur sous SQL Serveur en environnement Windows** ». | La phase 3 démarre sur une **hypothèse forte à confirmer** plutôt que sur une découverte à mener. Réallocation de ~15 JH vers la version WEB, dont l'architecture reste inconnue. |
| **4** | **La nomenclature des modules devient celle de l'éditeur**, établie par deux sources primaires concordantes à sept ans d'écart (clarification UNOPS 2020 ; proposition d'intégrateur 2013). | Les livrables deviennent directement opposables en marché public et lisibles par l'éditeur, les intégrateurs et les bailleurs. |
| **5** | **Périmètre produit corrigé.** `Tom²Conso` n'existe pas → supprimé. **`TOM²GRH`** existe → ajouté. **`Tom²Portail`**, la plateforme d'intégration elle-même, était absent → ajouté comme objet central de l'étude d'interopérabilité. | Évite de chercher un produit inexistant et de manquer la couche qui porte l'intégration. |
| **6** | **L'argument de verrouillage est reciblé.** Les exports Excel et CSV sont documentés par l'éditeur lui-même : l'argument « formats de sortie propriétaires » de la v1.0 est réfutable en une phrase. Le verrou réel est **la non-portabilité du paramétrage**, le schéma de données non documenté, le **modèle de licence par clés utilisateur**, et la concentration de la compétence dans un réseau certifié annuellement. | Dossier défendable devant l'éditeur et devant un bailleur. |
| **7** | **Le constat d'audit est redaté et renforcé.** Delta Grant Thornton, **exercice 2020**, rapport du 22/02/2022 (et non « exercice 2018 »). Fond confirmé mot pour mot, avec un fait plus fort : **les états financiers annuels sont reconstruits à la main sous Excel**. Nuance ajoutée : l'audit impute la défaillance à **la version acquise et à son paramétrage**, pas au produit. | Crédibilité du dossier ; et protection contre une contestation légitime de l'éditeur. |
| **8** | **Le repère de prix non sourçable (84 M MGA) est remplacé** par cinq points de prix publics et vérifiables, et par la **structure tarifaire réelle** : licence × projets × topologie × clés utilisateur + maintenance. | L'analyse coût-bénéfice de J0 repose sur des pièces opposables. |
| **9** | **Terminologie bailleurs corrigée.** « IPFR » n'existe pas. Les termes exacts sont **IFR/RFI**, **RSF**, **SOE/ECD**, **DRF**, **compte désigné**. | Condition de recevabilité des livrables de la phase 5. |
| **10** | **Deux objectifs spécifiques sont ajoutés** : la **stratégie de sortie et d'extraction des données** (OS7) et le **modèle de coût total de possession** (OS8), tous deux implicites dans la finalité de la v1.0 mais absents de ses livrables. | Le projet produit enfin ce qui motive sa commande. |
| **11** | **Exigence SYCEBNL intégrée au périmètre fonctionnel.** En vigueur depuis le 01/01/2024, avec registre des donateurs obligatoire (art. 17). **L'éditeur ne revendique nulle part la conformité SYSCOHADA ou SYCEBNL** : « plan comptable adaptable à toute normalisation ». La conformité repose donc entièrement sur le paramétrage client. | C'est le risque métier le mieux établi du dossier, et la justification la plus solide du projet. |

---

## 1. CONTEXTE ET JUSTIFICATION

### 1.1 Le logiciel TOM²PRO

TOM²PRO est un système d'information de gestion financière édité par **TOMATE**, déployé dans les unités de gestion de projets financés par les bailleurs multilatéraux, principalement en Afrique francophone. Il couvre le cycle complet : **codification → programmation budgétaire → engagement → comptabilisation → restitution et reporting bailleurs** `[SRC:marche:101:2020-05-19]`.

Il s'inscrit dans la suite **Tom²Portail**, présentée par l'éditeur comme une « conception modulaire et évolutive construite sur une plateforme commune » permettant « l'intégration totale de tous les modules » `[SRC:editeur:003]`. La gamme publiée comprend sept logiciels : Tom²Pro, Tom²Paie, Tom²EtatsFin, Tom²Monitoring, Tom²Projet, Tom²Marché, Tom²Stock `[SRC:editeur:002]` ; un huitième, **TOM²GRH**, apparaît dans les appels d'offres sans figurer au catalogue public `[SRC:marche:105:2025-07-02]`.

**Diffusion.** Le déploiement est largement attesté par des actes de bailleurs au Gabon, au Congo, au Tchad, au Mali, à Madagascar, en Guinée, en Haïti, au Burkina Faso, en RDC, au Niger et au Sénégal `[SRC:audit:201]` `[SRC:marche:301]` `[SRC:marche:303]` `[SRC:superv:203]` `[SRC:integrateur:104]` `[SRC:forma:501]`. Les volumes revendiqués par l'éditeur — « plus de 2 000 installations », « plus de 40 pays », « plus de 50 partenaires agréés » `[SRC:editeur:004]` — sont auto-déclarés et **ne doivent pas être repris comme des faits établis**.

**Distribution.** Exclusivement indirecte : « nos logiciels sont uniquement disponibles à travers un réseau de distributeurs » `[SRC:editeur:004]`, individuellement agréés et porteurs d'une certification « TechExpert » **renouvelée annuellement** par l'éditeur `[SRC:editeur:006]`. Partenaires identifiés : AGOSOFT (Côte d'Ivoire), SOFTWELL (Madagascar), 2DBC et AZ Consulting (Sénégal), ACECA International et MICROSYS (Burkina Faso), AE2C et CIFOPE Afrique (Mali), CE.S.I (Niger), ACW (Tunisie), DISS (France, zone Haïti) `[SRC:editeur:005]` `[SRC:integrateur:104]`.

**Générations.**
- **Client lourd Windows.** Prérequis affichés par l'éditeur : « Windows 10, 8, 7, Vista, XP », « CPU Intel ou AMD et 4 Go de RAM » `[SRC:editeur:001]`. Il n'existe **pas de version macOS native** : le support annoncé passe par « Parallels Desktop / Boot Camp / Windows », c'est-à-dire par émulation.
- **TOM²PRO WEB.** Son existence est établie par trois sources indépendantes de 2024-2025 : l'appel d'offres Caritas Africa portant sur « les versions web des produits logiciels TOMATE » `[SRC:marche:105:2025-07-02]`, une formation du PADS Burkina Faso sur « la version web du logiciel TOM2PRO » pour des subventions du Fonds mondial `[SRC:forma:501:2024-12]`, et un marché de la Banque mondiale de « fourniture et migration du logiciel TOM2PRO en version WEB » `[SRC:marche:304]`. **Fait notable : le site de l'éditeur ne la mentionne nulle part.** Le canal commercial réel est en avance sur la documentation publique — ce qui constitue en soi une difficulté d'accès à l'information et motive la démarche.

**Bailleurs revendiqués par l'éditeur** `[SRC:editeur:004]` : Banque mondiale, Union européenne, Banque africaine de développement, PNUD, FIDA, Fonds mondial, BID. *(Toute mention de GAFSP, AFD ou Expertise France est à traiter comme `[HYP]` jusqu'à production d'une pièce.)*

### 1.2 Problèmes constatés motivant la rétro-ingénierie

**(a) Conformité réglementaire reportée sur le client — motif principal.**
L'éditeur **ne revendique nulle part la conformité à un référentiel comptable nommé**. Ses formulations sont : « formats des tableaux (bilan, compte de résultat, tableau des emplois et ressources) **conformes aux normalisations comptables généralement reconnues** » et « **plan comptable adaptable à toute normalisation** » `[SRC:editeur:001]`. Ni SYSCOHADA, ni SYCEBNL, ni IFRS n'apparaissent dans la documentation publique de l'éditeur.

La conformité réglementaire repose donc **entièrement sur le paramétrage réalisé chez le client**. Or le **SYCEBNL** — 11ᵉ acte uniforme OHADA, adopté à Niamey le 22/12/2022, en vigueur le **1ᵉʳ janvier 2024** `[SRC:compta:407]` — impose aux entités à but non lucratif, dont relèvent la plupart des unités de gestion de projets, un référentiel nouveau avec des obligations nouvelles (registre des donateurs, art. 17 ; bilan d'ouverture ; dispositions pénales, art. 24-27). **Une organisation dont la conformité dépend d'un paramétrage non documenté et non portable est structurellement exposée à chaque évolution réglementaire.**

**(b) Défaillance documentée en exploitation réelle.**
Dans l'audit de clôture du projet PAZH (Gabon, don TF 016689-GA, exercice clos le 31/12/2020, rapport du 22/02/2022), Delta Grant Thornton constate `[SRC:audit:201:2022-02-22]` :

> « L'UCP utilise un progiciel qui, de fait de problèmes de paramétrage, **ne permet pas la préparation de l'état des emplois et ressources** […] **et le suivi budgétaire de manière automatique.** »

> « Les états financiers annuels du Projet sont **élaborés manuellement en fichier Excel**, après retraitement des balances et d'autres états extraits du logiciel TOM2 PRO. »

**Trois précisions d'honnêteté intellectuelle, à maintenir dans tout usage de ce constat :**
1. L'audit impute explicitement la défaillance à « **la version de TOM2 PRO acquise par le Projet** » — donc au périmètre de licence et au paramétrage, **non à un défaut intrinsèque du produit**.
2. Le rapport se contredit : la note 1.8 affirme que le logiciel produit bien « le Tableau emplois, le tableau d'utilisation des fonds, le tableau du suivi budgétaire ». Cette contradiction suggère une capacité existante mais non activée. **Trancher ce point est un objectif de test de la phase 2.**
3. L'opinion d'audit est **non modifiée (sans réserve)**. Le constat relève des observations et du contrôle interne, non d'une réserve sur les comptes.

**(c) Dépendance au réseau de distribution.**
L'acquisition initiale et le paramétrage sont fréquemment passés **par entente directe** avec l'éditeur ou par sélection directe d'un intégrateur agréé : Congo, projet PATN, réf. `CG-PATN-0018-F-ED-2023`, 20 308 193 FCFA `[SRC:marche:301]` ; Congo, fourniture et mise en réseau, 10 745 447 FCFA `[SRC:marche:302]` ; Tchad, UGP PDMFI/FJ (BAD) `[SRC:marche:303]` ; Madagascar, migration web par sélection directe, 27 556 USD `[SRC:marche:304]`.

*Nuance à conserver :* la **maintenance** fait parfois l'objet d'une mise en concurrence ouverte — mais avec des critères de référence restrictifs (« au moins deux marchés de prestations de maintenance des logiciels de la société TOMATE ») qui ramènent de fait la concurrence au réseau agréé `[SRC:marche:305]`.

**(d) Coût de possession indexé sur la croissance de l'organisation.**
La structure tarifaire documentée est multiplicative : licence par projet × topologie (mono-site / multi-sites) × **clés utilisateur facturées à l'unité** + maintenance en pourcentage. Exemple vérifié (Haïti, 2013, EUR HT) : licence siège multi-sites 10 000 € ; 4 licences régionales mono-site à 1 000 € ; **16 clés utilisateur à 200 €** ; sous-total logiciels 25 700 € ; maintenance 3 ans 15 % ; prestations de mise en place 60 J/H à 650 €/j, soit **39 000 €** `[SRC:integrateur:104:2013-09-16]`. Les prestations représentent à elles seules **1,5 fois** le coût des logiciels, avant toute migration ou formation ultérieure.

**(e) Non-portabilité du paramétrage et opacité du schéma de données.**
Les **exports** ne sont pas le problème : l'éditeur documente « importations et exportations des données » au module `Utilitaires` `[SRC:marche:101]`, et un intégrateur atteste que « tous les rapports peuvent être exportés vers MS-Excel » `[SRC:integrateur:104]`. Le verrou porte sur **(i)** le paramétrage, qui porte toute la valeur métier (plans de gestion, rubriques d'états, formules d'alimentation bailleurs) et n'est pas réputé exportable ; **(ii)** le schéma de la base, non documenté publiquement ; **(iii)** la concentration de la compétence dans le réseau certifié.

> **La démonstration de la complétude — ou de l'incomplétude — des exports natifs est un objectif de test explicite de la phase 2 (§7.3, cas transverse CT-07), et non un présupposé du présent cahier des charges.**

**(f) Trajectoire technique.**
Faits, et non appréciations : l'éditeur affiche en 2026 des prérequis incluant Windows XP, Vista, 7 et 8, tous en fin de support `[SRC:editeur:001]` ; des unités de gestion passent des marchés de « migration du logiciel TOM2PRO en version web » `[SRC:marche:304]` ; l'éditeur ne documente publiquement ni SGBD, ni technologie, ni version WEB.

### 1.3 Finalité du projet

Reconstituer, de manière exhaustive, traçable et opposable :

1. le **modèle fonctionnel** (processus, écrans, règles de gestion, machines à états) ;
2. le **modèle de données** (entités, relations, axes d'analyse, nomenclatures, lignage) ;
3. les **règles métier bailleurs** (gabarits de reporting, DRF, ECD/SOE, IFR/RSF, comptes désignés) et le **moteur d'états paramétrables** qui les produit ;
4. l'**architecture technique** (SGBD, topologies, consolidation multi-sites, mécanismes de licence) ;
5. les **interfaces d'interopérabilité** (exports, imports, services de la version WEB, intégration via Tom²Portail) ;
6. une **stratégie de sortie** opérationnelle : capacité autonome d'extraction et de reprise des données.

Le résultat alimente, selon la décision prise en **J0** : **(a)** un dossier d'architecture cible pour un développement de remplacement, **(b)** une capacité autonome de migration et d'extraction des données, **(c)** un dossier d'audit technique, ou **(d)** un cahier des charges de marché public de substitution.

---

## 2. OBJECTIFS DU PROJET

### 2.1 Objectif général

Produire un dossier de rétro-ingénierie complet, traçable et exploitable, couvrant **100 % des modules fonctionnels et du modèle de données** de TOM²PRO (versions desktop et WEB), dans le strict respect du cadre juridique applicable, et permettant à un tiers de spécifier une application reproduisant les sorties du logiciel sur un jeu de données de référence.

### 2.2 Objectifs spécifiques

| N° | Objectif | Indicateur | Cible |
|----|----------|------------|-------|
| **OS1** | Cartographier les modules et processus | Modules documentés / nomenclature éditeur `[SRC:marche:101]` | **10/10 modules** + Tom²Portail |
| **OS2** | Reconstituer le modèle de données | Entités du tronc commun (§8.2) documentées au dictionnaire, avec type, longueur, clé, nullabilité et source de preuve | **≥ 95 %** des entités du tronc commun, **100 %** de celles alimentant un état bailleur |
| **OS3** | Reconstituer les gabarits de reporting bailleurs | Gabarits spécifiés avec formules d'alimentation cellule par cellule | **≥ 6 bailleurs**, **≥ 30 gabarits** |
| **OS4** | Documenter les interfaces techniques | Formats d'import/export spécifiés avec spécimens et parseurs de référence | **100 %** des formats légalement accessibles |
| **OS5** | Constituer un référentiel de tests de conformité | Cas de test exécutables, données d'entrée et résultats attendus | **≥ 50 cas**, couvrant chaque module et chaque cas transverse du §7.3 |
| **OS6** | Produire l'architecture cible de remplacement *(si option (a))* | Dossier validé en COPIL | 1 dossier |
| **OS7** | **Établir une stratégie de sortie opérationnelle** *(nouveau)* | Chaîne d'extraction exécutable, bout en bout, d'une base TOM²PRO vers un format pivot documenté, rejouée avec succès sur le jeu de référence | **1 chaîne démontrée**, taux de reprise **≥ 99 %** des écritures et **100 %** des référentiels |
| **OS8** | **Chiffrer le coût total de possession et instruire la décision *make-or-buy*** *(nouveau)* | Modèle de TCO à 5 ans, à partir de pièces de marché opposables, comparant statu quo / migration / remplacement | **1 modèle chiffré**, livré à **J0** |

### 2.3 Limites et exclusions

- **Aucune contrefaçon.** Le projet ne reproduit ni le code source, ni l'interface graphique à l'identique, ni la documentation de l'éditeur au-delà du droit de citation.
- **Aucune neutralisation de mesure technique de protection.** Le contournement d'un dongle, d'une clé de licence ou d'un chiffrement est exclu, sauf exception légale d'interopérabilité expressément validée par le conseil juridique (§3.4).
- **Aucun accès aux systèmes de production d'un tiers** sans autorisation écrite du titulaire de la licence.
- **Aucune extraction de données à caractère personnel** des bases analysées (§3.5).
- **Modules satellites hors périmètre d'analyse détaillée** : Tom²Paie, Tom²GRH, Tom²EtatsFin, Tom²Marché, Tom²Stock, Tom²Monitoring, Tom²Projet font l'objet d'une **cartographie d'interopérabilité uniquement** (§4.1, M12).

---

## 3. CADRE JURIDIQUE, ÉTHIQUE ET CONFORMITÉ

> **Principe directeur de la v2.0.** La version 1.0 plaçait l'ensemble du projet sous le régime restrictif de l'exception de décompilation, et en surestimait d'autant le risque et le coût. En réalité, **trois régimes juridiques distincts s'appliquent à trois catégories d'actes distinctes**. Les distinguer est la première condition d'un projet proportionné.

### 3.1 Les trois régimes applicables

**Régime 1 — Ce qui n'est pas protégé : les phases 1, 2, 3 et 5.**

> CJUE, **C-406/10, *SAS Institute Inc. c/ World Programming Ltd*, 2 mai 2012** : **ni les fonctionnalités d'un programme d'ordinateur, ni le langage de programmation, ni les formats de fichiers de données ne constituent une forme d'expression protégée** par le droit d'auteur sur les programmes d'ordinateur. `[SRC:droit:403]`

**Conséquence directe.** Reconstituer par observation les fonctionnalités, les règles de gestion, le modèle de données, les nomenclatures, les gabarits d'états et **les formats de fichiers d'échange** n'est **pas un acte de contrefaçon**. Ces travaux — soit l'essentiel du présent cahier des charges — ne requièrent ni l'exception de décompilation, ni les conditions restrictives qui s'y attachent.

**Régime 2 — Ce qui est expressément permis : l'observation, l'étude et le test.**

> **Directive 2009/24/CE, art. 5 §3** et **art. L.122-6-1-III CPI** : la personne habilitée à utiliser le programme peut, **sans autorisation du titulaire**, observer, étudier ou tester son fonctionnement afin de déterminer les idées et principes qui sont à la base de n'importe quel élément du logiciel, lorsqu'elle effectue des opérations de chargement, d'affichage, d'exécution, de transmission ou de stockage qu'elle est en droit d'effectuer. `[SRC:droit:402]`

C'est le fondement direct du protocole d'expérimentation de la phase 2.

**Régime 3 — Ce qui est encadré : la décompilation du code exécutable.**

> **Art. L.122-6-1-IV CPI** et **directive 2009/24/CE, art. 6** : la décompilation n'est licite que si elle est **indispensable à l'interopérabilité** d'un logiciel créé de façon indépendante, réalisée par une personne **ayant licitement accès** au programme, et **limitée aux parties nécessaires**. Les informations obtenues ne peuvent servir à autre chose, ni être communiquées à des tiers hors besoin d'interopérabilité, ni servir à développer un logiciel substantiellement similaire. `[SRC:droit:401]`

> **CJUE, C-13/20, *Top System SA c/ État belge*, 6 octobre 2021** : l'acquéreur légitime peut décompiler, en tout ou partie, **pour corriger des erreurs affectant le fonctionnement** du programme — y compris en désactivant une fonction défectueuse. Fondement : **l'article 5 de la directive, et non son article 6** ; les conditions restrictives de l'article 6 ne s'y appliquent donc pas. `[SRC:droit:404]`

**Dans le présent projet, seul le régime 3 appelle un avis juridique préalable bloquant.** Les régimes 1 et 2 couvrent les phases 1, 2, 3, 5, 6 et l'essentiel de la phase 4.

### 3.2 Nullité des clauses de licence contraires

> **Art. L.122-6-1 CPI, in fine :** « **Toute stipulation contraire aux dispositions prévues aux II, III et IV du présent article est nulle et non avenue.** » `[SRC:droit:401]`

Une clause de CLUF interdisant l'observation, l'étude ou le test du fonctionnement du programme, ou la décompilation aux fins d'interopérabilité, **est inopposable en droit français**. L'analyse du CLUF TOM²PRO n'a donc pas pour objet de déterminer si le projet est permis, mais :
1. d'**identifier les clauses nulles** et de documenter leur nullité dans le journal de conformité ;
2. d'identifier les clauses **valablement opposables** (confidentialité, périmètre d'usage, nombre d'utilisateurs, audit) et de s'y conformer ;
3. de vérifier la **loi applicable et la juridiction compétente** stipulées au contrat — ce point détermine quel corpus s'applique réellement (§3.3).

### 3.3 Droit applicable dans les pays de déploiement

**La propriété intellectuelle ne relève pas de l'OHADA.** L'OHADA est un droit des affaires (sociétés, sûretés, comptabilité, procédures collectives) et ne traite ni du droit d'auteur sur les logiciels, ni des données personnelles.

| Matière | Cadre applicable | Portée |
|---|---|---|
| **Droit d'auteur sur le logiciel** (17 États d'Afrique de l'Ouest et centrale) | **OAPI — Accord de Bangui, Annexe VII** (propriété littéraire et artistique), révisé par l'**Accord de Bamako du 14/12/2015**, en vigueur depuis le **20/11/2020** `[SRC:droit:405]` | L'Annexe VII fixe une **norme minimale**. L'art. 5 de l'Accord dispose que les droits restent **des droits nationaux indépendants**, soumis à la législation de chaque État. → **L'analyse doit être conduite pays par pays, sur la loi nationale.** |
| **Hors espace OAPI** (Madagascar, notamment) | Droit national ; Madagascar n'est membre **ni de l'OHADA ni de l'OAPI** | Analyse nationale spécifique |
| **Données à caractère personnel** | **Convention de Malabo** (UA, cybersécurité et protection des données), adoptée le 27/06/2014, **en vigueur le 08/06/2023** `[SRC:droit:406]`, **+ lois nationales**, seules directement applicables | Pertinent dès que les spécimens touchent Tom²Paie, Tom²GRH ou les plans de tiers |
| **Droit du contrat de licence** | Loi stipulée au CLUF (à vérifier en P0) | Détermine l'applicabilité du CPI français et de la directive UE |
| **Conventions de financement des bailleurs** | Clauses d'audit, de propriété des données, d'accès des bailleurs aux systèmes | Peuvent **fonder un droit d'accès** aux données du projet, indépendant du CLUF |

> **Point souvent décisif :** les conventions de financement comportent presque toujours une clause de propriété des données du projet au bénéfice du bénéficiaire et un droit d'accès du bailleur. **La propriété des données n'est pas la propriété du logiciel** : elle fonde juridiquement l'objectif OS7 (stratégie de sortie) sans dépendre du CLUF.

### 3.4 Mesures de conformité obligatoires

1. **Avis juridique préalable écrit**, portant sur : (i) le CLUF (loi applicable, clauses nulles, clauses opposables) ; (ii) la loi nationale du pays de la maîtrise d'ouvrage ; (iii) **à titre bloquant, uniquement les actes relevant du régime 3** (décompilation, analyse de binaire, observation de protocole chiffré). **Les phases 1, 2, 3, 5 et 6 ne sont pas suspendues à cet avis** ; elles sont couvertes par les régimes 1 et 2, sous réserve d'un accès licite à une licence.
2. **Accès licite démontré.** Toute activité d'expérimentation est conduite **exclusivement sur une licence acquise licitement par la maîtrise d'ouvrage**, dans un environnement de test isolé. La pièce établissant ce droit (contrat, facture, attestation de l'intégrateur) est versée au dossier **avant** le démarrage de la phase 2. **C'est une condition suspensive, non un formalisme.**
3. **Salle blanche — à périmètre restreint.** Si l'option (a) « développement de remplacement » est retenue, la séparation stricte entre équipe d'analyse et équipe de développement s'applique **aux seuls livrables issus d'actes relevant du régime 3**. Les spécifications fonctionnelles issues de l'observation licite (régimes 1 et 2) ne portent pas d'éléments protégés et **peuvent être transmises directement à l'équipe de développement**. *(Cette restriction, fondée sur SAS c/ WPL, est la principale source d'économie de la v2.0 par rapport à la v1.0.)*
4. **Journal de conformité.** Consignation de toute opération d'analyse : qui, quoi, quand, sur quel support, **sous quel régime juridique (1, 2 ou 3)**, et sur quel fondement.
5. **Anonymisation systématique** de toute donnée réelle utilisée comme spécimen ; **interdiction d'extraire des données à caractère personnel** des bases analysées ; registre de traitement et purge documentée.
6. **Accords de confidentialité** pour tous les intervenants, couvrant notamment les clauses de confidentialité valablement opposables du CLUF.
7. **Vérification des clauses de non-concurrence** des analystes ayant une expérience TOM²PRO ou une certification TechExpert.

### 3.5 Données personnelles

Le périmètre M01 (plan de tiers) et les modules satellites Tom²Paie / Tom²GRH portent par construction des données à caractère personnel (identité, rémunération, coordonnées bancaires). Mesures :
- Les jeux de test sont **synthétiques par défaut** (§7.1).
- Toute extraction depuis une base réelle est subordonnée au **consentement écrit du responsable de traitement du projet concerné** et à une **anonymisation irréversible préalable**, documentée.
- Un **registre de traitement** est tenu pour la durée du projet et une **purge** est opérée et attestée à la clôture.
- Les VM d'analyse sont chiffrées au repos ; les instantanés sont détruits à la clôture, destruction attestée.

### 3.6 Éthique et transparence

Le projet respecte un principe de transparence vis-à-vis des bailleurs concernés. Lorsque la démarche vise la pérennité des données financières de projets qu'ils financent, **les bailleurs peuvent être informés et associés** — un observateur bailleur est prévu au COPIL (§14). Le projet ne vise ni à déprécier le produit de l'éditeur, ni à en diffuser des éléments protégés : ses constats sont sourcés, datés et contradictoires.

---

## 4. PÉRIMÈTRE DE LA RÉTRO-INGÉNIERIE

### 4.1 Modules fonctionnels dans le périmètre

La nomenclature ci-dessous est **celle de l'éditeur**, établie par deux sources primaires concordantes `[SRC:marche:101:2020-05-19]` `[SRC:integrateur:104:2013-09-16]`.

| Code | Module (nomenclature éditeur) | Contenu à reconstituer |
|------|-------------------------------|------------------------|
| **M01** | **Codifications** | Paramètres généraux ; plan comptable multi-exercices adaptable à toute normalisation ; plan de tiers ; plan de journaux ; **jusqu'à 4 plans de gestion** (axes : budgétaire, analytique, géographique, financement) ; **jusqu'à 4 plans auxiliaires** ; codification des sources de fonds (bailleur / financement / catégorie / sous-catégorie) ; **gestion des cofinancements** ; multidevises ; double libellé bilingue. *Référence 2013 : « cinq plans » = plan comptable + 4 axes de gestion.* |
| **M02** | **Comptabilité générale** (et auxiliaire) | **Bascule comptabilité d'engagement ↔ comptabilité de trésorerie** *(paramètre structurant — voir §7.3 CT-08)* ; saisie unique alimentant tous les autres modules ; contrepartie automatique ; schémas d'écritures prédéfinis ; lettrage / dé-lettrage ; rapprochement bancaire en monnaie et en devise ; arrêté de caisse ; ordres de paiement préformatés ; échéancier ; à-nouveaux ; clôtures mensuelles et annuelles ; conversion de devises ; **génération automatique d'écritures depuis les autres modules** (marchés, patrimoine, trésorerie, paie) |
| **M03** | **Comptabilité analytique** | Suivi des réalisations selon le découpage analytique du projet et/ou du cadre logique ; clés de répartition ; **ventilation a posteriori (imputation secondaire)** ; balance et grand livre analytiques ; tableaux récapitulatifs pluriannuels ; calcul de coûts |
| **M04** | **Budget et suivi budgétaire** | Saisie du budget en toute monnaie ; budget **configurable à partir d'une combinaison des plans** ; budgets multi-niveaux ; consommation ; **prise en compte des engagements dans les rapports budgétaires** ; réallocations ; clôture de budget ; reliquats ; taux d'exécution ; analyse multicritère ; arbitrage budgétaire (option) ; export de tous les rapports vers Excel |
| **M05** | **Marchés et engagements** | Types de passation ; schémas de décaissement ; saisie des contrats et bons de commande ; avenants ; décomptes ; **apurement des engagements** ; garanties et assurances ; rattachement documentaire ; fiches de marchés ; taux d'exécution physique et financier |
| **M06** | **Suivi des conventions de financement** | Conventions par catégorie ; réallocations ; **DRF (demandes de retrait / de réapprovisionnement de fonds)** ; **demandes de paiement direct au format des différents bailleurs** ; mémoires de justification des dépenses ; situation des accords de crédit et de dons ; comptes désignés / comptes spéciaux |
| **M07** | **Gestion des décaissements** | Comparaison budget / décaissé ; tableaux de bord de décaissements ; budget de trésorerie par période et par axe ; prévisions ; états de reporting associés |
| **M08** | **États financiers** | Bilan, compte de résultat, **tableau des emplois et ressources (TER)**, flux de trésorerie ; **rubriques paramétrables par fourchettes de comptes et formules** ; contrôles de cohérence ; ratios ; **états RSF / IFR suivant le format bailleur** (TER, tableau d'utilisation des fonds par activités) ; tableaux de bord ; conformité SYSCOHADA / **SYCEBNL** / PCG 2005 à évaluer |
| **M09** | **Gestion des immobilisations** | Fiches d'immobilisations (saisie comptable et extracomptable) ; affectations, localisation et traçabilité ; amortissements ; cessions ; inventaires ; cofinancement en pourcentage |
| **M10** | **Utilitaires** | Maintenance et **réparation de la base** ; **importations et exportations de données** ; sauvegarde et restitution ; mise à jour du système ; gestion des utilisateurs et des droits ; journaux d'audit ; multi-sites (code site) et consolidation |
| **M11** | **Interopérabilité** | Exports (Excel, CSV, PDF) ; imports (budgets, écritures, données historiques par fichiers Excel pré-formatés) ; API ou services web éventuels de la version WEB ; transferts inter-sites |
| **M11bis** | **Tom²Portail — plateforme d'intégration** *(nouveau)* | « Plateforme commune » revendiquée par l'éditeur ; mécanisme d'« intégration totale de tous les modules » ; partage d'informations entre fonctionnalités ; gestion commune des utilisateurs, des droits et de la traçabilité ; déclinaisons mono/multi-postes, mono/multi-sites (centralisé ou décentralisé), mono/multi-projets, versions light / complète / spécialisée `[SRC:editeur:003]`. **C'est la couche qui détermine la faisabilité réelle de tout remplacement partiel.** |
| **M12** | **Modules satellites** *(cartographie d'interopérabilité uniquement)* | **Tom²Paie**, **Tom²GRH**, **Tom²EtatsFin**, **Tom²Marché**, **Tom²Stock**, **Tom²Monitoring**, **Tom²Projet**. Objet : nature et format des flux échangés avec TOM²PRO, pas le fonctionnement interne. *(`Tom²Conso` est retiré : ce produit n'existe pas dans la gamme publiée ; la consolidation est une fonction de M10/M11bis.)* |

### 4.2 Versions couvertes

- **TOM²PRO client lourd Windows** — dernière version accessible sous licence. *Pas de version macOS native : le support annoncé passe par Parallels Desktop ou Boot Camp.*
- **TOM²PRO WEB** — avec **analyse comparative des écarts fonctionnels** par rapport au client lourd. **L'obtention d'un accès est le chemin critique du projet** (risque R2, §16).
- **Chronologie des versions** — reconstituée à partir des manuels, des notes de version et des marchés datés. Jalons connus : mention d'une « V2 » en 2021 `[SRC:forma:505]` ; marchés de migration vers la version web à partir de 2024-2025 `[SRC:marche:304]` `[SRC:marche:105]`.

### 4.3 Contextes de déploiement couverts

- **Mono-poste et multi-postes en réseau local.** Volumétries de référence observées : **10 accès simultanés** (Guinée, 2020) `[SRC:marche:101]` ; **16 clés utilisateur pour 10 financiers** répartis sur un siège et 4 régions (Haïti, 2013) `[SRC:integrateur:104]`. Dimensionnement des tests : **5, 10 et 25 utilisateurs simultanés**.
- **Multi-sites avec consolidation** — « mono-site, multisites centralisé ou décentralisé (avec des outils de consolidation) » `[SRC:editeur:003]`. Architecture type documentée : 4 sites décentralisés, consolidation au siège, transfert de données entre antennes et UGP `[SRC:integrateur:104]`.
- **Multi-projets** — déclinaisons « mono-projet ou multi-projets » et « biprojets » attestées par la grille tarifaire.
- **Multidevise** (FCFA, USD, EUR, MGA…) et **multi-bailleurs avec cofinancements ventilés**.
- **Référentiels comptables :**
  - **SYSCOHADA / AUDCIF** (entités à but lucratif) ;
  - **SYCEBNL** — obligatoire dans l'espace OHADA depuis le **1ᵉʳ janvier 2024** `[SRC:compta:407]`, avec registre des donateurs (art. 17) et bilan d'ouverture ;
  - **Plan comptable OHADA adapté aux projets et programmes de développement**, en **comptabilité de trésorerie avec opérations d'engagement occasionnelles** — configuration réellement observée en exploitation `[SRC:audit:201]` ;
  - **PCG 2005 (Madagascar)** — hors espace OHADA, pour les déploiements malgaches `[SRC:compta:409]` ;
  - plan comptable associatif / projet accepté par la Banque mondiale.

### 4.4 Hors périmètre

Fonctionnement interne des modules satellites (M12) ; postes de production de tiers ; systèmes d'information connexes du bénéficiaire ; audit de sécurité intrusif ; toute intervention sur une licence non détenue par la maîtrise d'ouvrage.

---

## 5. MÉTHODOLOGIE GÉNÉRALE ET PHASES

### 5.1 Approche

**Boîte noire complétée par boîte grise** : observation des comportements entrées/sorties et analyse des artefacts (fichiers de données, exports, sauvegardes), sans accès au code source. Toute étape touchant au code exécutable relève du régime 3 (§3.1) et est soumise à validation juridique préalable.

**Principes :**

- **Partir de l'état de l'art acquis, pas de zéro.** Le corpus de l'Annexe B établit déjà la nomenclature modulaire, la structure des plans, le mode de passation, la structure tarifaire et, à titre d'hypothèse forte, le SGBD. La phase 1 ne redécouvre pas ces éléments : elle les **confirme, date et étend**.
- **Traçabilité.** Chaque règle de gestion reconstituée porte une référence de preuve `[SRC:...]` (capture horodatée, spécimen de fichier, extrait de manuel, identifiant de test).
- **Reproductibilité.** Chaque observation doit pouvoir être rejouée par un tiers à partir du dossier de test.
- **Hypothèses balisées, avec gradation.**
  - `HYP-FORTE` — appuyée par une source primaire, mais à confirmer sur la version sous licence. *Exemple : « le SGBD est Microsoft SQL Server ».* Traitement : **test de confirmation en priorité 1**, pas investigation ouverte.
  - `HYP` — déduction non sourcée. Traitement : plan de vérification obligatoire.
  - `HYP-OUVERTE` — inconnue déclarée, sans point de départ. *Exemple : l'architecture de la version WEB.* Traitement : budget d'investigation dédié.
- **Itératif.** Cycles courts analyse → modélisation → test de validation → ajustement.
- **Contradictoire.** Tout constat défavorable au produit est daté, sourcé et accompagné de la nuance de sa source (voir §1.2 (b)).

### 5.2 Vue d'ensemble des phases

| Phase | Intitulé | Durée | Évolution vs v1.0 |
|-------|----------|-------|-------------------|
| **P0** | Cadrage, conformité juridique, **accès aux licences**, environnement, **TCO et décision *make-or-buy*** | **4 semaines** | +1 sem. — l'obtention des accès (desktop **et** WEB) est le chemin critique et n'était pas budgétée |
| **P1** | Analyse documentaire | **3 semaines** | −1 sem. — le corpus est déjà constitué (Annexe B) |
| **P2** | Rétro-ingénierie fonctionnelle (boîte noire) | **10 semaines** | inchangé |
| **P3** | Modèle de données | **5 semaines** | −1 sem. — le SGBD est en `HYP-FORTE`, à confirmer et non à découvrir |
| **P4** | Rétro-ingénierie technique (architecture, licence, formats) | **6 semaines** | inchangé — charge réallouée du SGBD desktop vers l'architecture WEB |
| **P5** | Règles métier bailleurs et reporting | **6 semaines** | inchangé |
| **P6** | Référentiel de tests de conformité **et chaîne d'extraction (OS7)** | **5 semaines** | +1 sem. — la stratégie de sortie devient un livrable exécutable |
| **P7** | Dossier d'architecture cible et restitution | **4 semaines** | inchangé |

**Durée totale indicative : 7 à 9 mois** avec les recouvrements.

### 5.3 Conditions suspensives

Deux conditions bloquent le démarrage de la phase 2 et doivent être levées en P0 :
1. **Pièce établissant l'accès licite** à une licence TOM²PRO détenue par la maîtrise d'ouvrage (contrat, facture ou attestation de l'intégrateur).
2. **Avis juridique écrit** sur le CLUF et la loi nationale applicable — à portée bloquante **uniquement pour les actes relevant du régime 3** (§3.4.1).

L'accès à une instance **TOM²PRO WEB** n'est pas une condition suspensive du projet entier, mais conditionne le périmètre de P2, P4 et le livrable D2.5. En cas d'échec, le repli du risque R2 (§16) s'applique et le périmètre est réduit formellement en COPIL.

---

## 6. PHASE 1 — ANALYSE DOCUMENTAIRE

### 6.1 Corpus de départ

**La phase 1 ne part pas d'une page blanche.** Le registre de l'[Annexe B](ANNEXE_B_REGISTRE_DES_SOURCES.md) recense 40 sources déjà localisées et lues, classées par fiabilité (`F1` primaire opposable, `F2` primaire de tiers qualifié, `F3` secondaire). La phase consiste à : **(i)** l'indexer formellement, **(ii)** obtenir les pièces manquantes du §B.7, **(iii)** en extraire la matrice des écarts.

**Catégories à compléter :**

1. **Manuels officiels** — manuel d'utilisation TOM²PRO WEB *(pagination à vérifier ; la mention « ≈ 650 pages » de la v1.0 n'est pas confirmée)*, manuel de formation TomPro desktop, guides d'installation et d'administration. **L'obtention de la documentation d'administration est prioritaire : elle confirme le SGBD et son mode d'exploitation.**
2. **Documents éditeur** — fiches produits, fiche Tom²Portail, page partenaires, FAQ, notes de version.
3. **Documents de marchés publics** — **sources privilégiées, car elles détaillent les spécifications exigées et les montants**. Pièces de référence : clarification UNOPS `RFQ/2020/14559` (liste des 10 modules), TDR Caritas Africa du 02/07/2025 (version WEB, TOM²GRH), marchés d'entente directe du Congo et du Tchad, marché de migration web de Madagascar. *(La v1.0 citait un « TDR GABAC de décembre 2025 » : aucun document de ce type n'a été retrouvé ; l'appel d'offres ERP du GABAC date de 2015 et ne mentionne pas TOMPRO. Référence retirée.)*
4. **Rapports d'audit publics** — audit de clôture PAZH Gabon (Delta Grant Thornton, exercice 2020), audit PDIL-II, rapports de supervision FIDA DEFIS Madagascar, rapport d'exécution CAFI Gabon. **Pièce à demander en priorité : la lettre de contrôle interne Delta Grant Thornton adressée au coordonnateur de l'UCP PAZH**, qui contient les recommandations détaillées sur le logiciel et n'est pas publiée.
5. **Directives des bailleurs** — *Disbursement Guidelines for Investment Project Financing* (Banque mondiale, février 2017), manuels de gestion financière, manuels de procédures des projets utilisateurs.
6. **Textes normatifs** — Acte uniforme SYCEBNL, AUDCIF/SYSCOHADA, PCG 2005 malgache, Accord de Bangui Annexe VII, Convention de Malabo.
7. **Offres de formation** des partenaires — les programmes détaillés valent plans de modules.

### 6.2 Productions attendues

- **D1.1 Registre documentaire** — base indexée (source, date, version logicielle couverte, **niveau de fiabilité F1/F2/F3**, extrait pertinent, identifiant `[SRC:...]`). *Amorcé par l'Annexe B.*
- **D1.2 Matrice fonctionnalités × sources** — chaque fonctionnalité connue rattachée à ses sources et à son niveau de preuve.
- **D1.3 Glossaire métier** aligné sur la terminologie officielle des bailleurs *(voir §10.1 pour les correspondances exactes)*.
- **D1.4 Carte des écarts** — ce qui est documenté / ce qui est `HYP-FORTE` / ce qui est `HYP-OUVERTE`. **Ce livrable pilote le plan de tests de la phase 2** et conditionne l'allocation de charge entre modules.
- **D1.5 Chronologie des versions** *(nouveau)* — reconstituée à partir des manuels, notes de version et marchés datés.

---

## 7. PHASE 2 — RÉTRO-INGÉNIERIE FONCTIONNELLE (BOÎTE NOIRE)

> **Fondement juridique :** régime 2 (directive 2009/24/CE art. 5 §3 ; L.122-6-1-III CPI) — droit d'observer, étudier et tester le fonctionnement du programme, sans autorisation du titulaire. Les résultats relèvent du régime 1 (*SAS c/ WPL*) : fonctionnalités et formats de données non protégés.

### 7.1 Environnement d'expérimentation

- Machines de test isolées (VM Windows), licence légale, **instantanés systématiques avant chaque campagne**.
- Instance TOM²PRO WEB de démonstration ou d'évaluation, si l'accès est obtenu en P0.
- **Jeu de données synthétiques de référence** — un projet fictif conçu pour exercer tous les cas transverses :
  - 3 conventions de financement, dont **1 cofinancement croisé à pourcentages paramétrés** ;
  - 2 monnaies de tenue + 1 devise de reporting ;
  - les 4 axes de gestion renseignés + 2 plans auxiliaires ;
  - 2 sites décentralisés + 1 siège consolidant ;
  - 3 exercices comptables, dont un clôturé et un rouvert ;
  - 1 marché avec avenant, décomptes, garantie et apurement d'engagement ;
  - 1 lot d'immobilisations cofinancées en pourcentage, avec cession en cours d'exercice ;
  - **aucune donnée à caractère personnel réelle**.
- Le jeu de référence est **versionné et figé** : il sert de base au critère de recette global (§12.2) et au référentiel de tests (D6.1).

### 7.2 Protocole d'expérimentation par module

Pour **chaque module M01 à M11bis** :

1. **Inventaire des écrans et menus** — arborescence complète des menus, formulaires, onglets, boutons et listes déroulantes, avec captures annotées et nommage normalisé (`M02_E014_saisie_ecriture.png`).
2. **Fiches de champs** — pour chaque formulaire : libellé, type, longueur, caractère obligatoire, valeur par défaut, contrôles de saisie, messages d'erreur. *Les contrôles et les messages d'erreur sont une source majeure d'information sur le modèle de données.*
3. **Règles de gestion** — chaque règle formalisée selon le modèle de l'Annexe D, avec le test qui la démontre. Exemple :
   `RG-M04-012 : une dépense ne peut être validée si le disponible budgétaire de l'axe est négatif — sauf si l'option de dépassement est activée [HYP]`
4. **Workflows et machines à états** — écriture : *saisie → validée → comptabilisée → clôturée* ; marché : *signé → en exécution → soldé* ; DRF : *préparée → soumise → justifiée → remboursée* ; etc.
5. **Tests aux limites** — bornes de dates d'exercice, montants négatifs, arrondis de conversion, dépassements budgétaires, exercices multiples, suppression ou modification après validation, comportement multi-utilisateur (verrous).
6. **Journal des expériences** — chaque test consigné : identifiant, données d'entrée, résultat observé, conclusion, preuve, **régime juridique de l'acte**.

### 7.3 Cas de test transverses obligatoires

| Réf. | Cas | Objet |
|------|-----|-------|
| **CT-01** | **Multidevise** | Saisie en devise, reporting en monnaie de tenue, écarts de change, règles d'arrondi, réévaluation |
| **CT-02** | **Multi-exercices** | À-nouveaux, clôture, réouverture, écritures d'inventaire, nombre d'exercices ouverts simultanément |
| **CT-03** | **Multi-sites** | Saisie décentralisée avec code site, **mécanisme de transfert antennes → UGP** `[HYP-FORTE]`, consolidation, gestion des conflits et des doublons |
| **CT-04** | **Cofinancement** | Ventilation automatique d'une dépense sur plusieurs conventions selon les pourcentages paramétrés ; comportement à l'arrondi ; impact sur les états bailleurs |
| **CT-05** | **Droits et traçabilité** | Matrice utilisateur × fonction (saisie, validation, administration) ; granularité de l'audit trail natif (« stockage de l'historique des manipulations » `[SRC:editeur:003]`) ; qui a saisi, validé, modifié |
| **CT-06** | **Reconstitution des états financiers** *(nouveau — test décisif)* | **Trancher la contradiction de l'audit PAZH** (§1.2 b) : la version sous licence produit-elle automatiquement le **TER**, le **tableau d'utilisation des fonds** et le **suivi budgétaire** ? Si oui, sous quelles conditions de paramétrage ? Si non, quel est exactement le reste à faire sous Excel ? **Ce test détermine à lui seul si le produit est défaillant ou si c'est son déploiement qui l'est.** |
| **CT-07** | **Complétude des exports** *(nouveau)* | Les exports natifs (Excel, CSV, sauvegarde) permettent-ils de **reconstituer l'intégralité** des référentiels, des écritures, des imputations analytiques, du paramétrage des états et des budgets ? Mesurer le **taux de reprise** par catégorie d'objet. **Ce test fonde ou infirme l'argument de verrouillage (§1.2 e) et conditionne OS7.** |
| **CT-08** | **Bascule trésorerie / engagement** *(nouveau)* | Le module M02 annonce une comptabilité « d'engagement **ou** de trésorerie » `[SRC:marche:101]`. Caractériser : paramètre global ou par journal ? réversible ? effet sur les états, le suivi budgétaire et les DRF ? **C'est le paramètre le plus structurant du produit, et la configuration réellement observée en exploitation** `[SRC:audit:201]`. |
| **CT-09** | **Conformité SYCEBNL** *(nouveau)* | Le paramétrage permet-il de produire les états du SYCEBNL en vigueur depuis le 01/01/2024, et de tenir le **registre des donateurs (art. 17)** ? Mesurer l'écart avec le référentiel. **L'éditeur ne revendiquant aucune conformité nommée, c'est un test et non une vérification.** |
| **CT-10** | **Licence et dimensionnement** *(nouveau)* | Caractériser le comportement aux limites de la licence : dépassement du nombre de clés utilisateur, ajout d'un site, ajout d'un projet, migration de poste. **Documente la mécanique économique du verrouillage (§1.2 d).** |
| **CT-11** | **Écarts desktop / WEB** *(nouveau)* | Comparer module par module les deux générations : fonctions présentes, absentes, modifiées ; compatibilité des données ; chemin de migration observé. *Conditionné à l'obtention d'un accès WEB.* |

### 7.4 Productions attendues

- **D2.1 Atlas fonctionnel** — cartographie complète écrans / processus, processus au format BPMN.
- **D2.2 Catalogue des règles de gestion** — toutes tracées et rattachées à un test. *Cible indicative : ≥ 300 règles. **Le critère de recette est la couverture, non le volume** : chaque écran et chaque cas transverse doit être couvert.*
- **D2.3 Journal des expériences** complet, avec régime juridique de chaque acte.
- **D2.4 Registre des zones d'ombre** — fonctions non comprises, comportements incohérents, anomalies observées.
- **D2.5 Rapport d'écart desktop / WEB** *(nouveau)* — ou, à défaut d'accès, note formelle de réduction de périmètre validée en COPIL.

---

## 8. PHASE 3 — RÉTRO-INGÉNIERIE DU MODÈLE DE DONNÉES

### 8.1 Méthode

**Point de départ : une hypothèse forte, pas une inconnue.**

> `HYP-FORTE-01` : **« TOM²PRO fonctionne en client/serveur sous SQL Serveur en environnement Windows »** `[SRC:integrateur:104:2013-09-16]`

Cette hypothèse est cohérente avec les prérequis Windows de l'éditeur et avec le module `Utilitaires` (« maintenance de la base de données, sauvegarde et restitution des bases de données ») `[SRC:marche:101]`. Elle date de 2013 et **ne vaut ni pour les versions récentes, ni pour la version WEB**.

**Conséquence méthodologique.** La phase 3 commence par un **test de confirmation** (quelques jours), et non par une campagne de découverte. Si l'hypothèse est confirmée, un **chemin d'extraction direct** s'ouvre — lecture du schéma par les vues système du SGBD, dans la limite des droits conférés par la licence et sous réserve de l'avis juridique — ce qui change radicalement l'économie de la phase et conditionne OS7.

**Étapes :**

1. **Confirmation du SGBD par observation licite** — fichiers présents après installation, services et processus, chaînes de connexion visibles dans l'interface d'administration, utilitaires de sauvegarde et de réparation, documentation d'administration. **Aucune ingénierie inverse du binaire sans validation juridique préalable (régime 3).**
2. **Analyse des artefacts** — structure des fichiers de sauvegarde, exports natifs les plus complets (grand livre, balance, exports Excel), fichiers d'import. En déduire les entités et leurs attributs.
3. **Modélisation par croisement** — chaque champ d'écran relevé en phase 2 est rattaché à une entité candidate ; les listes de choix révèlent les nomenclatures ; les codes et numéros automatiques révèlent les identifiants et les séquences ; les messages d'erreur révèlent les contraintes d'intégrité.
4. **Déduction du schéma relationnel** — MCD puis MLD en notation Merise ou UML, avec cardinalités.
5. **Validation par rejeu** — alimenter le modèle déduit avec le jeu de données de référence et vérifier qu'il reproduit les états de sortie observés en phase 2. **C'est le critère d'acceptation de la phase.**

### 8.2 Entités attendues (tronc commun à valider et enrichir)

- **Référentiels** — `Devise`, `TauxDeChange`, `ExerciceComptable`, `CompteGeneral`, `CompteAuxiliaire/Tiers`, `Journal`, `AxeGestion` (×4 : budgétaire, analytique, géographique, financement), `PlanAuxiliaire` (×4), `Bailleur`, `Convention`, `CategorieFinancement`, `SousCategorie`, `Site`, `Projet`, `Utilisateur`, `Profil`, `Droit`.
- **Flux** — `Ecriture` (entête / ligne), `SchemaEcriture`, `ImputationAnalytique`, `RapprochementBancaire`, `Lettrage`, `OrdrePaiement`, `ArreteCaisse`, `Echeance`.
- **Budget** — `Budget` (version), `LigneBudget`, `Reallocation`, `Engagement`, `ApurementEngagement`.
- **Marchés** — `Marche`, `Avenant`, `Decompte`, `Garantie`, `TypePassation`, `SchemaDecaissement`, `PieceJointe`.
- **Conventions** — `Convention`, `DemandeRetrait` (DRF), `PaiementDirect`, `Justification`, `CompteDesigne`, `ReconstitutionCompteDesigne`.
- **Patrimoine** — `Immobilisation`, `Affectation`, `Localisation`, `Amortissement`, `Cession`, `Inventaire`, `CleCofinancement`.
- **Pilotage** — `ModeleEtat`, `RubriqueEtat`, `FourchetteComptes`, `Formule`, `Ratio`, `TableauBord`.
- **Système** *(nouveau)* — `JournalAudit`, `Licence`, `CleUtilisateur`, `ParametreSysteme`, `TransfertInterSites`, `RegistreDonateurs` *(SYCEBNL art. 17)*.

### 8.3 Productions attendues

- **D3.1 Dictionnaire de données** exhaustif — entité, attribut, type, longueur, clé, nullabilité, règle de gestion associée, source de preuve.
- **D3.2 MCD / MLD** commenté, avec volumétrie estimée par table (ordres de grandeur constatés sur projets réels).
- **D3.3 Rapport de confirmation du SGBD** — moteur, version, mode fichier ou client-serveur, mécanisme de sauvegarde et de réparation, **et pour la version WEB : moteur, hébergement, mode d'accès**.
- **D3.4 Matrice données ↔ écrans ↔ états** — lignage complet de l'information (*data lineage*), condition de faisabilité de la phase 5.
- **D3.5 Modèle du paramétrage** *(nouveau)* — représentation des objets de configuration (plans, rubriques d'états, formules, schémas d'écritures, clés de répartition), **puisque c'est le paramétrage, et non les données, qui porte le verrouillage (§1.2 e)**.

---

## 9. PHASE 4 — RÉTRO-INGÉNIERIE TECHNIQUE (ARCHITECTURE, LICENCE, FORMATS)

### 9.1 Volet architecture

- **Topologies de déploiement** — mono-poste ; client-serveur en réseau local ; version WEB (serveur d'application, navigateurs supportés, hébergement) ; multi-sites.
- **Mécanisme de consolidation multi-sites.** `HYP-FORTE-02` : la consolidation repose sur un **transfert de données entre antennes et UGP**, et non sur une réplication native du SGBD `[SRC:integrateur:104]`. À confirmer : format du transfert, granularité, gestion des conflits et des doublons, réversibilité.
- **Couches logicielles déduites** — client, moteur de données, moteur d'états, utilitaires, **couche d'intégration Tom²Portail** (M11bis).
- **Mécanismes de licence et d'activation** — **observation fonctionnelle uniquement, sans aucun contournement**. Cible précise, déduite de la structure tarifaire `[SRC:integrateur:104]` : rechercher un mécanisme de **clés par utilisateur** (16 clés facturées à l'unité en 2013), en sus d'une clé produit, et des **verrous de périmètre** par nombre de projets et par topologie mono-site / multi-sites.
- **Gestion des droits et journalisation** — existence et granularité de l'audit trail natif.
- **Performances constatées** — temps de réponse aux volumétries de référence (10⁴, 10⁵, 10⁶ écritures) ; comportement à 5, 10 et 25 utilisateurs simultanés ; limites observées.

### 9.2 Volet formats et interfaces

> **Fondement juridique :** *SAS c/ WPL* — **les formats de fichiers de données ne sont pas protégés par le droit d'auteur** `[SRC:droit:403]`. Leur spécification et le développement de parseurs à partir de cette spécification ne sont pas des actes de contrefaçon.

Pour chaque format d'échange identifié :

- **Spécification tabulaire ou binaire** — encodage, séparateurs, en-têtes, ordre des colonnes, formats de dates et de montants, séparateur décimal, gestion des arrondis, valeurs nulles, jeux de caractères accentués.
- **Spécimens anonymisés** versés au dossier.
- **Parseurs de référence** (lecture et écriture) développés **à partir de la spécification**, jamais par décompilation.
- **Formats cibles** — exports Excel, CSV et PDF ; fichiers d'import de budgets, d'écritures et de **données historiques pré-formatées sous Excel** `[SRC:integrateur:104]` ; fichiers de sauvegarde ; fichiers de transfert inter-sites ; services ou API éventuels de la version WEB, documentés par **observation réseau en laboratoire instrumenté** (§15), si le CLUF et l'avis juridique le permettent.

### 9.3 Productions attendues

- **D4.1 Dossier d'architecture reconstituée** — diagrammes de déploiement et de composants, desktop **et** WEB.
- **D4.2 Catalogue des formats d'échange** — spécifications, spécimens, parseurs de référence exécutables.
- **D4.3 Rapport de sécurité** — authentification, gestion des sessions, chiffrement éventuel des données au repos et en transit, exposition réseau, hachage des mots de passe (par observation), vulnérabilités d'architecture. **Sans intrusion, sans test de pénétration, sans tentative de contournement.**
- **D4.4 Benchmark de performances** et limites de volumétrie.
- **D4.5 Note sur le modèle de licence** *(nouveau)* — mécanisme technique d'activation et de comptage, **et modèle économique associé** (§17.3). Alimente directement l'analyse coût-bénéfice OS8.

---

## 10. PHASE 5 — RÉTRO-INGÉNIERIE DES RÈGLES MÉTIER BAILLEURS

> C'est la valeur métier centrale du produit : sa bibliothèque de reporting bailleurs et le moteur d'états paramétrables qui la produit.

### 10.1 Terminologie de référence — correction obligatoire

La v1.0 employait le sigle **« IPFR », qui n'existe pas** dans la terminologie de la Banque mondiale. Les livrables de la phase 5 emploient exclusivement les termes suivants `[SRC:bailleur:410]` :

| Sigle | Français | Anglais | Définition |
|-------|----------|---------|------------|
| **IFR / RFI** | Rapport financier intermédiaire | *Interim Financial Report* | Rapport financier non audité prévu par l'accord de financement. **Dû au plus tard 45 jours après la fin de chaque trimestre civil** sous les conditions générales IDA. |
| **RSF** | Rapport de suivi financier | — | Terme employé par l'éditeur lui-même : « états RSF suivant le format bailleur (TER et tableau d'utilisation des fonds par activités) » `[SRC:marche:101]` |
| **SOE / ECD** | État certifié de dépenses | *Statement of Expenditure* | Récapitulatif des dépenses éligibles payées sur une période donnée |
| **TER** | Tableau des emplois et ressources | — | État financier central des projets de développement |
| **DRF** | Demande de retrait / de réapprovisionnement de fonds | *Withdrawal Application* | — |
| **Compte désigné** | — | *Designated Account* | Compte bancaire sur lequel le bailleur dépose les montants retirés |

Le *Summary Report* au sens des *Disbursement Guidelines* est **soit l'IFR, soit le SOE** — jamais les deux simultanément pour une même méthode de décaissement. Cette distinction structure la spécification des gabarits.

### 10.2 Travaux

1. **Inventaire des gabarits** présents dans le logiciel, bailleur par bailleur (Banque mondiale, BAD, UE, FIDA, Fonds mondial, BID, PNUD) : IFR/RSF, ECD/SOE, tableaux d'utilisation des fonds par activités, TER, relevés et états de reconstitution des comptes désignés, états de rapprochement, prévisionnels de trésorerie, mémoires de justification des dépenses, demandes de paiement direct.
2. **Spécification de chaque gabarit** — structure (zones, lignes, colonnes), **formules d'alimentation cellule par cellule** (quelles entités, quels axes, quelles fourchettes de comptes alimentent chaque cellule), règles d'arrondi et de conversion, périodicité, monnaie de sortie. *Ce travail dépend directement du livrable D3.4 (lignage).*
3. **Rapprochement avec les directives officielles** en vigueur — *Disbursement Guidelines* de la Banque mondiale, manuels de gestion financière des bailleurs — et **mesure de l'écart, datée**.
4. **Mécanisme de mise à jour** — comment les formats évoluent : correctifs de l'éditeur, paramétrage utilisateur des rubriques. **La paramétrabilité des rubriques d'états par fourchettes de comptes et par formules est la fonctionnalité clé à reconstituer intégralement** : c'est elle qui porte la valeur du produit et, simultanément, le verrouillage.
5. **Chaîne de production et de validation** du reporting — matérialisation dans le système du circuit d'élaboration, de contrôle et de validation avant transmission au bailleur.
6. **Évaluation de la conformité SYCEBNL** *(nouveau)* — capacité du moteur d'états à produire les états du référentiel en vigueur depuis le 01/01/2024 et à tenir le registre des donateurs (art. 17). **À traiter comme une évaluation, non comme une vérification : l'éditeur ne revendique aucune conformité nommée** `[SRC:editeur:001]`.

### 10.3 Productions attendues

- **D5.1 Référentiel des gabarits bailleurs** — ≥ 6 bailleurs, ≥ 30 gabarits, chacun avec sa structure et ses formules d'alimentation.
- **D5.2 Matrice de conformité** gabarits logiciel × directives bailleurs, avec écarts datés et sourcés.
- **D5.3 Spécification du moteur d'états paramétrables** — rubriques, fourchettes de comptes, formules, sous-totaux, contrôles de cohérence. **Livrable le plus critique du projet au regard de l'option (a).**
- **D5.4 Évaluation de conformité SYSCOHADA / SYCEBNL / PCG 2005** *(nouveau)* — avec plan de remédiation par paramétrage.

---

## 11. SPÉCIFICATIONS NON FONCTIONNELLES À RECONSTITUER

| Réf. | Exigence | Détail à documenter | Base de départ établie |
|------|----------|---------------------|------------------------|
| **NF01** | Multilingue | Langues disponibles, double libellé sur référentiels et états, langue d'exploitation, implémentation de langues additionnelles | Éditeur : « français, anglais, **portugais**, autres langues facilement implémentées » `[SRC:editeur:003]` — plus large que le bilingue annoncé en v1.0 |
| **NF02** | Multidevise | Nombre de devises, tables de taux, règles de conversion et d'arrondi, réévaluation, monnaie de tenue vs monnaie de reporting | Multidevises confirmé `[SRC:editeur:001]` |
| **NF03** | Multi-exercices | Nombre d'exercices ouverts simultanément, règles de clôture et d'à-nouveaux, réouverture | Multi-exercices confirmé `[SRC:editeur:001]` |
| **NF04** | Volumétrie | Capacités maximales (écritures, tiers, comptes, marchés, immobilisations), points de dégradation | À établir |
| **NF05** | Concurrence | Utilisateurs simultanés, verrouillage, gestion des conflits | **10 accès simultanés** `[SRC:marche:101]` ; **16 clés / 10 financiers sur 5 sites** `[SRC:integrateur:104]`. Tester à 5, 10, 25 |
| **NF06** | Sauvegarde et restitution | Fréquences, granularité, restauration, **réparation de base corrompue** | Module `Utilitaires` : « sauvegarde et restitution des bases de données » `[SRC:marche:101]` |
| **NF07** | Sécurité | Authentification, profils, audit trail, hachage des mots de passe (observation), chiffrement | Éditeur : « accès personnalisé (login et mot de passe) », « stockage de l'historique des manipulations » `[SRC:editeur:003]` |
| **NF08** | Portabilité | OS supportés, prérequis, navigateurs (version WEB), mobilité | « Windows 10, 8, 7, Vista, XP », « CPU Intel ou AMD et 4 Go de RAM » ; **macOS uniquement via Parallels Desktop / Boot Camp** `[SRC:editeur:001]` |
| **NF09** | Ergonomie | Arborescence, raccourcis, aides en ligne, cohérence IHM (grille d'évaluation) | À établir |
| **NF10** | Maintenabilité | Mécanisme de correctifs, numérotation des versions, **rétrocompatibilité des données** | Module `Utilitaires` : « mise à jour du système » `[SRC:marche:101]` ; éditeur : « mise à jour systématique », « implémentation de nouveaux modules » `[SRC:editeur:003]` |
| **NF11** | **Modularité du périmètre de licence** *(nouveau)* | Déclinaisons light / complète / spécialisée ; mono/multi-postes ; mono-site / multisites centralisé ou décentralisé ; mono/multi-projets. **Quelles fonctions sont désactivées dans chaque déclinaison ?** | `[SRC:editeur:003]` — **détermine la portée réelle du constat d'audit PAZH (§1.2 b)** |
| **NF12** | **Dépendance au réseau de distribution** *(nouveau)* | Opérations réservées à l'intégrateur agréé : paramétrage initial, correctifs, réparation de base, migration de version. Documenter ce qu'un client ne peut pas faire seul. | Distribution exclusivement indirecte, certification annuelle `[SRC:editeur:006]` |

---

## 12. LIVRABLES ET CRITÈRES D'ACCEPTATION

### 12.1 Tableau des livrables

| Réf. | Livrable | Phase | Format | Critère d'acceptation |
|------|----------|-------|--------|----------------------|
| **D0.1** | Note de cadrage + avis juridique | P0 | PDF | Validée par le COPIL et le conseil juridique ; **régimes 1/2/3 explicitement qualifiés** |
| **D0.2** | **Preuve d'accès licite** aux licences desktop et WEB | P0 | PDF | **Condition suspensive de P2** |
| **D0.3** | **Modèle de TCO et dossier *make-or-buy*** *(OS8)* | P0 | Tableur + PDF | Chiffré à partir de pièces de marché opposables ; **validé en J0** |
| **D1.1→D1.5** | Corpus documentaire, matrices, glossaire, chronologie | P1 | Base + PDF | 100 % des sources connues indexées et **cotées F1/F2/F3** |
| **D2.1→D2.5** | Atlas fonctionnel, règles de gestion, journaux, écarts WEB | P2 | PDF / BPMN | Revue croisée par 2 experts SIGF ; **100 % des règles tracées à un test** ; **tous les cas transverses CT-01 à CT-11 exécutés** |
| **D3.1→D3.5** | Dictionnaire, MCD/MLD, SGBD, lignage, modèle de paramétrage | P3 | PDF / outil de modélisation | **Rejeu validé** sur le jeu de données de référence |
| **D4.1→D4.5** | Architecture, formats, sécurité, benchmark, licence | P4 | PDF + scripts | **Parseurs de référence fonctionnels** sur les spécimens |
| **D5.1→D5.4** | Gabarits bailleurs, conformité, moteur d'états, SYCEBNL | P5 | PDF + gabarits | ≥ 30 gabarits spécifiés **avec formules d'alimentation** ; terminologie IFR/RSF/SOE/DRF conforme |
| **D6.1** | Référentiel de tests de conformité | P6 | Outil de test | ≥ 50 cas exécutables, résultats attendus définis |
| **D6.2** | **Chaîne d'extraction et stratégie de sortie** *(OS7)* | P6 | Code + documentation | **Exécutée de bout en bout** sur le jeu de référence ; taux de reprise ≥ 99 % des écritures, 100 % des référentiels |
| **D7.1** | Dossier d'architecture cible *(si option (a))* | P7 | PDF | Validation COPIL |
| **D7.2** | Rapport final + restitution | P7 | PDF + séminaire | Présentation et levée des réserves |

### 12.2 Processus de recette

- Revue interne MOE → recette MOA par lots → commission de validation finale.
- Tout livrable non conforme fait l'objet d'une fiche d'anomalie ; re-livraison sous 15 jours.
- **Règle de traçabilité :** un livrable comportant une affirmation non référencée `[SRC:...]` et non marquée `[HYP]` est rejeté en recette.

> **Critère global de sortie — rejeu réussi.** *Un tiers ne connaissant pas TOM²PRO doit pouvoir, à partir des seuls livrables, spécifier une application reproduisant les états de sortie sur le jeu de données de référence.*
>
> **Ce critère est conservé tel quel : c'est le meilleur élément de la version 1.0.** Il est complété par un second critère, opérationnel :
>
> **Critère de sortie complémentaire — extraction réussie.** *À partir des seuls livrables D4.2 et D6.2, un tiers doit pouvoir extraire une base TOM²PRO vers le format pivot documenté, sans recours à l'éditeur ni à un intégrateur agréé.*

---

## 13. PLANNING, JALONS ET CHARGES ESTIMÉES

### 13.1 Jalons

| Jalon | Contenu | Échéance |
|-------|---------|----------|
| **J0** | Validation du cadrage, feu vert juridique, **preuve d'accès licite**, **décision *make-or-buy* sur dossier chiffré** | Fin P0 |
| **J1** | Corpus documentaire validé et coté | Fin P1 |
| **J2** | Atlas fonctionnel à 50 % (M01–M05) | Mi-P2 |
| **J3** | Atlas fonctionnel complet + catalogue des règles de gestion + **CT-06 et CT-07 tranchés** | Fin P2 |
| **J4** | Modèle de données validé par rejeu | Fin P3 |
| **J5** | Dossier technique (architecture, formats, licence) | Fin P4 |
| **J6** | Référentiel bailleurs validé, **conformité SYCEBNL évaluée** | Fin P5 |
| **J6bis** | **Chaîne d'extraction démontrée** *(OS7)* | Fin P6 |
| **J7** | Recette globale et clôture | Fin P7 |

### 13.2 Charges indicatives (jours-homme)

| Profil | P0 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | Total |
|--------|----|----|----|----|----|----|----|----|-------|
| Chef de projet / expert SIGF | 7 | 6 | 20 | 10 | 6 | 10 | 8 | 12 | **79** |
| Analyste fonctionnel senior | 4 | 9 | 40 | 15 | 4 | 20 | 15 | 8 | **115** |
| Analyste fonctionnel | — | 6 | 40 | 15 | 4 | 15 | 20 | 4 | **104** |
| Ingénieur données / DBA | 2 | 2 | 5 | **18** | **22** | 5 | **12** | 4 | **70** |
| Ingénieur systèmes / sécurité | 3 | — | 2 | — | 25 | — | 5 | 4 | **39** |
| Conseil juridique | 6 | 2 | 2 | 2 | 3 | 1 | — | 2 | **18** |
| Expert bailleurs | — | 3 | 5 | — | — | 20 | 5 | 5 | **38** |
| **Total par phase** | **22** | **28** | **114** | **60** | **64** | **71** | **65** | **39** | **463** |

**Charge totale indicative : ≈ 463 jours-homme**, à ajuster après P0.

**Évolutions par rapport à la v1.0 (460 JH) — à charge quasi constante, l'allocation change :**

| Poste | Variation | Motif |
|---|---|---|
| Conseil juridique | **−4 JH** | Les régimes 1 et 2 (§3.1) couvrent l'essentiel du projet ; l'avis bloquant se limite au régime 3 |
| Chef de projet en P0 | **+2 JH** | Obtention des accès et pilotage de la décision *make-or-buy* |
| Ingénieur données en P3 | **−7 JH** | Le SGBD est en `HYP-FORTE` : confirmation, non découverte |
| Ingénieur données en P4 et P6 | **+9 JH** | Réallocation vers l'architecture WEB (inconnue) et la chaîne d'extraction (OS7) |
| Analystes en P1 | **−5 JH** | Corpus déjà constitué (Annexe B) |
| Ingénieur systèmes en P2 | **+2 JH** | Cas transverses CT-10 (licence) et CT-11 (écarts WEB) |

> **Trois charges ne figuraient pas à la v1.0 et sont désormais budgétées :** l'obtention des licences desktop **et** WEB (P0), la chaîne d'extraction exécutable (P6, OS7), et le modèle de TCO (P0, OS8).

---

## 14. ÉQUIPE PROJET ET COMPÉTENCES REQUISES

- **Chef de projet / expert SIGF** — ≥ 10 ans sur les systèmes de gestion financière de projets de développement ; maîtrise des cycles Banque mondiale (décaissements, IFR, SOE, comptes désignés) et BAD ; expérience de rétro-spécification.
- **Analystes fonctionnels** — comptabilité **SYSCOHADA**, **SYCEBNL** et **PCG 2005** ; comptabilité analytique et budgétaire des projets ; **maîtrise de la distinction comptabilité de trésorerie / d'engagement** (CT-08). Une pratique de TOM²PRO est appréciée — **sous réserve de vérification d'une éventuelle clause de non-concurrence ou d'un engagement de confidentialité lié à la certification TechExpert** `[SRC:editeur:006]`.
- **Ingénieur données** — modélisation Merise/UML ; **administration et investigation SQL Server** (compte tenu de `HYP-FORTE-01`) ; forensique de bases de données en environnement légal ; parsing de formats ; développement de chaînes d'extraction (OS7).
- **Ingénieur systèmes / sécurité** — audit d'architecture Windows et serveur ; **observation réseau en laboratoire instrumenté** ; analyse de mécanismes de licence **sans contournement**.
- **Expert bailleurs** — pratique des manuels de gestion financière et des formats de reporting (Banque mondiale, BAD, UE, FIDA, Fonds mondial, BID, PNUD) ; maîtrise de la terminologie officielle (§10.1).
- **Conseil juridique** — propriété intellectuelle du logiciel ; **jurisprudence de la CJUE sur les programmes d'ordinateur** (*SAS c/ WPL*, *Top System*) ; **droit OAPI et droit national des pays concernés** ; contrats de licence ; protection des données (Convention de Malabo et lois nationales).

**Gouvernance.** COPIL mensuel : maîtrise d'ouvrage, maîtrise d'œuvre, conseil juridique, représentant des utilisateurs, et — conformément au principe de transparence du §3.6 — **observateur bailleur lorsque la démarche vise la pérennité des données de projets financés**.

---

## 15. ENVIRONNEMENT DE TRAVAIL ET MOYENS

**Correction d'une incohérence de la v1.0 :** le §15 de la version 1.0 imposait des VM « sans sortie Internet », tandis que son §9.2 prévoyait l'observation réseau des services de la version WEB — ce qui suppose un serveur d'application joignable. Les deux environnements sont désormais distincts :

| Environnement | Configuration | Usage |
|---|---|---|
| **Poste d'analyse hors ligne** | VM Windows isolée, **sans aucune connectivité**, instantanés quotidiens, chiffrement au repos | Analyse du client lourd, manipulation de spécimens, travail sur données sensibles |
| **Laboratoire instrumenté** | Segment réseau dédié, **isolé d'Internet mais interconnecté** : serveur d'application WEB, client, proxy d'inspection TLS **sur matériel de test uniquement**, capture de trafic | Observation des échanges de la version WEB, tests multi-utilisateurs, tests multi-sites |
| **VM Linux d'analyse** | Outils de parsing, de modélisation et de rejeu | Développement des parseurs et de la chaîne d'extraction (D4.2, D6.2) |

**Moyens :**
- **Licences légales TOM²PRO** — desktop **et** WEB, contrats vérifiés, périmètre documenté (nombre de clés, de sites, de projets — voir NF11).
- **Outillage** — outil de modélisation (type EA ou drawio) ; gestionnaire d'exigences ou référentiel de règles ; **wiki documentaire versionné (Git)** ; outil BPMN ; banc d'essai automatisé ; outil de capture et d'annotation d'écrans avec horodatage.
- **Données** — jeux synthétiques par défaut ; extraction anonymisée d'une base réelle seulement si un projet y consent par écrit, après anonymisation irréversible et inscription au registre de traitement (§3.5).
- **Destruction** — tous les instantanés, spécimens et extractions sont détruits à la clôture, destruction attestée au dossier.

---

## 16. GESTION DES RISQUES

| Réf. | Risque | Prob. | Impact | Mitigation |
|------|--------|-------|--------|------------|
| **R1** | Contestation juridique par l'éditeur | **Faible** *(révisée à la baisse)* | Élevé | **Qualification explicite des régimes 1/2/3 (§3.1)** : l'essentiel du projet ne relève pas de l'exception de décompilation. Avis juridique préalable, journal de conformité par acte, salle blanche restreinte au régime 3, aucun contournement de protection, aucune diffusion d'éléments protégés |
| **R2** | **Accès impossible à une licence WEB** | Moyenne | **Élevé** *(révisée à la hausse)* | **Chemin critique.** Engager la négociation dès la semaine 1 de P0, en parallèle avec plusieurs intégrateurs agréés. Replis : (i) accès de démonstration temporaire ; (ii) partenariat avec une organisation déjà titulaire d'une licence WEB ; (iii) analyse documentaire du manuel WEB ; (iv) **réduction formelle du périmètre validée en COPIL**, livrable D2.5 requalifié en note d'écart |
| **R3** | Formats propriétaires opaques ou chiffrés | Moyenne *(révisée à la baisse)* | Moyen | Les exports Excel/CSV sont documentés par l'éditeur `[SRC:marche:101]` `[SRC:integrateur:104]`. Le cas échéant, basculer sur la spécification entrées/sorties en boîte noire. **Ne jamais casser un chiffrement.** |
| **R4** | Obsolescence des gabarits bailleurs pendant l'étude | Moyenne | Faible | Veille sur les directives ; matrice de conformité **datée** ; spécification du moteur d'états plutôt que des seuls gabarits |
| **R5** | Turnover d'experts rares | Moyenne | Élevé | Documentation continue, binômage, capitalisation dans le wiki versionné |
| **R6** | Dérive de périmètre vers les modules satellites | Élevée | Moyen | Périmètre **M01–M11bis verrouillé** ; M12 en cartographie d'interopérabilité seule |
| **R7** | Découverte de données personnelles dans les spécimens | Faible | Élevé | Jeux synthétiques par défaut ; procédure d'anonymisation ; registre de traitement ; purge documentée et attestée |
| **R8** | **Clause de non-concurrence ou de confidentialité d'un analyste certifié TechExpert** *(nouveau)* | Moyenne | Moyen | Vérification contractuelle **avant recrutement** ; à défaut, recourir à des analystes sans historique chez l'éditeur, au prix d'une courbe d'apprentissage |
| **R9** | **Le périmètre de licence détenue ne couvre pas les fonctions à analyser** *(nouveau)* | **Élevée** | Moyen | Risque directement établi par l'audit PAZH, qui impute la défaillance à « la version acquise par le Projet » `[SRC:audit:201]`. **Documenter le périmètre exact de la licence en P0 (NF11)** et distinguer systématiquement, dans tous les livrables, « fonction absente du produit » et « fonction absente de la licence » |
| **R10** | **Évolution réglementaire en cours d'étude (SYCEBNL)** *(nouveau)* | Moyenne | Moyen | Le SYCEBNL est en vigueur depuis le 01/01/2024 mais ses dispositions pénales ne sont pas transposées uniformément. Dater toute évaluation de conformité et suivre les transpositions nationales |
| **R11** | **Divergence entre documentation de l'éditeur et réalité du produit** *(nouveau)* | **Élevée** | Moyen | Avérée : le site n'évoque ni la version WEB, ni le SGBD, ni TOM²GRH, alors que les trois existent. **Ne jamais fonder un livrable sur la seule documentation de l'éditeur** ; exiger une double source (`F1` + test) pour toute affirmation structurante |

---

## 17. BUDGET ET ANALYSE COÛT-BÉNÉFICE

### 17.1 Postes de dépense

| Poste | Estimation |
|-------|-----------|
| Prestations (≈ 463 JH, taux selon profils et zone) | à chiffrer selon appel d'offres |
| **Licences de test TOM²PRO desktop + WEB** — poste à part entière, chemin critique (R2) | à chiffrer (voir §17.2) |
| Outils de modélisation, de test et d'infrastructure | faible |
| Conseil juridique (18 JH) | à chiffrer |
| Infrastructures de test (VM, laboratoire instrumenté) | faible |
| Formation et séminaire de restitution | forfait |
| **Provision pour aléas (15 %)** | recommandée |

### 17.2 Repères de prix vérifiables

*La version 1.0 citait « ≈ 84 millions MGA (≈ 17–19 kUSD) » pour une « licence nationale ». **Ce montant n'a pas pu être retrouvé en source ouverte et est retiré.*** Il est remplacé par des points de prix issus de pièces de marché publiques et identifiables :

| Contexte | Objet | Montant |
|---|---|---|
| **Haïti, 2013** — proposition d'intégrateur, FIDA `[SRC:integrateur:104]` | Licence TOM²PRO *biprojets, multi-sites, multi-utilisateurs* (siège) | **10 000 € HT** |
| idem | Licences TOM²PRO *biprojets, mono-site* (4 régions) | **4 × 1 000 € HT** |
| idem | **Clés utilisateur** | **16 × 200 € HT = 3 200 €** |
| idem | Sous-total logiciels (avec TOMMONITORING, remise éditeur 10 % déduite) | **25 700 € HT** |
| idem | Maintenance sur 3 ans | **15 % = 3 855 €** |
| idem | Paramétrage et formation (60 J/H à 650 €/j) | **39 000 € HT** |
| **Gabon, PAZH** `[SRC:audit:201]` | TOMPRO immobilisé au bilan | **19 577 288 FCFA** |
| **Congo, PATN (BM), 2023** `[SRC:marche:301]` | Entente directe TOMATE : acquisition + installation + paramétrage + formation + assistance + maintenance | **20 308 193 FCFA** |
| **Congo** `[SRC:marche:302]` | Entente directe TOMATE : fourniture + installation + mise en réseau | **10 745 447 FCFA** |
| **Madagascar (BM)** `[SRC:marche:304]` | **Migration vers la version WEB**, sélection directe SOFTWELL CONSULTING | **27 556 USD** |

### 17.3 Structure du coût de possession

La décomposition haïtienne révèle un modèle tarifaire **multiplicatif** :

```
Coût licence  =  f( nombre de projets )
               × f( topologie : mono-site / multi-sites )
               × f( nombre de clés utilisateur )
               + maintenance (pourcentage du sous-total logiciels)
```

avec un **rapport 10:1** entre la licence siège multi-sites (10 000 €) et la licence régionale mono-site (1 000 €), et des **clés utilisateur facturées à l'unité** (200 €).

**Implication centrale pour la décision :** le coût croît avec **la décentralisation et l'effectif** de l'organisation. C'est l'argument économique le plus solide du dossier, et il n'apparaissait pas dans la version 1.0.

**Sur le ratio de TCO.** L'affirmation de la v1.0 — « le coût total de possession sur 5 ans est typiquement de 3 à 5 fois la licence » — **n'est pas démontrée**. Elle est toutefois **plausible et vraisemblablement minorée** : dans le seul cas entièrement documenté, les prestations de mise en place (39 000 €) représentent déjà **1,5 fois** le coût des logiciels (25 700 €), **avant** toute maintenance, migration de version ou formation ultérieure. Formulation retenue : *« au moins 2,5 fois le coût des logiciels dès la première année dans le seul cas publiquement documenté »*.

### 17.4 Analyse coût-bénéfice — livrable D0.3, dû à J0

Le modèle de TCO à 5 ans compare trois scénarios, sur la base des pièces du §17.2 :

| Scénario | Coûts à modéliser |
|---|---|
| **S1 — Statu quo** | Licences + clés additionnelles liées à la croissance + maintenance annuelle + paramétrages successifs + migrations de version + formations + **coût du travail manuel résiduel** (reconstitution des états sous Excel, constaté au Gabon `[SRC:audit:201]`) + **coût du risque de non-conformité SYCEBNL** |
| **S2 — Migration vers la version WEB** | Coût de migration (repère : 27 556 USD `[SRC:marche:304]`) + licences WEB + reprise des données + formation + maintenance |
| **S3 — Remplacement** | Coût du présent projet (≈ 463 JH) + développement ou acquisition d'une solution cible + reprise des données (OS7) + conduite du changement + exploitation |

**Le dossier D0.3 est la pièce qui fonde la décision du COPIL en J0.** Sans lui, le projet n'a pas d'objectif chiffré — c'est la principale lacune de la version 1.0.

---

## 18. ANNEXES

### Annexe A — Rapport de vérification factuelle de la v1.0
Document séparé : [`ANNEXE_A_VERIFICATION_FACTUELLE.md`](ANNEXE_A_VERIFICATION_FACTUELLE.md)

### Annexe B — Registre documentaire et pièces à obtenir
Document séparé : [`ANNEXE_B_REGISTRE_DES_SOURCES.md`](ANNEXE_B_REGISTRE_DES_SOURCES.md)

### Annexe C — Glossaire

**Bailleur** · **Catégorie de dépense** · **Compte désigné** (*Designated Account*) · **Convention de financement** · **Décaissement** · **DRF** (demande de retrait / de réapprovisionnement de fonds) · **ECD / SOE** (état certifié de dépenses / *Statement of Expenditure*) · **Engagement** · **IFR / RFI** (rapport financier intermédiaire / *Interim Financial Report*) · **Imputation analytique** · **Lettrage** · **Plan de gestion** (axe d'analyse) · **Plan auxiliaire** · **RSF** (rapport de suivi financier) · **SYCEBNL** (Système comptable des entités à but non lucratif, OHADA, en vigueur le 01/01/2024) · **SYSCOHADA / AUDCIF** · **PCG 2005** (Madagascar) · **TER** (tableau des emplois et ressources) · **UCP / UGP** (unité de coordination / de gestion de projet) · **OAPI** (Organisation africaine de la propriété intellectuelle) · **Convention de Malabo**

> *Terme proscrit : **« IPFR »**, employé dans la version 1.0 — il n'existe dans la terminologie d'aucun bailleur. Voir §10.1.*

### Annexe D — Modèle de fiche de règle de gestion

```
ID            : RG-Mxx-nnn
Module/Écran  :
Énoncé        :
Entrées test  :
Résultat obs. :
Statut        : [ Démontrée | HYP-FORTE | HYP | HYP-OUVERTE | Contredite ]
Régime jur.   : [ 1 — non protégé | 2 — observation licite | 3 — décompilation ]
Preuve        : [SRC:type:id:date]
Date / Auteur :
```

### Annexe E — Norme de citation

```
[SRC:<type>:<id>:<date>]

type ∈ { editeur | marche | integrateur | audit | superv | projet |
         droit | compta | bailleur | forma | presse | profil | integr |
         ecran | test | fichier }
```

Toute affirmation du dossier final porte au moins une référence `[SRC:...]`. Toute affirmation non démontrée est marquée `[HYP]`, `[HYP-FORTE]` ou `[HYP-OUVERTE]` et assortie d'un plan de vérification. **Un livrable comportant une affirmation ni référencée ni marquée est rejeté en recette.**

### Annexe F — Grille de conformité clean room

Check-list de séparation entre équipe d'analyse, équipe de spécification cible et équipe de développement, **applicable aux seuls livrables issus d'actes relevant du régime 3** (§3.1 et §3.4.3) : habilitations, flux documentaires autorisés, interdictions, journal des transmissions.

> **Rappel :** les spécifications fonctionnelles issues de l'observation licite (régimes 1 et 2) ne portent pas d'éléments protégés au sens de *SAS Institute c/ World Programming* et **peuvent être transmises directement à l'équipe de développement**, sans passage par la salle blanche.

### Annexe G — Hypothèses fortes ouvertes au démarrage

| Réf. | Hypothèse | Source | Vérification |
|---|---|---|---|
| `HYP-FORTE-01` | Le SGBD est **Microsoft SQL Server**, en client/serveur sous Windows | `[SRC:integrateur:104:2013-09-16]` | P3, test de confirmation en priorité 1. **Ne vaut ni pour les versions récentes, ni pour la version WEB.** |
| `HYP-FORTE-02` | La consolidation multi-sites repose sur un **transfert de données entre antennes et UGP**, non sur une réplication SGBD | `[SRC:integrateur:104]` | P4, CT-03 |
| `HYP-FORTE-03` | La licence est dimensionnée par **projets × topologie × clés utilisateur** | `[SRC:integrateur:104]` | P4, CT-10 |
| `HYP-FORTE-04` | Les exports natifs couvrent les **rapports** mais pas nécessairement le **paramétrage** | `[SRC:marche:101]` `[SRC:integrateur:104]` | P2, CT-07 — **conditionne OS7** |
| `HYP-OUVERTE-01` | Architecture de la version WEB : serveur d'application, SGBD, mode d'hébergement, services exposés | aucune | P4, conditionnée à l'accès (R2) |
| `HYP-OUVERTE-02` | Technologie de développement (atelier, langage, framework) | aucune | P4, observation uniquement |

---

*Fin du cahier des charges — version 2.0. Toute modification ultérieure fait l'objet d'un avenant versionné validé en COPIL.*

*Les affirmations factuelles de ce document sont sourcées selon la norme de l'Annexe E. Le détail des vérifications, y compris des corrections apportées à la version 1.0, figure en [Annexe A](ANNEXE_A_VERIFICATION_FACTUELLE.md). Les sources elles-mêmes sont recensées en [Annexe B](ANNEXE_B_REGISTRE_DES_SOURCES.md), avec leur niveau de fiabilité et les pièces restant à obtenir.*
