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
