from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

# Un à-nouveau est une trace comptable : il ne se supprime jamais, et son seul changement permis
# est le passage « actif » -> « remplacé », avec l'écriture d'annulation qui l'accompagne.
# Les écritures, les montants et l'empreinte ne bougent plus une fois la ligne créée.
GARDE = """
CREATE OR REPLACE FUNCTION comptabilite_anouveau_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un à-nouveau ne se supprime pas : régénérez l''exercice pour le remplacer'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.status = 'remplace' THEN
    RAISE EXCEPTION 'Une version d''à-nouveau remplacée est figée'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.status <> 'remplace' OR NEW.ecriture_annulation_id IS NULL
     OR (to_jsonb(NEW) - 'status' - 'ecriture_annulation_id')
        <> (to_jsonb(OLD) - 'status' - 'ecriture_annulation_id') THEN
    RAISE EXCEPTION 'Un à-nouveau ne change que pour passer à « remplacé » avec son annulation'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER comptabilite_anouveau_garde
  BEFORE UPDATE OR DELETE ON comptabilite_anouveau
  FOR EACH ROW EXECUTE FUNCTION comptabilite_anouveau_garde();
"""

GARDE_INVERSE = """
DROP TRIGGER IF EXISTS comptabilite_anouveau_garde ON comptabilite_anouveau;
DROP FUNCTION IF EXISTS comptabilite_anouveau_garde();
"""


class Migration(migrations.Migration):
    dependencies = [("comptabilite", "0013_anouveau")]

    operations = [
        migrations.RunSQL(
            activer_rls("comptabilite_anouveau"), reverse_sql=desactiver_rls("comptabilite_anouveau")
        ),
        migrations.RunSQL(GARDE, reverse_sql=GARDE_INVERSE),
    ]
