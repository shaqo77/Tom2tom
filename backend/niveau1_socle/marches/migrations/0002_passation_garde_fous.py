from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = (
    "marches_methodepassation",
    "marches_planpassation",
    "marches_lignepassation",
    "marches_etapeavancement",
)

SQL = """
ALTER TABLE marches_methodepassation ADD CONSTRAINT uq_methodepassation_org_id UNIQUE (org_id, id);
ALTER TABLE marches_planpassation ADD CONSTRAINT uq_planpassation_org_id UNIQUE (org_id, id);
ALTER TABLE marches_lignepassation ADD CONSTRAINT uq_lignepassation_org_id UNIQUE (org_id, id);
ALTER TABLE marches_methodepassation ADD CONSTRAINT fk_methode_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE marches_planpassation ADD CONSTRAINT fk_plan_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE marches_lignepassation ADD CONSTRAINT fk_ligne_plan_meme_org
  FOREIGN KEY (org_id, plan_id) REFERENCES marches_planpassation (org_id, id);
ALTER TABLE marches_lignepassation ADD CONSTRAINT fk_ligne_methode_meme_org
  FOREIGN KEY (org_id, methode_id) REFERENCES marches_methodepassation (org_id, id);
ALTER TABLE marches_etapeavancement ADD CONSTRAINT fk_etape_ligne_meme_org
  FOREIGN KEY (org_id, ligne_id) REFERENCES marches_lignepassation (org_id, id);

-- Une seule version d'une méthode en vigueur à une date donnée (fin exclue).
ALTER TABLE marches_methodepassation ADD CONSTRAINT methode_sans_chevauchement
  EXCLUDE USING gist (org_id WITH =, project_id WITH =, code WITH =,
                      daterange(valid_from, valid_to, '[)') WITH &&);

-- Une méthode ne change pas de contenu (on en crée une version) ; seule sa fin se pose, une fois.
CREATE OR REPLACE FUNCTION marches_methode_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une méthode de passation ne se supprime pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.project_id, NEW.code, NEW.version, NEW.devise, NEW.seuil_min, NEW.seuil_max,
      NEW.exige_non_objection, NEW.valid_from) IS DISTINCT FROM
     (OLD.project_id, OLD.code, OLD.version, OLD.devise, OLD.seuil_min, OLD.seuil_max,
      OLD.exige_non_objection, OLD.valid_from) OR NEW.label IS DISTINCT FROM OLD.label THEN
    RAISE EXCEPTION 'Une méthode de passation ne se modifie pas : créez une nouvelle version'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.valid_to IS NOT NULL AND NEW.valid_to IS DISTINCT FROM OLD.valid_to THEN
    RAISE EXCEPTION 'La fin de validité d''une méthode ne se modifie plus'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER marches_methode_garde BEFORE UPDATE OR DELETE ON marches_methodepassation
  FOR EACH ROW EXECUTE FUNCTION marches_methode_garde();

CREATE OR REPLACE FUNCTION marches_rang_statut(s text) RETURNS integer AS $$
  SELECT CASE s WHEN 'prevu' THEN 1 WHEN 'lance' THEN 2 WHEN 'attribue' THEN 3
                WHEN 'signe' THEN 4 ELSE NULL END
$$ LANGUAGE sql IMMUTABLE;

-- Une ligne : jamais supprimée ; son statut avance (prévu, lancé, attribué, signé) ou s'annule
-- AVANT la signature ; signée ou annulée, elle est définitive ; dès qu'elle quitte « prévu », son
-- montant, sa méthode, sa devise, sa référence et son exigence d'avis sont figés.
CREATE OR REPLACE FUNCTION marches_ligne_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une ligne de passation ne se supprime pas : on l''annule'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.statut IN ('signe', 'annule') THEN
    RAISE EXCEPTION 'Une ligne % est définitive', OLD.statut
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.plan_id, NEW.project_id) IS DISTINCT FROM (OLD.plan_id, OLD.project_id) THEN
    RAISE EXCEPTION 'Le plan et le projet d''une ligne ne se modifient pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.statut <> 'annule' AND marches_rang_statut(NEW.statut) < marches_rang_statut(OLD.statut) THEN
    RAISE EXCEPTION 'Le statut d''une ligne ne recule pas (% vers %)', OLD.statut, NEW.statut
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.statut <> 'prevu' AND (NEW.montant_prevu, NEW.methode_id, NEW.devise, NEW.reference,
       NEW.non_objection_requise) IS DISTINCT FROM (OLD.montant_prevu, OLD.methode_id, OLD.devise,
       OLD.reference, OLD.non_objection_requise) THEN
    RAISE EXCEPTION 'Une ligne lancée ne change plus de montant, de méthode, de devise ni d''avis'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER marches_ligne_garde BEFORE UPDATE OR DELETE ON marches_lignepassation
  FOR EACH ROW EXECUTE FUNCTION marches_ligne_garde();

-- L'historique d'avancement est en AJOUT SEUL.
CREATE OR REPLACE FUNCTION marches_ajout_seul() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION '% est en ajout seul', TG_TABLE_NAME
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER marches_ajout_seul BEFORE UPDATE OR DELETE ON marches_etapeavancement
  FOR EACH ROW EXECUTE FUNCTION marches_ajout_seul();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS marches_ajout_seul ON marches_etapeavancement;
DROP FUNCTION IF EXISTS marches_ajout_seul();
DROP TRIGGER IF EXISTS marches_ligne_garde ON marches_lignepassation;
DROP FUNCTION IF EXISTS marches_ligne_garde();
DROP FUNCTION IF EXISTS marches_rang_statut(text);
DROP TRIGGER IF EXISTS marches_methode_garde ON marches_methodepassation;
DROP FUNCTION IF EXISTS marches_methode_garde();
ALTER TABLE marches_methodepassation DROP CONSTRAINT methode_sans_chevauchement;
ALTER TABLE marches_etapeavancement DROP CONSTRAINT fk_etape_ligne_meme_org;
ALTER TABLE marches_lignepassation DROP CONSTRAINT fk_ligne_methode_meme_org;
ALTER TABLE marches_lignepassation DROP CONSTRAINT fk_ligne_plan_meme_org;
ALTER TABLE marches_planpassation DROP CONSTRAINT fk_plan_projet_meme_org;
ALTER TABLE marches_methodepassation DROP CONSTRAINT fk_methode_projet_meme_org;
ALTER TABLE marches_lignepassation DROP CONSTRAINT uq_lignepassation_org_id;
ALTER TABLE marches_planpassation DROP CONSTRAINT uq_planpassation_org_id;
ALTER TABLE marches_methodepassation DROP CONSTRAINT uq_methodepassation_org_id;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("marches", "0001_plan_de_passation"),
        ("controles", "0002_rls_cles_garde_fous"),  # pose uq_projet_org_id via financements
    ]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        *(migrations.RunSQL(activer_rls(t), reverse_sql=desactiver_rls(t)) for t in TABLES),
    ]
