"""Types monétaires. Voir 03_GUIDE_DEMARRAGE.md §B.1.

Règle absolue : aucun montant ne touche jamais un float.
"""

from django.db import models


class MontantField(models.DecimalField):
    """Montant monétaire : 20 chiffres, 4 décimales. À utiliser PARTOUT."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 20)
        kwargs.setdefault("decimal_places", 4)
        super().__init__(**kwargs)


class TauxField(models.DecimalField):
    """Taux de change : précision supérieure, une conversion ne doit pas perdre."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 20)
        kwargs.setdefault("decimal_places", 10)
        super().__init__(**kwargs)
