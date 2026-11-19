from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = ("marches_decompte", "marches_paiement")

SQL = """
ALTER TABLE budget_engagement ADD CONSTRAINT uq_engagement_org_id UNIQUE (org_id, id);
ALTER TABLE marches_decompte ADD CONSTRAINT uq_decompte_org_id UNIQUE (org_id, id);
ALTER TABLE marches_decompte ADD CONSTRAINT fk_decompte_contrat_meme_org
  FOREIGN KEY (org_id, contrat_id) REFERENCES marches_contrat (org_id, id);
ALTER TABLE marches_decompte ADD CONSTRAINT fk_decompte_engagement_meme_org
  FOREIGN KEY (org_id, engagement_id) REFERENCES budget_engagement (org_id, id);
ALTER TABLE marches_paiement ADD CONSTRAINT fk_paiement_decompte_meme_org
  FOREIGN KEY (org_id, decompte_id) REFERENCES marches_decompte (org_id, id);

-- Montant COURANT d'un contrat : celui du dernier avenant, sinon le montant initial.
CREATE OR REPLACE FUNCTION marches_montant_courant(p_contrat uuid) RETURNS numeric AS $$
  SELECT COALESCE(
    (SELECT a.montant FROM marches_avenantcontrat a
      WHERE a.contrat_id = c.id ORDER BY a.numero DESC LIMIT 1),
    c.montant_initial)
  FROM marches_contrat c WHERE c.id = p_contrat;
$$ LANGUAGE sql STABLE;

-- Un décompte : jamais supprimé ; naît « soumis », numéroté SANS TROU ; sa décision (certifié ou
-- rejeté) est définitive. Certifié : par une autre personne que l'auteur, sur l'engagement DU
-- MARCHÉ du contrat, sans dépasser le montant courant du contrat ni faire reculer l'avancement.
CREATE OR REPLACE FUNCTION marches_decompte_garde() RETURNS trigger AS $$
DECLARE
  c marches_contrat%ROWTYPE;
  e budget_engagement%ROWTYPE;
  dernier integer;
  deja numeric;
  max_avancement numeric;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un décompte ne se supprime pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT * INTO c FROM marches_contrat WHERE id = NEW.contrat_id;
  IF NOT FOUND OR c.project_id <> NEW.project_id THEN
    RAISE EXCEPTION 'Le décompte doit suivre le projet de son contrat'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.statut <> 'soumis' THEN
      RAISE EXCEPTION 'Un décompte naît « soumis »' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    SELECT COALESCE(max(numero), 0) INTO dernier FROM marches_decompte WHERE contrat_id = c.id;
    IF NEW.numero <> dernier + 1 THEN
      RAISE EXCEPTION 'Numérotation des décomptes sans trou : attendu %, reçu %', dernier + 1, NEW.numero
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.statut <> 'soumis' THEN
    RAISE EXCEPTION 'Un décompte % est définitif', OLD.statut
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (to_jsonb(NEW) - 'statut' - 'decide_par' - 'date_decision' - 'engagement_id'
        - 'montant_apure' - 'motif_rejet' - 'updated_at' - 'updated_by')
     <> (to_jsonb(OLD) - 'statut' - 'decide_par' - 'date_decision' - 'engagement_id'
        - 'montant_apure' - 'motif_rejet' - 'updated_at' - 'updated_by') THEN
    RAISE EXCEPTION 'Le contenu d''un décompte ne se modifie pas : on en soumet un nouveau'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.statut = 'certifie' THEN
    SELECT * INTO e FROM budget_engagement WHERE id = NEW.engagement_id;
    IF NOT FOUND OR e.ligne_passation_id IS DISTINCT FROM c.ligne_id THEN
      RAISE EXCEPTION 'Le décompte n''apure que l''engagement du marché de son contrat'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.date_decision < NEW.date_decompte THEN
      RAISE EXCEPTION 'Un décompte ne se certifie pas avant sa date'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    SELECT COALESCE(sum(montant_brut), 0), COALESCE(max(avancement_physique), 0)
      INTO deja, max_avancement
      FROM marches_decompte WHERE contrat_id = c.id AND statut = 'certifie' AND id <> NEW.id;
    IF deja + NEW.montant_brut > marches_montant_courant(c.id) THEN
      RAISE EXCEPTION 'Les décomptes certifiés (%) dépasseraient le montant du contrat (%)',
        deja + NEW.montant_brut, marches_montant_courant(c.id)
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.avancement_physique < max_avancement THEN
      RAISE EXCEPTION 'L''avancement physique cumulé ne recule pas (% après %)',
        NEW.avancement_physique, max_avancement USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER marches_decompte_garde BEFORE INSERT OR UPDATE OR DELETE ON marches_decompte
  FOR EACH ROW EXECUTE FUNCTION marches_decompte_garde();

-- Un paiement : en ajout seul, sur un décompte CERTIFIÉ, sans dépasser son net (brut − retenue).
CREATE OR REPLACE FUNCTION marches_paiement_naissance() RETURNS trigger AS $$
DECLARE
  d marches_decompte%ROWTYPE;
  deja numeric;
BEGIN
  SELECT * INTO d FROM marches_decompte WHERE id = NEW.decompte_id FOR UPDATE;
  IF NOT FOUND OR d.project_id <> NEW.project_id OR d.statut <> 'certifie' THEN
    RAISE EXCEPTION 'On ne paie qu''un décompte certifié de son projet'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.date_paiement < d.date_decision THEN
    RAISE EXCEPTION 'Un paiement ne précède pas la certification du décompte'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT COALESCE(sum(montant), 0) INTO deja FROM marches_paiement WHERE decompte_id = d.id;
  IF deja + NEW.montant > d.montant_brut - d.retenue THEN
    RAISE EXCEPTION 'Les paiements (%) dépasseraient le net du décompte (%)',
      deja + NEW.montant, d.montant_brut - d.retenue USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER marches_paiement_naissance BEFORE INSERT ON marches_paiement
  FOR EACH ROW EXECUTE FUNCTION marches_paiement_naissance();
CREATE TRIGGER marches_ajout_seul BEFORE UPDATE OR DELETE ON marches_paiement
  FOR EACH ROW EXECUTE FUNCTION marches_ajout_seul();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS marches_ajout_seul ON marches_paiement;
DROP TRIGGER IF EXISTS marches_paiement_naissance ON marches_paiement;
DROP FUNCTION IF EXISTS marches_paiement_naissance();
DROP TRIGGER IF EXISTS marches_decompte_garde ON marches_decompte;
DROP FUNCTION IF EXISTS marches_decompte_garde();
DROP FUNCTION IF EXISTS marches_montant_courant(uuid);
ALTER TABLE marches_paiement DROP CONSTRAINT fk_paiement_decompte_meme_org;
ALTER TABLE marches_decompte DROP CONSTRAINT fk_decompte_engagement_meme_org;
ALTER TABLE marches_decompte DROP CONSTRAINT fk_decompte_contrat_meme_org;
ALTER TABLE marches_decompte DROP CONSTRAINT uq_decompte_org_id;
ALTER TABLE budget_engagement DROP CONSTRAINT uq_engagement_org_id;
"""


class Migration(migrations.Migration):
    dependencies = [("marches", "0008_decompte_paiement_decompte_uq_decompte_numero_and_more")]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        *(migrations.RunSQL(activer_rls(t), reverse_sql=desactiver_rls(t)) for t in TABLES),
    ]
