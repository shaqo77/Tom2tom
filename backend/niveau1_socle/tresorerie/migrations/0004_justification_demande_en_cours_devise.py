"""Justification du compte spécial : demande en cours et devise. Voir L11-D5.

La garde de la base évolue : une justification peut porter sur une demande encore PRÉPARÉE (le
formulaire l'accompagne), et le compte et l'accord de la demande ont la MÊME devise.
"""

import importlib
import re

from django.db import migrations

ANCIEN = importlib.import_module(
    "niveau1_socle.tresorerie.migrations.0003_justification_compte_special"
).SQL
DEBUT = "CREATE OR REPLACE FUNCTION tresorerie_justifcs_garde()"
FIN = "$$ LANGUAGE plpgsql;"
# La fonction seule : le déclencheur qui l'appelle existe déjà (0003).
FONCTION_ANCIENNE = ANCIEN[ANCIEN.index(DEBUT) : ANCIEN.index(FIN, ANCIEN.index(DEBUT)) + len(FIN)]

FONCTION = FONCTION_ANCIENNE.replace(
    "IF d.status NOT IN ('soumise', 'acceptee', 'contestee', 'remboursee') THEN\n"
    "    RAISE EXCEPTION 'Seule une demande soumise à la Banque se justifie (demande %)', d.numero",
    "IF d.status NOT IN ('preparee', 'soumise', 'acceptee', 'contestee', 'remboursee') THEN\n"
    "    RAISE EXCEPTION 'Une demande rejetée ou annulée ne se justifie pas (demande %)', d.numero",
).replace(
    "  SELECT COALESCE(sum(montant_a_retirer), 0) INTO total",
    "  IF NOT EXISTS (SELECT 1 FROM financements_accord a\n"
    "                  WHERE a.id = d.accord_id AND a.devise_id = c.devise_id) THEN\n"
    "    RAISE EXCEPTION 'Le compte % et l''accord de la demande % n''ont pas la même devise',\n"
    "      c.code, d.numero USING ERRCODE = 'integrity_constraint_violation';\n"
    "  END IF;\n"
    "  SELECT COALESCE(sum(montant_a_retirer), 0) INTO total",
)
assert FONCTION != FONCTION_ANCIENNE and re.search("preparee", FONCTION) and "même devise" in FONCTION


class Migration(migrations.Migration):
    dependencies = [("tresorerie", "0003_justification_compte_special")]

    operations = [migrations.RunSQL(FONCTION, reverse_sql=FONCTION_ANCIENNE)]
