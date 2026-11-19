"""Le contrôle de complétude d'un profil avant soumission. Voir L5-T04bis.

`verifier_completude(profil)` rend des ERREURS BLOQUANTES (la validation est refusée, chaque manque
nommé) et des AVERTISSEMENTS (tracés, avec la justification de qui valide, jamais bloquants).

Ce que la base garantit déjà n'est pas recontrôlé ici : un profil a toujours un accord (donc un
bailleur et une devise de référence), ses jalons sont dans l'ordre, ses ensembles sont fermés.

Un écart entre le budget et les financements contractualisés n'est PAS une anomalie : le budget du
projet n'est pas présumé entièrement financé par les bailleurs.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from core.i18n import Message, libelle_valeur, msg
from niveau1_socle.financements.services import montant_courant

from ..models import MethodeDecaissementCode, ProfilDecaissement, StatutExigence, StatutProfil


@dataclass(frozen=True)
class Anomalie:
    code: str
    message: Message


@dataclass
class Completude:
    bloquantes: list[Anomalie] = field(default_factory=list)
    avertissements: list[Anomalie] = field(default_factory=list)

    @property
    def complet(self) -> bool:
        return not self.bloquantes

    def codes(self) -> set[str]:
        return {a.code for a in self.bloquantes} | {a.code for a in self.avertissements}


def verifier_completude(profil: ProfilDecaissement) -> Completude:
    resultat = Completude()
    bloque, avertit = resultat.bloquantes.append, resultat.avertissements.append

    if profil.valid_to is not None and profil.valid_to <= profil.valid_from:
        bloque(Anomalie("dates_incoherentes", msg("completude.fin_validite_avant_debut")))
    jalons = [
        ("effectiveness_date", "eligibility_date"),
        ("eligibility_date", "closing_date"),
        ("closing_date", "disbursement_deadline"),
    ]
    for avant, apres in jalons:
        a, b = getattr(profil, avant), getattr(profil, apres)
        if a is not None and b is not None and a > b:
            bloque(
                Anomalie(
                    "dates_incoherentes",
                    msg("completude.jalons_desordre", avant=avant, a=a, apres=apres, b=b),
                )
            )

    methodes = list(profil.methodes.all())
    regles = list(profil.regles.all())
    if not methodes:
        bloque(Anomalie("aucune_methode", msg("completude.aucune_methode")))
    for methode in methodes:
        if methode.is_enabled and not methode.supporting_docs:
            bloque(
                Anomalie(
                    "methode_sans_pieces",
                    msg(
                        "completude.methode_sans_pieces",
                        methode=libelle_valeur(MethodeDecaissementCode, methode.method),
                    ),
                )
            )
    if not regles:
        bloque(Anomalie("aucune_categorie", msg("completude.aucune_categorie")))
    else:
        total = sum((r.allocation for r in regles), Decimal(0))
        plafond = montant_courant(profil.accord, profil.valid_from)
        if total > plafond:
            bloque(
                Anomalie(
                    "allocations_excessives",
                    msg("completude.allocations_excessives", total=total, plafond=plafond),
                )
            )
        for regle in regles:
            if regle.funding_rate == 1:
                avertit(
                    Anomalie(
                        "taux_integral",
                        msg("completude.taux_integral", code=regle.category.code),
                    )
                )

    exigence = profil.requirement
    if exigence is None:
        avertit(Anomalie("sans_exigence_source", msg("completude.sans_exigence_source")))
    elif exigence.status not in (StatutExigence.VALIDEE, StatutExigence.ACTIVE):
        bloque(
            Anomalie(
                "exigence_non_validee",
                msg(
                    "completude.exigence_non_validee",
                    code=exigence.code,
                    version=exigence.version,
                    status=exigence.status,
                ),
            )
        )

    for autre in ProfilDecaissement.objects.filter(
        accord_id=profil.accord_id, status=StatutProfil.ACTIF
    ).exclude(pk=profil.pk):
        if autre.valid_from >= profil.valid_from or (
            autre.valid_to is not None and autre.valid_to > profil.valid_from
        ):
            if autre.valid_to:
                message = msg(
                    "completude.chevauchement_avec_fin",
                    version=autre.version,
                    debut=autre.valid_from,
                    fin=autre.valid_to,
                )
            else:
                message = msg(
                    "completude.chevauchement_sans_fin",
                    version=autre.version,
                    debut=autre.valid_from,
                )
            bloque(Anomalie("chevauchement", message))

    if profil.eligibility_date is None:
        avertit(Anomalie("sans_date_eligibilite", msg("completude.sans_date_eligibilite")))
    if not list(profil.comptes.all()):
        avertit(Anomalie("sans_compte_designe", msg("completude.sans_compte_designe")))
    return resultat
