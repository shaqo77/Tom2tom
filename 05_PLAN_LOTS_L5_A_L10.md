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

---

### L5-T04 — Activation, versionnement, date d'effet

Service `activer_exigence()` : `proposed` → `validated` → `active`, transitions tracées.

**La contrainte posée en L0-T08 interdit déjà le passage en `active` sans validateur**, au niveau de la base. Vérifiez qu'elle est toujours là.

`ConfigurationProjet` : agrégat versionné de tout ce qui est actif à une date donnée. **Toute génération de rapport résout la configuration active à la date d'effet de la période**, jamais la configuration courante.

**Contrôle.** Modifier une exigence avec effet au 1ᵉʳ janvier 2028, puis régénérer un rapport du troisième trimestre 2027 : le rapport est **inchangé**.

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

### L10-T03 — Recette d'architecture

Exécuter les quatorze tests de réception de la [spécification fonctionnelle](01_SPECIFICATION_FONCTIONNELLE.md) §17, dont les sept du cahier des charges de l'unité de gestion.

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

ARCHITECTURE (les 14 tests de réception)
[ ] Nouveau projet, nouveau bailleur, nouveau modèle : par PARAMÉTRAGE,
    sans application distincte et sans duplication des données
```

---

*Retour : [guide de démarrage](03_GUIDE_DEMARRAGE.md) · [lots L0 à L4](04_PLAN_LOTS_L0_A_L4.md) · [spécification fonctionnelle](01_SPECIFICATION_FONCTIONNELLE.md) · [architecture technique](02_ARCHITECTURE_TECHNIQUE.md)*
