from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

# Deux versions d'un même schéma ne se chevauchent pas : garanti par la base, comme pour les
# exercices (extension btree_gist déjà posée par la migration des exercices).
CHEVAUCHEMENT = """
ALTER TABLE comptabilite_schemaecriture ADD CONSTRAINT schema_sans_chevauchement
  EXCLUDE USING gist (org_id WITH =, code WITH =, daterange(valid_from, valid_to, '[)') WITH &&);
"""
CHEVAUCHEMENT_INVERSE = (
    "ALTER TABLE comptabilite_schemaecriture DROP CONSTRAINT schema_sans_chevauchement;"
)

# Une version de schéma utilisée par une écriture ne change plus : ni ses lignes, ni son contenu.
# Seule exception, la clôture de sa validité (`valid_to`), pour lui substituer une nouvelle version.
IMMUABLE = """
CREATE OR REPLACE FUNCTION comptabilite_schema_utilise(cible uuid) RETURNS boolean AS $$
  SELECT EXISTS (SELECT 1 FROM comptabilite_ecriture WHERE schema_id = cible);
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION comptabilite_ligneschema_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') AND comptabilite_schema_utilise(OLD.schema_id) THEN
    RAISE EXCEPTION 'Le schéma est déjà utilisé par des écritures : créez-en une nouvelle version'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') AND comptabilite_schema_utilise(NEW.schema_id) THEN
    RAISE EXCEPTION 'Le schéma est déjà utilisé par des écritures : créez-en une nouvelle version'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION comptabilite_schemaecriture_garde() RETURNS trigger AS $$
BEGIN
  IF comptabilite_schema_utilise(OLD.id)
     AND (to_jsonb(NEW) - 'valid_to' - 'updated_at' - 'updated_by')
       <> (to_jsonb(OLD) - 'valid_to' - 'updated_at' - 'updated_by') THEN
    RAISE EXCEPTION 'Le schéma est déjà utilisé par des écritures : créez-en une nouvelle version'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ligneschema_garde ON comptabilite_ligneschema;
CREATE TRIGGER trg_ligneschema_garde
  BEFORE INSERT OR UPDATE OR DELETE ON comptabilite_ligneschema
  FOR EACH ROW EXECUTE FUNCTION comptabilite_ligneschema_garde();

DROP TRIGGER IF EXISTS trg_schemaecriture_garde ON comptabilite_schemaecriture;
CREATE TRIGGER trg_schemaecriture_garde
  BEFORE UPDATE ON comptabilite_schemaecriture
  FOR EACH ROW EXECUTE FUNCTION comptabilite_schemaecriture_garde();
"""
IMMUABLE_INVERSE = """
DROP TRIGGER IF EXISTS trg_schemaecriture_garde ON comptabilite_schemaecriture;
DROP TRIGGER IF EXISTS trg_ligneschema_garde ON comptabilite_ligneschema;
DROP FUNCTION IF EXISTS comptabilite_schemaecriture_garde();
DROP FUNCTION IF EXISTS comptabilite_ligneschema_garde();
DROP FUNCTION IF EXISTS comptabilite_schema_utilise(uuid);
"""


class Migration(migrations.Migration):
    dependencies = [("comptabilite", "0009_schemas_ecritures")]

    operations = [
        migrations.RunSQL(CHEVAUCHEMENT, reverse_sql=CHEVAUCHEMENT_INVERSE),
        migrations.RunSQL(IMMUABLE, reverse_sql=IMMUABLE_INVERSE),
        migrations.RunSQL(
            activer_rls("comptabilite_schemaecriture"),
            reverse_sql=desactiver_rls("comptabilite_schemaecriture"),
        ),
        migrations.RunSQL(
            activer_rls("comptabilite_ligneschema"),
            reverse_sql=desactiver_rls("comptabilite_ligneschema"),
        ),
    ]
