from django.db import migrations

# Les paramètres d'une règle de pièces font partie de son contenu : une fois le contrôle validé,
# ils ne changent plus (on crée une version). Ce sont aussi un objet JSON.
SQL = """
ALTER TABLE controles_controle ADD CONSTRAINT controle_parametres_objet
  CHECK (jsonb_typeof(parametres) = 'object');
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
       OR NEW.parametres IS DISTINCT FROM OLD.parametres
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
"""
SQL_INVERSE = """
ALTER TABLE controles_controle DROP CONSTRAINT controle_parametres_objet;
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
"""


class Migration(migrations.Migration):
    dependencies = [("controles", "0003_parametres_des_regles")]

    operations = [migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE)]
