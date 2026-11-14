from django.db import migrations, models

# L'action corrective d'un contrôle et le message d'une évaluation deviennent multilingues
# (`{"fr": …, "en": …}`, JSONB) comme tous les libellés. Un texte existant est conservé en français.
# Le journal est en ajout seul par déclencheur de LIGNE : un changement de type de colonne est une
# opération de schéma, il ne fait pas passer par ce déclencheur.
SQL = """
ALTER TABLE controles_controle
  ALTER COLUMN action_corrective DROP DEFAULT,
  ALTER COLUMN action_corrective TYPE jsonb USING CASE
    WHEN action_corrective IS NULL OR btrim(action_corrective) = '' THEN '{}'::jsonb
    ELSE jsonb_build_object('fr', action_corrective) END,
  ALTER COLUMN action_corrective SET DEFAULT '{}'::jsonb;
ALTER TABLE controles_evaluationcontrole
  ALTER COLUMN action_corrective DROP DEFAULT,
  ALTER COLUMN action_corrective TYPE jsonb USING CASE
    WHEN action_corrective IS NULL OR btrim(action_corrective) = '' THEN '{}'::jsonb
    ELSE jsonb_build_object('fr', action_corrective) END,
  ALTER COLUMN action_corrective SET DEFAULT '{}'::jsonb,
  ALTER COLUMN message DROP DEFAULT,
  ALTER COLUMN message TYPE jsonb USING CASE
    WHEN message IS NULL OR btrim(message) = '' THEN '{}'::jsonb
    ELSE jsonb_build_object('fr', message) END,
  ALTER COLUMN message SET DEFAULT '{}'::jsonb;
ALTER TABLE controles_controle ADD CONSTRAINT controle_action_objet
  CHECK (jsonb_typeof(action_corrective) = 'object');
ALTER TABLE controles_evaluationcontrole ADD CONSTRAINT evaluation_textes_objets
  CHECK (jsonb_typeof(action_corrective) = 'object' AND jsonb_typeof(message) = 'object');
"""
SQL_INVERSE = """
ALTER TABLE controles_evaluationcontrole DROP CONSTRAINT evaluation_textes_objets;
ALTER TABLE controles_controle DROP CONSTRAINT controle_action_objet;
ALTER TABLE controles_evaluationcontrole
  ALTER COLUMN message DROP DEFAULT,
  ALTER COLUMN message TYPE text USING COALESCE(message ->> 'fr', ''),
  ALTER COLUMN message SET DEFAULT '',
  ALTER COLUMN action_corrective DROP DEFAULT,
  ALTER COLUMN action_corrective TYPE text USING COALESCE(action_corrective ->> 'fr', ''),
  ALTER COLUMN action_corrective SET DEFAULT '';
ALTER TABLE controles_controle
  ALTER COLUMN action_corrective DROP DEFAULT,
  ALTER COLUMN action_corrective TYPE text USING COALESCE(action_corrective ->> 'fr', ''),
  ALTER COLUMN action_corrective SET DEFAULT '';
"""


class Migration(migrations.Migration):
    dependencies = [("controles", "0004_parametres_figes")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE)],
            state_operations=[
                migrations.AlterField(
                    model_name="controle",
                    name="action_corrective",
                    field=models.JSONField(blank=True, default=dict),
                ),
                migrations.AlterField(
                    model_name="evaluationcontrole",
                    name="action_corrective",
                    field=models.JSONField(blank=True, default=dict),
                ),
                migrations.AlterField(
                    model_name="evaluationcontrole",
                    name="message",
                    field=models.JSONField(blank=True, default=dict),
                ),
            ],
        )
    ]
