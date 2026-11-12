from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

# Deux exercices d'un même projet ne se chevauchent pas : garanti par la base.
CHEVAUCHEMENT = """
ALTER TABLE exercices_exercice ADD CONSTRAINT exercice_sans_chevauchement
  EXCLUDE USING gist (org_id WITH =, project_id WITH =,
                      daterange(date_debut, date_fin, '[]') WITH &&);
"""
CHEVAUCHEMENT_INVERSE = (
    "ALTER TABLE exercices_exercice DROP CONSTRAINT exercice_sans_chevauchement;"
)

# ouverte -> close -> verrouillee. Le verrou est définitif, même en SQL direct.
TRANSITION = """
CREATE OR REPLACE FUNCTION exercices_periode_transition() RETURNS trigger AS $$
BEGIN
  IF OLD.status = 'verrouillee' AND NEW.status <> OLD.status THEN
    RAISE EXCEPTION 'Période verrouillée : son statut est définitif'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.status = 'verrouillee' AND OLD.status <> 'verrouillee' AND OLD.status <> 'close' THEN
    RAISE EXCEPTION 'Seule une période close peut être verrouillée'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS periode_transition ON exercices_periode;
CREATE TRIGGER periode_transition
  BEFORE UPDATE ON exercices_periode
  FOR EACH ROW EXECUTE FUNCTION exercices_periode_transition();
"""
TRANSITION_INVERSE = """
DROP TRIGGER IF EXISTS periode_transition ON exercices_periode;
DROP FUNCTION IF EXISTS exercices_periode_transition();
"""


class Migration(migrations.Migration):
    dependencies = [("exercices", "0001_exercices_periodes")]

    operations = [
        BtreeGistExtension(),
        migrations.RunSQL(CHEVAUCHEMENT, reverse_sql=CHEVAUCHEMENT_INVERSE),
        migrations.RunSQL(TRANSITION, reverse_sql=TRANSITION_INVERSE),
        migrations.RunSQL(
            activer_rls("exercices_exercice"), reverse_sql=desactiver_rls("exercices_exercice")
        ),
        migrations.RunSQL(
            activer_rls("exercices_periode"), reverse_sql=desactiver_rls("exercices_periode")
        ),
    ]
