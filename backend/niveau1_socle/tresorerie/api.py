"""L'API HTTP de la trésorerie : disponibilités, prévisions, relevés, appariements, reconstitution.

Même conventions que `niveau1_socle/marches/api.py`. Le numéro d'un compte n'est jamais renvoyé :
seulement son code, son type, sa devise et son numéro masqué.
"""

from core.api import (
    VueMetier,
    champ_date,
    champ_decimal,
    champ_entier,
    champ_texte,
    champ_uuid,
    corps,
    objet_ou_404,
    parametre_date,
    parametre_entier,
    projeter,
    recharge,
    reponse,
    reponse_liste,
)
from core.metier import habilite, refuser
from niveau1_socle.decaissements.models import DemandeRetrait
from niveau1_socle.financements.models import CompteBancaire
from niveau1_socle.rapprochement.models import MouvementReleve
from niveau1_socle.referentiels.models import ValeurDimension
from niveau4_reporting.modeles_etats import (
    modele_rapprochement_compte_designe,
    modele_reconciliation_compte_special,
)
from niveau4_reporting.publication.rapports import publier_rapport

from . import compte_special, services
from .models import AppariementDemande, JustificationCompteSpecial
from .releves import importer_releve

NOTE_MAX = 4000  # la note qui explique l'écart de la réconciliation du compte spécial


def _compte(c: CompteBancaire) -> dict:
    """Un compte, sans son numéro complet : seul le numéro masqué sort."""
    return {
        "id": c.id,
        "code": c.code,
        "libelle": c.libelle,
        "type": c.type,
        "devise": c.devise_id,
        "accord": c.accord.numero if c.accord_id else None,
        "numero_masque": c.numero_masque,
        "actif": c.actif,
    }


class ComptesBancaires(VueMetier):
    """Les comptes bancaires d'un projet : de quoi choisir un compte dans la trésorerie."""

    def get(self, requete, project_id):
        habilite(requete.user, "consulter", project_id)
        comptes = CompteBancaire.objects.filter(project_id=project_id).select_related("accord")
        return reponse_liste(requete, comptes.order_by("code", "id"), _compte)


class Disponibilites(VueMetier):
    def get(self, requete, project_id):
        d = services.disponibilites(
            utilisateur=requete.user, project_id=project_id, jour=parametre_date(requete, "jour")
        )
        return reponse(
            {
                "jour": d.jour,
                "comptes": [
                    {
                        "code": c.code,
                        "numero_masque": c.numero_masque,
                        "type": c.type,
                        "devise": c.devise,
                        "solde_comptable": c.solde_comptable,
                        "solde_releve": c.solde_releve,
                        "date_releve": c.date_releve,
                        "marge_plafond": c.marge_plafond,
                    }
                    for c in d.comptes
                ],
                "totaux_par_devise": d.totaux_par_devise(),
            }
        )


class Previsions(VueMetier):
    def get(self, requete, project_id):
        lignes = services.previsions(
            utilisateur=requete.user,
            project_id=project_id,
            annee=parametre_entier(requete, "annee"),
            mois=parametre_entier(requete, "mois"),
            nombre_mois=parametre_entier(requete, "nombre_mois"),
            par_axe=requete.query_params.get("par_axe", "true").lower() != "false",
        )
        return reponse(
            [
                {
                    "annee": p.annee,
                    "mois": p.mois,
                    "devise": p.devise,
                    "axe": p.axe,
                    "encaissements": p.encaissements,
                    "decaissements": p.decaissements,
                    "net": p.net,
                }
                for p in lignes
            ]
        )

    def post(self, requete, project_id):
        habilite(requete.user, "saisir", project_id)
        d = corps(requete)
        id_axe = champ_uuid(d, "axe", obligatoire=False)
        prevision = services.etablir_prevision(
            utilisateur=requete.user,
            project_id=project_id,
            devise=champ_texte(d, "devise"),
            annee=champ_entier(d, "annee"),
            mois=champ_entier(d, "mois"),
            encaissements=champ_decimal(d, "encaissements", obligatoire=False, defaut="0"),
            decaissements=champ_decimal(d, "decaissements", obligatoire=False, defaut="0"),
            axe=objet_ou_404(ValeurDimension, pk=id_axe) if id_axe else None,
            motif=champ_texte(d, "motif", obligatoire=False, defaut=""),
        )
        return reponse(
            projeter(
                recharge(prevision),
                "id",
                "annee",
                "mois",
                "devise",
                "revision",
                "encaissements",
                "decaissements",
            ),
            201,
        )


class ComptesSoldes(VueMetier):
    def post(self, requete, compte_id):
        compte = objet_ou_404(CompteBancaire, pk=compte_id)
        habilite(requete.user, "saisir", compte.project_id)
        d = corps(requete)
        solde = services.enregistrer_solde_releve(
            utilisateur=requete.user,
            compte=compte,
            date_solde=champ_date(d, "date_solde"),
            solde=champ_decimal(d, "solde"),
            reference=champ_texte(d, "reference", obligatoire=False, defaut=""),
        )
        return reponse(projeter(recharge(solde), "id", "date_solde", "solde", "reference"), 201)


class ComptesReleves(VueMetier):
    def post(self, requete, compte_id):
        compte = objet_ou_404(CompteBancaire, pk=compte_id)
        habilite(requete.user, "comptabiliser", compte.project_id)
        d = corps(requete)
        bilan = importer_releve(
            utilisateur=requete.user,
            compte=compte,
            contenu=champ_texte(d, "contenu"),
            format=champ_texte(d, "format", obligatoire=False),
            taux=champ_decimal(d, "taux", obligatoire=False),
        )
        return reponse(bilan, 201)


class ComptesReconstitution(VueMetier):
    def get(self, requete, compte_id):
        compte = objet_ou_404(CompteBancaire, pk=compte_id)
        e = services.etat_reconstitution(
            utilisateur=requete.user,
            compte=compte,
            date_debut=parametre_date(requete, "debut"),
            date_fin=parametre_date(requete, "fin"),
        )
        return reponse(
            {
                "compte": e.compte_code,
                "numero_masque": e.compte_masque,
                "devise": e.devise,
                "date_debut": e.date_debut,
                "date_fin": e.date_fin,
                "complet": e.complet,
                "manques": e.manques,
                "ouverture": e.ouverture,
                "avances_recues": [{"demande": n, "montant": m} for n, m in e.avances_recues],
                "autres_encaissements": e.autres_encaissements,
                "decaissements": e.decaissements,
                "cloture_calculee": e.cloture_calculee,
                "cloture_releve": e.cloture_releve,
                "ecart_releve": e.ecart_releve,
                "non_justifie_releve": e.non_justifie_releve,
                "solde_comptable": e.solde_comptable,
                "ecart_comptable": e.ecart_comptable,
                "non_justifie_comptable": e.non_justifie_comptable,
                "justifie": e.justifie,
                "plafond": e.plafond,
                "depasse_plafond": e.depasse_plafond,
            }
        )


class ComptesJustifications(VueMetier):
    def post(self, requete, compte_id):
        compte = objet_ou_404(CompteBancaire, pk=compte_id)
        habilite(requete.user, "valider", compte.project_id)
        d = corps(requete)
        j = services.justifier_ecart(
            utilisateur=requete.user,
            compte=compte,
            date_debut=champ_date(d, "date_debut"),
            date_fin=champ_date(d, "date_fin"),
            cible=champ_texte(d, "cible"),
            montant=champ_decimal(d, "montant"),
            explication=champ_texte(d, "explication", obligatoire=False, defaut=""),
        )
        return reponse(projeter(recharge(j), "id", "cible", "montant", "explication"), 201)


class ComptesRapport(VueMetier):
    """Publie l'état « rapprochement du compte désigné » (habilitation « publier »)."""

    def post(self, requete, compte_id):
        compte = objet_ou_404(CompteBancaire, pk=compte_id)
        habilite(requete.user, "publier", compte.project_id)
        d = corps(requete)
        debut, fin = champ_date(d, "date_debut"), champ_date(d, "date_fin")
        publie = publier_rapport(
            utilisateur=requete.user,
            project_id=compte.project_id,
            modele=modele_rapprochement_compte_designe(),
            params={
                "fiscal_year": fin.year,
                "current_period": fin.month,
                "compte_designe": compte.code,
                "date_debut": debut.isoformat(),
                "date_fin": fin.isoformat(),
            },
            tables={},
            period_from=debut,
            period_to=fin,
        )
        return reponse(
            {
                "id": publie.id,
                "modele": publie.template_code,
                "scelle": bytes(publie.seal).hex(),
                "valeurs": publie.values,
            },
            201,
        )


class MouvementAppariement(VueMetier):
    def post(self, requete, mouvement_id):
        mouvement = objet_ou_404(MouvementReleve, pk=mouvement_id)
        habilite(requete.user, "saisir", mouvement.project_id)
        d = corps(requete)
        appariement = services.apparier_demande(
            utilisateur=requete.user,
            mouvement=mouvement,
            demande=objet_ou_404(DemandeRetrait, pk=champ_uuid(d, "demande")),
        )
        return reponse(projeter(recharge(appariement), "id", "mouvement_id", "demande_id"), 201)


class AppariementAnnulation(VueMetier):
    def post(self, requete, appariement_id):
        appariement = objet_ou_404(AppariementDemande, pk=appariement_id)
        habilite(requete.user, "saisir", appariement.project_id)
        d = corps(requete)
        appariement = services.annuler_appariement(
            utilisateur=requete.user,
            appariement=appariement,
            motif=champ_texte(d, "motif", obligatoire=False, defaut=""),
        )
        return reponse(projeter(recharge(appariement), "id", "annule_at", "motif_annulation"))


# --- compte spécial (BAD) : justifications soumises à la Banque (L11-D4) -------------------


def _justification(j: JustificationCompteSpecial) -> dict:
    return {
        "id": j.id,
        "demande": j.demande.numero,
        "montant": j.montant,
        "date_soumission": j.date_soumission,
        "annulee": j.annule_at is not None,
        "motif_annulation": j.motif_annulation,
    }


class ComptesJustificationsBanque(VueMetier):
    """Les dépenses justifiées à la Banque, demande par demande, pour un compte spécial."""

    def get(self, requete, compte_id):
        compte = objet_ou_404(CompteBancaire, pk=compte_id)
        habilite(requete.user, "consulter", compte.project_id)
        justifications = JustificationCompteSpecial.objects.filter(compte=compte).select_related(
            "demande"
        )
        return reponse(
            [_justification(j) for j in justifications.order_by("date_soumission", "id")]
        )

    def post(self, requete, compte_id):
        compte = objet_ou_404(CompteBancaire, pk=compte_id)
        d = corps(requete)
        justification = compte_special.justifier_aupres_de_la_banque(
            utilisateur=requete.user,
            compte=compte,
            demande=objet_ou_404(DemandeRetrait, pk=champ_uuid(d, "demande")),
            montant=champ_decimal(d, "montant", obligatoire=False),
            date_soumission=champ_date(d, "date_soumission", obligatoire=False),
        )
        return reponse(_justification(recharge(justification)), 201)


class JustificationBanqueAnnulation(VueMetier):
    def post(self, requete, justification_id):
        justification = objet_ou_404(JustificationCompteSpecial, pk=justification_id)
        d = corps(requete)
        justification = compte_special.annuler_justification(
            utilisateur=requete.user,
            justification=justification,
            motif=champ_texte(d, "motif", obligatoire=False, defaut=""),
        )
        return reponse(_justification(recharge(justification)))


class ComptesSituationSpecial(VueMetier):
    """La situation du compte spécial à une date (lignes 2 à 7 de l'annexe 9), montants exacts."""

    def get(self, requete, compte_id):
        compte = objet_ou_404(CompteBancaire, pk=compte_id)
        habilite(requete.user, "consulter", compte.project_id)
        s = compte_special.calculer_situation(
            compte,
            parametre_date(requete, "date"),
            requete.query_params.get("demande") or None,
        )
        return reponse(
            {
                "compte": s.compte_code,
                "devise": s.devise,
                "date": s.date,
                "complet": s.complet,
                "manques": s.manques,
                "avances": [{"demande": n, "montant": m} for n, m in s.avances],
                "justifications": [
                    {
                        "demande": n,
                        "montant": m,
                        "date_soumission": jour,
                        "en_cours": en_cours,
                        "comptee": comptee,
                    }
                    for n, m, jour, en_cours, comptee in s.justifications
                ],
                "total_avances": s.total_avances,
                "solde_cloture": s.solde_cloture,
                "justifie_cette_demande": s.justifie_cette_demande,
                "justifie_precedemment": s.justifie_precedemment,
                "total_justifie": s.total_justifie,
                "ecart": s.ecart,
            }
        )


class ComptesRapportSpecial(VueMetier):
    """Publie la réconciliation du compte spécial (habilitation « publier »)."""

    def post(self, requete, compte_id):
        compte = objet_ou_404(CompteBancaire, pk=compte_id)
        habilite(requete.user, "publier", compte.project_id)
        d = corps(requete)
        fin = champ_date(d, "date_fin")
        params = {
            "fiscal_year": fin.year,
            "current_period": fin.month,
            "compte_special": compte.code,
            "date_fin": fin.isoformat(),
        }
        demande = champ_texte(d, "demande", obligatoire=False)
        if demande:
            params["demande"] = demande
        # L'écart s'explique dans une NOTE (renvoi v de l'annexe 9) : gardée avec le rapport publié,
        # donc scellée avec lui ; elle n'entre dans aucun calcul.
        note = champ_texte(d, "note_ecart", obligatoire=False)
        if note:
            if len(note) > NOTE_MAX:
                refuser("compte_special.note_trop_longue", maximum=NOTE_MAX)
            params["note_ecart"] = note
        publie = publier_rapport(
            utilisateur=requete.user,
            project_id=compte.project_id,
            modele=modele_reconciliation_compte_special(),
            params=params,
            tables={},
            period_from=champ_date(d, "date_debut", obligatoire=False) or fin.replace(day=1),
            period_to=fin,
        )
        return reponse(
            {
                "id": publie.id,
                "modele": publie.template_code,
                "scelle": bytes(publie.seal).hex(),
                "valeurs": publie.values,
            },
            201,
        )
