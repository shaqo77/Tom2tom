from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = [
    "niveau3_config_documentreference",
    "niveau3_config_exigence",
    "niveau3_config_rattachementexigence",
]

EMPREINTE = """
ALTER TABLE niveau3_config_documentreference
  ADD CONSTRAINT documentreference_sha256_32_octets CHECK (octet_length(sha256) = 32);
"""
EMPREINTE_INVERSE = """
ALTER TABLE niveau3_config_documentreference
  DROP CONSTRAINT documentreference_sha256_32_octets;
"""


class Migration(migrations.Migration):
    dependencies = [("niveau3_config", "0001_registre_exigences")]

    operations = [
        migrations.RunSQL(EMPREINTE, reverse_sql=EMPREINTE_INVERSE),
        *[
            migrations.RunSQL(activer_rls(table), reverse_sql=desactiver_rls(table))
            for table in TABLES
        ],
    ]
