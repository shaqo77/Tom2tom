import { accordVide, avenantVide, bailleurVide, categorieVide, construireAccord, construireAvenant, construireBailleur, construireCategorie } from "./creation";

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


describe("saisie d'un avenant", () => {
  const valide = () => ({ ...avenantVide(), reference: "AV-2", date: "2026-06-01", document: "doc-1", montant: "1 500 000,75" });
  it("envoie le montant révisé en chaîne canonique et le document par son identifiant", () => {
    expect(construireAvenant(valide(), "fr")).toEqual({ ok: true, corps: { reference: "AV-2", date_avenant: "2026-06-01", document_id: "doc-1", montant_revise: "1500000.75" } });
  });
  it("garde le motif s'il est donné", () => {
    const r = construireAvenant({ ...valide(), motif: " Rallonge " }, "fr");
    expect(r.ok && r.corps.motif).toBe("Rallonge");
  });
  it("exige référence, date, document et un montant lisible et non négatif", () => {
    const r = construireAvenant({ ...avenantVide(), montant: "-3" }, "fr");
    expect(!r.ok && r.fautes.map((f) => f.cle)).toEqual(["accords.faute.reference", "accords.faute.date_avenant", "accords.faute.document", "accords.faute.montant_revise"]);
    expect(construireAvenant({ ...valide(), montant: "0" }, "fr").ok).toBe(true);
    expect(construireAvenant({ ...valide(), montant: "1.250" }, "fr").ok).toBe(false);
  });
});

describe("saisie d'un bailleur", () => {
  it("met le pays en majuscules et l'omet s'il est vide", () => {
    expect(construireBailleur({ code: " BAD ", nom: "Banque africaine", pays: "ci" })).toEqual({ ok: true, corps: { code: "BAD", nom: "Banque africaine", pays: "CI" } });
    expect(construireBailleur({ code: "UE", nom: "Union européenne", pays: "" })).toEqual({ ok: true, corps: { code: "UE", nom: "Union européenne" } });
  });
  it("exige un code et un nom, et un pays à deux lettres", () => {
    const r = construireBailleur({ ...bailleurVide(), pays: "FRA" });
    expect(!r.ok && r.fautes.map((f) => f.cle)).toEqual(["accords.faute.code_bailleur", "accords.faute.nom_bailleur", "accords.faute.pays"]);
  });
});
