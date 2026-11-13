from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

# Une version approuvée est IMMUABLE, pour tout rôle :
# - ses lignes ne s'insèrent, ne se modifient et ne se suppriment plus ;
# - la version ne change plus, sauf pour passer à « clos » quand une révision la remplace ;
# - seul un brouillon se supprime ; une version naît toujours en brouillon ;
# - on n'approuve pas une version sans ligne ; une révision porte sur le même projet.
GARDE = """
CREATE OR REPLACE FUNCTION budget_version_garde() RETURNS trigger AS $$
DECLARE
  projet_parent uuid;
  nb integer;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'brouillon' THEN
      RAISE EXCEPTION 'Une version de budget % ne se supprime pas', OLD.status
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN OLD;
  END IF;

  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'brouillon' THEN
      RAISE EXCEPTION 'Une version de budget naît en brouillon'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.parent_id IS NOT NULL THEN
      SELECT project_id INTO projet_parent FROM budget_versionbudget WHERE id = NEW.parent_id;
      IF projet_parent IS DISTINCT FROM NEW.project_id THEN
        RAISE EXCEPTION 'Une révision porte sur le même projet que la version révisée'
          USING ERRCODE = 'integrity_constraint_violation';
      END IF;
    END IF;
    RETURN NEW;
  END IF;

  -- UPDATE
  IF OLD.status = 'clos' THEN
    RAISE EXCEPTION 'Une version de budget close est figée'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.status = 'approuve' THEN
    IF NEW.status <> 'clos' OR NEW.closed_at IS NULL
       OR (to_jsonb(NEW) - 'status' - 'closed_at' - 'updated_at' - 'updated_by')
          <> (to_jsonb(OLD) - 'status' - 'closed_at' - 'updated_at' - 'updated_by') THEN
      RAISE EXCEPTION 'Une version de budget approuvée est immuable : on la remplace par une révision'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;
  -- brouillon
  IF NEW.project_id <> OLD.project_id OR NEW.numero <> OLD.numero OR NEW.type <> OLD.type
     OR NEW.parent_id IS DISTINCT FROM OLD.parent_id THEN
    RAISE EXCEPTION 'Le projet, le rang, le type et la version révisée ne changent pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.status = 'clos' THEN
    RAISE EXCEPTION 'Un brouillon ne se clôt pas : on le supprime ou on l''approuve'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.status = 'approuve' THEN
    SELECT count(*) INTO nb FROM budget_lignebudget WHERE version_id = NEW.id;
    IF nb = 0 THEN
      RAISE EXCEPTION 'On n''approuve pas une version de budget sans ligne'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER budget_version_garde
  BEFORE INSERT OR UPDATE OR DELETE ON budget_versionbudget
  FOR EACH ROW EXECUTE FUNCTION budget_version_garde();

CREATE OR REPLACE FUNCTION budget_ligne_garde() RETURNS trigger AS $$
DECLARE
  statut text;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    SELECT status INTO statut FROM budget_versionbudget WHERE id = OLD.version_id;
    IF statut IS DISTINCT FROM 'brouillon' THEN
      RAISE EXCEPTION 'Les lignes d''une version de budget % sont figées', statut
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    SELECT status INTO statut FROM budget_versionbudget WHERE id = NEW.version_id;
    IF statut IS DISTINCT FROM 'brouillon' THEN
      RAISE EXCEPTION 'Les lignes d''une version de budget % sont figées', statut
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER budget_ligne_garde
  BEFORE INSERT OR UPDATE OR DELETE ON budget_lignebudget
  FOR EACH ROW EXECUTE FUNCTION budget_ligne_garde();
"""

GARDE_INVERSE = """
DROP TRIGGER IF EXISTS budget_ligne_garde ON budget_lignebudget;
DROP TRIGGER IF EXISTS budget_version_garde ON budget_versionbudget;
DROP FUNCTION IF EXISTS budget_ligne_garde();
DROP FUNCTION IF EXISTS budget_version_garde();
"""


class Migration(migrations.Migration):
    dependencies = [("budget", "0001_budgets_versions")]

    operations = [
        migrations.RunSQL(
            activer_rls("budget_versionbudget"), reverse_sql=desactiver_rls("budget_versionbudget")
        ),
        migrations.RunSQL(
            activer_rls("budget_lignebudget"), reverse_sql=desactiver_rls("budget_lignebudget")
        ),
        migrations.RunSQL(GARDE, reverse_sql=GARDE_INVERSE),
    ]
