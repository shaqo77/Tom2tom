"""Les contrôles actifs s'exécutent sur les dépenses d'une écriture, à sa validation. Voir L11-A4.

Avant, la bibliothèque de contrôles (codification, pièces…) n'était évaluée nulle part sur le grand
livre : un contrôle « dépense sans catégorie » pouvait être actif sans jamais rien arrêter.

Pour chaque ligne de charge de l'écriture (même définition que le contrôle budgétaire : compte
budgété, côté débit), on construit le contexte de la dépense et on évalue les contrôles ACTIFS de
codification et de pièces. Un résultat bloquant (ou « à vérifier » non tranché) refuse la validation
(`CONTROLE_BLOQUANT`) ; un avertissement la laisse passer et se lit sur l'écriture.

Les évaluations sont écrites AVANT la transaction de validation : un refus ne les efface pas, sinon
un contrôle « à vérifier » ne pourrait jamais être tranché (la décision porte sur une évaluation
conservée). Aucun contrôle n'est actif tant qu'une personne habilitée ne l'a pas activé (règle 9) :
sans contrôle actif, rien ne change.
"""

from django.db import connection

from core.i18n import langue_courante
from niveau1_socle.comptabilite.models import LigneEcriture, PieceJustificative

from .contextes import contexte_depense
from .models import EvaluationControle, Resultat
from .services import evaluer_tous, exiger_controles_tranches

TYPES_DE_REGLE = ("codification", "pieces")
OBJET = "ligne_ecriture"


def _lignes_de_charge(ecriture) -> list[LigneEcriture]:
    """Les charges de l'écriture : côté débit, sur un compte budgété (comme le budget)."""
    with connection.cursor() as cur:
        cur.execute(
            """SELECT l.id FROM comptabilite_ligneecriture l
                 JOIN referentiels_compte c ON c.id = l.account_id
                WHERE l.entry_id = %s AND budget_compte_budgete(c.code, c.classe)
                  AND l.debit - l.credit > 0
                ORDER BY l.line_no""",
            [ecriture.pk],
        )
        ids = [rangee[0] for rangee in cur.fetchall()]
    lignes = LigneEcriture.objects.select_related("entry", "account").in_bulk(ids)
    return [lignes[i] for i in ids]


def _en_attente_de_decision(ligne, type_regle: str) -> frozenset[str]:
    """Les contrôles dont la dernière évaluation sur cette ligne est « à vérifier » : on ne les
    réévalue pas (une nouvelle évaluation sans décision effacerait celle d'une personne)."""
    derniere: dict = {}
    for e in EvaluationControle.objects.filter(
        objet_type=OBJET, objet_id=ligne.pk, controle__type_regle=type_regle
    ).order_by("created_at", "id"):
        derniere[e.controle.code] = e
    return frozenset(c for c, e in derniere.items() if e.resultat == Resultat.A_VERIFIER)


def controler_ecriture(ecriture, *, utilisateur) -> list[str]:
    """Évalue les contrôles actifs sur les charges de l'écriture ; refuse si un contrôle bloque.

    Retourne les avertissements (texte dans la langue de la requête)."""
    pieces = [
        {"type": p.type_piece, "rattachee": True, "valide": True}
        for p in PieceJustificative.objects.filter(ecriture_id=ecriture.pk)
    ]
    langue = langue_courante()
    avertissements: list[str] = []
    for ligne in _lignes_de_charge(ecriture):
        contexte = contexte_depense(ligne, pieces=pieces)
        for type_regle in TYPES_DE_REGLE:
            evaluations = evaluer_tous(
                ecriture.project_id,
                type_regle,
                contexte,
                date_operation=ecriture.accounting_date,
                objet_type=OBJET,
                objet_id=ligne.pk,
                utilisateur=utilisateur,
                sauf=_en_attente_de_decision(ligne, type_regle),
            )
            avertissements += [
                f"{e.controle.code} : {e.message.get(langue, '')}"
                for e in evaluations
                if e.resultat == Resultat.AVERTISSEMENT
            ]
        exiger_controles_tranches(ecriture.project_id, OBJET, ligne.pk, ecriture.accounting_date)
    return avertissements
