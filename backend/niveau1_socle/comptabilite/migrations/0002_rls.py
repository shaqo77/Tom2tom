from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = [
    "comptabilite_journal",
    "comptabilite_ecriture",
    "comptabilite_ligneecriture",
]


class Migration(migrations.Migration):
    dependencies = [("comptabilite", "0001_grand_livre")]

    operations = [
        migrations.RunSQL(activer_rls(table), reverse_sql=desactiver_rls(table))
        for table in TABLES
    ]
