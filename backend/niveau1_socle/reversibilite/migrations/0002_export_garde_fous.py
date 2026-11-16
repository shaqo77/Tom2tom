from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

SQL = """
ALTER TABLE reversibilite_exportorganisation ADD CONSTRAINT export_empreinte_hex CHECK (
  sha256 = '' OR sha256 ~ '^[0-9a-f]{64}$'
);

-- Un export prêt est une pièce : il ne change plus ; il ne se supprime pas. Avant, la seule
-- progression permise est demandé -> en cours -> prêt ou en échec (et un échec se redemande par
-- une NOUVELLE demande).
CREATE OR REPLACE FUNCTION reversibilite_export_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un export ne se supprime pas' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.statut IN ('pret', 'echec') THEN
    RAISE EXCEPTION 'Un export % ne change plus', OLD.statut
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.demandeur_id) IS DISTINCT FROM (OLD.demandeur_id) THEN
    RAISE EXCEPTION 'Le demandeur d''un export ne change pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.statut = 'en_cours' AND NEW.statut = 'demande' THEN
    RAISE EXCEPTION 'Un export en cours ne revient pas à demandé'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER reversibilite_export_garde BEFORE UPDATE OR DELETE ON reversibilite_exportorganisation
  FOR EACH ROW EXECUTE FUNCTION reversibilite_export_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS reversibilite_export_garde ON reversibilite_exportorganisation;
DROP FUNCTION IF EXISTS reversibilite_export_garde();
ALTER TABLE reversibilite_exportorganisation DROP CONSTRAINT export_empreinte_hex;
"""


class Migration(migrations.Migration):
    dependencies = [("reversibilite", "0001_export_organisation")]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        migrations.RunSQL(
            activer_rls("reversibilite_exportorganisation"),
            reverse_sql=desactiver_rls("reversibilite_exportorganisation"),
        ),
    ]
