"""L'API HTTP des documents de référence : dépôt (base64), liste, remplacement, intégrité.

Un document se dépose de DEUX façons : en JSON avec ses octets en base64 (le corps d'une requête ne
dépasse pas 10 Mo, donc un fichier d'environ 7 Mo), ou en MULTIPART (champs `kind`, `title`,
`version`, `issued_on` et le fichier `fichier`) jusqu'à la taille maximale du service, 50 Mio. Il se
télécharge (`contenu/`) après vérification de son empreinte ; un fichier altéré n'est jamais servi.
La référence de stockage est INTERNE : elle n'est jamais rendue, seule l'empreinte SHA-256 l'est.
Lecture et intégrité : habilitation `consulter` ; dépôt et remplacement : `parametrer`.
"""

import re

from django.db import IntegrityError
from django.http import HttpResponse
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from core.api import (
    VueMetier,
    champ_date,
    champ_decimal,
    champ_octets,
    champ_texte,
    corps,
    objet_ou_404,
    parametre_entier,
    recharge,
    reponse,
)
from core.audit import journaliser
from core.metier import decimal as decimal_exact
from core.metier import habilite, refuser, traduire_integrite
from niveau1_socle.financements.models import Accord
from niveau1_socle.referentiels.models import Devise

from . import stockage
from .models import (
    PIECES_EXIGEES,
    AssietteTaxes,
    DocumentReference,
    MethodeDecaissementCode,
    PlafondCompte,
    ProfilDecaissement,
    RegimeDecaissement,
    StatutProfil,
)
from .services.activation import activer_profil, rejeter_profil, valider_profil
from .services.comparaison import comparer_versions
from .services.completude import verifier_completude
from .services.documents import (
    IntegriteDocument,
    enregistrer_document,
    exigences_a_reverifier,
    remplacer_document,
    verifier_integrite,
)
from .services.profils_decaissement import (
    JALONS,
    creer_profil_decaissement,
    remplacer_brouillon,
    supprimer_brouillon,
)
from .services.versions import DATES_MODIFIABLES, nouvelle_version


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


def _contenu_du_depot(requete, d: dict) -> bytes:
    """Les octets du dépôt : le fichier d'un envoi multipart, ou le base64 d'un corps JSON."""
    fichier = requete.FILES.get("fichier")
    if fichier is not None:
        return fichier.read()
    return champ_octets(d, "contenu_base64")


class Documents(VueMetier):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

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
            contenu=_contenu_du_depot(requete, d),
            issued_on=champ_date(d, "issued_on", obligatoire=False),
        )
        return reponse(_document(document), 200 if existait else 201)


class DocumentRemplacement(VueMetier):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def post(self, requete, project_id, document_id):
        ancien = _du_projet(project_id, document_id)
        d = corps(requete)
        nouveau = remplacer_document(
            utilisateur=requete.user,
            ancien=ancien,
            contenu=_contenu_du_depot(requete, d),
            version=champ_texte(d, "version", obligatoire=False, defaut=""),
            issued_on=champ_date(d, "issued_on", obligatoire=False),
        )
        ancien.refresh_from_db()
        a_reverifier = sorted(e.code for e in exigences_a_reverifier(ancien))
        return reponse(_document(nouveau) | {"exigences_a_reverifier": a_reverifier}, 201)


# Le contenu ne se fie pas à ce que le fichier prétend être : on le sert TOUJOURS en pièce jointe,
# sans interprétation par le navigateur (un document déposé reste une donnée non fiable).
EXTENSIONS = ((b"%PDF-", ".pdf", "application/pdf"), (b"PK\x03\x04", ".zip", "application/zip"))


def _nom_de_fichier(titre: str, version: str, octets: bytes) -> tuple[str, str]:
    extension, genre = ".bin", "application/octet-stream"
    for signature, ext, mime in EXTENSIONS:
        if octets.startswith(signature):
            extension, genre = ext, mime
    base = (
        re.sub(r"[^A-Za-z0-9._-]+", "_", f"{titre}_{version}".strip("_")).strip("._") or "document"
    )
    return f"{base[:80]}{extension}", genre


class DocumentContenu(VueMetier):
    """Télécharge le fichier d'un document, après vérification de son empreinte.

    Habilitation `consulter` ; chaque téléchargement est journalisé. Un fichier altéré ou disparu
    n'est PAS servi : la réponse (409) dit pourquoi, et le constat est journalisé (une exception
    annulerait cette trace avec la transaction de la requête, voir `DocumentIntegrite`).
    """

    def get(self, requete, project_id, document_id):
        document = _du_projet(project_id, document_id)
        try:
            verifier_integrite(requete.user, document)
        except IntegriteDocument as probleme:
            return reponse({"code": "DOCUMENT_ALTERE", "message": str(probleme)}, 409)
        octets = stockage.lire(document.file_ref)
        nom, genre = _nom_de_fichier(document.title, document.version, octets)
        journaliser(
            org_id=document.org_id,
            actor_id=requete.user.id,
            action="document_downloaded",
            object_type="document_reference",
            object_id=document.id,
            project_id=project_id,
            after={"sha256": bytes(document.sha256).hex()},
        )
        reponse_http = HttpResponse(octets, content_type=genre)
        reponse_http["Content-Disposition"] = f'attachment; filename="{nom}"'
        reponse_http["X-Content-Type-Options"] = "nosniff"
        reponse_http["Content-Security-Policy"] = "sandbox"
        reponse_http["Digest"] = f"sha-256={bytes(document.sha256).hex()}"
        return reponse_http


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


# --- profils de décaissement -------------------------------------------------------------------
#
# Un profil se construit en brouillon, se valide (complétude), puis s'active à sa date d'effet ; un
# profil actif ne se modifie pas : on crée une NOUVELLE version. Lecture : `consulter` ; création,
# activation, nouvelle version : `parametrer` ; validation et rejet : `valider`.


def _accord_du_projet(project_id, accord_id) -> Accord:
    return objet_ou_404(Accord, pk=accord_id, project_id=project_id)


def _profil_de_l_accord(project_id, accord_id, profil_id) -> ProfilDecaissement:
    return objet_ou_404(
        ProfilDecaissement, pk=profil_id, accord_id=accord_id, project_id=project_id
    )


def _methode(m) -> dict:
    return {
        "method": m.method,
        "is_enabled": m.is_enabled,
        "supporting_docs": sorted(m.supporting_docs),
        "full_doc_threshold": m.full_doc_threshold,
        "min_application_amount": m.min_application_amount,
        "min_application_pct_of_ceiling": m.min_application_pct_of_ceiling,
    }


def _regle(r) -> dict:
    return {
        "category": r.category.code,
        "allocation": r.allocation,
        "funding_rate": r.funding_rate,
        "tax_basis": r.tax_basis,
        "eligibility_from": r.eligibility_from,
        "eligibility_to": r.eligibility_to,
        "requires_prior_review": r.requires_prior_review,
        "max_per_contract": r.max_per_contract,
    }


def _compte(c) -> dict:
    return {
        "compte": c.bank_account.code,
        "devise": c.currency_id,
        "ceiling_kind": c.ceiling_kind,
        "ceiling_amount": c.ceiling_amount,
        "replenishment_threshold_pct": c.replenishment_threshold_pct,
    }


def _profil(p: ProfilDecaissement, *, detail: bool = False) -> dict:
    sortie = {
        "id": p.id,
        "accord": p.accord.numero,
        "version": p.version,
        "status": p.status,
        "valid_from": p.valid_from,
        "valid_to": p.valid_to,
        "regime": p.regime,
        "exigence": p.requirement.code if p.requirement_id else None,
        "rejection_reason": p.rejection_reason,
        **{j: getattr(p, j) for j in JALONS},
    }
    if detail:
        sortie["methodes"] = [_methode(m) for m in p.methodes.order_by("method")]
        sortie["regles"] = [
            _regle(r) for r in p.regles.select_related("category").order_by("category__code")
        ]
        sortie["comptes"] = [
            _compte(c)
            for c in p.comptes.select_related("bank_account").order_by("bank_account__code")
        ]
        if p.status == StatutProfil.BROUILLON:
            c = verifier_completude(p)
            sortie["completude"] = {
                "complet": c.complet,
                "bloquantes": [{"code": a.code, "message": str(a.message)} for a in c.bloquantes],
                "avertissements": [
                    {"code": a.code, "message": str(a.message)} for a in c.avertissements
                ],
            }
    return sortie


def _liste(donnees: dict, nom: str, *, obligatoire: bool = True) -> list[dict]:
    valeur = donnees.get(nom)
    if not obligatoire and valeur in (None, []):  # facultative : absente ou vide, c'est « aucune »
        return []
    if not isinstance(valeur, list) or not valeur or not all(isinstance(x, dict) for x in valeur):
        refuser("api.champ_invalide", champ=nom, attendu="liste d'objets non vide")
    return valeur


def _optionnel(d: dict, nom: str):
    brut = d.get(nom)
    if brut in (None, ""):
        return None
    champ_decimal(d, nom)  # refuse un flottant et un type illisible
    return decimal_exact(brut, nom, signe="positif_ou_nul")


def _booleen(d: dict, nom: str, defaut: bool) -> bool:
    valeur = d.get(nom, defaut)
    if not isinstance(valeur, bool):
        refuser("api.champ_invalide", champ=nom, attendu="booléen")
    return valeur


def _methodes(d: dict) -> list[dict]:
    sortie = []
    for m in _liste(d, "methodes"):
        code = champ_texte(m, "method")
        if code not in MethodeDecaissementCode.values:
            refuser("profils_decaissement.methode_inconnue", methode=code)
        pieces = m.get("supporting_docs", [])
        if not isinstance(pieces, list) or not all(isinstance(x, str) for x in pieces):
            refuser("api.champ_invalide", champ="supporting_docs", attendu="liste de textes")
        for piece in pieces:
            if piece not in PIECES_EXIGEES:
                refuser("profils_decaissement.piece_inconnue", piece=piece)
        sortie.append(
            {
                "method": code,
                "is_enabled": _booleen(m, "is_enabled", True),
                "supporting_docs": pieces,
                "full_doc_threshold": _optionnel(m, "full_doc_threshold"),
                "min_application_amount": _optionnel(m, "min_application_amount"),
                "min_application_pct_of_ceiling": _optionnel(m, "min_application_pct_of_ceiling"),
            }
        )
    return sortie


def _regles(d: dict) -> list[dict]:
    sortie = []
    for r in _liste(d, "regles"):
        assiette = champ_texte(r, "tax_basis")
        if assiette not in AssietteTaxes.values:
            refuser("profils_decaissement.assiette_inconnue", assiette=assiette)
        champ_decimal(r, "allocation")
        champ_decimal(r, "funding_rate")
        sortie.append(
            {
                "category": champ_texte(r, "category"),
                "allocation": decimal_exact(r["allocation"], "allocation", signe="positif_ou_nul"),
                "funding_rate": decimal_exact(r["funding_rate"], "funding_rate", signe="positif"),
                "tax_basis": assiette,
                "eligibility_from": champ_date(r, "eligibility_from", obligatoire=False),
                "eligibility_to": champ_date(r, "eligibility_to", obligatoire=False),
                "requires_prior_review": _booleen(r, "requires_prior_review", False),
                "max_per_contract": _optionnel(r, "max_per_contract"),
            }
        )
    return sortie


def _comptes(d: dict) -> list[dict]:
    sortie = []
    for c in _liste(d, "comptes", obligatoire=False):
        devise = champ_texte(c, "devise")
        if not Devise.objects.filter(pk=devise).exists():
            refuser("profils_decaissement.devise_inconnue", devise=devise)
        genre = champ_texte(c, "ceiling_kind")
        if genre not in PlafondCompte.values:
            refuser("profils_decaissement.plafond_genre_inconnu", genre=genre)
        sortie.append(
            {
                "compte": champ_texte(c, "compte"),
                "currency_id": devise,
                "ceiling_kind": genre,
                "ceiling_amount": _optionnel(c, "ceiling_amount"),
                "replenishment_threshold_pct": _optionnel(c, "replenishment_threshold_pct"),
            }
        )
    return sortie


def _traduire_profil(erreur: IntegrityError):
    """Chaque contrainte de la base devient un refus métier précis (jamais une erreur brute)."""
    connues = {
        "uq_regle_categorie": ("profils_decaissement.categorie_en_double", {}),
        "uq_methode_par_profil": ("profils_decaissement.methode_en_double", {}),
        "uq_regle_compte": ("profils_decaissement.compte_en_double", {}),
        "regle_taux_dans_0_1": ("profils_decaissement.taux_hors_bornes", {}),
        "methode_un_seul_minimum": ("profils_decaissement.deux_minimums", {}),
        "methode_pourcentage_borne": ("profils_decaissement.pourcentage_hors_bornes", {}),
        "regle_compte_seuil_borne": ("profils_decaissement.pourcentage_hors_bornes", {}),
        "regle_compte_plafond_coherent": ("profils_decaissement.plafond_incoherent", {}),
        "regle_eligibilite_coherente": ("profils_decaissement.eligibilite_incoherente", {}),
        "profil_dates_coherentes": ("profils_decaissement.dates_incoherentes", {}),
    } | {f"profil_jalons_{i}": ("profils_decaissement.dates_incoherentes", {}) for i in range(4)}
    return traduire_integrite(erreur, connues)


def _lire_profil(d: dict) -> dict:
    """Le corps d'un profil (création ou remplacement), validé : mêmes règles dans les deux cas."""
    regime = champ_texte(d, "regime")
    if regime not in RegimeDecaissement.values:
        refuser("profils_decaissement.regime_inconnu", regime=regime)
    return {
        "valid_from": champ_date(d, "valid_from"),
        "regime": regime,
        "jalons": {j: champ_date(d, j, obligatoire=False) for j in JALONS},
        "methodes": _methodes(d),
        "regles": _regles(d),
        "comptes": _comptes(d),
        "exigence": champ_texte(d, "exigence", obligatoire=False),
    }


class ProfilsDecaissement(VueMetier):
    def get(self, requete, project_id, accord_id):
        habilite(requete.user, "consulter", project_id)
        accord = _accord_du_projet(project_id, accord_id)
        profils = ProfilDecaissement.objects.filter(accord=accord).select_related(
            "accord", "requirement"
        )
        return reponse([_profil(p) for p in profils.order_by("version")])

    def post(self, requete, project_id, accord_id):
        accord = _accord_du_projet(project_id, accord_id)
        contenu = _lire_profil(corps(requete))
        try:
            profil = creer_profil_decaissement(utilisateur=requete.user, accord=accord, **contenu)
        except IntegrityError as erreur:
            raise _traduire_profil(erreur) from erreur
        return reponse(_profil(recharge(profil), detail=True), 201)


class ProfilDecaissementDetail(VueMetier):
    def get(self, requete, project_id, accord_id, profil_id):
        habilite(requete.user, "consulter", project_id)
        return reponse(_profil(_profil_de_l_accord(project_id, accord_id, profil_id), detail=True))

    def put(self, requete, project_id, accord_id, profil_id):
        """Remplace le contenu d'un BROUILLON, d'un bloc : tout est accepté ou rien ne change."""
        profil = _profil_de_l_accord(project_id, accord_id, profil_id)
        contenu = _lire_profil(corps(requete))
        try:
            profil = remplacer_brouillon(utilisateur=requete.user, profil=profil, **contenu)
        except IntegrityError as erreur:
            raise _traduire_profil(erreur) from erreur
        return reponse(_profil(recharge(profil), detail=True))

    def delete(self, requete, project_id, accord_id, profil_id):
        """Abandonne un brouillon ; tout autre profil ne se supprime jamais."""
        profil = _profil_de_l_accord(project_id, accord_id, profil_id)
        supprimer_brouillon(utilisateur=requete.user, profil=profil)
        return reponse({"supprime": True})


class ProfilValider(VueMetier):
    def post(self, requete, project_id, accord_id, profil_id):
        profil = _profil_de_l_accord(project_id, accord_id, profil_id)
        d = corps(requete)
        justifications = d.get("justifications", {})
        if not isinstance(justifications, dict) or not all(
            isinstance(v, str) for v in justifications.values()
        ):
            refuser("api.champ_invalide", champ="justifications", attendu="objet de textes")
        profil = valider_profil(
            utilisateur=requete.user, profil=profil, justifications=justifications
        )
        return reponse(_profil(recharge(profil), detail=True))


class ProfilActiver(VueMetier):
    def post(self, requete, project_id, accord_id, profil_id):
        profil = _profil_de_l_accord(project_id, accord_id, profil_id)
        profil = activer_profil(utilisateur=requete.user, profil=profil)
        return reponse(_profil(recharge(profil), detail=True))


class ProfilRejeter(VueMetier):
    def post(self, requete, project_id, accord_id, profil_id):
        profil = _profil_de_l_accord(project_id, accord_id, profil_id)
        motif = champ_texte(corps(requete), "motif", obligatoire=False, defaut="")
        profil = rejeter_profil(utilisateur=requete.user, profil=profil, motif=motif)
        return reponse(_profil(recharge(profil), detail=True))


class ProfilNouvelleVersion(VueMetier):
    """Une copie brouillon du profil, à effet de `valid_from`, avec des allocations ou des jalons
    changés : `allocations` = `{code de catégorie: montant}`, `dates` = jalons à remplacer."""

    def post(self, requete, project_id, accord_id, profil_id):
        habilite(requete.user, "parametrer", project_id)
        base = _profil_de_l_accord(project_id, accord_id, profil_id)
        d = corps(requete)
        allocations_brutes = d.get("allocations", {})
        dates_brutes = d.get("dates", {})
        if not isinstance(allocations_brutes, dict) or not isinstance(dates_brutes, dict):
            refuser("api.champ_invalide", champ="allocations", attendu="objet")
        par_code = {r.category.code: r.category_id for r in base.regles.select_related("category")}
        allocations = {}
        for code, montant in allocations_brutes.items():
            if code not in par_code:
                refuser("profils_decaissement.categorie_sans_regle", code=code)
            champ_decimal({"montant": montant}, "montant")
            allocations[par_code[code]] = decimal_exact(montant, code, signe="positif_ou_nul")
        dates = {}
        for nom, valeur in dates_brutes.items():
            if nom not in DATES_MODIFIABLES:
                refuser("profils_decaissement.jalon_inconnu", jalon=nom)
            dates[nom] = champ_date({nom: valeur}, nom)
        try:
            nouveau = nouvelle_version(
                base,
                valid_from=champ_date(d, "valid_from"),
                utilisateur=requete.user,
                allocations=allocations,
                dates=dates,
            )
        except IntegrityError as erreur:
            raise _traduire_profil(erreur) from erreur
        return reponse(_profil(recharge(nouveau), detail=True), 201)


class ProfilComparaison(VueMetier):
    """Ce qui a changé entre deux versions du profil d'un même accord (`?avec=` + numéro)."""

    def get(self, requete, project_id, accord_id, profil_id):
        habilite(requete.user, "consulter", project_id)
        a = _profil_de_l_accord(project_id, accord_id, profil_id)
        version = parametre_entier(requete, "avec")
        b = objet_ou_404(
            ProfilDecaissement, accord_id=accord_id, project_id=project_id, version=version
        )

        def famille(f):
            return {
                "identiques": [str(x) for x in f.identiques],
                "modifies": [
                    {
                        "cle": str(cle),
                        "ecarts": {k: {"avant": v[0], "apres": v[1]} for k, v in e.items()},
                    }
                    for cle, e in f.modifies
                ],
                "ajoutes": [str(x) for x in f.ajoutes],
                "supprimes": [str(x) for x in f.supprimes],
            }

        c = comparer_versions(a, b)
        return reponse(
            {
                "de": a.version,
                "vers": b.version,
                "identiques": c.identiques,
                "parametres": famille(c.parametres),
                "methodes": famille(c.methodes),
                "categories": famille(c.categories),
                "comptes": famille(c.comptes),
            }
        )
