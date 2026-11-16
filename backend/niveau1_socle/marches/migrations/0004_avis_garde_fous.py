from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = ("marches_avisnonobjection", "marches_pieceavis")

SQL = """
ALTER TABLE marches_avisnonobjection ADD CONSTRAINT uq_avisnonobjection_org_id UNIQUE (org_id, id);
ALTER TABLE marches_avisnonobjection ADD CONSTRAINT fk_avis_ligne_meme_org
  FOREIGN KEY (org_id, ligne_id) REFERENCES marches_lignepassation (org_id, id);
ALTER TABLE marches_pieceavis ADD CONSTRAINT fk_pieceavis_avis_meme_org
  FOREIGN KEY (org_id, avis_id) REFERENCES marches_avisnonobjection (org_id, id);

-- Un avis : jamais supprimé ; il naît « demandé » ; décidé (obtenu ou refusé), il est figé.
-- Seules la décision (statut, date, référence, motif, auteur) peut s'ajouter à une demande.
CREATE OR REPLACE FUNCTION marches_avis_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un avis de non-objection ne se supprime pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.statut <> 'demande' THEN
      RAISE EXCEPTION 'Un avis naît à l''état « demandé »'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.statut <> 'demande' THEN
    RAISE EXCEPTION 'Un avis % est figé : on demande à nouveau', OLD.statut
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (to_jsonb(NEW) - 'statut' - 'date_decision' - 'reference_bailleur' - 'motif' - 'decide_par'
        - 'updated_at' - 'updated_by')
     <> (to_jsonb(OLD) - 'statut' - 'date_decision' - 'reference_bailleur' - 'motif' - 'decide_par'
        - 'updated_at' - 'updated_by') THEN
    RAISE EXCEPTION 'La demande d''un avis ne se modifie pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER marches_avis_garde BEFORE INSERT OR UPDATE OR DELETE ON marches_avisnonobjection
  FOR EACH ROW EXECUTE FUNCTION marches_avis_garde();

CREATE TRIGGER marches_ajout_seul BEFORE UPDATE OR DELETE ON marches_pieceavis
  FOR EACH ROW EXECUTE FUNCTION marches_ajout_seul();

-- L'avis est-il suffisant pour engager sur cette ligne ? Une ligne non soumise l'est toujours.
-- Sinon il faut au moins un avis, et chaque avis non obtenu doit avoir été suivi d'un avis obtenu
-- du même objet (une demande en attente ou un refus non repris bloque).
CREATE OR REPLACE FUNCTION marches_avis_suffisant(p_ligne uuid) RETURNS boolean AS $$
  SELECT NOT l.non_objection_requise OR (
    EXISTS (SELECT 1 FROM marches_avisnonobjection a WHERE a.ligne_id = l.id)
    AND NOT EXISTS (
      SELECT 1 FROM marches_avisnonobjection a
      WHERE a.ligne_id = l.id AND a.statut <> 'obtenu'
        AND NOT EXISTS (
          SELECT 1 FROM marches_avisnonobjection b
          WHERE b.ligne_id = a.ligne_id AND b.objet = a.objet AND b.statut = 'obtenu'
            AND b.created_at > a.created_at))
  )
  FROM marches_lignepassation l WHERE l.id = p_ligne;
$$ LANGUAGE sql STABLE;
"""
SQL_INVERSE = """
DROP FUNCTION IF EXISTS marches_avis_suffisant(uuid);
DROP TRIGGER IF EXISTS marches_ajout_seul ON marches_pieceavis;
DROP TRIGGER IF EXISTS marches_avis_garde ON marches_avisnonobjection;
DROP FUNCTION IF EXISTS marches_avis_garde();
ALTER TABLE marches_pieceavis DROP CONSTRAINT fk_pieceavis_avis_meme_org;
ALTER TABLE marches_avisnonobjection DROP CONSTRAINT fk_avis_ligne_meme_org;
ALTER TABLE marches_avisnonobjection DROP CONSTRAINT uq_avisnonobjection_org_id;
"""


class Migration(migrations.Migration):
    dependencies = [("marches", "0003_avisnonobjection_pieceavis_and_more")]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        *(migrations.RunSQL(activer_rls(t), reverse_sql=desactiver_rls(t)) for t in TABLES),
    ]
