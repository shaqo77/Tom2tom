"""Export d'une demande de retrait vers le format d'un bailleur (formulaires BAD A1, A2, A3). Lot 8.

La CORRESPONDANCE entre ce que l'application sait et les rubriques du formulaire est une DONNÉE
(`niveau2_profils/catalogue/<bailleur>_format_export.json`), pas du code : ajouter un bailleur,
c'est déposer un fichier. Le code ne connaît qu'une liste FERMÉE de sources (`sources.py`), jamais
une expression.

Sans le formulaire officiel éditable de la Banque, le fichier produit est toujours marqué
« DOCUMENT NON OFFICIEL » : il sert à reporter les chiffres sur le formulaire de la Banque, il ne
le remplace pas.
"""

from .export import FormatInapplicable, FormatInconnu, export_demande, formats_disponibles

__all__ = ["FormatInapplicable", "FormatInconnu", "export_demande", "formats_disponibles"]
