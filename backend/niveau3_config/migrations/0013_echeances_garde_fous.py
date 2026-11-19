from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

SQL = """
ALTER TABLE niveau3_config_exigence ADD CONSTRAINT uq_exigence_org_id_echeance UNIQUE (org_id, id);
ALTER TABLE niveau3_config_echeance ADD CONSTRAINT fk_echeance_exigence_meme_org
  FOREIGN KEY (org_id, exigence_id) REFERENCES niveau3_config_exigence (org_id, id);
ALTER TABLE niveau3_config_echeance ADD CONSTRAINT fk_echeance_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);

-- Une échéance ne change jamais de date ni d'exigence (une exigence révisée en produit d'autres) ;
-- elle passe d'« à remettre » à « remise » ou « annulée », une fois ; elle ne se supprime pas.
CREATE OR REPLACE FUNCTION niveau3_echeance_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une échéance ne se supprime pas : on l''annule'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.exigence_id, NEW.project_id, NEW.periode_debut, NEW.periode_fin, NEW.date_echeance)
       IS DISTINCT FROM
     (OLD.exigence_id, OLD.project_id, OLD.periode_debut, OLD.periode_fin, OLD.date_echeance) THEN
    RAISE EXCEPTION 'La date et l''exigence d''une échéance ne se modifient pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.statut <> 'a_remettre' AND NEW.statut IS DISTINCT FROM OLD.statut THEN
    RAISE EXCEPTION 'Une échéance % est définitive', OLD.statut
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.statut <> 'a_remettre' AND (NEW.rapport_id, NEW.remise_le, NEW.remise_par)
       IS DISTINCT FROM (OLD.rapport_id, OLD.remise_le, OLD.remise_par) THEN
    RAISE EXCEPTION 'La remise d''une échéance ne se réécrit pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER niveau3_echeance_garde BEFORE UPDATE OR DELETE ON niveau3_config_echeance
  FOR EACH ROW EXECUTE FUNCTION niveau3_echeance_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS niveau3_echeance_garde ON niveau3_config_echeance;
DROP FUNCTION IF EXISTS niveau3_echeance_garde();
ALTER TABLE niveau3_config_echeance DROP CONSTRAINT fk_echeance_projet_meme_org;
ALTER TABLE niveau3_config_echeance DROP CONSTRAINT fk_echeance_exigence_meme_org;
ALTER TABLE niveau3_config_exigence DROP CONSTRAINT uq_exigence_org_id_echeance;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("niveau3_config", "0012_echeances"),
        ("controles", "0002_rls_cles_garde_fous"),  # pose uq_projet_org_id via financements
    ]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        migrations.RunSQL(
            activer_rls("niveau3_config_echeance"),
            reverse_sql=desactiver_rls("niveau3_config_echeance"),
        ),
    ]
