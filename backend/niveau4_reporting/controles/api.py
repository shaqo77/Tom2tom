"""L'API HTTP des contrôles : un administrateur les installe, les écrit, les valide et les active
sans développeur. Voir L11-B5.

Un contrôle suit le cycle des autres configurations : brouillon → validé (`valider`) → actif
(`parametrer`), jamais de saut d'étape, et un changement est une NOUVELLE version. Rien n'est actif
sans une personne habilitée (règle 9) : installer la bibliothèque ne crée que des brouillons.
L'expression d'un contrôle s'écrit dans le langage de conditions BORNÉ (règle 5) ; une condition
hors schéma est refusée à la création, avec la raison. Lecture : `consulter`.
"""

import uuid

from core.api import (
    VueMetier,
    champ_date,
    champ_texte,
    corps,
    objet_ou_404,
    parametre_date,
    recharge,
    reponse,
)
from core.metier import habilite, refuser
from niveau4_reporting.controles import conditions

from .bibliotheque import livres_avec_risque
from .derogations import decider_derogation, demander_derogation, dossier_de_conformite, justifier
from .models import (
    Controle,
    Derogation,
    EvaluationControle,
    Resultat,
    Severite,
    StatutControle,
    StatutDerogation,
)
from .services import (
    activer_controle,
    controles_en_attente,
    creer_controle,
    installer_bibliotheque,
    rejeter_controle,
    trancher,
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


class LangageControles(VueMetier):
    """Le langage de conditions tel que le SERVEUR l'accepte : pour chaque type de règle ses champs
    et leur type, pour chaque opérateur les types de champ qu'il accepte et s'il prend une valeur.
    Un écran de création le lit au lieu de le recopier : il ne propose que ce que l'enregistrement
    acceptera."""

    def get(self, requete):
        return reponse(
            {
                "types_regle": {
                    type_regle: {
                        nom: {"type": champ.type.value}
                        | (
                            {"elements": {n: t.value for n, t in champ.elements}}
                            if champ.elements
                            else {}
                        )
                        for nom, champ in champs.items()
                    }
                    for type_regle, champs in conditions.SCHEMAS.items()
                },
                "operateurs": {
                    op.value: {
                        "types": [t.value for t in types],
                        "sans_valeur": op in conditions.SANS_VALEUR,
                    }
                    for op, types in conditions.COMPATIBILITE.items()
                },
                "severites": list(Severite.values),
                "max_conditions": conditions.MAX_CONDITIONS,
            }
        )


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
    """Installe des contrôles livrés EN BROUILLON (jamais validés ni activés).

    `seuils` règle les contrôles de risque (`{"RIS-CATEGORIE-SEUIL": "75", "RIS-AVANCE-NON-APUREE":
    60, "RIS-REJETS-REPETES": 2}`) ; sans lui, les seuils par défaut s'appliquent.
    """

    def post(self, requete, project_id):
        d = corps(requete)
        codes = d.get("codes")
        if codes is not None and (
            not isinstance(codes, list) or not codes or not all(isinstance(c, str) for c in codes)
        ):
            refuser("api.champ_invalide", champ="codes", attendu="liste de textes non vide")
        seuils = _objet(d, "seuils")
        resultat = installer_bibliotheque(
            utilisateur=requete.user,
            project_id=project_id,
            valid_from=champ_date(d, "valid_from"),
            codes=codes,
            seuils=seuils,
        )
        return reponse(
            {
                "crees": sorted(c.code for c in resultat.crees),
                "deja_presents": sorted(resultat.deja_presents),
            },
            201 if resultat.crees else 200,
        )


# --- évaluations, décisions, justifications, dérogations (L11-D7) -------------------------------
#
# Les évaluations sont écrites par le moteur (à la validation d'une écriture, à la préparation d'une
# demande…) : l'API les LIT et permet aux personnes habilitées de les traiter. Le journal reste en
# ajout seul : trancher, justifier ou déroger ajoute une ligne, ne modifie jamais l'évaluation.

LIMITE_EVALUATIONS = 200


def _evaluation(e: EvaluationControle, *, detail: bool = False) -> dict:
    sortie = {
        "id": e.id,
        "controle": e.controle.code,
        "controle_version": e.controle_version,
        "objet_type": e.objet_type,
        "objet_id": e.objet_id,
        "resultat": e.resultat,
        "severity": e.severity,
        "message": e.message,
        "action_corrective": e.action_corrective,
        "valeur_constatee": e.valeur_constatee,
        "valeur_attendue": e.valeur_attendue,
        "exigence": e.exigence_code or None,
        "evaluee_le": e.evaluee_le,
    }
    if detail:
        sortie["decisions"] = [
            {"decision": d.decision, "motif": d.motif, "decided_at": d.decided_at}
            for d in e.decisions.order_by("decided_at", "id")
        ]
        sortie["justifications"] = [
            {"texte": j.texte, "auteur": j.auteur_nom, "created_at": j.created_at}
            for j in e.justifications.order_by("created_at", "id")
        ]
        sortie["derogations"] = [_derogation(x) for x in e.derogations.order_by("created_at", "id")]
    return sortie


def _derogation(x: Derogation) -> dict:
    return {
        "id": x.id,
        "evaluation": x.evaluation_id,
        "controle": x.controle.code,
        "objet_type": x.objet_type,
        "objet_id": x.objet_id,
        "motif": x.motif,
        "justificatif": x.justificatif,
        "valide_du": x.valide_du,
        "valide_jusquau": x.valide_jusquau,
        "statut": x.statut,
        "motif_decision": x.motif_decision,
    }


def _uuid_param(requete, nom: str):
    brut = requete.query_params.get(nom)
    if not brut:
        return None
    try:
        return uuid.UUID(brut)
    except ValueError:
        refuser("api.champ_invalide", champ=nom, attendu="identifiant")


def _evaluation_du_projet(project_id, evaluation_id) -> EvaluationControle:
    return objet_ou_404(EvaluationControle, pk=evaluation_id, project_id=project_id)


class Evaluations(VueMetier):
    """Le journal des évaluations, du plus récent au plus ancien, filtrable, BORNÉ à 200."""

    def get(self, requete, project_id):
        habilite(requete.user, "consulter", project_id)
        evaluations = EvaluationControle.objects.filter(project_id=project_id).select_related(
            "controle"
        )
        for filtre, champ in (("objet_type", "objet_type"), ("controle", "controle__code")):
            valeur = requete.query_params.get(filtre)
            if valeur:
                evaluations = evaluations.filter(**{champ: valeur})
        resultat = requete.query_params.get("resultat")
        if resultat:
            if resultat not in Resultat.values:
                refuser("controles_api.resultat_inconnu", resultat=resultat)
            evaluations = evaluations.filter(resultat=resultat)
        objet = _uuid_param(requete, "objet_id")
        if objet is not None:
            evaluations = evaluations.filter(objet_id=objet)
        evaluations = evaluations.order_by("-created_at", "-id")[:LIMITE_EVALUATIONS]
        return reponse([_evaluation(e) for e in evaluations])


class EvaluationDetail(VueMetier):
    def get(self, requete, project_id, evaluation_id):
        habilite(requete.user, "consulter", project_id)
        e = _evaluation_du_projet(project_id, evaluation_id)
        return reponse(_evaluation(e, detail=True))


class EvaluationDecision(VueMetier):
    """Une personne habilitée (`valider`) tranche un contrôle « à vérifier »."""

    def post(self, requete, project_id, evaluation_id):
        e = _evaluation_du_projet(project_id, evaluation_id)
        d = corps(requete)
        trancher(
            utilisateur=requete.user,
            evaluation=e,
            decision=champ_texte(d, "decision"),
            motif=champ_texte(d, "motif", obligatoire=False, defaut=""),
        )
        return reponse(_evaluation(recharge(e), detail=True), 201)


class EvaluationJustification(VueMetier):
    def post(self, requete, project_id, evaluation_id):
        e = _evaluation_du_projet(project_id, evaluation_id)
        justifier(
            utilisateur=requete.user,
            evaluation=e,
            texte=champ_texte(corps(requete), "texte", obligatoire=False, defaut=""),
        )
        return reponse(_evaluation(recharge(e), detail=True), 201)


class EvaluationDerogation(VueMetier):
    """Demande une dérogation pour UN résultat bloquant, sur UN objet, pour une durée bornée."""

    def post(self, requete, project_id, evaluation_id):
        e = _evaluation_du_projet(project_id, evaluation_id)
        d = corps(requete)
        derogation = demander_derogation(
            utilisateur=requete.user,
            evaluation=e,
            motif=champ_texte(d, "motif", obligatoire=False, defaut=""),
            justificatif=champ_texte(d, "justificatif", obligatoire=False, defaut=""),
            valide_du=champ_date(d, "valide_du"),
            valide_jusquau=champ_date(d, "valide_jusquau"),
        )
        return reponse(_derogation(recharge(derogation)), 201)


class Derogations(VueMetier):
    def get(self, requete, project_id):
        habilite(requete.user, "consulter", project_id)
        derogations = Derogation.objects.filter(project_id=project_id).select_related("controle")
        statut = requete.query_params.get("statut")
        if statut:
            if statut not in StatutDerogation.values:
                refuser("controles_api.statut_derogation_inconnu", statut=statut)
            derogations = derogations.filter(statut=statut)
        return reponse([_derogation(x) for x in derogations.order_by("created_at", "id")])


class DerogationDecision(VueMetier):
    """Approuve ou refuse : `valider`, et jamais par le demandeur lui-même."""

    def post(self, requete, project_id, derogation_id):
        derogation = objet_ou_404(Derogation, pk=derogation_id, project_id=project_id)
        d = corps(requete)
        approuver = d.get("approuver")
        if not isinstance(approuver, bool):
            refuser("api.champ_invalide", champ="approuver", attendu="booléen")
        decider_derogation(
            utilisateur=requete.user,
            derogation=derogation,
            approuver=approuver,
            motif=champ_texte(d, "motif", obligatoire=False, defaut=""),
        )
        return reponse(_derogation(recharge(derogation)))


class ControlesEnAttente(VueMetier):
    """Ce qui empêche d'avancer pour un objet : bloquant non dérogé, à vérifier non tranché."""

    def get(self, requete, project_id):
        habilite(requete.user, "consulter", project_id)
        objet_type = requete.query_params.get("objet_type")
        if not objet_type:
            refuser("api.champ_obligatoire", champ="objet_type")
        en_attente = controles_en_attente(
            project_id,
            objet_type,
            _uuid_param(requete, "objet_id"),
            parametre_date(requete, "date", obligatoire=False),
        )
        return reponse(
            [
                {"evaluation": e.id, "controle": e.controle.code, "raison": str(raison)}
                for e, raison in en_attente
            ]
        )


class DossierConformiteObjet(VueMetier):
    """Le dossier d'un objet : chaque contrôle, son dernier résultat, décisions et dérogations."""

    def get(self, requete, project_id):
        habilite(requete.user, "consulter", project_id)
        objet_type = requete.query_params.get("objet_type")
        if not objet_type:
            refuser("api.champ_obligatoire", champ="objet_type")
        fil = dossier_de_conformite(project_id, objet_type, _uuid_param(requete, "objet_id"))
        return reponse(
            [
                {
                    "le": e["le"],
                    "genre": e["genre"],
                    "controle": e["controle"],
                    "detail": e["detail"],
                }
                for e in fil
            ]
        )
