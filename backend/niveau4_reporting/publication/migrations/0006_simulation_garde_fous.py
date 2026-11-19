from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = (
    "publication_motifrejet",
    "publication_simulationrevue",
    "publication_soumissionbailleur",
)

SQL = """
ALTER TABLE publication_simulationrevue ADD CONSTRAINT uq_simulationrevue_org_id
  UNIQUE (org_id, id);
ALTER TABLE publication_motifrejet ADD CONSTRAINT fk_motif_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE publication_simulationrevue ADD CONSTRAINT fk_simulation_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE publication_soumissionbailleur ADD CONSTRAINT fk_soumission_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE publication_soumissionbailleur ADD CONSTRAINT fk_soumission_simulation_meme_org
  FOREIGN KEY (org_id, simulation_id) REFERENCES publication_simulationrevue (org_id, id);

-- Une simulation est gardée telle quelle : ajout seul.
CREATE TRIGGER publication_ajout_seul BEFORE UPDATE OR DELETE ON publication_simulationrevue
  FOR EACH ROW EXECUTE FUNCTION publication_ajout_seul();

-- Un motif ne change pas de contrôle ni de code (on en ajoute un autre) ; il se désactive ; il ne
-- se supprime pas, parce qu'une simulation passée peut le citer.
CREATE OR REPLACE FUNCTION publication_motif_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un motif de rejet ne se supprime pas : on le désactive'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.project_id, NEW.code, NEW.controle_code) IS DISTINCT FROM
     (OLD.project_id, OLD.code, OLD.controle_code) THEN
    RAISE EXCEPTION 'Le code et le contrôle d''un motif de rejet ne se modifient pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER publication_motif_garde BEFORE UPDATE OR DELETE ON publication_motifrejet
  FOR EACH ROW EXECUTE FUNCTION publication_motif_garde();

-- Une soumission : l'issue se pose UNE fois (en attente -> accepté ou rejeté) ; rien d'autre ne
-- change ; elle ne se supprime pas.
CREATE OR REPLACE FUNCTION publication_soumission_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une soumission ne se supprime pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.resultat <> 'en_attente' THEN
    RAISE EXCEPTION 'L''issue d''une soumission ne se réécrit pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.project_id, NEW.template_code, NEW.period_to, NEW.numero_envoi, NEW.envoyee_le,
      NEW.saisie_par) IS DISTINCT FROM
     (OLD.project_id, OLD.template_code, OLD.period_to, OLD.numero_envoi, OLD.envoyee_le,
      OLD.saisie_par)
     OR NEW.rapport_id IS DISTINCT FROM OLD.rapport_id
     OR NEW.simulation_id IS DISTINCT FROM OLD.simulation_id THEN
    RAISE EXCEPTION 'Le contenu d''une soumission ne se modifie pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER publication_soumission_garde BEFORE UPDATE OR DELETE
  ON publication_soumissionbailleur
  FOR EACH ROW EXECUTE FUNCTION publication_soumission_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS publication_soumission_garde ON publication_soumissionbailleur;
DROP FUNCTION IF EXISTS publication_soumission_garde();
DROP TRIGGER IF EXISTS publication_motif_garde ON publication_motifrejet;
DROP FUNCTION IF EXISTS publication_motif_garde();
DROP TRIGGER IF EXISTS publication_ajout_seul ON publication_simulationrevue;
ALTER TABLE publication_soumissionbailleur DROP CONSTRAINT fk_soumission_simulation_meme_org;
ALTER TABLE publication_soumissionbailleur DROP CONSTRAINT fk_soumission_projet_meme_org;
ALTER TABLE publication_simulationrevue DROP CONSTRAINT fk_simulation_projet_meme_org;
ALTER TABLE publication_motifrejet DROP CONSTRAINT fk_motif_projet_meme_org;
ALTER TABLE publication_simulationrevue DROP CONSTRAINT uq_simulationrevue_org_id;
"""


class Migration(migrations.Migration):
    dependencies = [("publication", "0005_simulation_et_soumissions")]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        *(migrations.RunSQL(activer_rls(t), reverse_sql=desactiver_rls(t)) for t in TABLES),
    ]
