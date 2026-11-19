from django.db import migrations

# L'avis « avenant » appartient à la vie du contrat : il ne conditionne ni l'engagement ni la
# conclusion du contrat. « Avis suffisant » ne regarde donc que les autres objets.
SQL = """
CREATE OR REPLACE FUNCTION marches_avis_suffisant(p_ligne uuid) RETURNS boolean AS $$
  SELECT NOT l.non_objection_requise OR (
    EXISTS (SELECT 1 FROM marches_avisnonobjection a
            WHERE a.ligne_id = l.id AND a.objet <> 'avenant')
    AND NOT EXISTS (
      SELECT 1 FROM marches_avisnonobjection a
      WHERE a.ligne_id = l.id AND a.objet <> 'avenant' AND a.statut <> 'obtenu'
        AND NOT EXISTS (
          SELECT 1 FROM marches_avisnonobjection b
          WHERE b.ligne_id = a.ligne_id AND b.objet = a.objet AND b.statut = 'obtenu'
            AND b.created_at > a.created_at))
  )
  FROM marches_lignepassation l WHERE l.id = p_ligne;
$$ LANGUAGE sql STABLE;
"""
SQL_INVERSE = """
CREATE OR REPLACE FUNCTION marches_avis_suffisant(p_ligne uuid) RETURNS boolean AS $$
  SELECT NOT l.non_objection_requise OR (
    EXISTS (SELECT 1 FROM marches_avisnonobjection a WHERE a.ligne_id = l.id)
    AND NOT EXISTS (
      SELECT 1 FROM marches_avisnonobjection a
      WHERE a.ligne_id = l.id AND a.statut <> 'obtenu'
        AND NOT EXISTS (
          SELECT 1 FROM marches_avisnonobjection b
          WHERE b.ligne_id = a.ligne_id AND b.objet = a.objet AND b.statut = 'obtenu'
            AND b.created_at > a.created_at))
  )
  FROM marches_lignepassation l WHERE l.id = p_ligne;
$$ LANGUAGE sql STABLE;
"""


class Migration(migrations.Migration):
    dependencies = [("marches", "0006_contrats_garde_fous")]

    operations = [migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE)]
