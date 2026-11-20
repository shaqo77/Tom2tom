"""L'API HTTP des contrôles : un administrateur les installe, les écrit, les valide et les active
sans développeur. Voir L11-B5.

Un contrôle suit le cycle des autres configurations : brouillon → validé (`valider`) → actif
(`parametrer`), jamais de saut d'étape, et un changement est une NOUVELLE version. Rien n'est actif
sans une personne habilitée (règle 9) : installer la bibliothèque ne crée que des brouillons.
L'expression d'un contrôle s'écrit dans le langage de conditions BORNÉ (règle 5) ; une condition
hors schéma est refusée à la création, avec la raison. Lecture : `consulter`.
"""

from core.api import (
    VueMetier,
    champ_date,
    champ_texte,
    corps,
    objet_ou_404,
    recharge,
    reponse,
)
from core.metier import habilite, refuser
from niveau4_reporting.controles import conditions

from .bibliotheque import livres_avec_risque
from .models import Controle, Severite, StatutControle
from .services import (
    activer_controle,
    creer_controle,
    installer_bibliotheque,
    rejeter_controle,
    valider_controle,
)


def _controle(c: Controle, *, detail: bool = False) -> dict:
    sortie = {
        "id": c.id,
        "code": c.code,
        "version": c.version,
        "status": c.status,
        "mode": c.mode,
        "type_regle": c.type_regle,
        "severity": c.severity,
        "label": c.label,
        "valid_from": c.valid_from,
        "valid_to": c.valid_to,
    }
    if detail:
        sortie |= {
            "expression": c.expression,
            "applicable_si": c.applicable_si,
            "parametres": c.parametres,
            "action_corrective": c.action_corrective,
        }
    return sortie


def _du_projet(project_id, controle_id) -> Controle:
    return objet_ou_404(Controle, pk=controle_id, project_id=project_id)


def _objet(donnees: dict, nom: str, *, obligatoire: bool = False) -> dict | None:
    valeur = donnees.get(nom)
    if valeur is None:
        if obligatoire:
            refuser("api.champ_obligatoire", champ=nom)
        return None
    if not isinstance(valeur, dict):
        refuser("api.champ_invalide", champ=nom, attendu="objet")
    return valeur


class Controles(VueMetier):
    def get(self, requete, project_id):
        habilite(requete.user, "consulter", project_id)
        controles = Controle.objects.filter(project_id=project_id)
        code = requete.query_params.get("code")
        if code:
            controles = controles.filter(code=code)
        statut = requete.query_params.get("status")
        if statut:
            if statut not in StatutControle.values:
                refuser("controles_api.statut_inconnu", status=statut)
            controles = controles.filter(status=statut)
        return reponse([_controle(c) for c in controles.order_by("code", "version")])

    def post(self, requete, project_id):
        d = corps(requete)
        manuel = d.get("manuel", False)
        if not isinstance(manuel, bool):
            refuser("api.champ_invalide", champ="manuel", attendu="booléen")
        type_regle = champ_texte(d, "type_regle")
        if type_regle not in conditions.TYPES_DE_REGLE:
            refuser("controles_api.type_regle_inconnu", type_regle=type_regle)
        severity = champ_texte(d, "severity")
        if severity not in Severite.values:
            refuser("controles_api.severite_inconnue", severity=severity)
        controle = creer_controle(
            utilisateur=requete.user,
            project_id=project_id,
            code=champ_texte(d, "code"),
            label=_objet(d, "label", obligatoire=True),
            type_regle=type_regle,
            severity=severity,
            valid_from=champ_date(d, "valid_from"),
            expression=_objet(d, "expression"),
            applicable_si=_objet(d, "applicable_si"),
            action_corrective=_objet(d, "action_corrective"),
            manuel=manuel,
            parametres=_objet(d, "parametres"),
        )
        return reponse(_controle(recharge(controle), detail=True), 201)


class ControleDetail(VueMetier):
    def get(self, requete, project_id, controle_id):
        habilite(requete.user, "consulter", project_id)
        return reponse(_controle(_du_projet(project_id, controle_id), detail=True))


class ControleValider(VueMetier):
    def post(self, requete, project_id, controle_id):
        controle = valider_controle(
            utilisateur=requete.user, controle=_du_projet(project_id, controle_id)
        )
        return reponse(_controle(recharge(controle), detail=True))


class ControleActiver(VueMetier):
    def post(self, requete, project_id, controle_id):
        controle = activer_controle(
            utilisateur=requete.user, controle=_du_projet(project_id, controle_id)
        )
        return reponse(_controle(recharge(controle), detail=True))


class ControleRejeter(VueMetier):
    def post(self, requete, project_id, controle_id):
        motif = champ_texte(corps(requete), "motif", obligatoire=False, defaut="")
        controle = rejeter_controle(
            utilisateur=requete.user, controle=_du_projet(project_id, controle_id), motif=motif
        )
        return reponse(_controle(recharge(controle), detail=True))


class Bibliotheque(VueMetier):
    """Les contrôles livrés, et lesquels sont déjà installés dans ce projet."""

    def get(self, requete, project_id):
        habilite(requete.user, "consulter", project_id)
        installes = set(
            Controle.objects.filter(project_id=project_id).values_list("code", flat=True)
        )
        return reponse(
            [
                {
                    "code": d.code,
                    "famille": d.famille,
                    "type_regle": d.type_regle,
                    "severity": d.severity,
                    "label": d.label,
                    "action_corrective": d.action_corrective,
                    "installe": d.code in installes,
                }
                for d in livres_avec_risque()
            ]
        )


class BibliothequeInstaller(VueMetier):
    """Installe des contrôles livrés EN BROUILLON (jamais validés ni activés)."""

    def post(self, requete, project_id):
        d = corps(requete)
        codes = d.get("codes")
        if codes is not None and (
            not isinstance(codes, list) or not codes or not all(isinstance(c, str) for c in codes)
        ):
            refuser("api.champ_invalide", champ="codes", attendu="liste de textes non vide")
        resultat = installer_bibliotheque(
            utilisateur=requete.user,
            project_id=project_id,
            valid_from=champ_date(d, "valid_from"),
            codes=codes,
        )
        return reponse(
            {
                "crees": sorted(c.code for c in resultat.crees),
                "deja_presents": sorted(resultat.deja_presents),
            },
            201 if resultat.crees else 200,
        )
