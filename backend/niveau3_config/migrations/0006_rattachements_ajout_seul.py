from django.db import migrations

# Un rattachement est la trace de ce qui justifie un objet de configuration : il ne se modifie ni ne
# se supprime (on remplace l'objet ou l'exigence par une version nouvelle). Il ne se pose pas sur une
# exigence remplacée ou rejetée, qui ne justifie plus rien.
SQL = """
CREATE OR REPLACE FUNCTION niveau3_rattachement_garde() RETURNS trigger AS $$
DECLARE
  statut text;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    RAISE EXCEPTION 'Un rattachement est en ajout seul : on ne le modifie ni ne le supprime'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT status INTO statut FROM niveau3_config_exigence WHERE id = NEW.exigence_id;
  IF statut IN ('superseded', 'rejected') THEN
    RAISE EXCEPTION 'Une exigence % ne justifie plus aucun objet', statut
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER niveau3_rattachement_garde
  BEFORE INSERT OR UPDATE OR DELETE ON niveau3_config_rattachementexigence
  FOR EACH ROW EXECUTE FUNCTION niveau3_rattachement_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS niveau3_rattachement_garde ON niveau3_config_rattachementexigence;
DROP FUNCTION IF EXISTS niveau3_rattachement_garde();
"""


class Migration(migrations.Migration):
    dependencies = [("niveau3_config", "0005_exigences_garde_fous")]

    operations = [migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE)]
