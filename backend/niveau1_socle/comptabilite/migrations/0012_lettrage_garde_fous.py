from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

# 1. Lettrer n'est pas écrire. Les lignes d'une écriture comptabilisée restent immuables, sauf
#    leurs MARQUEURS (`reconciliation_id`, `bank_match_id`), qui peuvent changer même en période
#    close : lettrer et rapprocher se poursuivent après la clôture. Toute autre colonne qui
#    bouge dans le même UPDATE fait refuser le tout.
# 2. Un lettrage vérifié en base, au COMMIT : au moins deux lignes comptabilisées, même compte,
#    même tiers, même projet, solde nul (et nul en devise si la devise est unique). Un
#    dé-lettrage doit emporter tout le groupe ou rien.
# 3. Un lettrage ne se supprime pas et ne change que par annulation.
GARDE = """
CREATE OR REPLACE FUNCTION comptabilite_ligne_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.entry_id = OLD.entry_id
     AND (to_jsonb(NEW) - 'reconciliation_id' - 'bank_match_id' - 'updated_at' - 'updated_by')
       = (to_jsonb(OLD) - 'reconciliation_id' - 'bank_match_id' - 'updated_at' - 'updated_by') THEN
    RETURN NEW;  -- seul un marqueur change
  END IF;
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    PERFORM comptabilite_verifier_ecriture_modifiable(OLD.entry_id);
  END IF;
  IF TG_OP = 'INSERT' OR (TG_OP = 'UPDATE' AND NEW.entry_id IS DISTINCT FROM OLD.entry_id) THEN
    PERFORM comptabilite_verifier_ecriture_modifiable(NEW.entry_id);
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

ALTER TABLE comptabilite_ligneecriture
  ADD CONSTRAINT ligne_lettrage_fk FOREIGN KEY (reconciliation_id)
  REFERENCES comptabilite_lettrage (id);

CREATE OR REPLACE FUNCTION comptabilite_verifier_lettrage(cible uuid) RETURNS void AS $$
DECLARE
  g record;
  statut text;
BEGIN
  SELECT count(*) AS n,
         count(DISTINCT l.account_id) AS comptes,
         count(DISTINCT l.partner_id) AS tiers,
         count(DISTINCT l.project_id) AS projets,
         bool_and(l.partner_id IS NOT NULL) AS tous_ont_un_tiers,
         bool_and(e.status IN ('posted', 'locked')) AS toutes_comptabilisees,
         COALESCE(sum(l.debit - l.credit), 0) AS solde,
         count(DISTINCT l.currency_id) AS devises,
         COALESCE(sum(l.debit_cur - l.credit_cur), 0) AS solde_devise
    INTO g
    FROM comptabilite_ligneecriture l JOIN comptabilite_ecriture e ON e.id = l.entry_id
   WHERE l.reconciliation_id = cible;
  IF g.n = 0 THEN
    RETURN;  -- groupe entièrement dé-lettré
  END IF;
  IF g.n < 2 THEN
    RAISE EXCEPTION 'Un lettrage compte au moins deux lignes (% restante)', g.n
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF g.comptes <> 1 OR g.tiers <> 1 OR g.projets <> 1 OR NOT g.tous_ont_un_tiers THEN
    RAISE EXCEPTION 'Les lignes d''un lettrage portent sur le même compte, le même tiers et le même projet'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NOT g.toutes_comptabilisees THEN
    RAISE EXCEPTION 'On ne lettre que des lignes comptabilisées'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF g.solde <> 0 THEN
    RAISE EXCEPTION 'Le lettrage n''est pas soldé : écart de %', g.solde
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF g.devises = 1 AND g.solde_devise <> 0 THEN
    RAISE EXCEPTION 'Le lettrage n''est pas soldé en devise : écart de %', g.solde_devise
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT status INTO statut FROM comptabilite_lettrage WHERE id = cible;
  IF statut IS DISTINCT FROM 'actif' THEN
    RAISE EXCEPTION 'Le lettrage est annulé : ses lignes ne peuvent plus lui appartenir'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION comptabilite_ligne_lettrage() RETURNS trigger AS $$
BEGIN
  IF NEW.reconciliation_id IS NOT NULL THEN
    PERFORM comptabilite_verifier_lettrage(NEW.reconciliation_id);
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.reconciliation_id IS NOT NULL
     AND OLD.reconciliation_id IS DISTINCT FROM NEW.reconciliation_id THEN
    PERFORM comptabilite_verifier_lettrage(OLD.reconciliation_id);
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ligne_lettrage ON comptabilite_ligneecriture;
CREATE CONSTRAINT TRIGGER trg_ligne_lettrage
  AFTER INSERT OR UPDATE OF reconciliation_id ON comptabilite_ligneecriture
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION comptabilite_ligne_lettrage();

CREATE OR REPLACE FUNCTION comptabilite_lettrage_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un lettrage ne se supprime pas : on le dé-lettre, ce qui l''annule'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.status = 'annule' THEN
    RAISE EXCEPTION 'Un lettrage annulé ne se modifie plus'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (to_jsonb(NEW) - 'status' - 'annule_at' - 'annule_by' - 'motif_annulation'
        - 'updated_at' - 'updated_by')
     <> (to_jsonb(OLD) - 'status' - 'annule_at' - 'annule_by' - 'motif_annulation'
        - 'updated_at' - 'updated_by') THEN
    RAISE EXCEPTION 'Un lettrage ne se modifie pas : il ne change que par annulation'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_lettrage_garde ON comptabilite_lettrage;
CREATE TRIGGER trg_lettrage_garde
  BEFORE UPDATE OR DELETE ON comptabilite_lettrage
  FOR EACH ROW EXECUTE FUNCTION comptabilite_lettrage_garde();
"""
GARDE_INVERSE = """
DROP TRIGGER IF EXISTS trg_lettrage_garde ON comptabilite_lettrage;
DROP TRIGGER IF EXISTS trg_ligne_lettrage ON comptabilite_ligneecriture;
DROP FUNCTION IF EXISTS comptabilite_lettrage_garde();
DROP FUNCTION IF EXISTS comptabilite_ligne_lettrage();
DROP FUNCTION IF EXISTS comptabilite_verifier_lettrage(uuid);
ALTER TABLE comptabilite_ligneecriture DROP CONSTRAINT ligne_lettrage_fk;

CREATE OR REPLACE FUNCTION comptabilite_ligne_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    PERFORM comptabilite_verifier_ecriture_modifiable(OLD.entry_id);
  END IF;
  IF TG_OP = 'INSERT' OR (TG_OP = 'UPDATE' AND NEW.entry_id IS DISTINCT FROM OLD.entry_id) THEN
    PERFORM comptabilite_verifier_ecriture_modifiable(NEW.entry_id);
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [("comptabilite", "0011_lettrage")]

    operations = [
        migrations.RunSQL(GARDE, reverse_sql=GARDE_INVERSE),
        migrations.RunSQL(
            activer_rls("comptabilite_lettrage"), reverse_sql=desactiver_rls("comptabilite_lettrage")
        ),
    ]
