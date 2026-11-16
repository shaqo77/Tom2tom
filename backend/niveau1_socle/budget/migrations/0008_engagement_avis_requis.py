from django.db import migrations

SQL = """
ALTER TABLE budget_engagement ADD CONSTRAINT fk_engagement_ligne_meme_org
  FOREIGN KEY (org_id, ligne_passation_id) REFERENCES marches_lignepassation (org_id, id);

-- Un engagement rattaché à un marché soumis à non-objection ne naît pas sans avis obtenu, ni sur
-- une ligne annulée ou d'un autre projet. La règle tient en base, pas seulement dans le service.
-- (Après la naissance, `budget_engagement_garde` interdit déjà de changer le rattachement.)
CREATE OR REPLACE FUNCTION budget_engagement_avis() RETURNS trigger AS $$
DECLARE
  l marches_lignepassation%ROWTYPE;
BEGIN
  IF NEW.ligne_passation_id IS NULL THEN
    RETURN NEW;
  END IF;
  SELECT * INTO l FROM marches_lignepassation WHERE id = NEW.ligne_passation_id;
  IF NOT FOUND OR l.project_id <> NEW.project_id THEN
    RAISE EXCEPTION 'Le marché de cet engagement n''est pas celui du même projet'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF l.statut = 'annule' THEN
    RAISE EXCEPTION 'Impossible d''engager sur un marché annulé'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NOT marches_avis_suffisant(l.id) THEN
    RAISE EXCEPTION 'Engagement refusé : l''avis de non-objection du marché % n''est pas obtenu',
      l.reference USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER budget_engagement_avis BEFORE INSERT ON budget_engagement
  FOR EACH ROW EXECUTE FUNCTION budget_engagement_avis();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS budget_engagement_avis ON budget_engagement;
DROP FUNCTION IF EXISTS budget_engagement_avis();
ALTER TABLE budget_engagement DROP CONSTRAINT fk_engagement_ligne_meme_org;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0007_engagement_ligne_passation"),
        ("marches", "0004_avis_garde_fous"),
    ]

    operations = [migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE)]
