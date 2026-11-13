from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = ("niveau2_profils_profilbailleur", "niveau2_profils_elementprofil")

SQL = """
ALTER TABLE niveau2_profils_profilbailleur ADD CONSTRAINT uq_profil_bailleur_org_id
  UNIQUE (org_id, id);
ALTER TABLE niveau2_profils_profilbailleur ADD CONSTRAINT fk_profil_bailleur_meme_org
  FOREIGN KEY (org_id, bailleur_id) REFERENCES financements_bailleur (org_id, id);
ALTER TABLE niveau2_profils_elementprofil ADD CONSTRAINT fk_element_profil_meme_org
  FOREIGN KEY (org_id, profil_id) REFERENCES niveau2_profils_profilbailleur (org_id, id);
-- L'origine bibliothèque d'une exigence est un profil de la MÊME organisation.
ALTER TABLE niveau3_config_exigence ADD CONSTRAINT fk_exigence_profil_bailleur_meme_org
  FOREIGN KEY (org_id, donor_profile_id) REFERENCES niveau2_profils_profilbailleur (org_id, id);

ALTER TABLE niveau2_profils_elementprofil ADD CONSTRAINT element_profil_objets_json CHECK (
  jsonb_typeof(contenu) = 'object'
  AND (exigence IS NULL OR jsonb_typeof(exigence) = 'object')
);

-- Une seule proposition en attente par (projet, code, profil) : un double import concurrent ne
-- crée pas deux exigences.
CREATE UNIQUE INDEX uq_exigence_importee_en_attente
  ON niveau3_config_exigence (org_id, project_id, code, donor_profile_id)
  WHERE status = 'proposed' AND donor_profile_id IS NOT NULL;

-- Un profil publié ne change plus et ne se supprime pas : on en publie une version.
CREATE OR REPLACE FUNCTION niveau2_profil_bailleur_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'Un profil publié ne se supprime pas'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status <> 'draft' THEN
    RAISE EXCEPTION 'Un profil publié ne se modifie pas : publiez une nouvelle version'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER niveau2_profil_bailleur_garde
  BEFORE UPDATE OR DELETE ON niveau2_profils_profilbailleur
  FOR EACH ROW EXECUTE FUNCTION niveau2_profil_bailleur_garde();

-- Les éléments ne bougent que tant que le profil est un brouillon.
CREATE OR REPLACE FUNCTION niveau2_element_profil_garde() RETURNS trigger AS $$
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
    SELECT status INTO statut FROM niveau2_profils_profilbailleur WHERE id = parent;
    IF statut IS NOT NULL AND statut <> 'draft' THEN
      RAISE EXCEPTION 'Le profil est publié : ses éléments ne se modifient plus'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END LOOP;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER niveau2_element_profil_garde
  BEFORE INSERT OR UPDATE OR DELETE ON niveau2_profils_elementprofil
  FOR EACH ROW EXECUTE FUNCTION niveau2_element_profil_garde();

-- LA règle absolue : une exigence qui vient d'un profil naît `proposed`, d'un profil publié.
-- Aucun chemin de code, ni SQL direct, ne la crée autrement.
CREATE OR REPLACE FUNCTION niveau2_exigence_importee_garde() RETURNS trigger AS $$
DECLARE
  statut text;
BEGIN
  IF NEW.donor_profile_id IS NOT NULL THEN
    IF NEW.status <> 'proposed' THEN
      RAISE EXCEPTION 'Une exigence issue d''un profil de bailleur naît « proposed », jamais %',
        NEW.status USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    SELECT status INTO statut FROM niveau2_profils_profilbailleur WHERE id = NEW.donor_profile_id;
    IF statut IS DISTINCT FROM 'published' THEN
      RAISE EXCEPTION 'Seul un profil publié se met à disposition d''un projet'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER niveau2_exigence_importee_garde
  BEFORE INSERT ON niveau3_config_exigence
  FOR EACH ROW EXECUTE FUNCTION niveau2_exigence_importee_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS niveau2_exigence_importee_garde ON niveau3_config_exigence;
DROP FUNCTION IF EXISTS niveau2_exigence_importee_garde();
DROP TRIGGER IF EXISTS niveau2_element_profil_garde ON niveau2_profils_elementprofil;
DROP FUNCTION IF EXISTS niveau2_element_profil_garde();
DROP TRIGGER IF EXISTS niveau2_profil_bailleur_garde ON niveau2_profils_profilbailleur;
DROP FUNCTION IF EXISTS niveau2_profil_bailleur_garde();
DROP INDEX IF EXISTS uq_exigence_importee_en_attente;
ALTER TABLE niveau2_profils_elementprofil DROP CONSTRAINT element_profil_objets_json;
ALTER TABLE niveau3_config_exigence DROP CONSTRAINT fk_exigence_profil_bailleur_meme_org;
ALTER TABLE niveau2_profils_elementprofil DROP CONSTRAINT fk_element_profil_meme_org;
ALTER TABLE niveau2_profils_profilbailleur DROP CONSTRAINT fk_profil_bailleur_meme_org;
ALTER TABLE niveau2_profils_profilbailleur DROP CONSTRAINT uq_profil_bailleur_org_id;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("niveau2_profils", "0001_bibliotheque_profils"),
        ("niveau3_config", "0011_reallocation_rls_garde_fous"),
    ]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        *(
            migrations.RunSQL(activer_rls(t), reverse_sql=desactiver_rls(t))
            for t in TABLES
        ),
    ]
