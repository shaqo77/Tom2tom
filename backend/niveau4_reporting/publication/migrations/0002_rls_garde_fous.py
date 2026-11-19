from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

SQL = """
ALTER TABLE publication_rapportpublie ADD CONSTRAINT fk_rapport_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);

ALTER TABLE publication_rapportpublie ADD CONSTRAINT rapport_scelle CHECK (
  octet_length(seal) = 32 AND octet_length(dataset_hash) = 32
  AND jsonb_typeof(values) = 'object' AND jsonb_typeof(modele) = 'object'
);

-- Un rapport publié est la trace de ce qui a été transmis : jamais modifié, jamais supprimé, pour
-- tout rôle. Corriger, c'est publier un autre rapport.
CREATE OR REPLACE FUNCTION publication_ajout_seul() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION '% est en ajout seul : un rapport publié ne se modifie ni ne se supprime',
    TG_TABLE_NAME USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER publication_ajout_seul BEFORE UPDATE OR DELETE ON publication_rapportpublie
  FOR EACH ROW EXECUTE FUNCTION publication_ajout_seul();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS publication_ajout_seul ON publication_rapportpublie;
DROP FUNCTION IF EXISTS publication_ajout_seul();
ALTER TABLE publication_rapportpublie DROP CONSTRAINT rapport_scelle;
ALTER TABLE publication_rapportpublie DROP CONSTRAINT fk_rapport_projet_meme_org;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("publication", "0001_initial"),
        ("controles", "0002_rls_cles_garde_fous"),  # pose uq_projet_org_id via financements
    ]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        migrations.RunSQL(
            activer_rls("publication_rapportpublie"),
            reverse_sql=desactiver_rls("publication_rapportpublie"),
        ),
    ]
