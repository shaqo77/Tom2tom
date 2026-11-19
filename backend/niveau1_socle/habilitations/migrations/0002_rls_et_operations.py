from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

OPERATIONS = """
ALTER TABLE habilitations_role ADD CONSTRAINT role_operations_connues CHECK (
  jsonb_typeof(operations) = 'array'
  AND operations <@ '["consulter","saisir","valider","comptabiliser","parametrer","exporter","publier"]'::jsonb
);
"""
OPERATIONS_INVERSE = "ALTER TABLE habilitations_role DROP CONSTRAINT role_operations_connues;"


class Migration(migrations.Migration):
    dependencies = [("habilitations", "0001_roles_habilitations")]

    operations = [
        migrations.RunSQL(OPERATIONS, reverse_sql=OPERATIONS_INVERSE),
        migrations.RunSQL(
            activer_rls("habilitations_role"), reverse_sql=desactiver_rls("habilitations_role")
        ),
        migrations.RunSQL(
            activer_rls("habilitations_habilitation"),
            reverse_sql=desactiver_rls("habilitations_habilitation"),
        ),
    ]
