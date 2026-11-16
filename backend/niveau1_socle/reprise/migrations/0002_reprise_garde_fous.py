from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = (
    "reprise_reprise",
    "reprise_lignebalanceorigine",
    "reprise_piecereprise",
    "reprise_rapportreprise",
)

SQL = """
ALTER TABLE reprise_reprise ADD CONSTRAINT uq_reprise_org_id UNIQUE (org_id, id);
ALTER TABLE reprise_reprise ADD CONSTRAINT fk_reprise_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE reprise_lignebalanceorigine ADD CONSTRAINT fk_balance_reprise_meme_org
  FOREIGN KEY (org_id, reprise_id) REFERENCES reprise_reprise (org_id, id);
ALTER TABLE reprise_piecereprise ADD CONSTRAINT fk_piece_reprise_meme_org
  FOREIGN KEY (org_id, reprise_id) REFERENCES reprise_reprise (org_id, id);
ALTER TABLE reprise_rapportreprise ADD CONSTRAINT fk_rapport_reprise_meme_org
  FOREIGN KEY (org_id, reprise_id) REFERENCES reprise_reprise (org_id, id);

-- La balance d'origine et les pièces reprises sont en AJOUT SEUL : ce sont les pièces du dossier.
CREATE OR REPLACE FUNCTION reprise_ajout_seul() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION '% est en ajout seul : on ne modifie ni ne supprime une ligne de reprise',
    TG_TABLE_NAME USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER reprise_ajout_seul BEFORE UPDATE OR DELETE ON reprise_lignebalanceorigine
  FOR EACH ROW EXECUTE FUNCTION reprise_ajout_seul();
CREATE TRIGGER reprise_ajout_seul BEFORE UPDATE OR DELETE ON reprise_piecereprise
  FOR EACH ROW EXECUTE FUNCTION reprise_ajout_seul();

-- Une reprise acceptée est définitive ; son identité ne change jamais ; son mode et l'empreinte de
-- sa balance se posent une fois ; elle ne se supprime pas.
CREATE OR REPLACE FUNCTION reprise_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Une reprise ne se supprime pas' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.statut = 'acceptee' THEN
    RAISE EXCEPTION 'Une reprise acceptée est définitive' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.project_id, NEW.date_bascule, NEW.devise, NEW.cree_par)
       IS DISTINCT FROM (OLD.project_id, OLD.date_bascule, OLD.devise, OLD.cree_par) THEN
    RAISE EXCEPTION 'L''identité d''une reprise ne se modifie pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.mode IS NOT NULL AND NEW.mode IS DISTINCT FROM OLD.mode THEN
    RAISE EXCEPTION 'Le mode d''une reprise ne change pas' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.balance_sha256 IS NOT NULL AND NEW.balance_sha256 IS DISTINCT FROM OLD.balance_sha256 THEN
    RAISE EXCEPTION 'La balance d''origine d''une reprise ne change pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER reprise_garde BEFORE UPDATE OR DELETE ON reprise_reprise
  FOR EACH ROW EXECUTE FUNCTION reprise_garde();

-- Un rapport : contenu figé ; seule la signature se pose, une fois ; jamais supprimé.
CREATE OR REPLACE FUNCTION reprise_rapport_garde() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un rapport de reprise ne se supprime pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (NEW.reprise_id, NEW.accepte, NEW.ecart_general, NEW.ecart_accords, NEW.nombre_ecritures,
      NEW.contenu_sha256) IS DISTINCT FROM
     (OLD.reprise_id, OLD.accepte, OLD.ecart_general, OLD.ecart_accords, OLD.nombre_ecritures,
      OLD.contenu_sha256) OR NEW.ecarts IS DISTINCT FROM OLD.ecarts THEN
    RAISE EXCEPTION 'Le contenu d''un rapport de reprise ne se modifie pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.signe_par IS NOT NULL THEN
    RAISE EXCEPTION 'La signature d''un rapport de reprise ne se réécrit pas'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER reprise_rapport_garde BEFORE UPDATE OR DELETE ON reprise_rapportreprise
  FOR EACH ROW EXECUTE FUNCTION reprise_rapport_garde();
"""
SQL_INVERSE = """
DROP TRIGGER IF EXISTS reprise_rapport_garde ON reprise_rapportreprise;
DROP FUNCTION IF EXISTS reprise_rapport_garde();
DROP TRIGGER IF EXISTS reprise_garde ON reprise_reprise;
DROP FUNCTION IF EXISTS reprise_garde();
DROP TRIGGER IF EXISTS reprise_ajout_seul ON reprise_piecereprise;
DROP TRIGGER IF EXISTS reprise_ajout_seul ON reprise_lignebalanceorigine;
DROP FUNCTION IF EXISTS reprise_ajout_seul();
ALTER TABLE reprise_rapportreprise DROP CONSTRAINT fk_rapport_reprise_meme_org;
ALTER TABLE reprise_piecereprise DROP CONSTRAINT fk_piece_reprise_meme_org;
ALTER TABLE reprise_lignebalanceorigine DROP CONSTRAINT fk_balance_reprise_meme_org;
ALTER TABLE reprise_reprise DROP CONSTRAINT fk_reprise_projet_meme_org;
ALTER TABLE reprise_reprise DROP CONSTRAINT uq_reprise_org_id;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("reprise", "0001_reprise_des_donnees"),
        ("controles", "0002_rls_cles_garde_fous"),  # pose uq_projet_org_id via financements
    ]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE),
        *(migrations.RunSQL(activer_rls(t), reverse_sql=desactiver_rls(t)) for t in TABLES),
    ]
