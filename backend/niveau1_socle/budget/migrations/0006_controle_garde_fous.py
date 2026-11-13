from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

# Deux versions du contrôle d'un même axe ne se chevauchent pas (comme les exercices et les schémas).
# Une version ne se supprime pas et ne change que par la clôture de sa validité : les décisions
# prises sous un mode restent explicables.
SQL = """
ALTER TABLE budget_controlebudgetaire ADD CONSTRAINT controlebudget_sans_chevauchement
  EXCLUDE USING gist (org_id WITH =, project_id WITH =, axe WITH =,
                      daterange(valid_from, valid_to, '[)') WITH &&);

CREATE OR REPLACE FUNCTION budget_controle_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une version de contrôle budgétaire ne se supprime pas : créez-en une nouvelle'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.valid_to IS NOT NULL
     OR (to_jsonb(NEW) - 'valid_to' - 'updated_at' - 'updated_by')
        <> (to_jsonb(OLD) - 'valid_to' - 'updated_at' - 'updated_by') THEN
    RAISE EXCEPTION 'Une version de contrôle budgétaire ne change que par la clôture de sa validité'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER budget_controle_garde
  BEFORE UPDATE OR DELETE ON budget_controlebudgetaire
  FOR EACH ROW EXECUTE FUNCTION budget_controle_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS budget_controle_garde ON budget_controlebudgetaire;
DROP FUNCTION IF EXISTS budget_controle_garde();
ALTER TABLE budget_controlebudgetaire DROP CONSTRAINT IF EXISTS controlebudget_sans_chevauchement;
"""


class Migration(migrations.Migration):
    dependencies = [("budget", "0005_controle_budgetaire")]

    operations = [
        migrations.RunSQL(
            activer_rls("budget_controlebudgetaire"),
            reverse_sql=desactiver_rls("budget_controlebudgetaire"),
        ),
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
    ]
