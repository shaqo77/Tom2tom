import { construireEcriture, ecritureVide, totaux } from "./saisie";
import type { SaisieEcriture } from "./saisie";

const valide = (): SaisieEcriture => ({
  journal: "OD",
  date: "2026-03-10",
  libelle: "Charge commune",
  reference: "",
  lignes: [
    { compte: "6011", debit: "1 001,50", credit: "", label: "", cle: "CHARGES", accord: "" },
    { compte: "5211", debit: "", credit: "1 001,50", label: "", cle: "", accord: "" },
  ],
});

describe("saisie d'une écriture", () => {
  it("construit le corps : montants en chaînes canoniques, clé sur la ligne, aucun nombre", () => {
    const r = construireEcriture(valide(), "fr");
    expect(r).toEqual({
      ok: true,
      corps: {
        journal: "OD",
        date_comptable: "2026-03-10",
        libelle: "Charge commune",
        lignes: [
          { compte: "6011", debit: "1001.50", cle: "CHARGES" },
          { compte: "5211", credit: "1001.50" },
        ],
      },
    });
  });

  it("le total n'est jamais un flottant : 0,1 + 0,2 = 0,3 exactement", () => {
    const s = valide();
    s.lignes = [
      { ...s.lignes[0]!, debit: "0,1", cle: "" },
      { ...s.lignes[0]!, debit: "0,2", cle: "" },
      { ...s.lignes[1]!, credit: "0,3" },
    ];
    expect(totaux(s.lignes, "fr")).toEqual({ debit: "0.3", credit: "0.3", equilibre: true });
    expect(construireEcriture(s, "fr").ok).toBe(true);
  });

  it("refuse une pièce déséquilibrée en disant les deux totaux", () => {
    const s = valide();
    s.lignes[1]!.credit = "1000";
    const r = construireEcriture(s, "fr");
    expect(!r.ok && r.fautes).toEqual([{ cle: "ecritures.faute.desequilibre", params: { debit: "1001.5", credit: "1000" } }]);
  });

  it("refuse une écriture vide en les listant toutes", () => {
    const r = construireEcriture(ecritureVide(), "fr");
    expect(!r.ok && r.fautes.map((f) => f.cle)).toEqual([
      "ecritures.faute.journal",
      "ecritures.faute.date",
      "ecritures.faute.libelle",
      "ecritures.faute.compte",
      "ecritures.faute.sans_montant",
      "ecritures.faute.compte",
      "ecritures.faute.sans_montant",
    ]);
  });

  it("refuse un montant illisible, ambigu ou négatif, et un débit avec un crédit sur la même ligne", () => {
    for (const mauvais of ["abc", "1.250", "-5"]) {
      const s = valide();
      s.lignes[0]!.debit = mauvais;
      const r = construireEcriture(s, "fr");
      expect(!r.ok && r.fautes[0]?.cle).toBe("ecritures.faute.montant_illisible");
    }
    const s = valide();
    s.lignes[0]!.credit = "5";
    const r = construireEcriture(s, "fr");
    expect(!r.ok && r.fautes[0]).toEqual({ cle: "ecritures.faute.deux_montants", params: { n: "1" } });
  });

  it("refuse une ligne qui porte à la fois une clé et un accord", () => {
    const s = valide();
    s.lignes[0]!.accord = "DON-1";
    const r = construireEcriture(s, "fr");
    expect(!r.ok && r.fautes[0]).toEqual({ cle: "ecritures.faute.cle_et_accord", params: { n: "1" } });
  });

  it("une ligne à zéro n'est pas une ligne", () => {
    const s = valide();
    s.lignes[0]!.debit = "0";
    const r = construireEcriture(s, "fr");
    expect(!r.ok && r.fautes[0]?.cle).toBe("ecritures.faute.sans_montant");
  });

  it("exige au moins deux lignes", () => {
    const s = valide();
    s.lignes = [s.lignes[0]!];
    const r = construireEcriture(s, "fr");
    expect(!r.ok && r.fautes.map((f) => f.cle)).toContain("ecritures.faute.deux_lignes");
  });
});
