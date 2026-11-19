from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = (
    "decaissements_demanderetrait",
    "decaissements_lignedemande",
    "decaissements_miseaecart",
    "decaissements_soldecategorie",
    "decaissements_soldeaccord",
)

CLES = """
ALTER TABLE decaissements_demanderetrait ADD CONSTRAINT fk_demande_accord_meme_org
  FOREIGN KEY (org_id, accord_id) REFERENCES financements_accord (org_id, id);
ALTER TABLE decaissements_demanderetrait ADD CONSTRAINT fk_demande_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE decaissements_lignedemande ADD CONSTRAINT fk_lignedemande_ecriture
  FOREIGN KEY (ligne_ecriture_id) REFERENCES comptabilite_ligneecriture (id);
ALTER TABLE decaissements_miseaecart ADD CONSTRAINT fk_ecart_ecriture
  FOREIGN KEY (ligne_ecriture_id) REFERENCES comptabilite_ligneecriture (id);
"""
CLES_INVERSE = """
ALTER TABLE decaissements_miseaecart DROP CONSTRAINT fk_ecart_ecriture;
ALTER TABLE decaissements_lignedemande DROP CONSTRAINT fk_lignedemande_ecriture;
ALTER TABLE decaissements_demanderetrait DROP CONSTRAINT fk_demande_projet_meme_org;
ALTER TABLE decaissements_demanderetrait DROP CONSTRAINT fk_demande_accord_meme_org;
"""

FONCTIONS = """
-- Le montant courant d'un accord : celui de son dernier avenant, sinon le montant initial.
CREATE OR REPLACE FUNCTION financements_montant_courant(cible uuid) RETURNS numeric AS $$
  SELECT COALESCE(
    (SELECT montant_revise FROM financements_avenantaccord
      WHERE accord_id = cible ORDER BY date_avenant DESC, created_at DESC LIMIT 1),
    (SELECT montant_initial FROM financements_accord WHERE id = cible));
$$ LANGUAGE sql STABLE;

-- Répercute (signe = +1) ou retire (signe = -1) le montant d'une demande sur le solde de chaque
-- catégorie de ses lignes ET de leurs catégories parentes, et sur celui de l'accord.
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
    SELECT c.id, c.parent_id, l.montant
      FROM decaissements_lignedemande l JOIN financements_categorie c ON c.id = l.categorie_id
     WHERE l.demande_id = cible AND l.etat = 'actif'
    UNION ALL
    SELECT c.id, c.parent_id, ch.montant
      FROM chaine ch JOIN financements_categorie c ON c.id = ch.parent_id
  )
  SELECT id, SUM(montant) FROM chaine GROUP BY id;

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
           SELECT COALESCE(SUM(montant), 0) FROM decaissements_lignedemande
            WHERE demande_id = cible AND etat = 'actif'),
         updated_at = now()
   WHERE s.accord_id = d.accord_id;
END;
$$ LANGUAGE plpgsql;

-- LE refus ultime : même si un appelant contournait les verrous du service, la base ne laisse pas
-- passer un plafond de catégorie ni un montant d'accord dépassé (seule une HAUSSE est refusée :
-- un plafond abaissé plus tard ne bloque pas les restitutions).
CREATE OR REPLACE FUNCTION decaissements_solde_categorie_garde() RETURNS trigger AS $$
DECLARE
  plafond numeric;
BEGIN
  IF NEW.utilise > OLD.utilise THEN
    SELECT c.plafond INTO plafond FROM financements_categorie c WHERE c.id = NEW.categorie_id;
    IF plafond IS NOT NULL AND NEW.utilise > plafond THEN
      RAISE EXCEPTION 'Le plafond de la catégorie serait dépassé (% pour % autorisés)',
        NEW.utilise, plafond USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER decaissements_solde_categorie_garde
  BEFORE UPDATE ON decaissements_soldecategorie
  FOR EACH ROW EXECUTE FUNCTION decaissements_solde_categorie_garde();

CREATE OR REPLACE FUNCTION decaissements_solde_accord_garde() RETURNS trigger AS $$
DECLARE
  courant numeric;
BEGIN
  IF NEW.utilise > OLD.utilise THEN
    courant := financements_montant_courant(NEW.accord_id);
    IF NEW.utilise > courant THEN
      RAISE EXCEPTION 'Le montant de l''accord serait dépassé (% pour % autorisés)',
        NEW.utilise, courant USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER decaissements_solde_accord_garde
  BEFORE UPDATE ON decaissements_soldeaccord
  FOR EACH ROW EXECUTE FUNCTION decaissements_solde_accord_garde();

-- La demande : naissance, cycle fermé, contenu figé une fois soumise.
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
     OR NEW.periode_debut <> OLD.periode_debut OR NEW.periode_fin <> OLD.periode_fin THEN
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
    SELECT COALESCE(SUM(montant), 0) INTO total
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
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER decaissements_demande_garde
  BEFORE INSERT OR UPDATE OR DELETE ON decaissements_demanderetrait
  FOR EACH ROW EXECUTE FUNCTION decaissements_demande_garde();

-- Après une transition : les soldes suivent, les lignes sont libérées (annulation) ou marquées
-- « reprise seulement » (rejet).
CREATE OR REPLACE FUNCTION decaissements_demande_effets() RETURNS trigger AS $$
BEGIN
  IF NEW.status = OLD.status THEN
    RETURN NULL;
  END IF;
  IF OLD.status = 'preparee' AND NEW.status = 'soumise' THEN
    PERFORM decaissements_appliquer(NEW.id, 1);
  ELSIF NEW.status = 'rejetee' THEN
    PERFORM decaissements_appliquer(NEW.id, -1);
    UPDATE decaissements_lignedemande SET etat = 'rejete', updated_at = now()
     WHERE demande_id = NEW.id AND etat = 'actif';
  ELSIF NEW.status = 'annulee' THEN
    UPDATE decaissements_lignedemande SET etat = 'annule', updated_at = now()
     WHERE demande_id = NEW.id AND etat = 'actif';
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER decaissements_demande_effets
  AFTER UPDATE OF status ON decaissements_demanderetrait
  FOR EACH ROW EXECUTE FUNCTION decaissements_demande_effets();

-- La ligne : recopiée du grand livre et vérifiée, jamais dictée.
CREATE OR REPLACE FUNCTION decaissements_ligne_garde() RETURNS trigger AS $$
DECLARE
  dem record;
  src record;
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

  SELECT status, accord_id, project_id, reprise_de_id INTO dem
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
CREATE TRIGGER decaissements_ligne_garde
  BEFORE INSERT OR UPDATE OR DELETE ON decaissements_lignedemande
  FOR EACH ROW EXECUTE FUNCTION decaissements_ligne_garde();

-- La mise à l'écart : motif tracé, sur une demande préparée, définitive.
CREATE OR REPLACE FUNCTION decaissements_ecart_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    RAISE EXCEPTION 'Une mise à l''écart ne se modifie ni ne se supprime'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (SELECT status FROM decaissements_demanderetrait WHERE id = NEW.demande_id) <> 'preparee' THEN
    RAISE EXCEPTION 'On n''écarte des dépenses que d''une demande préparée'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER decaissements_ecart_garde
  BEFORE INSERT OR UPDATE OR DELETE ON decaissements_miseaecart
  FOR EACH ROW EXECUTE FUNCTION decaissements_ecart_garde();
"""
FONCTIONS_INVERSE = """
DROP TRIGGER IF EXISTS decaissements_ecart_garde ON decaissements_miseaecart;
DROP TRIGGER IF EXISTS decaissements_ligne_garde ON decaissements_lignedemande;
DROP TRIGGER IF EXISTS decaissements_demande_effets ON decaissements_demanderetrait;
DROP TRIGGER IF EXISTS decaissements_demande_garde ON decaissements_demanderetrait;
DROP TRIGGER IF EXISTS decaissements_solde_accord_garde ON decaissements_soldeaccord;
DROP TRIGGER IF EXISTS decaissements_solde_categorie_garde ON decaissements_soldecategorie;
DROP FUNCTION IF EXISTS decaissements_ecart_garde();
DROP FUNCTION IF EXISTS decaissements_ligne_garde();
DROP FUNCTION IF EXISTS decaissements_demande_effets();
DROP FUNCTION IF EXISTS decaissements_demande_garde();
DROP FUNCTION IF EXISTS decaissements_solde_accord_garde();
DROP FUNCTION IF EXISTS decaissements_solde_categorie_garde();
DROP FUNCTION IF EXISTS decaissements_appliquer(uuid, integer);
DROP FUNCTION IF EXISTS financements_montant_courant(uuid);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("decaissements", "0001_demandes_retrait"),
        ("financements", "0004_cles_garde_fous"),
        ("comptabilite", "0014_anouveau_garde_fous"),
        ("organisations", "0004_verrou_sur_grand_livre"),
    ]

    operations = [
        *(
            migrations.RunSQL(activer_rls(table), reverse_sql=desactiver_rls(table))
            for table in TABLES
        ),
        migrations.RunSQL(CLES, reverse_sql=CLES_INVERSE),
        migrations.RunSQL(FONCTIONS, reverse_sql=FONCTIONS_INVERSE),
    ]
