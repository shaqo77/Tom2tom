from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

# La classe est le premier chiffre du code : une classe qui s'en écarte est une faute de saisie.
CLASSE = """
ALTER TABLE referentiels_compte ADD CONSTRAINT compte_classe_egale_premier_chiffre
  CHECK (classe = left(code, 1)::int);
"""
CLASSE_INVERSE = "ALTER TABLE referentiels_compte DROP CONSTRAINT compte_classe_egale_premier_chiffre;"

# Seul un compte feuille est imputable : un total a des enfants et n'en reçoit pas.
HIERARCHIE = """
CREATE OR REPLACE FUNCTION referentiels_compte_hierarchie() RETURNS trigger AS $$
BEGIN
  IF NEW.parent_id IS NOT NULL
     AND (SELECT imputable FROM referentiels_compte WHERE id = NEW.parent_id) THEN
    RAISE EXCEPTION 'Le compte parent % est imputable : un compte imputable ne peut avoir d''enfant',
      NEW.parent_id USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.imputable
     AND EXISTS (SELECT 1 FROM referentiels_compte WHERE parent_id = NEW.id) THEN
    RAISE EXCEPTION 'Le compte % a des enfants : il ne peut pas devenir imputable', NEW.code
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS compte_hierarchie ON referentiels_compte;
CREATE TRIGGER compte_hierarchie
  BEFORE INSERT OR UPDATE ON referentiels_compte
  FOR EACH ROW EXECUTE FUNCTION referentiels_compte_hierarchie();
"""
HIERARCHIE_INVERSE = """
DROP TRIGGER IF EXISTS compte_hierarchie ON referentiels_compte;
DROP FUNCTION IF EXISTS referentiels_compte_hierarchie();
"""


class Migration(migrations.Migration):
    dependencies = [("referentiels", "0003_plan_comptable")]

    operations = [
        migrations.RunSQL(CLASSE, reverse_sql=CLASSE_INVERSE),
        migrations.RunSQL(HIERARCHIE, reverse_sql=HIERARCHIE_INVERSE),
        migrations.RunSQL(
            activer_rls("referentiels_compte"), reverse_sql=desactiver_rls("referentiels_compte")
        ),
    ]
