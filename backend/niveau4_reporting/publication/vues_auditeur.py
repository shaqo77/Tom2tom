"""Les points d'accès de l'auditeur : lecture seule, jeton `Auditeur`. Voir L7-T02.

Chaque vue vérifie, dans cet ordre : le jeton (401), le projet nommé (403), l'existence de l'objet
dans la plage de périodes (404), puis journalise la consultation.
"""

import hashlib

from django.http import Http404, HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from niveau4_reporting.publication.dossier import construire_dossier

from .auditeur import (
    AuthentificationAuditeur,
    LectureSeule,
    dans_la_plage,
    exiger_projet_et_plage,
    journaliser_consultation,
)
from .models import FichierRapport, RapportPublie


class VueAuditeur(APIView):
    authentication_classes = [AuthentificationAuditeur]
    permission_classes = [LectureSeule]


def _rapport(acces, project_id, rapport_id) -> RapportPublie:
    exiger_projet_et_plage(acces, project_id)
    rapport = RapportPublie.objects.filter(pk=rapport_id, project_id=project_id).first()
    if rapport is None or not dans_la_plage(acces, rapport.period_to):
        raise Http404
    return rapport


def _resume(r: RapportPublie) -> dict:
    return {
        "id": str(r.id),
        "modele": r.template_code,
        "version_modele": r.template_version,
        "periode": [r.period_from.isoformat(), r.period_to.isoformat()],
        "publie_le": r.published_at.isoformat(),
        "scelle": bytes(r.seal).hex(),
    }


class RapportsPublies(VueAuditeur):
    def get(self, request, project_id):
        acces = request.auth
        exiger_projet_et_plage(acces, project_id)
        rapports = RapportPublie.objects.filter(
            project_id=project_id, period_to__gte=acces.period_from, period_to__lte=acces.period_to
        ).order_by("period_to", "published_at")
        journaliser_consultation(request, acces, project_id, "rapports")
        return Response([_resume(r) for r in rapports])


class RapportPublie_(VueAuditeur):
    def get(self, request, project_id, rapport_id):
        acces = request.auth
        rapport = _rapport(acces, project_id, rapport_id)
        journaliser_consultation(
            request, acces, project_id, "rapport", {"rapport": str(rapport.id)}
        )
        return Response(
            {
                **_resume(rapport),
                "parametres": rapport.params,
                "versions_des_mappings": rapport.mapping_versions,
                "valeurs": rapport.values,
                "fichiers": [
                    {"id": str(f.id), "nature": f.nature, "format": f.format, "langue": f.langue}
                    for f in rapport.files.order_by("nature", "format", "langue")
                ],
            }
        )


class DossierDeConformite(VueAuditeur):
    def get(self, request, project_id, rapport_id):
        acces = request.auth
        rapport = _rapport(acces, project_id, rapport_id)
        dossier = construire_dossier(rapport)
        journaliser_consultation(
            request, acces, project_id, "dossier", {"rapport": str(rapport.id)}
        )
        return Response(
            {
                "taux_couverture": str(dossier.taux_couverture),
                "rubriques": [
                    {
                        "code": ligne.code,
                        "regle": ligne.regle,
                        "mapping": ligne.mapping,
                        "exigences": [
                            {
                                "code": s.code,
                                "version": s.version,
                                "document": s.document,
                                "version_document": s.document_version,
                                "citation": s.citation,
                                "validateur": s.validateur,
                                "valide_le": s.valide_le.isoformat() if s.valide_le else None,
                            }
                            for s in ligne.sources
                        ],
                    }
                    for ligne in dossier.lignes
                ],
            }
        )


class FichierExporte(VueAuditeur):
    def get(self, request, project_id, rapport_id, fichier_id):
        acces = request.auth
        rapport = _rapport(acces, project_id, rapport_id)
        fichier = FichierRapport.objects.filter(pk=fichier_id, rapport=rapport).first()
        if fichier is None:
            raise Http404
        contenu = bytes(fichier.contenu)
        if hashlib.sha256(contenu).hexdigest() != fichier.sha256:
            return Response({"detail": "fichier altéré"}, status=409)
        journaliser_consultation(
            request, acces, project_id, "export",
            {"rapport": str(rapport.id), "fichier": str(fichier.id), "sha256": fichier.sha256},
        )  # fmt: skip
        reponse = HttpResponse(contenu, content_type="application/octet-stream")
        reponse["Content-Disposition"] = f'attachment; filename="{fichier.nom}"'
        reponse["X-Empreinte-SHA256"] = fichier.sha256
        return reponse
