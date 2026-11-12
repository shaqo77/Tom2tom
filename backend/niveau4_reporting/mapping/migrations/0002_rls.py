from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls


class Migration(migrations.Migration):
    dependencies = [("mapping", "0001_initial")]

    operations = [
        migrations.RunSQL(
            activer_rls("mapping_table"),
            reverse_sql=desactiver_rls("mapping_table"),
        ),
        migrations.RunSQL(
            activer_rls("mapping_rule"),
            reverse_sql=desactiver_rls("mapping_rule"),
        ),
    ]
