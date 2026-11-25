"""L'API HTTP des écritures : saisir un brouillon (une clé de cofinancement par ligne si besoin),
le lire, le valider, le comptabiliser. E9a.

Montants en chaînes (jamais de `float`), comptes et accords désignés par leur CODE ou leur NUMÉRO.
Le serveur est l'autorité : équilibre, période ouverte, comptes imputables, accord actif, séparation
des tâches. Les droits sont ceux du service appelé (`saisir`, `valider`, `comptabiliser`).
"""

from core.api import (
    VueMetier,
    champ_date,
    champ_decimal,
    champ_texte,
    corps,
    objet_ou_404,
    projeter,
    reponse,
    reponse_liste,
)
from core.metier import habilite, refuser
from niveau1_socle.financements.models import Accord, Categorie
from niveau1_socle.referentiels.models import Tiers

from . import services
from .models import Ecriture

# Les axes qu'une ligne peut porter : des codes (textes), jamais des identifiants.
AXES = ("dim1", "dim2", "dim3", "dim4", "aux1", "aux2", "aux3", "aux4")
MONTANTS = ("debit", "credit")
LIGNES_MAX = 500


def _ligne_saisie(donnees, rang: int, project_id) -> dict:
    """Une ligne de la requête → le dictionnaire que `saisir_ecriture` attend."""
    if not isinstance(donnees, dict):
        refuser("api.champ_invalide", champ=f"lignes[{rang}]", attendu="objet")
    ligne: dict = {"compte": champ_texte(donnees, "compte")}
    for nom in MONTANTS:
        brut = champ_decimal(donnees, nom, obligatoire=False)
        if brut is not None:
            ligne[nom] = brut
    if not any(ligne.get(nom) for nom in MONTANTS):
        refuser("comptabilite.ligne_sans_montant", rang=rang)
    code_tiers = champ_texte(donnees, "tiers", obligatoire=False)
    if code_tiers:
        if not Tiers.objects.filter(code=code_tiers).exists():
            refuser("comptabilite.tiers_inconnu", code=code_tiers)
        ligne["tiers"] = code_tiers
    for nom in ("label", "cle", "categorie", *AXES):
        valeur = champ_texte(donnees, nom, obligatoire=False)
        if valeur:
            ligne[nom] = valeur
    numero = champ_texte(donnees, "accord", obligatoire=False)
    if numero:
        accord = Accord.objects.filter(project_id=project_id, numero=numero).first()
        if accord is None:
            refuser("comptabilite.accord_inconnu", numero=numero)
        ligne["agreement_id"] = accord.pk
    return ligne


def _ligne(ligne, numeros: dict, categories: dict) -> dict:
    return projeter(
        ligne,
        "line_no",
        "debit",
        "credit",
        "label",
        compte=ligne.account.code,
        accord=numeros.get(ligne.agreement_id),
        categorie=categories.get(ligne.category_id),
        cle_version=ligne.cofunding_key_version_id,
    )


def _ecriture(e: Ecriture, *, avec_lignes: bool = False) -> dict:
    sortie = projeter(
        e,
        "id",
        "number",
        "status",
        "label",
        "document_ref",
        "fx_rate",
        journal=e.journal.code,
        date_comptable=e.accounting_date,
        devise=e.currency_id,
        projet=e.project_id,
    )
    if avec_lignes:
        lignes = list(e.lignes.select_related("account").order_by("line_no", "id"))
        ids = {x.agreement_id for x in lignes if x.agreement_id}
        numeros = dict(Accord.objects.filter(pk__in=ids).values_list("pk", "numero"))
        ids_categories = {x.category_id for x in lignes if x.category_id}
        categories = dict(Categorie.objects.filter(pk__in=ids_categories).values_list("pk", "code"))
        sortie["lignes"] = [_ligne(x, numeros, categories) for x in lignes]
        sortie["total_debit"] = str(sum(x.debit for x in lignes))
        sortie["total_credit"] = str(sum(x.credit for x in lignes))
    return sortie


def _de_l_ecriture(project_id, ecriture_id) -> Ecriture:
    objet_ou_404(Ecriture, pk=ecriture_id, project_id=project_id)  # 404 si absente ou invisible
    return Ecriture.objects.select_related("journal").get(pk=ecriture_id)


class Ecritures(VueMetier):
    def get(self, requete, project_id):
        habilite(requete.user, "consulter", project_id)
        ecritures = Ecriture.objects.filter(project_id=project_id).select_related("journal")
        statut = requete.query_params.get("statut")
        if statut:
            ecritures = ecritures.filter(status=statut)
        return reponse_liste(requete, ecritures.order_by("-accounting_date", "-id"), _ecriture)

    def post(self, requete, project_id):
        d = corps(requete)
        brutes = d.get("lignes")
        if not isinstance(brutes, list) or not brutes:
            refuser("api.champ_invalide", champ="lignes", attendu="liste non vide")
        if len(brutes) > LIGNES_MAX:
            refuser("api.champ_invalide", champ="lignes", attendu=f"au plus {LIGNES_MAX} lignes")
        taux = champ_decimal(d, "taux", obligatoire=False)
        ecriture = services.saisir_ecriture(
            utilisateur=requete.user,
            project_id=project_id,
            journal=champ_texte(d, "journal"),
            date_comptable=champ_date(d, "date_comptable"),
            libelle=champ_texte(d, "libelle"),
            lignes=[_ligne_saisie(x, i, project_id) for i, x in enumerate(brutes, start=1)],
            devise=champ_texte(d, "devise", obligatoire=False),
            taux=taux if taux is not None else 1,
            reference_piece=champ_texte(d, "reference_piece", obligatoire=False, defaut=""),
            cle_idempotence=champ_texte(d, "cle_idempotence", obligatoire=False),
        )
        return reponse(_ecriture(_de_l_ecriture(project_id, ecriture.id), avec_lignes=True), 201)


class EcritureDetail(VueMetier):
    def get(self, requete, project_id, ecriture_id):
        habilite(requete.user, "consulter", project_id)
        return reponse(_ecriture(_de_l_ecriture(project_id, ecriture_id), avec_lignes=True))


class EcritureValider(VueMetier):
    def post(self, requete, project_id, ecriture_id):
        e = services.valider_ecriture(
            _de_l_ecriture(project_id, ecriture_id), utilisateur=requete.user
        )
        sortie = _ecriture(_de_l_ecriture(project_id, e.id), avec_lignes=True)
        sortie["avertissements"] = [
            str(a) for a in [*e.avertissements_budgetaires, *e.avertissements_controles]
        ]
        return reponse(sortie)


class EcritureComptabiliser(VueMetier):
    def post(self, requete, project_id, ecriture_id):
        e = services.comptabiliser_ecriture(
            _de_l_ecriture(project_id, ecriture_id), utilisateur=requete.user
        )
        return reponse(_ecriture(_de_l_ecriture(project_id, e.id), avec_lignes=True))
