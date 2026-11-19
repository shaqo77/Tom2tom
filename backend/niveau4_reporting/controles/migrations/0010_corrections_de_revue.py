from django.db import migrations

# Corrections issues de la revue de code de L6 :
# - la liste fermée des opérations d'une étape oubliait `voir_numero_compte` ;
# - une personne ne signe qu'une étape d'une même demande (la contrainte unique est posée par le
#   modèle ; ici, la liste des opérations).
SQL = """
ALTER TABLE controles_etapecircuit DROP CONSTRAINT etape_operation_fermee;
ALTER TABLE controles_etapecircuit ADD CONSTRAINT etape_operation_fermee CHECK (
  operation IN ('consulter','saisir','valider','comptabiliser','parametrer','exporter','publier',
                'voir_numero_compte')
);
"""
SQL_INVERSE = """
ALTER TABLE controles_etapecircuit DROP CONSTRAINT etape_operation_fermee;
ALTER TABLE controles_etapecircuit ADD CONSTRAINT etape_operation_fermee CHECK (
  operation IN ('consulter','saisir','valider','comptabiliser','parametrer','exporter','publier')
);
"""


class Migration(migrations.Migration):
    dependencies = [("controles", "0009_circuit_garde_fous")]

    operations = [migrations.RunSQL(SQL, reverse_sql=SQL_INVERSE)]
