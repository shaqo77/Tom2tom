from django.db import migrations

# Revue de code de L9 : (1) une ligne sous contrat ou avec un engagement ouvert ne s'annule pas ;
# (2) un avenant ne fixe pas un montant inférieur aux décomptes déjà certifiés.
SQL = """
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
  IF NEW.statut = 'annule' AND (
       EXISTS (SELECT 1 FROM marches_contrat c WHERE c.ligne_id = OLD.id)
       OR EXISTS (SELECT 1 FROM budget_engagement e
                   WHERE e.ligne_passation_id = OLD.id AND e.status = 'ouvert')) THEN
    RAISE EXCEPTION 'Une ligne sous contrat ou avec un engagement ouvert ne s''annule pas (ligne %)',
      OLD.reference USING ERRCODE = 'integrity_constraint_violation';
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

CREATE OR REPLACE FUNCTION marches_avenant_naissance() RETURNS trigger AS $$
DECLARE
  c marches_contrat%ROWTYPE;
  l marches_lignepassation%ROWTYPE;
  dernier integer;
  derniere_date date;
  a marches_avisnonobjection%ROWTYPE;
  certifie numeric;
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
  SELECT COALESCE(sum(montant_brut), 0) INTO certifie
    FROM marches_decompte WHERE contrat_id = c.id AND statut = 'certifie';
  IF NEW.montant < certifie THEN
    RAISE EXCEPTION 'Le nouveau montant (%) est inférieur aux décomptes déjà certifiés (%)',
      NEW.montant, certifie USING ERRCODE = 'integrity_constraint_violation';
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
"""
SQL_INVERSE = """
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
"""


class Migration(migrations.Migration):
    dependencies = [
        ("marches", "0009_decomptes_garde_fous"),
        ("budget", "0008_engagement_avis_requis"),
    ]

    operations = [migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE)]
