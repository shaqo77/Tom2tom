from django.db import migrations

# L5-T04 : un seul profil actif (et une seule exigence active) à la fois pour une même période,
# garanti par la base ; une configuration approuvée ne se modifie plus ; les statuts ne reculent pas.
SQL = """
ALTER TABLE niveau3_config_profildecaissement ADD CONSTRAINT profil_actif_sans_chevauchement
  EXCLUDE USING gist (org_id WITH =, accord_id WITH =,
                      daterange(valid_from, valid_to, '[)') WITH &&)
  WHERE (status = 'active');

ALTER TABLE niveau3_config_exigence ADD CONSTRAINT exigence_active_sans_chevauchement
  EXCLUDE USING gist (org_id WITH =, project_id WITH =, code WITH =,
                      daterange(valid_from, valid_to, '[)') WITH &&)
  WHERE (status = 'active');

-- Rang d'un statut : l'ordre ne se remonte jamais ; rejeté et remplacé sont définitifs.
CREATE OR REPLACE FUNCTION niveau3_rang_statut(statut text) RETURNS int AS $$
  SELECT CASE statut
    WHEN 'draft' THEN 0 WHEN 'proposed' THEN 0
    WHEN 'validated' THEN 1 WHEN 'active' THEN 2
    ELSE 3 END;
$$ LANGUAGE sql IMMUTABLE;

CREATE OR REPLACE FUNCTION niveau3_profil_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Un profil % ne se supprime pas', OLD.status
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status IN ('superseded', 'rejected') AND NEW.status IS DISTINCT FROM OLD.status THEN
    RAISE EXCEPTION 'Un profil % est définitif', OLD.status
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.status <> 'draft' THEN
    IF NEW.status IN ('draft') OR (OLD.status = 'active' AND NEW.status = 'validated') THEN
      RAISE EXCEPTION 'Le statut d''un profil ne recule pas (% vers %)', OLD.status, NEW.status
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.status = 'superseded' AND OLD.status <> 'active' THEN
      RAISE EXCEPTION 'Seul un profil actif peut être remplacé'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF (NEW.org_id, NEW.project_id, NEW.accord_id, NEW.version, NEW.valid_from, NEW.regime)
         IS DISTINCT FROM
       (OLD.org_id, OLD.project_id, OLD.accord_id, OLD.version, OLD.valid_from, OLD.regime)
       OR NEW.effectiveness_date IS DISTINCT FROM OLD.effectiveness_date
       OR NEW.eligibility_date IS DISTINCT FROM OLD.eligibility_date
       OR NEW.closing_date IS DISTINCT FROM OLD.closing_date
       OR NEW.disbursement_deadline IS DISTINCT FROM OLD.disbursement_deadline
       OR NEW.requirement_id IS DISTINCT FROM OLD.requirement_id
       OR (OLD.validated_by IS NOT NULL AND NEW.validated_by IS DISTINCT FROM OLD.validated_by)
       OR (OLD.validated_at IS NOT NULL AND NEW.validated_at IS DISTINCT FROM OLD.validated_at)
    THEN
      RAISE EXCEPTION 'Un profil approuvé ne se modifie pas : créez une nouvelle version'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    -- Seule la fin de validité peut être posée, une fois, pour laisser la place à la version suivante.
    IF NEW.valid_to IS DISTINCT FROM OLD.valid_to AND OLD.valid_to IS NOT NULL THEN
      RAISE EXCEPTION 'La fin de validité d''un profil ne se modifie plus'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.valid_to IS DISTINCT FROM OLD.valid_to AND OLD.status <> 'active' THEN
      RAISE EXCEPTION 'Seul un profil actif reçoit une fin de validité'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER niveau3_profil_garde
  BEFORE UPDATE OR DELETE ON niveau3_config_profildecaissement
  FOR EACH ROW EXECUTE FUNCTION niveau3_profil_garde();

-- Méthodes, comptes désignés et règles de taux : modifiables tant que le profil est un brouillon.
CREATE OR REPLACE FUNCTION niveau3_profil_enfant_garde() RETURNS trigger AS $$
DECLARE
  parent uuid;
  statut text;
BEGIN
  FOR parent IN
    SELECT DISTINCT p FROM (VALUES
      (CASE WHEN TG_OP <> 'INSERT' THEN OLD.profil_id END),
      (CASE WHEN TG_OP <> 'DELETE' THEN NEW.profil_id END)) AS v(p)
    WHERE p IS NOT NULL
  LOOP
    SELECT status INTO statut FROM niveau3_config_profildecaissement WHERE id = parent;
    IF statut IS NOT NULL AND statut <> 'draft' THEN
      RAISE EXCEPTION 'Le profil est % : ses méthodes, comptes et règles ne se modifient plus', statut
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END LOOP;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER niveau3_profil_enfant_garde
  BEFORE INSERT OR UPDATE OR DELETE ON niveau3_config_methodedecaissement
  FOR EACH ROW EXECUTE FUNCTION niveau3_profil_enfant_garde();
CREATE TRIGGER niveau3_profil_enfant_garde
  BEFORE INSERT OR UPDATE OR DELETE ON niveau3_config_reglecomptedesigne
  FOR EACH ROW EXECUTE FUNCTION niveau3_profil_enfant_garde();
CREATE TRIGGER niveau3_profil_enfant_garde
  BEFORE INSERT OR UPDATE OR DELETE ON niveau3_config_reglefinancementcategorie
  FOR EACH ROW EXECUTE FUNCTION niveau3_profil_enfant_garde();

-- Exigence : le statut ne recule pas ; une exigence engagée garde son contenu.
CREATE OR REPLACE FUNCTION niveau3_exigence_transition_garde() RETURNS trigger AS $$
BEGIN
  IF OLD.status IN ('superseded', 'rejected') AND NEW.status IS DISTINCT FROM OLD.status THEN
    RAISE EXCEPTION 'Une exigence % est définitive', OLD.status
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF niveau3_rang_statut(NEW.status) < niveau3_rang_statut(OLD.status) THEN
    RAISE EXCEPTION 'Le statut d''une exigence ne recule pas (% vers %)', OLD.status, NEW.status
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.status IN ('validated', 'active') THEN
    IF NEW.code IS DISTINCT FROM OLD.code OR NEW.version IS DISTINCT FROM OLD.version
       OR NEW.project_id IS DISTINCT FROM OLD.project_id
       OR NEW.document_id IS DISTINCT FROM OLD.document_id
       OR NEW.citation IS DISTINCT FROM OLD.citation OR NEW.rule IS DISTINCT FROM OLD.rule
       OR NEW.subject IS DISTINCT FROM OLD.subject
       OR NEW.obligation IS DISTINCT FROM OLD.obligation
       OR NEW.periodicity IS DISTINCT FROM OLD.periodicity
       OR NEW.due_offset_days IS DISTINCT FROM OLD.due_offset_days
       OR NEW.condition_expr IS DISTINCT FROM OLD.condition_expr
       OR NEW.valid_from IS DISTINCT FROM OLD.valid_from
       OR NEW.validated_by IS DISTINCT FROM OLD.validated_by
       OR NEW.validated_at IS DISTINCT FROM OLD.validated_at
    THEN
      RAISE EXCEPTION 'Une exigence validée ne se modifie pas : créez une nouvelle version'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.valid_to IS DISTINCT FROM OLD.valid_to AND OLD.valid_to IS NOT NULL THEN
      RAISE EXCEPTION 'La fin de validité d''une exigence ne se modifie plus'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER niveau3_exigence_transition_garde
  BEFORE UPDATE ON niveau3_config_exigence
  FOR EACH ROW EXECUTE FUNCTION niveau3_exigence_transition_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS niveau3_exigence_transition_garde ON niveau3_config_exigence;
DROP FUNCTION IF EXISTS niveau3_exigence_transition_garde();
DROP TRIGGER IF EXISTS niveau3_profil_enfant_garde ON niveau3_config_reglefinancementcategorie;
DROP TRIGGER IF EXISTS niveau3_profil_enfant_garde ON niveau3_config_reglecomptedesigne;
DROP TRIGGER IF EXISTS niveau3_profil_enfant_garde ON niveau3_config_methodedecaissement;
DROP FUNCTION IF EXISTS niveau3_profil_enfant_garde();
DROP TRIGGER IF EXISTS niveau3_profil_garde ON niveau3_config_profildecaissement;
DROP FUNCTION IF EXISTS niveau3_profil_garde();
DROP FUNCTION IF EXISTS niveau3_rang_statut(text);
ALTER TABLE niveau3_config_exigence DROP CONSTRAINT exigence_active_sans_chevauchement;
ALTER TABLE niveau3_config_profildecaissement DROP CONSTRAINT profil_actif_sans_chevauchement;
"""


class Migration(migrations.Migration):
    dependencies = [("niveau3_config", "0008_profil_rls_cles_garde_fous")]

    operations = [migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE)]
