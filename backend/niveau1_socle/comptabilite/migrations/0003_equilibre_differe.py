from django.db import migrations

# Une écriture est équilibrée : somme des débits = somme des crédits, en monnaie de tenue,
# au dix-millième près. La contrainte est DIFFÉRÉE : pendant qu'on insère la première
# ligne l'écriture est forcément déséquilibrée, donc on ne vérifie qu'au COMMIT, quand
# toutes les lignes sont là. Elle vaut pour tous les statuts, brouillons compris.
#
# Le déclencheur contrôle l'écriture ANCIENNE et la NOUVELLE lorsqu'une ligne change
# d'écriture : déplacer une ligne déséquilibre celle qu'elle quitte.
EQUILIBRE = """
CREATE OR REPLACE FUNCTION comptabilite_verifier_equilibre(cible uuid) RETURNS void AS $$
DECLARE
  ecart numeric(20,4);
BEGIN
  SELECT COALESCE(SUM(debit), 0) - COALESCE(SUM(credit), 0) INTO ecart
    FROM comptabilite_ligneecriture WHERE entry_id = cible;
  IF ecart <> 0 THEN
    RAISE EXCEPTION 'Écriture % déséquilibrée : écart de %', cible, ecart
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION comptabilite_assert_ecriture_equilibree() RETURNS trigger AS $$
BEGIN
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    PERFORM comptabilite_verifier_equilibre(NEW.entry_id);
  END IF;
  IF TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND OLD.entry_id IS DISTINCT FROM NEW.entry_id) THEN
    PERFORM comptabilite_verifier_equilibre(OLD.entry_id);
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ecriture_equilibree ON comptabilite_ligneecriture;
CREATE CONSTRAINT TRIGGER trg_ecriture_equilibree
  AFTER INSERT OR UPDATE OR DELETE ON comptabilite_ligneecriture
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION comptabilite_assert_ecriture_equilibree();
"""
EQUILIBRE_INVERSE = """
DROP TRIGGER IF EXISTS trg_ecriture_equilibree ON comptabilite_ligneecriture;
DROP FUNCTION IF EXISTS comptabilite_assert_ecriture_equilibree();
DROP FUNCTION IF EXISTS comptabilite_verifier_equilibre(uuid);
"""


class Migration(migrations.Migration):
    dependencies = [("comptabilite", "0002_rls")]

    operations = [migrations.RunSQL(EQUILIBRE, reverse_sql=EQUILIBRE_INVERSE)]
