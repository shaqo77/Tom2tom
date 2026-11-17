from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

# Ce que la base garantit, même en SQL direct : une version posée ne se modifie ni ne se supprime
# (seule sa fin se pose, une fois) ; deux versions du même niveau ne se chevauchent jamais ; une
# liste de devises n'est ni vide ni composée de devises inconnues. L'isolation par organisation.
SQL = (
    activer_rls("referentiels_parametredevises")
    + """
ALTER TABLE referentiels_parametredevises ADD CONSTRAINT parametredevises_liste_non_vide
  CHECK (devises_autorisees IS NULL OR cardinality(devises_autorisees) > 0);

ALTER TABLE referentiels_parametredevises ADD CONSTRAINT parametredevises_sans_chevauchement
  EXCLUDE USING gist (
    org_id WITH =,
    (COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid)) WITH =,
    daterange(valid_from, valid_to, '[)') WITH &&
  );

CREATE OR REPLACE FUNCTION referentiels_parametredevises_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un réglage de devises ne se supprime pas : créez une nouvelle version'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF (NEW.org_id, NEW.project_id, NEW.devise_reference_id, NEW.devises_autorisees,
        NEW.type_taux, NEW.version, NEW.valid_from, NEW.motif)
       IS DISTINCT FROM
       (OLD.org_id, OLD.project_id, OLD.devise_reference_id, OLD.devises_autorisees,
        OLD.type_taux, OLD.version, OLD.valid_from, OLD.motif)
       OR OLD.valid_to IS NOT NULL THEN
      RAISE EXCEPTION 'Un réglage de devises posé ne se modifie pas : créez une nouvelle version'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.devises_autorisees IS NOT NULL AND EXISTS (
       SELECT 1 FROM unnest(NEW.devises_autorisees) AS c(code)
       WHERE NOT EXISTS (SELECT 1 FROM referentiels_devise d WHERE d.code = c.code)) THEN
    RAISE EXCEPTION 'Devise inconnue dans la liste des devises autorisées'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER parametredevises_garde BEFORE INSERT OR UPDATE OR DELETE
  ON referentiels_parametredevises FOR EACH ROW
  EXECUTE FUNCTION referentiels_parametredevises_garde();
"""
)

SQL_INVERSE = (
    """
DROP TRIGGER IF EXISTS parametredevises_garde ON referentiels_parametredevises;
DROP FUNCTION IF EXISTS referentiels_parametredevises_garde();
ALTER TABLE referentiels_parametredevises DROP CONSTRAINT IF EXISTS parametredevises_sans_chevauchement;
ALTER TABLE referentiels_parametredevises DROP CONSTRAINT IF EXISTS parametredevises_liste_non_vide;
"""
    + desactiver_rls("referentiels_parametredevises")
)


class Migration(migrations.Migration):
    dependencies = [("referentiels", "0011_parametres_devises")]
    operations = [migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE)]
