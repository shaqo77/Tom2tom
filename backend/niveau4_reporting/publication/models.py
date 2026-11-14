"""Le rapport publié et scellé. Voir L6-T04.

Une ligne est ÉCRITE UNE FOIS et ne change plus : c'est la trace de ce qui a été transmis. Elle
garde de quoi rejouer le rapport tel qu'il a été produit : le modèle d'état en entier (copie, pas
référence : le modèle d'aujourd'hui n'est pas celui d'alors), les paramètres, les versions de
mappings, la configuration, et les valeurs. Le scellé en est l'empreinte (`scellement.py`).
"""

from django.db import models
from django.db.models import Q

from core.models import ModeleOrganisation


class RapportPublie(ModeleOrganisation):
    project_id = models.UUIDField(db_index=True)
    template_code = models.CharField(max_length=64)
    template_version = models.PositiveIntegerField(null=True, blank=True)
    modele = models.JSONField()  # le modèle d'état tel qu'utilisé
    period_from = models.DateField()
    period_to = models.DateField()
    params = models.JSONField(default=dict)
    config_version = models.JSONField(default=dict)
    # {"code de mapping": {"id": uuid, "version": n}}
    mapping_versions = models.JSONField(default=dict)
    dataset_hash = models.BinaryField()
    values = models.JSONField()  # {"rubrique/colonne": "montant canonique"}
    seal = models.BinaryField()
    published_by = models.UUIDField()
    published_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=["project_id", "template_code", "period_to"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(period_from__lte=models.F("period_to")),
                name="rapport_periode_coherente",
            ),
        ]
