"""L'API de l'export d'une demande de retrait vers le format du bailleur. Lot 8.

`GET /projets/<p>/demandes-retrait/<id>/export/<format>/` : droit `consulter`, réponse en PIÈCE
JOINTE, journalisée (qui, quelle demande, quel format, empreinte du fichier). Le nom du format
passe par une liste blanche (`export._definition`) : un nom reçu n'est jamais un morceau de chemin.

Le paramètre d'URL ne s'appelle pas `format` : Django REST Framework l'emploie pour choisir le
rendu de la réponse et répond 404 à tout nom qu'il ne connaît pas.
"""

import hashlib

from django.http import Http404, HttpResponse

from core.api import VueMetier, objet_ou_404
from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import msg
from core.metier import habilite
from niveau1_socle.decaissements.models import DemandeRetrait

from .export import FormatInapplicable, FormatInconnu, export_demande
from .types_bad import TypeBadIndeterminable

TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class DemandeExport(VueMetier):
    def get(self, requete, project_id, demande_id, nom_format):
        habilite(requete.user, "consulter", project_id)
        demande = objet_ou_404(DemandeRetrait, pk=demande_id, project_id=project_id)
        try:
            octets, nom = export_demande(demande, nom_format)
        except FormatInconnu as erreur:
            raise Http404 from erreur
        except FormatInapplicable as erreur:
            raise ErreurMetier(CodeErreur.REGLE_INVALIDE, erreur.args[0]) from erreur
        except TypeBadIndeterminable as erreur:
            raise ErreurMetier(
                CodeErreur.REGLE_INVALIDE, msg(erreur.cle, **erreur.params)
            ) from erreur
        journaliser(
            org_id=demande.org_id,
            actor_id=requete.user.id,
            action="demande_exportee",
            object_type="demande_retrait",
            object_id=demande.id,
            project_id=project_id,
            after={"format": nom_format, "sha256": hashlib.sha256(octets).hexdigest()},
        )
        reponse = HttpResponse(octets, content_type=TYPE_XLSX)
        reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
        return reponse
