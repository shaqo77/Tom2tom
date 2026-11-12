"""Ferme le schéma applicatif à tout rôle qui n'est pas le rôle applicatif.

Deux dangers distincts sont traités ici.

Le premier est général : une table créée avant que les privilèges par défaut
ne soient posés resterait invisible au rôle applicatif. On rattrape donc
explicitement l'existant, puis on retire de nouveau UPDATE et DELETE sur le
journal d'audit — un GRANT large les aurait silencieusement rendus.

Le second est propre à l'hébergement mutualisé. Une instance Supabase
expose une API dont la clé anonyme est publique, et le rôle « service_role »
qui la sert contourne la sécurité au niveau ligne. Un seul GRANT à ce rôle
annulerait l'isolation par organisation sans qu'aucun test applicatif ne
s'en aperçoive. On révoque donc, et la révocation ne coûte rien là où ces
rôles n'existent pas.
"""

from django.db import migrations

CLOISONNER = """
DO $$
DECLARE
  -- Le schéma visé est celui où Django a RÉELLEMENT posé ses tables, résolu
  -- par le chemin de recherche. Prendre current_schema() serait faux dès que
  -- le chemin désigne un schéma encore vide — l'erreur serait alors tardive
  -- et obscure.
  schema_app text := coalesce(
    (SELECT n.nspname
       FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE c.oid = to_regclass('core_auditlog')),
    current_schema());
  objet      record;
  role_api   text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sigf_app') THEN
    RAISE EXCEPTION
      'Le rôle sigf_app est absent. Lancez scripts/bootstrap_db.sh avant les migrations.';
  END IF;

  FOR objet IN
    SELECT tablename AS nom FROM pg_tables WHERE schemaname = schema_app
  LOOP
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I.%I TO sigf_app',
                   schema_app, objet.nom);
  END LOOP;

  FOR objet IN
    SELECT sequencename AS nom FROM pg_sequences WHERE schemaname = schema_app
  LOOP
    EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %I.%I TO sigf_app',
                   schema_app, objet.nom);
  END LOOP;

  -- Le journal d'audit est en ajout seul. Cette ligne doit suivre les GRANT
  -- ci-dessus, sans quoi elle serait défaite par eux.
  EXECUTE format('REVOKE UPDATE, DELETE ON %I.core_auditlog FROM sigf_app', schema_app);
  EXECUTE format('REVOKE UPDATE, DELETE ON %I.core_auditlog FROM PUBLIC', schema_app);

  FOREACH role_api IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_api) THEN
      EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM %I',
                     schema_app, role_api);
      EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA %I FROM %I',
                     schema_app, role_api);
      EXECUTE format('REVOKE ALL ON SCHEMA %I FROM %I', schema_app, role_api);
    END IF;
  END LOOP;

  EXECUTE format('REVOKE ALL ON SCHEMA %I FROM PUBLIC', schema_app);
END
$$;
"""

# Revenir en arrière rendrait des droits qu'on a retirés pour de bonnes
# raisons. On laisse la fermeture en place : elle n'empêche aucune
# migration descendante de se dérouler.
ROUVRIR = ""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_rls_nullif"),
        ("mapping", "0002_rls"),
        ("moteur", "0002_rls"),
    ]

    operations = [migrations.RunSQL(CLOISONNER, reverse_sql=ROUVRIR)]
