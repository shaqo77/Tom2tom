from django.db import migrations

from ._rls import activer_rls, desactiver_rls

REVOKE = """
REVOKE UPDATE, DELETE ON core_auditlog FROM sigf_app;
REVOKE UPDATE, DELETE ON core_auditlog FROM PUBLIC;
"""
REGRANT = """
GRANT UPDATE, DELETE ON core_auditlog TO sigf_app;
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.RunSQL(activer_rls("core_auditlog"),
                          reverse_sql=desactiver_rls("core_auditlog")),
        migrations.RunSQL(REVOKE, reverse_sql=REGRANT),
    ]
