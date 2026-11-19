"""La descente complète : cellule → sélection → lignes → écriture → pièces → scan. Voir L7-T03.

Une cellule d'un rapport PUBLIÉ se retrace avec le modèle, les mappings et les paramètres d'alors
(ceux que le rapport a gardés), sur les écritures comptabilisées avant sa publication : la somme
des lignes rendues est la valeur publiée, au centime, ou l'écart est dit.

- une cellule d'agrégat rend ses lignes ;
- une cellule calculée rend les cellules dont sa formule dépend, avec leurs valeurs publiées, et
  l'écart entre la formule recalculée et la valeur publiée : on descend d'une cellule à l'autre ;
- une écriture rend ses lignes et ses pièces justificatives ;
- une pièce rend son scan, après vérification de son empreinte.
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import connection

from niveau1_socle.comptabilite.models import PieceJustificative
from niveau4_reporting.moteur.compilateur import compiler
from niveau4_reporting.moteur.formules import evaluer, references
from niveau4_reporting.moteur.tracabilite import tracer

from .dossier import regle_de_la_rubrique
from .models import RapportPublie
from .rapports import SEP, _tables_par_code

ZERO = Decimal(0)


class CelluleInconnue(LookupError):
    """La rubrique ou la colonne n'existe pas dans ce rapport."""


@dataclass(frozen=True)
class LigneDescente:
    id: object
    ecriture_id: object
    numero: str | None
    journal: str
    date: datetime.date
    compte: str
    montant: Decimal


@dataclass
class Descente:
    rubrique: str
    colonne: str
    type: str  # "aggregate" | "computed"
    valeur_publiee: Decimal
    regle: str
    lignes: list[LigneDescente] = field(default_factory=list)
    posterieures: int = 0  # lignes comptabilisées APRÈS la publication, laissées de côté
    composantes: list[tuple[str, Decimal]] = field(default_factory=list)

    @property
    def somme(self) -> Decimal:
        if self.type == "aggregate":
            return sum((ligne.montant for ligne in self.lignes), ZERO)
        return self._recalcul

    _recalcul: Decimal = ZERO

    @property
    def ecart(self) -> Decimal:
        return self.somme - self.valeur_publiee

    @property
    def coherente(self) -> bool:
        return self.ecart == 0


def _valeur_publiee(rapport: RapportPublie, rubrique: str, colonne: str) -> Decimal:
    try:
        return Decimal(rapport.values[f"{rubrique}{SEP}{colonne}"])
    except KeyError:
        raise CelluleInconnue(f"{rubrique}/{colonne}") from None


def descendre_cellule(rapport: RapportPublie, rubrique: str, colonne: str) -> Descente:
    publiee = _valeur_publiee(rapport, rubrique, colonne)
    ligne_modele = next((r for r in rapport.modele["rows"] if r["code"] == rubrique), None)
    if ligne_modele is None or ligne_modele.get("type") not in ("aggregate", "computed"):
        raise CelluleInconnue(f"{rubrique}/{colonne}")  # un intitulé n'a pas de cellule à tracer
    regle = regle_de_la_rubrique(rapport, rubrique)
    if ligne_modele["type"] == "computed":
        codes = [r["code"] for r in rapport.modele["rows"]]
        dependances = sorted(references(ligne_modele["formula"], codes))
        valeurs = {
            code: Decimal(rapport.values[f"{code}{SEP}{colonne}"])
            for code in codes
            if f"{code}{SEP}{colonne}" in rapport.values
        }
        descente = Descente(rubrique, colonne, "computed", publiee, regle)
        descente.composantes = [(d, valeurs[d]) for d in dependances if d in valeurs]
        descente._recalcul = evaluer(ligne_modele["formula"], valeurs, codes)
        return descente
    etat = compiler(rapport.modele, _regles(rapport), rapport.params)
    trace = tracer(etat, rubrique, colonne)
    identifiants = [ligne.id for ligne in trace.lignes]
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id, ecriture_id, numero, journal, comptabilisee_le "
            "FROM moteur_ligneecriture WHERE id = ANY(%s)",
            [identifiants],
        )
        details = {r[0]: r for r in cur.fetchall()}
    lignes, posterieures = [], 0
    for t in trace.lignes:
        _, ecriture_id, numero, journal, posee_le = details[t.id]
        if posee_le is not None and posee_le > rapport.published_at:
            posterieures += 1  # arrivée depuis la publication : pas dans le rapport
            continue
        lignes.append(
            LigneDescente(
                t.id, ecriture_id, numero, journal, t.accounting_date, t.compte, t.montant
            )
        )
    descente = Descente(rubrique, colonne, "aggregate", publiee, regle, lignes, posterieures)
    return descente


def _regles(rapport: RapportPublie) -> dict:
    return {
        code: list(table.regles.all())
        for code, table in _tables_par_code(rapport.mapping_versions).items()
    }


@dataclass(frozen=True)
class EcritureDetail:
    id: object
    numero: str | None
    journal: str
    date: datetime.date
    libelle: str
    lignes: list[LigneDescente]
    pieces: list[PieceJustificative]


def detail_ecriture(project_id, ecriture_id) -> EcritureDetail | None:
    """L'écriture comptabilisée, ses lignes et ses pièces ; `None` si elle n'existe pas ici."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id, ecriture_id, numero, journal, accounting_date, compte, "
            "       debit - credit, libelle_ecriture "
            "FROM moteur_ligneecriture WHERE ecriture_id = %s AND project_id = %s "
            "ORDER BY ligne_no",
            [ecriture_id, project_id],
        )
        rangees = cur.fetchall()
    if not rangees:
        return None
    premiere = rangees[0]
    return EcritureDetail(
        id=ecriture_id,
        numero=premiere[2],
        journal=premiere[3],
        date=premiere[4],
        libelle=premiere[7],
        lignes=[LigneDescente(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in rangees],
        pieces=list(PieceJustificative.objects.filter(ecriture_id=ecriture_id).order_by("nom")),
    )
