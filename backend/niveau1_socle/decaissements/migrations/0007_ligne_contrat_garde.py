from django.db import migrations

SQL = """
-- Le contrat d'une ligne de demande est un contrat du MÊME projet que la demande (Lot 3-B).
CREATE OR REPLACE FUNCTION decaissements_ligne_contrat_garde() RETURNS trigger AS $$
DECLARE
  projet_demande uuid;
  projet_contrat uuid;
BEGIN
  IF NEW.contrat_id IS NULL THEN
    RETURN NEW;
  END IF;
  SELECT project_id INTO projet_demande FROM decaissements_demanderetrait WHERE id = NEW.demande_id;
  SELECT project_id INTO projet_contrat FROM marches_contrat WHERE id = NEW.contrat_id;
  IF projet_contrat IS DISTINCT FROM projet_demande THEN
    RAISE EXCEPTION 'Le contrat d''une dépense justifiée est un contrat du projet de la demande'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER decaissements_ligne_contrat_garde BEFORE INSERT
  ON decaissements_lignedemande
  FOR EACH ROW EXECUTE FUNCTION decaissements_ligne_contrat_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS decaissements_ligne_contrat_garde ON decaissements_lignedemande;
DROP FUNCTION IF EXISTS decaissements_ligne_contrat_garde();
"""


class Migration(migrations.Migration):
    dependencies = [("decaissements", "0006_ligne_demande_contrat")]

    operations = [migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE)]
