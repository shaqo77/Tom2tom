"""L'API HTTP du financement : bailleurs, accords, catégories, avenants et clés de cofinancement.

Même conventions que les autres API (JSON strict, erreurs `{code, message}`). Lecture : habilitation
`consulter` ; écriture : `parametrer`, contrôlée par les services. Les accords se désignent par
leur NUMÉRO (ce que voit un administrateur), jamais par un identifiant interne. Une part est une
chaîne décimale exacte ; les poids sont des nombres exacts strictement positifs, jamais des
flottants.
"""

import datetime
import re

from django.db import IntegrityError

from core.api import (
    VueMetier,
    champ_date,
    champ_texte,
    champ_uuid,
    corps,
    objet_ou_404,
    parametre_date,
    recharge,
    reponse,
    reponse_liste,
)
from core.metier import decimal as decimal_exact
from core.metier import habilite, refuser, traduire_integrite
from niveau1_socle.referentiels.models import Devise
from niveau3_config.models import DocumentReference

from .cles import creer_cle, creer_version_cle, version_en_vigueur
from .models import (
    Accord,
    AvenantAccord,
    Bailleur,
    Categorie,
    CleCofinancement,
    NatureAccord,
    VersionCle,
)
from .services import (
    changer_statut_accord,
    creer_accord,
    creer_avenant,
    creer_bailleur,
    creer_categorie,
    montant_courant,
    parametrer_numerotation_demandes,
    situation_avant_apres,
)


def _version(version: VersionCle) -> dict:
    parts = version.parts.select_related("accord").order_by("accord__numero")
    return {
        "id": version.id,
        "version": version.version,
        "valid_from": version.valid_from,
        "valid_to": version.valid_to,
        "porteur": version.rounding_residual_agreement.numero,
        "motif": version.motif,
        "parts": [{"accord": p.accord.numero, "part": p.share} for p in parts],
    }


def _cle(cle: CleCofinancement, jour: datetime.date | None = None) -> dict:
    sortie = {"id": cle.id, "code": cle.code, "label": cle.label}
    if jour is not None:
        courante = version_en_vigueur(cle, jour)
        sortie["version_en_vigueur"] = _version(courante) if courante else None
    return sortie


class Cles(VueMetier):
    def get(self, requete, project_id):
        habilite(requete.user, "consulter", project_id)
        jour = parametre_date(requete, "jour", obligatoire=False) or datetime.date.today()
        cles = CleCofinancement.objects.filter(project_id=project_id).order_by("code")
        return reponse([_cle(c, jour) for c in cles])

    def post(self, requete, project_id):
        d = corps(requete)
        libelle = d.get("label")
        if not isinstance(libelle, dict) or not libelle:
            refuser(
                "api.champ_invalide", champ="label", attendu="dictionnaire de libellés par langue"
            )
        if not all(isinstance(t, str) and t.strip() for t in libelle.values()):
            refuser("api.champ_invalide", champ="label", attendu="textes non vides")
        cle = creer_cle(
            utilisateur=requete.user,
            project_id=project_id,
            code=champ_texte(d, "code"),
            label=libelle,
        )
        return reponse(_cle(cle), 201)


def _cle_du_projet(project_id, cle_id) -> CleCofinancement:
    return objet_ou_404(CleCofinancement, pk=cle_id, project_id=project_id)


class CleDetail(VueMetier):
    def get(self, requete, project_id, cle_id):
        habilite(requete.user, "consulter", project_id)
        cle = _cle_du_projet(project_id, cle_id)
        versions = cle.versions.order_by("-version")
        return reponse(_cle(cle) | {"versions": [_version(v) for v in versions]})


def _poids(valeur) -> dict:
    """`{"numéro d'accord": poids}` → `{Accord: poids}`, poids exacts strictement positifs."""
    if not isinstance(valeur, dict) or not valeur:
        refuser("api.champ_invalide", champ="parts", attendu="accords et poids")
    poids = {}
    for numero, brut in valeur.items():
        ecrit_en_chiffres = isinstance(brut, int) and not isinstance(brut, bool)
        ecrit_en_chiffres = ecrit_en_chiffres or (
            isinstance(brut, str) and re.fullmatch(r"\d+(\.\d+)?", brut) is not None
        )
        if not ecrit_en_chiffres:  # ni flottant, ni texte, ni exposant
            refuser(
                "api.champ_invalide", champ=f"parts.{numero}", attendu="poids exact en chiffres"
            )
        accord = Accord.objects.filter(numero=numero).first()
        if accord is None:
            refuser("cles.accord_inconnu", numero=numero)
        poids[accord] = brut
    return poids


class CleVersions(VueMetier):
    def post(self, requete, project_id, cle_id):
        cle = _cle_du_projet(project_id, cle_id)
        d = corps(requete)
        poids = _poids(d.get("parts"))
        numero_porteur = champ_texte(d, "porteur")
        # Un porteur hors de la clé reste `None` : le service le refuse avec son message.
        porteur = next((a for a in poids if a.numero == numero_porteur), None)
        version = creer_version_cle(
            utilisateur=requete.user,
            cle=cle,
            poids=poids,
            porteur=porteur,
            valid_from=champ_date(d, "valid_from"),
            motif=champ_texte(d, "motif", obligatoire=False, defaut=""),
        )
        return reponse(_version(version), 201)


# --- bailleurs, accords, catégories, avenants ------------------------------------------------
#
# Les contraintes de la base (doublons, montants, dates) sont des refus MÉTIER, pas des pannes : on
# les traduit en 422 `{code, message}` plutôt que de laisser une erreur d'intégrité brute en 500.


def _montant(donnees: dict, nom: str, *, obligatoire: bool = True):
    brut = donnees.get(nom)
    if brut in (None, ""):
        if obligatoire:
            refuser("api.champ_obligatoire", champ=nom)
        return None
    # `decimal_exact` refuse un flottant, un booléen, un texte illisible, NaN et l'infini.
    return decimal_exact(brut, nom, signe="positif_ou_nul")


def _devise(code) -> str:
    """Une devise du référentiel (la base ne vérifie une clé étrangère qu'en fin de requête)."""
    if not Devise.objects.filter(pk=code).exists():
        refuser("financements.devise_inconnue", devise=code)
    return code


def _traduire(erreur: IntegrityError, **params):
    """Chaque message ne reçoit que SES paramètres (un message sans paramètre n'en attend pas)."""
    connues = {
        "uq_bailleur_code": ("financements.bailleur_deja_existant", {"code": params.get("code")}),
        "uq_accord_numero": (
            "financements.accord_numero_deja_pris",
            {"numero": params.get("numero")},
        ),
        "uq_categorie_code": (
            "financements.categorie_deja_existante",
            {"code": params.get("code")},
        ),
        "uq_avenant_reference": (
            "financements.avenant_deja_enregistre",
            {"reference": params.get("reference")},
        ),
        "accord_montant_positif": ("financements.montant_negatif", {}),
        "categorie_plafond_positif": ("financements.montant_negatif", {}),
        "avenant_montant_positif": ("financements.montant_negatif", {}),
    } | {f"accord_dates_{i}": ("financements.dates_incoherentes", {}) for i in range(6)}
    return traduire_integrite(erreur, connues)


def _bailleur(b: Bailleur) -> dict:
    return {"id": b.id, "code": b.code, "nom": b.nom, "pays": b.pays}


class Bailleurs(VueMetier):
    def get(self, requete):
        return reponse_liste(requete, Bailleur.objects.order_by("code", "id"), _bailleur)

    def post(self, requete):
        d = corps(requete)
        code, nom = champ_texte(d, "code"), champ_texte(d, "nom")
        pays = champ_texte(d, "pays", obligatoire=False, defaut="")
        if pays and not re.fullmatch(r"[A-Z]{2}", pays):  # la base ne le dit qu'en tronquant
            refuser("financements.pays_invalide")
        try:
            bailleur = creer_bailleur(
                utilisateur=requete.user,
                code=code,
                nom=nom,
                pays=pays,
            )
        except IntegrityError as erreur:
            raise _traduire(erreur, code=code) from erreur
        return reponse(_bailleur(recharge(bailleur)), 201)


def _accord(a: Accord, jour: datetime.date | None = None) -> dict:
    return {
        "id": a.id,
        "numero": a.numero,
        "libelle": a.libelle,
        "bailleur": a.bailleur.code,
        "nature": a.nature,
        "statut": a.status,
        "devise": a.devise_id,
        "montant_initial": a.montant_initial,
        "montant_courant": montant_courant(a, jour),
        "date_effet": a.date_effet,
        "date_fin_eligibilite": a.date_fin_eligibilite,
        "date_cloture": a.date_cloture,
        "date_limite_decaissement": a.date_limite_decaissement,
        "format_numero_demande": a.format_numero_demande,
        "suffixe_agence": a.suffixe_agence,
    }


def _categorie(c: Categorie) -> dict:
    return {
        "id": c.id,
        "code": c.code,
        "label": c.label,
        "parent": c.parent.code if c.parent_id else None,
        "plafond": c.plafond,
        "devise": c.devise_id,
    }


def _avenant(v: AvenantAccord) -> dict:
    return {
        "id": v.id,
        "reference": v.reference,
        "date_avenant": v.date_avenant,
        "montant_revise": v.montant_revise,
        "motif": v.motif,
        "document_id": v.document_id,
    }


def _accord_du_projet(project_id, accord_id) -> Accord:
    return objet_ou_404(Accord, pk=accord_id, project_id=project_id)


class Accords(VueMetier):
    def get(self, requete, project_id):
        habilite(requete.user, "consulter", project_id)
        accords = Accord.objects.filter(project_id=project_id).select_related("bailleur")
        return reponse_liste(requete, accords.order_by("numero", "id"), _accord)

    def post(self, requete, project_id):
        d = corps(requete)
        code_bailleur = champ_texte(d, "bailleur")
        bailleur = Bailleur.objects.filter(code=code_bailleur).first()
        if bailleur is None:
            refuser("financements.bailleur_inconnu", code=code_bailleur)
        nature = champ_texte(d, "nature")
        if nature not in NatureAccord.values:
            refuser("financements.nature_accord_inconnue", nature=nature)
        numero = champ_texte(d, "numero")
        try:
            accord = creer_accord(
                utilisateur=requete.user,
                project_id=project_id,
                bailleur=bailleur,
                numero=numero,
                nature=nature,
                devise=_devise(champ_texte(d, "devise")),
                montant_initial=_montant(d, "montant_initial"),
                libelle=champ_texte(d, "libelle", obligatoire=False, defaut=""),
                date_effet=champ_date(d, "date_effet", obligatoire=False),
                date_fin_eligibilite=champ_date(d, "date_fin_eligibilite", obligatoire=False),
                date_cloture=champ_date(d, "date_cloture", obligatoire=False),
                date_limite_decaissement=champ_date(
                    d, "date_limite_decaissement", obligatoire=False
                ),
            )
        except IntegrityError as erreur:
            raise _traduire(erreur, numero=numero) from erreur
        return reponse(_accord(recharge(accord)), 201)


class AccordDetail(VueMetier):
    def get(self, requete, project_id, accord_id):
        habilite(requete.user, "consulter", project_id)
        accord = _accord_du_projet(project_id, accord_id)
        categories = accord.categories.select_related("parent").order_by("parent_id", "code")
        # Les catégories racines d'abord, puis leurs sous-catégories : l'ordre se lit comme l'arbre.
        racines = [c for c in categories if c.parent_id is None]
        enfants = [c for c in categories if c.parent_id is not None]
        avenants = accord.avenants.order_by("date_avenant", "created_at")
        return reponse(
            _accord(accord)
            | {
                "categories": [_categorie(c) for c in [*racines, *enfants]],
                "avenants": [_avenant(v) for v in avenants],
            }
        )


class AccordStatut(VueMetier):
    def post(self, requete, project_id, accord_id):
        accord = _accord_du_projet(project_id, accord_id)
        d = corps(requete)
        accord = changer_statut_accord(
            accord,
            champ_texte(d, "statut"),
            utilisateur=requete.user,
            motif=champ_texte(d, "motif", obligatoire=False, defaut=""),
        )
        return reponse(_accord(accord))


class AccordNumerotation(VueMetier):
    """Le format de numérotation des demandes de retrait de l'accord (`standard` ou `bad` + suffixe
    d'agence). Il ne change plus dès qu'une demande existe."""

    def post(self, requete, project_id, accord_id):
        accord = _accord_du_projet(project_id, accord_id)
        d = corps(requete)
        accord = parametrer_numerotation_demandes(
            accord,
            format=champ_texte(d, "format"),
            suffixe_agence=champ_texte(d, "suffixe_agence", obligatoire=False, defaut=""),
            utilisateur=requete.user,
        )
        return reponse(_accord(accord))


class AccordCategories(VueMetier):
    def post(self, requete, project_id, accord_id):
        accord = _accord_du_projet(project_id, accord_id)
        d = corps(requete)
        libelle = d.get("label")
        if not isinstance(libelle, dict) or not libelle:
            refuser(
                "api.champ_invalide", champ="label", attendu="dictionnaire de libellés par langue"
            )
        if not all(isinstance(t, str) and t.strip() for t in libelle.values()):
            refuser("api.champ_invalide", champ="label", attendu="textes non vides")
        code = champ_texte(d, "code")
        parent = None
        code_parent = champ_texte(d, "parent", obligatoire=False)
        if code_parent:
            parent = accord.categories.filter(code=code_parent).first()
            if parent is None:
                refuser("financements.categorie_parente_inconnue", code=code_parent)
        devise = champ_texte(d, "devise", obligatoire=False)
        try:
            categorie = creer_categorie(
                utilisateur=requete.user,
                accord=accord,
                code=code,
                label=libelle,
                plafond=_montant(d, "plafond", obligatoire=False),
                parent=parent,
                devise=_devise(devise) if devise else None,
            )
        except IntegrityError as erreur:
            raise _traduire(erreur, code=code) from erreur
        return reponse(_categorie(recharge(categorie)), 201)


class AccordAvenants(VueMetier):
    def post(self, requete, project_id, accord_id):
        accord = _accord_du_projet(project_id, accord_id)
        d = corps(requete)
        reference = champ_texte(d, "reference")
        document = DocumentReference.objects.filter(pk=champ_uuid(d, "document_id")).first()
        if document is None:
            refuser("financements.document_inconnu")
        try:
            avenant = creer_avenant(
                utilisateur=requete.user,
                accord=accord,
                reference=reference,
                date_avenant=champ_date(d, "date_avenant"),
                document=document,
                montant_revise=_montant(d, "montant_revise"),
                motif=champ_texte(d, "motif", obligatoire=False, defaut=""),
            )
        except IntegrityError as erreur:
            raise _traduire(erreur, reference=reference) from erreur
        return reponse(situation_avant_apres(recharge(avenant)), 201)
