from django.db import migrations

# Ajoute l'opération `voir_numero_compte` à l'ensemble fermé des opérations (L4-T04) : elle seule
# donne accès au numéro complet d'un compte bancaire.
ANCIENNE = (
    '["consulter","saisir","valider","comptabiliser","parametrer","exporter","publier"]'
)
NOUVELLE = (
    '["consulter","saisir","valider","comptabiliser","parametrer","exporter","publier",'
    '"voir_numero_compte"]'
)


def _contrainte(liste: str) -> str:
    return f"""
    ALTER TABLE habilitations_role DROP CONSTRAINT role_operations_connues;
    ALTER TABLE habilitations_role ADD CONSTRAINT role_operations_connues CHECK (
      jsonb_typeof(operations) = 'array' AND operations <@ '{liste}'::jsonb
    );
    """


class Migration(migrations.Migration):
    dependencies = [("habilitations", "0002_rls_et_operations")]

    operations = [migrations.RunSQL(_contrainte(NOUVELLE), reverse_sql=_contrainte(ANCIENNE))]
