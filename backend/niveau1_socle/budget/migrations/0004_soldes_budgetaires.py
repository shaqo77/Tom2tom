from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

# Le disponible budgétaire est maintenu PAR LA BASE, pour que rien ne le contourne :
#
#   disponible d'une ligne = montant_base − engagé non apuré − consommé comptabilisé
#
# Une ligne de budget COUVRE une dépense quand l'année correspond, que la période correspond (ou que
# la ligne est annuelle) et que chaque axe que la ligne renseigne est égal à celui de la dépense. Un
# axe laissé vide sur la ligne ne restreint rien. Deux lignes peuvent couvrir la même dépense (par
# exemple une ligne par composante et une ligne par catégorie) : elle compte dans chacune.
#
# Trois chemins, deux écritures du même chiffre :
# - le CALCUL COMPLET (`budget_calculer_soldes`) lit le grand livre et les engagements ; il sert à
#   l'initialisation à l'approbation, à `recalculer_soldes` et à la vérification nocturne ;
# - l'INCRÉMENTAL (déclencheurs sur la comptabilisation et sur les engagements) ajoute le delta dans
#   la transaction même qui le provoque.
# Seule la comparaison des deux dit si le solde a dérivé.
#
# Comptes budgétés : classe 6, et classe 2 hors amortissements et provisions (28, 29) : les
# catégories d'un budget bailleur comprennent équipements et travaux. Une seule fonction décide.
FONCTIONS = """
CREATE OR REPLACE FUNCTION budget_compte_budgete(code text, classe integer) RETURNS boolean AS $$
  SELECT classe = 6 OR (classe = 2 AND code NOT LIKE '28%' AND code NOT LIKE '29%');
$$ LANGUAGE sql IMMUTABLE;

CREATE OR REPLACE FUNCTION budget_ligne_couvre(
  b budget_lignebudget, p_annee integer, p_periode integer,
  p_dim1 uuid, p_dim2 uuid, p_dim3 uuid, p_dim4 uuid,
  p_accord uuid, p_categorie uuid, p_site uuid
) RETURNS boolean AS $$
  SELECT b.annee = p_annee
     AND (b.periode IS NULL OR b.periode = p_periode)
     AND (b.dim1_id IS NULL OR b.dim1_id = p_dim1)
     AND (b.dim2_id IS NULL OR b.dim2_id = p_dim2)
     AND (b.dim3_id IS NULL OR b.dim3_id = p_dim3)
     AND (b.dim4_id IS NULL OR b.dim4_id = p_dim4)
     AND (b.agreement_id IS NULL OR b.agreement_id = p_accord)
     AND (b.category_id IS NULL OR b.category_id = p_categorie)
     AND (b.site_id IS NULL OR b.site_id = p_site);
$$ LANGUAGE sql IMMUTABLE;

CREATE OR REPLACE FUNCTION budget_calculer_soldes(p_projet uuid)
RETURNS TABLE (ligne_id uuid, consomme numeric, engage numeric) AS $$
  SELECT b.id,
         COALESCE((
           SELECT SUM(l.debit - l.credit)
             FROM comptabilite_ligneecriture l
             JOIN comptabilite_ecriture e ON e.id = l.entry_id AND e.status IN ('posted', 'locked')
             JOIN exercices_exercice x ON x.id = e.exercice_id
             JOIN exercices_periode p ON p.id = e.periode_id
             JOIN referentiels_compte c ON c.id = l.account_id
            WHERE e.project_id = v.project_id
              AND budget_compte_budgete(c.code, c.classe)
              AND budget_ligne_couvre(b, x.annee, p.numero, l.dim1_id, l.dim2_id, l.dim3_id,
                                      l.dim4_id, l.agreement_id, l.category_id, l.site_id)
         ), 0),
         COALESCE((
           SELECT SUM(g.montant - g.apure)
             FROM budget_engagement g
            WHERE g.project_id = v.project_id AND g.status = 'ouvert'
              AND budget_ligne_couvre(b, g.annee, g.periode, g.dim1_id, g.dim2_id, g.dim3_id,
                                      g.dim4_id, g.agreement_id, g.category_id, g.site_id)
         ), 0)
    FROM budget_lignebudget b
    JOIN budget_versionbudget v ON v.id = b.version_id AND v.status = 'approuve'
   WHERE p_projet IS NULL OR v.project_id = p_projet;
$$ LANGUAGE sql STABLE;

-- À l'approbation : une ligne de solde par ligne de la nouvelle version courante.
CREATE OR REPLACE FUNCTION budget_initialiser_soldes() RETURNS trigger AS $$
BEGIN
  IF NEW.status = 'approuve' AND OLD.status = 'brouillon' THEN
    INSERT INTO budget_soldebudgetaire
           (id, created_at, updated_at, org_id, project_id, version_id, ligne_id, consomme, engage)
    SELECT gen_random_uuid(), now(), now(), b.org_id, NEW.project_id, NEW.id, c.ligne_id,
           c.consomme, c.engage
      FROM budget_calculer_soldes(NEW.project_id) c
      JOIN budget_lignebudget b ON b.id = c.ligne_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER budget_initialiser_soldes
  AFTER UPDATE ON budget_versionbudget
  FOR EACH ROW EXECUTE FUNCTION budget_initialiser_soldes();

-- INCRÉMENTAL, côté grand livre : une écriture qui devient comptabilisée consomme le budget.
-- Une contre-passation est une écriture comptabilisée comme une autre : elle restitue.
CREATE OR REPLACE FUNCTION budget_solde_ecriture() RETURNS trigger AS $$
BEGIN
  IF NEW.status IN ('posted', 'locked') AND OLD.status NOT IN ('posted', 'locked') THEN
    UPDATE budget_soldebudgetaire s
       SET consomme = s.consomme + m.montant, updated_at = now()
      FROM (
        SELECT b.id AS ligne_id, SUM(l.debit - l.credit) AS montant
          FROM comptabilite_ligneecriture l
          JOIN referentiels_compte c ON c.id = l.account_id
          JOIN exercices_exercice ex ON ex.id = NEW.exercice_id
          JOIN exercices_periode pe ON pe.id = NEW.periode_id
          JOIN budget_versionbudget v ON v.project_id = NEW.project_id AND v.status = 'approuve'
          JOIN budget_lignebudget b ON b.version_id = v.id
         WHERE l.entry_id = NEW.id
           AND budget_compte_budgete(c.code, c.classe)
           AND budget_ligne_couvre(b, ex.annee, pe.numero, l.dim1_id, l.dim2_id, l.dim3_id,
                                   l.dim4_id, l.agreement_id, l.category_id, l.site_id)
         GROUP BY b.id
      ) m
     WHERE s.ligne_id = m.ligne_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER budget_solde_ecriture
  AFTER UPDATE OF status ON comptabilite_ecriture
  FOR EACH ROW EXECUTE FUNCTION budget_solde_ecriture();

-- INCRÉMENTAL, côté engagements : le non apuré réserve du budget.
CREATE OR REPLACE FUNCTION budget_solde_engagement() RETURNS trigger AS $$
DECLARE
  nouveau numeric;
  ancien numeric := 0;
BEGIN
  nouveau := CASE WHEN NEW.status = 'ouvert' THEN NEW.montant - NEW.apure ELSE 0 END;
  IF TG_OP = 'UPDATE' THEN
    ancien := CASE WHEN OLD.status = 'ouvert' THEN OLD.montant - OLD.apure ELSE 0 END;
  END IF;
  IF nouveau <> ancien THEN
    UPDATE budget_soldebudgetaire s
       SET engage = s.engage + (nouveau - ancien), updated_at = now()
      FROM budget_lignebudget b
      JOIN budget_versionbudget v ON v.id = b.version_id AND v.status = 'approuve'
     WHERE s.ligne_id = b.id AND v.project_id = NEW.project_id
       AND budget_ligne_couvre(b, NEW.annee, NEW.periode, NEW.dim1_id, NEW.dim2_id, NEW.dim3_id,
                               NEW.dim4_id, NEW.agreement_id, NEW.category_id, NEW.site_id);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER budget_solde_engagement
  AFTER INSERT OR UPDATE ON budget_engagement
  FOR EACH ROW EXECUTE FUNCTION budget_solde_engagement();

-- Un engagement ne se supprime pas ; il naît ouvert ; seuls l'apuré (qui ne baisse jamais) et
-- l'état changent, et un engagement soldé ou annulé est figé.
CREATE OR REPLACE FUNCTION budget_engagement_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un engagement ne se supprime pas : on l''annule'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'ouvert' OR NEW.apure <> 0 THEN
      RAISE EXCEPTION 'Un engagement naît ouvert et sans apurement'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status <> 'ouvert' THEN
    RAISE EXCEPTION 'Un engagement % est figé', OLD.status
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.apure < OLD.apure
     OR (to_jsonb(NEW) - 'apure' - 'status' - 'updated_at' - 'updated_by')
        <> (to_jsonb(OLD) - 'apure' - 'status' - 'updated_at' - 'updated_by') THEN
    RAISE EXCEPTION 'Un engagement ne change que par son apurement ou son annulation'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER budget_engagement_garde
  BEFORE INSERT OR UPDATE OR DELETE ON budget_engagement
  FOR EACH ROW EXECUTE FUNCTION budget_engagement_garde();
"""

FONCTIONS_INVERSE = """
DROP TRIGGER IF EXISTS budget_engagement_garde ON budget_engagement;
DROP TRIGGER IF EXISTS budget_solde_engagement ON budget_engagement;
DROP TRIGGER IF EXISTS budget_solde_ecriture ON comptabilite_ecriture;
DROP TRIGGER IF EXISTS budget_initialiser_soldes ON budget_versionbudget;
DROP FUNCTION IF EXISTS budget_engagement_garde();
DROP FUNCTION IF EXISTS budget_solde_engagement();
DROP FUNCTION IF EXISTS budget_solde_ecriture();
DROP FUNCTION IF EXISTS budget_initialiser_soldes();
DROP FUNCTION IF EXISTS budget_calculer_soldes(uuid);
DROP FUNCTION IF EXISTS budget_ligne_couvre(budget_lignebudget, integer, integer, uuid, uuid, uuid,
                                             uuid, uuid, uuid, uuid);
DROP FUNCTION IF EXISTS budget_compte_budgete(text, integer);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0003_engagements_soldes"),
        ("comptabilite", "0014_anouveau_garde_fous"),
    ]

    operations = [
        migrations.RunSQL(
            activer_rls("budget_engagement"), reverse_sql=desactiver_rls("budget_engagement")
        ),
        migrations.RunSQL(
            activer_rls("budget_soldebudgetaire"),
            reverse_sql=desactiver_rls("budget_soldebudgetaire"),
        ),
        migrations.RunSQL(FONCTIONS, reverse_sql=FONCTIONS_INVERSE),
    ]
