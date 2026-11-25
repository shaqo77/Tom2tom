import { accordVide, categorieVide, construireAccord, construireCategorie } from "./creation";

const valide = () => ({ ...accordVide(), bailleur: "BAD", numero: "DON-9", devise: "usd", montant_initial: "1 250 000,50" });

describe("saisie d'un accord", () => {
  it("rend le montant en chaîne canonique et la devise en majuscules", () => {
    const r = construireAccord(valide(), "fr");
    expect(r).toEqual({ ok: true, corps: { bailleur: "BAD", numero: "DON-9", nature: "don", devise: "USD", montant_initial: "1250000.50" } });
  });
  it("en anglais, la virgule sépare les milliers", () => {
    const r = construireAccord({ ...valide(), montant_initial: "1,250,000.50" }, "en");
    expect(r.ok && r.corps.montant_initial).toBe("1250000.50");
  });
  it("refuse un montant ambigu ou absent, un numéro vide, une devise mal formée, sans rien envoyer", () => {
    const r = construireAccord({ ...accordVide(), devise: "US", montant_initial: "1.250" }, "fr");
    expect(r.ok).toBe(false);
    expect(!r.ok && r.fautes.map((f) => f.cle)).toEqual([
      "accords.faute.bailleur",
      "accords.faute.numero",
      "accords.faute.devise",
      "accords.faute.montant",
    ]);
  });
  it("accepte un montant nul mais refuse un montant négatif", () => {
    expect(construireAccord({ ...valide(), montant_initial: "0" }, "fr").ok).toBe(true);
    expect(construireAccord({ ...valide(), montant_initial: "-5" }, "fr").ok).toBe(false);
  });
  it("refuse une fin d'éligibilité antérieure à l'entrée en vigueur", () => {
    const r = construireAccord({ ...valide(), date_effet: "2026-05-01", date_fin_eligibilite: "2026-04-01" }, "fr");
    expect(!r.ok && r.fautes[0]?.cle).toBe("accords.faute.ordre_dates");
  });
  it("n'envoie que les dates renseignées", () => {
    const r = construireAccord({ ...valide(), date_effet: "2026-01-01" }, "fr");
    expect(r.ok && Object.keys(r.corps)).toContain("date_effet");
    expect(r.ok && Object.keys(r.corps)).not.toContain("date_cloture");
  });
});

describe("saisie d'une catégorie", () => {
  it("construit un libellé par langue renseignée", () => {
    const r = construireCategorie({ ...categorieVide(), code: "BIENS", fr: "Biens", plafond: "600000,5", parent: "ROOT" }, "fr");
    expect(r).toEqual({ ok: true, corps: { code: "BIENS", label: { fr: "Biens" }, parent: "ROOT", plafond: "600000.5" } });
  });
  it("exige un code et au moins un libellé", () => {
    const r = construireCategorie(categorieVide(), "fr");
    expect(!r.ok && r.fautes.map((f) => f.cle)).toEqual(["accords.faute.code", "accords.faute.libelle"]);
  });
  it("refuse un plafond illisible", () => {
    const r = construireCategorie({ ...categorieVide(), code: "X", fr: "X", plafond: "abc" }, "fr");
    expect(!r.ok && r.fautes[0]?.cle).toBe("accords.faute.plafond");
  });
});
