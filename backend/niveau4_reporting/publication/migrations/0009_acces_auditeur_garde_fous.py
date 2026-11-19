from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

SQL = """
ALTER TABLE publication_accesauditeur ADD CONSTRAINT acces_auditeur_projets_liste CHECK (
  jsonb_typeof(project_ids) = 'array' AND jsonb_array_length(project_ids) BETWEEN 1 AND 50
);
ALTER TABLE publication_accesauditeur ADD CONSTRAINT acces_auditeur_jeton_32 CHECK (
  octet_length(jeton_hash) = 32
);

-- Un accès ne change jamais de périmètre ni de date d'expiration : pas de prolongation, de qui que
-- ce soit (un administrateur crée un NOUVEL accès). Seule sa révocation se pose, une fois. Il ne se
-- supprime pas : il reste la preuve de ce qui a été autorisé.
CREATE OR REPLACE FUNCTION publication_acces_auditeur_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un accès auditeur ne se supprime pas : on le révoque'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.nom, NEW.project_ids, NEW.period_from, NEW.period_to, NEW.jeton_hash, NEW.expire_le,
      NEW.cree_par) IS DISTINCT FROM
     (OLD.nom, OLD.project_ids, OLD.period_from, OLD.period_to, OLD.jeton_hash, OLD.expire_le,
      OLD.cree_par) THEN
    RAISE EXCEPTION 'Un accès auditeur ne se modifie ni ne se prolonge : créez-en un autre'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.revoque_le IS NOT NULL AND
     (NEW.revoque_le, NEW.revoque_par) IS DISTINCT FROM (OLD.revoque_le, OLD.revoque_par) THEN
    RAISE EXCEPTION 'La révocation d''un accès auditeur ne se réécrit pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER publication_acces_auditeur_garde BEFORE UPDATE OR DELETE
  ON publication_accesauditeur
  FOR EACH ROW EXECUTE FUNCTION publication_acces_auditeur_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS publication_acces_auditeur_garde ON publication_accesauditeur;
DROP FUNCTION IF EXISTS publication_acces_auditeur_garde();
ALTER TABLE publication_accesauditeur DROP CONSTRAINT acces_auditeur_jeton_32;
ALTER TABLE publication_accesauditeur DROP CONSTRAINT acces_auditeur_projets_liste;
"""


class Migration(migrations.Migration):
    dependencies = [("publication", "0008_acces_auditeur")]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        migrations.RunSQL(
            activer_rls("publication_accesauditeur"),
            reverse_sql=desactiver_rls("publication_accesauditeur"),
        ),
    ]
