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

> **Réalisation de L5-T03bis** (`niveau3_config/{models,services/decaissement}.py`, migrations `niveau3_config/0007-0008` et `decaissements/0003-0004`).
> - **Les quatre tables du §4bis** : `ProfilDecaissement`, `MethodeDecaissement`, `RegleCompteDesigne`, `RegleFinancementCategorie`. Les **ensembles fermés sont des CHECK** (régime, méthodes, pièces exigées, assiette de taxes, type de plafond) : ajouter une méthode est une migration, jamais un paramétrage. Contraintes en base : un seul minimum (montant OU pourcentage du plafond), taux dans ]0 ; 1], plafond fixe avec montant et plafond variable sans, jalons du profil dans l'ordre, statut validé ou actif avec validateur, rejet avec motif. Clés étrangères composites `(org_id, id)` et deux cohérences que seule la base tient : la **catégorie** d'une règle appartient à l'accord du profil, le **compte désigné** est du même projet et sans autre accord.
> - **La règle de calcul** : `montant_a_retirer = dépense × funding_rate`, sur l'assiette `tax_basis`, arrondi **vers zéro** au pas de la monnaie de tenue, comme la ventilation de cofinancement. Propriétés vérifiées (Hypothesis) : jamais plus que le taux n'autorise, jamais plus d'un pas de moins, croissant avec la dépense, la somme ligne à ligne ne dépasse jamais le taux sur le total, taxes comprises ≥ hors taxes. Une sous-catégorie **hérite** de la règle de sa catégorie parente la plus proche.
> - **Dans la demande de retrait** (`preparer_demande`, `date_demande`) : le profil est **résolu à la date de la demande** puis **figé** sur elle ; la méthode doit être autorisée ; le délai de décaissement, la date d'éligibilité du profil et la fenêtre de la catégorie sont contrôlés ; chaque catégorie doit avoir sa règle ; le **montant minimum** (valeur fixe, ou pourcentage du plafond du compte désigné) est exigé ; les **pièces exigées** sont calculées (une dépense au-delà de `full_doc_threshold` exige les copies de pièces `records` à la place de l'état certifié `soe`) et la soumission les exige, par le service et par la base. Chaque refus **nomme** la date, le seuil ou la règle.
> - **Persisté sur chaque ligne** : `regle_financement`, `profil_version`, `taux_applique`, `montant_a_retirer` (et le profil sur la demande), vérifiés par la base (règle du profil de la demande, de la catégorie de la ligne ou de son parent, taux égal à celui de la règle, montant ≤ dépense × taux). Les **soldes de catégorie et d'accord, le refus ultime et le total de la demande comptent désormais ce qui est demandé au bailleur**, pas la dépense. Un changement de régime ou de taux au 1ᵉʳ juillet laisse donc les demandes du premier semestre telles qu'elles étaient (tests).
> - **Sans profil** : un accord jamais paramétré garde le comportement de L4-T06 (montant à retirer = dépense, fixé par la base) ; si un profil a existé mais qu'aucun n'est en vigueur à la date, on **refuse**.
> - **Limites** : (1) l'assiette `net_of_taxes` est calculée dans `montant_a_retirer(…, taxes=…)` mais la demande ne reçoit pas encore les taxes de chaque dépense (le grand livre ne les distingue pas avant les schémas avec TVA) : elle les prend à zéro ; (2) le profil reste à **activer et versionner** proprement (un seul actif à la fois, immutabilité des enfants, rejet, concurrence) : c'est L5-T04, les tests créent ici des profils actifs directement ; (3) `profile_version_id` n'est persisté que sur la ligne de demande, pas encore sur la dépense validée ni sur les résultats de contrôle (L6) ; (4) l'aperçu de l'atelier (`verifier_disponible`) montre toujours les dépenses brutes ; (5) avec plusieurs comptes désignés, le pourcentage du minimum s'applique à la **somme** des plafonds fixes.

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

> **Réalisation de L5-T04** (`niveau3_config/services/activation.py`, migration `niveau3_config/0009`).
> - **Cycle commun** exigences et profils : `proposed`/`draft` → `validated` → `active`, ou `rejected` (motif obligatoire). `valider_*` et `rejeter_*` exigent l'habilitation `valider`, `activer_*` exige `parametrer` ; chaque transition est écrite dans le journal chaîné (acteur, état avant/après, motif). Une exigence ne se valide que si sa citation a été vérifiée sur le document en vigueur (L5-T02) ; un profil sans méthode ni règle ne se valide pas. Rien n'est jamais activé automatiquement.
> - **Un seul actif par période, garanti par la base** : `EXCLUDE USING gist` sur `(org_id, accord_id, daterange(valid_from, valid_to, '[)'))` pour les profils actifs, sur `(org_id, project_id, code, daterange(…))` pour les exigences actives. Fin exclue : V2 peut commencer le jour où V1 s'arrête.
> - **Activer une version ferme la précédente** : sa fin de validité est posée au `valid_from` de la nouvelle ; la précédente reste `active` pour les dates antérieures, donc une dépense du 15 juin garde la V2 quand l'accord passe en V3 en décembre. Une version qui prendrait effet avant le début de la version en vigueur (réécrire l'histoire) ou qui raccourcirait une version déjà programmée est refusée. Le verrou de ligne de l'accord (profils) ou de toutes les versions du code (exigences) sérialise les activations ; la base tranche en dernier recours (`ConflitActivation`).
> - **Immutabilité par déclencheur** : méthodes, comptes désignés et règles de taux refusent INSERT, UPDATE et DELETE dès que le profil n'est plus `draft`, y compris en SQL direct ; un profil approuvé ne change plus ses paramètres ni ne se supprime ; sa seule modification permise est la pose, une fois, de la fin de validité sur un profil actif. Les statuts ne reculent pas, `rejected` et `superseded` sont définitifs ; une exigence validée garde son contenu.
> - **`resoudre_configuration(project_id, date)`** : les exigences et profils actifs à la date, avec une empreinte SHA-256 ; la configuration d'un trimestre de 2027 est la même (même empreinte) avant et après une version d'exigence qui prend effet le 1ᵉʳ janvier 2028 (test).
> - **Limites** : (1) `superseded` existe dans les ensembles fermés mais aucun chemin ne l'utilise : une version fermée reste `active` jusqu'à sa fin de validité, pour que la résolution à une date passée continue de la trouver ; (2) la branche des générateurs de rapport sur `resoudre_configuration` relève de L6/L7, aucune génération actuelle ne lit les exigences ; (3) `profile_version_id` sur les dépenses validées et les résultats de contrôle attend L6 (il est déjà sur les lignes de demande) ; (4) le rejet d'une exigence n'a pas de colonne de motif, il est conservé dans le journal ; (5) pas encore d'interdiction de valider sa propre proposition (séparation des tâches) : à décider avec L5-T04bis (approbateur distinct).

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

> **Réalisation de L5-T04bis** (`niveau3_config/{models,services/{versions,reallocation,avenant,completude,comparaison}}.py`, migrations `niveau3_config/0010-0011`).
> - **Réallocation = événement.** Modèle `Reallocation` (accord, catégories source et cible, montant, devise, date d'effet, motif, justificatif, demandeur, approbateur, statut `requested`/`approved`/`rejected`, `profil_cree` en `OneToOne`). Garanties **en base** : montant > 0, source ≠ cible, approbation complète (approbateur nommé, **distinct du demandeur**, version créée, date), rejet motivé, clés composites `(org_id, id)`, catégories et version créée de l'accord de la réallocation, et une réallocation décidée ne se modifie ni ne se supprime.
> - **`approuver_reallocation`** verrouille dans cet ordre la réallocation, l'accord, les deux catégories (par identifiant), puis les versions du profil. Elle relit le **solde sous verrou** (`allocation − demandes en cours`, `SoldeCategorie`), refuse un solde insuffisant en nommant solde et montant, **copie** le profil en vigueur à la date d'effet avec les deux allocations modifiées, le valide et l'active (L5-T04) dans la même transaction, puis lie la réallocation. L'approbateur détient `valider` et `parametrer`. Ancienne version conservée et close à la date d'effet. Tests : deux réallocations simultanées de 80 sur une source de 100 → une seule aboutit, allocation exacte 20, somme conservée ; deux approbations simultanées de la même réallocation → une seule version.
> - **Avenant** (`enregistrer_avenant`) : crée dans la même transaction la nouvelle version (dates et allocations de l'avenant), enregistre l'avenant avec l'identifiant de cette version (un avenant ne se modifie jamais, donc la version est créée **avant** lui et validée **après**), puis la valide : la complétude compare alors les allocations au **montant révisé**. Tout ou rien (test : profil incomplet → ni avenant ni version). Accord sans profil : avenant seul ; accord qui a eu un profil mais n'en a aucun en vigueur à la date : refusé.
> - **Complétude** (`verifier_completude`, appelée par `valider_profil`) : *bloquantes* — dates incohérentes, aucune méthode, méthode activée sans pièces exigées, aucune catégorie, allocations > montant de l'accord à la date d'effet, exigence source non validée, chevauchement avec une version active ; *avertissements* — taux de 100 %, aucune exigence source, aucune date d'éligibilité, aucun compte désigné. Accord, bailleur et devise de référence ne sont pas recontrôlés : la base les garantit (clés non nulles). L'écart budget / financements n'est **jamais** une anomalie (test).
> - **Comparaison** (`comparer_versions`) : paramètres, méthodes, catégories (allocations et taux, par code) et comptes désignés, en identiques / modifiés (champ par champ) / ajoutés / supprimés ; refus de comparer deux accords.
> - **Écarts au plan, à connaître** : (1) *avertissements « acceptables avec justification selon les droits »* : la règle de droits n'étant pas spécifiée, l'avertissement ne bloque pas ; il est **tracé dans le journal** avec la justification fournie par qui valide (vide sinon) ; (2) *exigence critique sans source documentaire* : une exigence a toujours un document (clé non nulle) ; le contrôle porte sur l'exigence source du profil, qui doit être validée ou active ; (3) **la soumission des demandes de retrait (L4-T06) plafonne toujours sur `Categorie.plafond`**, pas sur l'allocation de la version de profil : une réallocation déplace l'allocation et le solde qu'elle contrôle, mais ne modifie pas ce plafond ; aligner les deux est une décision à prendre avec la fin de L5 ; (4) *devise* : une réallocation exige deux catégories de même devise, sans conversion ; (5) deux réallocations ne peuvent pas prendre effet le même jour (la seconde choisit une date postérieure).

### L5-T05 — Profils de bailleurs

**Fichier.** `backend/niveau2_profils/`

`ProfilBailleur` : bibliothèque réutilisable — références documentaires, familles d'états, modèles, règles de présentation, périodicités et délais types, contrôles, formats, nomenclatures.

> **Règle absolue :** un profil **n'impose jamais automatiquement** ses exigences à un projet. Il les met à disposition. Ce sont les documents contractuels du projet qui déterminent lesquelles s'appliquent.
>
> Techniquement : importer un profil crée des exigences en statut **`proposed`**, jamais `active`. Il n'existe aucun chemin de code permettant le contraire.

**Contrôle.** Importer un profil dans un projet ne produit **aucune** exigence active. Un test l'asserte explicitement.

---

> **Réalisation de L5-T05** (`backend/niveau2_profils/`, migrations `0001-0002`, `etayer_exigence` dans `niveau3_config/services/exigences.py`).
> - **Bibliothèque** : `ProfilBailleur` (code, version, libellé JSONB, bailleur facultatif, brouillon → publié avec publicateur et date) et `ElementProfil` (huit types fermés : références documentaires, familles d'états, modèles, règles de présentation, périodicités et délais types, contrôles, formats d'exportation, nomenclatures ; contenu JSON ; une `exigence` type facultative). Un profil **publié** ne se modifie ni ne se supprime et ses éléments non plus (déclencheurs, y compris en SQL direct) : on publie une nouvelle version. Clés composites `(org_id, id)` et RLS sur les deux tables. L'habilitation est `parametrer` sur l'organisation (le profil n'est pas lié à un projet).
> - **La règle absolue, à deux niveaux.** (1) `importer_profil` crée **uniquement** des exigences `proposed`, par un seul chemin (`_proposer_depuis_element`) qui fixe le statut en dur ; (2) la **base** refuse, par déclencheur, toute exigence portant un `donor_profile_id` qui ne naît pas `proposed`, ou qui vient d'un profil non publié : testé en création directe `active` et `validated`. `donor_profile_id` est désormais une clé étrangère composite vers le profil de la même organisation.
> - **Une exigence importée ne se fait pas passer pour sourcée** : sa citation vaut « À étayer par un passage du document contractuel du projet » et son empreinte de vérification est vide. `valider_exigence` la refuse donc (L5-T04) tant que `etayer_exigence` n'a pas retrouvé, **littéralement dans le document du projet**, un passage qui la justifie (même contrôle qu'à la proposition, L5-T02). Le test mène une exigence importée jusqu'à `active`, chaque étape par un humain habilité.
> - **Importer deux fois ne duplique rien** (service, et index unique partiel sur les propositions en attente par projet, code et profil) ; un profil se réutilise d'un projet à l'autre sans changer ; le document doit être celui du projet et en vigueur.
> - **Limites** : (1) les éléments autres que les exigences (modèles, nomenclatures, formats…) sont stockés mais **rien ne les consomme encore** : le moteur de rapports (L6/L7) et le mapping les liront ; (2) l'import crée une version `proposed` de plus quand le code existe déjà dans le projet, sans comparer avec l'exigence en vigueur ; (3) la mention « lorsque requis » de chaque élément relève de L5-T06 (interface) ; (4) la `valid_from` d'une exigence importée vaut la date du jour et aucun service ne la modifie encore avant validation (elle se fige à la validation) : à prévoir avec l'interface de revue des propositions.

### L5-T06 — Le profil Banque mondiale

Familles d'états : rapport financier intermédiaire, état des ressources et emplois, dépenses par composante / activité / catégorie / source, activité et rapprochement du compte désigné, prévisions de trésorerie et suivi des avances, demandes de retrait, états annuels pour l'audit.

Délai type : **45 jours après la fin de chaque trimestre civil** sous les conditions générales IDA.

> **Dans l'interface, chaque élément du profil porte la mention « lorsque requis ».** Il n'existe pas de modèle Banque mondiale universel : le DFIL du projet décide. Présenter un profil comme universel serait une erreur de conception et une faute commerciale.

---

> **Réalisation de L5-T06** (`backend/niveau2_profils/{catalogue/banque_mondiale.json,services/{catalogue,presentation}.py,management/commands/charger_profil_bailleur.py}`).
> - **Un profil livré est une donnée, pas du code** : un fichier du catalogue, chargé par `charger_profil` (commande `charger_profil_bailleur`) à travers les mêmes services que la saisie manuelle (mêmes contrôles, même journal). Il se charge en **brouillon** ; le publier est un acte distinct de `parametrer`. Recharger ne duplique rien. Ajouter un autre bailleur (L10) = ajouter un fichier.
> - **Contenu Banque mondiale** : la référence aux conditions générales de l'IDA et les **sept familles d'états** du plan (rapport financier intermédiaire ; état des ressources et emplois ; dépenses par composante, activité, catégorie et source ; activité et rapprochement du compte désigné ; prévisions de trésorerie et suivi des avances ; demandes de retrait ; états annuels pour l'audit). **Seul délai renseigné : 45 jours après la fin de chaque trimestre civil, pour le rapport financier intermédiaire** ; aucun autre délai ni périodicité n'est inventé, le DFIL du projet les fixera. Toutes les exigences livrées sont `facultatives` : le profil ne rend rien obligatoire d'office.
> - **« Lorsque requis » sur chaque élément** : `ElementProfil.mention` ; `presenter_profil` (point de passage de tout écran, guide ou export) ajoute la mention à chaque élément et l'avertissement « ce profil n'est pas un modèle universel » en tête ; la description du profil le dit aussi. Des tests de catalogue (logique pure) interdisent d'y glisser une exigence obligatoire, un second délai, ou une description qui présenterait le profil comme universel.
> - **Limites** : (1) il n'y a pas encore d'interface : la mention vit dans la couche de présentation, que l'interface devra emprunter ; (2) seule la famille « rapport financier intermédiaire » a un délai ; les modèles de rapport (structure, rubriques, formules) ne sont pas livrés avec le profil : ils relèvent des modèles de L7 ; (3) la mention est constante : une base ne l'impose pas (un profil saisi à la main sans passer par `presenter_profil` ne la porterait pas).

### L5-T07 — Le guide de configuration généré

Depuis le registre, produire un PDF lisible : chaque exigence active, sa source, son mapping, ses contrôles, sa périodicité, son validateur.

> **Pourquoi c'est important.** Les équipes d'unités de gestion tournent constamment. C'est là que meurent les installations concurrentes : le savoir du paramétrage reste chez un consultant d'intégrateur. Ici, il reste dans le système et s'imprime.

**Contrôle.** Le guide d'un projet configuré est lisible par un comptable qui n'a jamais vu le logiciel, et lui permet de dire **pourquoi** chaque rubrique existe.

---

> **Réalisation de L5-T07** (`backend/niveau3_config/services/{guide,pdf_minimal}.py`, commande `generer_guide_configuration`).
> - **`generer_guide(utilisateur, project_id, date)`** rend un PDF à partir du registre, à la **configuration résolue à la date** (L5-T04) : (1) chaque exigence **active** — rubrique, nature (obligatoire / conditionnelle avec sa condition / facultative), périodicité et délai, dates de validité, **document source et passage cité** (annexe, page, paragraphe, extrait), **validateur nommé et date**, origine (saisie pour le projet, ou issue d'un profil de bailleur et étayée), et **ce qu'elle justifie** (mappings, rubriques, contrôles rattachés, nommés) ; (2) les **profils de décaissement en vigueur** (régime, jalons, méthodes et pièces exigées, taux par catégorie, comptes désignés) ; (3) les propositions et validations **en attente, dites non appliquées** ; (4) les **points d'attention** : ce qui est configuré sans exigence source. L'empreinte de la configuration est imprimée.
> - **Sans dépendance** : un écrivain de PDF minimal (polices standard, accents français, repli de ligne, pagination, numéros de page). **Déterministe** : mêmes données et même date, mêmes octets. L'habilitation est `consulter` ; la génération est journalisée avec l'empreinte du document produit.
> - **Contrôle du plan, démontré par des tests** : le texte extrait du PDF seul permet de dire quoi, d'où (document et paragraphe), qui l'a validé et quand, et pour quel mapping chaque exigence existe ; une proposition n'apparaît jamais parmi les exigences actives ; une exigence qui prend effet en 2028 ne change pas la configuration d'un guide de 2027 (même empreinte).
> - **Limites** : (1) les libellés de ce qu'une exigence justifie ne sont lus que pour les types branchés sur `SOURCES` (aujourd'hui les mappings) ; une rubrique ou un contrôle non branché apparaît par sa référence abrégée jusqu'à L6/L7, qui doivent enregistrer leur source (le point d'extension existe) ; (2) le guide n'a pas de mise en page graphique (texte structuré, titres, pied de page) : il est lisible et imprimable, la mise en forme soignée relève de L7 ; (3) un guide régénéré après la clôture d'une version dit sa fin de validité (« au … exclu »), information vraie mais absente d'un guide imprimé plus tôt ; la configuration résolue, elle, ne change pas ; (4) un utilisateur supprimé apparaît par son identifiant.

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

> **Réalisation de L6-T01a** (`backend/niveau4_reporting/controles/conditions.py`). *L6-T01 est livrée en trois temps : T01a le langage de conditions (ici), T01b les contrôles, leur journal, leurs résultats et les codes d'erreur, T01c la bibliothèque des huit familles et les contrôles de risque.*
> - **Le langage, fermé** : les dix-sept opérateurs du plan (`eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `est_renseigne`, `est_absent`, `avant`, `apres`, `entre`, `est_vrai`, `est_faux`, `somme_lte`, `nombre_eq`), et aucun autre : un test compare le jeu au tableau du plan. `entre` est semi-ouvert `[du, au[` (propriété vérifiée sur toutes les dates : `avant`, `entre` et « à partir de `au` » partitionnent le temps).
> - **Une expression n'est jamais du texte** : `{"type_regle": …, "conditions": [{"champ", "op", "valeur"}, …]}`, validée par un **schéma propre à chaque type de règle** (codification, pièces, éligibilité, budget, trésorerie, avances, rapport, cohérence, risque : un champ d'un type est refusé dans un autre). Refusés **à l'enregistrement**, avec un message qui nomme la condition : opérateur inconnu, champ hors schéma, opérateur incompatible avec le type du champ, valeur absente ou superflue, date non ISO, intervalle vide ou à l'envers, liste vide ou de plus de 200 valeurs, plus de 20 conditions, clés inconnues.
> - **Règles 1 et 5** : un montant s'écrit en chaîne ou en entier (un nombre à virgule flottante est refusé) ; le contexte d'évaluation doit fournir des `Decimal` (un `float`, un booléen pour un entier ou un horodatage pour une date lève `TypeError`) ; la somme de `somme_lte` est exacte (0,1 + 0,2 ≤ 0,30). Un test d'analyse syntaxique interdit `eval`, `exec`, `compile`, `getattr`, `open`, les imports dynamiques et `os`/`subprocess` dans le module ; une charge (`__import__('os')…`, `DROP TABLE`) placée dans une valeur n'est que du texte comparé.
> - **Décisions à connaître** : (1) les conditions d'une expression se lisent ensemble, en ET implicite (le plan ne prévoit ni `et` ni `ou` : ce ne sont pas des opérateurs) ; (2) une valeur absente ne satisfait aucune comparaison (`neq` et `not_in` sont vrais : l'absence ne vaut rien) ; un booléen absent n'est ni vrai ni faux ; (3) les champs des schémas sont ceux que les contextes de T01c devront fournir : en ajouter un est une décision de schéma, pas de paramétrage.
> - **Limites** : le langage n'a pas de condition sur les éléments d'une liste (« une pièce de type X, validée ») : le contexte de la règle de pièces (T01c) fournit les décomptes déjà filtrés. Rien n'est encore enregistré en base : T01b.

> **Réalisation de L6-T01b** (`backend/niveau4_reporting/controles/{models,services,sources}.py`, `backend/core/erreurs.py`, migrations `controles/0001-0002`).
> - **`Controle`** : objet de configuration versionné (`[valid_from, valid_to[`), code, libellé JSONB, type de règle, sévérité (`bloquant`/`avertissement`/`information`), mode **automatique** (une `expression`) ou **manuel** (« à vérifier » : aucune expression), condition d'applicabilité facultative, action corrective. Enregistré par `creer_controle`, **qui refuse à l'enregistrement** (`ErreurMetier` `REGLE_INVALIDE`, rien n'est écrit) toute condition hors schéma ou opérateur inconnu. Cycle brouillon → validé → actif (ou rejeté avec motif), tenu par la base comme les exigences et les profils : un seul actif par code et par période (`EXCLUDE`), contenu figé une fois validé, statut qui ne recule pas, fin de validité posée une fois, seul un brouillon se supprime. Branché sur la règle de L5-T03 : un contrôle actif sans exigence source est signalé comme orphelin.
> - **Résultats** : `reussi`, `bloquant`, `avertissement`, `information` (selon la sévérité du contrôle), `a_verifier`, et `non_applicable` — noté **au journal seulement**.
> - **Journal de chaque évaluation** (`EvaluationControle`, **ajout seul** pour tout rôle) : contrôle et version, projet, objet contrôlé, résultat, sévérité, valeur constatée, valeur attendue, message, action corrective, **version du profil de décaissement résolue à la date de l'opération** (si l'accord est fourni), exigence et clause sources (l'exigence **active** à la date qui justifie le contrôle), date, **déclencheur** (un utilisateur, ou un service nommé : jamais l'un sans l'autre, par `CHECK`). La base refuse une évaluation qui ne décrit pas la bonne version du contrôle ou le bon projet.
> - **Le moteur est appelé, jamais réimplémenté** : `evaluer_controle` (un contrôle) et `evaluer_tous` (tous les actifs d'un type de règle) sont le point d'entrée des autres modules. Un contrôle non actif à la date n'est pas évalué (`AUCUNE_CONFIGURATION_A_LA_DATE`).
> - **« À vérifier » et étape suivante** : `trancher` (habilitation `valider`, décision motivée `conforme`/`non_conforme`, en ajout seul, seulement sur un contrôle « à vérifier ») ; `exiger_controles_tranches` refuse d'avancer (`CONTROLE_BLOQUANT`, nommant chaque contrôle et sa raison) tant que la dernière évaluation d'un contrôle sur l'objet est `bloquant`, « à vérifier » non tranché, ou tranchée « non conforme ». C'est la garde que le workflow de validation (T02) branchera sur l'étape 5.
> - **Codes d'erreur stables** : `CodeErreur` (les douze du plan) et `ErreurMetier` (code, message, `vers_dict`) dans `core/erreurs.py` ; T01b emploie `REGLE_INVALIDE`, `CONTROLE_BLOQUANT`, `AUCUNE_CONFIGURATION_A_LA_DATE`, `CONFLIT_DE_PERIODE`, `TRANSITION_INTERDITE`. Les autres attendent l'API et le workflow.
> - **Limites** : (1) le schéma JSON de l'expression n'est tenu que par le service : la base garantit seulement que c'est un objet (un contrôle inséré en SQL direct avec une expression absurde échouerait à l'évaluation, pas à l'insertion) ; (2) la dérogation à un contrôle bloquant (auto-dérogation refusée, expiration, historique) relève de T02 ; ici seule la décision sur un « à vérifier » existe ; (3) aucun contrôle n'est encore livré : la bibliothèque des huit familles, les contrôles de pièces et de risque, et les contextes qui nourrissent les schémas, sont T01c ; (4) le moteur n'est pas encore appelé par la comptabilité, les dépenses ou les demandes.

> **Réalisation de L6-T01c** (`backend/niveau4_reporting/controles/{bibliotheque,contextes,decision}.py`, `installer_bibliotheque` dans `services.py`, migrations `controles/0003-0004`). *Avec T01a et T01b, L6-T01 est complète.*
> - **Bibliothèque livrée, en données** (conditions du langage fermé, jamais du code) : **codification** (catégorie, source, axe 1), **budget** (ligne, catégorie, allocation, plafond d'accord), **pièces** (doublon de facture ; pièce manquante pour une dépense destinée à un état certifié), **trésorerie** (écart de rapprochement non justifié ; solde du compte désigné), **avances** (avance non justifiée ; au-delà du délai), **rapport** (rubrique obligatoire vide ; **compte non mappé** ; assertion non vérifiée), **cohérence** (entre états, entre périodes, rupture de cumul), plus **trois contrôles de risque** paramétrés (catégorie consommée au-delà d'un seuil, avance non apurée depuis plus d'un délai, rejets répétés). Les contrôles de plafond s'écrivent sur le **reste** (« le disponible est positif ou nul ») ; un plafond absent rend le contrôle **non applicable**, noté au journal, plutôt que de le déclencher.
> - **Trois familles par fabrique, parce que le projet les configure** : `regle_de_piece` (type exigé, validation exigée ou non, portée cumulative : catégorie, méthode, seuil de montant, nature), `eligibilite_nature|zone|periode|beneficiaires_exclus` (période semi-ouverte `[du, au[`) et les seuils de risque. **Aucune liste universelle de justificatifs.**
> - **Pièces** : `Controle.parametres` (`type_piece`, `validee`) fige la règle ; le moteur ne retient, parmi les pièces fournies, que celles **du bon type, rattachées à l'opération**, et validées si la règle l'exige : une pièce du mauvais type ou non rattachée est refusée comme absente (une pièce au rattachement inconnu aussi). Les paramètres se figent à la validation, comme le reste du contenu.
> - **`decision.py`** : la décision d'un contrôle (applicabilité, pièces, résultat) en logique pure, partagée par le service et testée sans base. **`contextes.py`** : `contexte()` refuse un champ hors schéma ou d'un mauvais type (une faute de frappe serait sinon lue comme « absent ») ; `contexte_depense` lit une ligne comptable (montant, date, catégorie, source, compte, axes, référence de facture) ; `facture_en_double` = **même référence de document pour le même tiers** dans une autre écriture (sans référence ou sans tiers, on n'affirme rien) ; `contexte_avance` lit la situation d'une avance (L4-T07).
> - **Installation** : `installer_bibliotheque` crée les contrôles **en brouillon**, jamais validés ni activés (règle 9), sans recréer un code déjà présent, avec un sous-ensemble possible et un code inconnu refusé.
> - **Contrôle du plan** : chaque contrôle livré a un test qui le déclenche **et** un test qui prouve qu'il ne se déclenche pas à tort ; un test de couverture refuse un contrôle livré sans ses deux cas ; la sévérité attendue de chacun est écrite à part de sa définition (sans quoi le test la comparerait à elle-même) ; les écarts sont des anomalies dans les deux sens.
> - **Limites** : (1) le moteur n'est toujours pas appelé par la comptabilité, les dépenses et les demandes : L6-T01 livre le moteur, la bibliothèque et les constructeurs de contexte, le branchement relève des tâches qui en ont besoin (workflow, génération) ; (2) la nature, la zone, le bénéficiaire, la méthode et les pièces d'une dépense ne sont pas portés par le grand livre : l'appelant les fournit ; (3) l'axe obligatoire est l'axe 1 par défaut : un autre axe obligatoire s'obtient en créant le même contrôle sur ce champ ; (4) pas de contrôle livré sur les marchés (le plan les cite comme appelants, ils n'existent pas encore).

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

> **Réalisation de L6-T02a — justifications et dérogations** (`backend/niveau4_reporting/controles/derogations.py`, modèles `Justification` et `Derogation`, migrations `controles/0006-0007`, `tests/test_derogations_bd.py`, 17 tests, 5 mutations vérifiées). *Le circuit à étapes (T02b) reste à faire.*
> - **Justification** : textuelle, nominative (nom figé), en ajout seul. Elle **explique** et ne lève aucun blocage.
> - **Dérogation** : demandée (`saisir`), décidée une seule fois par une AUTRE personne habilitée (`valider`) ; l'égalité demandeur/approbateur est refusée par le service ET par une contrainte de base. Périmètre déduit de l'évaluation par la base (contrôle, projet, objet) ; validité `[valide_du, valide_jusquau[`. La ligne est verrouillée à la décision, un trigger interdit toute seconde décision.
> - `controles_en_attente` / `exiger_controles_tranches` acceptent une `date` et ne comptent plus un résultat bloquant couvert par une dérogation approuvée et valide ; le résultat initial n'est jamais modifié. `dossier_de_conformite` rend le fil échec → justification → dérogation.
> - **Limites assumées** : il n'existe pas d'opération « approuver » dans les habilitations (ensemble fermé) : l'approbation exige `valider`. Le document justificatif est une **référence** textuelle, pas encore un lien vers un document stocké. Une dérogation ne vise que la dernière évaluation du contrôle sur l'objet.

**Circuit borné.** Conformément à la note 06 §3.2 : 1 à 5 étapes, chacune avec un rôle requis, une condition d'entrée optionnelle (seuil de montant, catégorie, bailleur) et un motif obligatoire en cas de rejet. Pas de moteur de processus général.

> **Réalisation de L6-T02b — le circuit de validation** (`backend/niveau4_reporting/controles/circuit.py`, modèles `Circuit`, `EtapeCircuit`, `DemandeValidation`, `DecisionEtape`, migrations `controles/0008-0009`, `tests/test_circuit_validation_bd.py`, 15 tests, 5 mutations vérifiées ; le test d'isolation de toutes les tables peuple les nouvelles tables). *Avec T02a, L6-T02 couvre les étapes 4 à 6 du workflow.*
> - Circuit **versionné** `[valid_from, valid_to[` (une version close la précédente, aucune modification, pas de chevauchement garanti par EXCLUDE), de **1 à 5 étapes** (CHECK en base), chacune avec une habilitation requise (ensemble fermé), un nom dans chaque langue, une condition d'entrée facultative bornée (`montant_min`, `categories`, `bailleurs`) et un drapeau `exige_controles_tranches`.
> - `decider_etape` verrouille la demande, exige que l'étape signée soit l'étape COURANTE (deux signatures concurrentes : une seule prend effet), l'habilitation de l'étape, un signataire différent du demandeur, un motif au rejet. Si l'étape l'exige, les contrôles de l'objet doivent être tranchés (dérogations approuvées comprises) : refusé au serveur avec `CONTROLE_BLOQUANT`, rien n'est signé ; un rejet reste possible.
> - **Limites assumées** : les étapes 1-3 (extraction, génération, exécution des contrôles) et 7-8 (export, archivage de la version transmise) dépendent des rapports (L7) et ne sont pas dans ce circuit. Le contexte d'une demande (montant, catégorie, bailleur) est fourni par l'appelant, figé à l'ouverture. Un même signataire peut signer plusieurs étapes s'il détient les habilitations (seule la séparation avec le demandeur est imposée). Pas d'interface HTTP : services seuls.

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

> **Réalisation de L6-T03** (`backend/niveau4_reporting/publication/scellement.py`, `tests/test_scellement.py`, 18 tests, 5 mutations vérifiées). Écarts avec l'esquisse, voulus : SHA-256 aussi pour le jeu de données (le plan proposait MD5) ; lecture dans la vue `moteur_ligneecriture` (jamais le grand livre) ; montants sous forme canonique (`10.50`, `10.5` et `1E+1` ne donnent pas deux empreintes) ; `float` et ensembles refusés ; charge versionnée (`schema`).
> - « Modifier une ligne source » : les lignes comptabilisées sont immuables, donc le test ajoute ou contre-passe une écriture dans le périmètre. L'altération directe d'un montant (administrateur hors déclencheurs, `session_replication_role = replica`) est aussi détectée, en débit comme en crédit.
> - **Limites assumées** : il n'existe pas encore d'objet « rapport publié » ni de modèle d'état en base ; `sceller` accepte tout objet qui expose les champs du plan (protocole `Scellable`). Le modèle `published_report`, `generer` et l'enregistrement du scellé viennent avec T04. L'empreinte du jeu de données porte id, compte, date, débit, crédit, devise, taux, accord et catégorie : une colonne ajoutée plus tard à la vue ne la change pas sans montée de `schema`.

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

> **Réalisation de L6-T04** (`backend/niveau4_reporting/publication/{models,rapports}.py`, migrations `publication/0001-0002` et `moteur/0005`, `tests/test_regeneration_bd.py`, 9 tests, 5 mutations vérifiées ; suite complète verte en 6 shards).
> - `RapportPublie` : ajout seul pour tout rôle (trigger), RLS, clé composite vers le projet. Il garde une COPIE du modèle d'état (pas une référence), les paramètres, les versions de mappings (id et numéro) et les valeurs `rubrique/colonne` en montants canoniques ; `seal` = `sceller()` de T03.
> - `publier_rapport` (habilitation `publier`) génère, scelle, enregistre, journalise ; une assertion fausse ou un mapping incomplet empêche toute publication. `regenerer` rejoue avec le modèle, les mappings (chargés PAR ID, même remplacés depuis) et les paramètres d'alors : même scellé = identique ; sinon écarts par rubrique et colonne (`Ecart.difference`) et **causes nommées** : chaque écriture comptabilisée après la publication dans le périmètre, avec numéro de pièce, compte, montant signé et, pour une contre-passation, le numéro de la pièce contre-passée.
> - La vue `moteur_ligneecriture` gagne `comptabilisee_le` et `contrepasse_ecriture_id` (colonnes ajoutées en fin, `security_invoker` conservé).
> - **Limites assumées** : le différentiel ne nomme que les écritures arrivées depuis ; une exigence révisée ou un mapping remplacé n'apparaît pas comme cause (le rejeu les ignore par construction). Un écart SANS écriture nouvelle (altération hors déclencheurs) est signalé `inexpliquee` plutôt qu'expliqué. La `config_version` est fournie par l'appelant (pas encore résolue depuis le registre) ; la période (`period_from/to`) aussi. Pas d'interface HTTP.

**Contrôle.** Publier un rapport, ajouter une écriture dans la période, régénérer : le différentiel **nomme l'écriture ajoutée et son montant**. Ne vous contentez pas d'un « écart détecté ».

---

### L6-T05 — Génération Excel et PDF

Excel via `openpyxl` : mise en forme conforme au modèle, montants en type numérique à 2 ou 4 décimales selon la devise, **jamais en texte**.
PDF via Typst ou WeasyPrint, **compatible droite-à-gauche**.

Les fichiers produits sont stockés avec leur empreinte dans `published_report.files`.

> **Réalisation de L6-T05** (`backend/niveau4_reporting/publication/exports.py`, modèle `FichierRapport`, migrations `publication/0003-0004`, `tests/test_exports_rapport_bd.py`, 12 tests, mutations vérifiées).
> - **Excel** (openpyxl) : montants en vrais nombres (`data_type == "n"`) au format de la devise (0 à 4 décimales selon `Devise.decimales` : DJF 0, USD 2, TND 3), feuille en `rightToLeft` pour une langue de droite à gauche, **octets déterministes** (dates d'entrée du ZIP et date de modification fixées sur la date de publication ; openpyxl pose « maintenant » à l'enregistrement, ce que la première version du test a révélé).
> - **Stockage** : `FichierRapport` (une ligne par rapport, format et langue ; ajout seul) garde le contenu et son SHA-256 ; la base vérifie que l'empreinte et la taille correspondent au contenu, et `lire_fichier` la RECALCULE : un fichier altéré lève `FichierAltere`. Le plan parlait de `published_report.files` : le rapport publié étant immuable, les fichiers sont dans une table à part.
> - **Écarts et limites assumés** : (1) le PDF utilise l'écrivain minimal du projet (latin, polices standard), pas Typst ni WeasyPrint (absents de l'environnement) : **le PDF de droite à gauche est refusé explicitement** (`exports.pdf_droite_a_gauche`) au lieu de produire un PDF faux ; il reste à faire quand l'arabe sera livré. (2) Le contenu est en base (`bytea`) : à reprendre vers un stockage objet quand les volumes l'exigeront. (3) Le « format conforme au modèle » se limite aux libellés, colonnes, nombres et gel de volet ; pas de gabarit bailleur imposé.

**Contrôle.** Le fichier téléchargé a exactement l'empreinte enregistrée.

---

### L6-T06 — Le calendrier des obligations

Généré **automatiquement depuis le registre** : chaque exigence périodique produit ses échéances (`periodicity` + `due_offset_days`).

Tâche de fond quotidienne : exécuter les contrôles **avant** l'échéance, alerter, escalader.

> **L'écran d'accueil est ce calendrier, à feux de signalisation — pas une arborescence de menus.** Le métier réel d'un responsable administratif et financier est de ne jamais rater une échéance et de ne jamais faire rejeter un rapport. Le produit doit être organisé autour de cela.

> **Réalisation de L6-T06** (`backend/niveau3_config/services/calendrier.py`, modèle `Echeance`, migrations `niveau3_config/0012-0013`, commande `verifier_echeances`, `tests/test_calendrier_bd.py`, 13 tests, 8 mutations vérifiées ; suite complète verte).
> - `generer_calendrier(projet, année)` (habilitation `parametrer`, idempotent) produit, pour chaque exigence ACTIVE périodique avec délai, une échéance par période civile à `fin de période + due_offset_days` (T1 + 45 jours = 15 mai, puis 14 août, 14 novembre, 14 février). Elle n'échéance une période que si l'exigence est en vigueur à sa fin (`[valid_from, valid_to[`). Une exigence périodique SANS délai est listée (`sans_delai`), jamais échéancée : aucun délai inventé. Une exigence « à l'événement » n'a pas de calendrier.
> - Une exigence remplacée ou retirée **annule** ses échéances à remettre (jamais de suppression ; les remises ne bougent pas). La base interdit de changer la date ou l'exigence d'une échéance et de réécrire une remise.
> - Le **feu** (vert, orange à 15 jours ou moins, rouge si dépassée) se calcule, il ne se stocke pas. `alertes_du_jour` : imminente (≤ 15 j), en retard, escalade (> 7 j de retard). `verifier_echeances` (tâche quotidienne) les liste et sort en code 2 s'il y a une escalade.
> - **Limites assumées** : périodes civiles uniquement (pas d'exercice décalé) ; seuils 15 et 7 jours fixés dans le code, pas encore paramétrables par projet ; aucune notification n'est envoyée (la commande liste, l'ordonnanceur relaie) ; la tâche n'**exécute pas** encore les contrôles avant l'échéance (le plan le demande) : cela suppose de savoir quel objet contrôler pour un rapport donné, donc les modèles d'états en base ; l'écran d'accueil à feux est du front-end et n'est pas dans ce dépôt. `marquer_remise` reçoit l'identifiant du rapport publié sans le vérifier.

**Contrôle.** Activer une exigence trimestrielle à 45 jours génère les quatre échéances de l'exercice, aux bonnes dates.

---

### L6-T07 — La simulation de revue bailleur

Rejouer sur un rapport en préparation les motifs de rejet connus du bailleur, et rendre un **avis go / no-go avec liste d'actions**.

Enregistrer le résultat des soumissions réelles pour alimenter l'**indicateur phare : le taux de rapports acceptés au premier envoi**.

> **Réalisation de L6-T07** (`backend/niveau4_reporting/publication/revue.py`, modèles `MotifRejet`, `SimulationRevue`, `SoumissionBailleur`, migrations `publication/0005-0006`, `tests/test_revue_bailleur_bd.py`, 14 tests, 7 mutations vérifiées ; suite complète verte). *Avec T07, le lot L6 est livré tâche par tâche ; son contrôle de sortie reste à exécuter.*
> - `simuler_revue` rejoue sur l'objet en préparation les contrôles ACTIFS : ceux du type avances sur chaque avance échue (via le moteur, contexte `contexte_avance`), les contrôles bloquants non traités de l'objet (dérogations approuvées prises en compte) et ses avertissements. **Avis** : `no_go` si un constat est bloquant OU recoupe un motif de rejet connu ; `go_reserves` s'il y a d'autres constats ; `go` sinon. Chaque constat porte son message dans chaque langue (l'avance et ses jours de retard sont nommés), l'action corrective du contrôle et, s'il y a lieu, le motif connu avec sa source. La simulation est gardée (ajout seul) et écrit au journal d'évaluation (déclencheur : service `simulation_revue`).
> - `MotifRejet` : donnée (un motif appris d'un rejet s'ajoute sans déployer), relié au contrôle qui le détecte, désactivable, jamais supprimé.
> - `enregistrer_envoi` / `enregistrer_issue` : envois numérotés par (projet, rapport, période) sous verrou, un nouvel envoi n'est possible qu'après l'issue du précédent, l'issue se pose UNE fois, un rejet exige son motif. `taux_acceptation_premier_envoi` : acceptés / décidés **sur les premiers envois** de la fenêtre ; `None` sans issue connue (aucun taux inventé).
> - **Limites assumées** : seuls les contrôles du type avances sont rejoués sur des objets que la simulation sait énumérer ; les autres types (dépenses, budget) ne sont vus que par leurs évaluations déjà journalisées sur l'objet, faute d'énumération des objets d'un rapport avant les modèles d'états en base. La règle « un motif connu force le no-go » est un choix de prudence, pas une exigence du plan. L'indicateur n'est pas ventilé par bailleur ni comparé à l'avis simulé (calibrage) ; pas d'API HTTP.

**Contrôle.** Un rapport avec une avance non justifiée au-delà du délai reçoit un avis `no-go` qui nomme l'avance et le nombre de jours de retard.

> **Contrôle de sortie de L6** (`backend/tests/test_sortie_l6_bd.py`, 2 tests ; suite complète verte en 6 shards). Le premier test vérifie que chacun des contrôles du plan de L6 (T01 à T07 et l'annexe D « assertion fausse : publication bloquée ») renvoie à un test qui existe. Le second déroule le scénario de bout en bout, chaque étape par un humain habilité : bibliothèque installée en brouillon puis validée et activée, motif de rejet connu, exigence trimestrielle (quatre échéances, la première le 15 mai), circuit de validation en deux étapes, avance qui traîne ; la revue dit `no_go` en nommant l'avance et son retard et en reconnaissant le motif, passe en `go` après justification ; publication scellée rejouée à l'identique ; validation par le responsable financier puis le coordonnateur ; export Excel et PDF vérifiés par empreinte ; remise de l'échéance, premier envoi accepté, taux 1 ; une écriture tardive est ensuite NOMMÉE (pièce et montant) par le rejeu, le rapport remis ne bouge pas.
> - **Ce que le scénario ne prouve pas** (couvert par les tests propres de chaque tâche, mutations vérifiées) : le blocage de l'étape de validation par un contrôle bloquant, l'altération d'un fichier exporté, les concurrences.
> - **Restent hors de ce contrôle** (annexe D) : « dossier de conformité : 100 % des rubriques couvertes » (lot L7), « export → instance vierge → rapport régénéré identique » (lot L8), « aucun objet de configuration actif sans exigence source » pour les contrôles (signalé par `detecter_configuration_orpheline`, testé en L6-T01, non bloquant à l'activation), et les contrôles de performance (TER sur 200 000 lignes) qui relèvent de la campagne de charge.

> **Corrections de la revue de code de L6** (`backend/tests/test_revue_corrections_bd.py`, 23 tests, tous écrits pour échouer avant la correction ; migrations `controles/0010-0011`). Dix constats traités :
> 1. **Une nouvelle version d'un contrôle remplace l'ancienne dans le blocage** : `controles_en_attente` retient la dernière évaluation par CODE de contrôle (toutes versions), pas par version ; même règle pour « la dernière évaluation » d'une dérogation et pour la revue. Sans cela, un blocage de la v1 ne se levait jamais (journal en ajout seul).
> 2. **La simulation de revue est « à blanc »** : `evaluer_controle(..., ecrire=False)` calcule sans rien écrire. Elle ne peut plus faire bloquer l'étape de validation d'un objet ; ses constats restent dans la `SimulationRevue`. *Remplace la phrase de T07 qui disait qu'elle écrit au journal.*
> 3. **Le contexte d'une demande est validé** : tout champ dont dépend une étape à condition doit être fourni, un montant doit être un nombre fini positif ou nul, un seuil `NaN`/infini/négatif est refusé à la création du circuit. Un contexte incomplet ne fait plus sauter une étape en silence.
> 4. **Une personne ne signe qu'une étape par demande** (service ET contrainte unique `uq_decision_par_personne`). *Remplace la limite de T02b « un même signataire peut signer plusieurs étapes ».*
> 5. **La publication lit un état cohérent** : l'empreinte du jeu de données est lue avant et après la génération (jusqu'à 3 tentatives, sinon refus), la date de publication est prise avant la génération, la période du rapport doit correspondre à l'exercice et à la période des paramètres. **Limite** : sans instantané unique de la base (la transaction de la requête a déjà lu), une écriture arrivée pendant la génération peut être nommée « arrivée depuis la publication » alors qu'elle est dans le rapport ; ce défaut est du côté sûr (une cause en trop, jamais un écart « inexpliqué » à tort).
> 6. **La contrainte de base des étapes suit `OPERATIONS`** (`voir_numero_compte` y manquait) ; un test compare les deux listes.
> 7. **Un seuil de risque à 0 est un seuil** (`is None` au lieu de `or`).
> 8. **Plus de français figé dans le journal ni dans les refus** : `valeur_attendue` en symboles (`sum(montant) <= 5`, `#2`), refus de formule et d'assertion par le catalogue. Le test de catalogue ne couvre pas les `f"…"` de `core/`, `conditions.py` : la garde reste un test dédié.
> 9. **Le PDF formate comme la langue** (`1 234 567,50` en français, dates localisées) avec les décimales de la devise : `formater_montant(valeur, langue, decimales)`.
> 10. **Export** : un code de modèle avec `/ \ ? * [ ] :` donne un titre de feuille valide ; deux exports simultanés du même fichier rendent le même fichier.

---

# LOT L7 — DOSSIER DE CONFORMITÉ ET ACCÈS AUDITEUR

> **État** : L7-T01 à T03 livrées ; le contrôle de sortie du lot (descente de bout en bout en accès auditeur) est exécuté par `test_descente_de_bout_en_bout_en_acces_auditeur`.

**Objectif.** Un auditeur externe descend d'une cellule du TER jusqu'à la pièce scannée, sans assistance.

---

### L7-T01 — Le dossier de conformité

Généré depuis `published_report` joint à `RattachementExigence` et `Exigence`.

Pour chaque rubrique : l'exigence satisfaite, **sa citation documentaire exacte** (document, version, page, paragraphe, texte cité), la règle appliquée, le mapping utilisé et sa version, le validateur et la date.

Export PDF, **scellé avec le rapport**.

> **Réalisation de L7-T01** (`backend/niveau4_reporting/publication/dossier.py`, migration `publication/0007`, `tests/test_dossier_conformite_bd.py`, 7 tests, 7 mutations vérifiées).
> - `construire_dossier(rapport)` : une ligne par rubrique portant une valeur (les intitulés `heading` n'en sont pas). Une rubrique d'agrégat par **mapping** hérite des exigences rattachées à la VERSION de ce mapping (celle du rapport) ; une rubrique **calculée** hérite de celles des rubriques dont sa formule dépend (sans doublon) ; une rubrique d'agrégat par **comptes sans mapping** n'a aucune source et est NOMMÉE dans la section « sans exigence source » du PDF et dans `non_couvertes`, jamais cachée. Chaque source donne exigence et version, document et version, annexe, page, paragraphe, **texte cité exact**, validateur et date.
> - Les exigences retenues sont celles **en vigueur à la date de publication** (actives, ou remplacées depuis) : réviser l'exigence plus tard ne change pas le dossier d'un rapport déjà publié.
> - `exporter_dossier` : PDF français ou anglais portant le scellé du rapport, enregistré dans `FichierRapport` (nouvelle colonne `nature` : `rapport` ou `dossier`, clé unique étendue) avec son SHA-256, idempotent, habilitation `exporter`.
> - **Limites assumées** : la « couverture à 100 % » n'est PAS imposée à la publication : le plan compte sur la règle de L5-T03 « aucun objet actif sans exigence source », qui ne vise que les objets de configuration en base (mappings, contrôles) et pas une rubrique de modèle d'état en JSON ; ce cas est donc rendu visible dans le dossier (taux de couverture) plutôt que bloqué. La « règle appliquée » est une description lisible du mapping, des comptes ou de la formule, pas un lien vers la règle de mapping elle-même.

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

> **Réalisation de L7-T02** (`backend/niveau4_reporting/publication/{auditeur,vues_auditeur,urls}.py`, modèle `AccesAuditeur`, migrations `publication/0008-0009`, `config/urls.py`, `tests/test_acces_auditeur_bd.py`, 30 tests, 8 mutations vérifiées). Premier point d'accès HTTP du dépôt.
> - **Jeton** `<organisation>.<secret>` : jamais stocké (seul le SHA-256 du secret l'est). L'organisation en clair sert à poser le périmètre pour la transaction : la recherche se fait SOUS la RLS, **sans nouvelle exception à l'isolation** ; un secret faux ou une organisation devinée ne trouvent rien (401). Test d'isolation : le jeton d'une autre organisation donne 403, son secret derrière la mauvaise organisation 401.
> - **401** : jeton absent, mal formé, inconnu, révoqué ou expiré, **sur toutes les routes** (avant même le 403). **403** : projet hors des projets nommés ; toute méthode autre que lecture. **404** : un rapport hors de la plage de périodes n'existe pas pour lui.
> - **Durée** : 1 à 90 jours ; `expire_le` est posé à la création et la base REFUSE toute modification de l'expiration, du périmètre ou du jeton, pour tout rôle, et toute suppression : « pas de prolongation par lui-même » vaut aussi pour l'administrateur (il crée un nouvel accès). Seule la révocation se pose, une fois.
> - **Lecture** : liste et détail des rapports publiés (valeurs, scellé, versions de mappings), dossier de conformité (citations), téléchargement des fichiers déjà produits avec leur empreinte (`X-Empreinte-SHA256`, refus 409 si le contenu ne correspond plus). **Chaque consultation et chaque export** écrit au journal d'audit de l'organisation (acteur = l'accès, adresse IP, ressource, SHA-256) ; `journal_des_acces` les rend à qui peut `parametrer` le projet, octroi et révocation compris.
> - **Limites assumées** : l'auditeur ne peut pas FAIRE produire un export, seulement télécharger ceux qui existent (produire est une écriture de l'organisation) ; la plage porte sur la fin de période du rapport ; pas de limitation de débit ni de verrouillage après essais de jetons faux (à poser en amont, au serveur web) ; la descente jusqu'à l'écriture et à la pièce est L7-T03.

**Contrôle.** Un jeton auditeur sur le projet A reçoit `403` sur le projet B ; après expiration, `401` partout ; les accès figurent au journal d'audit de l'organisation.

---

### L7-T03 — La descente complète

Depuis une cellule : rubrique → prédicat de sélection → lignes d'écriture → écriture → pièces justificatives → fichier scanné.

> **Réalisation de L7-T03** (`backend/niveau4_reporting/publication/descente.py`, `niveau1_socle/comptabilite/pieces.py`, modèle `PieceJustificative`, migrations `comptabilite/0015-0016`, trois routes de plus dans `urls.py`, `tests/test_descente_complete_bd.py`, 9 tests, 8 mutations vérifiées). *Le contrôle de bout en bout du plan est un test : `test_descente_de_bout_en_bout_en_acces_auditeur`.*
> - **Cellule** (`/cellules/<rubrique>/<colonne>/`) : rejouée avec le modèle, les mappings et les paramètres que le rapport a gardés ; rend la règle (mapping et version, comptes ou formule), les lignes (écriture, numéro, journal, date, compte, montant), la **somme**, la valeur publiée et l'**écart** (`coherente`). Une cellule calculée rend les cellules dont elle dépend et le recalcul de sa formule. Les lignes comptabilisées APRÈS la publication sont laissées de côté et comptées à part : la descente d'un rapport publié reste celle du rapport, pas celle d'aujourd'hui.
> - **Écriture** (`/ecritures/<id>/`) : ses lignes et ses pièces ; **pièce** (`/pieces/<id>/`) : les octets du scan, après recalcul de leur SHA-256 (409 si le fichier stocké a été remplacé), empreinte en en-tête.
> - **Pièces justificatives** : nouvelle table en ajout seul (pour tout rôle), clé composite vers l'écriture, scan dans le stockage adressé par le contenu de L5-T01 ; idempotent (mêmes octets, une seule pièce), habilitation `saisir`. Un scan se joint même à une écriture comptabilisée : c'est une annexe, pas une écriture du grand livre.
> - **Périmètre auditeur** : projet nommé (403), écriture d'un autre projet de la même organisation introuvable (404), écriture postérieure à la plage introuvable ; chaque consultation (cellule, écriture, pièce) est journalisée.
> - **Limites assumées** : (1) une écriture comptabilisée entre le début de la génération et son achèvement est dans le rapport mais postérieure à `published_at` : la descente la compterait « postérieure » et l'écart (`coherente: false`) le dirait au lieu de le cacher (fenêtre étroite, voir la correction de revue n°5) ; (2) aucune pièce n'existait dans le dépôt : la table et le service sont créés ici, sans écran de téléversement ; (3) l'aperçu du scan dans un navigateur (« le scan s'affiche ») est du front-end, l'API rend les octets ; (4) la descente ne passe pas encore par un identifiant de ligne stable entre rapports successifs (les lignes sont celles du grand livre).

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

> **Réalisation de L8-T01 et L8-T02** (`backend/niveau1_socle/reprise/{models,services}.py`, migrations `reprise/0001-0002`, `tests/test_reprise_bd.py`, 37 tests dont un de 50 000 écritures lancé avec `RUN_LENT=1`, 12 mutations vérifiées). T01 et T02 partagent le même code : l'idempotence est dans l'import lui-même, pas ajoutée après.
> - **Chaîne** : `ouvrir_reprise` → `importer_balance_origine` (la balance du progiciel quitté, **équilibrée** sinon refusée) → soit `generer_soldes_ouverture` (une écriture d'ouverture à la date de bascule), soit `importer_historique` (les écritures antérieures avec accord, axe et tiers) → `controler_reprise` (rapproche balance d'origine et balance reprise **par compte, par accord, par axe**) → `signer_rapport`. Les deux modes s'excluent dans une même reprise. Une correspondance de colonnes (`correspondance={champ: en-tête}`) accueille les exports aux en-têtes différents.
> - **La règle** : acceptée seulement à **écart nul sur la balance générale (par compte) ET sur le cumul par accord** ; l'écart par axe est listé mais ne bloque pas. Un écart non nul est listé ligne à ligne, la reprise est `refusée`, et le rapport ne se signe pas (service ET contrainte de base). La signature est nominative, d'une personne habilitée `valider` **autre que celle qui a ouvert la reprise**, sur le DERNIER rapport ; elle fait passer la reprise à `acceptée`, définitive. `reprise_acceptee(projet)` dit si la mise en service est permise.
> - **Idempotence (T02)** : chaque pièce a une clé dérivée de la source (journal, numéro de pièce, date) et une empreinte de contenu. Rejouer le même fichier ne crée rien ; un fichier complété n'ajoute que les pièces nouvelles ; une pièce de même clé au **contenu différent** est un **conflit** qui arrête tout l'import, sans écrasement ni doublon. Trois imports du même fichier donnent 3 écritures, 6 lignes, 3 pièces reprises, sans trou de numérotation.
> - **Tout ou rien** : références inconnues (compte, tiers, accord, axe, journal), compte non imputable, pièce déséquilibrée, date après la bascule, période absente ou non ouverte, montant illisible : l'import entier est rejeté, rien n'est écrit, chaque cause est nommée avec sa ligne.
> - **Volume mesuré** : 50 000 écritures (100 000 lignes) importées, contrôlées à écart nul et signées en **154 s** au total sur la base locale. Une première version dépassait dix minutes : sur une base neuve, les tables n'ont pas de statistiques et les vérifications de clés étrangères font des parcours séquentiels, d'où un coût quadratique. `ANALYZE` après chaque lot rend le temps linéaire.
> - **Limites assumées** : (1) « un export réel » n'existe pas dans le dépôt : le gros jeu est GÉNÉRÉ, avec une balance d'origine calculée à part ; (2) `ANALYZE` n'agit que pour le propriétaire des tables : avec le rôle applicatif de production, PostgreSQL l'ignore et l'autovacuum prend le relais, donc le temps réel dépend de lui : un `ANALYZE` par le rôle propriétaire avant une grosse reprise est recommandé ; (3) l'import se fait dans une seule transaction (tout ou rien), donc long et verrouillant pour 50 000 pièces ; (4) l'assistant de correspondance n'est pas encore SAUVEGARDÉ pour être rejoué (la correspondance se passe en paramètre) ; (5) seul le plan comptable avait un import de référentiel (L2-T07) : tiers, journaux, axes, accords et catégories doivent exister avant la reprise ; (6) les périodes des années antérieures doivent exister et rester ouvertes pendant l'import (leur clôture est une opération à part) ; (7) la mise en service n'est pas encore BLOQUÉE par `reprise_acceptee` dans les autres modules.

**Contrôle.** Migrer un jeu de 50 000 écritures issu d'un export réel : écart nul, rapport signé produit.

---

### L8-T02 — L'import idempotent

Chaque ligne importée porte une **clé d'idempotence** dérivée de la source. Rejouer un import ne crée **jamais** de doublon.

> **Réalisation de L8-T02** : voir la note de L8-T01, qui porte le code et les tests des deux tâches (`test_trois_imports_du_meme_fichier_donnent_le_meme_nombre_d_ecritures`).

**Contrôle.** Lancer trois fois le même import : le nombre d'écritures est identique après chaque passage.

---

### L8-T03 — L'export complet

Déclenché depuis l'interface, produit en tâche de fond, mis à disposition par lien signé à durée limitée :

1. **Données** — archive CSV UTF-8 par table, schéma documenté, plus un dépôt SQL restaurable.
2. **Paramétrage** — JSON lisible : plans, axes, clés, schémas d'écritures, mappings, modèles d'états.
3. **Registre des exigences** et guide de configuration.
4. **Rapports publiés scellés** avec leurs fichiers.
5. **Journal d'audit.**

> **Réalisation de L8-T03** (`backend/niveau1_socle/reversibilite/{models,archive,restauration,services,vues}.py`, commande `produire_exports`, migrations `reversibilite/0001-0002`, `tests/test_export_complet_bd.py`, 12 tests, 10 mutations vérifiées ; `DICTIONNAIRE_DE_DONNEES.md` régénéré). **Le contrôle décisif est un test** : `test_exporter_supprimer_restaurer_puis_regenerer_un_rapport_scelle_donne_le_meme_resultat`. Il exporte une organisation complète (écritures, rapport publié scellé, fichiers Excel et PDF, dossier de conformité, pièce scannée, exigence, journal d'audit), la SUPPRIME de la base (toutes ses lignes, tous ses fichiers stockés), restaure l'archive, puis régénère le rapport : `regenerer(...).identique` est vrai, le scellé est identique octet pour octet, le dossier de conformité, les fichiers du rapport (empreintes), le scan et la chaîne du journal d'audit sont identiques.
> - **L'archive** (ZIP, UTF-8, dates fixes) : `MANIFESTE.json` (SHA-256 de chaque fichier, lignes par table), `LISEZMOI.txt`, `schema/dictionnaire.json` (le schéma des seules tables exportées), `donnees/<table>.csv` (une table par fichier, en-têtes), `restauration.sql` (dépôt `COPY … FROM stdin` restaurable avec psql), `parametrage/parametrage.json` (plan comptable, axes et valeurs, journaux, schémas d'écriture, mappings et règles, modèles d'états tels que les rapports les ont utilisés), `registre/exigences.json` et un guide de configuration PDF par projet, `rapports/<id>/` (rapport JSON et tous ses fichiers), `journal_audit.csv`, `fichiers/` (documents et pièces).
> - **Sécurité** : les **mots de passe** ne sortent pas (colonne remplacée par `!`, les comptes se réinitialisent) ; les **jetons d'accès auditeur** non plus (table exclue). Aucun filtre d'organisation écrit à la main, sauf pour la table des utilisateurs, seule non isolée par RLS. Exporter l'organisation entière exige l'habilitation `exporter` sur CHAQUE projet.
> - **Restauration** (`restaurer_archive`, rôle propriétaire) : vérifie d'abord le manifeste (un octet changé est refusé avant toute écriture), refuse une instance où l'organisation existe déjà, copie tout dans UNE transaction avec les déclencheurs suspendus (numéros, statuts, empreintes, scellés repris tels quels), compare les lignes restaurées au manifeste (annulation complète sinon), puis replace les fichiers dans le stockage.
> - **Demande, tâche de fond, lien** : `demander_export` (interface) → `produire_export` (commande `produire_exports --organisation`, à planifier : le dépôt n'a pas d'ordonnanceur) → `lien_signe` (signé par la clé secrète, organisation, export et expiration inclus, de 1 minute à 24 heures) servi par `GET /export/<jeton>/` (403 si signature fausse ou lien expiré). Un export prêt ne change plus ; un échec est enregistré avec sa cause.
> - **Limites assumées** : (1) « instance vierge » est ici l'organisation supprimée de la même base ; une seconde base fraîchement migrée serait plus fidèle, mais ce que ce test prouve est que **l'archive suffit à reconstruire l'organisation** ; que les migrations produisent un schéma identique est ce que la CI vérifie à chaque exécution ; (2) la restauration exige le rôle propriétaire (`session_replication_role` est réservé aux superutilisateurs) ; (3) les tables hors organisation (devises) ne sont pas exportées : elles viennent des migrations ; (4) l'archive est construite en mémoire : pour de très grosses organisations, il faudra la produire en flux ; (5) l'export des fichiers dépend du stockage local ; un document dont la référence n'existe pas est NOMMÉ dans `notes` du manifeste ; (6) `produire_export` n'est pas distribué (pas de file) ; (7) le lien signé est un lien porteur : qui le détient télécharge, d'où sa durée limitée.

**Contrôle décisif.** Exporter une organisation, l'importer dans une instance **vierge**, régénérer un rapport scellé : **résultat identique**. Si ce test passe, la réversibilité n'est plus une promesse commerciale, c'est un fait vérifié.

---

### L8-T04 — Le dictionnaire de données publié

Généré depuis les modèles : table, colonne, type, description, relations. **Publié ouvertement**, pas réservé aux clients.

> C'est l'inverse exact du modèle économique des concurrents. Dites-le.

> **Réalisation de L8-T04** (`backend/core/dictionnaire.py`, commande `generer_dictionnaire`, `DICTIONNAIRE_DE_DONNEES.md` à la racine, `tests/test_dictionnaire.py`, 6 tests). Généré depuis les modèles : 83 tables, chaque colonne avec son type PostgreSQL, sa nullité, sa clé primaire, sa relation (`table.colonne`), les contraintes nommées de chaque table et un indicateur « isolée par organisation » ; trié, donc déterministe. **Un test échoue si le fichier publié n'est plus celui que les modèles produisent** (vérifié en l'altérant), un autre qu'aucune colonne n'est un flottant (règle 1), un autre que chaque table des modèles figure au dictionnaire avec une clé primaire.
> - **Limite assumée** : les descriptions de colonnes viennent de `help_text` et du vocabulaire des colonnes techniques communes ; la plupart des colonnes métier n'ont pas encore de description (« — »). Les descriptions de table viennent des docstrings des modèles. C'est un travail de rédaction à poursuivre, que le test de fraîcheur rendra visible dans le diff à chaque ajout.
> - **Publié ouvertement** : le fichier est à la racine du dépôt, à côté de la spécification, et le README le dit.

> **Contrôle de sortie de L8** (`backend/tests/test_sortie_l8_bd.py`, 2 tests). Le premier vérifie que chaque contrôle du plan de L8 (T01 à T04) renvoie à un test qui existe. Le second déroule le scénario de bout en bout : balance d'origine chargée, historique importé **trois fois**, contrôle à écart nul, signature par une autre personne que celle qui a ouvert la reprise ; un rapport publié et scellé sur les données reprises (R110 du trimestre = 1325,75, la balance d'origine) ; export complet ; suppression de l'organisation ; restauration ; la reprise reste acceptée et signée, le scellé du rapport est identique octet pour octet et `regenerer` rend « identique ».
> - **Ce que le scénario ne prouve pas** (couvert par les tests propres de chaque tâche, mutations vérifiées) : le refus d'un écart non nul, le conflit d'une pièce modifiée, l'archive altérée, le lien expiré.
> - **Restent hors de ce contrôle** : le jeu de 50 000 écritures « issu d'un export réel » (le dépôt n'en a pas ; le test généré tourne avec `RUN_LENT=1`, 154 s mesurées) ; la restauration dans une **seconde base fraîchement migrée** plutôt que dans la même base débarrassée de l'organisation ; l'assistant de correspondance sauvegardable ; la production de l'export en flux pour de très grosses organisations.

> **Corrections de la revue de code de L7 et L8** (`backend/tests/test_revue_corrections_l7_l8_bd.py`, 14 tests, tous écrits pour échouer avant la correction). Dix constats traités :
> 1. **Séquences après restauration** : la restauration remet à niveau toute séquence de clé série (`core_auditlog.id`) ; sans cela, la première écriture après restauration reprenait un identifiant pris. Le test remet la séquence à 1 comme sur une instance neuve, restaure, puis journalise.
> 2. **Une archive n'est pas crue sur parole** : le manifeste est dans l'archive, il ne l'authentifie pas. `restaurer_archive(…, sha256_attendu=…)` compare l'empreinte enregistrée à l'export (transmise hors de l'archive) ; les tables visées doivent être celles du manifeste ET des tables exportables ; chaque table doit n'avoir gagné QUE les lignes de l'organisation annoncée (comptage avant et après, et par `org_id`) ; une archive qui apporte un compte administrateur est refusée. Une archive forgée avec un manifeste recalculé ne passe pas.
> 3. **Axe 1** : les valeurs se résolvent sur le plan de gestion du rang 1, plus sur n'importe quel plan portant le même code (balance d'origine, validation et écriture).
> 4. **Périmètre de l'archive** : `construire_archive` refuse si le périmètre posé n'est pas celui de l'organisation demandée (archive vide ou d'une autre organisation).
> 5. **Téléchargement** : l'archive stockée est re-hachée avant d'être servie (409 sinon).
> 6. **Exports interrompus** : `recuperer_exports_bloques` (appelée par `produire_exports`) passe en échec ceux restés `en_cours` au-delà d'un délai ; la demande d'export n'entre plus dans l'archive.
> 7. **Erreurs de reprise** : elles nomment la pièce par SA source (`OD/P003 (2026-04-05)`), plus par un morceau de hash.
> 8. **Signature** : ni l'ouvreur, ni celui qui a chargé la balance ou l'historique, ni celui qui a produit le rapport ne peut le signer.
> 9. **Descente** : la règle d'une cellule se décrit sans reconstruire le dossier ; les lignes sont paginées (`limite` ≤ 5 000, `decalage`), la somme portant sur TOUTES les lignes. La mémoire reste proportionnelle au nombre de lignes de la cellule : la pagination borne la réponse, pas le calcul.
> 10. **Réponses HTTP** : « fichier altéré », « scan altéré », « lien invalide » passent par le catalogue et suivent `Accept-Language`.
> - **Limites restantes** : l'authenticité de l'archive repose sur l'empreinte transmise hors de l'archive (l'opérateur doit la fournir) ; sans elle, la restauration protège de la corruption et de l'injection entre organisations, pas d'une archive forgée de bout en bout pour la MÊME organisation.

---

# LOT L9 — MARCHÉS, NON-OBJECTIONS ET TRÉSORERIE

**Objectif.** Un engagement bloqué faute d'avis de non-objection.

> **Contrôle de sortie de L9** (`backend/tests/test_sortie_l9_bd.py`, 2 tests). Le premier vérifie que chaque contrôle du plan de L9 (T01 à T05) renvoie à un test qui existe. Le second déroule le scénario de bout en bout : un marché soumis à non-objection (méthode AOI) **refuse l'engagement sans avis** et **l'accepte dès réception** ; le contrat s'appuie sur l'avis, et un avenant sur un avis « avenant » obtenu ; deux décomptes certifiés par une autre personne **apurent exactement l'engagement** du marché ordinaire (1 234 567,89 = 700 000,11 + 534 567,78) : il est soldé, seul reste engagé celui du marché soumis, et l'incrémental égale le recalcul complet des soldes ; les paiements portent l'exécution à 100 % (solde contractuel nul, taux financier et physique à 100,00) ; une garantie à échéance proche lève une alerte ; l'état de reconstitution du compte désigné se rapproche du relevé **sans écart**, numéro de compte masqué ; la chaîne du journal d'audit est intacte.
> - **Ce que le scénario ne prouve pas** (couvert par les tests propres de chaque tâche, mutations vérifiées) : le refus d'un engagement sans avis ou sur un marché annulé en base, le refus d'un avenant sans avis, le dépassement du montant du contrat, l'écart non justifié, l'appariement double d'un mouvement. Vérifié à la main : supprimer le blocage de l'engagement ou l'apurement du décompte fait échouer le scénario ; deux mutations (avis « avenant » d'un mauvais objet, solde du relevé injecté dans le rapprochement) ne le font pas échouer : ce sont des refus, que seuls les tests unitaires exercent.
> - **Restent hors de ce contrôle** : l'écriture comptable du paiement d'un décompte (le paiement n'écrit rien au grand livre) ; l'import de relevés au format bancaire ; un modèle de rapport « rapprochement du compte désigné » branché sur le moteur d'états ; les API HTTP du plan de passation, des contrats et de la trésorerie ; la revue de code du lot.

> **Corrections de la revue de code de L9** (`backend/tests/test_revue_corrections_l9_bd.py`, 19 tests, tous écrits pour échouer avant la correction ; migration `marches 0010`, `core/metier.py`). Neuf constats traités :
> 1. **Journal d'audit** : `avancer_ligne` enregistrait le NOUVEAU statut comme ancien (`before` = `after`) ; l'ancien statut est désormais relevé avant la transition.
> 2. **Avenant sous le certifié** : un avenant ne peut plus fixer un montant inférieur aux décomptes déjà certifiés, par le service et par `marches_avenant_naissance`.
> 3. **Annulation d'une ligne engagée ou sous contrat** : refusée par le service et par `marches_ligne_garde` (un contrat, ou un engagement ouvert, bloque l'annulation ; elle redevient possible une fois l'engagement annulé).
> 4. **Prévisions agrégées** : avec `par_axe=False`, la prévision « tous axes » l'emporte quand elle existe, sinon on additionne les axes : plus de double compte.
> 5. **Taux physique** : maximum des avancements certifiés (la règle d'avancement compare déjà au maximum), non le décompte au plus grand numéro.
> 6. **Violations d'intégrité** : traduites **par contrainte** (`traduire_integrite`) ; une contrainte inconnue garde le message de la base. Un second contrat sur un même marché n'est plus présenté comme « référence déjà existante ».
> 7. **Agrégation en base** : la fenêtre des prévisions est filtrée dans la requête, et le solde comptable d'un compte est un `SUM` (plus de lignes de grand livre chargées en Python).
> 8. **Alertes d'échéance** : quelques requêtes au lieu d'une par contrat (dernier avenant et sommes en sous-requêtes) ; un contrat **soldé** (certifié = montant courant, entièrement payé) n'alerte plus.
> 9. **Helpers partagés** : `habilite`, `refuser`, `decimal`, `traduire_integrite` dans `core/metier.py`, utilisés par les cinq modules (un test interdit les copies).
> - **Mutations vérifiées** (16, toutes détectées). Une avait d'abord survécu (garde SQL sur l'engagement ouvert) : test ajouté.
> - **Limites assumées** : un contrat ne peut toujours pas être clos explicitement (il sort des alertes parce qu'il est soldé, pas parce qu'on l'a clos) ; l'annulation d'une ligne sous contrat reste impossible (aucune résiliation de contrat n'est modélisée).

> **Le paiement d'un décompte s'écrit au grand livre** (`backend/niveau1_socle/marches/decomptes.py`, `Paiement.ecriture`, migration `marches 0011`, `tests/test_paiement_ecriture_bd.py`, 13 tests). `enregistrer_paiement` crée, dans la même transaction que le paiement, un **brouillon d'écriture équilibré** : le fournisseur (tiers du contrat, sur le compte donné) au débit, la banque (compte bancaire, sur le compte donné) au crédit, au journal donné. Le paiement et son écriture naissent ensemble ou pas du tout (journal inconnu, période close : rien n'est créé).
> - **Aucun compte, journal ni taux n'est supposé** : l'appelant les donne. Le compte bancaire est dans la **devise du contrat** ; si elle diffère de la monnaie de tenue du projet, le **taux est obligatoire** et le montant converti est arrondi à la devise de tenue (arrondi supérieur à la demi-unité) ; l'écriture est alors équilibrée en monnaie de tenue **et** en devise.
> - **Le brouillon suit le cycle ordinaire** : validé par une autre personne, puis comptabilisé ; c'est à ce moment seulement qu'il compte dans le solde comptable du compte (test : brouillon = solde nul, comptabilisé = −60 000 USD). Clé d'idempotence stable par décompte et référence.
> - **Tenu en base** : tout nouveau paiement exige une écriture **du même projet** (`marches_paiement_naissance`) ; les paiements antérieurs, sans écriture, restent lisibles.
> - **Mutations vérifiées** (13, toutes détectées) : devise du compte, taux obligatoire (message), arrondi, lien du paiement à l'écriture, montants en devise, compte bancaire de la ligne, clé d'idempotence, écriture requise et du même projet. Trois ont d'abord survécu (message du taux, clé, projet de l'écriture) : tests ajoutés.
> - **Limites assumées** : seul le **paiement** est écrit ; la **certification** d'un décompte (charge, dette fournisseur, retenue) n'écrit toujours rien : l'imputation de la charge (compte, axes, accord, catégorie) n'est pas encore décidée ; aucune écriture de différence de change entre la dette et le paiement.

> **Import d'un relevé bancaire MT940 / CAMT.053** (`backend/niveau1_socle/tresorerie/releves.py`, `tests/test_releves_bd.py`, 22 tests). `importer_releve(compte, contenu, format=None, taux=None)` lit un ou plusieurs relevés, vérifie qu'**ouverture + mouvements = clôture** (sinon rien n'est écrit), que le **compte** (comparé au numéro, sans jamais l'afficher) et la **devise** sont ceux du compte bancaire, puis enregistre les mouvements (rejouables : une référence déjà importée est ignorée) et **les deux soldes de relevé** (ouverture et clôture), en tout ou rien. Le relevé importé alimente directement l'état de reconstitution du compte désigné.
> - **MT940** : enveloppe SWIFT tolérée, soldes `60F/60M/62F/62M`, mouvements `:61:` (crédit, débit, **annulations RC/RD** qui inversent le sens) et libellés `:86:` sur plusieurs lignes. **CAMT.053** : `Bal` OPBD/CLBD, `Ntry` (sens, annulation `RvslInd`, référence de la banque, libellé). Les deux formats donnent le même relevé (test).
> - **Références stables** : celle de la banque quand elle est unique dans le relevé, sinon `<référence du relevé>:<rang>` ; rejouer le même fichier, ou son équivalent dans l'autre format, ne change rien.
> - **Sécurité** : un fichier XML contenant une DTD ou une entité est refusé (aucune expansion) ; taille limitée à 10 Mio ; habilitation « comptabiliser » vérifiée avant toute lecture ; un solde déjà posé avec une autre valeur est un conflit qui défait l'import entier.
> - **Mutations vérifiées** (16, toutes détectées). Cinq ont d'abord survécu (solde d'ouverture débiteur, taille maximale, références en double, devises d'ouverture et de clôture, habilitation avant lecture) : tests ajoutés.
> - **Limites assumées** : un compte en devise étrangère exige un `taux` explicite, **unique pour tout le fichier** (le relevé n'en porte pas) ; les autres formats (OFX, CSV de banque, CAMT.052/054) ne sont pas lus ; la ventilation fine des codes de transaction (`NTRF`, `NCHG`) n'est pas exploitée ; l'import n'écrit pas le grand livre (le rapprochement avec les écritures reste l'étape existante).

> **L'état « rapprochement du compte désigné » sur le moteur d'états** (`backend/niveau4_reporting/moteur/sources_externes.py`, `source_compte_designe.py`, `modeles_etats.py`, `tests/test_etat_compte_designe_bd.py`, 9 tests). Le moteur, qui ne lisait que le grand livre, sait désormais lire des **sources externes DÉCLARÉES** : une rubrique `{"type": "external", "source": "…", "item": "…"}`. Le registre est **fermé** (on n'exécute jamais un nom venu d'un modèle) et une source ou un élément inconnu est refusé **à la compilation**. Un état purement externe est admis (colonne SQL neutre).
> - **Le modèle livré** (`modele_rapprochement_compte_designe`, code `RCD`) : ouverture + avances reçues + autres encaissements − décaissements = clôture calculée (R150), comparée au relevé de clôture (écart R170), puis au grand livre (écart R200). Les deux **écarts non justifiés** (R180 relevé, R210 grand livre) portent une **assertion** : tant qu'un écart n'est pas expliqué au centime par `justifier_ecart`, **l'état ne se publie pas** (`AssertionsViolees`, rien n'est enregistré). Les écarts eux-mêmes restent affichés une fois justifiés.
> - **Publié, scellé, régénérable** comme les autres états : sans solde d'ouverture ou de clôture du relevé, l'état est **refusé** (`SourceIncomplete`) ; un mouvement arrivé après la publication bloque la régénération tant que l'écart n'est pas justifié, puis les rubriques qui changent sont nommées (R130, R150, R170, R200). Aucun mapping n'est requis. Le numéro du compte n'apparaît ni dans les valeurs, ni dans les paramètres, ni dans le modèle publiés.
> - **Les états de rapprochement et de reconstitution** se calculent maintenant sans contrôle d'habilitation en interne (`calculer_etat_de_rapprochement`, `calculer_reconstitution`), l'habilitation « publier » étant vérifiée en amont ; leurs versions publiques gardent leur contrôle (« consulter »).
> - **Mutations vérifiées** (14, toutes détectées). Une avait d'abord survécu (compte non désigné accepté par la source) : test ajouté.
> - **Limites assumées** : l'empreinte du jeu de données scellée (`dataset_hash`) ne couvre que le grand livre, pas le relevé ni les justifications : leurs changements se voient par les VALEURS régénérées, pas par l'empreinte ; l'analyse des causes d'un écart de régénération reste celle du grand livre (un mouvement de relevé tardif est signalé par ses écarts de rubriques, non par sa cause nommée) ; une valeur externe vaut pour toutes les colonnes du modèle ; aucun gabarit d'export (PDF, Excel) propre à ce modèle.

> **L'API HTTP du plan de passation, des contrats, des décomptes et de la trésorerie** (`backend/core/api.py`, `niveau1_socle/marches/{api,urls}.py`, `niveau1_socle/tresorerie/{api,urls}.py`, `tests/test_api_marches_bd.py`, `tests/test_api_tresorerie_bd.py`, 24 tests ; `/api/v1/…`). C'est la première couche API métier générale du dépôt : session authentifiée, JSON, **montants en chaînes** (un nombre JSON décimal est refusé : jamais de `float`, ni en entrée ni en sortie), un champ invalide est nommé, les erreurs ont un code stable `{code, message}` dans la langue de l'utilisateur (règle invalide **422**, transition interdite **409**, habilitation **403**, objet absent ou d'une autre organisation **404**).
> - **Plan et avis** : méthodes (`GET/POST projets/<id>/methodes/`), plans, lignes (liste, détail avec étapes et avis, avancer, replanifier, modifier), retards, avis (demande, décision, pièces en base64, en attente). **Contrats** : conclure sur une ligne, détail (montant et date de fin courants, avenants, garanties), avenants, garanties et leur clôture, alertes d'échéance. **Décomptes** : soumettre, lister, certifier, rejeter, payer, situation contractuelle (soldes et taux).
> - **Trésorerie** : disponibilités par devise, prévisions (pose, révision, lecture avec `par_axe`), soldes de relevé, **import de relevé MT940 / CAMT.053**, reconstitution du compte désigné, justifications d'écart, **publication du rapport** `RCD`, appariement d'un encaissement à une demande et son annulation. Le numéro d'un compte n'est jamais renvoyé : seulement son numéro masqué.
> - **L'habilitation est vérifiée AVANT la lecture du corps** : sans le droit, la réponse est 403 même si le corps est invalide (aucune validation ne fuit). Le service appelé la contrôle ensuite à son tour. L'isolation par organisation reste celle de la base (404).
> - **Un défaut trouvé en écrivant l'API** : un second appariement d'un mouvement déjà apparié recevait le message « dépasserait le montant de la demande » ; le service vérifie désormais d'abord « déjà apparié » (l'index unique reste la garde en base).
> - **Mutations vérifiées** (21, toutes détectées). Sept ont d'abord survécu (sérialiseur sans float, booléen pris pour un entier, habilitation avant le corps pour la certification, les relevés et la publication, lecture de `par_axe`) : tests ajoutés. Un incident de sauvegarde (trois `api.py` de même nom écrasés par mon script de mutations) a obligé à reconstruire deux fichiers non encore commités ; ils ont été rejoués par les 16 tests de l'API avant commit, et les mutations utilisent désormais `git checkout` pour restaurer.
> - **Limites assumées** : pas de pagination ni de filtres sur les listes ; pas de contrat d'API publié (schéma OpenAPI) ; pas de limitation de débit ; l'authentification est celle de la session (pas de jeton d'API pour les intégrations) ; pas d'API pour les engagements du budget (un décompte certifié reçoit l'identifiant d'un engagement existant) ; les pièces d'avis se téléversent en base64 dans le JSON (pas de téléversement par fichier) et leur téléchargement n'a pas de point d'accès.

---

### L9-T01 — Plan de passation

Lignes prévisionnelles, méthodes, seuils, calendrier, états d'avancement.

> **Réalisation de L9-T01** (`backend/niveau1_socle/marches/` : `models.py`, `plan.py`, migrations `0001`/`0002` ; `tests/test_plan_passation_bd.py`, 19 tests ; catalogues `passation.json` fr/en). Quatre tables isolées par RLS : `MethodePassation` (versionnée, seuils `[seuil_min, seuil_max[` par devise, exigence d'avis de non-objection), `PlanPassation`, `LignePassation`, `EtapeAvancement` (ajout seul).
> - **Aucun seuil par défaut** : chaque projet pose les siens (habilitation `parametrer`). Une nouvelle version ferme la précédente à sa date d'effet ; la base refuse tout chevauchement (EXCLUDE) et toute modification du contenu d'une version.
> - **Une ligne ne se prévoit qu'avec une méthode applicable** à son montant, dans la même devise, à la date de lancement prévue ; sinon refus, avec la plage citée. L'exigence d'avis est copiée de la méthode au moment de la saisie (instantané) : une nouvelle version de la méthode ne change pas les lignes déjà prévues.
> - **Avancement** prévu → lancé → attribué → signé, ou annulé (motivé) avant la signature ; une étape ne se saute pas, sa date ne précède pas celle de l'étape d'avant. Signée ou annulée, la ligne est définitive. La base le garantit par trigger (statut qui ne recule pas, montant, méthode, devise, référence et exigence d'avis figés dès le lancement, aucune suppression).
> - **Suivi** : `lignes_en_retard` (étape attendue, jours de retard, échéance du jour non comptée) et `synthese` (par statut et par méthode, jamais en mélangeant les devises).
> - **Mutations vérifiées** (7, toutes détectées) : seuil maximal exclu, seuil minimal, saut d'étape, date antérieure, modification après lancement, jour de retard, relecture de l'avis. Deux ont d'abord survécu (bornes de seuil, jour d'échéance) : tests de bornes ajoutés.
> - **Limites assumées** : l'engagement n'est pas encore relié au marché (L9-T02) ; une ligne n'est pas encore liée à un contrat (L9-T03) ; l'étape « prévu » est datée du jour de saisie et n'entre pas dans l'ordre des dates ; pas d'API HTTP ni de tableau de bord du plan.

### L9-T02 — Avis de non-objection

Demande, pièces, statut, date de réception. **Blocage de l'engagement tant que l'avis requis n'est pas obtenu.**

> Point de friction quotidien sur les projets Banque mondiale. C'est la raison pour laquelle il appartient au socle, et non à une version ultérieure.

**Contrôle.** Un marché soumis à non-objection refuse l'engagement sans avis, et l'accepte dès réception.

> **Réalisation de L9-T02** (`backend/niveau1_socle/marches/avis.py`, tables `AvisNonObjection` et `PieceAvis`, migrations `marches 0003/0004` et `budget 0007/0008`, `tests/test_avis_non_objection_bd.py`, 15 tests). Un avis a un objet (dossier, évaluation, contrat, avenant, autre), une date de demande, des pièces (demande envoyée, réponse reçue ; ajout seul, empreinte relue), puis une décision : obtenu ou refusé (motivé), datée, avec la référence du bailleur. Décidé, un avis est figé : après un refus on demande à nouveau, le refus reste dans l'historique.
> - **Blocage de l'engagement** : `creer_engagement(..., ligne_passation=...)` refuse l'engagement d'un marché dont la méthode exige l'avis tant que l'avis n'est pas suffisant, et l'accepte dès la décision « obtenu » enregistrée. **Avis suffisant** : au moins un avis demandé, et chaque demande non obtenue (en attente ou refusée) suivie d'un avis obtenu du même objet.
> - **Tenu aussi en base** : un déclencheur sur `budget_engagement` refuse la naissance d'un engagement sans avis suffisant, sur un marché annulé ou d'un autre projet, même créé hors du service ; le rattachement ne change plus ensuite (garde existante de l'engagement). Clé composite `(org_id, ligne_passation_id)`.
> - **Engagement sans marché** : reste possible (dépense hors passation) ; seul un engagement rattaché à un marché soumis à avis est bloqué.
> - **Suivi** : `avis_en_attente` liste les demandes sans réponse, les plus anciennes d'abord, avec leur ancienneté en jours.
> - **Mutations vérifiées** (10, toutes détectées) : blocage du service, ordre des avis (service et SQL), refus non repris, marché non soumis, date de décision, motif de refus, déclencheur d'avis, marché annulé, avis figé. Trois ont d'abord survécu (marché annulé et ordre des avis en SQL, refus non repris) : tests écrits qui contournent le service pour interroger la base.
> - **Limites assumées** : la règle ne couvre que la **naissance** de l'engagement (un avis refusé après coup ne révoque pas un engagement existant) ; l'avis de la signature du contrat n'est pas encore exigé (L9-T03) ; la décision se saisit avec l'habilitation « saisir » (pas de séparation des tâches) ; pas d'API HTTP ni de rappel automatique des avis en retard.

### L9-T03 — Contrats, avenants, garanties

Contrats, avenants versionnés, garanties et assurances avec échéances et alertes.

> **Réalisation de L9-T03** (`backend/niveau1_socle/marches/contrats.py`, tables `Contrat`, `AvenantContrat`, `Garantie`, migrations `marches 0005` à `0007`, `tests/test_contrats_bd.py`, 18 tests). Le contrat naît d'un marché **attribué** (ou signé), dans la devise et le projet de sa ligne, avec un titulaire (`Tiers`) ; il porte sa valeur INITIALE et ne se modifie ni ne se supprime. Chaque avenant porte la valeur SUIVANTE (montant total, date de fin) : la valeur courante est celle du dernier avenant, le contrat ne bouge jamais.
> - **Avenants numérotés sans trou** : verrou sur le contrat dans le service, et déclencheur en base (numéro = précédent + 1, jamais antérieur à la signature ni à l'avenant précédent, ajout seul). Sur un marché soumis à non-objection, un avenant s'appuie sur un avis **obtenu d'objet « avenant »**, de la même ligne, qu'aucun autre avenant n'a utilisé ; sur un marché non soumis, aucun avis n'est à joindre.
> - **Non-objection du contrat** : un contrat sur un marché soumis exige l'avis suffisant du marché (dossier, évaluation, contrat…), service et base. L'avis d'objet « avenant » est **exclu** de la règle d'avis suffisant (migration `0007`) : un avenant en attente ne bloque ni l'engagement ni le contrat. Un marché signé ne reçoit plus de demande d'avis que pour un avenant.
> - **Garanties et assurances** (bonne exécution, restitution d'avance, retenue, assurance) : émetteur, référence unique par contrat, montant dans la devise du contrat, émission, échéance. Contenu figé en base ; seul le statut avance, une fois : libérée (mainlevée) ou appelée (motivée), avec sa date. Une prolongation est une nouvelle garantie ; l'ancienne se libère.
> - **Alertes d'échéance** : `alertes_echeances(jour, horizon_jours)` liste les garanties actives et les contrats arrivant à échéance dans l'horizon, ou déjà dépassés, du plus urgent au moins urgent. **L'horizon est choisi par l'appelant** : aucun délai n'est supposé. Un contrat s'évalue à sa date de fin COURANTE (celle du dernier avenant). La limite est incluse.
> - **Mutations vérifiées** (18, toutes détectées) : marché non attribué, avis du contrat, numérotation, date d'avenant, avis réutilisé ou d'un mauvais objet, avis sur un marché non soumis, appel motivé, garantie définitive, fin courante, bornes d'horizon, garanties libérées exclues, déclencheurs SQL (avis, attribution, trou, avenant, garantie figée, exclusion de l'avis avenant). Deux ont d'abord survécu (avis joint à un marché non soumis, borne d'horizon) : tests ajoutés.
> - **Limites assumées** : un avenant ne vérifie pas encore un plafond de variation du montant (aucun seuil n'est inventé) ; le contrat ne passe pas la ligne à « signé » (l'avancement du plan reste une saisie distincte) ; pas de rappel automatique ni de lien avec le calendrier des obligations ; pas d'API HTTP ; la libération d'une garantie ne vérifie pas encore la réception des travaux (L9-T04).

### L9-T04 — Décomptes et apurement

Décomptes, factures, paiements, **apurement des engagements**, soldes contractuels, taux d'exécution physique et financier.

**Contrôle.** Un engagement totalement apuré libère exactement le disponible budgétaire qu'il réservait, au centime.

> **Réalisation de L9-T04** (`backend/niveau1_socle/marches/decomptes.py`, tables `Decompte` et `Paiement`, migrations `marches 0008/0009`, refactor de `budget/engagements.py`, `tests/test_decomptes_bd.py`, 19 tests). Un décompte est **soumis** par une personne (« saisir »), numéroté sans trou par contrat, puis **certifié** par une autre (« valider ») ou **rejeté** (motivé) ; décidé, il est définitif. La certification **apure l'engagement du marché dans la même transaction** : si l'apurement échoue (reste insuffisant, engagement clos), rien n'est certifié.
> - **Contrôle décisif** (`test_un_engagement_totalement_apure_libere_exactement_le_disponible_qu_il_reservait`) : budget approuvé de 50 000 000,00 ; engagement de 1 234 567,89 ; deux décomptes apurent 700 000,11 puis 534 567,78. Après le premier, le disponible vaut exactement le budget − le non-apuré ; après le second, l'engagement est soldé et le disponible égale le budget **au centime**, et `comparer_soldes` ne trouve aucune divergence entre l'incrémental et le recalcul complet.
> - **Règles tenues en base** (déclencheurs et CHECK, vérifiées hors du service) : numérotation sans trou ; certificateur ≠ auteur ; décompte décidé figé ; engagement = celui du marché du contrat ; Σ décomptes certifiés ≤ montant courant du contrat (celui du dernier avenant) ; avancement physique cumulé qui ne recule pas ; paiements en ajout seul, sur un décompte certifié, sans dépasser son net (brut − retenue).
> - **Un engagement rattaché à un marché ne s'apure plus à la main** (`apurer_engagement` refuse) : l'apurement direct contournerait les soldes contractuels. L'apurement partagé (`apurer_verrouille`) sert aux deux chemins.
> - **Soldes et taux** (`situation_contrat`) : montant courant, certifié, solde contractuel, net certifié, payé, reste à payer, taux financier (certifié ÷ montant courant, en %) et taux physique (avancement du dernier décompte certifié). Un décompte soumis ou rejeté n'y compte pas.
> - **Devises** : le décompte est dans la devise du contrat ; l'apurement, en monnaie de tenue du projet. À devise égale, il vaut le brut ; sinon le certificateur donne le montant apuré : **aucun taux n'est supposé**.
> - **Mutations vérifiées** (19, toutes détectées) : auteur ≠ certificateur (service), engagement du marché, apurement transactionnel, plafond du contrat, avancement, paiement hors net, paiement d'un décompte non certifié, retenue, date, taux, reste à payer, devise égale, apurement manuel, déclencheurs SQL (numéro, plafond, décompte figé, net, état, avancement). Trois ont d'abord survécu (service d'auteur, décompte décidé, avancement en base) : tests écrits.
> - **Limites assumées** : le paiement n'écrit **pas** encore d'écriture comptable (le rapprochement avec le grand livre et la trésorerie relève de L9-T05) ; la « facture » n'est qu'une référence et une date portées par le décompte, sans contrôle du tiers ni de la TVA ; aucun contrôle de vraisemblance entre avancement physique et financier ; un engagement rattaché ne s'apure que par décompte, mais l'apurement hors décompte reste possible en base pour qui contournerait le service ; la libération des garanties n'est pas liée à la réception ; pas d'API HTTP.

### L9-T05 — Trésorerie

Comptes bancaires, mouvements, prévisions par période et par axe, disponibilités, **état de reconstitution du compte désigné**.

**Contrôle.** L'état de reconstitution du compte désigné se rapproche du relevé bancaire, et tout écart est explicitement justifié.

**Rapprochements et doublons.** Un mouvement bancaire est rapprochable d'une demande de décaissement et d'une écriture, **une seule fois** : contrainte d'unicité empêchant qu'un même mouvement soit rapproché de deux demandes. Les numéros de compte restent masqués sans l'habilitation `voir_numero_compte` (L4-T04).


> **Réalisation de L9-T05** (`backend/niveau1_socle/tresorerie/`, tables `SoldeReleve`, `AppariementDemande`, `PrevisionTresorerie`, `JustificationEcart`, migrations `0001/0002`, `tests/test_tresorerie_bd.py`, 16 tests). Les comptes bancaires, les mouvements de relevé et le rapprochement avec le grand livre existaient depuis L3-T07 et L4-T04 ; cette tâche ajoute ce qui manquait pour lire la trésorerie.
> - **Solde du relevé enregistré** (`SoldeReleve`, un par compte et par jour, ajout seul) : le solde d'ouverture n'est plus un paramètre de l'appelant. Le solde d'un jour inclut déjà les mouvements de ce jour (test) ; au-delà, on ajoute les mouvements importés ensuite.
> - **Appariement d'un encaissement à une demande de retrait, UNE SEULE FOIS** : index unique partiel en base sur les appariements actifs (un mouvement, une demande), vérifié aussi hors service. Règles de la base : encaissement seulement, même projet, devise du compte = devise de l'accord, demande acceptée ou remboursée, total apparié ≤ montant retiré par la demande. L'annulation est motivée, unique et libère le mouvement ; l'historique garde l'appariement annulé. L'appariement à l'écriture est celui du rapprochement existant (`bank_match_id`).
> - **Prévisions par période et par axe** (`etablir_prevision`, `previsions`) : un mois, un axe (ou « tous axes »), une devise ; **révisées sans jamais écraser** (révision 1, 2, 3… numérotée sans trou par un déclencheur, motif obligatoire dès la deuxième) ; la courante est la plus récente. Lecture avec ou sans ventilation par axe ; **les devises ne sont jamais additionnées**.
> - **Disponibilités** (`disponibilites`) : par compte actif, solde comptable (grand livre) et solde du relevé à une date, marge sous le plafond ; totaux **par devise**.
> - **État de reconstitution du compte désigné** (`etat_reconstitution`) : ouverture (relevé de la veille) + avances reçues (encaissements appariés, par demande) + autres encaissements − décaissements = clôture calculée, comparée au relevé de clôture, puis au grand livre par les éléments en suspens du rapprochement. **Deux écarts** : relevé (clôture du relevé − calculée) et comptable (ce que le rapprochement n'explique pas). Chaque écart se justifie **explicitement** (`justifier_ecart`, habilitation « valider », ajout seul, montant signé, explication obligatoire) : l'état n'est `justifie` que si les justifications égalent chaque écart **au centime** ; sans solde d'ouverture ou de clôture il est `incomplet` et dit lequel manque. Le plafond du compte est signalé s'il est dépassé. Le numéro complet du compte n'apparaît jamais : seulement le numéro masqué.
> - **Mutations vérifiées** (27, toutes détectées) : calcul de clôture, justification partielle ou d'un seul écart, solde du relevé injecté dans le rapprochement, compte non désigné, plafond, appariements annulés, motif de révision, révision courante, bornes de période, solde de la veille, double compte du jour, devise et état de la demande, plafond d'appariement, numérotation des révisions, index unique. Une a d'abord survécu (mouvement du jour du solde compté deux fois) : test ajouté.
> - **Limites assumées** : l'état couvre une période dont les soldes de relevé d'ouverture (veille) et de clôture sont enregistrés tels quels (l'import MT940 / CAMT.053 est livré ensuite, voir plus bas) ; les avances reçues ne sont reconnues que si elles sont appariées à une demande (un encaissement non apparié est classé « autres encaissements ») ; aucun taux de change n'est appliqué (les comptes en devise étrangère se lisent dans leur devise) ; le plafond n'est qu'un signal, pas un blocage ; pas d'API HTTP, de restitution PDF ni de modèle de rapport « rapprochement du compte désigné » branché sur le moteur d'états.

---

# LOT L10 — MULTI-BAILLEURS ET TABLEAU DE BORD

**Objectif.** Deux rapports de bailleurs différents produits à partir des **mêmes données**.

### L10-T01 — Profils BAD, UE, FIDA, Fonds mondial, BID, Nations unies

Chacun avec ses modèles, rubriques, règles, périodicités et nomenclatures.

> **Critère de recette, repris du cahier des charges :** ajouter un profil et un modèle **sans créer une nouvelle application**, et **sans écrire une ligne de code**. Si un profil demande du code, c'est que le moteur a un manque — traitez-le comme tel.

> **Réalisation de L10-T01** (`backend/niveau2_profils/catalogue/{bad,union_europeenne,fida,fonds_mondial,bid,nations_unies}.json`, `backend/niveau4_reporting/{modeles_etats.py,catalogue_modeles/}`, `tests/test_profils_bailleurs_livres_bd.py`, 36 tests). **Décision prise avec le demandeur** : le contenu réel de ces six profils n'est dans aucune source du dépôt (qui ne connaît que des noms de formulaires, lus au sommaire du manuel de l'éditeur) ; le lot livre donc un **squelette sourcé, rien d'inventé**, au lieu de rubriques et de délais écrits de mémoire.
> - **Six profils livrés comme données**, chargés par le MÊME mécanisme que la Banque mondiale (`charger_profil`, brouillon puis publication, import en propositions, présentation « lorsque requis ») : aucun code, aucune application. **BAD** : formulaires A1, A2, A3. **FIDA** : formulaires 100, 104, 105. **Union européenne** : devis-programmes et mémoires (mécanisme du FED, avec l'avertissement que le FED ne s'applique pas d'office à tous les instruments actuels). **Fonds mondial, BID, Nations unies** : un seul élément, la référence au document contractuel du projet, « à identifier » : des profils d'attente.
> - **Rien n'est inventé, et le test le prouve** : chaque élément **cite sa source** (un code `SRC:` qui existe au registre `ANNEXE_B`, ou le dossier d'apports qui le justifie) ; chaque formulaire est nommé « intitulé et contenu à préciser » (le profil n'affirme rien de ce qu'il contient) ; **aucun délai, aucune périodicité** ; toute exigence est facultative, importée seulement comme **proposition** (règle 9).
> - **Catalogue de modèles d'états** (`catalogue_modeles/*.json`, liste blanche de noms) : un modèle d'état est désormais un fichier de données ; le rapprochement du compte désigné (L9-T05) en est le premier, et chaque modèle livré se compile (test).
> - **Critère de recette démontré** : dans un catalogue temporaire, on dépose **deux fichiers** (un profil d'essai, un modèle d'essai) et le chargeur, la présentation et la lecture du modèle les utilisent **sans une ligne de code**. **Objectif du lot** : deux états de bailleurs différents (rubriques, colonnes et nomenclatures propres à chacun, tables de mapping distinctes) publiés sur les **mêmes données** : même empreinte du jeu de données, même chiffre de charges (225,35), deux scellés différents, chacun régénéré à l'identique.
> - **Mutations vérifiées** (11, toutes détectées ; un mutant équivalent écarté) : liste blanche, version du modèle, code d'un formulaire, obligation, sources du registre, caractère « non universel », assertion du rapport, périodicité et délai inventés.
> - **Limites assumées** : ces profils ne contiennent **aucun modèle d'état réel de bailleur** (les modèles « BAILLEUR-A » et « BAILLEUR-B » des tests sont des données d'essai) ; il reste à lire le manuel de l'éditeur et les documents contractuels des projets pour renseigner les formulaires, les délais, les périodicités et les nomenclatures ; Fonds mondial, BID et Nations unies n'ont aucune exigence à ce stade ; aucune interface ne liste les modèles livrés (catalogue lisible par le code seulement).
### L10-T02 — Tableau de bord multi-projets

Projets actifs et bailleurs · budgets approuvés et révisés · financements reçus · dépenses et taux d'exécution, global et par composante · soldes bancaires · engagements et **avances non justifiées** · **échéances, rapports en attente, anomalies ouvertes** · taux d'acceptation au premier envoi.

Chaque indicateur est **cliquable jusqu'au détail, puis jusqu'à l'écriture**.

**Contrôle.** Le total d'un indicateur consolidé égale exactement la somme de ses détails par projet.

> **Réalisation de L10-T02a (socle et indicateurs financiers).** Module en lecture seule `niveau4_reporting/tableau_de_bord/` (aucun modèle) : `perimetre` (projets où l'utilisateur a l'opération « consulter » ; un filtre ne donne jamais un droit), `Filtres` (projets, bailleur, accord, devise, période, statut d'accord, de projet et de configuration), `tableau_de_bord` (indicateurs `{projet: {devise: montant}}` : budgets approuvé/initial, financements accordés et reçus, exécution engagé/consommé global et par composante, soldes comptables et de relevé, engagements ouverts, avances non justifiées) et `consolider` (taux officiel le plus récent ≤ date, arrondi par projet à la décimale de la devise de référence, méthode/date/taux exposés ; un taux manquant → `montant=None` et la raison, jamais de chiffre approché). Les devises ne sont jamais additionnées sans consolidation. Vérifié : total = somme exacte des détails par projet, recalculé en SQL indépendant ; 8 mutations tuées (droit « consulter », intersection des projets, date du taux, arrondi, année des engagements, avances).
> **Limites assumées.** Les engagements ouverts sont l'état courant filtré sur l'année (pas de reconstitution historique) ; le consommé global additionne les lignes de la version approuvée et peut compter deux fois une dépense couverte par deux lignes qui se recouvrent (avertissement `tableau_de_bord.execution_recouvrement` affiché) ; la consolidation utilise un taux unique par devise à la date demandée. Restent L10-T02b (échéances, rapports en attente, anomalies, taux d'acceptation) et L10-T02c (descente jusqu'à l'écriture, API).

> **Réalisation de L10-T02b (indicateurs de conformité).** `tableau_de_bord/conformite.py` ajoute `TableauDeBord.conformite` : par projet, les échéances à remettre / imminentes / en retard / en escalade (niveaux exclusifs, repris de `alertes_du_jour`), les **rapports en attente** (envois au bailleur sans issue), les **anomalies ouvertes** (contrôles bloquants non levés ou « à vérifier » non tranchés, via `controles_en_attente`, tous objets confondus) et les premiers envois acceptés/décidés. Le total d'un compte est la somme exacte des détails ; le **taux d'acceptation consolidé est calculé sur les sommes** (4/6 et non la moyenne de 1 et 1/3), `None` sans issue connue, sur la période `du`/`au` du filtre (défaut : tout jusqu'au jour). Le périmètre des projets s'applique aussi à ces comptes. 6 mutations tuées (échéances remises comptées, rapports en attente, bornes de période, objets des anomalies, dénominateur du taux).
> **Limites.** « Rapport en attente » = envoi en attente de décision du bailleur ; un rapport attendu mais non encore produit est une échéance à remettre. Les filtres d'accord, de devise et de configuration n'agissent pas sur ces comptes (rattachés au projet).

> **Réalisation de L10-T02c (descente et API HTTP).** `tableau_de_bord/detail.py` : `detail_indicateur` rend, pour un projet, les objets qui composent un indicateur (lignes de budget, accords, appariements, comptes bancaires, engagements, avances) avec les MÊMES règles que le tableau — la somme du détail égale l'indicateur, devise par devise, projet par projet (testé sur les 11 indicateurs). `ecritures_du_detail` descend jusqu'aux écritures du grand livre pour un compte bancaire (la somme des écritures est son solde) et pour une avance (versement et justifications à la date), puis `publication.descente.detail_ecriture` rend l'écriture, ses lignes et ses pièces. Un objet sans écriture (engagement, accord, ligne de budget) le dit (`a_une_ecriture`) au lieu d'en inventer. API (`niveau4_reporting/tableau_de_bord/{api,urls}.py`, JSON strict, montants en chaînes, erreurs `{code,message}`) : `GET /api/v1/tableau-de-bord/`, `…/<indicateur>/consolidation/`, `projets/<id>/tableau-de-bord/<indicateur>/detail/` et `…/detail/<id>/ecritures/` ; un projet hors périmètre est ignoré dans le tableau (jamais ajouté par l'URL) et refusé (403) pour la descente. 12 mutations tuées sur le détail et l'API (dont avances soldées, lignes postérieures au jour, justifications futures, somme des lignes d'une même écriture, consolidation sans taux).
> **Limites assumées.** La descente jusqu'à l'écriture n'existe que pour les comptes bancaires et les avances : le consommé budgétaire d'une ligne n'est pas encore relié à ses écritures (le solde budgétaire est incrémental) ; les financements reçus s'arrêtent au mouvement de relevé apparié. Pas de pagination ni de jeton d'API (comme le reste de l'API L9).

**Devises.** Le tableau de bord **ne somme jamais des devises différentes sans le dire** : par défaut, montants ventilés par devise. Une consolidation dans une devise de référence affiche, à côté du chiffre, **la méthode, la date et le taux** utilisés ; sans taux disponible à la date, l'indicateur n'est pas consolidé et le dit. Filtres : organisation, projet, bailleur, accord, devise, période, statut d'accord, statut de configuration.

**Contrôle.** Un portefeuille USD + EUR sans taux affiche deux totaux séparés, jamais un total mélangé.

### L10-T03 — Recette d'architecture

Exécuter les dix-sept tests de réception (T1 à T17) de la [spécification fonctionnelle](01_SPECIFICATION_FONCTIONNELLE.md) §17, dont les sept du cahier des charges de l'unité de gestion.

**Scénario T17, de référence (chiffres fictifs).** Un même projet financé par deux bailleurs au moyen de deux accords indépendants (par exemple 5 millions USD et 3 millions USD) : chacun avec sa configuration issue d'un profil, ses catégories, ses taux, ses pièces et son reporting ; une dépense sur chaque accord contrôlée **par ses propres règles** ; un avenant sur le premier crée une nouvelle version **sans effet sur le second** ; une dépense antérieure à l'avenant **conserve la version** qui était applicable à sa date ; un accès croisé d'une autre organisation est refusé.

> **Le critère qui prime sur tous les autres :** la solution est acceptée si elle démontre qu'un nouveau projet, un nouveau bailleur ou un nouveau modèle de reporting s'ajoute **par paramétrage**, sans application distincte et sans duplication des données comptables.

> **Réalisation de L10-T03 (recette d'architecture).** `tests/test_recette_architecture_bd.py` : chaque scénario T1 à T17 de la spécification §17 renvoie au(x) test(s) qui le démontrent (vérifié : tous existent) ; **T17 est joué de bout en bout** — un projet, deux accords de deux bailleurs, chacun avec son profil : une dépense à 80 % sous l'un et à 50 % sous l'autre (chacune contrôlée par SES règles), la dépense de l'un refusée sous l'autre, un avenant sur le premier qui crée la version 2 sans toucher au second (version, validité et montant inchangés), la demande antérieure qui garde sa version, un accès d'une autre organisation qui ne voit ni accord ni profil, et **aucune écriture comptable créée** en ajoutant le second accord et sa configuration (pas de duplication des données comptables). Un test vérifie qu'aucune application installée n'est propre à un bailleur (le critère qui prime). Mutations : taux de l'accord 2 et recherche du profil en vigueur sans l'accord, toutes deux tuées.
> **Limites déclarées, pas contournées.** **T14 (connectivité dégradée) n'est pas livré** : la capture hors ligne est la version 2 du plan ; la recette le déclare (`NON_LIVRES`) et vérifie qu'il figure bien au plan. T1 à T13, T15 et T16 s'appuient sur les tests des lots précédents plutôt que sur un nouveau scénario ; T13 (reprise à écart nul) repose sur les données du contrôle de sortie de L8, pas sur une base cliente réelle. Les profils BAD, UE, FIDA, Fonds mondial, BID et Nations unies restent des squelettes sourcés (L10-T01) : T3 démontre le mécanisme, pas le contenu réglementaire.

> **Revue de code de L10 et corrections.** Dix constats, vérifiés un par un contre le code : **huit retenus et corrigés**, deux écartés. Retenus : (1) le montant d'un accord était celui d'aujourd'hui et non celui de la date du tableau (un avenant postérieur y comptait) — corrigé, testé avec un avenant daté après le jour demandé ; (2) les financements reçus ne s'arrêtaient pas à la date du tableau — borne `min(au, jour)` ; (3) la descente d'un solde de **relevé** proposait les écritures du grand livre, dont la somme n'est pas le chiffre cliqué — le détail est désormais de type `compte_releve`, sans écriture ; (4) un appel de `controles_en_attente` par objet évalué (N+1) — seuls les objets ayant une évaluation bloquante ou « à vérifier » sont examinés ; (5) l'exécution budgétaire est l'état d'aujourd'hui quel que soit le jour demandé — **avertissement explicite** `tableau_de_bord.execution_etat_courant` (le calcul à une date passée n'est pas fait : les soldes sont incrémentaux) ; (6) l'API acceptait un type de taux ou une devise inconnus et répondait « non consolidé » — refus 422 ; (7) la recette acceptait un test cité ignoré (`skip`/`xfail`) ou vide — vérification par analyse du code source ; (8) le test T17 laissait `app.org_id` posé — `RESET` en fin de test. Les requêtes du tableau et de la descente sont maintenant **définies une seule fois** (`sources.py`) : plus de copie qui diverge, `NotFound` importé en tête.
> **Écartés après vérification.** « Le périmètre ne retient que les habilitations sans site » : c'est exactement la règle de `est_habilite` sans site, donc tableau et descente concordent (et un utilisateur limité à un site ne voit pas des chiffres de tout le projet). « Départage des taux » : la base garantit un seul taux par devise, date et type (`uq_taux_jour_type`). **Reste vrai :** le budget « courant » est la version courante d'aujourd'hui, pas celle de la date demandée (l'historique des versions n'est pas daté de façon exploitable) ; il est couvert par l'avertissement du point 5.

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

## A.2bis Avancement du front-end

> **F1 — API de session (livrée).** Le dépôt n'avait **aucun frontend** (backend seul) et **aucun point d'entrée de connexion**. `niveau1_socle/organisations/{api,urls}.py` : `GET /api/v1/session/csrf/` (jeton CSRF), `POST …/connexion/`, `GET|PATCH …/moi/` (qui je suis, mon organisation, ma langue, mes projets avec, pour chacun, les opérations autorisées et celles limitées à un site), `POST …/deconnexion/`. Authentification par **session** (cookie HttpOnly), CSRF contrôlé partout, connexion comprise ; un identifiant inconnu, un mauvais mot de passe et un compte désactivé donnent exactement la même réponse (401 `IDENTIFIANTS_INVALIDES`) ; la session change à la connexion (contre la fixation) ; un visiteur reçoit un 401 `NON_AUTHENTIFIE` lisible. 15 tests, 7 mutations (6 tuées, 1 équivalente retirée).
> **Limites assumées.** Aucune limitation du nombre de tentatives de connexion (à poser au niveau du proxy ou de Fly) ; pas de réinitialisation de mot de passe ni de double authentification ; un compte de plateforme (sans organisation) peut se connecter mais ne voit aucun projet. Le frontend lui-même (React, TypeScript, Vite) reste à construire : étape F2.

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
