from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = ("rapprochement_rapprochement", "rapprochement_mouvementreleve")

CLES = """
ALTER TABLE financements_comptebancaire ADD CONSTRAINT uq_comptebancaire_org_id UNIQUE (org_id, id);
ALTER TABLE rapprochement_rapprochement ADD CONSTRAINT fk_rapprochement_compte_meme_org
  FOREIGN KEY (org_id, compte_id) REFERENCES financements_comptebancaire (org_id, id);
ALTER TABLE rapprochement_rapprochement ADD CONSTRAINT fk_rapprochement_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE rapprochement_mouvementreleve ADD CONSTRAINT fk_mouvement_compte_meme_org
  FOREIGN KEY (org_id, compte_id) REFERENCES financements_comptebancaire (org_id, id);
ALTER TABLE rapprochement_mouvementreleve ADD CONSTRAINT fk_mouvement_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE comptabilite_ligneecriture ADD CONSTRAINT fk_ligne_rapprochement
  FOREIGN KEY (bank_match_id) REFERENCES rapprochement_rapprochement (id);
"""
CLES_INVERSE = """
ALTER TABLE comptabilite_ligneecriture DROP CONSTRAINT fk_ligne_rapprochement;
ALTER TABLE rapprochement_mouvementreleve DROP CONSTRAINT fk_mouvement_projet_meme_org;
ALTER TABLE rapprochement_mouvementreleve DROP CONSTRAINT fk_mouvement_compte_meme_org;
ALTER TABLE rapprochement_rapprochement DROP CONSTRAINT fk_rapprochement_projet_meme_org;
ALTER TABLE rapprochement_rapprochement DROP CONSTRAINT fk_rapprochement_compte_meme_org;
ALTER TABLE financements_comptebancaire DROP CONSTRAINT uq_comptebancaire_org_id;
"""

GARDE = """
-- Le groupe d'un rapprochement, vérifié au COMMIT, EN DEVISE ET EN MONNAIE DE TENUE.
--   devise : Σ (lignes du grand livre) = Σ (mouvements du relevé), au centime ;
--   monnaie de tenue : Σ (lignes) = Σ (mouvements valorisés) : la différence éventuelle est portée
--   par une écriture explicite d'écart de change, qui fait partie du groupe.
CREATE OR REPLACE FUNCTION rapprochement_verifier(cible uuid) RETURNS void AS $$
DECLARE
  r record;
  base text;
  etrangere boolean;
  l record;
  m record;
BEGIN
  SELECT rp.status, rp.compte_id, rp.project_id, c.devise_id INTO r
    FROM rapprochement_rapprochement rp JOIN financements_comptebancaire c ON c.id = rp.compte_id
   WHERE rp.id = cible;
  IF NOT FOUND THEN
    RETURN;
  END IF;
  SELECT base_currency INTO base FROM organisations_projet WHERE id = r.project_id;
  etrangere := r.devise_id <> base;

  SELECT count(*) AS n,
         count(DISTINCT li.account_id) AS comptes,
         COALESCE(bool_and(e.status IN ('posted', 'locked')), true) AS postees,
         COALESCE(bool_and(li.bank_account_id = r.compte_id), true) AS du_compte,
         COALESCE(bool_and(li.project_id = r.project_id), true) AS du_projet,
         COALESCE(bool_and(NOT etrangere OR li.currency_id = r.devise_id), true) AS devise_ok,
         COALESCE(sum(CASE WHEN etrangere THEN li.debit_cur - li.credit_cur
                           ELSE li.debit - li.credit END), 0) AS devise,
         COALESCE(sum(li.debit - li.credit), 0) AS base
    INTO l
    FROM comptabilite_ligneecriture li JOIN comptabilite_ecriture e ON e.id = li.entry_id
   WHERE li.bank_match_id = cible;
  SELECT count(*) AS n, COALESCE(sum(montant), 0) AS devise, COALESCE(sum(montant_base), 0) AS base
    INTO m
    FROM rapprochement_mouvementreleve WHERE rapprochement_id = cible;

  IF l.n = 0 AND m.n = 0 THEN
    RETURN;  -- groupe entièrement défait
  END IF;
  IF l.n = 0 OR m.n = 0 THEN
    RAISE EXCEPTION 'Un rapprochement compte au moins une ligne du grand livre et un mouvement du relevé'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF r.status <> 'actif' THEN
    RAISE EXCEPTION 'Le rapprochement est annulé : ses lignes et ses mouvements ne peuvent plus lui appartenir'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NOT l.postees THEN
    RAISE EXCEPTION 'On ne rapproche que des lignes comptabilisées'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NOT l.du_compte OR NOT l.du_projet THEN
    RAISE EXCEPTION 'Les lignes rapprochées sont celles du compte bancaire du rapprochement'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF l.comptes <> 1 THEN
    RAISE EXCEPTION 'Les lignes rapprochées portent sur un même compte comptable'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NOT l.devise_ok THEN
    RAISE EXCEPTION 'Les lignes rapprochées sont dans la devise du compte bancaire'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF l.devise <> m.devise THEN
    RAISE EXCEPTION 'Le groupe n''est pas soldé en devise : grand livre %, relevé %', l.devise, m.devise
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF l.base <> m.base THEN
    RAISE EXCEPTION 'Le groupe n''est pas soldé en monnaie de tenue : grand livre %, relevé % (un écart de change s''enregistre en écriture explicite)',
      l.base, m.base USING ERRCODE = 'integrity_constraint_violation';
  END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION rapprochement_ligne_assert() RETURNS trigger AS $$
BEGIN
  IF NEW.bank_match_id IS NOT NULL THEN
    PERFORM rapprochement_verifier(NEW.bank_match_id);
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.bank_match_id IS NOT NULL
     AND OLD.bank_match_id IS DISTINCT FROM NEW.bank_match_id THEN
    PERFORM rapprochement_verifier(OLD.bank_match_id);
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER trg_ligne_rapprochement
  AFTER INSERT OR UPDATE OF bank_match_id ON comptabilite_ligneecriture
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION rapprochement_ligne_assert();

CREATE OR REPLACE FUNCTION rapprochement_mouvement_assert() RETURNS trigger AS $$
BEGIN
  IF NEW.rapprochement_id IS NOT NULL THEN
    PERFORM rapprochement_verifier(NEW.rapprochement_id);
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.rapprochement_id IS NOT NULL
     AND OLD.rapprochement_id IS DISTINCT FROM NEW.rapprochement_id THEN
    PERFORM rapprochement_verifier(OLD.rapprochement_id);
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER trg_mouvement_rapprochement
  AFTER INSERT OR UPDATE OF rapprochement_id ON rapprochement_mouvementreleve
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION rapprochement_mouvement_assert();

-- Un mouvement de relevé est en ajout seul : seul son marqueur change.
CREATE OR REPLACE FUNCTION rapprochement_mouvement_garde() RETURNS trigger AS $$
DECLARE
  projet_compte uuid;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un mouvement de relevé ne se supprime pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'INSERT' THEN
    SELECT project_id INTO projet_compte FROM financements_comptebancaire WHERE id = NEW.compte_id;
    IF projet_compte IS DISTINCT FROM NEW.project_id THEN
      RAISE EXCEPTION 'Le mouvement et son compte bancaire appartiennent au même projet'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.rapprochement_id IS NOT NULL THEN
      RAISE EXCEPTION 'Un mouvement naît non rapproché' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.montant * NEW.montant_base < 0 THEN
      RAISE EXCEPTION 'Le montant valorisé a le signe du montant'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF (to_jsonb(NEW) - 'rapprochement_id' - 'updated_at' - 'updated_by')
     <> (to_jsonb(OLD) - 'rapprochement_id' - 'updated_at' - 'updated_by') THEN
    RAISE EXCEPTION 'Un mouvement de relevé ne change que par son rapprochement'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER rapprochement_mouvement_garde
  BEFORE INSERT OR UPDATE OR DELETE ON rapprochement_mouvementreleve
  FOR EACH ROW EXECUTE FUNCTION rapprochement_mouvement_garde();

-- Un rapprochement ne se supprime pas et ne change que par son annulation motivée.
CREATE OR REPLACE FUNCTION rapprochement_garde() RETURNS trigger AS $$
DECLARE
  projet_compte uuid;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un rapprochement ne se supprime pas : on l''annule'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'INSERT' THEN
    SELECT project_id INTO projet_compte FROM financements_comptebancaire WHERE id = NEW.compte_id;
    IF projet_compte IS DISTINCT FROM NEW.project_id THEN
      RAISE EXCEPTION 'Le rapprochement et son compte bancaire appartiennent au même projet'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.status <> 'actif' THEN
      RAISE EXCEPTION 'Un rapprochement naît actif' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status <> 'actif' THEN
    RAISE EXCEPTION 'Un rapprochement annulé est figé' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.status <> 'annule'
     OR (to_jsonb(NEW) - 'status' - 'annule_at' - 'annule_by' - 'motif_annulation'
         - 'ecriture_ecart_annulation_id' - 'updated_at' - 'updated_by')
      <> (to_jsonb(OLD) - 'status' - 'annule_at' - 'annule_by' - 'motif_annulation'
          - 'ecriture_ecart_annulation_id' - 'updated_at' - 'updated_by') THEN
    RAISE EXCEPTION 'Un rapprochement ne change que par son annulation'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER rapprochement_garde
  BEFORE INSERT OR UPDATE OR DELETE ON rapprochement_rapprochement
  FOR EACH ROW EXECUTE FUNCTION rapprochement_garde();
"""
GARDE_INVERSE = """
DROP TRIGGER IF EXISTS rapprochement_garde ON rapprochement_rapprochement;
DROP TRIGGER IF EXISTS rapprochement_mouvement_garde ON rapprochement_mouvementreleve;
DROP TRIGGER IF EXISTS trg_mouvement_rapprochement ON rapprochement_mouvementreleve;
DROP TRIGGER IF EXISTS trg_ligne_rapprochement ON comptabilite_ligneecriture;
DROP FUNCTION IF EXISTS rapprochement_garde();
DROP FUNCTION IF EXISTS rapprochement_mouvement_garde();
DROP FUNCTION IF EXISTS rapprochement_mouvement_assert();
DROP FUNCTION IF EXISTS rapprochement_ligne_assert();
DROP FUNCTION IF EXISTS rapprochement_verifier(uuid);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("rapprochement", "0001_rapprochements_mouvements"),
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
        migrations.RunSQL(GARDE, reverse_sql=GARDE_INVERSE),
    ]
