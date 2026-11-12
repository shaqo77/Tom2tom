from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

# Seules les feuilles sont imputables ; un enfant reste dans le plan de son parent.
HIERARCHIE = """
CREATE OR REPLACE FUNCTION referentiels_valeurdimension_hierarchie() RETURNS trigger AS $$
DECLARE
  parent referentiels_valeurdimension%ROWTYPE;
BEGIN
  IF NEW.parent_id IS NOT NULL THEN
    SELECT * INTO parent FROM referentiels_valeurdimension WHERE id = NEW.parent_id;
    IF parent.is_postable THEN
      RAISE EXCEPTION 'La valeur parente % est imputable : une feuille ne peut avoir d''enfant',
        parent.code USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF parent.plan_id <> NEW.plan_id THEN
      RAISE EXCEPTION 'Une valeur ne peut pas dépendre d''une valeur d''un autre plan'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.is_postable
     AND EXISTS (SELECT 1 FROM referentiels_valeurdimension WHERE parent_id = NEW.id) THEN
    RAISE EXCEPTION 'La valeur % a des enfants : elle ne peut pas devenir imputable', NEW.code
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS valeurdimension_hierarchie ON referentiels_valeurdimension;
CREATE TRIGGER valeurdimension_hierarchie
  BEFORE INSERT OR UPDATE ON referentiels_valeurdimension
  FOR EACH ROW EXECUTE FUNCTION referentiels_valeurdimension_hierarchie();
"""
HIERARCHIE_INVERSE = """
DROP TRIGGER IF EXISTS valeurdimension_hierarchie ON referentiels_valeurdimension;
DROP FUNCTION IF EXISTS referentiels_valeurdimension_hierarchie();
"""


class Migration(migrations.Migration):
    dependencies = [("referentiels", "0005_axes")]

    operations = [
        migrations.RunSQL(HIERARCHIE, reverse_sql=HIERARCHIE_INVERSE),
        migrations.RunSQL(
            activer_rls("referentiels_plandimension"),
            reverse_sql=desactiver_rls("referentiels_plandimension"),
        ),
        migrations.RunSQL(
            activer_rls("referentiels_valeurdimension"),
            reverse_sql=desactiver_rls("referentiels_valeurdimension"),
        ),
    ]
