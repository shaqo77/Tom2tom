from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

# L'organisation EST le locataire : sa clé est `id`, pas `org_id`. Chaque
# organisation ne voit — et ne peut créer — que sa propre fiche.
RLS_ORGANISATION = """
ALTER TABLE organisations_organisation ENABLE ROW LEVEL SECURITY;
ALTER TABLE organisations_organisation FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS org_isolation ON organisations_organisation;
CREATE POLICY org_isolation ON organisations_organisation
  USING      (id = NULLIF(current_setting('app.org_id', true), '')::uuid)
  WITH CHECK (id = NULLIF(current_setting('app.org_id', true), '')::uuid);
"""
RLS_ORGANISATION_INVERSE = """
DROP POLICY IF EXISTS org_isolation ON organisations_organisation;
ALTER TABLE organisations_organisation NO FORCE ROW LEVEL SECURITY;
ALTER TABLE organisations_organisation DISABLE ROW LEVEL SECURITY;
"""

# La monnaie de tenue et la base comptable d'un projet ne changent plus après
# la première écriture : y toucher réécrirait le sens de tous les montants.
# Le déclencheur lit les lignes sous la RLS de l'appelant, donc dans son
# organisation. Le lot L3 le repointera sur le grand livre définitif.
FONCTION = """
CREATE OR REPLACE FUNCTION organisations_projet_verrou_ecritures() RETURNS trigger AS $$
BEGIN
  IF (NEW.base_currency IS DISTINCT FROM OLD.base_currency
      OR NEW.accounting_basis IS DISTINCT FROM OLD.accounting_basis)
     AND EXISTS (SELECT 1 FROM moteur_ligneecriture WHERE project_id = OLD.id) THEN
    RAISE EXCEPTION
      'La monnaie de tenue et la base comptable ne sont plus modifiables après la première écriture'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS projet_verrou_ecritures ON organisations_projet;
CREATE TRIGGER projet_verrou_ecritures
  BEFORE UPDATE ON organisations_projet
  FOR EACH ROW EXECUTE FUNCTION organisations_projet_verrou_ecritures();
"""
FONCTION_INVERSE = """
DROP TRIGGER IF EXISTS projet_verrou_ecritures ON organisations_projet;
DROP FUNCTION IF EXISTS organisations_projet_verrou_ecritures();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("organisations", "0001_organisation_projet"),
        ("moteur", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(RLS_ORGANISATION, reverse_sql=RLS_ORGANISATION_INVERSE),
        migrations.RunSQL(
            activer_rls("organisations_projet"),
            reverse_sql=desactiver_rls("organisations_projet"),
        ),
        migrations.RunSQL(FONCTION, reverse_sql=FONCTION_INVERSE),
    ]
