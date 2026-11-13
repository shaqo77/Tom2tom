"""Comparer deux versions d'un profil : identiques, modifiés, ajoutés, supprimés. Voir L5-T04bis.

La même mécanique servira à la régénération par différentiel (L6-T04) : on indexe chaque famille
par sa clé naturelle (méthode, code de catégorie, compte) et on compare champ à champ.
"""

from dataclasses import dataclass, field

from ..models import ProfilDecaissement

CHAMPS_PROFIL = (
    "regime",
    "valid_from",
    "valid_to",
    "effectiveness_date",
    "eligibility_date",
    "closing_date",
    "disbursement_deadline",
    "requirement_id",
)
IGNORES = {
    "id", "org_id", "profil", "created_at", "created_by", "updated_at", "updated_by",
    "category", "bank_account", "method",
}  # fmt: skip


@dataclass
class Famille:
    identiques: list = field(default_factory=list)
    modifies: list = field(default_factory=list)  # (clé, {champ: (avant, après)})
    ajoutes: list = field(default_factory=list)
    supprimes: list = field(default_factory=list)

    @property
    def inchangee(self) -> bool:
        return not (self.modifies or self.ajoutes or self.supprimes)


@dataclass
class Comparaison:
    parametres: Famille
    methodes: Famille
    categories: Famille  # allocations et taux, par code de catégorie
    comptes: Famille

    @property
    def identiques(self) -> bool:
        return all(
            f.inchangee for f in (self.parametres, self.methodes, self.categories, self.comptes)
        )


def _valeurs(objet) -> dict:
    return {
        f.attname: getattr(objet, f.attname)
        for f in objet._meta.concrete_fields
        if f.name not in IGNORES
    }


def _comparer(avant: dict, apres: dict) -> Famille:
    famille = Famille()
    for cle in sorted(avant.keys() | apres.keys(), key=str):
        if cle not in apres:
            famille.supprimes.append(cle)
        elif cle not in avant:
            famille.ajoutes.append(cle)
        else:
            ecarts = {
                champ: (avant[cle][champ], apres[cle][champ])
                for champ in avant[cle]
                if avant[cle][champ] != apres[cle][champ]
            }
            if ecarts:
                famille.modifies.append((cle, ecarts))
            else:
                famille.identiques.append(cle)
    return famille


def comparer_versions(a: ProfilDecaissement, b: ProfilDecaissement) -> Comparaison:
    if a.accord_id != b.accord_id:
        raise ValueError("On ne compare que deux versions d'un même accord")
    parametres = _comparer(
        {"profil": {c: getattr(a, c) for c in CHAMPS_PROFIL}},
        {"profil": {c: getattr(b, c) for c in CHAMPS_PROFIL}},
    )
    return Comparaison(
        parametres=parametres,
        methodes=_comparer(
            {m.method: _valeurs(m) for m in a.methodes.all()},
            {m.method: _valeurs(m) for m in b.methodes.all()},
        ),
        categories=_comparer(
            {r.category.code: _valeurs(r) for r in a.regles.select_related("category")},
            {r.category.code: _valeurs(r) for r in b.regles.select_related("category")},
        ),
        comptes=_comparer(
            {c.bank_account_id: _valeurs(c) for c in a.comptes.all()},
            {c.bank_account_id: _valeurs(c) for c in b.comptes.all()},
        ),
    )
