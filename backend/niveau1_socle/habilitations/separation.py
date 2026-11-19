"""Séparation des tâches. Voir L1-T06 et architecture §8.

Un même utilisateur ne peut pas saisir ET valider la même pièce. La règle est
paramétrable par organisation (`Organisation.separation_des_taches`) et
ACTIVÉE PAR DÉFAUT. Elle s'applique au serveur, en plus de l'habilitation :
être habilité à valider ne suffit pas à valider sa propre pièce.
"""

from rest_framework.exceptions import PermissionDenied

from core.i18n import msg
from niveau1_socle.organisations.models import Organisation

MESSAGE = msg("separation.valider_sa_propre_saisie")


def exiger_separation_des_taches(utilisateur, auteur_id) -> None:
    """Refuse (403) que l'auteur d'une pièce la valide, si l'organisation l'impose.

    Une pièce sans auteur connu (`auteur_id` nul : pièce importée) n'a personne à
    comparer : la règle ne se déclenche pas. L'organisation est lue sous la RLS
    du périmètre courant.
    """
    if auteur_id is None or utilisateur.id != auteur_id:
        return
    organisation = Organisation.objects.filter(pk=utilisateur.org_id).first()
    # Organisation illisible : on garde la règle (défaut sûr).
    if organisation is None or organisation.separation_des_taches:
        raise PermissionDenied(MESSAGE)
