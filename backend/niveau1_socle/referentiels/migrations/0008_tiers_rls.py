from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls


class Migration(migrations.Migration):
    dependencies = [("referentiels", "0007_tiers")]

    operations = [
        migrations.RunSQL(
            activer_rls("referentiels_tiers"), reverse_sql=desactiver_rls("referentiels_tiers")
        ),
    ]
