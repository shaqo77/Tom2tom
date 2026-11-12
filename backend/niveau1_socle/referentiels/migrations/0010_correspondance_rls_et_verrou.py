from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

# Une correspondance validée est rejouée à l'identique : elle ne se modifie plus.
VERROU = """
CREATE OR REPLACE FUNCTION referentiels_correspondance_verrou() RETURNS trigger AS $$
BEGIN
  IF OLD.statut = 'validee'
     AND (NEW.nom, NEW.type_referentiel, NEW.colonnes, NEW.valeurs_defaut)
         IS DISTINCT FROM (OLD.nom, OLD.type_referentiel, OLD.colonnes, OLD.valeurs_defaut) THEN
    RAISE EXCEPTION 'Correspondance validée : créez-en une nouvelle plutôt que de la modifier'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS correspondance_verrou ON referentiels_correspondanceimport;
CREATE TRIGGER correspondance_verrou
  BEFORE UPDATE ON referentiels_correspondanceimport
  FOR EACH ROW EXECUTE FUNCTION referentiels_correspondance_verrou();
"""
VERROU_INVERSE = """
DROP TRIGGER IF EXISTS correspondance_verrou ON referentiels_correspondanceimport;
DROP FUNCTION IF EXISTS referentiels_correspondance_verrou();
"""


class Migration(migrations.Migration):
    dependencies = [("referentiels", "0009_correspondance_import")]

    operations = [
        migrations.RunSQL(VERROU, reverse_sql=VERROU_INVERSE),
        migrations.RunSQL(
            activer_rls("referentiels_correspondanceimport"),
            reverse_sql=desactiver_rls("referentiels_correspondanceimport"),
        ),
    ]
