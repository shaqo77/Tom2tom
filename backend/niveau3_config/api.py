"""L'API HTTP des documents de référence : dépôt (base64), liste, remplacement, intégrité.

Un document se dépose avec ses octets en base64 (le JSON ne porte pas d'octets) ; le corps d'une
requête ne dépasse pas 10 Mo (`DATA_UPLOAD_MAX_MEMORY_SIZE`), donc un fichier d'environ 7 Mo.
La référence de stockage est INTERNE : elle n'est jamais rendue, seule l'empreinte SHA-256 l'est.
Lecture et intégrité : habilitation `consulter` ; dépôt et remplacement : `parametrer`.
"""

from core.api import (
    VueMetier,
    champ_date,
    champ_octets,
    champ_texte,
    corps,
    objet_ou_404,
    reponse,
)
from core.metier import habilite

from .models import DocumentReference
from .services.documents import (
    IntegriteDocument,
    enregistrer_document,
    exigences_a_reverifier,
    remplacer_document,
    verifier_integrite,
)


def _document(d: DocumentReference) -> dict:
    return {
        "id": d.id,
        "kind": d.kind,
        "title": d.title,
        "version": d.version,
        "issued_on": d.issued_on,
        "sha256": bytes(d.sha256).hex(),
        "remplace_par": d.superseded_by_id,
    }


def _du_projet(project_id, document_id) -> DocumentReference:
    return objet_ou_404(DocumentReference, pk=document_id, project_id=project_id)


class Documents(VueMetier):
    def get(self, requete, project_id):
        habilite(requete.user, "consulter", project_id)
        documents = DocumentReference.objects.filter(project_id=project_id).order_by(
            "title", "version"
        )
        return reponse([_document(d) for d in documents])

    def post(self, requete, project_id):
        d = corps(requete)
        kind, titre = champ_texte(d, "kind"), champ_texte(d, "title")
        version = champ_texte(d, "version", obligatoire=False, defaut="")
        # Le service est idempotent (mêmes octets, même titre et version : même document) ; on le
        # dit : 201 quand le document est nouveau, 200 quand il existait déjà.
        existait = DocumentReference.objects.filter(
            project_id=project_id, kind=kind, title=titre, version=version
        ).exists()
        document = enregistrer_document(
            utilisateur=requete.user,
            project_id=project_id,
            kind=kind,
            title=titre,
            version=version,
            contenu=champ_octets(d, "contenu_base64"),
            issued_on=champ_date(d, "issued_on", obligatoire=False),
        )
        return reponse(_document(document), 200 if existait else 201)


class DocumentRemplacement(VueMetier):
    def post(self, requete, project_id, document_id):
        ancien = _du_projet(project_id, document_id)
        d = corps(requete)
        nouveau = remplacer_document(
            utilisateur=requete.user,
            ancien=ancien,
            contenu=champ_octets(d, "contenu_base64"),
            version=champ_texte(d, "version", obligatoire=False, defaut=""),
            issued_on=champ_date(d, "issued_on", obligatoire=False),
        )
        ancien.refresh_from_db()
        a_reverifier = sorted(e.code for e in exigences_a_reverifier(ancien))
        return reponse(_document(nouveau) | {"exigences_a_reverifier": a_reverifier}, 201)


class DocumentIntegrite(VueMetier):
    """Relit le fichier stocké et le compare à l'empreinte enregistrée.

    Un fichier altéré ou disparu n'est PAS une erreur de requête : c'est la réponse à la question.
    Le service journalise le constat avant de lever ; une réponse d'erreur annulerait cette trace
    avec la transaction de la requête, donc on la transforme en réponse normale.
    """

    def get(self, requete, project_id, document_id):
        document = _du_projet(project_id, document_id)
        try:
            verifier_integrite(requete.user, document)
        except IntegriteDocument as probleme:
            return reponse({"integre": False, "probleme": str(probleme)})
        return reponse({"integre": True, "probleme": None})
