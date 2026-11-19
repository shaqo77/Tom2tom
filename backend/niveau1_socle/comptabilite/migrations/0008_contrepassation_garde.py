from django.db import migrations

# On ne contre-passe qu'une écriture COMPTABILISÉE, du MÊME projet, et qui n'est pas elle-même une
# contre-passation. La cohérence `origin = reversal` <-> `reverses` et l'unicité d'une
# contre-passation par écriture sont des contraintes du modèle (migration précédente).
GARDE = """
CREATE OR REPLACE FUNCTION comptabilite_ecriture_contrepassation() RETURNS trigger AS $$
DECLARE
  cible record;
BEGIN
  IF NEW.reverses_id IS NULL THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.reverses_id IS NOT DISTINCT FROM OLD.reverses_id THEN
    RETURN NEW;
  END IF;
  SELECT status, project_id, origin INTO cible
    FROM comptabilite_ecriture WHERE id = NEW.reverses_id;
  IF NOT FOUND THEN
    RETURN NEW;  -- la clé étrangère refusera
  END IF;
  IF cible.status NOT IN ('posted', 'locked') THEN
    RAISE EXCEPTION 'On ne contre-passe qu''une écriture comptabilisée'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF cible.project_id <> NEW.project_id THEN
    RAISE EXCEPTION 'La contre-passation appartient au même projet que l''écriture d''origine'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF cible.origin = 'reversal' THEN
    RAISE EXCEPTION 'Une contre-passation ne se contre-passe pas : saisissez une nouvelle écriture'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ecriture_contrepassation ON comptabilite_ecriture;
CREATE TRIGGER trg_ecriture_contrepassation
  BEFORE INSERT OR UPDATE ON comptabilite_ecriture
  FOR EACH ROW EXECUTE FUNCTION comptabilite_ecriture_contrepassation();
"""
GARDE_INVERSE = """
DROP TRIGGER IF EXISTS trg_ecriture_contrepassation ON comptabilite_ecriture;
DROP FUNCTION IF EXISTS comptabilite_ecriture_contrepassation();
"""


class Migration(migrations.Migration):
    dependencies = [("comptabilite", "0007_contrepassation")]

    operations = [migrations.RunSQL(GARDE, reverse_sql=GARDE_INVERSE)]
