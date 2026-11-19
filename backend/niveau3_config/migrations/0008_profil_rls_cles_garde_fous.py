from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = (
    "niveau3_config_profildecaissement",
    "niveau3_config_methodedecaissement",
    "niveau3_config_reglecomptedesigne",
    "niveau3_config_reglefinancementcategorie",
)

# Clés étrangères composites (org_id, id) : un profil ne vise que l'accord, le projet, le compte et
# les catégories de son organisation ; ses règles, que son propre profil. Et la cohérence que seule
# la base peut tenir : les catégories et le compte d'un profil appartiennent à l'accord du profil.
CLES = """
ALTER TABLE financements_categorie ADD CONSTRAINT uq_categorie_org_id UNIQUE (org_id, id);
ALTER TABLE niveau3_config_profildecaissement ADD CONSTRAINT uq_profil_org_id UNIQUE (org_id, id);
ALTER TABLE niveau3_config_profildecaissement ADD CONSTRAINT fk_profil_accord_meme_org
  FOREIGN KEY (org_id, accord_id) REFERENCES financements_accord (org_id, id);
ALTER TABLE niveau3_config_profildecaissement ADD CONSTRAINT fk_profil_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE niveau3_config_methodedecaissement ADD CONSTRAINT fk_methode_profil_meme_org
  FOREIGN KEY (org_id, profil_id) REFERENCES niveau3_config_profildecaissement (org_id, id);
ALTER TABLE niveau3_config_reglecomptedesigne ADD CONSTRAINT fk_regle_compte_profil_meme_org
  FOREIGN KEY (org_id, profil_id) REFERENCES niveau3_config_profildecaissement (org_id, id);
ALTER TABLE niveau3_config_reglecomptedesigne ADD CONSTRAINT fk_regle_compte_compte_meme_org
  FOREIGN KEY (org_id, bank_account_id) REFERENCES financements_comptebancaire (org_id, id);
ALTER TABLE niveau3_config_reglefinancementcategorie ADD CONSTRAINT fk_regle_profil_meme_org
  FOREIGN KEY (org_id, profil_id) REFERENCES niveau3_config_profildecaissement (org_id, id);
ALTER TABLE niveau3_config_reglefinancementcategorie ADD CONSTRAINT fk_regle_categorie_meme_org
  FOREIGN KEY (org_id, category_id) REFERENCES financements_categorie (org_id, id);
"""
CLES_INVERSE = """
ALTER TABLE niveau3_config_reglefinancementcategorie DROP CONSTRAINT fk_regle_categorie_meme_org;
ALTER TABLE niveau3_config_reglefinancementcategorie DROP CONSTRAINT fk_regle_profil_meme_org;
ALTER TABLE niveau3_config_reglecomptedesigne DROP CONSTRAINT fk_regle_compte_compte_meme_org;
ALTER TABLE niveau3_config_reglecomptedesigne DROP CONSTRAINT fk_regle_compte_profil_meme_org;
ALTER TABLE niveau3_config_methodedecaissement DROP CONSTRAINT fk_methode_profil_meme_org;
ALTER TABLE niveau3_config_profildecaissement DROP CONSTRAINT fk_profil_projet_meme_org;
ALTER TABLE niveau3_config_profildecaissement DROP CONSTRAINT fk_profil_accord_meme_org;
ALTER TABLE niveau3_config_profildecaissement DROP CONSTRAINT uq_profil_org_id;
ALTER TABLE financements_categorie DROP CONSTRAINT uq_categorie_org_id;
"""

COHERENCE = """
CREATE OR REPLACE FUNCTION niveau3_profil_coherence() RETURNS trigger AS $$
DECLARE
  p record;
  c record;
BEGIN
  SELECT accord_id, project_id INTO p FROM niveau3_config_profildecaissement WHERE id = NEW.profil_id;
  IF TG_TABLE_NAME = 'niveau3_config_reglefinancementcategorie' THEN
    SELECT accord_id INTO c FROM financements_categorie WHERE id = NEW.category_id;
    IF c.accord_id IS DISTINCT FROM p.accord_id THEN
      RAISE EXCEPTION 'La catégorie d''une règle de financement appartient à l''accord du profil'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  ELSIF TG_TABLE_NAME = 'niveau3_config_reglecomptedesigne' THEN
    SELECT accord_id, project_id INTO c FROM financements_comptebancaire WHERE id = NEW.bank_account_id;
    IF c.project_id IS DISTINCT FROM p.project_id
       OR (c.accord_id IS NOT NULL AND c.accord_id <> p.accord_id) THEN
      RAISE EXCEPTION 'Le compte désigné d''un profil est du même projet, sans autre accord que celui du profil'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER niveau3_regle_categorie_coherence
  BEFORE INSERT OR UPDATE ON niveau3_config_reglefinancementcategorie
  FOR EACH ROW EXECUTE FUNCTION niveau3_profil_coherence();
CREATE TRIGGER niveau3_regle_compte_coherence
  BEFORE INSERT OR UPDATE ON niveau3_config_reglecomptedesigne
  FOR EACH ROW EXECUTE FUNCTION niveau3_profil_coherence();

CREATE OR REPLACE FUNCTION niveau3_profil_projet_coherence() RETURNS trigger AS $$
DECLARE
  projet_accord uuid;
BEGIN
  SELECT project_id INTO projet_accord FROM financements_accord WHERE id = NEW.accord_id;
  IF projet_accord IS DISTINCT FROM NEW.project_id THEN
    RAISE EXCEPTION 'Le profil et son accord appartiennent au même projet'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER niveau3_profil_projet_coherence
  BEFORE INSERT OR UPDATE ON niveau3_config_profildecaissement
  FOR EACH ROW EXECUTE FUNCTION niveau3_profil_projet_coherence();
"""
COHERENCE_INVERSE = """
DROP TRIGGER IF EXISTS niveau3_profil_projet_coherence ON niveau3_config_profildecaissement;
DROP TRIGGER IF EXISTS niveau3_regle_compte_coherence ON niveau3_config_reglecomptedesigne;
DROP TRIGGER IF EXISTS niveau3_regle_categorie_coherence ON niveau3_config_reglefinancementcategorie;
DROP FUNCTION IF EXISTS niveau3_profil_projet_coherence();
DROP FUNCTION IF EXISTS niveau3_profil_coherence();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("niveau3_config", "0007_profil_decaissement"),
        ("financements", "0004_cles_garde_fous"),
        ("rapprochement", "0002_rls_cles_garde_fous"),
        ("organisations", "0004_verrou_sur_grand_livre"),
    ]

    operations = [
        *(
            migrations.RunSQL(activer_rls(table), reverse_sql=desactiver_rls(table))
            for table in TABLES
        ),
        migrations.RunSQL(CLES, reverse_sql=CLES_INVERSE),
        migrations.RunSQL(COHERENCE, reverse_sql=COHERENCE_INVERSE),
    ]
