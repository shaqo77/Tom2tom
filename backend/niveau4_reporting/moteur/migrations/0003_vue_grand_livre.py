from django.db import migrations

# Le moteur d'états lit « moteur_ligneecriture » avec les noms de colonnes du prototype
# L0 : comptes et axes en codes texte, période en numéro. Cette vue les expose depuis le
# vrai grand livre, sans toucher au compilateur, au mapping ni à la traçabilité.
#
# - security_invoker : la vue s'exécute avec les droits de l'APPELANT, donc sous la RLS
#   des tables sous-jacentes. Sans cette option, une vue contourne la RLS de son
#   propriétaire et ouvrirait toutes les organisations les unes aux autres.
# - Seules les écritures comptabilisées ou verrouillées alimentent les états.
# - Accord, catégorie et site n'ont pas encore de référentiel (L4) : ils s'exposent en
#   texte d'UUID. L4 les rebranchera sur leurs codes.
VUE = """
CREATE VIEW moteur_ligneecriture WITH (security_invoker = true) AS
SELECT l.id, l.org_id, l.project_id,
       x.annee AS fiscal_year, p.numero AS period, e.accounting_date,
       c.code AS compte, t.code AS tiers,
       d1.code AS dim1, d2.code AS dim2, d3.code AS dim3, d4.code AS dim4,
       l.agreement_id::text AS accord,
       l.category_id::text AS categorie,
       l.site_id::text AS site,
       l.debit, l.credit, l.currency_id AS devise, l.fx_rate AS taux,
       l.created_at, l.updated_at
  FROM comptabilite_ligneecriture l
  JOIN comptabilite_ecriture e ON e.id = l.entry_id
  JOIN exercices_periode p ON p.id = e.periode_id
  JOIN exercices_exercice x ON x.id = p.exercice_id
  JOIN referentiels_compte c ON c.id = l.account_id
  LEFT JOIN referentiels_tiers t ON t.id = l.partner_id
  LEFT JOIN referentiels_valeurdimension d1 ON d1.id = l.dim1_id
  LEFT JOIN referentiels_valeurdimension d2 ON d2.id = l.dim2_id
  LEFT JOIN referentiels_valeurdimension d3 ON d3.id = l.dim3_id
  LEFT JOIN referentiels_valeurdimension d4 ON d4.id = l.dim4_id
 WHERE e.status IN ('posted', 'locked');

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sigf_app') THEN
    GRANT SELECT ON moteur_ligneecriture TO sigf_app;
  END IF;
END $$;
"""
VUE_INVERSE = "DROP VIEW IF EXISTS moteur_ligneecriture;"


class Migration(migrations.Migration):
    dependencies = [
        ("moteur", "0002_rls"),
        ("comptabilite", "0002_rls"),
        ("exercices", "0002_rls_chevauchement_verrou"),
        ("referentiels", "0010_correspondance_rls_et_verrou"),
    ]

    operations = [
        # Le prototype L0 disparaît ; il ne contenait que des données générées.
        migrations.DeleteModel(name="LigneEcriture"),
        migrations.RunSQL(VUE, reverse_sql=VUE_INVERSE),
    ]
