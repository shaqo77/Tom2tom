"""Modèle de lignes d'écriture — version L0.

Ce modèle est PROVISOIRE : il sera remplacé en L3 par le grand livre
complet (écriture + ligne). Il existe pour que le moteur d'états puisse
être construit et mesuré avant la comptabilité, conformément à L0.
"""

from django.db import models

from core.fields import MontantField, TauxField
from core.models import ModeleOrganisation


class LigneEcriture(ModeleOrganisation):
    project_id = models.UUIDField(db_index=True)
    fiscal_year = models.IntegerField()
    period = models.IntegerField()  # 1..12
    accounting_date = models.DateField()

    compte = models.CharField(max_length=20, db_index=True)
    tiers = models.CharField(max_length=20, null=True, blank=True)

    dim1 = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    dim2 = models.CharField(max_length=20, null=True, blank=True)
    dim3 = models.CharField(max_length=20, null=True, blank=True)
    dim4 = models.CharField(max_length=20, null=True, blank=True)

    accord = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    categorie = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    site = models.CharField(max_length=20, null=True, blank=True)

    debit = MontantField(default=0)
    credit = MontantField(default=0)
    devise = models.CharField(max_length=3)
    taux = TauxField(default=1)

    class Meta:
        db_table = "moteur_ligneecriture"
        indexes = [
            models.Index(
                fields=["org_id", "project_id", "fiscal_year", "compte", "dim1", "accord"],
                name="idx_lignes_agregation",
            ),
        ]
