import { construireJustification } from "./justification";

describe("saisie d'une justification", () => {
  it("n'envoie que la demande quand le reste est vide", () => {
    expect(construireJustification("d1", "", "", "fr")).toEqual({ ok: true, corps: { demande: "d1" } });
  });
  it("rend le montant en chaîne canonique, selon la langue", () => {
    expect(construireJustification("d1", "1 250,50", "2026-03-20", "fr")).toEqual({ ok: true, corps: { demande: "d1", montant: "1250.50", date_soumission: "2026-03-20" } });
    expect(construireJustification("d1", "1,250.50", "", "en")).toEqual({ ok: true, corps: { demande: "d1", montant: "1250.50" } });
  });
  it("refuse une demande absente, un montant nul, négatif, ambigu ou illisible", () => {
    expect(construireJustification("", "", "", "fr")).toEqual({ ok: false, fautes: [{ cle: "special.faute.demande" }] });
    for (const m of ["0", "-5", "1.250", "abc"]) {
      expect(construireJustification("d1", m, "", "fr")).toEqual({ ok: false, fautes: [{ cle: "special.faute.montant" }] });
    }
  });
});
