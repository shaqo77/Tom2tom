from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = ("avances_delaiavance", "avances_avance", "avances_justificationavance")

CLES = """
ALTER TABLE referentiels_tiers ADD CONSTRAINT uq_tiers_org_id UNIQUE (org_id, id);
ALTER TABLE avances_delaiavance ADD CONSTRAINT fk_delaiavance_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE avances_avance ADD CONSTRAINT fk_avance_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE avances_avance ADD CONSTRAINT fk_avance_tiers_meme_org
  FOREIGN KEY (org_id, tiers_id) REFERENCES referentiels_tiers (org_id, id);
ALTER TABLE avances_avance ADD CONSTRAINT fk_avance_ligne_ecriture
  FOREIGN KEY (ligne_ecriture_id) REFERENCES comptabilite_ligneecriture (id);
ALTER TABLE avances_justificationavance ADD CONSTRAINT fk_justification_ligne_ecriture
  FOREIGN KEY (ligne_ecriture_id) REFERENCES comptabilite_ligneecriture (id);
-- Deux versions du délai d'un projet ne se chevauchent pas.
ALTER TABLE avances_delaiavance ADD CONSTRAINT delaiavance_sans_chevauchement
  EXCLUDE USING gist (org_id WITH =, project_id WITH =, daterange(valid_from, valid_to, '[)') WITH &&);
"""
CLES_INVERSE = """
ALTER TABLE avances_delaiavance DROP CONSTRAINT delaiavance_sans_chevauchement;
ALTER TABLE avances_justificationavance DROP CONSTRAINT fk_justification_ligne_ecriture;
ALTER TABLE avances_avance DROP CONSTRAINT fk_avance_ligne_ecriture;
ALTER TABLE avances_avance DROP CONSTRAINT fk_avance_tiers_meme_org;
ALTER TABLE avances_avance DROP CONSTRAINT fk_avance_projet_meme_org;
ALTER TABLE avances_delaiavance DROP CONSTRAINT fk_delaiavance_projet_meme_org;
ALTER TABLE referentiels_tiers DROP CONSTRAINT uq_tiers_org_id;
"""

# Ajout seul : une avance et ses justifications ne se modifient ni ne se suppriment, pour tout rôle.
# Une justification ne dépasse jamais l'avance (cumul sous verrou de ligne de l'avance, donc exact
# même sous accès concurrents) et ne précède pas le versement. Un délai ne change que par la clôture
# de sa validité.
GARDE = """
CREATE OR REPLACE FUNCTION avances_ajout_seul() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Une avance et ses justifications sont en ajout seul : on ne les modifie ni ne les supprime'
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER avances_avance_ajout_seul
  BEFORE UPDATE OR DELETE ON avances_avance
  FOR EACH ROW EXECUTE FUNCTION avances_ajout_seul();
CREATE TRIGGER avances_justification_ajout_seul
  BEFORE UPDATE OR DELETE ON avances_justificationavance
  FOR EACH ROW EXECUTE FUNCTION avances_ajout_seul();

CREATE OR REPLACE FUNCTION avances_justification_garde() RETURNS trigger AS $$
DECLARE
  av record;
  deja numeric;
BEGIN
  SELECT montant, date_versement INTO av
    FROM avances_avance WHERE id = NEW.avance_id FOR UPDATE;  -- sérialise les justifications
  IF NEW.date_justification < av.date_versement THEN
    RAISE EXCEPTION 'Une justification ne précède pas le versement de l''avance'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT COALESCE(SUM(montant), 0) INTO deja
    FROM avances_justificationavance WHERE avance_id = NEW.avance_id;
  IF deja + NEW.montant > av.montant THEN
    RAISE EXCEPTION 'Les justifications (% + %) dépasseraient l''avance (%)',
      deja, NEW.montant, av.montant USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER avances_justification_garde
  BEFORE INSERT ON avances_justificationavance
  FOR EACH ROW EXECUTE FUNCTION avances_justification_garde();

CREATE OR REPLACE FUNCTION avances_delai_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une version du délai ne se supprime pas : créez-en une nouvelle'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.valid_to IS NOT NULL
     OR (to_jsonb(NEW) - 'valid_to' - 'updated_at' - 'updated_by')
        <> (to_jsonb(OLD) - 'valid_to' - 'updated_at' - 'updated_by') THEN
    RAISE EXCEPTION 'Une version du délai ne change que par la clôture de sa validité'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER avances_delai_garde
  BEFORE UPDATE OR DELETE ON avances_delaiavance
  FOR EACH ROW EXECUTE FUNCTION avances_delai_garde();
"""
GARDE_INVERSE = """
DROP TRIGGER IF EXISTS avances_delai_garde ON avances_delaiavance;
DROP TRIGGER IF EXISTS avances_justification_garde ON avances_justificationavance;
DROP TRIGGER IF EXISTS avances_justification_ajout_seul ON avances_justificationavance;
DROP TRIGGER IF EXISTS avances_avance_ajout_seul ON avances_avance;
DROP FUNCTION IF EXISTS avances_delai_garde();
DROP FUNCTION IF EXISTS avances_justification_garde();
DROP FUNCTION IF EXISTS avances_ajout_seul();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("avances", "0001_avances_justifications"),
        ("organisations", "0004_verrou_sur_grand_livre"),
        ("financements", "0002_rls_cles_garde_fous"),  # pose uq_projet_org_id
        ("referentiels", "0010_correspondance_rls_et_verrou"),
        ("comptabilite", "0014_anouveau_garde_fous"),
    ]

    operations = [
        *(
            migrations.RunSQL(activer_rls(table), reverse_sql=desactiver_rls(table))
            for table in TABLES
        ),
        migrations.RunSQL(CLES, reverse_sql=CLES_INVERSE),
        migrations.RunSQL(GARDE, reverse_sql=GARDE_INVERSE),
    ]
