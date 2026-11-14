from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

SQL = """
ALTER TABLE publication_rapportpublie ADD CONSTRAINT uq_rapportpublie_org_id UNIQUE (org_id, id);
ALTER TABLE publication_fichierrapport ADD CONSTRAINT fk_fichier_rapport_meme_org
  FOREIGN KEY (org_id, rapport_id) REFERENCES publication_rapportpublie (org_id, id);
ALTER TABLE publication_fichierrapport ADD CONSTRAINT fichier_empreinte_coherente CHECK (
  sha256 ~ '^[0-9a-f]{64}$' AND taille = octet_length(contenu)
  AND sha256 = encode(sha256(contenu), 'hex')
);
-- Le fichier et son empreinte sont écrits ensemble, une fois : même fonction d'ajout seul.
CREATE TRIGGER publication_ajout_seul BEFORE UPDATE OR DELETE ON publication_fichierrapport
  FOR EACH ROW EXECUTE FUNCTION publication_ajout_seul();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS publication_ajout_seul ON publication_fichierrapport;
ALTER TABLE publication_fichierrapport DROP CONSTRAINT fichier_empreinte_coherente;
ALTER TABLE publication_fichierrapport DROP CONSTRAINT fk_fichier_rapport_meme_org;
ALTER TABLE publication_rapportpublie DROP CONSTRAINT uq_rapportpublie_org_id;
"""


class Migration(migrations.Migration):
    dependencies = [("publication", "0003_fichiers_des_rapports")]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        migrations.RunSQL(
            activer_rls("publication_fichierrapport"),
            reverse_sql=desactiver_rls("publication_fichierrapport"),
        ),
    ]
