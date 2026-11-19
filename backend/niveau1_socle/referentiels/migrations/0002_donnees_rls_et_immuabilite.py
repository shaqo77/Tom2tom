from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

from niveau1_socle.referentiels.semences import charger


def charger_devises(apps, schema_editor):
    charger(apps.get_model("referentiels", "Devise"))


def vider_devises(apps, schema_editor):
    apps.get_model("referentiels", "Devise").objects.all().delete()


# Les devises sont un référentiel général : l'application les lit, ne les écrit pas.
# Un déclencheur plutôt qu'un REVOKE : retirer UPDATE au propriétaire de la table
# lui retire aussi le verrou de clé étrangère (FOR KEY SHARE) dont dépendent les
# taux, et le comportement différerait selon que le rôle applicatif possède ou
# non la table (c'est le cas dans la base de test). Le déclencheur se comporte
# partout pareil. Une migration qui ajoute des devises exécute d'abord
# SET LOCAL sigf.ecriture_referentiel = 'on'.
LECTURE_SEULE = """
CREATE OR REPLACE FUNCTION referentiels_devise_lecture_seule() RETURNS trigger AS $$
BEGIN
  IF current_setting('sigf.ecriture_referentiel', true) IS DISTINCT FROM 'on' THEN
    RAISE EXCEPTION 'Le référentiel des devises est en lecture seule : il se modifie par migration'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS devise_lecture_seule ON referentiels_devise;
CREATE TRIGGER devise_lecture_seule
  BEFORE INSERT OR UPDATE OR DELETE ON referentiels_devise
  FOR EACH ROW EXECUTE FUNCTION referentiels_devise_lecture_seule();
"""
LECTURE_SEULE_INVERSE = """
DROP TRIGGER IF EXISTS devise_lecture_seule ON referentiels_devise;
DROP FUNCTION IF EXISTS referentiels_devise_lecture_seule();
"""

# Un taux n'est jamais écrasé ni supprimé : un nouveau taux est une nouvelle ligne.
IMMUABLE = """
CREATE OR REPLACE FUNCTION referentiels_taux_immuable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Un taux n''est jamais écrasé ni supprimé : enregistrez un nouveau taux à une nouvelle date'
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS taux_immuable ON referentiels_taux;
CREATE TRIGGER taux_immuable
  BEFORE UPDATE OR DELETE ON referentiels_taux
  FOR EACH ROW EXECUTE FUNCTION referentiels_taux_immuable();
"""
IMMUABLE_INVERSE = """
DROP TRIGGER IF EXISTS taux_immuable ON referentiels_taux;
DROP FUNCTION IF EXISTS referentiels_taux_immuable();
"""


class Migration(migrations.Migration):
    dependencies = [("referentiels", "0001_devises_taux")]

    operations = [
        migrations.RunPython(charger_devises, vider_devises),
        migrations.RunSQL(LECTURE_SEULE, reverse_sql=LECTURE_SEULE_INVERSE),
        migrations.RunSQL(IMMUABLE, reverse_sql=IMMUABLE_INVERSE),
        migrations.RunSQL(
            activer_rls("referentiels_taux"), reverse_sql=desactiver_rls("referentiels_taux")
        ),
    ]
