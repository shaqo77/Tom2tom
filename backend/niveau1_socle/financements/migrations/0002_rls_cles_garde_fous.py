from django.db import migrations

from core.migrations._rls import activer_rls, desactiver_rls

TABLES = (
    "financements_bailleur",
    "financements_accord",
    "financements_categorie",
    "financements_avenantaccord",
    "financements_comptebancaire",
)

# 1. Clés étrangères COMPOSITES (org_id, id) : un accord, une catégorie, un compte ne peuvent pas
#    pointer vers le bailleur, le projet ou l'accord d'une AUTRE organisation. La RLS filtre ce
#    qu'on lit et écrit, pas ce que vérifie une clé étrangère : sans ceci, un identifiant connu
#    d'une autre organisation passerait.
CLES = """
ALTER TABLE organisations_projet ADD CONSTRAINT uq_projet_org_id UNIQUE (org_id, id);
ALTER TABLE financements_bailleur ADD CONSTRAINT uq_bailleur_org_id UNIQUE (org_id, id);
ALTER TABLE financements_accord ADD CONSTRAINT uq_accord_org_id UNIQUE (org_id, id);

ALTER TABLE financements_accord ADD CONSTRAINT fk_accord_bailleur_meme_org
  FOREIGN KEY (org_id, bailleur_id) REFERENCES financements_bailleur (org_id, id);
ALTER TABLE financements_accord ADD CONSTRAINT fk_accord_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
ALTER TABLE financements_categorie ADD CONSTRAINT fk_categorie_accord_meme_org
  FOREIGN KEY (org_id, accord_id) REFERENCES financements_accord (org_id, id);
ALTER TABLE financements_avenantaccord ADD CONSTRAINT fk_avenant_accord_meme_org
  FOREIGN KEY (org_id, accord_id) REFERENCES financements_accord (org_id, id);
ALTER TABLE financements_comptebancaire ADD CONSTRAINT fk_compte_accord_meme_org
  FOREIGN KEY (org_id, accord_id) REFERENCES financements_accord (org_id, id);
ALTER TABLE financements_comptebancaire ADD CONSTRAINT fk_compte_projet_meme_org
  FOREIGN KEY (org_id, project_id) REFERENCES organisations_projet (org_id, id);
"""
CLES_INVERSE = """
ALTER TABLE financements_comptebancaire DROP CONSTRAINT fk_compte_projet_meme_org;
ALTER TABLE financements_comptebancaire DROP CONSTRAINT fk_compte_accord_meme_org;
ALTER TABLE financements_avenantaccord DROP CONSTRAINT fk_avenant_accord_meme_org;
ALTER TABLE financements_categorie DROP CONSTRAINT fk_categorie_accord_meme_org;
ALTER TABLE financements_accord DROP CONSTRAINT fk_accord_projet_meme_org;
ALTER TABLE financements_accord DROP CONSTRAINT fk_accord_bailleur_meme_org;
ALTER TABLE financements_accord DROP CONSTRAINT uq_accord_org_id;
ALTER TABLE financements_bailleur DROP CONSTRAINT uq_bailleur_org_id;
ALTER TABLE organisations_projet DROP CONSTRAINT uq_projet_org_id;
"""

# 2. Garde-fous. « Utilisé » = référencé par une ligne d'écriture, une ligne de budget ou un
#    engagement.
GARDE = """
CREATE OR REPLACE FUNCTION financements_accord_utilise(cible uuid) RETURNS boolean AS $$
  SELECT EXISTS (SELECT 1 FROM comptabilite_ligneecriture WHERE agreement_id = cible)
      OR EXISTS (SELECT 1 FROM budget_lignebudget WHERE agreement_id = cible)
      OR EXISTS (SELECT 1 FROM budget_engagement WHERE agreement_id = cible);
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION financements_categorie_utilisee(cible uuid) RETURNS boolean AS $$
  SELECT EXISTS (SELECT 1 FROM comptabilite_ligneecriture WHERE category_id = cible)
      OR EXISTS (SELECT 1 FROM budget_lignebudget WHERE category_id = cible)
      OR EXISTS (SELECT 1 FROM budget_engagement WHERE category_id = cible);
$$ LANGUAGE sql STABLE;

-- Accord : transitions fermées, figé une fois activé, jamais supprimé s'il porte des opérations.
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
  IF OLD.status <> 'brouillon'
     AND (to_jsonb(NEW) - 'status' - 'updated_at' - 'updated_by')
      <> (to_jsonb(OLD) - 'status' - 'updated_at' - 'updated_by') THEN
    RAISE EXCEPTION 'Un accord activé ne change plus que de statut : un avenant porte les nouvelles valeurs'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER financements_accord_garde
  BEFORE UPDATE OR DELETE ON financements_accord
  FOR EACH ROW EXECUTE FUNCTION financements_accord_garde();

-- Avenant : jamais modifié ni supprimé ; sur un accord vivant ; document de l'accord, de même projet.
CREATE OR REPLACE FUNCTION financements_avenant_garde() RETURNS trigger AS $$
DECLARE
  statut text;
  projet_accord uuid;
  projet_document uuid;
  genre text;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    RAISE EXCEPTION 'Un avenant ne se modifie ni ne se supprime : on en ajoute un autre'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT status, project_id INTO statut, projet_accord
    FROM financements_accord WHERE id = NEW.accord_id;
  IF statut NOT IN ('actif', 'suspendu') THEN
    RAISE EXCEPTION 'Un avenant porte sur un accord actif ou suspendu, pas %', statut
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT project_id, kind INTO projet_document, genre
    FROM niveau3_config_documentreference WHERE id = NEW.document_id;
  IF genre IS DISTINCT FROM 'financing_agreement' OR projet_document IS DISTINCT FROM projet_accord THEN
    RAISE EXCEPTION 'Le document d''un avenant est un accord de financement du même projet'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER financements_avenant_garde
  BEFORE INSERT OR UPDATE OR DELETE ON financements_avenantaccord
  FOR EACH ROW EXECUTE FUNCTION financements_avenant_garde();

-- Catégorie : sous-catégorie dans le même accord, plafond sous celui du parent, immuable une fois
-- utilisée (hors libellé), jamais supprimée si utilisée.
CREATE OR REPLACE FUNCTION financements_categorie_garde() RETURNS trigger AS $$
DECLARE
  parent record;
  statut text;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF financements_categorie_utilisee(OLD.id)
       OR EXISTS (SELECT 1 FROM financements_categorie WHERE parent_id = OLD.id) THEN
      RAISE EXCEPTION 'Une catégorie utilisée ou parente ne se supprime pas'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN OLD;
  END IF;
  SELECT status INTO statut FROM financements_accord WHERE id = NEW.accord_id;
  IF statut IN ('clos', 'annule') THEN
    RAISE EXCEPTION 'On ne touche plus aux catégories d''un accord %', statut
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF NEW.accord_id <> OLD.accord_id OR NEW.code <> OLD.code
       OR NEW.parent_id IS DISTINCT FROM OLD.parent_id THEN
      RAISE EXCEPTION 'Une catégorie ne change ni d''accord, ni de code, ni de parent'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF financements_categorie_utilisee(OLD.id)
       AND (to_jsonb(NEW) - 'label' - 'updated_at' - 'updated_by')
        <> (to_jsonb(OLD) - 'label' - 'updated_at' - 'updated_by') THEN
      RAISE EXCEPTION 'Cette catégorie est utilisée : seul son libellé change'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  IF NEW.parent_id IS NOT NULL THEN
    SELECT accord_id, plafond INTO parent FROM financements_categorie WHERE id = NEW.parent_id;
    IF parent.accord_id IS DISTINCT FROM NEW.accord_id THEN
      RAISE EXCEPTION 'Une sous-catégorie appartient au même accord que sa catégorie'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF parent.plafond IS NOT NULL AND NEW.plafond IS NOT NULL AND NEW.plafond > parent.plafond THEN
      RAISE EXCEPTION 'Le plafond d''une sous-catégorie ne dépasse pas celui de sa catégorie'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER financements_categorie_garde
  BEFORE INSERT OR UPDATE OR DELETE ON financements_categorie
  FOR EACH ROW EXECUTE FUNCTION financements_categorie_garde();

-- Compte bancaire : l'accord d'un compte est du même projet ; un compte référencé ne se supprime pas.
CREATE OR REPLACE FUNCTION financements_compte_garde() RETURNS trigger AS $$
DECLARE
  projet_accord uuid;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF EXISTS (SELECT 1 FROM comptabilite_ligneecriture WHERE bank_account_id = OLD.id) THEN
      RAISE EXCEPTION 'Un compte bancaire portant des opérations ne se supprime pas : on le désactive'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF NEW.accord_id IS NOT NULL THEN
    SELECT project_id INTO projet_accord FROM financements_accord WHERE id = NEW.accord_id;
    IF projet_accord IS DISTINCT FROM NEW.project_id THEN
      RAISE EXCEPTION 'Le compte et son accord appartiennent au même projet'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER financements_compte_garde
  BEFORE INSERT OR UPDATE OR DELETE ON financements_comptebancaire
  FOR EACH ROW EXECUTE FUNCTION financements_compte_garde();
"""
GARDE_INVERSE = """
DROP TRIGGER IF EXISTS financements_compte_garde ON financements_comptebancaire;
DROP TRIGGER IF EXISTS financements_categorie_garde ON financements_categorie;
DROP TRIGGER IF EXISTS financements_avenant_garde ON financements_avenantaccord;
DROP TRIGGER IF EXISTS financements_accord_garde ON financements_accord;
DROP FUNCTION IF EXISTS financements_compte_garde();
DROP FUNCTION IF EXISTS financements_categorie_garde();
DROP FUNCTION IF EXISTS financements_avenant_garde();
DROP FUNCTION IF EXISTS financements_accord_garde();
DROP FUNCTION IF EXISTS financements_categorie_utilisee(uuid);
DROP FUNCTION IF EXISTS financements_accord_utilise(uuid);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("financements", "0001_bailleurs_accords"),
        ("organisations", "0004_verrou_sur_grand_livre"),
        ("niveau3_config", "0002_rls_et_empreinte"),
        ("comptabilite", "0014_anouveau_garde_fous"),
        ("budget", "0006_controle_garde_fous"),
    ]

    operations = [
        *(
            migrations.RunSQL(activer_rls(table), reverse_sql=desactiver_rls(table))
            for table in TABLES
        ),
        migrations.RunSQL(CLES, reverse_sql=CLES_INVERSE),
        migrations.RunSQL(GARDE, reverse_sql=GARDE_INVERSE),
    ]
