"""L'effet d'un avenant sur le profil de décaissement. Voir L5-T04bis.

Enregistrer un avenant crée, dans la même transaction, la nouvelle version du profil (dates et
allocations de l'avenant) et la lie à l'avenant. La version est créée AVANT l'avenant (son
identifiant est écrit dans l'avenant, qui ne se modifie jamais) puis validée après lui : le
contrôle de complétude compare alors les allocations au montant révisé.

Un accord qui n'a jamais eu de profil reçoit son avenant seul : il n'y a rien à versionner. Un
accord qui a eu un profil mais n'en a aucun en vigueur à la date de l'avenant est refusé.
"""

import datetime
import uuid

from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from niveau1_socle.financements.models import Accord, AvenantAccord
from niveau1_socle.financements.services import creer_avenant
from niveau1_socle.habilitations.permissions import est_habilite

from ..models import DocumentReference
from .activation import ActivationRefusee, activer_profil, valider_profil
from .decaissement import accord_a_un_profil, profil_en_vigueur
from .versions import nouvelle_version


def enregistrer_avenant(
    *,
    utilisateur,
    accord: Accord,
    reference: str,
    date_avenant: datetime.date,
    document: DocumentReference,
    montant_revise,
    motif: str = "",
    allocations: dict | None = None,
    dates: dict | None = None,
) -> AvenantAccord:
    """`allocations` : `{catégorie: nouvelle allocation}` ; `dates` : jalons à remplacer."""
    for operation in ("parametrer", "valider"):
        if not est_habilite(utilisateur, operation, accord.project_id):
            raise PermissionDenied(f"Vous n'êtes pas habilité à « {operation} » sur ce projet.")
    with transaction.atomic():
        accord = Accord.objects.select_for_update().get(pk=accord.pk)
        base = profil_en_vigueur(accord, date_avenant)
        if base is None:
            if accord_a_un_profil(accord):
                raise ActivationRefusee(
                    f"Aucun profil de décaissement n'est en vigueur le {date_avenant} : "
                    "l'avenant ne peut pas être appliqué"
                )
            return creer_avenant(
                utilisateur=utilisateur,
                accord=accord,
                reference=reference,
                date_avenant=date_avenant,
                document=document,
                montant_revise=montant_revise,
                motif=motif,
            )
        nouveau = nouvelle_version(
            base,
            valid_from=date_avenant,
            utilisateur=utilisateur,
            allocations={c.pk: m for c, m in (allocations or {}).items()},
            dates=dates,
            profil_id=uuid.uuid4(),
        )
        avenant = creer_avenant(
            utilisateur=utilisateur,
            accord=accord,
            reference=reference,
            date_avenant=date_avenant,
            document=document,
            montant_revise=montant_revise,
            motif=motif,
            profile_version_id=nouveau.id,
        )
        valider_profil(utilisateur=utilisateur, profil=nouveau)
        activer_profil(utilisateur=utilisateur, profil=nouveau)
    return avenant
