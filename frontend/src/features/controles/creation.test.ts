import { construireControle, controleVide, operateursDuChamp, saisieDe } from "./creation";
import type { SaisieControle } from "./creation";
import type { Langage } from "./types";

const LANGAGE: Langage = {
  types_regle: {
    budget: { montant: { type: "decimal" }, plafond_accord: { type: "decimal" } },
    pieces: { methode: { type: "texte" }, date: { type: "date" }, pieces: { type: "liste", elements: { type: "texte", valide: "booleen", montant: "decimal" } } },
    risque: { rejets_categorie: { type: "entier" } },
  },
  operateurs: {
    eq: { types: ["decimal", "entier", "date", "texte"], sans_valeur: false },
    gt: { types: ["decimal", "entier"], sans_valeur: false },
    in: { types: ["decimal", "entier", "date", "texte"], sans_valeur: false },
    entre: { types: ["date"], sans_valeur: false },
    est_renseigne: { types: ["decimal", "entier", "date", "texte", "booleen", "liste"], sans_valeur: true },
    somme_lte: { types: ["liste"], sans_valeur: false },
    nombre_eq: { types: ["liste"], sans_valeur: false },
  },
  severites: ["bloquant", "avertissement", "information"],
  max_conditions: 3,
};

const base = (extra: Partial<SaisieControle> = {}): SaisieControle => ({
  ...controleVide(),
  code: "BUD-MONTANT",
  fr: "Montant plafonné",
  type_regle: "budget",
  valid_from: "2026-01-01",
  conditions: [{ champ: "montant", op: "gt", valeur: "1 250,50", valeur2: "", somme_de: "" }],
  ...extra,
});

describe("le langage proposé par le serveur", () => {
  it("ne propose, pour un champ, que les opérateurs compatibles avec son type", () => {
    expect(operateursDuChamp(LANGAGE, LANGAGE.types_regle.budget!.montant)).toEqual(["eq", "gt", "in", "est_renseigne"]);
    expect(operateursDuChamp(LANGAGE, LANGAGE.types_regle.pieces!.date)).toEqual(["eq", "in", "entre", "est_renseigne"]);
    expect(operateursDuChamp(LANGAGE, undefined)).toEqual([]);
  });
  it("dit ce que l'écran doit demander pour chaque opérateur", () => {
    expect(saisieDe("est_renseigne", "texte", LANGAGE)).toBe("aucune");
    expect(saisieDe("in", "texte", LANGAGE)).toBe("liste");
    expect(saisieDe("entre", "date", LANGAGE)).toBe("deux_dates");
    expect(saisieDe("somme_lte", "liste", LANGAGE)).toBe("somme");
    expect(saisieDe("nombre_eq", "liste", LANGAGE)).toBe("entier");
    expect(saisieDe("gt", "decimal", LANGAGE)).toBe("valeur");
  });
});

describe("construction d'un contrôle", () => {
  it("un montant part en chaîne canonique, jamais en nombre", () => {
    const r = construireControle(base(), LANGAGE, "fr");
    expect(r).toEqual({
      ok: true,
      corps: {
        code: "BUD-MONTANT",
        label: { fr: "Montant plafonné" },
        type_regle: "budget",
        severity: "avertissement",
        valid_from: "2026-01-01",
        expression: { type_regle: "budget", conditions: [{ champ: "montant", op: "gt", valeur: "1250.50" }] },
      },
    });
  });

  it("un entier part en entier, une condition sans valeur n'en porte pas", () => {
    const r = construireControle(
      base({ type_regle: "risque", conditions: [{ champ: "rejets_categorie", op: "eq", valeur: "3", valeur2: "", somme_de: "" }, { champ: "rejets_categorie", op: "est_renseigne", valeur: "ignoree", valeur2: "", somme_de: "" }] }),
      LANGAGE,
      "fr",
    );
    expect(r.ok && (r.corps.expression as { conditions: unknown[] }).conditions).toEqual([{ champ: "rejets_categorie", op: "eq", valeur: 3 }, { champ: "rejets_categorie", op: "est_renseigne" }]);
  });

  it("une liste de valeurs se sépare par des points-virgules", () => {
    const r = construireControle(base({ type_regle: "pieces", conditions: [{ champ: "methode", op: "in", valeur: "advance; reimbursement ", valeur2: "", somme_de: "" }] }), LANGAGE, "fr");
    expect(r.ok && (r.corps.expression as { conditions: unknown[] }).conditions).toEqual([{ champ: "methode", op: "in", valeur: ["advance", "reimbursement"] }]);
  });

  it("« entre » exige deux dates dans l'ordre", () => {
    const sain = construireControle(base({ type_regle: "pieces", conditions: [{ champ: "date", op: "entre", valeur: "2026-01-01", valeur2: "2026-12-31", somme_de: "" }] }), LANGAGE, "fr");
    expect(sain.ok && (sain.corps.expression as { conditions: unknown[] }).conditions).toEqual([{ champ: "date", op: "entre", valeur: ["2026-01-01", "2026-12-31"] }]);
    const envers = construireControle(base({ type_regle: "pieces", conditions: [{ champ: "date", op: "entre", valeur: "2026-12-31", valeur2: "2026-01-01", somme_de: "" }] }), LANGAGE, "fr");
    expect(!envers.ok && envers.fautes[0]?.cle).toBe("controles.faute.intervalle");
  });

  it("« somme ≤ » désigne un champ numérique des éléments", () => {
    const ok = construireControle(base({ type_regle: "pieces", conditions: [{ champ: "pieces", op: "somme_lte", valeur: "10", valeur2: "", somme_de: "montant" }] }), LANGAGE, "fr");
    expect(ok.ok && (ok.corps.expression as { conditions: unknown[] }).conditions).toEqual([{ champ: "pieces", op: "somme_lte", valeur: "10", somme_de: "montant" }]);
    const mauvais = construireControle(base({ type_regle: "pieces", conditions: [{ champ: "pieces", op: "somme_lte", valeur: "10", valeur2: "", somme_de: "valide" }] }), LANGAGE, "fr");
    expect(!mauvais.ok && mauvais.fautes[0]?.cle).toBe("controles.faute.somme_de");
  });

  it("refuse un opérateur incompatible avec le champ, un champ inconnu, une valeur illisible", () => {
    const incompatible = construireControle(base({ conditions: [{ champ: "montant", op: "entre", valeur: "", valeur2: "", somme_de: "" }] }), LANGAGE, "fr");
    expect(!incompatible.ok && incompatible.fautes[0]).toEqual({ cle: "controles.faute.operateur", params: { n: "1" } });
    const inconnu = construireControle(base({ conditions: [{ champ: "zzz", op: "gt", valeur: "1", valeur2: "", somme_de: "" }] }), LANGAGE, "fr");
    expect(!inconnu.ok && inconnu.fautes[0]?.cle).toBe("controles.faute.champ");
    for (const mauvais of ["abc", "1.250", ""]) {
      const r = construireControle(base({ conditions: [{ champ: "montant", op: "gt", valeur: mauvais, valeur2: "", somme_de: "" }] }), LANGAGE, "fr");
      expect(!r.ok && r.fautes[0]?.cle).toBe("controles.faute.valeur");
    }
  });

  it("refuse un formulaire vide en listant ce qui manque", () => {
    const r = construireControle(controleVide(), LANGAGE, "fr");
    expect(!r.ok && r.fautes.map((f) => f.cle)).toEqual(["controles.faute.code", "controles.faute.libelle", "controles.faute.type_regle", "controles.faute.date_effet"]);
  });

  it("limite le nombre de conditions à celui du serveur", () => {
    const c = { champ: "montant", op: "gt", valeur: "1", valeur2: "", somme_de: "" };
    const r = construireControle(base({ conditions: [c, c, c, c] }), LANGAGE, "fr");
    expect(!r.ok && r.fautes[0]).toEqual({ cle: "controles.faute.trop_de_conditions", params: { max: "3" } });
  });

  it("un contrôle à vérifier à la main n'envoie aucune expression", () => {
    const r = construireControle(base({ manuel: true, conditions: [] }), LANGAGE, "fr");
    expect(r.ok && r.corps.manuel).toBe(true);
    expect(r.ok && "expression" in r.corps).toBe(false);
  });

  it("les libellés et l'action corrective ne gardent que les langues renseignées", () => {
    const r = construireControle(base({ en: "Capped amount", action_fr: "Réduire le montant" }), LANGAGE, "fr");
    expect(r.ok && r.corps.label).toEqual({ fr: "Montant plafonné", en: "Capped amount" });
    expect(r.ok && r.corps.action_corrective).toEqual({ fr: "Réduire le montant" });
  });
});
