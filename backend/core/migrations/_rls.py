"""Fabrique le SQL d'isolation par organisation. Voir 03_GUIDE_DEMARRAGE.md §B.4."""


def activer_rls(nom_table: str) -> str:
    return f"""
    ALTER TABLE {nom_table} ENABLE ROW LEVEL SECURITY;
    ALTER TABLE {nom_table} FORCE  ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS org_isolation ON {nom_table};
    CREATE POLICY org_isolation ON {nom_table}
      USING      (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid)
      WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), '')::uuid);
    """


def desactiver_rls(nom_table: str) -> str:
    return f"""
    DROP POLICY IF EXISTS org_isolation ON {nom_table};
    ALTER TABLE {nom_table} NO FORCE ROW LEVEL SECURITY;
    ALTER TABLE {nom_table} DISABLE ROW LEVEL SECURITY;
    """
