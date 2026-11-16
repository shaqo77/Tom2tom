from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = (
    "tresorerie_soldereleve",
    "tresorerie_appariementdemande",
    "tresorerie_previsiontresorerie",
    "tresorerie_justificationecart",
)

SQL = """
ALTER TABLE rapprochement_mouvementreleve ADD CONSTRAINT uq_mouvementreleve_org_id UNIQUE (org_id, id);
ALTER TABLE decaissements_demanderetrait ADD CONSTRAINT uq_demanderetrait_org_id UNIQUE (org_id, id);
ALTER TABLE tresorerie_soldereleve ADD CONSTRAINT fk_soldereleve_compte_meme_org
  FOREIGN KEY (org_id, compte_id) REFERENCES financements_comptebancaire (org_id, id);
ALTER TABLE tresorerie_appariementdemande ADD CONSTRAINT fk_appariement_mouvement_meme_org
  FOREIGN KEY (org_id, mouvement_id) REFERENCES rapprochement_mouvementreleve (org_id, id);
ALTER TABLE tresorerie_appariementdemande ADD CONSTRAINT fk_appariement_demande_meme_org
  FOREIGN KEY (org_id, demande_id) REFERENCES decaissements_demanderetrait (org_id, id);
ALTER TABLE tresorerie_justificationecart ADD CONSTRAINT fk_justifecart_compte_meme_org
  FOREIGN KEY (org_id, compte_id) REFERENCES financements_comptebancaire (org_id, id);

CREATE OR REPLACE FUNCTION tresorerie_ajout_seul() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION '% est en ajout seul', TG_TABLE_NAME
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;

-- Le solde du relevé : du projet du compte, en ajout seul.
CREATE OR REPLACE FUNCTION tresorerie_soldereleve_naissance() RETURNS trigger AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM financements_comptebancaire c
                  WHERE c.id = NEW.compte_id AND c.project_id = NEW.project_id) THEN
    RAISE EXCEPTION 'Le solde de relevé doit suivre le projet de son compte'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER tresorerie_soldereleve_naissance BEFORE INSERT ON tresorerie_soldereleve
  FOR EACH ROW EXECUTE FUNCTION tresorerie_soldereleve_naissance();
CREATE TRIGGER tresorerie_ajout_seul BEFORE UPDATE OR DELETE ON tresorerie_soldereleve
  FOR EACH ROW EXECUTE FUNCTION tresorerie_ajout_seul();

-- L'appariement d'un encaissement à une demande : même projet, même devise que l'accord, demande
-- acceptée ou remboursée, jamais plus que ce que la demande retire au total. Jamais supprimé ;
-- seule son annulation (une fois, motivée) change.
CREATE OR REPLACE FUNCTION tresorerie_appariement_garde() RETURNS trigger AS $$
DECLARE
  m rapprochement_mouvementreleve%ROWTYPE;
  d decaissements_demanderetrait%ROWTYPE;
  deja numeric;
  total numeric;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un appariement ne se supprime pas : on l''annule'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF OLD.annule_at IS NOT NULL
       OR (to_jsonb(NEW) - 'annule_at' - 'annule_par' - 'motif_annulation' - 'updated_at' - 'updated_by')
          <> (to_jsonb(OLD) - 'annule_at' - 'annule_par' - 'motif_annulation' - 'updated_at' - 'updated_by')
    THEN
      RAISE EXCEPTION 'Un appariement ne change que par son annulation, une seule fois'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;
  SELECT * INTO m FROM rapprochement_mouvementreleve WHERE id = NEW.mouvement_id;
  SELECT * INTO d FROM decaissements_demanderetrait WHERE id = NEW.demande_id;
  IF m.montant <= 0 THEN
    RAISE EXCEPTION 'Seul un encaissement s''apparie à une demande de retrait'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF m.project_id <> NEW.project_id OR d.project_id <> NEW.project_id THEN
    RAISE EXCEPTION 'Mouvement, demande et appariement doivent être du même projet'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM financements_comptebancaire c
                   JOIN financements_accord a ON a.id = d.accord_id
                  WHERE c.id = m.compte_id AND c.devise_id = a.devise_id) THEN
    RAISE EXCEPTION 'Le compte du mouvement et l''accord de la demande n''ont pas la même devise'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF d.status NOT IN ('acceptee', 'remboursee') THEN
    RAISE EXCEPTION 'Seule une demande acceptée ou remboursée reçoit un encaissement (demande %)',
      d.numero USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT COALESCE(sum(mv.montant), 0) INTO deja
    FROM tresorerie_appariementdemande ap
    JOIN rapprochement_mouvementreleve mv ON mv.id = ap.mouvement_id
   WHERE ap.demande_id = d.id AND ap.annule_at IS NULL;
  SELECT COALESCE(sum(montant_a_retirer), 0) INTO total
    FROM decaissements_lignedemande WHERE demande_id = d.id AND etat = 'actif';
  IF deja + m.montant > total THEN
    RAISE EXCEPTION 'Les encaissements appariés (%) dépasseraient le montant de la demande (%)',
      deja + m.montant, total USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER tresorerie_appariement_garde BEFORE INSERT OR UPDATE OR DELETE
  ON tresorerie_appariementdemande
  FOR EACH ROW EXECUTE FUNCTION tresorerie_appariement_garde();

-- Une prévision : en ajout seul, révisée SANS TROU (1, puis 2, puis 3…) pour la même période,
-- le même axe et la même devise.
CREATE OR REPLACE FUNCTION tresorerie_prevision_naissance() RETURNS trigger AS $$
DECLARE
  derniere integer;
BEGIN
  SELECT COALESCE(max(revision), 0) INTO derniere FROM tresorerie_previsiontresorerie
   WHERE project_id = NEW.project_id AND devise = NEW.devise AND annee = NEW.annee
     AND mois = NEW.mois AND axe_id IS NOT DISTINCT FROM NEW.axe_id;
  IF NEW.revision <> derniere + 1 THEN
    RAISE EXCEPTION 'Révision de prévision sans trou : attendu %, reçu %', derniere + 1, NEW.revision
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER tresorerie_prevision_naissance BEFORE INSERT ON tresorerie_previsiontresorerie
  FOR EACH ROW EXECUTE FUNCTION tresorerie_prevision_naissance();
CREATE TRIGGER tresorerie_ajout_seul BEFORE UPDATE OR DELETE ON tresorerie_previsiontresorerie
  FOR EACH ROW EXECUTE FUNCTION tresorerie_ajout_seul();

-- Une justification d'écart : du projet du compte, en ajout seul.
CREATE OR REPLACE FUNCTION tresorerie_justification_naissance() RETURNS trigger AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM financements_comptebancaire c
                  WHERE c.id = NEW.compte_id AND c.project_id = NEW.project_id) THEN
    RAISE EXCEPTION 'La justification doit suivre le projet de son compte'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER tresorerie_justification_naissance BEFORE INSERT ON tresorerie_justificationecart
  FOR EACH ROW EXECUTE FUNCTION tresorerie_justification_naissance();
CREATE TRIGGER tresorerie_ajout_seul BEFORE UPDATE OR DELETE ON tresorerie_justificationecart
  FOR EACH ROW EXECUTE FUNCTION tresorerie_ajout_seul();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS tresorerie_ajout_seul ON tresorerie_justificationecart;
DROP TRIGGER IF EXISTS tresorerie_justification_naissance ON tresorerie_justificationecart;
DROP FUNCTION IF EXISTS tresorerie_justification_naissance();
DROP TRIGGER IF EXISTS tresorerie_ajout_seul ON tresorerie_previsiontresorerie;
DROP TRIGGER IF EXISTS tresorerie_prevision_naissance ON tresorerie_previsiontresorerie;
DROP FUNCTION IF EXISTS tresorerie_prevision_naissance();
DROP TRIGGER IF EXISTS tresorerie_appariement_garde ON tresorerie_appariementdemande;
DROP FUNCTION IF EXISTS tresorerie_appariement_garde();
DROP TRIGGER IF EXISTS tresorerie_ajout_seul ON tresorerie_soldereleve;
DROP TRIGGER IF EXISTS tresorerie_soldereleve_naissance ON tresorerie_soldereleve;
DROP FUNCTION IF EXISTS tresorerie_soldereleve_naissance();
DROP FUNCTION IF EXISTS tresorerie_ajout_seul();
ALTER TABLE tresorerie_justificationecart DROP CONSTRAINT fk_justifecart_compte_meme_org;
ALTER TABLE tresorerie_appariementdemande DROP CONSTRAINT fk_appariement_demande_meme_org;
ALTER TABLE tresorerie_appariementdemande DROP CONSTRAINT fk_appariement_mouvement_meme_org;
ALTER TABLE tresorerie_soldereleve DROP CONSTRAINT fk_soldereleve_compte_meme_org;
ALTER TABLE decaissements_demanderetrait DROP CONSTRAINT uq_demanderetrait_org_id;
ALTER TABLE rapprochement_mouvementreleve DROP CONSTRAINT uq_mouvementreleve_org_id;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("tresorerie", "0001_initial"),
        ("rapprochement", "0002_rls_cles_garde_fous"),
        ("decaissements", "0004_montant_a_retirer_et_pieces"),
    ]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        *(migrations.RunSQL(activer_rls(t), reverse_sql=desactiver_rls(t)) for t in TABLES),
    ]
