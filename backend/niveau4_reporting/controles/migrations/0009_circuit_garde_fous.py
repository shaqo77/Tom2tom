from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = (
    "controles_circuit",
    "controles_etapecircuit",
    "controles_demandevalidation",
    "controles_decisionetape",
)

SQL = """
ALTER TABLE controles_circuit ADD CONSTRAINT uq_circuit_org_id UNIQUE (org_id, id);
ALTER TABLE controles_demandevalidation ADD CONSTRAINT uq_demandevalidation_org_id
  UNIQUE (org_id, id);
ALTER TABLE controles_circuit ADD CONSTRAINT fk_circuit_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE controles_etapecircuit ADD CONSTRAINT fk_etape_circuit_meme_org
  FOREIGN KEY (org_id, circuit_id) REFERENCES controles_circuit (org_id, id);
ALTER TABLE controles_demandevalidation ADD CONSTRAINT fk_demande_circuit_meme_org
  FOREIGN KEY (org_id, circuit_id) REFERENCES controles_circuit (org_id, id);
ALTER TABLE controles_demandevalidation ADD CONSTRAINT fk_demande_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE controles_decisionetape ADD CONSTRAINT fk_decision_etape_demande_meme_org
  FOREIGN KEY (org_id, demande_id) REFERENCES controles_demandevalidation (org_id, id);

-- L'opération requise d'une étape appartient à l'ensemble fermé des habilitations.
ALTER TABLE controles_etapecircuit ADD CONSTRAINT etape_operation_fermee CHECK (
  operation IN ('consulter','saisir','valider','comptabiliser','parametrer','exporter','publier')
);

-- Un seul circuit en vigueur par projet, type d'objet et période (fin exclue).
ALTER TABLE controles_circuit ADD CONSTRAINT circuit_sans_chevauchement
  EXCLUDE USING gist (org_id WITH =, project_id WITH =, objet_type WITH =,
                      daterange(valid_from, valid_to, '[)') WITH &&);

-- Un circuit ne change plus (on en crée un autre) ; seule sa fin peut être posée, une fois.
CREATE OR REPLACE FUNCTION controles_circuit_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un circuit ne se supprime pas' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.project_id, NEW.objet_type, NEW.version, NEW.valid_from)
       IS DISTINCT FROM (OLD.project_id, OLD.objet_type, OLD.version, OLD.valid_from)
     OR (OLD.valid_to IS NOT NULL AND NEW.valid_to IS DISTINCT FROM OLD.valid_to) THEN
    RAISE EXCEPTION 'Un circuit ne se modifie pas : créez une nouvelle version'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER controles_circuit_garde BEFORE UPDATE OR DELETE ON controles_circuit
  FOR EACH ROW EXECUTE FUNCTION controles_circuit_garde();

CREATE TRIGGER controles_ajout_seul BEFORE UPDATE OR DELETE ON controles_etapecircuit
  FOR EACH ROW EXECUTE FUNCTION controles_ajout_seul();
CREATE TRIGGER controles_ajout_seul BEFORE UPDATE OR DELETE ON controles_decisionetape
  FOR EACH ROW EXECUTE FUNCTION controles_ajout_seul();

-- Une demande qui a abouti ou été rejetée est définitive ; son contenu ne change jamais.
CREATE OR REPLACE FUNCTION controles_demande_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une demande de validation ne se supprime pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.statut <> 'en_cours' THEN
    RAISE EXCEPTION 'Une demande % est définitive', OLD.statut
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.circuit_id, NEW.project_id, NEW.objet_type, NEW.objet_id, NEW.date_effet,
      NEW.demandeur_id) IS DISTINCT FROM
     (OLD.circuit_id, OLD.project_id, OLD.objet_type, OLD.objet_id, OLD.date_effet,
      OLD.demandeur_id) OR NEW.contexte IS DISTINCT FROM OLD.contexte THEN
    RAISE EXCEPTION 'Le contenu d''une demande de validation ne se modifie pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER controles_demande_garde BEFORE UPDATE OR DELETE ON controles_demandevalidation
  FOR EACH ROW EXECUTE FUNCTION controles_demande_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS controles_demande_garde ON controles_demandevalidation;
DROP FUNCTION IF EXISTS controles_demande_garde();
DROP TRIGGER IF EXISTS controles_ajout_seul ON controles_decisionetape;
DROP TRIGGER IF EXISTS controles_ajout_seul ON controles_etapecircuit;
DROP TRIGGER IF EXISTS controles_circuit_garde ON controles_circuit;
DROP FUNCTION IF EXISTS controles_circuit_garde();
ALTER TABLE controles_circuit DROP CONSTRAINT circuit_sans_chevauchement;
ALTER TABLE controles_etapecircuit DROP CONSTRAINT etape_operation_fermee;
ALTER TABLE controles_decisionetape DROP CONSTRAINT fk_decision_etape_demande_meme_org;
ALTER TABLE controles_demandevalidation DROP CONSTRAINT fk_demande_projet_meme_org;
ALTER TABLE controles_demandevalidation DROP CONSTRAINT fk_demande_circuit_meme_org;
ALTER TABLE controles_etapecircuit DROP CONSTRAINT fk_etape_circuit_meme_org;
ALTER TABLE controles_circuit DROP CONSTRAINT fk_circuit_projet_meme_org;
ALTER TABLE controles_demandevalidation DROP CONSTRAINT uq_demandevalidation_org_id;
ALTER TABLE controles_circuit DROP CONSTRAINT uq_circuit_org_id;
"""


class Migration(migrations.Migration):
    dependencies = [("controles", "0008_circuit_de_validation")]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        *(migrations.RunSQL(activer_rls(t), reverse_sql=desactiver_rls(t)) for t in TABLES),
    ]
