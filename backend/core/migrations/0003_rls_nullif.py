"""Rend la politique d'isolation robuste à une valeur vide.

Sans NULLIF, « app.org_id = '' » provoque une erreur de conversion au lieu
de ne rien montrer. Le défaut sûr doit être « aucune ligne », jamais une
erreur qui pourrait être traitée à tort comme un incident technique.
"""

from django.db import migrations

from ._rls import activer_rls


class Migration(migrations.Migration):
    dependencies = [("core", "0002_rls_et_audit_inalterable"), ("moteur", "0002_rls")]

    operations = [
        migrations.RunSQL(activer_rls("core_auditlog"), reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(
            activer_rls("moteur_ligneecriture"), reverse_sql=migrations.RunSQL.noop
        ),
    ]
