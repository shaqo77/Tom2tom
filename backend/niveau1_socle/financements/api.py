"""L'API HTTP des clés de cofinancement : créer une clé, ouvrir une version, lire la répartition.

Même conventions que les autres API (JSON strict, erreurs `{code, message}`). Lecture : habilitation
`consulter` ; écriture : `parametrer`, contrôlée par les services. Les accords se désignent par
leur NUMÉRO (ce que voit un administrateur), jamais par un identifiant interne. Une part est une
chaîne décimale exacte ; les poids sont des nombres exacts strictement positifs, jamais des
flottants.
"""

import datetime
import re

from core.api import (
    VueMetier,
    champ_date,
    champ_texte,
    corps,
    objet_ou_404,
    parametre_date,
    reponse,
)
from core.metier import habilite, refuser

from .cles import creer_cle, creer_version_cle, version_en_vigueur
from .models import Accord, CleCofinancement, VersionCle


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
