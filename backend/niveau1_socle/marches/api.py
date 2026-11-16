"""L'API HTTP du plan de passation, des avis, des contrats et des décomptes. Voir L9.

Session authentifiée, JSON, montants en chaînes. Chaque point d'accès appelle un SERVICE : c'est lui
qui contrôle l'habilitation sur le projet de l'objet (403) ; la base isole les organisations (404).
Les refus métier ont un code stable (voir `core/api.py`).
"""

from core.api import (
    VueMetier,
    champ,
    champ_date,
    champ_decimal,
    champ_octets,
    champ_texte,
    champ_uuid,
    corps,
    objet_ou_404,
    parametre_date,
    parametre_entier,
    projeter,
    recharge,
    reponse,
)
from core.metier import habilite
from niveau1_socle.budget.models import Engagement
from niveau1_socle.financements.models import CompteBancaire
from niveau1_socle.referentiels.models import Tiers

from . import avis as svc_avis
from . import contrats as svc_contrats
from . import decomptes as svc_decomptes
from . import plan as svc_plan
from .models import (
    AvisNonObjection,
    Contrat,
    Decompte,
    Garantie,
    LignePassation,
    MethodePassation,
    PlanPassation,
)

# --- vues d'objets -----------------------------------------------------------------------------


def vue_methode(m: MethodePassation) -> dict:
    return projeter(
        m,
        "id",
        "code",
        "version",
        "label",
        "devise",
        "seuil_min",
        "seuil_max",
        "exige_non_objection",
        "valid_from",
        "valid_to",
    )


def vue_plan(p: PlanPassation) -> dict:
    return projeter(p, "id", "code", "nom", "date_debut", "date_fin")


def vue_ligne(ligne: LignePassation, *, detail: bool = False) -> dict:
    sortie = projeter(
        ligne,
        "id",
        "plan_id",
        "reference",
        "libelle",
        "montant_prevu",
        "devise",
        "statut",
        "non_objection_requise",
        "date_lancement_prevue",
        "date_attribution_prevue",
        "date_signature_prevue",
        methode=f"{ligne.methode.code} v{ligne.methode.version}",
    )
    if detail:
        sortie["etapes"] = [
            projeter(e, "statut", "date_effet", "note") for e in ligne.etapes.order_by("created_at")
        ]
        sortie["avis"] = [vue_avis(a) for a in ligne.avis.order_by("created_at")]
        contrat = Contrat.objects.filter(ligne=ligne).first()
        sortie["contrat_id"] = str(contrat.id) if contrat else None
    return sortie


def vue_avis(a: AvisNonObjection) -> dict:
    return projeter(
        a,
        "id",
        "ligne_id",
        "objet",
        "statut",
        "date_demande",
        "date_decision",
        "reference_bailleur",
        "motif",
        pieces=[projeter(p, "id", "nature", "nom", "taille") for p in a.pieces.all()],
    )


def vue_contrat(c: Contrat) -> dict:
    return projeter(
        c,
        "id",
        "ligne_id",
        "reference",
        "objet",
        "montant_initial",
        "devise",
        "date_signature",
        "date_debut",
        "date_fin_initiale",
        montant_courant=svc_contrats.montant_courant(c),
        date_fin_courante=svc_contrats.date_fin_courante(c),
        avenants=[
            projeter(a, "numero", "date_effet", "montant", "date_fin", "motif", "avis_id")
            for a in c.avenants.order_by("numero")
        ],
        garanties=[
            projeter(g, "id", "type_garantie", "reference", "montant", "date_echeance", "statut")
            for g in c.garanties.order_by("date_echeance", "reference")
        ],
    )


def vue_decompte(d: Decompte) -> dict:
    return projeter(
        d,
        "id",
        "contrat_id",
        "numero",
        "date_decompte",
        "montant_brut",
        "retenue",
        "avancement_physique",
        "statut",
        "date_decision",
        "engagement_id",
        "montant_apure",
        "motif_rejet",
    )


# --- méthodes et plans -------------------------------------------------------------------------


class Methodes(VueMetier):
    def get(self, requete, project_id):
        habilite(requete.user, "consulter", project_id)
        methodes = MethodePassation.objects.filter(project_id=project_id).order_by(
            "code", "version"
        )
        return reponse([vue_methode(m) for m in methodes])

    def post(self, requete, project_id):
        habilite(requete.user, "parametrer", project_id)
        d = corps(requete)
        methode = svc_plan.definir_methode(
            utilisateur=requete.user,
            project_id=project_id,
            code=champ_texte(d, "code"),
            label=champ(d, "label"),
            devise=champ_texte(d, "devise"),
            seuil_min=champ_decimal(d, "seuil_min"),
            seuil_max=champ_decimal(d, "seuil_max", obligatoire=False),
            exige_non_objection=bool(d.get("exige_non_objection", False)),
            valid_from=champ_date(d, "valid_from"),
        )
        return reponse(vue_methode(recharge(methode)), 201)


class Plans(VueMetier):
    def get(self, requete, project_id):
        habilite(requete.user, "consulter", project_id)
        return reponse(
            [
                vue_plan(p)
                for p in PlanPassation.objects.filter(project_id=project_id).order_by("code")
            ]
        )

    def post(self, requete, project_id):
        habilite(requete.user, "saisir", project_id)
        d = corps(requete)
        plan = svc_plan.creer_plan(
            utilisateur=requete.user,
            project_id=project_id,
            code=champ_texte(d, "code"),
            nom=champ_texte(d, "nom"),
            date_debut=champ_date(d, "date_debut"),
            date_fin=champ_date(d, "date_fin"),
        )
        return reponse(vue_plan(recharge(plan)), 201)


class PlanDetail(VueMetier):
    def get(self, requete, plan_id):
        plan = objet_ou_404(PlanPassation, pk=plan_id)
        synthese = svc_plan.synthese(utilisateur=requete.user, plan=plan)
        return reponse(
            {
                **vue_plan(plan),
                "nombre": synthese["nombre"],
                "non_objection_requise": synthese["non_objection_requise"],
                "par_statut": [
                    {"statut": s, "devise": dv, "montant": m}
                    for (s, dv), m in sorted(synthese["par_statut"].items())
                ],
                "par_methode": [
                    {"methode": c, "devise": dv, "montant": m}
                    for (c, dv), m in sorted(synthese["par_methode"].items())
                ],
            }
        )


class LignesDuPlan(VueMetier):
    def get(self, requete, plan_id):
        plan = objet_ou_404(PlanPassation, pk=plan_id)
        habilite(requete.user, "consulter", plan.project_id)
        return reponse([vue_ligne(ligne) for ligne in plan.lignes.order_by("reference")])

    def post(self, requete, plan_id):
        plan = objet_ou_404(PlanPassation, pk=plan_id)
        habilite(requete.user, "saisir", plan.project_id)
        d = corps(requete)
        ligne = svc_plan.ajouter_ligne(
            utilisateur=requete.user,
            plan=plan,
            reference=champ_texte(d, "reference"),
            libelle=champ_texte(d, "libelle"),
            montant_prevu=champ_decimal(d, "montant_prevu"),
            devise=champ_texte(d, "devise"),
            methode_code=champ_texte(d, "methode_code"),
            date_lancement_prevue=champ_date(d, "date_lancement_prevue"),
            date_attribution_prevue=champ_date(d, "date_attribution_prevue"),
            date_signature_prevue=champ_date(d, "date_signature_prevue"),
            categorie_id=champ_uuid(d, "categorie_id", obligatoire=False),
        )
        return reponse(vue_ligne(recharge(ligne)), 201)


class LigneDetail(VueMetier):
    def get(self, requete, ligne_id):
        ligne = objet_ou_404(LignePassation, pk=ligne_id)
        habilite(requete.user, "consulter", ligne.project_id)
        return reponse(vue_ligne(ligne, detail=True))


class LigneAvancer(VueMetier):
    def post(self, requete, ligne_id):
        ligne = objet_ou_404(LignePassation, pk=ligne_id)
        habilite(requete.user, "saisir", ligne.project_id)
        d = corps(requete)
        ligne = svc_plan.avancer_ligne(
            utilisateur=requete.user,
            ligne=ligne,
            statut=champ_texte(d, "statut"),
            date_effet=champ_date(d, "date_effet"),
            note=champ_texte(d, "note", obligatoire=False, defaut=""),
        )
        return reponse(vue_ligne(recharge(ligne)))


class LigneReplanifier(VueMetier):
    def post(self, requete, ligne_id):
        ligne = objet_ou_404(LignePassation, pk=ligne_id)
        habilite(requete.user, "saisir", ligne.project_id)
        d = corps(requete)
        ligne = svc_plan.replanifier(
            utilisateur=requete.user,
            ligne=ligne,
            motif=champ_texte(d, "motif", obligatoire=False, defaut=""),
            date_lancement_prevue=champ_date(d, "date_lancement_prevue"),
            date_attribution_prevue=champ_date(d, "date_attribution_prevue"),
            date_signature_prevue=champ_date(d, "date_signature_prevue"),
        )
        return reponse(vue_ligne(recharge(ligne)))


class LigneModifier(VueMetier):
    def post(self, requete, ligne_id):
        ligne = objet_ou_404(LignePassation, pk=ligne_id)
        habilite(requete.user, "saisir", ligne.project_id)
        d = corps(requete)
        ligne = svc_plan.modifier_ligne_prevue(
            utilisateur=requete.user,
            ligne=ligne,
            montant_prevu=champ_decimal(d, "montant_prevu"),
            methode_code=champ_texte(d, "methode_code", obligatoire=False),
        )
        return reponse(vue_ligne(recharge(ligne)))


class Retards(VueMetier):
    def get(self, requete, project_id):
        retards = svc_plan.lignes_en_retard(
            utilisateur=requete.user, project_id=project_id, jour=parametre_date(requete, "jour")
        )
        return reponse(
            [
                {
                    "ligne": vue_ligne(r.ligne),
                    "etape_attendue": r.etape_attendue,
                    "date_prevue": r.date_prevue,
                    "jours": r.jours,
                }
                for r in retards
            ]
        )


# --- avis de non-objection ---------------------------------------------------------------------


class AvisDeLaLigne(VueMetier):
    def post(self, requete, ligne_id):
        ligne = objet_ou_404(LignePassation, pk=ligne_id)
        habilite(requete.user, "saisir", ligne.project_id)
        d = corps(requete)
        avis = svc_avis.demander_avis(
            utilisateur=requete.user,
            ligne=ligne,
            objet=champ_texte(d, "objet"),
            date_demande=champ_date(d, "date_demande"),
        )
        return reponse(vue_avis(recharge(avis)), 201)


class AvisDetail(VueMetier):
    def get(self, requete, avis_id):
        avis = objet_ou_404(AvisNonObjection, pk=avis_id)
        habilite(requete.user, "consulter", avis.project_id)
        return reponse(vue_avis(avis))


class AvisDecision(VueMetier):
    def post(self, requete, avis_id):
        avis = objet_ou_404(AvisNonObjection, pk=avis_id)
        habilite(requete.user, "saisir", avis.project_id)
        d = corps(requete)
        avis = svc_avis.enregistrer_decision(
            utilisateur=requete.user,
            avis=avis,
            statut=champ_texte(d, "statut"),
            date_decision=champ_date(d, "date_decision"),
            reference_bailleur=champ_texte(d, "reference_bailleur", obligatoire=False, defaut=""),
            motif=champ_texte(d, "motif", obligatoire=False, defaut=""),
        )
        return reponse(vue_avis(recharge(avis)))


class AvisPieces(VueMetier):
    def post(self, requete, avis_id):
        avis = objet_ou_404(AvisNonObjection, pk=avis_id)
        habilite(requete.user, "saisir", avis.project_id)
        d = corps(requete)
        piece = svc_avis.joindre_piece(
            utilisateur=requete.user,
            avis=avis,
            nature=champ_texte(d, "nature"),
            nom=champ_texte(d, "nom"),
            contenu=champ_octets(d, "contenu_base64"),
        )
        return reponse(projeter(recharge(piece), "id", "nature", "nom", "taille"), 201)


class AvisEnAttente(VueMetier):
    def get(self, requete, project_id):
        attente = svc_avis.avis_en_attente(
            utilisateur=requete.user, project_id=project_id, jour=parametre_date(requete, "jour")
        )
        return reponse([{**vue_avis(a), "jours_d_attente": jours} for a, jours in attente])


# --- contrats, avenants, garanties -------------------------------------------------------------


class ContratDeLaLigne(VueMetier):
    def post(self, requete, ligne_id):
        ligne = objet_ou_404(LignePassation, pk=ligne_id)
        habilite(requete.user, "saisir", ligne.project_id)
        d = corps(requete)
        contrat = svc_contrats.conclure_contrat(
            utilisateur=requete.user,
            ligne=ligne,
            reference=champ_texte(d, "reference"),
            tiers=objet_ou_404(Tiers, pk=champ_uuid(d, "tiers")),
            objet=champ_texte(d, "objet"),
            montant=champ_decimal(d, "montant"),
            date_signature=champ_date(d, "date_signature"),
            date_debut=champ_date(d, "date_debut"),
            date_fin=champ_date(d, "date_fin"),
        )
        return reponse(vue_contrat(recharge(contrat)), 201)


class ContratDetail(VueMetier):
    def get(self, requete, contrat_id):
        contrat = objet_ou_404(Contrat, pk=contrat_id)
        habilite(requete.user, "consulter", contrat.project_id)
        return reponse(vue_contrat(recharge(contrat)))


class ContratAvenants(VueMetier):
    def post(self, requete, contrat_id):
        contrat = objet_ou_404(Contrat, pk=contrat_id)
        habilite(requete.user, "saisir", contrat.project_id)
        d = corps(requete)
        id_avis = champ_uuid(d, "avis", obligatoire=False)
        svc_contrats.ajouter_avenant(
            utilisateur=requete.user,
            contrat=contrat,
            date_effet=champ_date(d, "date_effet"),
            montant=champ_decimal(d, "montant"),
            date_fin=champ_date(d, "date_fin"),
            motif=champ_texte(d, "motif", obligatoire=False, defaut=""),
            avis=objet_ou_404(AvisNonObjection, pk=id_avis) if id_avis else None,
        )
        return reponse(vue_contrat(recharge(contrat)), 201)


class ContratGaranties(VueMetier):
    def post(self, requete, contrat_id):
        contrat = objet_ou_404(Contrat, pk=contrat_id)
        habilite(requete.user, "saisir", contrat.project_id)
        d = corps(requete)
        garantie = svc_contrats.enregistrer_garantie(
            utilisateur=requete.user,
            contrat=contrat,
            type_garantie=champ_texte(d, "type_garantie"),
            emetteur=champ_texte(d, "emetteur"),
            reference=champ_texte(d, "reference"),
            montant=champ_decimal(d, "montant"),
            date_emission=champ_date(d, "date_emission"),
            date_echeance=champ_date(d, "date_echeance"),
        )
        return reponse(
            projeter(recharge(garantie), "id", "type_garantie", "reference", "montant", "statut"),
            201,
        )


class GarantieCloture(VueMetier):
    def post(self, requete, garantie_id):
        garantie = objet_ou_404(Garantie, pk=garantie_id)
        habilite(requete.user, "saisir", garantie.project_id)
        d = corps(requete)
        garantie = svc_contrats.cloturer_garantie(
            utilisateur=requete.user,
            garantie=garantie,
            statut=champ_texte(d, "statut"),
            date_cloture=champ_date(d, "date_cloture"),
            note=champ_texte(d, "note", obligatoire=False, defaut=""),
        )
        return reponse(projeter(recharge(garantie), "id", "statut", "date_cloture", "note_cloture"))


class Alertes(VueMetier):
    def get(self, requete, project_id):
        alertes = svc_contrats.alertes_echeances(
            utilisateur=requete.user,
            project_id=project_id,
            jour=parametre_date(requete, "jour"),
            horizon_jours=parametre_entier(requete, "horizon_jours"),
        )
        return reponse(
            [
                {
                    "nature": a.nature,
                    "reference": a.reference,
                    "echeance": a.echeance,
                    "jours_restants": a.jours_restants,
                    "etat": a.etat,
                }
                for a in alertes
            ]
        )


# --- décomptes, certification, paiements -------------------------------------------------------


class ContratDecomptes(VueMetier):
    def get(self, requete, contrat_id):
        contrat = objet_ou_404(Contrat, pk=contrat_id)
        habilite(requete.user, "consulter", contrat.project_id)
        return reponse([vue_decompte(d) for d in contrat.decomptes.order_by("numero")])

    def post(self, requete, contrat_id):
        contrat = objet_ou_404(Contrat, pk=contrat_id)
        habilite(requete.user, "saisir", contrat.project_id)
        d = corps(requete)
        decompte = svc_decomptes.soumettre_decompte(
            utilisateur=requete.user,
            contrat=contrat,
            date_decompte=champ_date(d, "date_decompte"),
            montant_brut=champ_decimal(d, "montant_brut"),
            avancement_physique=champ_decimal(d, "avancement_physique"),
            retenue=champ_decimal(d, "retenue", obligatoire=False, defaut="0"),
            facture_reference=champ_texte(d, "facture_reference", obligatoire=False, defaut=""),
            facture_date=champ_date(d, "facture_date", obligatoire=False),
        )
        return reponse(vue_decompte(recharge(decompte)), 201)


class ContratSituation(VueMetier):
    def get(self, requete, contrat_id):
        contrat = objet_ou_404(Contrat, pk=contrat_id)
        s = svc_decomptes.situation_contrat(utilisateur=requete.user, contrat=contrat)
        return reponse(
            {
                "montant_courant": s.montant_courant,
                "certifie": s.certifie,
                "solde_contractuel": s.solde_contractuel,
                "net_certifie": s.net_certifie,
                "paye": s.paye,
                "reste_a_payer": s.reste_a_payer,
                "taux_financier": s.taux_financier,
                "taux_physique": s.taux_physique,
            }
        )


class DecompteDetail(VueMetier):
    def get(self, requete, decompte_id):
        decompte = objet_ou_404(Decompte, pk=decompte_id)
        habilite(requete.user, "consulter", decompte.project_id)
        return reponse(vue_decompte(decompte))


class DecompteCertifier(VueMetier):
    def post(self, requete, decompte_id):
        decompte = objet_ou_404(Decompte, pk=decompte_id)
        habilite(requete.user, "valider", decompte.project_id)
        d = corps(requete)
        decompte = svc_decomptes.certifier_decompte(
            utilisateur=requete.user,
            decompte=decompte,
            engagement=objet_ou_404(Engagement, pk=champ_uuid(d, "engagement")),
            date_certification=champ_date(d, "date_certification"),
            montant_apure=champ_decimal(d, "montant_apure", obligatoire=False),
        )
        return reponse(vue_decompte(recharge(decompte)))


class DecompteRejeter(VueMetier):
    def post(self, requete, decompte_id):
        decompte = objet_ou_404(Decompte, pk=decompte_id)
        habilite(requete.user, "valider", decompte.project_id)
        d = corps(requete)
        decompte = svc_decomptes.rejeter_decompte(
            utilisateur=requete.user,
            decompte=decompte,
            date_decision=champ_date(d, "date_decision"),
            motif=champ_texte(d, "motif", obligatoire=False, defaut=""),
        )
        return reponse(vue_decompte(recharge(decompte)))


class DecomptePaiements(VueMetier):
    def post(self, requete, decompte_id):
        decompte = objet_ou_404(Decompte, pk=decompte_id)
        habilite(requete.user, "saisir", decompte.project_id)
        d = corps(requete)
        paiement = svc_decomptes.enregistrer_paiement(
            utilisateur=requete.user,
            decompte=decompte,
            reference=champ_texte(d, "reference"),
            date_paiement=champ_date(d, "date_paiement"),
            montant=champ_decimal(d, "montant"),
            compte_bancaire=objet_ou_404(CompteBancaire, pk=champ_uuid(d, "compte_bancaire")),
            compte_fournisseur=champ_texte(d, "compte_fournisseur"),
            compte_banque=champ_texte(d, "compte_banque"),
            journal=champ_texte(d, "journal"),
            taux=champ_decimal(d, "taux", obligatoire=False),
        )
        return reponse(
            projeter(
                recharge(paiement), "id", "reference", "date_paiement", "montant", "ecriture_id"
            ),
            201,
        )
