from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

# Le numéro est attribué par la BASE, dans la transaction de la comptabilisation :
# - il vient d'un compteur par journal et par exercice, incrémenté sous verrou
#   consultatif ; annuler la transaction annule l'incrément (pas de trou, contrairement à
#   une séquence PostgreSQL) ;
# - l'appelant ne le choisit jamais ; une écriture naît en brouillon et se comptabilise par
#   changement de statut ;
# - le compteur ne bouge que de +1, et ne se supprime pas.
#
# Le trigger de numérotation s'appelle « trg_ecriture_numerotation » : PostgreSQL déclenche
# les triggers dans l'ordre alphabétique, donc « trg_ecriture_garde » (immuabilité, période
# ouverte) passe avant lui et refuse une écriture comptabilisée ou en période close.
NUMEROTATION = """
CREATE OR REPLACE FUNCTION comptabilite_ecriture_numerotation() RETURNS trigger AS $$
DECLARE
  rang integer;
  code_journal text;
  annee_exercice integer;
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.status IN ('posted', 'locked') THEN
      RAISE EXCEPTION 'Une écriture naît en brouillon : elle se comptabilise par mise à jour'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.number IS NOT NULL THEN
      RAISE EXCEPTION 'Le numéro est attribué par la base à la comptabilisation'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;

  IF NEW.status = 'posted' AND OLD.status NOT IN ('posted', 'locked') THEN
    IF NEW.number IS NOT NULL THEN
      RAISE EXCEPTION 'Le numéro est attribué par la base à la comptabilisation : ne le fournissez pas'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    -- Verrou consultatif : les comptabilisations d'un même journal et exercice font la queue
    -- jusqu'au COMMIT ; le compteur ci-dessous est lui aussi verrouillé par sa ligne.
    PERFORM pg_advisory_xact_lock(
      hashtext('numero:' || NEW.org_id || ':' || NEW.journal_id || ':' || NEW.exercice_id));
    INSERT INTO comptabilite_compteur
        (id, org_id, journal_id, exercice_id, dernier, created_at, updated_at)
      VALUES (gen_random_uuid(), NEW.org_id, NEW.journal_id, NEW.exercice_id, 1, now(), now())
      ON CONFLICT (org_id, journal_id, exercice_id)
      DO UPDATE SET dernier = comptabilite_compteur.dernier + 1, updated_at = now()
      RETURNING dernier INTO rang;
    SELECT j.code, x.annee INTO code_journal, annee_exercice
      FROM comptabilite_journal j, exercices_exercice x
     WHERE j.id = NEW.journal_id AND x.id = NEW.exercice_id;
    NEW.number := code_journal || '-' || annee_exercice || '-' || lpad(rang::text, 6, '0');
  ELSIF NEW.number IS DISTINCT FROM OLD.number THEN
    RAISE EXCEPTION 'Le numéro d''une écriture ne se modifie pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ecriture_numerotation ON comptabilite_ecriture;
CREATE TRIGGER trg_ecriture_numerotation
  BEFORE INSERT OR UPDATE ON comptabilite_ecriture
  FOR EACH ROW EXECUTE FUNCTION comptabilite_ecriture_numerotation();

CREATE OR REPLACE FUNCTION comptabilite_compteur_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Le compteur de numérotation ne se supprime pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.org_id, NEW.journal_id, NEW.exercice_id) IS DISTINCT FROM
     (OLD.org_id, OLD.journal_id, OLD.exercice_id) THEN
    RAISE EXCEPTION 'Le compteur de numérotation ne change pas de journal ni d''exercice'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.dernier <> OLD.dernier + 1 THEN
    RAISE EXCEPTION 'Le compteur de numérotation ne s''incrémente que de 1 (%, puis %)',
      OLD.dernier, NEW.dernier USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_compteur_garde ON comptabilite_compteur;
CREATE TRIGGER trg_compteur_garde
  BEFORE UPDATE OR DELETE ON comptabilite_compteur
  FOR EACH ROW EXECUTE FUNCTION comptabilite_compteur_garde();
"""
NUMEROTATION_INVERSE = """
DROP TRIGGER IF EXISTS trg_compteur_garde ON comptabilite_compteur;
DROP TRIGGER IF EXISTS trg_ecriture_numerotation ON comptabilite_ecriture;
DROP FUNCTION IF EXISTS comptabilite_compteur_garde();
DROP FUNCTION IF EXISTS comptabilite_ecriture_numerotation();
"""


class Migration(migrations.Migration):
    dependencies = [("comptabilite", "0005_compteur")]

    operations = [
        migrations.RunSQL(NUMEROTATION, reverse_sql=NUMEROTATION_INVERSE),
        migrations.RunSQL(
            activer_rls("comptabilite_compteur"), reverse_sql=desactiver_rls("comptabilite_compteur")
        ),
    ]
