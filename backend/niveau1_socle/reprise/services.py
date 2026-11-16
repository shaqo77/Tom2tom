"""La chaîne de reprise : balance d'origine, soldes d'ouverture ou historique, contrôle, signature.

L8-T01 et L8-T02. La règle : une reprise n'est acceptée qu'à ÉCART NUL sur la balance générale (par
compte) ET sur le cumul par accord. L'écart par axe est listé mais ne bloque pas. Un écart non nul
est listé ligne à ligne et la reprise reste refusée : elle ne se signe pas.

Idempotence : chaque pièce de l'historique a une clé dérivée de la SOURCE (journal, numéro de pièce,
date) ; rejouer le même fichier ne crée rien, et une pièce de même clé au contenu différent est un
conflit signalé, jamais un écrasement ni un doublon. Tout ou rien : une ligne invalide, un
conflit ou une pièce déséquilibrée arrêtent l'import, rien n'est écrit.
"""

import datetime
import hashlib
import json
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from core.audit import journaliser
from core.erreurs import CodeErreur, ErreurMetier
from core.i18n import Liste, msg
from niveau1_socle.comptabilite.models import Ecriture, Journal, LigneEcriture
from niveau1_socle.exercices.models import Periode
from niveau1_socle.financements.models import Accord
from niveau1_socle.habilitations.permissions import est_habilite
from niveau1_socle.referentiels.imports import _normaliser, lire_fichier
from niveau1_socle.referentiels.models import Compte, Devise, Tiers, ValeurDimension

from .models import (
    LigneBalanceOrigine,
    ModeReprise,
    PieceReprise,
    RapportReprise,
    Reprise,
    StatutReprise,
)

ZERO = Decimal(0)
JOURNAL_PAR_DEFAUT = "REPRISE"
TAILLE_LOT = 500
MAX_ERREURS = 50  # on nomme les premières, on compte le reste

SYNONYMES = {
    "compte": {"compte", "numerocompte", "numcompte", "ncompte", "account", "codecompte"},
    "debit": {"debit", "debits", "montantdebit", "dr"},
    "credit": {"credit", "credits", "montantcredit", "cr"},
    "accord": {"accord", "numeroaccord", "agreement", "convention", "financement"},
    "axe1": {"axe1", "axe", "section", "projetanalytique", "dim1", "analytique"},
    "journal": {"journal", "codejournal", "jrn"},
    "piece": {"piece", "numeropiece", "numpiece", "ecriture", "numeroecriture", "reference"},
    "date": {"date", "datecomptable", "dateecriture", "datepiece"},
    "libelle": {"libelle", "intitule", "designation", "description", "label"},
    "tiers": {"tiers", "codetiers", "fournisseur", "auxiliaire"},
}
BALANCE = (("compte", "debit", "credit"), ("accord", "axe1"))
HISTORIQUE = (
    ("journal", "piece", "date", "compte", "debit", "credit"),
    ("libelle", "tiers", "accord", "axe1"),
)


def _habilite(utilisateur, operation: str, project_id) -> None:
    if not est_habilite(utilisateur, operation, project_id):
        raise PermissionDenied(msg("reprise.habilitation_requise", operation=operation))


def _refuser(cle: str, **params):
    raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg(cle, **params))


# --- lecture d'un fichier ---------------------------------------------------------------------


def _colonnes(entetes, champs, correspondance):
    """`champ -> en-tête du fichier`, par la correspondance donnée, sinon par synonymes."""
    par_norme = {_normaliser(e): e for e in entetes}
    trouvees, manquantes = {}, []
    for champ in champs[0] + champs[1]:
        voulu = (correspondance or {}).get(champ)
        if voulu is not None:
            if voulu not in entetes:
                _refuser("reprise.colonne_inconnue", colonne=voulu)
            trouvees[champ] = voulu
            continue
        candidat = next((par_norme[n] for n in SYNONYMES[champ] if n in par_norme), None)
        if candidat is not None:
            trouvees[champ] = candidat
        elif champ in champs[0]:
            manquantes.append(champ)
    if manquantes:
        _refuser("reprise.colonnes_obligatoires", v1=manquantes)
    return trouvees


_NOMBRE = re.compile(r"^-?\d+(\.\d+)?$")


def _decimal(texte: str) -> Decimal | None:
    t = (texte or "").replace("\xa0", "").replace(" ", "").replace(" ", "")
    if not t:
        return ZERO
    if "," in t and "." not in t:
        t = t.replace(",", ".")
    return Decimal(t) if _NOMBRE.match(t) else None


def _date(texte: str) -> datetime.date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(texte.strip()[:10], fmt).date()
        except ValueError:
            continue
    return None


@dataclass
class Erreurs:
    lignes: list = field(default_factory=list)
    total: int = 0

    def ajouter(self, ligne: int, cle: str, **params):
        self.total += 1
        if len(self.lignes) < MAX_ERREURS:
            self.lignes.append(
                msg("reprise.ligne_en_erreur", ligne=ligne, motif=msg(cle, **params))
            )

    def lever(self):
        if self.total:
            raise ErreurMetier(
                CodeErreur.REGLE_INVALIDE,
                msg(
                    "reprise.import_rejete",
                    n=self.total,
                    detail=Liste(self.lignes, " ; "),
                ),
            )


# --- ouvrir ---------------------------------------------------------------------------------


def ouvrir_reprise(
    *, utilisateur, project_id, nom: str, date_bascule: datetime.date, devise: str = "DJF"
) -> Reprise:
    _habilite(utilisateur, "parametrer", project_id)
    if not (nom or "").strip():
        _refuser("reprise.nom_obligatoire")
    if not Devise.objects.filter(code=devise).exists():
        _refuser("reprise.devise_inconnue", devise=devise)
    with transaction.atomic():
        reprise = Reprise.objects.create(
            org_id=utilisateur.org_id,
            project_id=project_id,
            nom=nom.strip(),
            date_bascule=date_bascule,
            devise=devise,
            cree_par=utilisateur.id,
            created_by=utilisateur.id,
        )
        journaliser(
            org_id=reprise.org_id,
            actor_id=utilisateur.id,
            action="migration_opened",
            object_type="reprise",
            object_id=reprise.id,
            project_id=project_id,
            after={"nom": reprise.nom, "date_bascule": date_bascule.isoformat()},
        )
    return reprise


def _exiger_modifiable(reprise: Reprise):
    # Le statut se relit : l'objet de l'appelant peut dater d'avant l'acceptation.
    statut = Reprise.objects.filter(pk=reprise.pk).values_list("statut", flat=True).first()
    if statut == StatutReprise.ACCEPTEE:
        raise ErreurMetier(CodeErreur.TRANSITION_INTERDITE, msg("reprise.deja_acceptee"))


# --- la balance d'origine --------------------------------------------------------------------


def importer_balance_origine(
    *, utilisateur, reprise: Reprise, contenu: bytes, nom_fichier: str, correspondance=None
) -> int:
    """Charge la balance du progiciel quitté (ÉQUILIBRÉE) et rend son nombre de lignes."""
    _habilite(utilisateur, "parametrer", reprise.project_id)
    _exiger_modifiable(reprise)
    empreinte = hashlib.sha256(contenu).digest()
    if reprise.balance_sha256 is not None:
        if bytes(reprise.balance_sha256) == empreinte:
            return reprise.balance.count()  # le même fichier rejoué : rien à faire
        raise ErreurMetier(CodeErreur.TRANSITION_INTERDITE, msg("reprise.balance_deja_chargee"))
    entetes, rangees = lire_fichier(contenu, nom_fichier)
    colonnes = _colonnes(entetes, BALANCE, correspondance)
    comptes = set(Compte.objects.values_list("code", flat=True))
    accords = set(
        Accord.objects.filter(project_id=reprise.project_id).values_list("numero", flat=True)
    )
    axes = set(ValeurDimension.objects.values_list("code", flat=True))
    erreurs, agregat = Erreurs(), defaultdict(lambda: [ZERO, ZERO])
    for i, r in enumerate(rangees, start=2):
        compte = r.get(colonnes["compte"], "").strip()
        accord = r.get(colonnes.get("accord", ""), "").strip()
        axe1 = r.get(colonnes.get("axe1", ""), "").strip()
        debit, credit = _decimal(r.get(colonnes["debit"])), _decimal(r.get(colonnes["credit"]))
        if compte not in comptes:
            erreurs.ajouter(i, "reprise.compte_inconnu", compte=compte)
        if debit is None or credit is None or debit < 0 or credit < 0:
            erreurs.ajouter(i, "reprise.montant_invalide")
            continue
        if accord and accord not in accords:
            erreurs.ajouter(i, "reprise.accord_inconnu", accord=accord)
        if axe1 and axe1 not in axes:
            erreurs.ajouter(i, "reprise.axe_inconnu", axe=axe1)
        cle = (compte, accord, axe1)
        agregat[cle][0] += debit
        agregat[cle][1] += credit
    if not rangees:
        _refuser("reprise.fichier_vide")
    total_debit = sum((d for d, _ in agregat.values()), ZERO)
    total_credit = sum((c for _, c in agregat.values()), ZERO)
    if total_debit != total_credit:
        erreurs.ajouter(1, "reprise.balance_desequilibree", ecart=total_debit - total_credit)
    erreurs.lever()
    with transaction.atomic():
        LigneBalanceOrigine.objects.bulk_create(
            LigneBalanceOrigine(
                org_id=reprise.org_id,
                reprise=reprise,
                compte=c,
                accord=a,
                axe1=x,
                debit=d,
                credit=cr,
                created_by=utilisateur.id,
            )  # fmt: skip
            for (c, a, x), (d, cr) in agregat.items()
        )
        Reprise.objects.filter(pk=reprise.pk).update(balance_sha256=empreinte)
        journaliser(
            org_id=reprise.org_id,
            actor_id=utilisateur.id,
            action="migration_balance_loaded",
            object_type="reprise",
            object_id=reprise.id,
            project_id=reprise.project_id,
            after={"lignes": len(agregat), "sha256": empreinte.hex(), "debit": str(total_debit)},
        )
    reprise.refresh_from_db()
    return len(agregat)


# --- les pièces : soldes d'ouverture et historique ------------------------------------------


@dataclass
class _PieceSource:
    cle: str
    journal: str
    date: datetime.date
    libelle: str
    lignes: list  # (compte, debit, credit, tiers, accord, axe1, libelle)


def _empreinte_piece(p: _PieceSource) -> bytes:
    canonique = json.dumps(
        [
            p.journal,
            p.date.isoformat(),
            [[c, str(d), str(cr), t, a, x] for c, d, cr, t, a, x, _ in p.lignes],
        ],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonique.encode()).digest()


@dataclass
class ResultatImport:
    creees: int = 0
    deja_presentes: int = 0


def _actualiser_statistiques() -> None:
    """Remet à jour les statistiques du planificateur pendant une reprise volumineuse.

    Sur une base neuve, les tables n'ont encore aucune statistique : les vérifications de clés
    étrangères choisissent alors des parcours séquentiels et le coût d'un lot croît avec le nombre
    de lots déjà écrits (mesuré : 50 000 écritures en plus de dix minutes sans cette remise à jour,
    linéaire avec). Seul le propriétaire d'une table peut l'analyser ; pour les autres rôles,
    PostgreSQL ignore la demande avec un avertissement, et l'autovacuum prend le relais.
    """
    with connection.cursor() as cur:
        cur.execute(
            "ANALYZE comptabilite_ecriture, comptabilite_ligneecriture, reprise_piecereprise"
        )


def _ecrire_pieces(utilisateur, reprise: Reprise, pieces: list[_PieceSource]) -> ResultatImport:
    """Crée les pièces absentes (par lots, comptabilisées) ; les présentes sont comptées."""
    resultat = ResultatImport()
    existantes = {
        p.cle: bytes(p.contenu_sha256) for p in PieceReprise.objects.filter(reprise=reprise)
    }
    journaux = {j.code: j for j in Journal.objects.all()}
    comptes = {c.code: c for c in Compte.objects.all()}
    tiers = {t.code: t for t in Tiers.objects.all()}
    axes = {v.code: v for v in ValeurDimension.objects.all()}
    accords = {a.numero: a.id for a in Accord.objects.filter(project_id=reprise.project_id)}
    periodes = list(Periode.objects.select_related("exercice").filter(
        exercice__project_id=reprise.project_id))  # fmt: skip
    a_creer = [p for p in pieces if p.cle not in existantes]
    resultat.deja_presentes = len(pieces) - len(a_creer)
    for debut in range(0, len(a_creer), TAILLE_LOT):
        lot = a_creer[debut : debut + TAILLE_LOT]
        ecritures, lignes, suivi = [], [], []
        for p in lot:
            periode = next(x for x in periodes if x.date_debut <= p.date <= x.date_fin)
            eid = uuid.uuid4()
            ecritures.append(
                Ecriture(
                    id=eid,
                    org_id=reprise.org_id,
                    project_id=reprise.project_id,
                    exercice=periode.exercice,
                    periode=periode,
                    journal=journaux[p.journal],
                    accounting_date=p.date,
                    label=(p.libelle or f"Reprise {p.journal}")[:255],
                    status="draft",
                    currency_id=reprise.devise,
                    origin="import",
                    origin_module="reprise",
                    origin_ref=reprise.id,
                    idempotency_key=f"reprise:{reprise.id}:{p.cle[:40]}",
                    created_by=utilisateur.id,
                )  # fmt: skip
            )
            for numero, (compte, debit, credit, t, a, x, lib) in enumerate(p.lignes, start=1):
                lignes.append(
                    LigneEcriture(
                        org_id=reprise.org_id,
                        project_id=reprise.project_id,
                        entry_id=eid,
                        line_no=numero,
                        account=comptes[compte],
                        partner=tiers.get(t),
                        dim1=axes.get(x),
                        agreement_id=accords.get(a),
                        debit=debit,
                        credit=credit,
                        currency_id=reprise.devise,
                        debit_cur=debit,
                        credit_cur=credit,
                        label=lib[:255],
                        created_by=utilisateur.id,
                    )  # fmt: skip
                )
            suivi.append(
                PieceReprise(
                    org_id=reprise.org_id,
                    reprise=reprise,
                    cle=p.cle,
                    contenu_sha256=_empreinte_piece(p),
                    ecriture_id=eid,
                    created_by=utilisateur.id,
                )  # fmt: skip
            )
        with transaction.atomic():
            Ecriture.objects.bulk_create(ecritures)
            LigneEcriture.objects.bulk_create(lignes)
            # Le numéro est attribué par la base au passage à « comptabilisée » (L3-T04).
            Ecriture.objects.filter(pk__in=[e.pk for e in ecritures]).update(
                status="posted", posted_at=timezone.now(), posted_by=utilisateur.id
            )
            PieceReprise.objects.bulk_create(suivi)
        resultat.creees += len(lot)
        _actualiser_statistiques()
    return resultat


def _verifier_references(reprise: Reprise, pieces: list[_PieceSource]) -> None:
    """Tout ou rien : les références, les périodes ouvertes, l'équilibre de chaque pièce."""
    comptes = {c.code: c for c in Compte.objects.all()}
    journaux = set(Journal.objects.values_list("code", flat=True))
    tiers = set(Tiers.objects.values_list("code", flat=True))
    axes = set(ValeurDimension.objects.values_list("code", flat=True))
    accords = set(
        Accord.objects.filter(project_id=reprise.project_id).values_list("numero", flat=True)
    )
    periodes = list(Periode.objects.filter(exercice__project_id=reprise.project_id))
    erreurs = Erreurs()
    for p in pieces:
        if p.journal not in journaux:
            erreurs.ajouter(
                p.lignes[0][-1] and 0 or 0, "reprise.journal_inconnu", journal=p.journal
            )
        if p.date > reprise.date_bascule:
            erreurs.ajouter(0, "reprise.apres_la_bascule", piece=p.cle[:8], date=p.date.isoformat())
        periode = next((x for x in periodes if x.date_debut <= p.date <= x.date_fin), None)
        if periode is None:
            erreurs.ajouter(0, "reprise.aucune_periode", date=p.date.isoformat())
        elif periode.status != "ouverte":
            erreurs.ajouter(0, "reprise.periode_non_ouverte", date=p.date.isoformat())
        debit = sum((ligne[1] for ligne in p.lignes), ZERO)
        credit = sum((ligne[2] for ligne in p.lignes), ZERO)
        if debit != credit:
            erreurs.ajouter(
                0,
                "reprise.piece_desequilibree",
                piece=f"{p.journal}/{p.libelle}",
                ecart=debit - credit,
            )
        for compte, d, c, t, a, x, _ in p.lignes:
            if compte not in comptes:
                erreurs.ajouter(0, "reprise.compte_inconnu", compte=compte)
            elif not comptes[compte].imputable:
                erreurs.ajouter(0, "reprise.compte_non_imputable", compte=compte)
            if t and t not in tiers:
                erreurs.ajouter(0, "reprise.tiers_inconnu", tiers=t)
            if a and a not in accords:
                erreurs.ajouter(0, "reprise.accord_inconnu", accord=a)
            if x and x not in axes:
                erreurs.ajouter(0, "reprise.axe_inconnu", axe=x)
            if d and c:
                erreurs.ajouter(0, "reprise.deux_sens", compte=compte)
    erreurs.lever()


def importer_historique(
    *, utilisateur, reprise: Reprise, contenu: bytes, nom_fichier: str, correspondance=None
) -> ResultatImport:
    """Importe les écritures antérieures à la bascule, avec leurs imputations. Idempotent."""
    _habilite(utilisateur, "parametrer", reprise.project_id)
    _exiger_modifiable(reprise)
    if reprise.mode == ModeReprise.OUVERTURE:
        raise ErreurMetier(CodeErreur.TRANSITION_INTERDITE, msg("reprise.mode_ouverture"))
    entetes, rangees = lire_fichier(contenu, nom_fichier)
    colonnes = _colonnes(entetes, HISTORIQUE, correspondance)
    if not rangees:
        _refuser("reprise.fichier_vide")
    groupes: dict[tuple, list] = defaultdict(list)
    erreurs = Erreurs()
    for i, r in enumerate(rangees, start=2):
        journal = r.get(colonnes["journal"], "").strip() or JOURNAL_PAR_DEFAUT
        piece = r.get(colonnes["piece"], "").strip()
        jour = _date(r.get(colonnes["date"], ""))
        debit, credit = _decimal(r.get(colonnes["debit"])), _decimal(r.get(colonnes["credit"]))
        if not piece or jour is None:
            erreurs.ajouter(i, "reprise.piece_ou_date_invalide")
            continue
        if debit is None or credit is None or debit < 0 or credit < 0:
            erreurs.ajouter(i, "reprise.montant_invalide")
            continue
        groupes[(journal, piece, jour)].append(
            (
                r.get(colonnes["compte"], "").strip(), debit, credit,
                r.get(colonnes.get("tiers", ""), "").strip(),
                r.get(colonnes.get("accord", ""), "").strip(),
                r.get(colonnes.get("axe1", ""), "").strip(),
                r.get(colonnes.get("libelle", ""), "").strip(),
            )
        )  # fmt: skip
    erreurs.lever()
    pieces = [
        _PieceSource(
            cle=hashlib.sha256(f"{j}|{n}|{d.isoformat()}".encode()).hexdigest(),
            journal=j,
            date=d,
            libelle=lignes[0][-1] or f"{j} {n}",
            lignes=lignes,
        )  # fmt: skip
        for (j, n, d), lignes in groupes.items()
    ]
    return _importer_pieces(
        utilisateur, reprise, pieces, ModeReprise.HISTORIQUE, "migration_history_loaded"
    )


def _importer_pieces(utilisateur, reprise, pieces, mode, action) -> ResultatImport:
    with transaction.atomic():
        courante = Reprise.objects.select_for_update().get(pk=reprise.pk)
        if courante.mode not in (None, mode):
            raise ErreurMetier(CodeErreur.TRANSITION_INTERDITE, msg("reprise.mode_different"))
        existantes = {
            p.cle: bytes(p.contenu_sha256) for p in PieceReprise.objects.filter(reprise=courante)
        }
        conflits = [
            p for p in pieces if p.cle in existantes and existantes[p.cle] != _empreinte_piece(p)
        ]
        if conflits:
            raise ErreurMetier(
                CodeErreur.REGLE_INVALIDE,
                msg(
                    "reprise.conflit_de_piece",
                    n=len(conflits),
                    v1=[p.cle[:8] for p in conflits[:10]],
                ),
            )
        Journal.objects.get_or_create(
            org_id=courante.org_id,
            code=JOURNAL_PAR_DEFAUT,
            defaults={"label": {"fr": "Reprise de données", "en": "Data migration"}},
        )
        _verifier_references(courante, [p for p in pieces if p.cle not in existantes])
        resultat = _ecrire_pieces(utilisateur, courante, pieces)
        if courante.mode is None:
            Reprise.objects.filter(pk=courante.pk).update(mode=mode)
        journaliser(
            org_id=courante.org_id,
            actor_id=utilisateur.id,
            action=action,
            object_type="reprise",
            object_id=courante.id,
            project_id=courante.project_id,
            after={"creees": resultat.creees, "deja_presentes": resultat.deja_presentes},
        )
    reprise.refresh_from_db()
    return resultat


def generer_soldes_ouverture(*, utilisateur, reprise: Reprise, journal: str = JOURNAL_PAR_DEFAUT):
    """Crée l'écriture d'ouverture à la date de bascule, depuis la balance d'origine. Idempotent."""
    _habilite(utilisateur, "parametrer", reprise.project_id)
    _exiger_modifiable(reprise)
    if reprise.mode == ModeReprise.HISTORIQUE:
        raise ErreurMetier(CodeErreur.TRANSITION_INTERDITE, msg("reprise.mode_historique"))
    lignes = []
    for b in reprise.balance.order_by("compte", "accord", "axe1"):
        net = b.debit - b.credit
        if net == 0:
            continue
        lignes.append(
            (b.compte, max(net, ZERO), max(-net, ZERO), "", b.accord, b.axe1, "Solde d'ouverture")
        )
    if not lignes:
        _refuser("reprise.balance_absente")
    piece = _PieceSource(
        cle=hashlib.sha256(f"ouverture|{reprise.id}".encode()).hexdigest(), journal=journal,
        date=reprise.date_bascule, libelle="Soldes d'ouverture", lignes=lignes,
    )  # fmt: skip
    return _importer_pieces(
        utilisateur, reprise, [piece], ModeReprise.OUVERTURE, "migration_opening_loaded"
    )


# --- le contrôle et la signature ------------------------------------------------------------


def _ecarts(dimension: str, origine: dict, reprise_: dict) -> list[dict]:
    sortie = []
    for cle in sorted(set(origine) | set(reprise_)):
        o, r = origine.get(cle, ZERO), reprise_.get(cle, ZERO)
        if o != r:
            sortie.append(
                {
                    "dimension": dimension,
                    "cle": cle,
                    "origine": str(o),
                    "reprise": str(r),
                    "ecart": str(r - o),
                }
            )
    return sortie


def controler_reprise(*, utilisateur, reprise: Reprise) -> RapportReprise:
    """Rapproche la balance d'origine et la balance reprise : par compte, par accord, par axe."""
    _habilite(utilisateur, "parametrer", reprise.project_id)
    _exiger_modifiable(reprise)
    if reprise.balance_sha256 is None:
        _refuser("reprise.balance_absente")
    if reprise.mode is None:
        _refuser("reprise.aucune_ecriture")
    origine = {
        "compte": defaultdict(Decimal),
        "accord": defaultdict(Decimal),
        "axe1": defaultdict(Decimal),
    }
    for b in reprise.balance.all():
        net = b.debit - b.credit
        origine["compte"][b.compte] += net
        origine["accord"][b.accord] += net
        origine["axe1"][b.axe1] += net
    numeros = {str(a.id): a.numero for a in Accord.objects.filter(project_id=reprise.project_id)}
    repris = {
        "compte": defaultdict(Decimal),
        "accord": defaultdict(Decimal),
        "axe1": defaultdict(Decimal),
    }
    lignes = LigneEcriture.objects.filter(
        entry__origin_ref=reprise.id, entry__status__in=["posted", "locked"]
    ).select_related("account", "dim1")
    for ligne in lignes.iterator(chunk_size=5000):
        net = ligne.debit - ligne.credit
        repris["compte"][ligne.account.code] += net
        repris["accord"][
            numeros.get(str(ligne.agreement_id), "") if ligne.agreement_id else ""
        ] += net
        repris["axe1"][ligne.dim1.code if ligne.dim1_id else ""] += net
    nombre = Ecriture.objects.filter(origin_ref=reprise.id, status__in=["posted", "locked"]).count()
    ecarts = []
    for dimension in ("compte", "accord", "axe1"):
        ecarts += _ecarts(dimension, origine[dimension], repris[dimension])
    ecart_general = sum(
        (abs(Decimal(e["ecart"])) for e in ecarts if e["dimension"] == "compte"), ZERO
    )
    ecart_accords = sum(
        (abs(Decimal(e["ecart"])) for e in ecarts if e["dimension"] == "accord"), ZERO
    )
    accepte = ecart_general == 0 and ecart_accords == 0
    contenu = json.dumps(
        {"reprise": str(reprise.id), "date_bascule": reprise.date_bascule.isoformat(),
         "ecritures": nombre, "ecarts": ecarts, "accepte": accepte},
        sort_keys=True, separators=(",", ":"),
    )  # fmt: skip
    with transaction.atomic():
        rapport = RapportReprise.objects.create(
            org_id=reprise.org_id, reprise=reprise, accepte=accepte, ecart_general=ecart_general,
            ecart_accords=ecart_accords, nombre_ecritures=nombre, ecarts=ecarts,
            contenu_sha256=hashlib.sha256(contenu.encode()).digest(), created_by=utilisateur.id,
        )  # fmt: skip
        Reprise.objects.filter(pk=reprise.pk).update(
            statut=StatutReprise.CONTROLEE if accepte else StatutReprise.REFUSEE
        )
        journaliser(
            org_id=reprise.org_id,
            actor_id=utilisateur.id,
            action="migration_checked",
            object_type="reprise",
            object_id=reprise.id,
            project_id=reprise.project_id,
            after={
                "accepte": accepte,
                "ecart_general": str(ecart_general),
                "ecart_accords": str(ecart_accords),
                "ecarts": len(ecarts),
            },
        )
    reprise.refresh_from_db()
    return rapport


def signer_rapport(*, utilisateur, rapport: RapportReprise) -> RapportReprise:
    """Signature nominative d'un rapport à écart nul : accepte la reprise. Jamais par celui qui l'a
    ouverte, et jamais sur un rapport à écart non nul."""
    reprise = rapport.reprise
    _habilite(utilisateur, "valider", reprise.project_id)
    with transaction.atomic():
        courant = RapportReprise.objects.select_for_update().get(pk=rapport.pk)
        if utilisateur.id == reprise.cree_par:
            raise ErreurMetier(CodeErreur.APPROBATION_REQUISE, msg("reprise.signataire_distinct"))
        if not courant.accepte:
            raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("reprise.ecart_non_nul"))
        if courant.signe_par is not None:
            raise ErreurMetier(CodeErreur.TRANSITION_INTERDITE, msg("reprise.deja_signe"))
        dernier = (
            RapportReprise.objects.filter(reprise=reprise).order_by("-created_at", "-id").first()
        )
        if dernier.pk != courant.pk:
            raise ErreurMetier(CodeErreur.REGLE_INVALIDE, msg("reprise.rapport_depasse"))
        courant.signe_par = utilisateur.id
        courant.signe_nom = utilisateur.get_username()
        courant.signe_le = timezone.now()
        courant.save(update_fields=["signe_par", "signe_nom", "signe_le", "updated_at"])
        Reprise.objects.filter(pk=reprise.pk).update(statut=StatutReprise.ACCEPTEE)
        journaliser(
            org_id=reprise.org_id,
            actor_id=utilisateur.id,
            action="migration_accepted",
            object_type="reprise",
            object_id=reprise.id,
            project_id=reprise.project_id,
            after={"rapport": str(courant.id), "sha256": bytes(courant.contenu_sha256).hex()},
        )
    rapport.refresh_from_db()
    return rapport


def reprise_acceptee(project_id) -> bool:
    """La mise en service est permise : une reprise du projet est acceptée et signée."""
    return Reprise.objects.filter(project_id=project_id, statut=StatutReprise.ACCEPTEE).exists()
