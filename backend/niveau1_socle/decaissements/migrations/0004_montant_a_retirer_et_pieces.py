from django.db import migrations

# L5-T03bis : le montant demandé au bailleur est `montant_a_retirer` (dépense × taux de la règle de
# financement), pas la dépense. Les soldes de catégorie et d'accord, le total de la demande et le
# refus ultime de la base le comptent ainsi. Une ligne porte sa règle, son profil et son taux
# (persistés : une réallocation ultérieure ne les change pas) ; sans profil, la base fixe le montant
# à retirer à la dépense. La soumission exige les pièces que le profil impose.
FONCTIONS = """
CREATE OR REPLACE FUNCTION decaissements_appliquer(cible uuid, signe integer) RETURNS void AS $$
DECLARE
  d record;
BEGIN
  SELECT org_id, accord_id INTO d FROM decaissements_demanderetrait WHERE id = cible;

  CREATE TEMP TABLE IF NOT EXISTS _delta_categorie (categorie_id uuid, total numeric)
    ON COMMIT DROP;
  TRUNCATE _delta_categorie;
  INSERT INTO _delta_categorie
  WITH RECURSIVE chaine AS (
    SELECT c.id, c.parent_id, l.montant_a_retirer
      FROM decaissements_lignedemande l JOIN financements_categorie c ON c.id = l.categorie_id
     WHERE l.demande_id = cible AND l.etat = 'actif'
    UNION ALL
    SELECT c.id, c.parent_id, ch.montant_a_retirer
      FROM chaine ch JOIN financements_categorie c ON c.id = ch.parent_id
  )
  SELECT id, SUM(montant_a_retirer) FROM chaine GROUP BY id;

  INSERT INTO decaissements_soldecategorie (id, created_at, updated_at, org_id, categorie_id, utilise)
  SELECT gen_random_uuid(), now(), now(), d.org_id, categorie_id, 0 FROM _delta_categorie
  ON CONFLICT (categorie_id) DO NOTHING;
  UPDATE decaissements_soldecategorie s
     SET utilise = s.utilise + signe * x.total, updated_at = now()
    FROM _delta_categorie x WHERE s.categorie_id = x.categorie_id;

  INSERT INTO decaissements_soldeaccord (id, created_at, updated_at, org_id, accord_id, utilise)
  VALUES (gen_random_uuid(), now(), now(), d.org_id, d.accord_id, 0)
  ON CONFLICT (accord_id) DO NOTHING;
  UPDATE decaissements_soldeaccord s
     SET utilise = s.utilise + signe * (
           SELECT COALESCE(SUM(montant_a_retirer), 0) FROM decaissements_lignedemande
            WHERE demande_id = cible AND etat = 'actif'),
         updated_at = now()
   WHERE s.accord_id = d.accord_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION decaissements_demande_garde() RETURNS trigger AS $$
DECLARE
  statut_accord text;
  projet_accord uuid;
  precedente record;
  total numeric;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une demande de retrait ne se supprime jamais : on l''annule'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;

  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'preparee' THEN
      RAISE EXCEPTION 'Une demande naît préparée' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    SELECT status, project_id INTO statut_accord, projet_accord
      FROM financements_accord WHERE id = NEW.accord_id;
    IF statut_accord <> 'actif' THEN
      RAISE EXCEPTION 'L''accord est % : aucune nouvelle demande de décaissement n''est possible',
        statut_accord USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF projet_accord <> NEW.project_id THEN
      RAISE EXCEPTION 'La demande et son accord appartiennent au même projet'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.profil_version_id IS NOT NULL AND NOT EXISTS (
         SELECT 1 FROM niveau3_config_profildecaissement
          WHERE id = NEW.profil_version_id AND accord_id = NEW.accord_id) THEN
      RAISE EXCEPTION 'Le profil d''une demande est celui de son accord'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.reprise_de_id IS NOT NULL THEN
      SELECT status, accord_id INTO precedente
        FROM decaissements_demanderetrait WHERE id = NEW.reprise_de_id;
      IF precedente.status IS DISTINCT FROM 'rejetee' OR precedente.accord_id <> NEW.accord_id THEN
        RAISE EXCEPTION 'On ne représente qu''une demande rejetée du même accord'
          USING ERRCODE = 'integrity_constraint_violation';
      END IF;
    END IF;
    RETURN NEW;
  END IF;

  -- UPDATE
  IF OLD.status IN ('rejetee', 'remboursee', 'annulee') THEN
    RAISE EXCEPTION 'Une demande % est figée', OLD.status
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.status <> OLD.status AND NOT (
       (OLD.status = 'preparee' AND NEW.status IN ('soumise', 'annulee'))
    OR (OLD.status = 'soumise' AND NEW.status IN ('acceptee', 'rejetee', 'contestee'))
    OR (OLD.status = 'acceptee' AND NEW.status IN ('remboursee', 'contestee'))
    OR (OLD.status = 'contestee' AND NEW.status IN ('acceptee', 'rejetee'))) THEN
    RAISE EXCEPTION 'Transition de demande interdite : % vers %', OLD.status, NEW.status
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.accord_id <> OLD.accord_id OR NEW.project_id <> OLD.project_id OR NEW.type <> OLD.type
     OR NEW.numero <> OLD.numero OR NEW.reprise_de_id IS DISTINCT FROM OLD.reprise_de_id
     OR NEW.periode_debut <> OLD.periode_debut OR NEW.periode_fin <> OLD.periode_fin
     OR NEW.profil_version_id IS DISTINCT FROM OLD.profil_version_id THEN
    RAISE EXCEPTION 'Le projet, l''accord, le type, le numéro, la période et la reprise d''une demande ne changent pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.status <> 'preparee'
     AND (to_jsonb(NEW) - 'status' - 'motif_rejet' - 'motif_contestation' - 'decidee_le'
          - 'decidee_par' - 'updated_at' - 'updated_by')
      <> (to_jsonb(OLD) - 'status' - 'motif_rejet' - 'motif_contestation' - 'decidee_le'
          - 'decidee_par' - 'updated_at' - 'updated_by') THEN
    RAISE EXCEPTION 'Le contenu d''une demande soumise ne change plus'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.status = 'soumise' AND OLD.status = 'preparee' THEN
    SELECT COALESCE(SUM(montant_a_retirer), 0) INTO total
      FROM decaissements_lignedemande WHERE demande_id = NEW.id AND etat = 'actif';
    IF total = 0 OR total <> NEW.montant_total THEN
      RAISE EXCEPTION 'Le montant de la demande (%) ne correspond pas à ses lignes (%)',
        NEW.montant_total, total USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    SELECT status INTO statut_accord FROM financements_accord WHERE id = NEW.accord_id;
    IF statut_accord <> 'actif' THEN
      RAISE EXCEPTION 'L''accord est % : aucune nouvelle demande de décaissement n''est possible',
        statut_accord USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NOT (COALESCE(NEW.pieces_fournies, '[]'::jsonb) @> COALESCE(NEW.pieces_exigees, '[]'::jsonb)) THEN
      RAISE EXCEPTION 'Les pièces exigées (%) ne sont pas toutes fournies (%)',
        NEW.pieces_exigees, NEW.pieces_fournies USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION decaissements_ligne_garde() RETURNS trigger AS $$
DECLARE
  dem record;
  src record;
  regle record;
  derniere uuid;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une dépense justifiée ne se retire pas d''une demande : on annule la demande'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF pg_trigger_depth() < 2
       OR (to_jsonb(NEW) - 'etat' - 'updated_at' - 'updated_by')
        <> (to_jsonb(OLD) - 'etat' - 'updated_at' - 'updated_by') THEN
      RAISE EXCEPTION 'Une ligne de demande ne change que par le sort de sa demande'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;

  SELECT status, accord_id, project_id, reprise_de_id, profil_version_id INTO dem
    FROM decaissements_demanderetrait WHERE id = NEW.demande_id;
  IF dem.status <> 'preparee' THEN
    RAISE EXCEPTION 'On ne choisit des dépenses que pour une demande préparée'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT l.agreement_id, l.category_id, l.project_id, l.debit - l.credit AS net, e.status,
         e.number, e.accounting_date
    INTO src
    FROM comptabilite_ligneecriture l JOIN comptabilite_ecriture e ON e.id = l.entry_id
   WHERE l.id = NEW.ligne_ecriture_id;
  IF src.status NOT IN ('posted', 'locked') THEN
    RAISE EXCEPTION 'Seule une dépense comptabilisée peut être justifiée'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF src.project_id <> dem.project_id OR src.agreement_id IS DISTINCT FROM dem.accord_id THEN
    RAISE EXCEPTION 'La dépense n''est pas imputée à l''accord de la demande'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF src.category_id IS DISTINCT FROM NEW.categorie_id OR src.category_id IS NULL THEN
    RAISE EXCEPTION 'La catégorie de la ligne est celle du grand livre (une dépense sans catégorie ne se justifie pas)'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF src.net <= 0 OR src.net <> NEW.montant THEN
    RAISE EXCEPTION 'Le montant de la ligne est celui du grand livre (%)', src.net
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  -- Le montant demandé au bailleur : sans profil, la dépense entière ; sous profil, le fruit de la
  -- règle de financement de la catégorie (ou de sa catégorie parente), persistée sur la ligne.
  IF NEW.regle_financement_id IS NULL THEN
    IF dem.profil_version_id IS NOT NULL OR NEW.profil_version_id IS NOT NULL
       OR NEW.taux_applique IS NOT NULL THEN
      RAISE EXCEPTION 'Une demande sous profil exige la règle de financement de chaque ligne'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    NEW.montant_a_retirer := NEW.montant;
  ELSE
    SELECT profil_id, category_id, funding_rate INTO regle
      FROM niveau3_config_reglefinancementcategorie WHERE id = NEW.regle_financement_id;
    IF regle.profil_id IS DISTINCT FROM dem.profil_version_id
       OR NEW.profil_version_id IS DISTINCT FROM dem.profil_version_id THEN
      RAISE EXCEPTION 'La règle de financement est celle du profil de la demande'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NOT EXISTS (
         WITH RECURSIVE chaine AS (
           SELECT id, parent_id FROM financements_categorie WHERE id = NEW.categorie_id
           UNION ALL
           SELECT c.id, c.parent_id FROM financements_categorie c JOIN chaine ch ON c.id = ch.parent_id
         ) SELECT 1 FROM chaine WHERE id = regle.category_id) THEN
      RAISE EXCEPTION 'La règle de financement est celle de la catégorie de la ligne ou de son parent'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.taux_applique IS DISTINCT FROM regle.funding_rate THEN
      RAISE EXCEPTION 'Le taux appliqué est celui de la règle (%)', regle.funding_rate
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.montant_a_retirer <= 0 OR NEW.montant_a_retirer > NEW.montant * regle.funding_rate THEN
      RAISE EXCEPTION 'Le montant à retirer dépasse dépense × taux (% × %)', NEW.montant,
        regle.funding_rate USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  IF NEW.etat <> 'actif' THEN
    RAISE EXCEPTION 'Une ligne naît active' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  -- Une dépense d'une demande rejetée ne revient que par la reprise de CETTE demande.
  SELECT o.demande_id INTO derniere
    FROM decaissements_lignedemande o
   WHERE o.ligne_ecriture_id = NEW.ligne_ecriture_id AND o.etat = 'rejete'
   ORDER BY o.created_at DESC, o.id DESC LIMIT 1;
  IF derniere IS NOT NULL AND derniere IS DISTINCT FROM dem.reprise_de_id THEN
    RAISE EXCEPTION 'Cette dépense a été rejetée : elle ne revient que par une demande qui reprend la demande rejetée'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  NEW.piece := COALESCE(src.number, '');
  NEW.date_piece := src.accounting_date;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [("decaissements", "0003_profil_et_montant_a_retirer")]

    # Les fonctions de la migration 0002 sont remplacées sur place ; revenir en arrière ne se fait
    # qu'en revenant au schéma de L4-T06 (base vierge).
    operations = [migrations.RunSQL(FONCTIONS, reverse_sql=migrations.RunSQL.noop)]
