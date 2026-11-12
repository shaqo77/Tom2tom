from django.db import migrations

# Le verrou de la monnaie de tenue et de la base comptable (migration 0002) lisait la
# table prototype du moteur. On le repointe sur les lignes du grand livre définitif.
FONCTION = """
CREATE OR REPLACE FUNCTION organisations_projet_verrou_ecritures() RETURNS trigger AS $$
BEGIN
  IF (NEW.base_currency IS DISTINCT FROM OLD.base_currency
      OR NEW.accounting_basis IS DISTINCT FROM OLD.accounting_basis)
     AND EXISTS (SELECT 1 FROM comptabilite_ligneecriture WHERE project_id = OLD.id) THEN
    RAISE EXCEPTION
      'La monnaie de tenue et la base comptable ne sont plus modifiables après la première écriture'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
FONCTION_INVERSE = FONCTION.replace("comptabilite_ligneecriture", "moteur_ligneecriture")


class Migration(migrations.Migration):
    dependencies = [
        ("organisations", "0003_separation_des_taches"),
        ("comptabilite", "0002_rls"),
    ]

    operations = [migrations.RunSQL(FONCTION, reverse_sql=FONCTION_INVERSE)]
