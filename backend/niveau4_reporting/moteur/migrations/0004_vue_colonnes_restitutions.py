import importlib

from django.db import migrations

# Les restitutions (L3-T09) listent des lignes : elles ont besoin du numéro de pièce, du journal et
# des libellés. On AJOUTE ces colonnes à la fin de la vue ; les colonnes existantes, leur ordre et
# `security_invoker` ne bougent pas, donc le compilateur, le mapping et la traçabilité ne voient
# aucune différence. CREATE OR REPLACE VIEW conserve les droits déjà accordés.
VUE = """
CREATE OR REPLACE VIEW moteur_ligneecriture WITH (security_invoker = true) AS
SELECT l.id, l.org_id, l.project_id,
       x.annee AS fiscal_year, p.numero AS period, e.accounting_date,
       c.code AS compte, t.code AS tiers,
       d1.code AS dim1, d2.code AS dim2, d3.code AS dim3, d4.code AS dim4,
       l.agreement_id::text AS accord,
       l.category_id::text AS categorie,
       l.site_id::text AS site,
       l.debit, l.credit, l.currency_id AS devise, l.fx_rate AS taux,
       l.created_at, l.updated_at,
       e.id AS ecriture_id, e.number AS numero, j.code AS journal,
       e.label AS libelle_ecriture, l.line_no AS ligne_no, l.label AS libelle_ligne
  FROM comptabilite_ligneecriture l
  JOIN comptabilite_ecriture e ON e.id = l.entry_id
  JOIN comptabilite_journal j ON j.id = e.journal_id
  JOIN exercices_periode p ON p.id = e.periode_id
  JOIN exercices_exercice x ON x.id = p.exercice_id
  JOIN referentiels_compte c ON c.id = l.account_id
  LEFT JOIN referentiels_tiers t ON t.id = l.partner_id
  LEFT JOIN referentiels_valeurdimension d1 ON d1.id = l.dim1_id
  LEFT JOIN referentiels_valeurdimension d2 ON d2.id = l.dim2_id
  LEFT JOIN referentiels_valeurdimension d3 ON d3.id = l.dim3_id
  LEFT JOIN referentiels_valeurdimension d4 ON d4.id = l.dim4_id
 WHERE e.status IN ('posted', 'locked');

"""


def _ancienne_vue():
    return importlib.import_module("niveau4_reporting.moteur.migrations.0003_vue_grand_livre")


class Migration(migrations.Migration):
    dependencies = [
        ("moteur", "0003_vue_grand_livre"),
        ("comptabilite", "0014_anouveau_garde_fous"),
    ]

    operations = [
        migrations.RunSQL(
            VUE,
            # Retirer des colonnes impose de recréer la vue ; on reprend la définition de 0003.
            reverse_sql="DROP VIEW IF EXISTS moteur_ligneecriture;" + _ancienne_vue().VUE,
        ),
    ]
