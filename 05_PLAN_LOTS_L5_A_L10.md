# PLAN DE DÉVELOPPEMENT — LOTS L5 À L10 (MÉTIER ET DIFFÉRENCIATION)

**Prérequis :** contrôle de sortie des fondations validé ([lots L0 à L4](04_PLAN_LOTS_L0_A_L4.md)).

> **C'est ici que le produit cesse d'être un logiciel comptable de plus.** Les lots L5 à L7 construisent les trois artefacts que personne d'autre ne fournit : le dossier de conformité traçable, le rapport scellé reproductible, et l'accès auditeur direct.

| Lot | Objectif | Durée |
|---|---|---|
| **L5** | Configuration de projet et registre des exigences | 4 semaines |
| **L6** | Production, contrôles, scellement, calendrier | 5 semaines |
| **L7** | Dossier de conformité et accès auditeur | 3 semaines |
| **L8** | Reprise et réversibilité | 3 semaines |
| **L9** | Marchés, non-objections et trésorerie | 4 semaines |
| **L10** | Multi-bailleurs et tableau de bord | 3 semaines |

---

# LOT L5 — CONFIGURATION ET REGISTRE DES EXIGENCES

**Objectif.** Un projet configuré à partir de son DFIL, avec traçabilité au paragraphe.

---

### L5-T01 — Documents de référence

**Fichiers.** `backend/niveau3_config/models.py`, `services/documents.py`

`DocumentReference` : type (`financing_agreement`, `dfil`, `implementation_manual`, `awp_budget`, `report_template`, `instruction`), titre, version, date, fichier en stockage objet, **`sha256`**, chaînage `superseded_by`.

> **Pourquoi l'empreinte.** Une exigence cite « DFIL §4.2 ». Si le fichier est remplacé en douce, la citation ne veut plus rien dire. L'empreinte garantit que la citation renvoie **exactement** au document analysé.

**Contrôle.** Téléverser deux fois le même fichier produit la même empreinte ; un fichier modifié d'un octet en produit une différente et le système le signale.

> **Réalisation de L5-T01** (`niveau3_config/{stockage,services/documents}.py`, migration `0003`).
> - **Stockage adressé par le contenu** : la clé d'un fichier est son SHA-256, préfixée par l'organisation (deux organisations qui téléversent les mêmes octets n'ont pas le même objet, donc aucune ne devine ce que l'autre détient). Même fichier, même référence, aucun doublon ; un octet de différence, un autre objet ; l'ancien reste intact. Les chemins sont validés (pas de `..`). Ici un dossier local (`STOCKAGE_DOCUMENTS_ROOT`, `backend/var/documents`, ignoré par git) ; en production le stockage objet souverain tiendra la même interface, seule la classe change.
> - **`enregistrer_document`** : idempotent (mêmes octets sous le même type, titre et version : le document existant) ; des octets DIFFÉRENTS sous les mêmes type, titre et version sont refusés par `DocumentModifie`, qui nomme les deux empreintes : un document modifié est une nouvelle version. Habilitation `parametrer`.
> - **`remplacer_document`** : nouvelle version, ancien chaîné par `superseded_by`, sans jamais toucher à l'ancien ni à son fichier ; `exigences_a_reverifier` liste les exigences qui citent encore l'ancien texte.
> - **`verifier_integrite`** relit le fichier stocké et le compare à l'empreinte enregistrée (fichier altéré ou disparu : `IntegriteDocument`, constatation tracée au journal d'audit) ; `verifier_integrite_du_projet` les passe tous.
> - **En base, pour tout rôle** : un document ne se supprime jamais ; empreinte, fichier, titre, version, type ne changent jamais ; seul `superseded_by` se pose, UNE fois, vers un document du même projet qui n'est pas lui-même remplacé (donc jamais de cycle) ; unicité (projet, type, titre, version).
> - **Limites** : l'extraction du texte, nécessaire à la validation des citations, est l'objet de L5-T02 ; pas de stockage objet réel branché (seulement l'interface et le dossier local) ; la taille maximale (50 Mio) est une valeur de départ.

---

### L5-T02 — Le registre des exigences

**Fichier.** `backend/niveau3_config/models.py`

Modèle `Exigence` complet (dossier d'architecture §4). Les attributs qui comptent :

```python
citation = models.JSONField()
# {"annex": "2", "page": 37, "paragraph": "4.2", "quote": "…texte exact…"}
```

**Validation à l'enregistrement :** `citation["quote"]` doit être un extrait **littéralement retrouvable** dans le texte du document. Une citation inventée est refusée.

```python
def valider_citation(exigence):
    texte = extraire_texte(exigence.document)
    if normaliser(exigence.citation["quote"]) not in normaliser(texte):
        raise ValidationError(
            "La citation n'a pas été retrouvée dans le document référencé."
        )
```

**Contrôle.** Une citation absente du document est refusée avec ce message exact.

> **Réalisation de L5-T02** (`niveau3_config/services/{extraction,exigences}.py`, migrations `0004`-`0005`, dépendance `pypdf`).
> - **`valider_citation`** : l'extrait doit être littéralement retrouvable dans le texte du document, sinon `CitationIntrouvable` avec le message exact « La citation n'a pas été retrouvée dans le document référencé. ». Comparaison **normalisée** : même Unicode (ligatures, espaces insécables), même typographie (guillemets, apostrophes, tirets, traits d'union conditionnels), espaces et retours à la ligne ramenés à un seul espace. La **casse et les accents restent significatifs** : une citation est littérale.
> - **Formats** : PDF (par page, via `pypdf`), DOCX (lu sans dépendance, déclarations de type refusées contre les entités XML, taille décompressée bornée) et texte brut (UTF-8 puis cp1252). Tout autre contenu, un PDF chiffré ou scanné (sans texte extractible), un fichier illisible : **refusés avec leur raison**, jamais validés sur un texte mal lu.
> - **Page** : si le document est un PDF et que la citation donne une page, l'extrait doit s'y trouver (ou y commencer et se poursuivre sur la suivante) ; sinon `CitationMalPlacee`, qui distingue « absent du document » de « présent, mais ailleurs ». Hors PDF, la page n'est pas vérifiable et ne bloque pas.
> - **Un extrait trop court** (moins de 10 caractères) est refusé : « le » est partout, il ne désigne aucun passage. Valeur de départ à ajuster.
> - **On ne vérifie jamais sur un fichier modifié** : l'empreinte du fichier stocké est revérifiée avant l'extraction. Un document remplacé ne se cite plus (citez la version en vigueur) ; le document doit être du projet.
> - **`proposer_exigence`** (habilitation `parametrer`) : crée l'exigence `proposed`, un code déjà connu donnant une **nouvelle version**, jamais une modification ; trace au journal d'audit avec l'empreinte et la citation.
> - **Ce que la base garantit en plus de L0-T08** : citation en objet avec extrait non vide et paragraphe ou page (les `COALESCE` évitent qu'un `CHECK` à valeur NULL passe) ; exigence conditionnelle avec sa condition ; confiance seulement pour une exigence assistée, entre 0 et 1 ; et **une exigence validée ou active a une citation vérifiée sur l'empreinte exacte du document référencé** (`citation_verifiee_sha256`, posée par le service). Une exigence ne peut donc pas devenir active sans que sa citation ait été retrouvée.
> - **Limites** : la base ne relit pas le fichier (elle ne peut pas) : un chemin qui ferait `INSERT` d'une exigence `proposed` sans le service n'a pas sa citation vérifiée, et la base l'empêchera seulement d'être validée ou activée ; la détection de format se fait au contenu (pas de type MIME enregistré) ; pas d'OCR.

---

### L5-T03 — Le rattachement : la règle qui donne sa valeur au produit

**Fichier.** `backend/niveau3_config/models.py`

```python
class RattachementExigence(models.Model):
    exigence    = models.ForeignKey(Exigence, on_delete=models.PROTECT)
    target_type = models.CharField(max_length=32)   # report_template | report_row
                                                    # | mapping | control | field
    target_id   = models.UUIDField()
    class Meta:
        unique_together = [("exigence", "target_type", "target_id")]
```

> **La règle :** tout objet de configuration **actif** — rubrique de rapport, mapping, contrôle, périodicité — doit posséder au moins un rattachement. Un objet actif sans exigence source est une **anomalie de configuration**, signalée par le système lui-même.

C'est ce qui rend le dossier de conformité (L7) générable automatiquement, et ce qui empêche la configuration de redevenir une boîte noire — le défaut exact que l'audit du Gabon a sanctionné.

**Contrôle à écrire maintenant :**

```python
@pytest.mark.django_db
def test_aucun_objet_actif_sans_exigence_source(projet_configure):
    orphelins = detecter_configuration_orpheline(projet_configure)
    assert not orphelins, f"Configuration sans exigence source : {orphelins}"
```

> **Réalisation de L5-T03** (`niveau3_config/services/rattachement.py`, commande `verifier_configuration`, migration `0006`).
> - **La règle, appliquée** : `detecter_configuration_orpheline(projet, date)` liste les objets de configuration ACTIFS à `date` sans exigence source **active, du projet, valable à `date`** (`valid_to` exclu). La raison distingue **« aucun rattachement »** (un oubli) de **« rattaché seulement à des exigences non actives ou hors validité »** (un défaut de suivi) : un rattachement à une exigence seulement proposée ou validée ne justifie rien, puisque ce sont les exigences actives que les documents contractuels du projet ont fait entrer.
> - **Point d'extension** : chaque type d'objet déclare comment lister ses objets actifs et comment vérifier qu'un identifiant existe (`enregistrer_cible`). Les **mappings** sont branchés ; les modèles d'états, rubriques, contrôles et périodicités, qui n'existent pas encore comme objets (les modèles d'états sont des fichiers JSON jusqu'à L6), s'y brancheront avec L6 sans rien changer ici. Un test enregistre un type fictif pour prouver que la règle s'y applique.
> - **`rattacher`** (habilitation `parametrer`) : idempotent, tracé ; quand le type est branché, l'objet doit exister **dans le projet de l'exigence** ; une exigence remplacée ou rejetée ne justifie plus rien et n'accepte plus de rattachement.
> - **En base, pour tout rôle** : un rattachement est en **ajout seul** (ni modification, ni suppression : on remplace l'objet ou l'exigence par une version nouvelle) et ne se pose pas sur une exigence remplacée ou rejetée.
> - **`verifier_configuration --organisation --projet [--date]`** : liste les orphelins et sort en code 1 s'il y en a, pour l'ordonnanceur et la chaîne d'intégration.
> - **Limites** : l'anomalie est **signalée**, elle ne bloque pas l'activation d'un mapping (la règle du plan dit « signalée par le système lui-même ») ; les types non branchés se rattachent sans vérification d'existence ; les mappings d'organisation (sans projet) ne sont pas couverts par la détection d'un projet.

---

### L5-T03bis — Profil de décaissement du projet

**But.** Porter ce qui varie d'un projet à l'autre chez un même bailleur : régime, méthodes autorisées, seuils, pièces exigées, comptes désignés, **taux de financement par catégorie**.

**Fichiers.** `backend/niveau3_config/models.py` (tables du §4bis du dossier d'architecture), `services/decaissement.py`

**Les trois points à ne pas rater :**

1. **Ensembles fermés contraints en base.** `method` et `supporting_docs` sont des `CHECK`, pas des tables libres. Ajouter une méthode est une migration, jamais un paramétrage client.
2. **La règle de calcul.**
   ```
   montant_a_retirer = depense_eligible × funding_rate, sur l'assiette tax_basis
   ```
   avec arrondi déterministe, comme la ventilation de cofinancement.
3. **`category_funding_rule_id` persisté sur chaque ligne de demande de retrait.** Sans cela, une réallocation ultérieure rend inexplicable une demande déjà soumise.

**Contrôles.**

```
[ ] Trois projets du MÊME bailleur avec des montants minimums de demande
    différents (20 % du plafond, 100 000, 200 000) coexistent sans conflit
[ ] Changer le régime de transactionnel à « sur rapport » au 01/07 laisse
    INCHANGÉES les demandes du premier semestre
[ ] Une réallocation modifiant un taux de 100 % à 80 % ne recalcule aucune
    demande antérieure
[ ] Une dépense antérieure à la date d'éligibilité est refusée, en nommant la date
[ ] Une demande inférieure au montant minimum est bloquée, en nommant le seuil
[ ] Une dépense au-delà du seuil de documentation exige les copies de pièces
    et non l'état certifié
```

### L5-T04 — Activation, versionnement, date d'effet

Service `activer_exigence()` : `proposed` → `validated` → `active`, transitions tracées.

**La contrainte posée en L0-T08 interdit déjà le passage en `active` sans validateur**, au niveau de la base. Vérifiez qu'elle est toujours là.

`ConfigurationProjet` : agrégat versionné de tout ce qui est actif à une date donnée. **Toute génération de rapport résout la configuration active à la date d'effet de la période**, jamais la configuration courante.

**Contrôle.** Modifier une exigence avec effet au 1ᵉʳ janvier 2028, puis régénérer un rapport du troisième trimestre 2027 : le rapport est **inchangé**.

---

**Compléments à L5-T04 (issus de l'examen des dossiers « bailleurs et conventions »).**

1. **Un seul profil actif à la fois, garanti par la base.** Contrainte `EXCLUDE USING gist` sur `(org_id, agreement_id, daterange(valid_from, valid_to, '[)'))` pour les versions `active` du profil de décaissement, et sur `(org_id, project_id, code, daterange(…))` pour les exigences. Convention de dates : guide §B.6.
2. **Immutabilité par déclencheur.** Les tables `disbursement_method`, `designated_account_rule`, `category_funding_rule` refusent toute modification dès que le profil parent n'est plus `draft`.
3. **Rejet motivé.** Les statuts du profil gagnent `rejected` (motif obligatoire). Pas d'autre statut : « programmé » reste une version `active` dont `valid_from` est futur.
4. **Version persistée sur l'opération.** À chaque contrôle ou validation d'une dépense ou d'une demande, on enregistre `profile_version_id` (le profil résolu à la date de l'opération) à côté de `category_funding_rule_id`. Sans cela, on retrouve la règle de taux mais pas le régime ni les seuils en vigueur.

**Contrôles.**

```
[ ] Deux versions actives qui se chevauchent : refusées par la base, pas par le code
[ ] Version de profil approuvée : UPDATE et DELETE d'une méthode refusés, y compris en SQL direct
[ ] Dépense du 15/06 contrôlée sous V2, accord passé en V3 en décembre : la dépense garde V2
[ ] Activation concurrente de deux versions incompatibles : une seule aboutit
```

---

### L5-T04bis — Réallocations, avenants, complétude et comparaison

**Fichiers.** `backend/niveau3_config/models.py`, `services/reallocation.py`, `services/completude.py`, `services/comparaison.py`

**1. La réallocation est un événement, pas une modification.** Modèle `Reallocation` : accord, catégorie source, catégorie cible, montant, devise, demandeur, **approbateur distinct du demandeur**, motif, document justificatif, statut (`demandée` · `approuvée` · `rejetée`), et **la version de profil qu'elle crée** à l'approbation, avec date d'effet. Notre principe reste : une réallocation crée une version du profil (spécification §5.3-E). Ce qui s'ajoute, c'est la trace du transfert et de son approbation.

```
approuver_reallocation(r):
    verrouiller (FOR UPDATE) les deux catégories
    refuser si approbateur == demandeur
    refuser si le solde de la catégorie source < montant
    créer la nouvelle version du profil (allocations modifiées, valid_from = date d'effet)
    écrire l'audit et lier r à la version créée
```

**2. Avenant d'accord.** Le modèle `AvenantAccord` est défini en L4-T04. Ici on branche son effet : enregistrer un avenant crée, dans la même transaction, la nouvelle version de profil (montant, dates, allocations) et le lie à l'avenant.

**3. Contrôle de complétude avant soumission.** `verifier_completude(profil)` renvoie des erreurs **bloquantes** (accord ou bailleur absent, dates incohérentes, aucune catégorie, allocations dont la somme dépasse le montant de l'accord, devise de référence absente, méthode activée sans pièces exigées, exigence critique sans source documentaire, chevauchement de période) et des **avertissements** acceptables avec justification selon les droits. Une erreur bloquante interdit la soumission. Le même service alimente l'assistant d'extraction et le guide généré (L5-T07).

> Le budget du projet n'est **pas** présumé entièrement financé par les bailleurs : un écart entre budget et financements contractualisés est une information, jamais une erreur bloquante.

**4. Comparaison de deux versions.** `comparer_versions(a, b)` liste les paramètres, méthodes, taux, catégories et règles **identiques, modifiés, ajoutés, supprimés**. Même mécanique que la régénération par différentiel (L6-T04), appliquée à la configuration. Elle sert au « avant / après avenant » et au dossier de conformité.

**5. Concurrence.** Deux réallocations simultanées sur la même catégorie source ne peuvent pas toutes deux aboutir (verrou ci-dessus) ; deux approbations concurrentes de la même réallocation n'en produisent qu'une (contrainte d'unicité sur la version créée).

**Contrôles.**

```
[ ] Réallocation approuvée : nouvelle version créée, ancienne conservée, demandes antérieures inchangées
[ ] Demandeur == approbateur : refusé au serveur
[ ] Deux réallocations simultanées sur une même catégorie : solde exact, une seule aboutit si le solde ne couvre pas les deux
[ ] Double approbation concurrente : une seule version créée
[ ] Avenant : situation avant / après affichable, ancienne version intacte
[ ] Profil incomplet : soumission refusée, chaque manque nommé
[ ] Comparaison V1 / V2 : les quatre catégories de différences sont détectées
```

---

### L5-T05 — Profils de bailleurs

**Fichier.** `backend/niveau2_profils/`

`ProfilBailleur` : bibliothèque réutilisable — références documentaires, familles d'états, modèles, règles de présentation, périodicités et délais types, contrôles, formats, nomenclatures.

> **Règle absolue :** un profil **n'impose jamais automatiquement** ses exigences à un projet. Il les met à disposition. Ce sont les documents contractuels du projet qui déterminent lesquelles s'appliquent.
>
> Techniquement : importer un profil crée des exigences en statut **`proposed`**, jamais `active`. Il n'existe aucun chemin de code permettant le contraire.

**Contrôle.** Importer un profil dans un projet ne produit **aucune** exigence active. Un test l'asserte explicitement.

---

### L5-T06 — Le profil Banque mondiale

Familles d'états : rapport financier intermédiaire, état des ressources et emplois, dépenses par composante / activité / catégorie / source, activité et rapprochement du compte désigné, prévisions de trésorerie et suivi des avances, demandes de retrait, états annuels pour l'audit.

Délai type : **45 jours après la fin de chaque trimestre civil** sous les conditions générales IDA.

> **Dans l'interface, chaque élément du profil porte la mention « lorsque requis ».** Il n'existe pas de modèle Banque mondiale universel : le DFIL du projet décide. Présenter un profil comme universel serait une erreur de conception et une faute commerciale.

---

### L5-T07 — Le guide de configuration généré

Depuis le registre, produire un PDF lisible : chaque exigence active, sa source, son mapping, ses contrôles, sa périodicité, son validateur.

> **Pourquoi c'est important.** Les équipes d'unités de gestion tournent constamment. C'est là que meurent les installations concurrentes : le savoir du paramétrage reste chez un consultant d'intégrateur. Ici, il reste dans le système et s'imprime.

**Contrôle.** Le guide d'un projet configuré est lisible par un comptable qui n'a jamais vu le logiciel, et lui permet de dire **pourquoi** chaque rubrique existe.

---

# LOT L6 — PRODUCTION, CONTRÔLES ET SCELLEMENT

**Objectif.** Un rapport financier intermédiaire et son état certifié de dépenses produits, contrôlés, validés, scellés et transmis — **sans Excel**.

---

### L6-T01 — Le moteur de contrôles

`Controle` : code, libellé, **sévérité** (`bloquant` / `avertissement` / `information`), portée, expression, **rattachement à une exigence**.

Bibliothèque livrée — huit familles :

| Famille | Exemples |
|---|---|
| Codification | dépense sans catégorie, sans source, sans axe obligatoire |
| Budget | dépassement de ligne, de catégorie, d'allocation, de plafond d'accord |
| Pièces | doublon de facture ; pièce manquante pour une dépense destinée à un état certifié |
| Trésorerie | écart de rapprochement non justifié ; solde du compte désigné incohérent |
| Avances | avance non justifiée, ou au-delà du délai applicable |
| Rapport | rubrique obligatoire vide ; **compte non mappé** ; assertion non vérifiée |
| Cohérence | incohérence entre états d'une période ; entre deux périodes ; rupture de cumul |
| Éligibilité | dépense non conforme aux règles configurées (nature, date, zone, bénéficiaire) |

**Contrôle.** Chaque contrôle livré a un test qui le déclenche **et** un test qui prouve qu'il ne se déclenche pas à tort.

**Condition structurée, jeu d'opérateurs fermé.** L'`expression` d'un contrôle n'est jamais du texte libre : c'est une condition JSON évaluée en Python avec des `Decimal`, validée par un **schéma propre à chaque type de règle**. Opérateurs autorisés, et aucun autre :

| Opérateur | Sens |
|---|---|
| `eq`, `neq` | égal, différent |
| `gt`, `gte`, `lt`, `lte` | comparaisons |
| `in`, `not_in` | appartenance à une liste |
| `est_renseigne`, `est_absent` | valeur présente ou non |
| `avant`, `apres`, `entre` | dates ; `entre` est semi-ouvert `[du, au[` |
| `est_vrai`, `est_faux` | booléens |
| `somme_lte` | somme inférieure ou égale à une limite |
| `nombre_eq` | nombre d'éléments égal à une valeur |

Aucune requête SQL, aucun JavaScript, aucun `eval`/`exec` (règle 5). Une condition qui sort du schéma est refusée à l'enregistrement.

**Résultats.** `réussi` · `bloquant` · `avertissement` · `information` · **`à_vérifier`** (contrôle non automatisable, vérification humaine requise ; ne laisse pas passer l'étape 5 tant qu'il n'est pas tranché). Un contrôle conditionnel non applicable est noté `non_applicable` **dans le journal seulement**, pas dans l'interface.

**Journal de chaque évaluation.** Règle, version du profil, valeur constatée, valeur attendue, résultat, message, action corrective, exigence et clause sources, date, déclencheur (utilisateur ou service). Le moteur est **appelé** par la comptabilité, les dépenses, les marchés et les demandes ; aucun module ne réimplémente ses règles.

**Pièces exigées.** Une pièce requise est une règle de ce moteur (type de pièce, portée : catégorie, méthode, seuil de montant, type de dépense), pas une table de plus. Le contrôle vérifie la présence d'un document **du bon type, rattaché à l'opération**, et validé lorsque la règle l'exige. Il n'existe pas de liste universelle de justificatifs.

**Contrôles de risque (sans module dédié).** Trois contrôles livrés, de sévérité `avertissement` ou `information` : catégorie consommée au-delà d'un seuil paramétré, avance non apurée depuis plus d'un délai paramétré, rejets répétés sur une même catégorie.

**Codes d'erreur stables.** Énumération `CodeErreur`, en français, renvoyée par l'API : `ACCES_ORGANISATION_REFUSE`, `ACCES_PROJET_REFUSE`, `ACCORD_INTROUVABLE`, `AUCUNE_CONFIGURATION_A_LA_DATE`, `CONFIGURATION_NON_APPROUVEE`, `CONFLIT_DE_PERIODE`, `REGLE_INVALIDE`, `CONTROLE_BLOQUANT`, `PIECE_OBLIGATOIRE`, `SOLDE_CATEGORIE_INSUFFISANT`, `APPROBATION_REQUISE`, `TRANSITION_INTERDITE`. Les messages ne révèlent jamais l'existence de données d'une autre organisation.

**Contrôles supplémentaires.**

```
[ ] Condition hors schéma ou opérateur inconnu : refusée à l'enregistrement
[ ] Contrôle « à_vérifier » non tranché : étape 5 inaccessible
[ ] Pièce du mauvais type ou non rattachée à l'opération : refusée comme absente
[ ] Chaque évaluation laisse une ligne de journal avec la version du profil
```

---

### L6-T02 — Le workflow de validation

```
1. Extraire les données de la période
2. Générer selon la configuration ACTIVE à la date d'effet
3. Exécuter les contrôles
4. Corriger ou justifier chaque anomalie       ← justification tracée et conservée
5. Valider — responsable financier             ← signature nominative
6. Approuver — coordonnateur
7. Exporter et transmettre
8. Archiver LA VERSION EFFECTIVEMENT TRANSMISE
```

**Blocage dur :** aucun passage à l'étape 5 tant qu'un contrôle `bloquant` est ouvert et non justifié. Une justification est obligatoirement textuelle, nominative et conservée.

**Contrôle.** Un contrôle bloquant non traité rend l'étape 5 inaccessible — vérifié au serveur, pas seulement masqué dans l'interface.

**Dérogation formelle.** Distincte de la justification : une justification **explique** une anomalie, une dérogation **autorise** à poursuivre malgré un contrôle bloquant. Modèle `Derogation` : contrôle et opération visés (périmètre limité à cet objet), motif, durée de validité, demandeur, **approbateur distinct et habilité**, document justificatif. Le **résultat initial du contrôle n'est jamais effacé ni réécrit** : l'opération apparaît comme « bénéficiant d'une dérogation approuvée », et les deux lignes (échec, dérogation) figurent au dossier de conformité et au journal d'audit.

**Circuit borné.** Conformément à la note 06 §3.2 : 1 à 5 étapes, chacune avec un rôle requis, une condition d'entrée optionnelle (seuil de montant, catégorie, bailleur) et un motif obligatoire en cas de rejet. Pas de moteur de processus général.

**Contrôles.**

```
[ ] Dérogation par son propre demandeur : refusée
[ ] Dérogation expirée ou hors périmètre : le contrôle bloque de nouveau
[ ] Après dérogation, le résultat initial « bloquant » reste lisible dans l'historique
[ ] Deux approbations concurrentes d'une même demande : une seule prend effet
```

---

### L6-T03 — Le scellement

**Fichier.** `backend/niveau4_reporting/publication/scellement.py`

```python
import hashlib, json
from decimal import Decimal

def sceller(rapport) -> bytes:
    """Empreinte stable de tout ce qui détermine le résultat."""
    charge = {
        "template": [rapport.template.code, rapport.template_version],
        "period": [str(rapport.period_from), str(rapport.period_to)],
        "params": rapport.params,
        "config_version": rapport.config_version,
        "mapping_versions": rapport.mapping_versions,
        "dataset_hash": rapport.dataset_hash.hex(),
        "values": {k: str(v) for k, v in sorted(rapport.values.items())},
    }
    return hashlib.sha256(
        json.dumps(charge, sort_keys=True, separators=(",", ":")).encode()
    ).digest()

def empreinte_jeu_de_donnees(cur, predicat_sql, params) -> bytes:
    """Empreinte des lignes retenues : détecte toute modification du périmètre."""
    cur.execute(f"""
        SELECT COALESCE(
          md5(string_agg(id::text || ':' || debit || ':' || credit, '|'
                         ORDER BY id)), '')
        FROM comptabilite_ligneecriture WHERE {predicat_sql}
    """, params)
    return bytes.fromhex(cur.fetchone()[0] or "0" * 32)
```

**Contrôle.** Sceller, modifier une ligne source, re-sceller : les empreintes diffèrent.

---

### L6-T04 — La régénération par différentiel

> **La tâche qui tient la promesse « les rapports historiques restent reproductibles ».** Un système qui se contente de régénérer à la demande ne la tient pas : il produit silencieusement un autre chiffre.

```python
def regenerer(rapport_publie) -> ResultatRegeneration:
    nouveau = generer(
        template=rapport_publie.template,
        version=rapport_publie.template_version,      # la version D'ALORS
        config_version=rapport_publie.config_version, # la configuration D'ALORS
        mapping_versions=rapport_publie.mapping_versions,
        **rapport_publie.params,
    )
    if sceller(nouveau) == rapport_publie.seal:
        return ResultatRegeneration(identique=True)

    return ResultatRegeneration(
        identique=False,
        ecarts_par_rubrique=comparer_valeurs(rapport_publie.values, nouveau.values),
        causes=analyser_causes(rapport_publie, nouveau),
        # → écritures ajoutées depuis, écritures contre-passées,
        #   mappings modifiés, exigences révisées
    )
```

**Contrôle.** Publier un rapport, ajouter une écriture dans la période, régénérer : le différentiel **nomme l'écriture ajoutée et son montant**. Ne vous contentez pas d'un « écart détecté ».

---

### L6-T05 — Génération Excel et PDF

Excel via `openpyxl` : mise en forme conforme au modèle, montants en type numérique à 2 ou 4 décimales selon la devise, **jamais en texte**.
PDF via Typst ou WeasyPrint, **compatible droite-à-gauche**.

Les fichiers produits sont stockés avec leur empreinte dans `published_report.files`.

**Contrôle.** Le fichier téléchargé a exactement l'empreinte enregistrée.

---

### L6-T06 — Le calendrier des obligations

Généré **automatiquement depuis le registre** : chaque exigence périodique produit ses échéances (`periodicity` + `due_offset_days`).

Tâche de fond quotidienne : exécuter les contrôles **avant** l'échéance, alerter, escalader.

> **L'écran d'accueil est ce calendrier, à feux de signalisation — pas une arborescence de menus.** Le métier réel d'un responsable administratif et financier est de ne jamais rater une échéance et de ne jamais faire rejeter un rapport. Le produit doit être organisé autour de cela.

**Contrôle.** Activer une exigence trimestrielle à 45 jours génère les quatre échéances de l'exercice, aux bonnes dates.

---

### L6-T07 — La simulation de revue bailleur

Rejouer sur un rapport en préparation les motifs de rejet connus du bailleur, et rendre un **avis go / no-go avec liste d'actions**.

Enregistrer le résultat des soumissions réelles pour alimenter l'**indicateur phare : le taux de rapports acceptés au premier envoi**.

**Contrôle.** Un rapport avec une avance non justifiée au-delà du délai reçoit un avis `no-go` qui nomme l'avance et le nombre de jours de retard.

---

# LOT L7 — DOSSIER DE CONFORMITÉ ET ACCÈS AUDITEUR

**Objectif.** Un auditeur externe descend d'une cellule du TER jusqu'à la pièce scannée, sans assistance.

---

### L7-T01 — Le dossier de conformité

Généré depuis `published_report` joint à `RattachementExigence` et `Exigence`.

Pour chaque rubrique : l'exigence satisfaite, **sa citation documentaire exacte** (document, version, page, paragraphe, texte cité), la règle appliquée, le mapping utilisé et sa version, le validateur et la date.

Export PDF, **scellé avec le rapport**.

**Contrôle.** Le dossier d'un rapport publié couvre **100 %** de ses rubriques. Une rubrique sans exigence source est impossible — la règle de L5-T03 l'interdit en amont.

---

### L7-T02 — L'accès auditeur

Jeton à portée et durée limitées : projets nommés, plage de périodes, lecture seule, **expiration automatique**.

| Autorisé | Interdit |
|---|---|
| Consulter les états publiés et scellés | Toute écriture |
| Descendre jusqu'à l'écriture et à la pièce | Toute modification de configuration |
| Consulter le dossier de conformité | Tout accès aux autres projets |
| Exporter son périmètre | Toute prolongation par lui-même |

**Chaque consultation et chaque export sont journalisés** et consultables par l'organisation.

**Contrôle.** Un jeton auditeur sur le projet A reçoit `403` sur le projet B ; après expiration, `401` partout ; les accès figurent au journal d'audit de l'organisation.

---

### L7-T03 — La descente complète

Depuis une cellule : rubrique → prédicat de sélection → lignes d'écriture → écriture → pièces justificatives → fichier scanné.

**Contrôle de bout en bout, à démontrer devant l'équipe :**

```
[ ] Ouvrir un TER publié
[ ] Cliquer une cellule → la liste des écritures s'affiche
[ ] La somme des lignes == la valeur de la cellule, au centime
[ ] Cliquer une écriture → ses pièces s'affichent
[ ] Ouvrir une pièce → le scan s'affiche
[ ] Le tout en accès auditeur, sans aucune assistance
```

---

# LOT L8 — REPRISE ET RÉVERSIBILITÉ

**Objectif.** Une base migrée à **écart nul**, intégralement ré-exportable.

---

### L8-T01 — La chaîne de reprise

```
1. Référentiels       plan comptable · tiers · journaux · axes · accords · catégories
                      ▼ assistant de correspondance, sauvegardable et rejouable
2. Soldes d'ouverture balance à la date de bascule, équilibre vérifié
3. Historique         écritures antérieures avec leurs imputations
4. Contrôle           rapprochement balance d'origine ↔ balance reprise
                      écart par compte, par axe, par accord
                      → RAPPORT DE REPRISE SIGNÉ
```

**La règle :** une reprise n'est acceptée qu'à **écart nul** sur la balance générale **et** sur le cumul par accord. Un écart non nul bloque la mise en service et est listé ligne à ligne.

La voie est ouverte : les progiciels en place exportent vers Excel, et leurs propres intégrateurs migrent les historiques par fichiers Excel pré-formatés.

**Contrôle.** Migrer un jeu de 50 000 écritures issu d'un export réel : écart nul, rapport signé produit.

---

### L8-T02 — L'import idempotent

Chaque ligne importée porte une **clé d'idempotence** dérivée de la source. Rejouer un import ne crée **jamais** de doublon.

**Contrôle.** Lancer trois fois le même import : le nombre d'écritures est identique après chaque passage.

---

### L8-T03 — L'export complet

Déclenché depuis l'interface, produit en tâche de fond, mis à disposition par lien signé à durée limitée :

1. **Données** — archive CSV UTF-8 par table, schéma documenté, plus un dépôt SQL restaurable.
2. **Paramétrage** — JSON lisible : plans, axes, clés, schémas d'écritures, mappings, modèles d'états.
3. **Registre des exigences** et guide de configuration.
4. **Rapports publiés scellés** avec leurs fichiers.
5. **Journal d'audit.**

**Contrôle décisif.** Exporter une organisation, l'importer dans une instance **vierge**, régénérer un rapport scellé : **résultat identique**. Si ce test passe, la réversibilité n'est plus une promesse commerciale, c'est un fait vérifié.

---

### L8-T04 — Le dictionnaire de données publié

Généré depuis les modèles : table, colonne, type, description, relations. **Publié ouvertement**, pas réservé aux clients.

> C'est l'inverse exact du modèle économique des concurrents. Dites-le.

---

# LOT L9 — MARCHÉS, NON-OBJECTIONS ET TRÉSORERIE

**Objectif.** Un engagement bloqué faute d'avis de non-objection.

---

### L9-T01 — Plan de passation

Lignes prévisionnelles, méthodes, seuils, calendrier, états d'avancement.

### L9-T02 — Avis de non-objection

Demande, pièces, statut, date de réception. **Blocage de l'engagement tant que l'avis requis n'est pas obtenu.**

> Point de friction quotidien sur les projets Banque mondiale. C'est la raison pour laquelle il appartient au socle, et non à une version ultérieure.

**Contrôle.** Un marché soumis à non-objection refuse l'engagement sans avis, et l'accepte dès réception.

### L9-T03 — Contrats, avenants, garanties

Contrats, avenants versionnés, garanties et assurances avec échéances et alertes.

### L9-T04 — Décomptes et apurement

Décomptes, factures, paiements, **apurement des engagements**, soldes contractuels, taux d'exécution physique et financier.

**Contrôle.** Un engagement totalement apuré libère exactement le disponible budgétaire qu'il réservait, au centime.

### L9-T05 — Trésorerie

Comptes bancaires, mouvements, prévisions par période et par axe, disponibilités, **état de reconstitution du compte désigné**.

**Contrôle.** L'état de reconstitution du compte désigné se rapproche du relevé bancaire, et tout écart est explicitement justifié.

**Rapprochements et doublons.** Un mouvement bancaire est rapprochable d'une demande de décaissement et d'une écriture, **une seule fois** : contrainte d'unicité empêchant qu'un même mouvement soit rapproché de deux demandes. Les numéros de compte restent masqués sans l'habilitation `voir_numero_compte` (L4-T04).

---

# LOT L10 — MULTI-BAILLEURS ET TABLEAU DE BORD

**Objectif.** Deux rapports de bailleurs différents produits à partir des **mêmes données**.

### L10-T01 — Profils BAD, UE, FIDA, Fonds mondial, BID, Nations unies

Chacun avec ses modèles, rubriques, règles, périodicités et nomenclatures.

> **Critère de recette, repris du cahier des charges :** ajouter un profil et un modèle **sans créer une nouvelle application**, et **sans écrire une ligne de code**. Si un profil demande du code, c'est que le moteur a un manque — traitez-le comme tel.

### L10-T02 — Tableau de bord multi-projets

Projets actifs et bailleurs · budgets approuvés et révisés · financements reçus · dépenses et taux d'exécution, global et par composante · soldes bancaires · engagements et **avances non justifiées** · **échéances, rapports en attente, anomalies ouvertes** · taux d'acceptation au premier envoi.

Chaque indicateur est **cliquable jusqu'au détail, puis jusqu'à l'écriture**.

**Contrôle.** Le total d'un indicateur consolidé égale exactement la somme de ses détails par projet.

**Devises.** Le tableau de bord **ne somme jamais des devises différentes sans le dire** : par défaut, montants ventilés par devise. Une consolidation dans une devise de référence affiche, à côté du chiffre, **la méthode, la date et le taux** utilisés ; sans taux disponible à la date, l'indicateur n'est pas consolidé et le dit. Filtres : organisation, projet, bailleur, accord, devise, période, statut d'accord, statut de configuration.

**Contrôle.** Un portefeuille USD + EUR sans taux affiche deux totaux séparés, jamais un total mélangé.

### L10-T03 — Recette d'architecture

Exécuter les dix-sept tests de réception (T1 à T17) de la [spécification fonctionnelle](01_SPECIFICATION_FONCTIONNELLE.md) §17, dont les sept du cahier des charges de l'unité de gestion.

**Scénario T17, de référence (chiffres fictifs).** Un même projet financé par deux bailleurs au moyen de deux accords indépendants (par exemple 5 millions USD et 3 millions USD) : chacun avec sa configuration issue d'un profil, ses catégories, ses taux, ses pièces et son reporting ; une dépense sur chaque accord contrôlée **par ses propres règles** ; un avenant sur le premier crée une nouvelle version **sans effet sur le second** ; une dépense antérieure à l'avenant **conserve la version** qui était applicable à sa date ; un accès croisé d'une autre organisation est refusé.

> **Le critère qui prime sur tous les autres :** la solution est acceptée si elle démontre qu'un nouveau projet, un nouveau bailleur ou un nouveau modèle de reporting s'ajoute **par paramétrage**, sans application distincte et sans duplication des données comptables.

---

# APRÈS : VERSION 2

| Chantier | Note |
|---|---|
| **Immobilisations** | Fiches, localisation, amortissements, cofinancement en pourcentage, cessions, inventaires |
| **Capture hors ligne** | Voir l'annexe B ci-dessous. Périmètre strictement borné. |
| **Assistant d'extraction** | Module optionnel, garde-fous imposés **en base** (dossier d'architecture §7) |
| **Paquets OHADA** | SYSCOHADA, SYCEBNL avec registre des donateurs — marché d'expansion, 17 États |
| **Paquet de langue arabe** | Le droite-à-gauche est déjà en place depuis L0 ; il ne reste que la traduction |
| **API publique** | Pour les satellites : paie, ressources humaines, stocks, suivi-évaluation |

---

# ANNEXE A — LE FRONT-END

Le front se construit **en parallèle**, lot par lot. Un lot n'est pas fini si son écran n'existe pas.

## A.1 Conventions obligatoires

| Règle | Détail |
|---|---|
| **Les montants sont des chaînes** | Ils arrivent en `"1250.0000"`. Manipulés avec `decimal.js`, **jamais avec `Number`**. Un `parseFloat` sur un montant est un bogue. |
| **Jamais de `left` ni de `right` en CSS** | `margin-inline-start`, `padding-inline-end`, `text-align: start`. Sinon l'arabe sera impossible sans tout refaire. |
| **Aucun libellé en dur** | Tout passe par `i18n`, y compris les messages d'erreur. |
| **L'interface masque, elle ne protège pas** | Chaque action est revérifiée au serveur. Masquer un bouton n'est pas une sécurité. |
| **Test en pseudo-locale droite-à-gauche dès L0** | Bien avant toute traduction arabe. C'est ce qui rend la décision D-04 tenable. |

## A.2 Les écrans, lot par lot

| Lot | Écrans |
|---|---|
| **L0** | Éditeur de modèle d'état · aperçu d'un état généré · descente sur une cellule |
| **L1** | Connexion · sélecteur d'organisation et de projet · gestion des utilisateurs et habilitations |
| **L2** | Plan comptable · axes · tiers · devises et taux · installation d'un paquet |
| **L3** | **Saisie d'écritures** (grille dense, usage clavier) · consultation · balance · grand livre · journaux · clôture |
| **L4** | Budget et versions · suivi budgétaire · accords et catégories · **atelier DRF** |
| **L5** | Documents de référence · **registre des exigences** · activation · profils |
| **L6** | **Calendrier des obligations (écran d'accueil)** · production d'un rapport · anomalies · validation |
| **L7** | Dossier de conformité · **espace auditeur** |
| **L8** | Assistant de reprise · export complet |
| **L9** | Plan de passation · non-objections · contrats · trésorerie |
| **L10** | **Tableau de bord multi-projets** |

## A.3 L'écran de saisie — le plus exigeant

C'est le seul écran qu'un comptable utilise huit heures par jour. Exigences :

- **Tout au clavier**, sans souris : tabulation entre cellules, recherche de compte à la frappe, duplication de ligne, équilibrage automatique de la dernière ligne.
- **Équilibre affiché en permanence**, en évidence.
- **Contrôle budgétaire en temps réel** sur l'axe imputé, avec le disponible visible.
- **Brouillon sauvegardé automatiquement**, jamais de saisie perdue.
- **Moins de 100 ms** entre une frappe et l'affichage.

**Contrôle.** Un comptable saisit 50 écritures sans toucher la souris, et le chronomètre le prouve.

---

# ANNEXE B — LE MODE HORS LIGNE (V2)

Périmètre **strictement borné : la capture de pièces, et rien d'autre.**

```
Poste en antenne, sans réseau
├── Référentiels en cache local : comptes, tiers, axes, accords, catégories
├── Saisie ──▶ file locale, chaque pièce portant une CLÉ D'IDEMPOTENCE
└── Retour du réseau
       └─▶ envoi séquentiel ──▶ écritures créées en « BROUILLON »
              ├── clé déjà vue ──▶ ignorée (contrainte UNIQUE en base)
              └── référentiel obsolète ──▶ rejet, motif affiché, correction locale
```

**Jamais délégué au client :** numérotation, validation, contrôle budgétaire, comptabilisation.

> **Pourquoi pas une réplication bidirectionnelle complète.** Sur une comptabilité à numérotation séquentielle et contrôle budgétaire concurrent, la résolution de conflits produit des doublons, des trous de séquence et des soldes irréconciliables. C'est une restriction assumée, documentée, et toute demande d'extension passe par une décision explicite.

**Contrôle.** Saisir une journée complète sans réseau, synchroniser : aucun doublon, aucun trou de séquence.

---

# ANNEXE C — MISE EN PRODUCTION

| Élément | Exigence |
|---|---|
| **Migrations** | Exécutées avec `sigf_owner`. L'application tourne avec `sigf_app`. Jamais l'inverse. |
| **Sauvegardes** | PostgreSQL managé avec restauration à un instant donné, rétention 30 jours · export logique quotidien par organisation, chiffré, conservé séparément |
| **Restauration** | **Testée chaque trimestre** sur environnement distinct, chronométrée, consignée. *Une sauvegarde jamais restaurée n'est pas une sauvegarde.* |
| **Observabilité** | Journaux corrélés par requête, organisation et projet · métriques : latence, durée de génération des états, profondeur de file, **divergences de soldes** · alerte sur toute divergence d'intégrité |
| **Hébergement souverain** | Même image, un schéma par installation, migrations idempotentes, retour arrière documenté, **aucune dépendance à un service en ligne pour fonctionner** |
| **Secrets** | Coffre dédié. Jamais en dépôt, jamais en variable d'image. |

---

# ANNEXE D — RÉCAPITULATIF DES CONTRÔLES DE SORTIE

À exécuter avant toute mise en service.

```
INTÉGRITÉ COMPTABLE
[ ] Écriture déséquilibrée refusée au COMMIT
[ ] Écriture comptabilisée non modifiable (déclencheur de base)
[ ] Période close inviolable, sans exception administrateur
[ ] Numérotation sans trou sous 10 processus concurrents
[ ] Balance = balance analytique = balance par accord, au centime

ISOLATION ET AUDIT
[ ] Test d'accès croisé en échec sur TOUTES les tables à org_id
[ ] Toute table à org_id possède sa politique de sécurité
[ ] Journal d'audit : altération détectée par le vérificateur
[ ] UPDATE sur le journal d'audit refusé au rôle applicatif

MONTANTS
[ ] Aucun FloatField dans le backend (test automatique)
[ ] Ventilation de cofinancement conservative (test de propriété)
[ ] Soldes budgétaires incrémentaux == recalcul complet

MOTEUR
[ ] Formule malveillante refusée (4 cas)
[ ] Référence circulaire refusée
[ ] Compte non mappé : génération bloquée, compte nommé
[ ] Assertion fausse : publication bloquée
[ ] États de référence : tous conformes
[ ] TER sur 200 000 lignes : < 3 s, 1 seule requête

CONFORMITÉ ET TRAÇABILITÉ
[ ] Aucun objet de configuration actif sans exigence source
[ ] Citation introuvable dans le document : refusée
[ ] Exigence active sans validateur : impossible (contrainte de base)
[ ] Import de profil : aucune exigence activée automatiquement
[ ] Dossier de conformité : 100 % des rubriques couvertes
[ ] Régénération : identique, ou écart nommant sa cause

RÉVERSIBILITÉ
[ ] Reprise à écart nul sur balance et cumul par accord
[ ] Import rejoué trois fois : aucun doublon
[ ] Export → instance vierge → rapport régénéré identique

CONFIGURATION DES ACCORDS
[ ] Deux versions actives qui se chevauchent : refusées par la base
[ ] Version approuvée : modification d'une table enfant refusée, SQL direct compris
[ ] Réallocation : événement tracé, approbateur ≠ demandeur, version créée
[ ] Profil incomplet : soumission refusée, manques nommés
[ ] Dérogation : résultat initial conservé, périmètre et durée limités
[ ] Concurrence : réallocations, soumissions, approbations, activations

ARCHITECTURE (les 17 tests de réception, T1 à T17)
[ ] Nouveau projet, nouveau bailleur, nouveau modèle : par PARAMÉTRAGE,
    sans application distincte et sans duplication des données
```

---

*Retour : [guide de démarrage](03_GUIDE_DEMARRAGE.md) · [lots L0 à L4](04_PLAN_LOTS_L0_A_L4.md) · [spécification fonctionnelle](01_SPECIFICATION_FONCTIONNELLE.md) · [architecture technique](02_ARCHITECTURE_TECHNIQUE.md)*
