from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

SQL = """
-- Le compteur d'un accord ne décroît jamais et ne se supprime pas : un numéro annulé n'est jamais
-- réattribué (manuel BAD). Il ne change ni d'accord ni d'organisation.
CREATE OR REPLACE FUNCTION financements_compteur_demande_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un compteur de demandes ne se supprime pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.derniere_sequence < OLD.derniere_sequence THEN
    RAISE EXCEPTION 'Un compteur de demandes ne décroît jamais : un numéro n''est pas réattribué'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.accord_id, NEW.org_id) IS DISTINCT FROM (OLD.accord_id, OLD.org_id) THEN
    RAISE EXCEPTION 'Un compteur de demandes ne change ni d''accord ni d''organisation'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER financements_compteur_demande_garde BEFORE UPDATE OR DELETE
  ON financements_compteurdemande
  FOR EACH ROW EXECUTE FUNCTION financements_compteur_demande_garde();

-- L'accord activé ne change plus que de statut, SAUF le format de numérotation des demandes
-- (`format_numero_demande`, `suffixe_agence`), tant qu'aucune demande n'existe : règle 7.
CREATE OR REPLACE FUNCTION financements_accord_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'brouillon' OR financements_accord_utilise(OLD.id)
       OR EXISTS (SELECT 1 FROM financements_categorie WHERE accord_id = OLD.id)
       OR EXISTS (SELECT 1 FROM financements_avenantaccord WHERE accord_id = OLD.id)
       OR EXISTS (SELECT 1 FROM financements_comptebancaire WHERE accord_id = OLD.id) THEN
      RAISE EXCEPTION 'Un accord activé ou portant des opérations ne se supprime jamais'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN OLD;
  END IF;

  IF OLD.status IN ('clos', 'annule') THEN
    RAISE EXCEPTION 'Un accord % est figé', OLD.status
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.status <> OLD.status AND NOT (
       (OLD.status = 'brouillon' AND NEW.status IN ('actif', 'annule'))
    OR (OLD.status = 'actif' AND NEW.status IN ('suspendu', 'clos', 'annule'))
    OR (OLD.status = 'suspendu' AND NEW.status IN ('actif', 'clos'))) THEN
    RAISE EXCEPTION 'Transition d''accord interdite : % vers %', OLD.status, NEW.status
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.status = 'annule' AND OLD.status <> 'brouillon' AND financements_accord_utilise(OLD.id) THEN
    RAISE EXCEPTION 'Un accord portant des opérations ne s''annule pas : on le clôt'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.format_numero_demande, NEW.suffixe_agence)
       IS DISTINCT FROM (OLD.format_numero_demande, OLD.suffixe_agence)
     AND EXISTS (SELECT 1 FROM decaissements_demanderetrait WHERE accord_id = OLD.id) THEN
    RAISE EXCEPTION 'Le format de numérotation ne change plus : l''accord a déjà des demandes'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.status <> 'brouillon'
     AND (to_jsonb(NEW) - 'status' - 'updated_at' - 'updated_by'
          - 'format_numero_demande' - 'suffixe_agence')
      <> (to_jsonb(OLD) - 'status' - 'updated_at' - 'updated_by'
          - 'format_numero_demande' - 'suffixe_agence') THEN
    RAISE EXCEPTION 'Un accord activé ne change plus que de statut : un avenant porte les nouvelles valeurs'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS financements_compteur_demande_garde ON financements_compteurdemande;
DROP FUNCTION IF EXISTS financements_compteur_demande_garde();
"""


class Migration(migrations.Migration):
    # La garde de l'accord (fonction ci-dessus) n'est pas restaurée à l'ancienne version au retour
    # arrière : elle est plus stricte ou égale, jamais plus laxiste pour les autres colonnes.
    dependencies = [
        ("financements", "0005_numerotation_des_demandes"),
        ("decaissements", "0005_numero_unique_par_accord"),
    ]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        migrations.RunSQL(
            activer_rls("financements_compteurdemande"),
            reverse_sql=desactiver_rls("financements_compteurdemande"),
        ),
    ]
