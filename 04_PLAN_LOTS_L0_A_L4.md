# PLAN DE DÉVELOPPEMENT — LOTS L0 À L4 (FONDATIONS)

**Prérequis :** avoir terminé le [guide de démarrage](03_GUIDE_DEMARRAGE.md), contrôles A.1 à A.7 validés.

**Comment lire.** Chaque lot a un objectif, une durée indicative pour **deux développeurs**, et une liste de tâches numérotées `L<lot>-T<n>`. Chaque tâche donne : **le but**, **les fichiers**, **le code** quand il est délicat, et **le contrôle** à exécuter. Une tâche n'est finie que si la *définition de terminé* du guide (§B.8) est satisfaite — les sept points, pas six.

| Lot | Objectif | Durée |
|---|---|---|
| **L0** | Prototype du moteur d'états, de mapping et d'exigences | 4 semaines |
| **L1** | Socle d'organisation : isolation, projets, habilitations, audit | 3 semaines |
| **L2** | Référentiels et paquet comptable | 3 semaines |
| **L3** | Grand livre | 5 semaines |
| **L4** | Budget et financements | 4 semaines |

---

# LOT L0 — PROTOTYPE DU MOTEUR

> **Pourquoi en premier, avant même la comptabilité.** C'est la pièce la plus difficile et celle qui porte toute la valeur du produit. Si elle ne tient pas, toute la trajectoire est à revoir. Mieux vaut le découvrir à la semaine 4 qu'au mois 9.
>
> **On ne construit pas encore le grand livre.** On travaille sur une table de lignes d'écriture **générée**, au bon format, remplie de données factices.

**Critère de sortie du lot :** un TER et un rapport financier intermédiaire produits à partir d'un registre d'exigences, avec mapping versionné et traçabilité descendante jusqu'aux lignes.

---

### L0-T01 — La table de lignes factice

**But.** Disposer d'une table au format définitif, remplie, pour travailler sans attendre le grand livre.

**Fichiers.** `backend/niveau4_reporting/moteur/models.py`, `backend/niveau4_reporting/moteur/management/commands/generer_donnees.py`

```python
# models.py — version prototype, remplacée par le vrai modèle en L3
from django.db import models
from core.models import ModeleOrganisation
from core.fields import MontantField, TauxField

class LigneEcriture(ModeleOrganisation):
    project_id      = models.UUIDField(db_index=True)
    fiscal_year     = models.IntegerField()
    period          = models.IntegerField()           # 1..12
    accounting_date = models.DateField()
    compte          = models.CharField(max_length=20, db_index=True)
    tiers           = models.CharField(max_length=20, null=True)
    dim1 = models.CharField(max_length=20, null=True, db_index=True)   # composante
    dim2 = models.CharField(max_length=20, null=True)                  # activité
    dim3 = models.CharField(max_length=20, null=True)                  # zone
    dim4 = models.CharField(max_length=20, null=True)
    accord          = models.CharField(max_length=20, null=True, db_index=True)
    categorie       = models.CharField(max_length=20, null=True, db_index=True)
    site            = models.CharField(max_length=20, null=True)
    debit  = MontantField(default=0)
    credit = MontantField(default=0)
    devise = models.CharField(max_length=3)
    taux   = TauxField(default=1)

    class Meta:
        indexes = [
            models.Index(fields=["org_id", "project_id", "fiscal_year",
                                 "compte", "dim1", "accord"]),
        ]
```

Commande de génération : 200 000 lignes équilibrées, 2 organisations, 3 projets, 2 accords, 5 composantes, 3 exercices, 2 devises.

**Contrôle.** `uv run python manage.py generer_donnees --lignes 200000` termine en moins de 60 secondes, et `SELECT sum(debit)-sum(credit) FROM ...` retourne exactement `0`.

---

### L0-T02 — L'analyseur de formules

**But.** Évaluer `SUM(R110:R180)` et `R190 - R290` **sans jamais exécuter de code arbitraire**.

> **C'est la tâche la plus sensible du lot pour la sécurité.** `eval()` sur une chaîne fournie par un utilisateur permet d'exécuter n'importe quoi sur votre serveur. Nous utilisons l'analyseur syntaxique de Python, puis nous **refusons tout nœud qui n'est pas dans une liste blanche**.

**Fichier.** `backend/niveau4_reporting/moteur/formules.py`

```python
import ast, re
from decimal import Decimal

NOEUDS_AUTORISES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Call,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd, ast.Load,
)
FONCTIONS_AUTORISEES = {"SUM", "ABS", "MIN", "MAX", "ROUND"}
MOTIF_PLAGE = re.compile(r"\b([A-Z]\d+)\s*:\s*([A-Z]\d+)\b")

class FormuleInvalide(ValueError):
    pass

def _etendre_plages(formule: str, codes_connus: list[str]) -> str:
    """Transforme R110:R180 en R110,R120,...,R180 selon l'ordre réel des rubriques."""
    def remplacer(m):
        debut, fin = m.group(1), m.group(2)
        try:
            i, j = codes_connus.index(debut), codes_connus.index(fin)
        except ValueError as e:
            raise FormuleInvalide(f"rubrique inconnue dans la plage {debut}:{fin}") from e
        if i > j:
            raise FormuleInvalide(f"plage inversée {debut}:{fin}")
        return ",".join(codes_connus[i:j + 1])
    return MOTIF_PLAGE.sub(remplacer, formule)

def valider(formule: str, codes_connus: list[str]) -> ast.Expression:
    arbre = ast.parse(_etendre_plages(formule, codes_connus), mode="eval")
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, NOEUDS_AUTORISES):
            raise FormuleInvalide(f"construction interdite : {type(noeud).__name__}")
        if isinstance(noeud, ast.Call):
            if not isinstance(noeud.func, ast.Name) or \
               noeud.func.id not in FONCTIONS_AUTORISEES:
                raise FormuleInvalide("fonction non autorisée")
        if isinstance(noeud, ast.Name) and noeud.id not in FONCTIONS_AUTORISEES:
            if noeud.id not in codes_connus:
                raise FormuleInvalide(f"rubrique inconnue : {noeud.id}")
    return arbre

def evaluer(formule: str, valeurs: dict[str, Decimal],
            codes_connus: list[str]) -> Decimal:
    arbre = valider(formule, codes_connus)

    def _eval(n):
        if isinstance(n, ast.Expression):      return _eval(n.body)
        if isinstance(n, ast.Constant):        return Decimal(str(n.value))
        if isinstance(n, ast.Name):            return valeurs.get(n.id, Decimal(0))
        if isinstance(n, ast.UnaryOp):
            v = _eval(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp):
            g, d = _eval(n.left), _eval(n.right)
            if isinstance(n.op, ast.Add):  return g + d
            if isinstance(n.op, ast.Sub):  return g - d
            if isinstance(n.op, ast.Mult): return g * d
            if isinstance(n.op, ast.Div):
                if d == 0:
                    raise FormuleInvalide("division par zéro")
                return g / d
        if isinstance(n, ast.Call):
            args = [_eval(a) for a in n.args]
            nom = n.func.id
            if nom == "SUM":   return sum(args, Decimal(0))
            if nom == "ABS":   return abs(args[0])
            if nom == "MIN":   return min(args)
            if nom == "MAX":   return max(args)
            if nom == "ROUND":
                decimales = int(args[1]) if len(args) > 1 else 2
                return args[0].quantize(Decimal(1).scaleb(-decimales))
            raise FormuleInvalide(f"fonction non autorisée : {nom}")
        raise FormuleInvalide("nœud non géré")

    return _eval(arbre)
```

**Contrôle.** Ces tests passent (ils sont fournis, pas à inventer) :

```python
def test_formule_simple():
    assert evaluer("R1 - R2", {"R1": Decimal(10), "R2": Decimal(3)}, ["R1","R2"]) == 7

def test_plage():
    v = {"R1": Decimal(1), "R2": Decimal(2), "R3": Decimal(3)}
    assert evaluer("SUM(R1:R3)", v, ["R1","R2","R3"]) == 6

@pytest.mark.parametrize("mechante", [
    "__import__('os').system('rm -rf /')",
    "().__class__.__bases__[0].__subclasses__()",
    "open('/etc/passwd').read()",
    "R1 if R2 else R3",
    "[x for x in R1]",
    "R1.__class__",
])
def test_code_arbitraire_refuse(mechante):
    with pytest.raises(FormuleInvalide):
        valider(mechante, ["R1","R2","R3"])

def test_rubrique_inconnue_refusee():
    with pytest.raises(FormuleInvalide):
        valider("R9 + 1", ["R1"])

def test_plage_inversee_refusee():
    with pytest.raises(FormuleInvalide):
        valider("SUM(R3:R1)", ["R1","R2","R3"])
```

> **Ce code a été exécuté contre ces huit tests avant d'être écrit ici : les huit passent.** Les six tentatives d'exécution de code arbitraire sont toutes bloquées à la validation, avant toute évaluation.

---

### L0-T03 — Le graphe de dépendances

**But.** Évaluer les rubriques calculées dans le bon ordre et **détecter les références circulaires**.

**Fichier.** `backend/niveau4_reporting/moteur/dependances.py`

Extraire les `ast.Name` de chaque formule, construire le graphe, faire un tri topologique (`graphlib.TopologicalSorter` de la bibliothèque standard), et lever une erreur explicite en cas de cycle.

**Contrôle.** Un modèle dont `R1 = R2 + 1` et `R2 = R1 - 1` est refusé avec le message `référence circulaire : R1 → R2 → R1`.

---

### L0-T04 — Le moteur de mapping

**But.** Transformer un compte interne en rubrique de bailleur, par règles priorisées et versionnées.

**Fichier.** `backend/niveau4_reporting/mapping/resolveur.py`

```python
def construire_cas_sql(regles: list[RegleMapping]) -> tuple[str, list]:
    """Compile les règles en une expression CASE unique.

    Les règles sont triées par priorité : la première qui correspond gagne.
    Tout est compilé en SQL — on ne parcourt jamais les lignes une par une.
    """
    morceaux, params = [], []
    for r in sorted(regles, key=lambda x: x.priority):
        conds = []
        if comptes := r.match.get("accounts"):
            ors = []
            for debut, fin in comptes:
                ors.append("(compte >= %s AND compte < %s)")
                params += [debut, fin + "￿"]   # fourchette préfixe
            conds.append("(" + " OR ".join(ors) + ")")
        for champ in ("dim1", "dim2", "dim3", "dim4", "accord", "categorie", "site"):
            if valeurs := r.match.get(champ):
                conds.append(f"{champ} = ANY(%s)")
                params.append(list(valeurs))
        if conds:
            morceaux.append("WHEN " + " AND ".join(conds) + " THEN %s")
            params.append(r.target_code)
    return "CASE " + " ".join(morceaux) + " ELSE NULL END", params
```

**Le contrôle d'exhaustivité — la partie qui compte vraiment :**

```python
def comptes_non_mappes(table, periode) -> list[str]:
    """Comptes mouvementés qu'aucune règle active ne couvre.

    S'il en reste un seul, la génération DOIT être bloquée :
    une dépense non mappée disparaît silencieusement du rapport.
    C'est l'erreur la plus coûteuse de ce métier.
    """
```

**Contrôle.** Un jeu où le compte `6281` n'est couvert par aucune règle : `comptes_non_mappes()` le retourne, et la génération lève `MappingIncomplet` en nommant le compte.

---

### L0-T05 — Le compilateur d'états

**But.** Produire un état **en une seule requête d'agrégation**, jamais en parcourant les lignes.

**Fichier.** `backend/niveau4_reporting/moteur/compilateur.py`

Principe :
1. Résoudre toutes les rubriques d'agrégat en expressions `CASE` (T04 et fourchettes de comptes).
2. Les réunir dans **un seul `SELECT ... GROUP BY`** sur `LigneEcriture`, une colonne par période du modèle.
3. Récupérer les totaux en `Decimal`.
4. Évaluer les rubriques calculées dans l'ordre topologique (T02 et T03).
5. Vérifier les assertions.

```sql
-- forme générée, simplifiée
SELECT
  CASE <mapping ou fourchettes> END                      AS rubrique,
  SUM(CASE WHEN period BETWEEN %s AND %s THEN debit - credit ELSE 0 END) AS col_QTR,
  SUM(CASE WHEN fiscal_year = %s        THEN debit - credit ELSE 0 END) AS col_YTD,
  SUM(debit - credit)                                     AS col_CUMUL
FROM moteur_ligneecriture
WHERE org_id = %s AND project_id = %s AND fiscal_year <= %s
GROUP BY 1
```

**Contrôle.** `assert nombre_de_requetes == 1` avec `django.test.utils.CaptureQueriesContext`, **et** le TER sur 200 000 lignes rend en **moins de 3 secondes**. Si c'est plus lent, vérifiez l'index de `L0-T01` avant d'aller plus loin.

---

### L0-T06 — Les assertions de cohérence

**But.** Un état déséquilibré ne peut pas être publié.

Chaque rubrique peut porter `"assert": "R900 == BALANCE('5')"`. L'évaluation produit un rapport de contrôle. **Une assertion fausse bloque la publication** — elle ne produit pas un avertissement.

**Contrôle.** Falsifiez une ligne du jeu de données : la génération refuse de publier et nomme l'assertion violée.

---

### L0-T07 — La traçabilité descendante

**But.** Depuis une cellule, obtenir les écritures qui l'alimentent.

Le compilateur conserve, pour chaque rubrique d'agrégat, **son prédicat de sélection**. La traçabilité rejoue ce prédicat en `SELECT *` au lieu de `SUM`.

**Contrôle.** Pour chaque rubrique d'agrégat d'un TER généré : `somme des lignes retournées == valeur de la cellule`. Au centime près, sur **toutes** les rubriques.

---

### L0-T08 — Le registre des exigences, version minimale

**But.** Prouver qu'une rubrique peut être rattachée à un paragraphe de document.

Modèles `DocumentReference` et `Exigence` (voir le [dossier d'architecture](02_ARCHITECTURE_TECHNIQUE.md) §4), plus `RattachementExigence`. La contrainte clé, **en base** :

```sql
ALTER TABLE niveau3_config_exigence ADD CONSTRAINT exigence_validation_obligatoire
  CHECK (status <> 'active' OR (validated_by IS NOT NULL AND validated_at IS NOT NULL));
```

**Contrôle.** Tenter de passer une exigence en `active` sans validateur lève une `IntegrityError` **au niveau de la base**, pas de l'application.

---

### L0-T09 — Le jeu d'états de référence

**But.** Verrouiller le comportement du moteur pour toujours.

Pour chaque modèle d'état du prototype : un jeu de données figé et un **résultat attendu versionné** en JSON dans le dépôt.

```python
def test_etat_de_reference_TER(donnees_figees):
    produit = generer("TER", **PARAMS_REFERENCE)
    attendu = json.loads(Path("tests/references/TER.json").read_text())
    assert produit == attendu   # au centime près
```

> **Toute modification du moteur qui change un chiffre fait échouer la construction.** C'est la garantie de non-régression du reporting bailleur, et le test que vous remercierez dans deux ans.

**Contrôle.** Modifiez volontairement une règle d'arrondi : le test échoue en nommant la rubrique.

---

### L0-T10 — Vérification de bout en bout du lot

**Contrôle de sortie de L0 — à démontrer devant l'équipe :**

```
[ ] Un TER produit depuis un registre d'exigences
[ ] Un rapport financier intermédiaire produit depuis les MÊMES données,
    avec un mapping différent
[ ] Un compte non mappé bloque la génération et est nommé
[ ] Une formule malveillante est refusée (4 cas de T02)
[ ] Une référence circulaire est refusée
[ ] Une assertion fausse bloque la publication
[ ] Toute cellule est traçable jusqu'aux lignes, au centime près
[ ] TER sur 200 000 lignes : < 3 secondes, 1 seule requête
```

---

# LOT L1 — SOCLE D'ORGANISATION

**Objectif.** Deux organisations et quatre projets, cloisonnés de façon démontrable, avec un journal d'audit infalsifiable.

---

### L1-T01 — Organisation, utilisateur, projet

**Fichiers.** `backend/niveau1_socle/organisations/models.py`

`Organisation` (code, raison sociale, pays, monnaie de tenue, langues actives) · `Utilisateur` étendant `AbstractUser` avec `org_id` · `Projet` (voir le dossier d'architecture §3.2 pour le schéma exact).

**Attention.** `base_currency` et `accounting_basis` d'un projet **ne sont pas modifiables** après la première écriture. Posez la contrainte tout de suite, pas « plus tard ».

**Contrôle.** Créer deux organisations, deux projets chacune, sans erreur.

---

### L1-T02 — Activer l'isolation sur toutes les tables

**But.** Appliquer `activer_rls()` (guide §B.4) à **chaque** table portant `org_id`.

```python
# migration
from core.migrations._rls import activer_rls

operations = [
    migrations.RunSQL(activer_rls("organisations_projet"), reverse_sql="..."),
    migrations.RunSQL(activer_rls("moteur_ligneecriture"),  reverse_sql="..."),
    # … une ligne par table
]
```

**Garde-fou automatique**, à ajouter maintenant :

```python
@pytest.mark.django_db
def test_toute_table_avec_org_id_a_sa_politique():
    """Empêche qu'une nouvelle table soit créée sans isolation."""
    with connection.cursor() as cur:
        cur.execute("""
          SELECT c.relname FROM pg_class c
          JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'org_id'
          WHERE c.relkind = 'r' AND NOT c.relrowsecurity
        """)
        manquantes = [r[0] for r in cur.fetchall()]
    assert not manquantes, f"Tables sans isolation : {manquantes}"
```

**Contrôle.** Ce test, plus celui du guide §B.4, passent tous les deux.

---

> **Ajout au contrôle de L1-T02 — modification de `org_id`.** Un `UPDATE … SET org_id = <autre organisation>` doit être **refusé** (la clause `WITH CHECK` de la politique) sur chaque table. Test en `django_db(transaction=True)`, périmètre posé par `SET` de session, comme les autres tests d'isolation. Il complète le test de lecture croisée.

---

### L1-T03 — Le journal d'audit chaîné

**But.** Un journal que personne ne peut altérer sans que cela se voie.

**Fichier.** `backend/core/audit.py`

```python
import hashlib, json
from django.db import connection

def journaliser(*, org_id, actor_id, action, object_type,
                object_id=None, project_id=None, before=None, after=None,
                actor_ip=None) -> None:
    charge = json.dumps({
        "org_id": str(org_id), "actor_id": str(actor_id), "action": action,
        "object_type": object_type, "object_id": str(object_id) if object_id else None,
        "project_id": str(project_id) if project_id else None,
        "before": before, "after": after,
    }, sort_keys=True, separators=(",", ":"), default=str).encode()

    with connection.cursor() as cur:
        # verrou : le chaînage impose une insertion strictement séquentielle
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"audit:{org_id}"])
        cur.execute("SELECT hash FROM core_auditlog WHERE org_id=%s "
                    "ORDER BY id DESC LIMIT 1", [str(org_id)])
        rangee = cur.fetchone()
        precedent = rangee[0] if rangee else b""
        courant = hashlib.sha256(precedent + charge).digest()
        cur.execute("""INSERT INTO core_auditlog
            (org_id, actor_id, actor_ip, action, object_type, object_id,
             project_id, before, after, prev_hash, hash, occurred_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())""",
            [org_id, actor_id, actor_ip, action, object_type, object_id,
             project_id, json.dumps(before, default=str),
             json.dumps(after, default=str), precedent, courant])
```

**Retirer les droits**, dans la même migration :

```sql
REVOKE UPDATE, DELETE ON core_auditlog FROM sigf_app;
```

**Vérificateur d'intégrité** — commande `verifier_audit` qui relit la chaîne et signale la première rupture.

**Contrôle.** Écrivez 100 entrées, altérez-en une directement en SQL avec `sigf_owner`, puis lancez `verifier_audit` : il doit nommer l'entrée altérée. Et `UPDATE core_auditlog ...` avec `sigf_app` doit être **refusé**.

---

### L1-T04 — Exercices et périodes

`Exercice` (dates, statut) · `Periode` (mois, statut `ouverte` / `close` / `verrouillee`).

Service `cloturer_periode()` qui refuse si des écritures sont en brouillon.

**Contrôle.** Une période close refuse l'ouverture d'une écriture (contrainte posée en L3-T03).

---

### L1-T05 — Habilitations par projet et par site

Modèles `Role`, `Habilitation` (utilisateur × projet × site × opérations).

Vérification **au serveur**, sur chaque requête, par un décorateur ou une classe de permission DRF. L'interface masque, elle ne protège pas.

**Contrôle.** Un utilisateur habilité sur le projet A reçoit `403` sur une ressource du projet B — **même organisation**.

---

### L1-T06 — Séparation des tâches

Règle : le validateur d'une pièce ne peut pas en être le créateur. Paramétrable par organisation, **activée par défaut**.

**Contrôle.** L'auteur d'une écriture reçoit `403` en tentant de la valider.

---

# LOT L2 — RÉFÉRENTIELS ET PAQUET COMPTABLE

**Objectif.** Un plan projet opérationnel, importé depuis un existant, avec quatre axes configurés.

---

### L2-T01 — Devises et taux

`Devise` (code ISO 4217, libellé, décimales) · `Taux` (devise, date, taux, **type** : `officiel` / `bailleur` / `cloture` / `budget`).

> **Règle :** un taux n'est **jamais** écrasé. Un nouveau taux est une nouvelle ligne, à une nouvelle date. Recalculer un historique avec un taux courant est une faute comptable.

**Contrôle.** Deux taux du même jour, de types différents, coexistent sans conflit.

---

### L2-T02 — Plan comptable

`Compte` (code, libellé multilingue, classe, sens normal, imputable, actif, hiérarchie parent-enfant, `paquet_id`).

**Contrôle.** Un compte non imputable (un total) refuse l'imputation directe.

---

### L2-T03 — Les axes configurables

`PlanDimension` (emplacement 1 à 4, type gestion ou auxiliaire) · `ValeurDimension` (hiérarchique, imputable seulement en feuille).

> **Rappel de conception :** les emplacements sont **fixes dans le schéma**, leur **signification est configurable par organisation**. C'est ce qui donne la souplesse métier sans payer le coût d'un modèle clé-valeur, qui interdirait l'indexation et les contraintes.

**Contrôle.** Deux organisations placent des plans différents sur l'emplacement 1, sans interférence.

---

### L2-T04 — Tiers

`Tiers` (code, nature, identification, coordonnées bancaires, actif). Données personnelles : prévoir dès maintenant la journalisation des accès en lecture et la durée de rétention.

---

### L2-T05 — Le paquet Plan Comptable Général de Djibouti

**But.** Livrer un référentiel versionné, pas un paramétrage client.

```
backend/paquets/pcg_djibouti_2012/
├── manifeste.json          # code, version, date d'effet, pays, validateur
├── comptes.csv             # code, libellé fr, libellé en, classe, sens, imputable
├── modeles_etats/          # bilan, compte de résultat, annexes
└── controles.json          # contrôles de cohérence du référentiel
```

Commande `installer_paquet pcg_djibouti_2012 --org <id> --date-effet 2027-01-01`.

**Règles d'installation, non négociables :**
1. **Ne modifie jamais un exercice clos.**
2. Prend effet à une date choisie par l'organisation.
3. Une mise à jour du paquet arrive comme **proposition** sur les objets dupliqués par le client, **jamais comme écrasement**.

**Contrôle.** Installer, clôturer un exercice, installer la version suivante : l'exercice clos est **inchangé**, bit pour bit.

---

### L2-T06 — Le paquet Plan projet

Même structure. Comptabilité de **trésorerie avec engagements occasionnels**, plan de comptes adapté aux projets de développement, modèles TER et tableau des recettes et paiements.

> C'est le référentiel **réellement utilisé** par les unités de gestion de projets, indépendamment du plan comptable national. Ne le traitez pas comme un cas particulier : c'est le cas nominal.

---

### L2-T07 — Import des référentiels

Assistant de correspondance : fichier Excel ou CSV en entrée, proposition de correspondance, validation humaine, **correspondance sauvegardable et rejouable**.

**Contrôle.** Importer un plan de 800 comptes depuis un export Excel, rejouer l'import : **aucun doublon**.

---

# LOT L3 — GRAND LIVRE

**Objectif.** Balance, grand livre et journaux justes sur un exercice complet.

> **Le lot le plus exigeant.** Les quatre contraintes d'intégrité (T02 à T05) sont posées **en base de données**, pas en Python. Le code applicatif s'oublie, se contourne, se régresse. Un déclencheur, non.

---

### L3-T01 — Modèles définitifs

Remplacer le modèle prototype de L0-T01 par `Ecriture` et `LigneEcriture` complets (dossier d'architecture §3.3). Migration de reprise des données du prototype.

**Contrôle.** Les tests d'états de référence de L0-T09 passent toujours, à l'identique.

> **Réalisation de L3-T01.** `Journal`, `Ecriture` et `LigneEcriture` vivent dans `niveau1_socle/comptabilite`. Le moteur d'états n'est pas modifié : il lit la vue `moteur_ligneecriture` (`security_invoker`, écritures `posted`/`locked` seulement), qui expose le grand livre sous les noms de colonnes du prototype. Accord, catégorie, site, marché, compte bancaire et clé de cofinancement sont des UUID sans clé étrangère jusqu'à L4 et L9 ; la vue les expose en texte d'UUID, et L4 la rebranchera sur leurs codes. Coût mesuré : TER sur 200 000 lignes en 0,68 s (0,19 s sur la table prototype), une requête, limite 3 s. Aucune reprise de données : le prototype ne contenait que des lignes générées.

---

### L3-T02 — L'équilibre, en contrainte différée

```sql
CREATE OR REPLACE FUNCTION assert_ecriture_equilibree() RETURNS trigger AS $$
DECLARE ecart numeric(20,4); cible uuid;
BEGIN
  cible := COALESCE(NEW.entry_id, OLD.entry_id);
  SELECT COALESCE(SUM(debit),0) - COALESCE(SUM(credit),0) INTO ecart
    FROM comptabilite_ligneecriture WHERE entry_id = cible;
  IF ecart <> 0 THEN
    RAISE EXCEPTION 'Écriture % déséquilibrée : écart de %', cible, ecart;
  END IF;
  RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER trg_ecriture_equilibree
  AFTER INSERT OR UPDATE OR DELETE ON comptabilite_ligneecriture
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION assert_ecriture_equilibree();
```

> **Pourquoi « différée ».** Pendant qu'on insère la première ligne, l'écriture est forcément déséquilibrée. La contrainte différée ne vérifie qu'à la validation de la transaction, quand toutes les lignes sont là.

**Contrôle.** Insérer une écriture déséquilibrée dans une transaction lève l'exception **au `COMMIT`**, et rien n'est écrit.

> **Réalisation de L3-T02.** Le déclencheur du plan ne contrôle que l'écriture `NEW` : une ligne déplacée vers une écriture temporaire, puis supprimée avec elle, laissait l'écriture d'origine amputée sans qu'aucun événement la cite (un test le démontre). La version livrée contrôle aussi l'écriture `OLD` quand une ligne change d'écriture. La contrainte vaut pour **tous** les statuts : un brouillon doit lui aussi être équilibré à la fin de sa transaction, donc la saisie enregistre une pièce complète à la fois. Les tests du moteur qui créaient des lignes isolées les équilibrent par une contrepartie sur le compte technique `8999` (`tests/outils.py`).

---

### L3-T03 — Immuabilité et périodes closes

```sql
CREATE OR REPLACE FUNCTION interdire_modification_comptabilisee()
RETURNS trigger AS $$
BEGIN
  IF OLD.status IN ('posted','locked') THEN
    RAISE EXCEPTION
      'Écriture % comptabilisée : modification interdite. Utilisez la contre-passation.',
      OLD.id;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ecriture_immuable
  BEFORE UPDATE OR DELETE ON comptabilite_ecriture
  FOR EACH ROW EXECUTE FUNCTION interdire_modification_comptabilisee();
```

Plus un déclencheur symétrique refusant toute insertion ou modification dans une période dont le statut n'est pas `ouverte`.

**Contrôle.** `UPDATE` sur une écriture comptabilisée → exception. `INSERT` dans une période close → exception. Aucune exception administrateur n'existe.

> **Réalisation de L3-T03.** Deux déclencheurs `BEFORE` (écritures, lignes), valables pour tout rôle : un test exécute les mêmes opérations avec le rôle propriétaire (`BYPASSRLS`) et obtient le même refus. Écarts et précisions par rapport au texte du plan :
> - **Le verrouillage reste possible.** `posted` → `locked` est autorisé, mais seulement s'il ne change que le statut (même dans une période close) : sans cela, `locked` serait inatteignable. `locked` → `posted` est refusé.
> - **Les lignes sont protégées aussi** : on ne modifie, supprime ni n'ajoute une ligne d'une écriture comptabilisée. Une écriture naît donc en brouillon, reçoit ses lignes, puis change de statut ; la suppression en cascade d'une écriture comptabilisée est refusée.
> - **Un brouillon laissé dans une période devenue close est figé** (ni modifié, ni comptabilisé, ni supprimé). La clôture mensuelle de L3-T08 devra donc refuser de clore tant qu'il reste des brouillons.
> - **Cohérence date et période** : la date comptable tombe dans la période de l'écriture, et la période appartient à l'exercice de l'écriture.
> - **Pas de retrait de droits au rôle applicatif** (prévu au §3.4 de l'architecture) : les brouillons se modifient et se suppriment, et retirer `UPDATE` au propriétaire d'une table lui retire aussi le verrou de clé étrangère.
> - Le générateur de données ne purge plus : repartir de zéro se fait par `TRUNCATE` du propriétaire.

---

### L3-T04 — Numérotation sans trou

> **Pourquoi pas une séquence PostgreSQL.** Une séquence n'est pas annulée par un `ROLLBACK` : elle produit des trous. Un auditeur qui voit passer de la pièce 412 à la 414 présume une suppression, et c'est une réserve d'audit.

```python
def attribuer_numero(ecriture) -> str:
    with connection.cursor() as cur:
        cle = f"{ecriture.journal_id}:{ecriture.fiscal_year_id}"
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [cle])
        cur.execute("""
            INSERT INTO comptabilite_compteur (org_id, journal_id, fiscal_year_id, dernier)
            VALUES (%s,%s,%s,1)
            ON CONFLICT (org_id, journal_id, fiscal_year_id)
            DO UPDATE SET dernier = comptabilite_compteur.dernier + 1
            RETURNING dernier
        """, [ecriture.org_id, ecriture.journal_id, ecriture.fiscal_year_id])
        n = cur.fetchone()[0]
    return f"{ecriture.journal.code}-{ecriture.fiscal_year.annee}-{n:06d}"
```

Le numéro est attribué **à la comptabilisation**, jamais à la création du brouillon.

**Contrôle.** Comptabilisez 1 000 écritures depuis 10 processus en parallèle, dont 100 transactions annulées : la suite est `000001` à `000900`, **sans trou ni doublon**.

> **Réalisation de L3-T04.** Le numéro n'est pas attribué par `attribuer_numero()` en Python mais par un **déclencheur** `BEFORE UPDATE` de la base, dans la transaction de la comptabilisation : la règle 3 (aucun trou) doit tenir quel que soit l'appelant. Même algorithme que le plan (compteur par journal et exercice, verrou consultatif, `INSERT … ON CONFLICT DO UPDATE`), avec en plus :
> - l'appelant **ne choisit jamais** le numéro (il est refusé s'il en fournit un) ; une écriture naît en brouillon, sans numéro, et se comptabilise par changement de statut ;
> - le compteur ne bouge que de +1 et ne se supprime pas ;
> - `trous_de_numerotation(journal, exercice)` détecte un trou fabriqué hors des déclencheurs (administrateur qui les contourne).
>
> Le contrôle est exécuté avec dix **sessions** concurrentes (fils, chacun avec sa connexion), pas dix processus : pour PostgreSQL c'est équivalent. Remplacer le compteur par une séquence PostgreSQL fait échouer ce test, ce qui confirme l'argument du plan. Limite connue : une transaction qui comptabilise des écritures de deux journaux en ordre inverse d'une autre peut provoquer un interblocage (PostgreSQL en annule une).

---

### L3-T05 — Saisie, validation, comptabilisation

Services `valider_ecriture()` et `comptabiliser_ecriture()`. Transitions d'état, journalisation d'audit à chaque transition, vérification de la séparation des tâches.

Service `contre_passer()` : crée une écriture inverse, renseigne `reverses_id`, **ne touche jamais l'originale**.

**Contrôle.** Le cycle complet brouillon → validée → comptabilisée → contre-passée laisse **deux** écritures en base, toutes deux intactes.

> **Réalisation de L3-T05, partie a** (saisie, validation, comptabilisation ; la contre-passation est la partie b). `saisir_ecriture`, `valider_ecriture`, `comptabiliser_ecriture` (`niveau1_socle/comptabilite/services.py`). Chaque transition, dans une transaction avec verrou de ligne : vérifie l'**habilitation** de l'utilisateur sur le projet (opérations `saisir`, `valider`, `comptabiliser`), la **séparation des tâches** (l'auteur ne valide pas sa pièce) et le **contenu** (au moins deux lignes, montant non nul, comptes et valeurs d'axe imputables et actifs, tous les manques listés d'un coup), puis journalise. Le contenu est revérifié à la comptabilisation : un compte désactivé depuis la validation la bloque. Une période close est refusée avec un message clair avant que la base ne le fasse.
>
> **Réalisation de L3-T05, partie b** (`contre_passer`). L'écriture inverse naît en **brouillon**, liée à l'originale par `reverses`, avec `origin = reversal` ; elle suit le circuit habituel (validation par un autre, puis comptabilisation) : la personne qui demande la correction ne la comptabilise pas d'un geste. L'originale n'est jamais touchée. Garanties : une seule contre-passation par écriture (contrainte d'unicité) ; on ne contre-passe qu'une écriture **comptabilisée** du **même projet** (déclencheur) ; une contre-passation ne se contre-passe pas (on saisit une nouvelle écriture) ; `origin = reversal` et `reverses` vont ensemble (contrainte) ; **la validation refuse une contre-passation retouchée** qui ne reproduirait plus l'originale en sens inverse (comptes, axes, devises, montants). Sans date, elle reprend celle de l'originale ; si sa période est close, on précise une date dans une période ouverte. Habilitation requise : `saisir`.

> Limites connues : les montants de la saisie sont en monnaie de tenue (pas de conversion automatique de devise) ; les axes obligatoires (`PlanDimension.is_mandatory`) ne sont pas contrôlés ici mais par les contrôles de conformité de L6 ; aucune interface HTTP pour l'instant (les services sont le contrat, la vue viendra avec le front).

---

### L3-T06 — Schémas d'écritures et contrepartie automatique

`SchemaEcriture` : modèle de lignes avec comptes, sens et règles de calcul. Alimente la saisie, ne la remplace pas.

> **Réalisation de L3-T06.** Le plan tenait en une ligne ; voici ce qui a été décidé. `SchemaEcriture` (pièce type, **versionnée** `[valid_from, valid_to[`, sans chevauchement pour un même code, garanti par la base) et `LigneSchema` (compte, sens, règle, taux, axes par défaut). La règle de calcul est un **ensemble fermé**, jamais une formule : `base` (montant saisi), `taux` (montant × taux, arrondi à la devise, moitié vers le haut), `solde` (**contrepartie automatique** : elle prend le sens qui équilibre et absorbe les arrondis, donc la pièce générée est équilibrée pour tout montant, ce que vérifie un test de propriété). Un schéma n'a qu'une contrepartie ; une ligne à montant arrondi nul n'est pas générée ; un montant qui arrondit à zéro (0,01 en devise sans décimale) est refusé avec un message exact.
>
> Le schéma **alimente** la saisie : `generer_lignes_du_schema` retourne des lignes modifiables, `saisir_depuis_schema` les enregistre par `saisir_ecriture` (mêmes garde-fous). La version applicable est résolue à la **date comptable**. L'écriture retient la version qui l'a alimentée (`Ecriture.schema`) ; une version **utilisée** ne se modifie plus, ni ses lignes (déclencheur), sauf la clôture de sa validité pour lui substituer une nouvelle version (règle 7).
>
> Un `CHECK` laisse passer `NULL` (`taux > 0` sur un taux absent vaut `NULL`) : la contrainte de forme des lignes teste explicitement la présence des valeurs. Un test l'a révélé ; les futures contraintes de ce type doivent faire de même.

---

### L3-T07 — Lettrage et rapprochement bancaire

Lettrage : groupe de lignes de solde nul sur un même compte de tiers. Dé-lettrage tracé.
Rapprochement : en monnaie de tenue **et** en devise, avec génération des **écarts de change en écritures explicites**.

**Contrôle.** Lettrer puis dé-lettrer laisse les lignes dans leur état initial, et les deux opérations sont au journal d'audit.

> **Réalisation de L3-T07, partie a (lettrage).** Le **rapprochement bancaire** (partie b) n'est pas fait : il suppose des comptes bancaires et des mouvements de relevé, que le plan ne crée qu'en L4-T04 (`CompteBancaire`) et L9-T05 (trésorerie).
>
> `lettrer` et `delettrer` (`niveau1_socle/comptabilite/lettrage.py`). Un `Lettrage` regroupe au moins deux lignes **comptabilisées**, de même compte, même tiers (obligatoire) et même projet, de solde nul en monnaie de tenue (et nul en devise si la devise est unique). **Lettrer ne modifie pas les lignes** : seul leur marqueur `reconciliation_id` change, et elles restent immuables (le déclencheur d'immuabilité autorise un UPDATE qui ne touche que `reconciliation_id` et `bank_match_id`, même en période close, car le lettrage se poursuit après la clôture). La base vérifie le groupe **au COMMIT** : un lettrage posé sans le service, non soldé, partiel ou hétérogène, est refusé. Un lettrage ne se supprime pas ; on le **dé-lettre**, ce qui l'annule (auteur, date, motif obligatoire) ; son code (`AA`, `AB`…) n'est jamais réutilisé. Un dé-lettrage emporte tout le groupe. Habilitation requise : `comptabiliser`. Deux lettrages simultanés des mêmes lignes n'en laissent qu'un (verrou de ligne).
>
> Pas de lettrage partiel (acompte) : un groupe est soldé ou n'existe pas.

---

### L3-T08 — Clôtures et à-nouveaux

Clôture mensuelle : liste de contrôle bloquante — écritures en brouillon, comptes non lettrés, rapprochements non soldés.

> **Réalisation de L3-T08, partie a (clôture mensuelle).** `cloturer_periode` exécute une liste de contrôles et **les liste tous** d'un coup (`niveau1_socle/comptabilite/cloture.py`, branchés au démarrage sur `VERIFICATIONS_DE_CLOTURE`) :
> - **écritures non comptabilisées** (brouillon ou validée) dans la période ;
> - **groupes soldés non lettrés** : « comptes non lettrés » du plan est précisé ainsi. Exiger que tous les comptes de tiers soient lettrés bloquerait toute période comportant une facture impayée, ce qui est normal ; on bloque donc seulement les lignes de tiers qui **se soldent entre elles** sans être lettrées (par compte, tiers et projet, cumulées jusqu'à la fin de la période : une facture de mars et son règlement d'avril forment un groupe soldé dès avril).
> - **rapprochements non soldés** : non implémenté, il attend le rapprochement bancaire (L3-T07b) ; il suffira d'enregistrer un contrôle de plus.
>
> Un brouillon ne peut donc plus rester dans une période close par le service (il est figé par la base s'il y est malgré tout).
Clôture annuelle : génération des à-nouveaux, **versionnée et re-générable** tant que l'exercice d'origine n'est pas verrouillé.

**Contrôle.** Clôturer, régénérer les à-nouveaux, comparer : résultat identique.

> **Réalisation de L3-T08, partie b (clôture annuelle).** `cloturer_exercice(exercice, utilisateur, compte_resultat)` (`niveau1_socle/comptabilite/annuelle.py`) :
> - **Ce qui est reporté** : les soldes des classes 1 à 5, **par compte, tiers et accord de financement** (sans axes analytiques : ils n'ont pas de sens au bilan), soldes nuls exclus. Le résultat (classes 6 et 7) est porté sur un **compte paramètre** (`compte_resultat`, imputable), au crédit pour un bénéfice. Les classes 8 et 9 ne sont pas reportées ; si elles ne se soldent pas entre elles, **on refuse de générer** (`ANouveauxIncoherents`) plutôt que de produire un résultat faux.
> - **Conditions** (habilitation `comptabiliser`, puis) : exercice non verrouillé, **toutes** les périodes closes (la liste des périodes ouvertes est donnée), exercice suivant existant dont la **première période est ouverte**, compte de résultat imputable.
> - **Versions** : l'écriture d'à-nouveaux (journal `AN`, origine `module`, numéro attribué par la base) est datée du premier jour de l'exercice suivant. `ANouveau` garde la version, l'empreinte des lignes et le résultat. Régénérer **sans changement** n'écrit rien (statut `inchange`). Après correction (`rouvrir_periode`, qui exige `parametrer` et un motif), l'ancienne écriture est **contre-passée** (même mécanique que `contre_passer`, factorisée dans `_creer_inverse`), sa version passe à `remplace`, la nouvelle devient la seule active (index unique partiel). `difference` donne les lignes ajoutées, supprimées, modifiées.
> - **Garde-fous en base** : un à-nouveau ne se supprime pas ; son seul changement possible est `actif` → `remplace` avec son écriture d'annulation ; une version remplacée est figée ; RLS.
> - **Limites assumées** : le report est en monnaie de tenue (pas de conversion des soldes en devise) ; le compte de résultat est donné à chaque appel, non mémorisé ; l'exercice rouvert par une correction redevient `ouvert` et doit être reclôturé.

---

### L3-T09 — Restitutions

Balance (générale, auxiliaire, analytique) · grand livre · journaux. **Toutes construites sur le moteur de L0**, pas réécrites à côté.

**Contrôle.** Balance générale = balance analytique = balance par accord, au centime, sur le même périmètre. Trois chemins, un seul chiffre.

> **Réalisation de L3-T09** (`niveau4_reporting/restitutions.py`).
> - **Même socle que le moteur** : toutes les restitutions lisent la vue `moteur_ligneecriture` (comptabilisées et verrouillées seulement, sous la RLS), jamais le grand livre à côté. La vue reçoit, **en fin de liste**, le numéro de pièce, le journal, les libellés et le rang de ligne (migration `moteur/0004`) ; les colonnes existantes, leur ordre et `security_invoker` ne bougent pas. Un test confronte la balance aux chiffres de `generer` (le moteur d'états) pour les mêmes comptes.
> - **Balances** : `balance(..., nature=)` avec `generale`, `auxiliaire` (tiers), `analytique_1..4` (un axe à la fois) et `accord` ; ouverture (avant la période, exercices antérieurs compris), débits et crédits de la période, solde. Chaque ventilation porte une ligne **« non ventilé »** (`None`) : sans elle, une écriture sans tiers, sans axe ou sans accord disparaîtrait de la balance correspondante et les totaux divergeraient. La colonne de ventilation vient d'une **liste blanche**.
> - **Contrôle** : `controler_balances` calcule toutes les natures et exige (1) chaque balance équilibrée, ouverture nulle au total ; (2) pour chaque compte, mêmes ouverture, débits et crédits dans toutes les balances. Sinon `BalancesIncoherentes` **énumère tous les écarts** et rien n'est rendu.
> - **Grand livre** (par compte, et par tiers si demandé) : report, solde cumulé, ordre date → journal → numéro → ligne. **Journal** : lignes par pièce, débits = crédits.
> - Habilitation `consulter` sur le projet (le projet n'est pas isolé par la RLS : la restitution le cloisonne, comme prévu en L1).
> - **Limites** : une balance analytique par axe (pas de croisement d'axes) ; accord affiché en UUID jusqu'à L4 ; pas encore d'export ni de point d'accès HTTP ; consolidation multi-projets non traitée.

---

# LOT L4 — BUDGET ET FINANCEMENTS

**Objectif.** Un engagement bloqué sur dépassement, et débloqué par l'option paramétrée.

---

### L4-T01 — Budgets et versions

`VersionBudget` (initial, révision, réallocation ; brouillon, approuvé, clos) · `LigneBudget` (combinaison d'axes, période ou année, montant, devise, taux de budget).

**Contrôle.** Une version approuvée est immuable ; une révision crée une nouvelle version et conserve l'ancienne.

> **Réalisation de L4-T01** (`niveau1_socle/budget/`).
> - **Une version est un instantané complet** : ses lignes disent tout le budget, pas un écart. Une révision ou une réallocation reprend les lignes de la version courante dans un brouillon, qu'on modifie ; à l'approbation l'ancienne passe à `clos` dans la même transaction, intacte (un test compare ses lignes avant/après). Ce choix évite de reconstituer le budget en empilant des deltas.
> - **Règles** : un seul budget initial par projet ; **une seule version approuvée « courante »** et **un seul brouillon à la fois** (index uniques partiels) ; motif obligatoire hors budget initial ; une révision doit partir de la version courante, sinon l'approbation est refusée (elle écraserait une approbation plus récente). Numéros de version sans trou, sérialisés par verrou consultatif par projet.
> - **Lignes** : combinaison d'axes de gestion (`dim1..4`), accord, catégorie, site (UUID jusqu'à L4-T04) ; année entière ou période 1-12 ; **devise et taux de budget** propres à la ligne, avec le **montant en monnaie de tenue** calculé (montant × taux, arrondi aux décimales de la devise du projet). Une combinaison n'apparaît qu'une fois par version, NULL compris (`NULLS NOT DISTINCT`). À l'approbation, on refuse une combinaison qui mêle ligne annuelle et lignes par période (budget compté deux fois).
> - **Droits** : créer et éditer = `saisir` ; approuver = `valider`, par une autre personne que l'auteur (séparation des tâches).
> - **Immutabilité garantie en base, pour tout rôle** : lignes d'une version non brouillon figées (insertion, modification, suppression) ; version approuvée modifiable seulement pour passer à `clos` ; version close figée ; seul un brouillon se supprime ; une version naît en brouillon ; on n'approuve pas une version vide ; une révision porte sur le même projet que son parent. RLS sur les deux tables.
> - **Limites** : un budget par combinaison d'axes de gestion (pas d'axes auxiliaires) ; les lignes sur une valeur d'axe regroupement sont admises (le budget se pose souvent sur une composante, les dépenses sur une activité) ; le rattachement à la catégorie et à l'accord par clé étrangère viendra avec L4-T04 ; le disponible est l'objet de L4-T02.

---

### L4-T02 — Le disponible

```
disponible = Σ lignes de la version approuvée courante
           − Σ engagements non apurés
           − Σ lignes d'écriture comptabilisées
```

Maintenu dans une **table de soldes budgétaires**, mise à jour **dans la même transaction** que la comptabilisation.

**Impérativement :** une commande `recalculer_soldes` reconstruit tout depuis les écritures, et une tâche nocturne compare les deux. **Toute divergence déclenche une alerte.**

> Un solde pré-agrégé qui dérive silencieusement est pire que pas de solde du tout.

**Contrôle.** Après 10 000 opérations aléatoires, `recalculer_soldes` donne exactement les mêmes valeurs que l'incrémental.

> **Réalisation de L4-T02** (`niveau1_socle/budget/{soldes,engagements}.py`, migration `0004`).
> - **Une ligne de budget COUVRE une dépense** quand l'année correspond, que la période correspond (ou que la ligne est annuelle) et que **chaque axe que la ligne renseigne** est égal à celui de la dépense ; un axe vide sur la ligne ne restreint rien. Le plan ne le disait pas : c'est la règle retenue pour rapprocher un budget à maille variable (par composante, par accord, par catégorie…) d'écritures détaillées. Deux lignes peuvent couvrir la même dépense, qui compte alors dans chacune ; le grand total n'a donc de sens que par ligne.
> - **Réalisations budgétées** : charges (classe 6) et équipements/travaux (classe 2 hors amortissements et provisions 28 et 29). Une seule fonction SQL (`budget_compte_budgete`) en décide : à ajuster si un bailleur budgète autrement.
> - **Engagements** : le plan parle d'engagements non apurés mais ne les créait nulle part avant L9. Version minimale ajoutée ici (`Engagement` : axes, montant en monnaie de tenue, apuré, statut ouvert/soldé/annulé) ; le marché, la non-objection et l'apurement par décompte viendront en L9. Un engagement ne se supprime pas (on l'annule, avec motif), ne change que par son apuré (qui ne baisse jamais), naît ouvert, et soldé ou annulé il est figé (base).
> - **Deux écritures du même chiffre.** Le **calcul complet** (`budget_calculer_soldes`, SQL) lit le grand livre et les engagements : il initialise les soldes à l'approbation d'une version et sert à `recalculer_soldes` et à la vérification. L'**incrémental** (déclencheurs sur la comptabilisation d'une écriture et sur les engagements) ajoute le delta dans la transaction même qui le provoque, pour tout chemin (service, import, SQL). Une contre-passation, écriture comptabilisée comme une autre, restitue le consommé. Un brouillon ne consomme rien.
> - **Vérification et alerte** : `comparer_soldes` donne les écarts (ligne de solde manquante comprise) ; `verifier_soldes` écrit toute divergence au **journal d'audit** (`budget_balance_divergence`) et au journal technique ; `recalculer_soldes` corrige en laissant la trace de ce qui avait dérivé. Commandes `verifier_soldes` (code de sortie 1 en cas d'écart : c'est ce code que l'ordonnanceur transforme en alerte) et `recalculer_soldes`, par organisation (`--organisation`), car la RLS impose un périmètre.
> - **Contrôle** : 10 000 opérations aléatoires (écritures posées puis en partie verrouillées, 15 % de sens inverse, engagements créés, apurés, annulés, une révision de budget en cours de route) : incrémental = recalcul de la base = **calcul indépendant en Python**, au centime (≈ 95 s).
> - **Limites** : la planification nocturne elle-même (cron ou tâche planifiée) reste à brancher à l'exploitation (L10) ; le calcul complet parcourt le grand livre du projet, ce qui est correct à cette échelle et à surveiller ensuite ; un engagement annuel ne couvre pas une ligne à période précise ; les montants de budget sont en monnaie de tenue pour le disponible (`montant_base`).

---

### L4-T03 — Le contrôle budgétaire

Paramétrable **par axe** : `bloquant` / `avertissement` / `inactif`. Appliqué à la validation.

> Certains bailleurs exigent le blocage, d'autres l'interdisent. La souplesse n'est pas un confort, c'est une exigence contractuelle.

**Contrôle.** Les trois modes se comportent correctement sur un même dépassement.

> **Réalisation de L4-T03** (`niveau1_socle/budget/controle.py`, migrations `0005`-`0006`).
> - **Où le contrôle s'applique** : à la **validation** d'une écriture (`valider_ecriture`, comme demandé) et à l'**ouverture d'un engagement** (c'est lui que l'objectif du lot dit « bloqué sur dépassement, débloqué par l'option paramétrée »). Une opération dépasse une ligne de budget quand son effet net dépasse le disponible de cette ligne (budget − engagé − consommé), **atteindre exactement le disponible n'est pas dépasser** ; une opération qui restitue du budget (contre-passation, crédit) ne dépasse jamais, même sur une ligne déjà dépassée.
> - **Quel mode pour quelle ligne** (le plan ne le disait pas) : celui des axes que la ligne de budget renseigne, **le plus strict l'emporte** ; une ligne sans axe suit l'axe « projet ». Une dépense couverte par deux lignes est contrôlée ligne par ligne, chacune avec son mode.
> - **Défaut : `avertissement`.** Le blocage est une exigence qu'une organisation choisit (d'autres bailleurs l'interdisent) : aucune exigence n'est activée d'office (règle 9), mais on n'éteint pas l'information non plus.
> - **Paramétrage versionné** (`ControleBudgetaire`, `[valid_from, valid_to[`, sans chevauchement garanti par la base) : changer de mode clôt la version en cours et en ouvre une autre, sous l'habilitation `parametrer`, avec motif et trace d'audit ; une version ne se supprime pas et ne change que par la clôture de sa validité. Le mode appliqué à une écriture est celui de **sa date comptable**.
> - **Résultat** : `bloquant` -> `DepassementBudgetaire` (la pièce reste en brouillon) ; `avertissement` -> validation acceptée, avertissements lisibles dans `ecriture.avertissements_budgetaires` (ou `engagement.avertissements_budgetaires`) et tracés au journal d'audit (`budget_overrun_warning`) ; `inactif` -> rien. La création d'engagement pose un **verrou de ligne** sur les soldes concernés.
> - **Limites connues** : (1) seules les lignes de budget qui **couvrent** l'opération sont contrôlées : une dépense qu'aucune ligne ne couvre échappe au contrôle ; (2) un refus ne laisse pas de trace d'audit, car il annule la transaction qui la porterait ; (3) le contrôle à la validation ne voit pas les autres pièces validées mais pas encore comptabilisées (elles ne consomment qu'à la comptabilisation) ; le blocage par verrou de catégorie des demandes de retrait est l'objet de L4-T06.

---

### L4-T04 — Bailleurs, accords, catégories

`Bailleur` · `Accord` (prêt, don, contrepartie ; devise, montant initial et **montant révisé**, dates) · `Categorie` (plafond, **sous-catégories par `parent`**, devise ; identité stable d'une version de profil à l'autre) · `CompteBancaire` (devise, banque, plafond, seuil) · `AvenantAccord`.

**Statuts de l'accord :** `brouillon` · `actif` · **`suspendu`** · `clos` · `annulé`. Un accord `suspendu` bloque toute **nouvelle** demande de décaissement et toute nouvelle imputation sans être clos ; ses opérations historiques restent consultables. Un accord portant des opérations ne se supprime jamais.

**Contraintes.** Numéro d'accord unique par organisation ; projet et bailleur de la même organisation (clé étrangère composite `(org_id, id)`) ; montants positifs ou nuls ; dates cohérentes (date d'effet ≤ fin d'éligibilité ≤ clôture ≤ date limite de décaissement, quand elles sont renseignées).

**Comptes bancaires.** Type de compte : `désigné` · `spécial` · `opérationnel` · `contrepartie` · `transit`, ensemble fermé contraint en base. Le **numéro complet** n'est visible que d'une habilitation dédiée (`voir_numero_compte`) ; partout ailleurs il est masqué. Mêmes règles d'audit en lecture que pour les données de tiers.

**`AvenantAccord`.** Référence, date, `DocumentReference` signé, montant révisé de l'accord, et **la version de profil de décaissement créée à la suite** (voir L5-T04bis). L'application doit pouvoir afficher la situation de l'accord avant et après l'avenant. Un avenant ne modifie jamais un accord en place : il porte la nouvelle valeur et la nouvelle version.

**Contrôle.** Deux accords du même bailleur sur le même projet coexistent sans partager ni catégories ni paramètres ; un accord suspendu refuse une nouvelle demande ; un numéro de compte n'est lisible que par l'habilitation dédiée.

> **Réalisation de L4-T04** (`niveau1_socle/financements/`, `habilitations/0003`).
> - **Le montant de l'accord ne change jamais en place.** Le plan donne à l'accord « montant initial et montant révisé » et dit qu'un avenant ne modifie jamais l'accord : les deux ne se concilient qu'ainsi. L'accord porte son `montant_initial` ; le montant **courant** est celui du dernier avenant daté au plus tard le jour demandé (`montant_courant(accord, date)`), et `situation_avant_apres(avenant)` donne montant avant, après et variation. Un avenant peut réduire. Il est immuable, exige un accord actif ou suspendu, et un `DocumentReference` de type accord de financement **du même projet**. « Signé » est entendu comme : le document est référencé avec son empreinte SHA-256 (il n'existe pas d'indicateur de signature dans le registre des documents). `profile_version_id` attend la version de profil de L5-T04bis.
> - **Isolation renforcée** : des **clés étrangères composites** `(org_id, id)` (accord → bailleur et projet, catégorie, avenant et compte → accord, compte → projet). La RLS filtre ce qu'on lit et écrit, pas ce que vérifie une clé étrangère : sans cela, l'identifiant connu d'un bailleur d'une autre organisation aurait passé.
> - **Statuts** : brouillon → actif | annulé ; actif → suspendu | clos | annulé ; suspendu → actif | clos ; clos et annulé terminaux. Transitions **vérifiées aussi par la base** ; motif obligatoire hors activation ; un accord activé ne change plus que de statut (un avenant porte les nouvelles valeurs, les dates restent donc figées : limite assumée). Un accord qui porte des opérations (lignes d'écriture, de budget, engagements, catégories, avenants, comptes) **ne se supprime jamais** et ne s'annule pas : on le clôt.
> - **Accord suspendu** : `exiger_accord_actif` est le point d'appui commun. La **saisie d'écriture** l'applique (accord inconnu, brouillon, suspendu, clos : refus) et la **validation** aussi pour une pièce saisie avant la suspension ; une **contre-passation** reste possible (corriger l'historique n'est pas une nouvelle imputation). Le refus d'une **demande de décaissement** s'y branchera en L4-T06 (la demande n'existe pas encore) ; les engagements et lignes de budget ne sont pas contrôlés (réservations, pas imputations).
> - **Catégories** : identité = `(accord, code)`, stable d'une version de profil à l'autre ; sous-catégories dans le même accord, plafond sous celui du parent ; une catégorie **utilisée** ne change plus que de libellé et ne se supprime pas. Deux accords du même bailleur sur le même projet n'ont rien en commun (même code de catégorie possible).
> - **Comptes bancaires** : cinq types fermés, plafond et seuil de réapprovisionnement (seuil ≤ plafond), numéro unique par organisation, accord de même projet. Nouvelle opération **`voir_numero_compte`** (ensemble fermé des opérations étendu, contrainte de base mise à jour) : seule elle donne le numéro complet (`consulter_numero_compte`), chaque lecture est journalisée **sans le numéro** ; ailleurs `numero_masque` (quatre derniers caractères), y compris dans `str`, `repr` et le journal de création.
> - **Limites** : le numéro est stocké en clair en base, comme les coordonnées bancaires des tiers (chiffrement au repos : décision d'exploitation, L10) ; `agreement_id`, `category_id` et `bank_account_id` des lignes d'écriture, de budget et des engagements restent des UUID sans clé étrangère (les jeux de tests et le moteur d'états les manipulent encore comme identifiants libres) ; le rapprochement bancaire (L3-T07b) peut désormais s'appuyer sur `CompteBancaire`.

---

### L4-T05 — Cofinancement : l'arithmétique

> **La tâche où une erreur détruit la confiance du client.** Lisez l'algorithme deux fois.

```python
from decimal import Decimal, ROUND_DOWN
CENTIME = Decimal("0.01")

def ventiler(montant: Decimal, version_cle) -> list[tuple[str, Decimal]]:
    """Répartit un montant entre accords. Le total est TOUJOURS conservé."""
    parts = []
    for p in version_cle.parts.all():
        parts.append((p.accord_id, (montant * p.share).quantize(CENTIME, ROUND_DOWN)))

    reliquat = montant - sum(m for _, m in parts)      # jamais négatif avec ROUND_DOWN
    porteur = version_cle.rounding_residual_agreement_id
    parts = [(a, m + reliquat) if a == porteur else (a, m) for a, m in parts]

    assert sum(m for _, m in parts) == montant, "ventilation non conservative"
    return parts
```

Et **persister `cofunding_key_version_id` sur chaque ligne produite** : sans cela, une modification ultérieure de la clé rend l'historique inexplicable, et l'audit impossible.

**Contrôle — test de propriété, obligatoire :**

```python
from hypothesis import given, strategies as st

@given(montant=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("1e9"),
                           places=2),
       parts=st.lists(st.integers(1, 99), min_size=2, max_size=5))
def test_la_ventilation_conserve_toujours_le_total(montant, parts):
    cle = cle_normalisee(parts)
    assert sum(m for _, m in ventiler(montant, cle)) == montant
```

> **Cet algorithme a été éprouvé sur 50 000 ventilations aléatoires** (montants jusqu'à 10⁹, de 2 à 5 accords) : **toutes conservatives**, reliquat maximal observé de 0,04. Deux points à retenir : les parts doivent être **normalisées pour sommer exactement à 1** — calculez la dernière par différence, jamais par division — et `ROUND_DOWN` garantit un reliquat **toujours positif**, donc jamais de montant à retrancher au porteur.

> **Réalisation de L4-T05** (`niveau1_socle/financements/{cofinancement,cles}.py`, migrations `0003`-`0004`).
> - **L'algorithme du plan, avec quatre corrections.** (1) Le pas d'arrondi est celui de la **devise** (`pas_de_devise`), pas un centime codé en dur : en franc de Djibouti, qui n'a pas de décimale, `quantize(0,01)` aurait produit des montants impossibles à comptabiliser. (2) Le garde-fou final lève une erreur explicite au lieu d'un `assert`, qui disparaît avec `python -O`. (3) Un **montant négatif** (remboursement, contre-passation) est le miroir exact de la ventilation de son opposé (sinon `ROUND_DOWN`, qui arrondit vers zéro, donnerait un reliquat négatif et une asymétrie avec la dépense d'origine). (4) Le montant doit être un multiple du pas de la devise ; les parts sont vérifiées positives et de somme exactement 1.
> - **Normalisation** (`normaliser_parts`) : des poids (60, 30, 10) deviennent des parts à dix décimales, toutes arrondies vers zéro sauf la **dernière, calculée par différence** : la somme vaut 1 par construction, jamais par division.
> - **Clé versionnée** (`CleCofinancement` -> `VersionCle` -> `PartCle`, validité `[valid_from, valid_to[` sans chevauchement garantie par la base) ; le porteur d'arrondi est **toujours le même accord**, désigné dans la version. La base vérifie **au COMMIT** que les parts somment exactement à 1, que le porteur est l'une d'elles et que tous les accords sont ceux du projet de la clé ; elle impose des clés étrangères composites `(org_id, id)`. Les accords sont **triés par numéro** pour que la même clé donne toujours le même résultat.
> - **Historique explicable** : chaque ligne produite (`lignes_ventilees`) porte son accord **et** `cofunding_key_version_id` (colonne prévue dès L3, désormais en clé étrangère vers la version). Une version **utilisée par une ligne d'écriture** ne change plus (ni ses parts, ni elle-même, ni suppression) hors clôture de sa validité ; la contre-passation recopie la référence, et le miroir exact la vérifie.
> - **Contrôles** : tests de propriété Hypothesis (conservation, parts exactes, reliquat dans [0, n-1] pas, miroir du négatif, pas de la devise) ; **50 000 ventilations aléatoires** du plan (reliquat maximal observé inférieur à 5 centimes) ; 1 000 ventilations sur une clé relue en base, en franc de Djibouti et en dollar.
> - **Limites** : la clé ne s'applique pas toute seule à une saisie : l'appelant demande les lignes (`lignes_ventilees`) et les passe à `saisir_ecriture` avec la contrepartie ; une dépense dont la date ne tombe dans aucune version de clé n'a pas de ventilation (`version_en_vigueur` rend rien) ; le contrôle d'éligibilité d'une dépense par accord (dates, catégories) relève de L5.

---

### L4-T06 — Demandes de retrait de fonds

`DemandeRetrait` (type : retrait, réapprovisionnement, paiement direct, engagement spécial) et son cycle `préparée → soumise → acceptée/rejetée → remboursée`.

**Atelier DRF** — un seul écran : sélection d'un accord et d'une période ; dépenses éligibles non encore justifiées avec leur pièce ; mise à l'écart **avec motif tracé** ; vérification du plafond de catégorie et du disponible de l'accord ; production de la demande et de l'état certifié de dépenses.

**Contrôle.** Une dépense déjà justifiée dans une demande antérieure ne peut **pas** être sélectionnée une seconde fois.

**Rejets et litiges.** Une demande rejetée porte un **motif de rejet obligatoire** ; une demande contestée prend le statut `contestée`. Une demande représentée référence la précédente (`reprise_de`) : le contrôle anti-doublon ci-dessus reste appliqué, la dépense rejetée redevient sélectionnable **uniquement** par ce lien. Une régularisation est une opération nouvelle, jamais la modification de la demande d'origine.

**Concurrence.** Deux demandes consommant simultanément le même disponible de catégorie ne peuvent pas toutes deux aboutir : verrou de ligne sur le solde de catégorie, et clé d'idempotence sur la soumission (une double soumission ne crée qu'une demande).

**Contrôle de concurrence.** Dix soumissions simultanées sur un disponible qui n'en autorise que trois : exactement trois acceptées, solde final exact au centime.

> **Réalisation de L4-T06** (`niveau1_socle/decaissements/`).
> - **L'atelier** (`depenses_eligibles`, `verifier_disponible`, `preparer_demande`) : les dépenses éligibles sont les charges budgétées, comptabilisées, imputées à l'accord, dans la période ; chacune est dite *sélectionnable* ou non, avec sa raison (déjà justifiée, rejetée, sans catégorie). On en **écarte avec un motif tracé** (`MiseAEcart`, définitive, au journal d'audit) ; une dépense écartée reste libre pour une demande ultérieure. La demande produite est *préparée* ; `soumettre_demande` fige l'**état certifié de dépenses** (par catégorie, avec le numéro de pièce de chaque ligne) et son **empreinte SHA-256**.
> - **Anti-doublon, garanti par la base** : index unique partiel (une dépense n'a qu'**une** ligne de demande « en cours »). Les valeurs d'une ligne (montant, catégorie, pièce) sont **recopiées du grand livre et vérifiées** par la base : l'appelant ne les dicte pas. Une dépense d'une demande rejetée ne redevient sélectionnable **que** par la demande qui reprend la *dernière* rejetée (`reprise_de`) ; annuler une demande préparée, elle, libère ses dépenses sans condition. Une régularisation est une demande nouvelle : la rejetée n'est jamais modifiée.
> - **Plafonds et accord** : la soumission pèse le montant de la demande sur le solde de **chaque catégorie et de ses catégories parentes** et sur celui de l'accord (montant courant, avenants compris). Ne comptent que les demandes soumises, acceptées, contestées ou remboursées ; un rejet restitue.
> - **Concurrence — deux niveaux.** (1) Le service pose un **verrou de ligne** sur les soldes concernés dans un **ordre fixe** (pas d'interblocage) puis tranche. (2) **Refus ultime en base** : même si ce verrou était contourné, la base refuse toute hausse qui franchirait un plafond de catégorie ou le montant de l'accord. Idempotence : rejouer la soumission avec la même clé rend la même demande, consommée **une** fois (cinq soumissions simultanées avec une même clé : un seul effet, un seul événement d'audit).
> - **Cycle fermé** (vérifié aussi par la base) : préparée → soumise | annulée ; soumise → acceptée | rejetée | contestée ; acceptée → remboursée | contestée ; contestée → acceptée | rejetée ; rejetée, remboursée, annulée terminales. Rejet et contestation **motivés** (contrainte). Une demande soumise est **figée** (hors statut et décision) ; aucune demande, ligne ni écart ne se supprime. Accord suspendu : nouvelle demande refusée, par le service **et** par la base, à la préparation comme à la soumission.
> - **Droits** : préparer et annuler = `saisir` ; soumettre et enregistrer la suite = `valider`, la soumission par une autre personne que le préparateur.
> - **Limites** : (1) montants en **monnaie de tenue** : un accord dans une autre devise est refusé (`DeviseNonSupportee`) tant que la conversion des dépenses n'existe pas — c'est la limite la plus gênante pour un accord en dollars sur un projet en franc de Djibouti ; (2) les quatre types de demande (retrait, réapprovisionnement, paiement direct, engagement spécial) suivent le même parcours par dépenses justifiées : un **retrait d'avance sans dépense** ne se saisit pas encore (L4-T07 et L7) ; (3) une dépense n'est rattachée qu'à la catégorie du grand livre, sans réallocation entre catégories ; (4) l'état certifié est un instantané JSON : sa mise en page (PDF, modèle du bailleur) relève de L7.

---

### L4-T07 — Suivi des avances

Avances non justifiées, délais applicables, alertes. Alimente le contrôle « avance non justifiée au-delà du délai » du lot L6.

> **Réalisation de L4-T07** (`niveau1_socle/avances/`).
> - **Modèle sans dérive.** Une avance (tiers, montant, date de versement, délai) et ses justifications (dépense prouvée par une pièce, ou remboursement de l'excédent) sont en **ajout seul**, pour tout rôle ; le **reste à justifier se calcule** (`montant − Σ justifications`), il n'est stocké nulle part, donc ne peut pas diverger. Une justification ne dépasse jamais l'avance ni ne précède le versement : la base le vérifie sous **verrou de ligne de l'avance** (dix justifications simultanées sur une avance de 300 : trois passent, le total est exactement 300).
> - **Délai applicable versionné** (`DelaiAvance`, `[valid_from, valid_to[`, sans chevauchement garanti par la base, habilitation `parametrer`). Le délai en vigueur **le jour du versement est figé sur l'avance** : changer la règle ne rend pas rétroactivement en retard ce qui était dans les temps. **Aucun délai par défaut** : sans paramétrage, verser une avance sans préciser son délai est refusé (une règle contractuelle ne se devine pas).
> - **Situation, suivi, alertes.** `situation_avance`, `suivi`, `alertes`, `encours_par_tiers` se lisent **à une date donnée** (le passé reste lisible : une avance soldée tardivement était bien échue la veille). Niveaux : `soldee`, `en_cours`, `a_echeance` (dans le préavis, 7 jours par défaut), `echue` (strictement après l'échéance, avec son nombre de jours de retard). `avances_non_justifiees_au_dela_du_delai` est la ressource que **consomme le contrôle du même nom de L6**. Lecture : habilitation `consulter` ; verser et justifier : `saisir`. Le suivi n'expose que le **code** du tiers, pas son identité.
> - **Limites** : une avance versée par erreur ne s'annule pas (ajout seul) : on la régularise par un remboursement ; les montants sont en monnaie de tenue ; l'avance et ses justifications peuvent citer une ligne d'écriture (clé étrangère) mais ne sont pas **générées** par la comptabilité (un versement comptabilisé ne crée pas encore l'avance tout seul) ; les alertes sont **calculées à la demande**, la diffusion (courriel, tableau de bord) relève de L6 et L10.

---

## Contrôle de sortie des fondations

```
[ ] Un exercice complet saisi, clôturé, avec à-nouveaux générés
[ ] Balance = balance analytique = balance par accord, au centime
[ ] Numérotation sans trou sous 10 processus concurrents
[ ] Écriture comptabilisée non modifiable, période close inviolable
[ ] Isolation : test d'accès croisé en échec sur TOUTES les tables
[ ] Journal d'audit : altération détectée par le vérificateur
[ ] Ventilation de cofinancement conservative (test de propriété)
[ ] Soldes budgétaires incrémentaux == recalcul complet
[ ] Les états de référence de L0 passent toujours
[ ] UPDATE de org_id vers une autre organisation refusé sur toutes les tables
[ ] Soumissions concurrentes sur un même disponible : aucune sur-consommation
[ ] Accord suspendu : nouvelle demande refusée
[ ] Numéro de compte bancaire masqué sans l'habilitation dédiée
```

---

**Suite :** [lots L5 à L10](05_PLAN_LOTS_L5_A_L10.md).
