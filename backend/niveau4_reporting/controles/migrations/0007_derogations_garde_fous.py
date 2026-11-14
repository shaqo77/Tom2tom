from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = ("controles_justification", "controles_derogation")

SQL = """
ALTER TABLE controles_justification ADD CONSTRAINT fk_justification_evaluation_meme_org
  FOREIGN KEY (org_id, evaluation_id) REFERENCES controles_evaluationcontrole (org_id, id);
ALTER TABLE controles_derogation ADD CONSTRAINT fk_derogation_evaluation_meme_org
  FOREIGN KEY (org_id, evaluation_id) REFERENCES controles_evaluationcontrole (org_id, id);
ALTER TABLE controles_derogation ADD CONSTRAINT fk_derogation_controle_meme_org
  FOREIGN KEY (org_id, controle_id) REFERENCES controles_controle (org_id, id);
ALTER TABLE controles_derogation ADD CONSTRAINT fk_derogation_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);

-- Une justification est en AJOUT SEUL (même fonction que le journal d'évaluation).
CREATE TRIGGER controles_ajout_seul BEFORE UPDATE OR DELETE ON controles_justification
  FOR EACH ROW EXECUTE FUNCTION controles_ajout_seul();

-- Une dérogation vise un résultat BLOQUANT, et reprend exactement son contrôle, son projet et son
-- objet : le périmètre ne se choisit pas, il se déduit.
CREATE OR REPLACE FUNCTION controles_derogation_coherence() RETURNS trigger AS $$
DECLARE
  e record;
BEGIN
  SELECT controle_id, project_id, objet_type, objet_id, resultat INTO e
    FROM controles_evaluationcontrole WHERE id = NEW.evaluation_id;
  IF e.resultat IS DISTINCT FROM 'bloquant' THEN
    RAISE EXCEPTION 'Une dérogation vise un résultat bloquant'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (e.controle_id, e.project_id, e.objet_type) IS DISTINCT FROM
       (NEW.controle_id, NEW.project_id, NEW.objet_type)
     OR e.objet_id IS DISTINCT FROM NEW.objet_id THEN
    RAISE EXCEPTION 'La dérogation reprend le contrôle, le projet et l''objet de l''évaluation'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.statut <> 'demandee' THEN
    RAISE EXCEPTION 'Une dérogation naît « demandée »'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER controles_derogation_coherence BEFORE INSERT ON controles_derogation
  FOR EACH ROW EXECUTE FUNCTION controles_derogation_coherence();

-- Une dérogation se décide UNE fois (demandée -> approuvée ou refusée) ; rien d'autre ne change ;
-- elle ne se supprime pas. Deux approbations concurrentes : la seconde échoue ici même si le
-- service oubliait de verrouiller.
CREATE OR REPLACE FUNCTION controles_derogation_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une dérogation ne se supprime pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.statut <> 'demandee' THEN
    RAISE EXCEPTION 'Une dérogation décidée ne change plus'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.evaluation_id, NEW.controle_id, NEW.project_id, NEW.objet_type, NEW.motif,
      NEW.justificatif, NEW.valide_du, NEW.valide_jusquau, NEW.demandeur_id)
       IS DISTINCT FROM
     (OLD.evaluation_id, OLD.controle_id, OLD.project_id, OLD.objet_type, OLD.motif,
      OLD.justificatif, OLD.valide_du, OLD.valide_jusquau, OLD.demandeur_id)
     OR NEW.objet_id IS DISTINCT FROM OLD.objet_id THEN
    RAISE EXCEPTION 'Le contenu d''une dérogation ne se modifie pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER controles_derogation_garde BEFORE UPDATE OR DELETE ON controles_derogation
  FOR EACH ROW EXECUTE FUNCTION controles_derogation_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS controles_derogation_garde ON controles_derogation;
DROP FUNCTION IF EXISTS controles_derogation_garde();
DROP TRIGGER IF EXISTS controles_derogation_coherence ON controles_derogation;
DROP FUNCTION IF EXISTS controles_derogation_coherence();
DROP TRIGGER IF EXISTS controles_ajout_seul ON controles_justification;
ALTER TABLE controles_derogation DROP CONSTRAINT fk_derogation_projet_meme_org;
ALTER TABLE controles_derogation DROP CONSTRAINT fk_derogation_controle_meme_org;
ALTER TABLE controles_derogation DROP CONSTRAINT fk_derogation_evaluation_meme_org;
ALTER TABLE controles_justification DROP CONSTRAINT fk_justification_evaluation_meme_org;
"""


class Migration(migrations.Migration):
    dependencies = [("controles", "0006_justifications_derogations")]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        *(migrations.RunSQL(activer_rls(t), reverse_sql=desactiver_rls(t)) for t in TABLES),
    ]
