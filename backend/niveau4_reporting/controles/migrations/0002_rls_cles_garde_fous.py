from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = ("controles_controle", "controles_evaluationcontrole", "controles_decisioncontrole")

SQL = """
ALTER TABLE controles_controle ADD CONSTRAINT uq_controle_org_id UNIQUE (org_id, id);
ALTER TABLE controles_evaluationcontrole ADD CONSTRAINT uq_evaluation_controle_org_id
  UNIQUE (org_id, id);
ALTER TABLE controles_controle ADD CONSTRAINT fk_controle_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE controles_evaluationcontrole ADD CONSTRAINT fk_evaluation_controle_meme_org
  FOREIGN KEY (org_id, controle_id) REFERENCES controles_controle (org_id, id);
ALTER TABLE controles_decisioncontrole ADD CONSTRAINT fk_decision_evaluation_meme_org
  FOREIGN KEY (org_id, evaluation_id) REFERENCES controles_evaluationcontrole (org_id, id);

ALTER TABLE controles_controle ADD CONSTRAINT controle_objets_json CHECK (
  (expression IS NULL OR jsonb_typeof(expression) = 'object')
  AND (applicable_si IS NULL OR jsonb_typeof(applicable_si) = 'object')
);

-- Un seul contrôle actif par code et par période (fin exclue), garanti par la base.
ALTER TABLE controles_controle ADD CONSTRAINT controle_actif_sans_chevauchement
  EXCLUDE USING gist (org_id WITH =, project_id WITH =, code WITH =,
                      daterange(valid_from, valid_to, '[)') WITH &&)
  WHERE (status = 'active');

-- Un contrôle validé ne change plus de contenu ; son statut ne recule pas ; seul un brouillon
-- se supprime. (Même discipline que les exigences et les profils : on crée une version.)
CREATE OR REPLACE FUNCTION controles_controle_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Un contrôle % ne se supprime pas', OLD.status
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status IN ('superseded', 'rejected') AND NEW.status IS DISTINCT FROM OLD.status THEN
    RAISE EXCEPTION 'Un contrôle % est définitif', OLD.status
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF niveau3_rang_statut(NEW.status) < niveau3_rang_statut(OLD.status) THEN
    RAISE EXCEPTION 'Le statut d''un contrôle ne recule pas (% vers %)', OLD.status, NEW.status
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.status IN ('validated', 'active') THEN
    IF (NEW.project_id, NEW.code, NEW.version, NEW.type_regle, NEW.severity, NEW.mode,
        NEW.valid_from, NEW.action_corrective)
         IS DISTINCT FROM
       (OLD.project_id, OLD.code, OLD.version, OLD.type_regle, OLD.severity, OLD.mode,
        OLD.valid_from, OLD.action_corrective)
       OR NEW.expression IS DISTINCT FROM OLD.expression
       OR NEW.applicable_si IS DISTINCT FROM OLD.applicable_si
       OR NEW.label IS DISTINCT FROM OLD.label
       OR NEW.validated_by IS DISTINCT FROM OLD.validated_by
       OR NEW.validated_at IS DISTINCT FROM OLD.validated_at
    THEN
      RAISE EXCEPTION 'Un contrôle validé ne se modifie pas : créez une nouvelle version'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.valid_to IS DISTINCT FROM OLD.valid_to AND OLD.valid_to IS NOT NULL THEN
      RAISE EXCEPTION 'La fin de validité d''un contrôle ne se modifie plus'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER controles_controle_garde
  BEFORE UPDATE OR DELETE ON controles_controle
  FOR EACH ROW EXECUTE FUNCTION controles_controle_garde();

-- Le journal et les décisions sont en AJOUT SEUL, pour tout rôle.
CREATE OR REPLACE FUNCTION controles_ajout_seul() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION '% est en ajout seul : on ne modifie ni ne supprime une ligne', TG_TABLE_NAME
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER controles_ajout_seul BEFORE UPDATE OR DELETE ON controles_evaluationcontrole
  FOR EACH ROW EXECUTE FUNCTION controles_ajout_seul();
CREATE TRIGGER controles_ajout_seul BEFORE UPDATE OR DELETE ON controles_decisioncontrole
  FOR EACH ROW EXECUTE FUNCTION controles_ajout_seul();

-- Une évaluation décrit la version du contrôle qu'elle évalue, dans son projet.
CREATE OR REPLACE FUNCTION controles_evaluation_coherence() RETURNS trigger AS $$
DECLARE
  c record;
BEGIN
  SELECT version, project_id INTO c FROM controles_controle WHERE id = NEW.controle_id;
  IF c.version IS DISTINCT FROM NEW.controle_version OR c.project_id IS DISTINCT FROM NEW.project_id THEN
    RAISE EXCEPTION 'L''évaluation décrit la version et le projet du contrôle évalué'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER controles_evaluation_coherence BEFORE INSERT ON controles_evaluationcontrole
  FOR EACH ROW EXECUTE FUNCTION controles_evaluation_coherence();

-- Seul un contrôle « à vérifier » reçoit une décision.
CREATE OR REPLACE FUNCTION controles_decision_coherence() RETURNS trigger AS $$
DECLARE
  resultat text;
BEGIN
  SELECT e.resultat INTO resultat FROM controles_evaluationcontrole e WHERE e.id = NEW.evaluation_id;
  IF resultat IS DISTINCT FROM 'a_verifier' THEN
    RAISE EXCEPTION 'Seul un contrôle « à vérifier » se tranche'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER controles_decision_coherence BEFORE INSERT ON controles_decisioncontrole
  FOR EACH ROW EXECUTE FUNCTION controles_decision_coherence();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS controles_decision_coherence ON controles_decisioncontrole;
DROP FUNCTION IF EXISTS controles_decision_coherence();
DROP TRIGGER IF EXISTS controles_evaluation_coherence ON controles_evaluationcontrole;
DROP FUNCTION IF EXISTS controles_evaluation_coherence();
DROP TRIGGER IF EXISTS controles_ajout_seul ON controles_decisioncontrole;
DROP TRIGGER IF EXISTS controles_ajout_seul ON controles_evaluationcontrole;
DROP FUNCTION IF EXISTS controles_ajout_seul();
DROP TRIGGER IF EXISTS controles_controle_garde ON controles_controle;
DROP FUNCTION IF EXISTS controles_controle_garde();
ALTER TABLE controles_controle DROP CONSTRAINT controle_actif_sans_chevauchement;
ALTER TABLE controles_controle DROP CONSTRAINT controle_objets_json;
ALTER TABLE controles_decisioncontrole DROP CONSTRAINT fk_decision_evaluation_meme_org;
ALTER TABLE controles_evaluationcontrole DROP CONSTRAINT fk_evaluation_controle_meme_org;
ALTER TABLE controles_controle DROP CONSTRAINT fk_controle_projet_meme_org;
ALTER TABLE controles_evaluationcontrole DROP CONSTRAINT uq_evaluation_controle_org_id;
ALTER TABLE controles_controle DROP CONSTRAINT uq_controle_org_id;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("controles", "0001_controles_journal"),
        ("niveau3_config", "0011_reallocation_rls_garde_fous"),
        ("financements", "0002_rls_cles_garde_fous"),  # pose uq_projet_org_id
    ]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        *(migrations.RunSQL(activer_rls(t), reverse_sql=desactiver_rls(t)) for t in TABLES),
    ]
