from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

SQL = """
ALTER TABLE organisations_jetonapi ADD CONSTRAINT jeton_api_empreinte_32 CHECK (
  octet_length(empreinte) = 32
);
ALTER TABLE organisations_jetonapi ADD CONSTRAINT jeton_api_prefixe_8 CHECK (
  char_length(prefixe) = 8
);
ALTER TABLE organisations_jetonapi ADD CONSTRAINT jeton_api_libelle_non_vide CHECK (
  btrim(libelle) <> ''
);
ALTER TABLE organisations_jetonapi ADD CONSTRAINT jeton_api_expiration_apres_creation CHECK (
  expire_le > created_at
);

-- Un jeton ne se prolonge pas, ne change ni de propriétaire ni de secret, et ne se supprime pas :
-- il reste la preuve de ce qui a été autorisé. Seuls se posent : la révocation (une fois, jamais
-- réécrite) et la date du dernier usage.
CREATE OR REPLACE FUNCTION organisations_jeton_api_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un jeton d''API ne se supprime pas : on le révoque'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.utilisateur_id, NEW.libelle, NEW.prefixe, NEW.empreinte, NEW.expire_le, NEW.org_id)
     IS DISTINCT FROM
     (OLD.utilisateur_id, OLD.libelle, OLD.prefixe, OLD.empreinte, OLD.expire_le, OLD.org_id) THEN
    RAISE EXCEPTION 'Un jeton d''API ne se modifie ni ne se prolonge : créez-en un autre'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.revoque_le IS NOT NULL AND NEW.revoque_le IS DISTINCT FROM OLD.revoque_le THEN
    RAISE EXCEPTION 'La révocation d''un jeton d''API ne se réécrit pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER organisations_jeton_api_garde BEFORE UPDATE OR DELETE
  ON organisations_jetonapi
  FOR EACH ROW EXECUTE FUNCTION organisations_jeton_api_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS organisations_jeton_api_garde ON organisations_jetonapi;
DROP FUNCTION IF EXISTS organisations_jeton_api_garde();
ALTER TABLE organisations_jetonapi DROP CONSTRAINT jeton_api_expiration_apres_creation;
ALTER TABLE organisations_jetonapi DROP CONSTRAINT jeton_api_libelle_non_vide;
ALTER TABLE organisations_jetonapi DROP CONSTRAINT jeton_api_prefixe_8;
ALTER TABLE organisations_jetonapi DROP CONSTRAINT jeton_api_empreinte_32;
"""


class Migration(migrations.Migration):
    dependencies = [("organisations", "0006_jeton_api")]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        migrations.RunSQL(
            activer_rls("organisations_jetonapi"),
            reverse_sql=desactiver_rls("organisations_jetonapi"),
        ),
    ]
