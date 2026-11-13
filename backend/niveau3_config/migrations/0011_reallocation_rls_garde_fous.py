from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLE = "niveau3_config_reallocation"

# Clés composites (org_id, id), cohérence de l'accord, et événement non modifiable une fois décidé.
CLES = """
ALTER TABLE niveau3_config_reallocation ADD CONSTRAINT fk_realloc_accord_meme_org
  FOREIGN KEY (org_id, accord_id) REFERENCES financements_accord (org_id, id);
ALTER TABLE niveau3_config_reallocation ADD CONSTRAINT fk_realloc_source_meme_org
  FOREIGN KEY (org_id, source_id) REFERENCES financements_categorie (org_id, id);
ALTER TABLE niveau3_config_reallocation ADD CONSTRAINT fk_realloc_cible_meme_org
  FOREIGN KEY (org_id, cible_id) REFERENCES financements_categorie (org_id, id);
ALTER TABLE niveau3_config_reallocation ADD CONSTRAINT fk_realloc_profil_meme_org
  FOREIGN KEY (org_id, profil_cree_id) REFERENCES niveau3_config_profildecaissement (org_id, id);

-- Les deux catégories appartiennent à l'accord de la réallocation, et le profil créé aussi.
CREATE OR REPLACE FUNCTION niveau3_reallocation_garde() RETURNS trigger AS $$
DECLARE
  s uuid; c uuid; p uuid;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une réallocation ne se supprime pas : c''est un événement tracé'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.status <> 'requested' THEN
    RAISE EXCEPTION 'Une réallocation % ne se modifie plus', OLD.status
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'UPDATE' AND (NEW.accord_id, NEW.source_id, NEW.cible_id, NEW.montant, NEW.date_effet,
       NEW.demandeur, NEW.motif) IS DISTINCT FROM (OLD.accord_id, OLD.source_id, OLD.cible_id,
       OLD.montant, OLD.date_effet, OLD.demandeur, OLD.motif) THEN
    RAISE EXCEPTION 'La demande de réallocation ne se modifie pas : décidez-la, ou refaites-en une'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT accord_id INTO s FROM financements_categorie WHERE id = NEW.source_id;
  SELECT accord_id INTO c FROM financements_categorie WHERE id = NEW.cible_id;
  IF s IS DISTINCT FROM NEW.accord_id OR c IS DISTINCT FROM NEW.accord_id THEN
    RAISE EXCEPTION 'Les catégories d''une réallocation appartiennent à son accord'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.profil_cree_id IS NOT NULL THEN
    SELECT accord_id INTO p FROM niveau3_config_profildecaissement WHERE id = NEW.profil_cree_id;
    IF p IS DISTINCT FROM NEW.accord_id THEN
      RAISE EXCEPTION 'La version créée par une réallocation est un profil de son accord'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER niveau3_reallocation_garde
  BEFORE INSERT OR UPDATE OR DELETE ON niveau3_config_reallocation
  FOR EACH ROW EXECUTE FUNCTION niveau3_reallocation_garde();
"""
CLES_INVERSE = """
DROP TRIGGER IF EXISTS niveau3_reallocation_garde ON niveau3_config_reallocation;
DROP FUNCTION IF EXISTS niveau3_reallocation_garde();
ALTER TABLE niveau3_config_reallocation DROP CONSTRAINT fk_realloc_profil_meme_org;
ALTER TABLE niveau3_config_reallocation DROP CONSTRAINT fk_realloc_cible_meme_org;
ALTER TABLE niveau3_config_reallocation DROP CONSTRAINT fk_realloc_source_meme_org;
ALTER TABLE niveau3_config_reallocation DROP CONSTRAINT fk_realloc_accord_meme_org;
"""




class Migration(migrations.Migration):
    dependencies = [("niveau3_config", "0010_reallocation")]

    operations = [
        migrations.RunSQL(CLES, reverse_sql=CLES_INVERSE),
        migrations.RunSQL(activer_rls(TABLE), reverse_sql=desactiver_rls(TABLE)),
    ]
