from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls


class Migration(migrations.Migration):
    dependencies = [("moteur", "0001_initial")]

    operations = [
        migrations.RunSQL(activer_rls("moteur_ligneecriture"),
                          reverse_sql=desactiver_rls("moteur_ligneecriture")),
    ]
