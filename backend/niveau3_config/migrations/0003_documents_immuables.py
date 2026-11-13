from django.db import migrations

# Un document de référence est ce que les citations visent : son empreinte, son fichier, son titre et
# sa version ne changent jamais, et il ne se supprime pas. Seul le chaînage `superseded_by` se pose,
# UNE fois, vers un document du même projet qui n'est pas lui-même remplacé (donc jamais de cycle).
SQL = """
ALTER TABLE niveau3_config_documentreference ADD CONSTRAINT uq_documentreference_version
  UNIQUE (org_id, project_id, kind, title, version);

CREATE OR REPLACE FUNCTION niveau3_document_garde() RETURNS trigger AS $$
DECLARE
  cible record;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un document de référence ne se supprime jamais : on le remplace'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (to_jsonb(NEW) - 'superseded_by_id' - 'updated_at' - 'updated_by')
     <> (to_jsonb(OLD) - 'superseded_by_id' - 'updated_at' - 'updated_by') THEN
    RAISE EXCEPTION 'Un document de référence ne change pas : son empreinte est ce que les citations visent'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.superseded_by_id IS DISTINCT FROM OLD.superseded_by_id THEN
    IF OLD.superseded_by_id IS NOT NULL THEN
      RAISE EXCEPTION 'Ce document est déjà remplacé' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    SELECT project_id, superseded_by_id INTO cible
      FROM niveau3_config_documentreference WHERE id = NEW.superseded_by_id;
    IF NEW.superseded_by_id = NEW.id OR cible.project_id IS DISTINCT FROM NEW.project_id
       OR cible.superseded_by_id IS NOT NULL THEN
      RAISE EXCEPTION 'Un document est remplacé par un autre document du même projet, lui-même non remplacé'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER niveau3_document_garde
  BEFORE UPDATE OR DELETE ON niveau3_config_documentreference
  FOR EACH ROW EXECUTE FUNCTION niveau3_document_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS niveau3_document_garde ON niveau3_config_documentreference;
DROP FUNCTION IF EXISTS niveau3_document_garde();
ALTER TABLE niveau3_config_documentreference DROP CONSTRAINT uq_documentreference_version;
"""


class Migration(migrations.Migration):
    dependencies = [("niveau3_config", "0002_rls_et_empreinte")]

    operations = [migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE)]
