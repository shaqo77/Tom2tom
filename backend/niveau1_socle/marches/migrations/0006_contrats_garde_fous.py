from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = ("marches_contrat", "marches_avenantcontrat", "marches_garantie")

SQL = """
ALTER TABLE marches_contrat ADD CONSTRAINT uq_contrat_org_id UNIQUE (org_id, id);
ALTER TABLE marches_contrat ADD CONSTRAINT fk_contrat_ligne_meme_org
  FOREIGN KEY (org_id, ligne_id) REFERENCES marches_lignepassation (org_id, id);
ALTER TABLE marches_contrat ADD CONSTRAINT fk_contrat_tiers_meme_org
  FOREIGN KEY (org_id, tiers_id) REFERENCES referentiels_tiers (org_id, id);
ALTER TABLE marches_avenantcontrat ADD CONSTRAINT fk_avenant_contrat_meme_org
  FOREIGN KEY (org_id, contrat_id) REFERENCES marches_contrat (org_id, id);
ALTER TABLE marches_avenantcontrat ADD CONSTRAINT fk_avenant_avis_meme_org
  FOREIGN KEY (org_id, avis_id) REFERENCES marches_avisnonobjection (org_id, id);
ALTER TABLE marches_garantie ADD CONSTRAINT fk_garantie_contrat_meme_org
  FOREIGN KEY (org_id, contrat_id) REFERENCES marches_contrat (org_id, id);

-- Un contrat : en ajout seul. Il naît d'une ligne attribuée ou signée, dans sa devise et son
-- projet, et, si le marché est soumis à non-objection, avec un avis suffisant.
CREATE OR REPLACE FUNCTION marches_contrat_naissance() RETURNS trigger AS $$
DECLARE
  l marches_lignepassation%ROWTYPE;
BEGIN
  SELECT * INTO l FROM marches_lignepassation WHERE id = NEW.ligne_id;
  IF NOT FOUND OR l.project_id <> NEW.project_id OR l.devise <> NEW.devise THEN
    RAISE EXCEPTION 'Le contrat doit suivre le projet et la devise de sa ligne de passation'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF l.statut NOT IN ('attribue', 'signe') THEN
    RAISE EXCEPTION 'Un contrat ne se conclut que sur un marché attribué (ligne %)', l.reference
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NOT marches_avis_suffisant(l.id) THEN
    RAISE EXCEPTION 'Contrat refusé : l''avis de non-objection du marché % n''est pas obtenu',
      l.reference USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER marches_contrat_naissance BEFORE INSERT ON marches_contrat
  FOR EACH ROW EXECUTE FUNCTION marches_contrat_naissance();
CREATE TRIGGER marches_ajout_seul BEFORE UPDATE OR DELETE ON marches_contrat
  FOR EACH ROW EXECUTE FUNCTION marches_ajout_seul();

-- Un avenant : en ajout seul, numéroté SANS TROU, jamais antérieur au précédent ni à la signature ;
-- sur un marché soumis, il s'appuie sur un avis obtenu d'objet « avenant » de la même ligne.
CREATE OR REPLACE FUNCTION marches_avenant_naissance() RETURNS trigger AS $$
DECLARE
  c marches_contrat%ROWTYPE;
  l marches_lignepassation%ROWTYPE;
  dernier integer;
  derniere_date date;
  a marches_avisnonobjection%ROWTYPE;
BEGIN
  SELECT * INTO c FROM marches_contrat WHERE id = NEW.contrat_id;
  IF NOT FOUND OR c.project_id <> NEW.project_id THEN
    RAISE EXCEPTION 'L''avenant doit suivre le projet de son contrat'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT COALESCE(max(numero), 0) INTO dernier FROM marches_avenantcontrat WHERE contrat_id = c.id;
  IF NEW.numero <> dernier + 1 THEN
    RAISE EXCEPTION 'Numérotation des avenants sans trou : attendu %, reçu %', dernier + 1, NEW.numero
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT max(date_effet) INTO derniere_date FROM marches_avenantcontrat WHERE contrat_id = c.id;
  IF NEW.date_effet < GREATEST(c.date_signature, COALESCE(derniere_date, c.date_signature)) THEN
    RAISE EXCEPTION 'Un avenant ne prend pas effet avant la signature ni avant l''avenant précédent'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.date_fin < c.date_debut THEN
    RAISE EXCEPTION 'La nouvelle date de fin précède le début du contrat'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT * INTO l FROM marches_lignepassation WHERE id = c.ligne_id;
  IF l.non_objection_requise THEN
    SELECT * INTO a FROM marches_avisnonobjection WHERE id = NEW.avis_id;
    IF NOT FOUND OR a.statut <> 'obtenu' OR a.objet <> 'avenant' OR a.ligne_id <> l.id THEN
      RAISE EXCEPTION 'Avenant refusé : un avis de non-objection « avenant » obtenu est requis'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER marches_avenant_naissance BEFORE INSERT ON marches_avenantcontrat
  FOR EACH ROW EXECUTE FUNCTION marches_avenant_naissance();
CREATE TRIGGER marches_ajout_seul BEFORE UPDATE OR DELETE ON marches_avenantcontrat
  FOR EACH ROW EXECUTE FUNCTION marches_ajout_seul();

-- Une garantie : jamais supprimée ; naît active, dans la devise et le projet de son contrat ;
-- seul son statut avance (libérée ou appelée), une fois, avec sa date de clôture.
CREATE OR REPLACE FUNCTION marches_garantie_garde() RETURNS trigger AS $$
DECLARE
  c marches_contrat%ROWTYPE;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une garantie ne se supprime pas : on la libère'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'INSERT' THEN
    SELECT * INTO c FROM marches_contrat WHERE id = NEW.contrat_id;
    IF NOT FOUND OR c.project_id <> NEW.project_id OR c.devise <> NEW.devise THEN
      RAISE EXCEPTION 'La garantie doit suivre le projet et la devise de son contrat'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.statut <> 'active' THEN
      RAISE EXCEPTION 'Une garantie naît active' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.statut <> 'active' THEN
    RAISE EXCEPTION 'Une garantie % est définitive', OLD.statut
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (to_jsonb(NEW) - 'statut' - 'date_cloture' - 'note_cloture' - 'updated_at' - 'updated_by')
     <> (to_jsonb(OLD) - 'statut' - 'date_cloture' - 'note_cloture' - 'updated_at' - 'updated_by')
     OR NEW.date_cloture < OLD.date_emission THEN
    RAISE EXCEPTION 'Une garantie ne change que par sa clôture'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER marches_garantie_garde BEFORE INSERT OR UPDATE OR DELETE ON marches_garantie
  FOR EACH ROW EXECUTE FUNCTION marches_garantie_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS marches_garantie_garde ON marches_garantie;
DROP FUNCTION IF EXISTS marches_garantie_garde();
DROP TRIGGER IF EXISTS marches_ajout_seul ON marches_avenantcontrat;
DROP TRIGGER IF EXISTS marches_avenant_naissance ON marches_avenantcontrat;
DROP FUNCTION IF EXISTS marches_avenant_naissance();
DROP TRIGGER IF EXISTS marches_ajout_seul ON marches_contrat;
DROP TRIGGER IF EXISTS marches_contrat_naissance ON marches_contrat;
DROP FUNCTION IF EXISTS marches_contrat_naissance();
ALTER TABLE marches_garantie DROP CONSTRAINT fk_garantie_contrat_meme_org;
ALTER TABLE marches_avenantcontrat DROP CONSTRAINT fk_avenant_avis_meme_org;
ALTER TABLE marches_avenantcontrat DROP CONSTRAINT fk_avenant_contrat_meme_org;
ALTER TABLE marches_contrat DROP CONSTRAINT fk_contrat_tiers_meme_org;
ALTER TABLE marches_contrat DROP CONSTRAINT fk_contrat_ligne_meme_org;
ALTER TABLE marches_contrat DROP CONSTRAINT uq_contrat_org_id;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("marches", "0005_contrat_avenantcontrat_garantie_and_more"),
        ("avances", "0002_rls_cles_garde_fous"),  # pose uq_tiers_org_id sur referentiels_tiers
    ]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        *(migrations.RunSQL(activer_rls(t), reverse_sql=desactiver_rls(t)) for t in TABLES),
    ]
