-- Amorçage du cluster : schéma applicatif et rôles.
--
-- Cette étape précède les migrations Django. Elle ne décrit pas le schéma
-- métier — elle installe ce dont les migrations ont besoin pour exister :
-- un schéma qui leur appartient et le rôle applicatif auquel elles retirent
-- des droits (voir core/0002_rls_et_audit_inalterable.py).
--
-- Rejouable sans dommage. Exécutée par le rôle PROPRIÉTAIRE.
--   scripts/bootstrap_db.sh
--
-- Pourquoi un schéma dédié plutôt que « public » : sur une instance Supabase,
-- PostgREST sert le schéma « public » au rôle « anon », dont la clé est
-- publique par construction. Tout ce qui vit dans « public » est donc exposé
-- à Internet, et seule la sécurité au niveau ligne s'y oppose. Les tables
-- techniques de Django (sessions, utilisateurs, journal des migrations) n'ont
-- pas de politique d'isolation : elles ne doivent pas s'y trouver. Hors
-- Supabase, le schéma dédié reste une bonne pratique sans coût.

BEGIN;

-- 1. Le schéma applicatif, propriété du rôle qui exécute les migrations.
CREATE SCHEMA IF NOT EXISTS sigf AUTHORIZATION CURRENT_USER;

-- 2. Le rôle applicatif. Aucune création, aucun contournement de la
--    sécurité au niveau ligne : c'est tout l'intérêt de la séparation.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sigf_app') THEN
    CREATE ROLE sigf_app LOGIN;
  END IF;
END
$$;

-- Deux attributs ne sont volontairement pas réaffirmés ici.
--   NOSUPERUSER : sur une instance mutualisée, le rôle propriétaire n'est
--     lui-même pas superutilisateur et n'a donc pas le droit d'y toucher.
--     CREATE ROLE le pose déjà à « non ».
--   NOCREATEDB : l'attribut vaut pour tout le cluster, et la suite de tests
--     crée sa propre base avec ce rôle. L'imposer ici casserait les tests
--     partout pour un gain nul : créer une base ne traverse aucune isolation.
-- NOBYPASSRLS, lui, est réaffirmé : c'est le seul qui, perdu, ouvrirait
-- toutes les organisations les unes aux autres.
ALTER ROLE sigf_app NOCREATEROLE NOBYPASSRLS NOINHERIT LOGIN;
ALTER ROLE sigf_app SET search_path = sigf, public;

-- 3. Il voit le schéma applicatif, et rien d'autre.
GRANT USAGE ON SCHEMA sigf TO sigf_app;
REVOKE CREATE ON SCHEMA sigf FROM sigf_app;

-- 4. Les tables que les migrations créeront ensuite lui seront lisibles et
--    modifiables — mais jamais modifiables dans leur structure.
ALTER DEFAULT PRIVILEGES FOR ROLE CURRENT_USER IN SCHEMA sigf
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sigf_app;
ALTER DEFAULT PRIVILEGES FOR ROLE CURRENT_USER IN SCHEMA sigf
  GRANT USAGE, SELECT ON SEQUENCES TO sigf_app;

-- 5. Les rôles d'API de Supabase n'ont rien à faire ici. « service_role »
--    contourne la sécurité au niveau ligne : lui ouvrir ce schéma reviendrait
--    à annuler l'isolation par organisation d'un seul GRANT.
DO $$
DECLARE
  role_api text;
BEGIN
  FOREACH role_api IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_api) THEN
      EXECUTE format('REVOKE ALL ON SCHEMA sigf FROM %I', role_api);
      EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE CURRENT_USER IN SCHEMA sigf '
        'REVOKE ALL ON TABLES FROM %I', role_api);
      EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE CURRENT_USER IN SCHEMA sigf '
        'REVOKE ALL ON SEQUENCES FROM %I', role_api);
    END IF;
  END LOOP;
END
$$;

REVOKE ALL ON SCHEMA sigf FROM PUBLIC;

COMMIT;
