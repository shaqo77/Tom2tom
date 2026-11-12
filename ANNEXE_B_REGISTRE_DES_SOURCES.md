# ANNEXE B — REGISTRE DOCUMENTAIRE INITIAL (amorce du livrable D1.1)

**Objet :** corpus de sources primaires et secondaires effectivement localisées et lues au 12 novembre 2026, indexées selon la norme de citation `[SRC:type:id:date]` de l'Annexe E.
**Statut :** ce registre n'est pas un point de départ théorique — c'est le résultat d'une collecte réelle. Il constitue le socle du livrable **D1.1** et permet d'ouvrir la phase 1 avec un corpus déjà constitué plutôt qu'une page blanche.

**Échelle de fiabilité :**
- `F1` — Source primaire émanant de l'éditeur, d'un intégrateur agréé, ou d'un bailleur dans un acte contractuel. Opposable.
- `F2` — Source primaire d'un tiers qualifié (auditeur, acheteur public) décrivant le produit. Fiable, à dater.
- `F3` — Source secondaire (presse, agrégateur, site de formation). Indicative, à recouper.

---

## B.1 — Sources éditeur (TOMATE)

| ID | Type | Intitulé / contenu utile | Date | Fiab. | URL |
|----|------|--------------------------|------|-------|-----|
| `SRC:editeur:001` | Fiche produit | **Fiche Tom²Pro** — les 9 blocs fonctionnels commerciaux ; « jusqu'à quatre plans de gestion » ; « jusqu'à quatre plans auxiliaires » ; codification des sources de fonds ; cofinancements ; multidevises ; double libellé ; prérequis Windows/macOS | consultée 11/2026 | F1 | https://www.tomate.com/logiciels/tom2-pro_1 |
| `SRC:editeur:002` | Catalogue | **Gamme publiée** — 7 logiciels : Tom²Pro, Tom²Paie, Tom²EtatsFin, Tom²Monitoring, Tom²Projet, Tom²Marché, Tom²Stock | consultée 11/2026 | F1 | https://www.tomate.com/logiciels |
| `SRC:editeur:003` | Fiche plateforme | **Tom²Portail** — « plateforme commune » ; versions light/complète/spécialisée ; mono/multi-postes ; mono-site, multisites centralisé ou décentralisé « avec des outils de consolidation » ; mono/multi-projets ; multilingue FR/EN/PT ; traçabilité : « stockage de l'historique des manipulations » | consultée 11/2026 | F1 | https://www.tomate.com/solutions/suite-logicielle/tomportail |
| `SRC:editeur:004` | Présentation | **À propos** — « plus de 25 années d'expérience » ; « plus de 2 000 installations dans 40 pays » ; « plus de 50 partenaires agréés » ; bailleurs revendiqués : Banque mondiale, UE, BAD, PNUD, FIDA, Global Funds, BID | consultée 11/2026 | F1 | https://www.tomate.com/tomate |
| `SRC:editeur:005` | Annuaire | **Partenaires agréés** — « Distributeur agréé et TechExpert Certifié ». Identifiés : 2DBC (SN, depuis 2004), ACECA International (BF, 1991), AGOSOFT (CI, 1999), AE2C (ML, 2009), ACW (TN), AZ Consulting (SN, 2009), CE.S.I (NE), CIFOPE Afrique (ML) | consultée 11/2026 | F1 | https://www.tomate.com/partenaires |
| `SRC:editeur:006` | FAQ | **FAQ Tom²Pro** — distribution exclusivement par distributeurs agréés ; certification TechExpert renouvelée annuellement | 06/12/2019 | F1 | https://www.tomate.com/support/systeme-integre-de-gestion-optimise-pour-les-i_5 |

> **Lacunes de la source éditeur, à documenter comme telles :** aucune mention de raison sociale, de siège, de SGBD, de technologie de développement, de version WEB, ni de SYSCOHADA/SYCEBNL.

---

## B.2 — Sources primaires décrivant le produit (tiers acheteurs)

| ID | Type | Intitulé / contenu utile | Date | Fiab. | Référence |
|----|------|--------------------------|------|-------|-----------|
| `SRC:marche:101` | **Clarification d'avis de marché — source de référence pour le périmètre modulaire** | **UNOPS, Guinée, `RFQ/2020/14559`** (UNGM n° 108162). Clarification du 19/05/2020 : « Gestion financière et comptable TOMPRO qui est un outil intégré de **10 modules** », avec l'intitulé et la description de chacun. Lot 1 : logiciel TOMPRO + formation. **10 accès simultanés.** Avis annulé le 24/05/2020. | 13/05/2020 | **F1** | https://www.ungm.org/Public/Notice/108162 |
| `SRC:marche:102` | Avis de marché | **UNOPS, Guinée, `RFQ/2020/14883`** (UNGM n° 108937) — republication du précédent ; clarifications des 29/05, 03/06 et 04/06/2020 (accès simultanés, contexte multi-utilisateurs décentralisé) | 29/05/2020 | F1 | https://www.ungm.org/Public/Notice/108937 |
| `SRC:marche:103` | Avis de marché | UNOPS, Guinée, `RFQ/2019/9633` (UNGM n° 91471) — TOMPRO cité parmi 7 logiciels, sans description | 30/05/2019 | F2 | https://www.ungm.org/Public/Notice/91471 |
| `SRC:integrateur:104` | **Proposition technique et financière — source de référence pour l'architecture et le modèle de licence** | **DISS (Développement Informatique et Systèmes de Suivi, SARL, Ris-Orangis, France) pour l'UCP MARNDR/FIDA, Haïti** — projets PPI-II et PPI-III. Contient : **« TOM²PRO fonctionne en client/serveur sous SQL Serveur en environnement Windows »** ; liste des 10 modules ; **les cinq plans** (financier, analytique, budgétaire, géographique, comptable) ; « tous les rapports peuvent être exportés vers MS-Excel » ; DRF et paiement direct « au format des différents bailleurs » ; **grille tarifaire complète** (licences siège/régions, clés utilisateur, maintenance, J/H) ; architecture multi-sites (4 sites décentralisés, consolidation à Port-au-Prince, 10 financiers) ; modules TOMMONITORING dont « transfert de données entre antennes et l'UGP » ; import des données historiques par fichiers Excel pré-formatés | 16/09/2013 | **F1** | https://agriculture.gouv.ht/view/01/IMG/pdf/proposition_tomportail_ppi2_3_mise_a_jour.pdf |
| `SRC:marche:105` | **Termes de référence** | **Caritas Africa / SERCAF, soutien CRS** — acquisition des **« versions web des produits logiciels TOMATE »** : `TOM²PRO`, `TOM²PAIE`, **`TOM²GRH`**, `TOM²ETATSFINANCIERS`. Justification : « les solutions logicielles TOMATE sont considérées comme les mieux adaptées aux besoins des organisations à but non lucratif et orientées vers le développement ». 46 Caritas nationales. | 02/07/2025 | **F1** | https://caritas-africa.org/appel-doffre-pour-lacquisition-de-logiciels-pour-caritas-africa/ |

---

## B.3 — Sources d'audit et de supervision (preuve des usages et des défaillances)

| ID | Type | Intitulé / contenu utile | Date | Fiab. | Référence |
|----|------|--------------------------|------|-------|-----------|
| `SRC:audit:201` | **Rapport d'audit — pièce centrale du dossier** | **Delta Grant Thornton** (membre de Grant Thornton International Ltd, agréée CEMAC n° SEC 61 ; signataire Adrien Degbey, EC n° 312) — **audit de clôture du projet PAZH Gabon, don TF 016689-GA, exercice clos le 31/12/2020, rapport du 22/02/2022**. Contient : note 1.8 « Paramétrage du logiciel d'exploitation Tom2Pro » ; **« ne permet pas la préparation de l'état des emplois et ressources […] et le suivi budgétaire de manière automatique »** ; **« les états financiers annuels du Projet sont élaborés manuellement en fichier Excel, après retraitement des balances et d'autres états extraits du logiciel TOM2 PRO »** ; comptabilité de trésorerie selon le plan comptable OHADA adapté aux projets ; TOMPRO immobilisé à **19 577 288 FCFA** ; opinion non modifiée. **Renvoie à une lettre de contrôle interne non publiée — à demander.** | 22/02/2022 | **F1** | https://documents1.worldbank.org/curated/en/099915003082237609/txt/PAZH02020000Ra0decembre02020000vDef.txt |
| `SRC:audit:202` | Rapport d'audit | **Projet PDIL-II** — comptabilité du projet informatisée avec TOM2PRO | exercice 2017 | F2 | https://documents1.worldbank.org/curated/en/839071543505286603/txt/PDIL-II-RAPPORT-AUDIT-COMPTABLE-ET-FINANCIER-2017.txt |
| `SRC:superv:203` | Rapport de supervision | **FIDA, programme DEFIS, Madagascar** — paramétrage TOMPRO « quasi finalisé », formation des comptables et de l'administrateur financier ; besoin d'harmonisation du plan comptable entre agences d'exécution (EPR) et unités (UL) ; contrat SOFTWELL pour acquisition, installation et formation TOMPRO : **19 430 000** (devise non précisée dans la source — **à vérifier sur pièce**) | 12/2013 | F2 | https://www.ifad.org/documents/48415603/49455874/Rapport+de+supervision+dcembre+2013_1.pdf |
| `SRC:superv:204` | Rapport de supervision | **FIDA, DEFIS, Madagascar** — écarts entre registre des immobilisations, comptabilité et inventaire physique | 02/2022 | F2 | https://www.ifad.org/documents/48415603/49455874/Madagascar+2000001492+DEFIS+Supervision+Report+February+2022.pdf |
| `SRC:projet:205` | Manuel de procédures | **FID Madagascar, Projet Filets Sociaux de Sécurité** — Tom²Pro comme logiciel comptable et financier ; ariary comme unité de comptabilisation ; module de rapprochement bancaire | 12/2022 | F2 | https://www.fid.mg/wp-content/uploads/2023/07/FID-FSS-FA3-Gestion-comptable-volume-2-revise-ANO-BM-du-01-decembre-2022.pdf |
| `SRC:projet:206` | Rapport d'exécution | **CAFI / Gabon** — « le logiciel comptable TOMPRO de l'unité de gestion a été acquis, installé et est fonctionnel » ; formation du responsable financier sur TOM2PRO | 2022 | F2 | https://mptf.undp.org/sites/default/files/documents/2023-09/2022_annual_report_cga_1224_cafi-gabon-rapport_annuel_2022_at_et_suivi_des_forets_afd.pdf |

---

## B.4 — Marchés publics (preuve du mode de passation et des prix)

| ID | Objet | Procédure | Montant | Date | Fiab. |
|----|-------|-----------|---------|------|-------|
| `SRC:marche:301` | **Congo, projet PATN (Banque mondiale), réf. `CG-PATN-0018-F-ED-2023`** — acquisition TOM2PRO, installation, paramétrage, formation, assistance, maintenance | **Entente directe avec la société TOMATE** | **20 308 193 FCFA** | 2023 | F1 |
| `SRC:marche:302` | **Congo** — fourniture, installation TOMPRO et mise en réseau | **Entente directe avec la société TOMATE** | **10 745 447 FCFA** | — | F1 |
| `SRC:marche:303` | **Tchad, UGP PDMFI/FJ (BAD)** — acquisition du logiciel Tom2Pro, mise en place, formation du personnel financier et comptable | **Entente directe** | non publié | — | F1 |
| `SRC:marche:304` | **Madagascar (Banque mondiale)** — **fourniture et migration du logiciel TOM2PRO en version WEB** pour l'UGP PRRC | **Direct Selection** — SOFTWELL CONSULTING | **27 556 USD** | — | F1 |
| `SRC:marche:305` | **Mali / Tchad** — maintenance du logiciel Tom2Pro ; exigence d'« au moins deux marchés de prestations de maintenance des logiciels de la société TOMATE » | **Concurrentielle, mais à référence restrictive** | — | — | F2 |
| `SRC:marche:306` | **GABAC (CEMAC)** — acquisition d'un ERP (comptabilité générale, projets, passation de marchés, RH), dépôt au 30/09/**2015**. **Ne mentionne pas TOMPRO.** *(Cité à tort par la v1.0 comme « TDR GABAC déc. 2025 ».)* | Appel d'offres | — | 2015 | F3 |

---

## B.5 — Sources normatives et juridiques

| ID | Texte | Point utile | Date clé | Référence |
|----|-------|-------------|----------|-----------|
| `SRC:droit:401` | **Art. L.122-6-1 CPI** (France) | Exception de décompilation pour interopérabilité (IV) ; **« toute stipulation contraire aux dispositions prévues aux II, III et IV du présent article est nulle et non avenue »** | — | Légifrance |
| `SRC:droit:402` | **Directive 2009/24/CE** | Art. 5 §3 : droit d'observer, étudier, tester le fonctionnement du programme. Art. 6 : décompilation | 23/04/2009 | EUR-Lex |
| `SRC:droit:403` | **CJUE, C-406/10, *SAS Institute Inc. c/ World Programming Ltd*** | **Les fonctionnalités, le langage de programmation et les formats de fichiers de données ne sont pas protégés par le droit d'auteur.** Fondement juridique de l'approche boîte noire. | **02/05/2012** | curia.europa.eu |
| `SRC:droit:404` | **CJUE, C-13/20, *Top System SA c/ État belge*** | L'acquéreur légitime peut décompiler pour **corriger des erreurs**, sur le fondement de l'**art. 5** (et non 6) de la directive | **06/10/2021** | curia.europa.eu |
| `SRC:droit:405` | **OAPI — Accord de Bangui, Annexe VII** (propriété littéraire et artistique) | Norme **minimale** ; art. 5 de l'Accord : les droits restent **des droits nationaux indépendants** → analyse pays par pays obligatoire. Révision par l'**Accord de Bamako du 14/12/2015**, en vigueur le **20/11/2020**. 17 États membres. **Madagascar n'en fait pas partie.** | 20/11/2020 | http://siege.oapi.int/Ressources/accord_bangui/2020/francais.pdf |
| `SRC:droit:406` | **Convention de Malabo** (UA, cybersécurité et protection des données à caractère personnel) | Adoptée le **27/06/2014**, **entrée en vigueur le 08/06/2023**. À compléter par les lois nationales. | 08/06/2023 | Union africaine |
| `SRC:compta:407` | **Acte uniforme OHADA relatif au SYCEBNL** | 11ᵉ acte uniforme. Adopté à **Niamey le 22/12/2022**, publié au JO OHADA le **22/02/2023**, **en vigueur le 01/01/2024**. Comble l'exclusion des entités à but non lucratif du SYSCOHADA par l'art. 5 de l'AUDCIF. **Art. 17 : registre des donateurs obligatoire.** Art. 24–27 : dispositions pénales (transposition nationale inégale). Bilan d'ouverture exigé. | **01/01/2024** | https://www.ohada.org/acte-uniforme-relatif-au-systeme-comptable-des-entites-a-but-non-lucratif/ |
| `SRC:compta:408` | **SYSCOHADA révisé / AUDCIF** | Référentiel des entités à but lucratif ; exclut les entités à but non lucratif (art. 5) | — | OHADA |
| `SRC:compta:409` | **PCG 2005 (Madagascar)** | Référentiel applicable hors espace OHADA — requis pour les déploiements malgaches | 2005 | droit national malgache |
| `SRC:bailleur:410` | **Banque mondiale — *Disbursement Guidelines for Investment Project Financing*** | Terminologie officielle : **Interim Financial Report (IFR)**, **Statement of Expenditure (SOE)**, **Designated Account**. Le « Summary Report » est soit l'IFR, soit le SOE. **IFR dus au plus tard 45 jours après la fin de chaque trimestre civil** (conditions générales IDA). | **02/2017** | https://documents1.worldbank.org/curated/en/099817206282434189/pdf/IDU1857458331ee0214b971afbc19f73662643de.pdf |

> **Correction terminologique importante.** La v1.0 emploie le sigle **« IPFR »**, qui n'existe pas dans la terminologie de la Banque mondiale. Les termes corrects sont :
> - **IFR** — *Interim Financial Report* / **RFI** — rapport financier intermédiaire ;
> - **RSF** — rapport de suivi financier (terme employé par l'éditeur lui-même dans la description du module `États financiers` : « états RSF suivant le format bailleur (TER et tableau d'utilisation des fonds par activités) ») ;
> - **SOE** — *Statement of Expenditure* / **ECD** — état certifié de dépenses ;
> - **DRF** — demande de retrait / de réapprovisionnement de fonds ;
> - **Compte désigné** — *Designated Account*.

---

## B.6 — Sources de formation et sources secondaires

| ID | Contenu | Date | Fiab. |
|----|---------|------|-------|
| `SRC:forma:501` | **PADS Burkina Faso** — mise à niveau des acteurs des subventions **Fonds mondial** sur **la version web du logiciel TOM2PRO**. *Confirme l'existence et le déploiement de la version WEB.* | 12/2024 | F2 |
| `SRC:forma:502` | **Manuel d'utilisation de Tom Pro Web** — document de référence utilisateur en circulation publique. *Pagination (~650 p.) non vérifiée.* | — | F3 |
| `SRC:forma:503` | **Manuel de formation Tom²Pro** (desktop) — navigation, saisies, modifications, suppressions, paramétrage général | — | F3 |
| `SRC:forma:504` | **CIFOPE** — programme de formation « gestion informatisée des projets et agences », module Tom²EtatsFin Projets | 11/2024 | F3 |
| `SRC:forma:505` | **COPED** — atelier de formation standard au logiciel TOM²PRO V2 ; mentionne le directeur technique de la S.A.S TOMATE comme concepteur du logiciel | 09/2021 | F3 |
| `SRC:presse:506` | **RDC** — journée portes ouvertes TOMATE ; « plus de 100 licences tous modules confondus » utilisées quotidiennement | 10/2024 | F3 |
| `SRC:profil:507` | **Devex — fiche organisation « Societe Tomate »** | — | F3 |
| `SRC:integr:508` | **Softwell (Madagascar)** — distributeur ; présente Tom²EtatsFin comme produisant des états conformes au SYSCOHADA *(revendication du distributeur, non de l'éditeur)* | — | F3 |
| `SRC:integr:509` | **AGOSOFT (Côte d'Ivoire)**, **MICROSYS (Burkina Faso)** — fiches distributeurs | — | F3 |

---

## B.7 — Pièces à obtenir (lacunes identifiées du corpus)

Ces pièces n'ont pas pu être obtenues en sources ouvertes. Leur obtention est une **action de phase 0/1**, et pour certaines le **chemin critique du projet**.

| Priorité | Pièce | Détenteur probable | Voie d'obtention |
|---|---|---|---|
| **1 — bloquante** | **CLUF / contrat de licence TOM²Pro** (desktop et WEB) | Maîtrise d'ouvrage titulaire d'une licence | Demande interne. **Sans cette pièce, aucune phase 2+ ne peut démarrer.** |
| **1 — bloquante** | **Licence d'accès à une instance TOM²Pro WEB** | Éditeur ou intégrateur agréé | Négociation d'un accès de démonstration ou d'évaluation. **Risque R2 : c'est le chemin critique.** |
| 2 | **Lettre de contrôle interne Delta Grant Thornton** (PAZH, exercice 2020) — contient les recommandations détaillées sur le logiciel | Coordonnateur de l'UCP PAZH / DGEPN Gabon | Demande motivée ; possible via la Banque mondiale |
| 2 | **Cahier des charges complet (Section II / liste des besoins)** des avis UNOPS 108162, 108937 | UNGM — pièces jointes aux avis | Compte fournisseur UNGM |
| 2 | **TDR complets Caritas Africa** (publication au journal officiel du 02/07/2025) — version WEB, spécifications d'hébergement et de migration | Caritas Africa / SERCAF | Téléchargement depuis la page de l'avis |
| 3 | **Manuel d'utilisation TOM²Pro WEB** — version officielle et pagination | Éditeur / intégrateur | Fourni avec la licence |
| 3 | **Notes de version / release notes** — pour la chronologie d'évolution (§4.2 du CdC) | Éditeur | Contrat de maintenance |
| 3 | **Documentation d'administration et de sauvegarde** — confirme le SGBD et son mode d'exploitation | Éditeur / intégrateur | Fournie avec la licence |
| 3 | Identité juridique complète de l'éditeur (raison sociale, siège, immatriculation) | Registres du commerce | Recherche au registre ; le contrat de licence la porte nécessairement |
| 4 | Pièce d'origine du montant « 84 millions MGA » cité par la v1.0 | Auteur de la v1.0 | À produire ou à retirer |

---

## B.8 — Norme de citation (reprise et précisée depuis l'Annexe A de la v1.0)

```
[SRC:<type>:<id>:<date>]

type ∈ { editeur | marche | integrateur | audit | superv | projet |
         droit | compta | bailleur | forma | presse | profil | integr |
         ecran | test | fichier }

Exemples :
  [SRC:marche:101:2020-05-19]   → clarification UNOPS, liste des 10 modules
  [SRC:integrateur:104:2013-09-16] → architecture SQL Server
  [SRC:audit:201:2022-02-22]    → constat Delta Grant Thornton
  [SRC:ecran:M02_E014:2026-11-20]  → capture d'écran horodatée (phase 2)
  [SRC:test:T-M04-012:2026-11-22]  → cas de test démontrant une règle de gestion
```

**Règle de recette :** toute affirmation du dossier final porte au moins une référence `[SRC:...]`. Toute affirmation sans référence est marquée `[HYP]` et assortie d'un plan de vérification. Un livrable comportant une affirmation non référencée et non marquée `[HYP]` est rejeté en recette.
