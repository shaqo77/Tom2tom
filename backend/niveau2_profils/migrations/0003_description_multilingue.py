from django.db import migrations, models

# La description d'un profil de bailleur devient multilingue (`{"fr": …, "en": …}`, JSONB). Un
# texte existant est conservé en français. Les profils publiés sont figés par un déclencheur de
# LIGNE : ce changement de type de colonne est une opération de schéma, il ne passe pas par lui.
SQL = """
ALTER TABLE niveau2_profils_profilbailleur
  ALTER COLUMN description DROP DEFAULT,
  ALTER COLUMN description TYPE jsonb USING CASE
    WHEN description IS NULL OR btrim(description) = '' THEN '{}'::jsonb
    ELSE jsonb_build_object('fr', description) END,
  ALTER COLUMN description SET DEFAULT '{}'::jsonb;
ALTER TABLE niveau2_profils_profilbailleur ADD CONSTRAINT profil_bailleur_description_objet
  CHECK (jsonb_typeof(description) = 'object');
"""
SQL_INVERSE = """
ALTER TABLE niveau2_profils_profilbailleur DROP CONSTRAINT profil_bailleur_description_objet;
ALTER TABLE niveau2_profils_profilbailleur
  ALTER COLUMN description DROP DEFAULT,
  ALTER COLUMN description TYPE text USING COALESCE(description ->> 'fr', ''),
  ALTER COLUMN description SET DEFAULT '';
"""


class Migration(migrations.Migration):
    dependencies = [("niveau2_profils", "0002_rls_cles_garde_fous")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE)],
            state_operations=[
                migrations.AlterField(
                    model_name="profilbailleur",
                    name="description",
                    field=models.JSONField(blank=True, default=dict),
                ),
            ],
        )
    ]
