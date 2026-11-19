from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

SQL = """
ALTER TABLE comptabilite_ecriture ADD CONSTRAINT uq_ecriture_org_id_piece UNIQUE (org_id, id);
ALTER TABLE comptabilite_piecejustificative ADD CONSTRAINT fk_piece_ecriture_meme_org
  FOREIGN KEY (org_id, ecriture_id) REFERENCES comptabilite_ecriture (org_id, id);
ALTER TABLE comptabilite_piecejustificative ADD CONSTRAINT piece_empreinte_32 CHECK (
  octet_length(sha256) = 32 AND taille > 0
);

-- Une pièce est la trace de ce qui justifie une écriture : on l'ajoute, on ne la modifie ni ne la
-- supprime, pour tout rôle. (Sa pièce jointe est une annexe : l'écriture, elle, n'est pas touchée.)
CREATE OR REPLACE FUNCTION comptabilite_piece_ajout_seul() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Une pièce justificative est en ajout seul : on ne la modifie ni ne la supprime'
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER comptabilite_piece_ajout_seul BEFORE UPDATE OR DELETE
  ON comptabilite_piecejustificative
  FOR EACH ROW EXECUTE FUNCTION comptabilite_piece_ajout_seul();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS comptabilite_piece_ajout_seul ON comptabilite_piecejustificative;
DROP FUNCTION IF EXISTS comptabilite_piece_ajout_seul();
ALTER TABLE comptabilite_piecejustificative DROP CONSTRAINT piece_empreinte_32;
ALTER TABLE comptabilite_piecejustificative DROP CONSTRAINT fk_piece_ecriture_meme_org;
ALTER TABLE comptabilite_ecriture DROP CONSTRAINT uq_ecriture_org_id_piece;
"""


class Migration(migrations.Migration):
    dependencies = [("comptabilite", "0015_pieces_justificatives")]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        migrations.RunSQL(
            activer_rls("comptabilite_piecejustificative"),
            reverse_sql=desactiver_rls("comptabilite_piecejustificative"),
        ),
    ]
