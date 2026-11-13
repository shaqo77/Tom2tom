"""Lettrage et dé-lettrage. Voir L3-T07 (partie a).

Lettrer, c'est marquer un groupe de lignes COMPTABILISÉES dont le solde est nul, sur un même
compte, un même tiers et un même projet. Les lignes ne sont pas modifiées : seul leur marqueur
`reconciliation_id` change, et elles restent immuables. La base vérifie le groupe au COMMIT ;
ce module anticipe pour rendre l'erreur lisible, et garde la trace de chaque opération.
"""

from decimal import Decimal

from django.db import connection, transaction
from django.utils import timezone

from core.audit import journaliser

from .models import Lettrage, LigneEcriture
from .services import _exiger_habilitation

ZERO = Decimal(0)


class LettrageImpossible(ValueError):
    """Le groupe de lignes ne peut pas être lettré ; `raisons` les liste toutes."""

    def __init__(self, raisons: list[str]):
        self.raisons = raisons
        super().__init__(" ; ".join(raisons))


def _code(rang: int) -> str:
    """AA, AB… AZ, BA… ZZ, puis AAA… : 0 -> AA, 1 -> AB, 26 -> BA."""
    longueur = 2
    while rang >= 26**longueur:
        rang -= 26**longueur
        longueur += 1
    lettres = []
    for _ in range(longueur):
        rang, reste = divmod(rang, 26)
        lettres.append(chr(65 + reste))
    return "".join(reversed(lettres))


def _problemes(lignes: list[LigneEcriture], attendues: int) -> list[str]:
    raisons = []
    if len(lignes) != attendues:
        raisons.append("Une ligne au moins est introuvable")
    if len(lignes) < 2:
        raisons.append("Un lettrage compte au moins deux lignes")
    if len({ligne.account_id for ligne in lignes}) > 1:
        raisons.append("Les lignes doivent porter sur le même compte")
    if any(ligne.partner_id is None for ligne in lignes):
        raisons.append("Chaque ligne d'un lettrage doit porter un tiers")
    elif len({ligne.partner_id for ligne in lignes}) > 1:
        raisons.append("Les lignes doivent concerner le même tiers")
    if len({ligne.project_id for ligne in lignes}) > 1:
        raisons.append("Les lignes doivent appartenir au même projet")
    for ligne in lignes:
        if ligne.reconciliation_id is not None:
            raisons.append(f"La ligne {ligne.entry.number} / {ligne.line_no} est déjà lettrée")
        if ligne.entry.status not in ("posted", "locked"):
            raisons.append("On ne lettre que des lignes comptabilisées")
            break
    solde = sum((ligne.debit - ligne.credit for ligne in lignes), ZERO)
    if solde != 0:
        raisons.append(f"Le groupe n'est pas soldé : écart de {solde}")
    if len({ligne.currency_id for ligne in lignes}) == 1:
        solde_devise = sum((ligne.debit_cur - ligne.credit_cur for ligne in lignes), ZERO)
        if solde_devise != 0:
            raisons.append(f"Le groupe n'est pas soldé en devise : écart de {solde_devise}")
    return raisons


def lettrer(lignes, *, utilisateur) -> Lettrage:
    """Lettre un groupe de lignes. Retourne le lettrage créé."""
    ids = list({getattr(ligne, "pk", ligne) for ligne in lignes})
    with transaction.atomic():
        # Verrou de ligne : deux lettrages simultanés des mêmes lignes ne passent pas ensemble.
        courantes = list(
            LigneEcriture.objects.select_for_update(of=("self",))
            .select_related("entry", "account", "partner")
            .filter(pk__in=ids)
            .order_by("pk")
        )
        for projet in {ligne.project_id for ligne in courantes}:
            _exiger_habilitation(utilisateur, "comptabiliser", projet)
        raisons = _problemes(courantes, len(ids))
        if raisons:
            raise LettrageImpossible(raisons)

        modele = courantes[0]
        with connection.cursor() as cur:  # le code se déduit d'un décompte : on sérialise
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                [f"lettrage:{modele.org_id}:{modele.account_id}"],
            )
        rang = Lettrage.objects.filter(account_id=modele.account_id).count()
        lettrage = Lettrage.objects.create(
            org_id=modele.org_id,
            code=_code(rang),
            account=modele.account,
            partner=modele.partner,
            project_id=modele.project_id,
            lettre_by=utilisateur.id,
            created_by=utilisateur.id,
        )
        # `update` sur un queryset : la ligne n'est pas « réécrite » (updated_at inchangé).
        LigneEcriture.objects.filter(pk__in=ids).update(reconciliation_id=lettrage.pk)
        journaliser(
            org_id=lettrage.org_id,
            actor_id=utilisateur.id,
            action="lettering_created",
            object_type="lettrage",
            object_id=lettrage.id,
            project_id=lettrage.project_id,
            after={"code": lettrage.code, "lignes": sorted(str(i) for i in ids)},
        )
    return lettrage


def delettrer(lettrage: Lettrage, *, utilisateur, motif: str) -> Lettrage:
    """Annule un lettrage et libère ses lignes, qui reviennent à leur état initial."""
    if not (motif or "").strip():
        raise LettrageImpossible(["Le dé-lettrage exige un motif"])
    with transaction.atomic():
        courant = Lettrage.objects.select_for_update().get(pk=lettrage.pk)
        _exiger_habilitation(utilisateur, "comptabiliser", courant.project_id)
        if courant.status != "actif":
            raise LettrageImpossible([f"Le lettrage {courant.code} est déjà annulé"])
        ids = list(
            LigneEcriture.objects.filter(reconciliation_id=courant.pk).values_list("pk", flat=True)
        )
        LigneEcriture.objects.filter(reconciliation_id=courant.pk).update(reconciliation_id=None)
        Lettrage.objects.filter(pk=courant.pk).update(
            status="annule",
            annule_at=timezone.now(),
            annule_by=utilisateur.id,
            motif_annulation=motif.strip(),
        )
        journaliser(
            org_id=courant.org_id,
            actor_id=utilisateur.id,
            action="lettering_cancelled",
            object_type="lettrage",
            object_id=courant.id,
            project_id=courant.project_id,
            before={"status": "actif", "code": courant.code},
            after={
                "status": "annule",
                "motif": motif.strip(),
                "lignes": sorted(str(i) for i in ids),
            },
        )
    lettrage.refresh_from_db()
    return lettrage
