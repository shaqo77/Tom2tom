"""Le téléchargement d'un export par lien signé : le lien EST l'authentification. Voir L8-T03."""

import hashlib

from django.http import Http404, HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit import journaliser
from core.i18n import msg
from niveau3_config import stockage

from .models import ExportOrganisation, StatutExport
from .services import lire_jeton, poser_organisation


class TelechargerExport(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request, jeton):
        try:
            org, export_id = lire_jeton(jeton)
        except ValueError:
            return Response({"detail": str(msg("export.lien_invalide"))}, status=403)
        poser_organisation(org)
        export = ExportOrganisation.objects.filter(pk=export_id).first()
        if export is None or export.statut != StatutExport.PRET:
            raise Http404
        contenu = stockage.lire(export.file_ref)
        if hashlib.sha256(contenu).hexdigest() != export.sha256:
            return Response({"detail": str(msg("export.archive_alteree"))}, status=409)
        journaliser(
            org_id=export.org_id,
            actor_id=None,
            action="export_downloaded",
            object_type="export_organisation",
            object_id=export.id,
            after={"sha256": export.sha256},
            actor_ip=request.META.get("REMOTE_ADDR"),
        )
        reponse = HttpResponse(contenu, content_type="application/zip")
        reponse["Content-Disposition"] = f'attachment; filename="export_{export.id}.zip"'
        reponse["X-Empreinte-SHA256"] = export.sha256
        return reponse
