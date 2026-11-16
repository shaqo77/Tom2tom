"""Les points d'accès de l'auditeur : lecture seule, jeton `Auditeur`. Voir L7-T02.

Chaque vue vérifie, dans cet ordre : le jeton (401), le projet nommé (403), l'existence de l'objet
dans la plage de périodes (404), puis journalise la consultation.
"""

import hashlib

from django.http import Http404, HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from niveau1_socle.comptabilite import pieces as pieces_service
from niveau1_socle.comptabilite.models import PieceJustificative
from niveau4_reporting.publication.dossier import construire_dossier

from .auditeur import (
    AuthentificationAuditeur,
    LectureSeule,
    dans_la_plage,
    exiger_projet_et_plage,
    journaliser_consultation,
)
from .descente import CelluleInconnue, descendre_cellule, detail_ecriture
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


def _ligne(ligne) -> dict:
    return {
        "id": str(ligne.id),
        "ecriture": str(ligne.ecriture_id),
        "numero": ligne.numero,
        "journal": ligne.journal,
        "date": ligne.date.isoformat(),
        "compte": ligne.compte,
        "montant": str(ligne.montant),
    }


class CelluleDescente(VueAuditeur):
    """Une cellule d'un rapport publié : sa règle, ses lignes, et la preuve que la somme est la
    valeur publiée."""

    def get(self, request, project_id, rapport_id, rubrique, colonne):
        acces = request.auth
        rapport = _rapport(acces, project_id, rapport_id)
        try:
            descente = descendre_cellule(rapport, rubrique, colonne)
        except CelluleInconnue:
            raise Http404 from None
        detail = {"rapport": str(rapport.id), "cellule": f"{rubrique}/{colonne}"}
        journaliser_consultation(request, acces, project_id, "cellule", detail)
        return Response(
            {
                "rubrique": rubrique,
                "colonne": colonne,
                "type": descente.type,
                "regle": descente.regle,
                "valeur_publiee": str(descente.valeur_publiee),
                "somme": str(descente.somme),
                "ecart": str(descente.ecart),
                "coherente": descente.coherente,
                "lignes": [_ligne(ligne) for ligne in descente.lignes],
                "lignes_posterieures_a_la_publication": descente.posterieures,
                "composantes": [
                    {"rubrique": code, "valeur_publiee": str(valeur)}
                    for code, valeur in descente.composantes
                ],
            }
        )


def _ecriture(acces, project_id, ecriture_id):
    exiger_projet_et_plage(acces, project_id)
    detail = detail_ecriture(project_id, ecriture_id)
    if detail is None or detail.date > acces.period_to:
        raise Http404
    return detail


class EcritureDescente(VueAuditeur):
    def get(self, request, project_id, ecriture_id):
        acces = request.auth
        detail = _ecriture(acces, project_id, ecriture_id)
        journaliser_consultation(
            request, acces, project_id, "ecriture", {"ecriture": str(ecriture_id)}
        )
        return Response(
            {
                "id": str(detail.id),
                "numero": detail.numero,
                "journal": detail.journal,
                "date": detail.date.isoformat(),
                "libelle": detail.libelle,
                "lignes": [_ligne(ligne) for ligne in detail.lignes],
                "pieces": [
                    {
                        "id": str(p.id),
                        "type": p.type_piece,
                        "nom": p.nom,
                        "taille": p.taille,
                        "sha256": bytes(p.sha256).hex(),
                    }
                    for p in detail.pieces
                ],
            }
        )


class PieceScan(VueAuditeur):
    """Le scan d'une pièce : les octets stockés, après vérification de leur empreinte."""

    def get(self, request, project_id, ecriture_id, piece_id):
        acces = request.auth
        _ecriture(acces, project_id, ecriture_id)
        piece = PieceJustificative.objects.filter(pk=piece_id, ecriture_id=ecriture_id).first()
        if piece is None:
            raise Http404
        try:
            contenu = pieces_service.lire_piece(piece)
        except pieces_service.PieceAlteree:
            return Response({"detail": "scan altéré"}, status=409)
        detail = {
            "ecriture": str(ecriture_id),
            "piece": str(piece.id),
            "sha256": bytes(piece.sha256).hex(),
        }
        journaliser_consultation(request, acces, project_id, "piece", detail)
        reponse = HttpResponse(contenu, content_type="application/octet-stream")
        reponse["Content-Disposition"] = f'attachment; filename="{piece.nom}"'
        reponse["X-Empreinte-SHA256"] = bytes(piece.sha256).hex()
        return reponse
