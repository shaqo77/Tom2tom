from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = ("financements_clecofinancement", "financements_versioncle", "financements_partcle")

# Clés étrangères composites (org_id, id) : une clé, une version et ses parts ne visent que des
# objets de leur organisation. La ligne d'écriture référence la version qui l'a produite.
CLES = """
ALTER TABLE financements_clecofinancement ADD CONSTRAINT fk_cle_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE financements_versioncle ADD CONSTRAINT fk_versioncle_porteur_meme_org
  FOREIGN KEY (org_id, rounding_residual_agreement_id) REFERENCES financements_accord (org_id, id);
ALTER TABLE financements_partcle ADD CONSTRAINT fk_partcle_accord_meme_org
  FOREIGN KEY (org_id, accord_id) REFERENCES financements_accord (org_id, id);
ALTER TABLE financements_versioncle ADD CONSTRAINT uq_versioncle_org_id UNIQUE (org_id, id);
ALTER TABLE comptabilite_ligneecriture ADD CONSTRAINT fk_ligne_version_cle
  FOREIGN KEY (org_id, cofunding_key_version_id) REFERENCES financements_versioncle (org_id, id);

-- Deux versions d'une même clé ne se chevauchent pas.
ALTER TABLE financements_versioncle ADD CONSTRAINT versioncle_sans_chevauchement
  EXCLUDE USING gist (org_id WITH =, cle_id WITH =, daterange(valid_from, valid_to, '[)') WITH &&);
"""
CLES_INVERSE = """
ALTER TABLE financements_versioncle DROP CONSTRAINT versioncle_sans_chevauchement;
ALTER TABLE comptabilite_ligneecriture DROP CONSTRAINT fk_ligne_version_cle;
ALTER TABLE financements_versioncle DROP CONSTRAINT uq_versioncle_org_id;
ALTER TABLE financements_partcle DROP CONSTRAINT fk_partcle_accord_meme_org;
ALTER TABLE financements_versioncle DROP CONSTRAINT fk_versioncle_porteur_meme_org;
ALTER TABLE financements_clecofinancement DROP CONSTRAINT fk_cle_projet_meme_org;
"""

# La somme des parts vaut EXACTEMENT 1 : vérifié au COMMIT (la version et ses parts s'insèrent dans
# la même transaction), avec le porteur d'arrondi parmi les parts et tous les accords du projet de
# la clé. Une version utilisée par une ligne d'écriture est figée, hors clôture de sa validité.
GARDE = """
CREATE OR REPLACE FUNCTION financements_version_cle_verifier(cible uuid) RETURNS void AS $$
DECLARE
  v record;
  g record;
BEGIN
  SELECT vc.id, vc.rounding_residual_agreement_id AS porteur, c.project_id
    INTO v
    FROM financements_versioncle vc JOIN financements_clecofinancement c ON c.id = vc.cle_id
   WHERE vc.id = cible;
  IF NOT FOUND THEN
    RETURN;  -- version supprimée dans la même transaction
  END IF;
  SELECT count(*) AS n,
         COALESCE(sum(p.share), 0) AS total,
         bool_or(p.accord_id = v.porteur) AS porteur_present,
         bool_and(a.project_id = v.project_id) AS meme_projet
    INTO g
    FROM financements_partcle p JOIN financements_accord a ON a.id = p.accord_id
   WHERE p.version_id = cible;
  IF g.n = 0 THEN
    RAISE EXCEPTION 'Une version de clé de cofinancement a au moins une part'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF g.total <> 1 THEN
    RAISE EXCEPTION 'Les parts d''une clé doivent sommer exactement à 1 (somme : %)', g.total
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NOT g.porteur_present THEN
    RAISE EXCEPTION 'Le porteur d''arrondi doit être l''un des accords de la clé'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NOT g.meme_projet THEN
    RAISE EXCEPTION 'Tous les accords d''une clé appartiennent au projet de la clé'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION financements_version_cle_assert() RETURNS trigger AS $$
BEGIN
  IF TG_TABLE_NAME = 'financements_partcle' THEN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
      PERFORM financements_version_cle_verifier(OLD.version_id);
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
      PERFORM financements_version_cle_verifier(NEW.version_id);
    END IF;
  ELSE
    PERFORM financements_version_cle_verifier(NEW.id);
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER financements_partcle_somme
  AFTER INSERT OR UPDATE OR DELETE ON financements_partcle
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION financements_version_cle_assert();
CREATE CONSTRAINT TRIGGER financements_versioncle_somme
  AFTER INSERT OR UPDATE ON financements_versioncle
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION financements_version_cle_assert();

CREATE OR REPLACE FUNCTION financements_version_cle_utilisee(cible uuid) RETURNS boolean AS $$
  SELECT EXISTS (SELECT 1 FROM comptabilite_ligneecriture WHERE cofunding_key_version_id = cible);
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION financements_versioncle_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF financements_version_cle_utilisee(OLD.id) THEN
      RAISE EXCEPTION 'Cette version de clé est utilisée par des écritures : elle ne se supprime pas'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF financements_version_cle_utilisee(OLD.id)
     AND (to_jsonb(NEW) - 'valid_to' - 'updated_at' - 'updated_by')
      <> (to_jsonb(OLD) - 'valid_to' - 'updated_at' - 'updated_by') THEN
    RAISE EXCEPTION 'Cette version de clé est utilisée par des écritures : créez-en une nouvelle'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER financements_versioncle_garde
  BEFORE UPDATE OR DELETE ON financements_versioncle
  FOR EACH ROW EXECUTE FUNCTION financements_versioncle_garde();

CREATE OR REPLACE FUNCTION financements_partcle_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') AND financements_version_cle_utilisee(OLD.version_id) THEN
    RAISE EXCEPTION 'Cette version de clé est utilisée par des écritures : créez-en une nouvelle'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') AND financements_version_cle_utilisee(NEW.version_id) THEN
    RAISE EXCEPTION 'Cette version de clé est utilisée par des écritures : créez-en une nouvelle'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER financements_partcle_garde
  BEFORE INSERT OR UPDATE OR DELETE ON financements_partcle
  FOR EACH ROW EXECUTE FUNCTION financements_partcle_garde();
"""
GARDE_INVERSE = """
DROP TRIGGER IF EXISTS financements_partcle_garde ON financements_partcle;
DROP TRIGGER IF EXISTS financements_versioncle_garde ON financements_versioncle;
DROP TRIGGER IF EXISTS financements_versioncle_somme ON financements_versioncle;
DROP TRIGGER IF EXISTS financements_partcle_somme ON financements_partcle;
DROP FUNCTION IF EXISTS financements_partcle_garde();
DROP FUNCTION IF EXISTS financements_versioncle_garde();
DROP FUNCTION IF EXISTS financements_version_cle_utilisee(uuid);
DROP FUNCTION IF EXISTS financements_version_cle_assert();
DROP FUNCTION IF EXISTS financements_version_cle_verifier(uuid);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("financements", "0003_cles_cofinancement"),
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
