from django.db import migrations

# Deux garanties, posées EN BASE et valables pour tout rôle, propriétaire compris :
#
# 1. Une écriture comptabilisée (`posted`) ou verrouillée (`locked`) ne se modifie ni ne se
#    supprime, ni elle ni ses lignes : on corrige par contre-passation. Seule exception, le
#    passage `posted` -> `locked`, qui ne change que le statut : verrouiller n'est pas écrire.
# 2. On n'écrit rien dans une période qui n'est pas `ouverte`. Cela vaut aussi pour le
#    brouillon resté dans une période devenue close, qui se trouve figé.
#
# La date comptable doit en outre tomber dans la période de l'écriture, et la période
# appartenir à l'exercice de l'écriture.
#
# Le plan prévoyait aussi de retirer UPDATE et DELETE au rôle applicatif. On ne le fait pas :
# les brouillons se modifient et se suppriment, et retirer UPDATE au propriétaire d'une table
# lui retire aussi le verrou de clé étrangère (voir la migration des devises).
FONCTIONS = """
CREATE OR REPLACE FUNCTION comptabilite_verifier_periode_ouverte(cible uuid) RETURNS void AS $$
DECLARE
  per record;
BEGIN
  SELECT numero, status INTO per FROM exercices_periode WHERE id = cible;
  IF FOUND AND per.status <> 'ouverte' THEN
    RAISE EXCEPTION 'La période % est % : aucune écriture ne peut y être créée ni modifiée',
      per.numero, per.status USING ERRCODE = 'integrity_constraint_violation';
  END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION comptabilite_ecriture_garde() RETURNS trigger AS $$
DECLARE
  verrouillage boolean := false;
  per record;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') AND OLD.status IN ('posted', 'locked') THEN
    IF TG_OP = 'UPDATE' AND OLD.status = 'posted' AND NEW.status = 'locked'
       AND (to_jsonb(NEW) - 'status' - 'updated_at' - 'updated_by')
         = (to_jsonb(OLD) - 'status' - 'updated_at' - 'updated_by') THEN
      verrouillage := true;
    ELSE
      RAISE EXCEPTION 'Écriture % comptabilisée : modification interdite. Utilisez la contre-passation.',
        OLD.id USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;

  IF NOT verrouillage THEN
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
      PERFORM comptabilite_verifier_periode_ouverte(NEW.periode_id);
    END IF;
    IF TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND OLD.periode_id IS DISTINCT FROM NEW.periode_id) THEN
      PERFORM comptabilite_verifier_periode_ouverte(OLD.periode_id);
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
      SELECT exercice_id, date_debut, date_fin INTO per
        FROM exercices_periode WHERE id = NEW.periode_id;
      IF FOUND THEN
        IF per.exercice_id <> NEW.exercice_id THEN
          RAISE EXCEPTION 'La période de l''écriture n''appartient pas à son exercice'
            USING ERRCODE = 'integrity_constraint_violation';
        END IF;
        IF NEW.accounting_date < per.date_debut OR NEW.accounting_date > per.date_fin THEN
          RAISE EXCEPTION 'La date comptable % est hors de la période (du % au %)',
            NEW.accounting_date, per.date_debut, per.date_fin
            USING ERRCODE = 'integrity_constraint_violation';
        END IF;
      END IF;
    END IF;
  END IF;

  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION comptabilite_verifier_ecriture_modifiable(cible uuid) RETURNS void AS $$
DECLARE
  courante record;
BEGIN
  SELECT e.status AS statut, p.id AS periode_id INTO courante
    FROM comptabilite_ecriture e JOIN exercices_periode p ON p.id = e.periode_id
   WHERE e.id = cible;
  IF NOT FOUND THEN RETURN; END IF;
  IF courante.statut IN ('posted', 'locked') THEN
    RAISE EXCEPTION 'Écriture % comptabilisée : ses lignes ne se modifient pas. Utilisez la contre-passation.',
      cible USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  PERFORM comptabilite_verifier_periode_ouverte(courante.periode_id);
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION comptabilite_ligne_garde() RETURNS trigger AS $$
BEGIN
  -- L'écriture d'origine ET celle de destination : déplacer une ligne touche les deux.
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

DROP TRIGGER IF EXISTS trg_ecriture_garde ON comptabilite_ecriture;
CREATE TRIGGER trg_ecriture_garde
  BEFORE INSERT OR UPDATE OR DELETE ON comptabilite_ecriture
  FOR EACH ROW EXECUTE FUNCTION comptabilite_ecriture_garde();

DROP TRIGGER IF EXISTS trg_ligne_garde ON comptabilite_ligneecriture;
CREATE TRIGGER trg_ligne_garde
  BEFORE INSERT OR UPDATE OR DELETE ON comptabilite_ligneecriture
  FOR EACH ROW EXECUTE FUNCTION comptabilite_ligne_garde();
"""
FONCTIONS_INVERSE = """
DROP TRIGGER IF EXISTS trg_ligne_garde ON comptabilite_ligneecriture;
DROP TRIGGER IF EXISTS trg_ecriture_garde ON comptabilite_ecriture;
DROP FUNCTION IF EXISTS comptabilite_ligne_garde();
DROP FUNCTION IF EXISTS comptabilite_verifier_ecriture_modifiable(uuid);
DROP FUNCTION IF EXISTS comptabilite_ecriture_garde();
DROP FUNCTION IF EXISTS comptabilite_verifier_periode_ouverte(uuid);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("comptabilite", "0003_equilibre_differe"),
        ("exercices", "0002_rls_chevauchement_verrou"),
    ]

    operations = [migrations.RunSQL(FONCTIONS, reverse_sql=FONCTIONS_INVERSE)]
