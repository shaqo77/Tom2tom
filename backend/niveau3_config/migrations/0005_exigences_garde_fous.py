from django.db import migrations

# Ce que la base garantit d'une exigence, en plus de L0-T08 (validateur nommé et daté) :
# - la citation a la forme voulue : un objet avec un extrait non vide et un paragraphe ou une page
#   (les COALESCE : un CHECK dont le résultat est NULL le laisse passer) ;
# - une exigence conditionnelle porte sa condition ; la confiance n'existe que si l'assistant
#   a proposé l'exigence, et c'est alors un ratio entre 0 et 1 ;
# - une exigence validée ou active a une citation VÉRIFIÉE, sur le texte du document référencé.
SQL = """
ALTER TABLE niveau3_config_exigence ADD CONSTRAINT exigence_citation_structuree CHECK (
  jsonb_typeof(citation) = 'object'
  AND COALESCE(jsonb_typeof(citation -> 'quote'), '') = 'string'
  AND length(btrim(COALESCE(citation ->> 'quote', ''))) > 0
  AND (citation ? 'paragraph' OR citation ? 'page')
);
ALTER TABLE niveau3_config_exigence ADD CONSTRAINT exigence_condition_si_conditionnelle CHECK (
  obligation <> 'conditional' OR length(btrim(COALESCE(condition_expr, ''))) > 0
);
ALTER TABLE niveau3_config_exigence ADD CONSTRAINT exigence_confiance_si_assistee CHECK (
  (source = 'manual' AND confidence IS NULL)
  OR (source = 'assisted' AND confidence IS NOT NULL AND confidence >= 0 AND confidence <= 1)
);

CREATE OR REPLACE FUNCTION niveau3_exigence_citation_garde() RETURNS trigger AS $$
DECLARE
  empreinte bytea;
BEGIN
  IF NEW.status IN ('validated', 'active') AND NEW.citation_verifiee_sha256 IS NULL THEN
    RAISE EXCEPTION 'Une exigence validée ou active a une citation vérifiée dans le document référencé'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.citation_verifiee_sha256 IS NOT NULL THEN
    SELECT sha256 INTO empreinte FROM niveau3_config_documentreference WHERE id = NEW.document_id;
    IF empreinte IS DISTINCT FROM NEW.citation_verifiee_sha256 THEN
      RAISE EXCEPTION 'La citation a été vérifiée sur un autre texte que celui du document référencé'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER niveau3_exigence_citation_garde
  BEFORE INSERT OR UPDATE ON niveau3_config_exigence
  FOR EACH ROW EXECUTE FUNCTION niveau3_exigence_citation_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS niveau3_exigence_citation_garde ON niveau3_config_exigence;
DROP FUNCTION IF EXISTS niveau3_exigence_citation_garde();
ALTER TABLE niveau3_config_exigence DROP CONSTRAINT exigence_confiance_si_assistee;
ALTER TABLE niveau3_config_exigence DROP CONSTRAINT exigence_condition_si_conditionnelle;
ALTER TABLE niveau3_config_exigence DROP CONSTRAINT exigence_citation_structuree;
"""


class Migration(migrations.Migration):
    dependencies = [("niveau3_config", "0004_citation_verifiee")]

    operations = [migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE)]
