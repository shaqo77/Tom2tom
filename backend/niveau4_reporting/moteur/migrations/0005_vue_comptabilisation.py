import importlib

from django.db import migrations

# La régénération par différentiel (L6-T04) doit NOMMER les écritures arrivées depuis la publication
# d'un rapport : il lui faut la date de comptabilisation et le lien de contre-passation. Colonnes
# AJOUTÉES à la fin ; les existantes, leur ordre et `security_invoker` ne bougent pas.
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
       e.label AS libelle_ecriture, l.line_no AS ligne_no, l.label AS libelle_ligne,
       e.posted_at AS comptabilisee_le, e.reverses_id AS contrepasse_ecriture_id
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


def _vue_precedente():
    return importlib.import_module(
        "niveau4_reporting.moteur.migrations.0004_vue_colonnes_restitutions"
    )


class Migration(migrations.Migration):
    dependencies = [("moteur", "0004_vue_colonnes_restitutions")]

    operations = [
        migrations.RunSQL(
            VUE, reverse_sql="DROP VIEW IF EXISTS moteur_ligneecriture;" + _vue_precedente().VUE
        ),
    ]
