import { CODES_METHODE, construireCorps, decimal, pourcentage, saisieVide, taux } from "./corps";
import type { Saisie } from "./corps";

function valide(): Saisie {
  const s = saisieVide(["SERVICES", "BIENS"]);
  s.valid_from = "2026-01-01";
  s.methodes.reimbursement = { autorisee: true, pieces: ["soe", "ifr"], seuil_complet: "", min_montant: "100", min_pourcentage: "" };
  s.regles.SERVICES = { incluse: true, allocation: "400000", taux: "0.85", assiette: "taxes_included", de: "", a: "", revue: false, max_contrat: "", fin_propre: false };
  return s;
}
const fautes = (s: Saisie) => {
  const r = construireCorps(s);
  return r.ok ? [] : r.fautes.map((f) => f.cle);
};

describe("décimaux exacts", () => {
  it("garde la chaîne telle quelle : jamais de passage par un nombre", () => {
    expect(decimal("0.1")).toBe("0.1");
    expect(decimal("0,30")).toBe("0.30");
    expect(decimal(" 1250.50 ")).toBe("1250.50");
    expect(decimal("")).toBe("");
  });
  it.each(["abc", "-1", "1e3", "1.2.3", "1,2,3", "Infinity", "NaN"])("refuse « %s »", (v) => {
    expect(decimal(v)).toBeNull();
  });
  it("0.1 + 0.2 ne produit jamais 0.30000000000000004 : rien n'est additionné ici", () => {
    const s = valide();
    s.regles.SERVICES!.allocation = "0.1";
    const r = construireCorps(s);
    expect(r.ok && (r.corps.regles as { allocation: string }[])[0]?.allocation).toBe("0.1");
  });
});

describe("taux entre 0 (exclu) et 1", () => {
  it.each(["0.01", "0.85", "1", "1.0", "1.000000"])("accepte %s", (v) => expect(taux(v)).not.toBeNull());
  it.each(["0", "0.0", "1.01", "1.5", "2", "abc", "", "-0.5", "1e-1"])("refuse « %s »", (v) => expect(taux(v)).toBeNull());
  it("envoie 0,85 sous la forme « 0.85 »", () => expect(taux("0,85")).toBe("0.85"));
});

describe("pourcentage de 0 à 100", () => {
  it.each(["0", "50", "100", "99.99"])("accepte %s", (v) => expect(pourcentage(v)).toBe(v));
  it.each(["100.01", "101", "-1", "abc"])("refuse « %s »", (v) => expect(pourcentage(v)).toBeNull());
  it("vide : pas de valeur", () => expect(pourcentage("")).toBe(""));
});

describe("le corps d'un profil", () => {
  it("un profil minimal valide donne un corps complet, jalons nuls compris", () => {
    const r = construireCorps(valide());
    expect(r).toEqual({
      ok: true,
      corps: {
        valid_from: "2026-01-01",
        regime: "transaction_based",
        effectiveness_date: null,
        eligibility_date: null,
        closing_date: null,
        disbursement_deadline: null,
        methodes: [{ method: "reimbursement", is_enabled: true, supporting_docs: ["ifr", "soe"], min_application_amount: "100" }],
        regles: [{ category: "SERVICES", allocation: "400000", funding_rate: "0.85", tax_basis: "taxes_included", requires_prior_review: false, fin_propre_a_la_categorie: false }],
      },
    });
  });
  it("n'envoie que les méthodes autorisées et les catégories incluses", () => {
    const s = valide();
    expect(CODES_METHODE).toHaveLength(4);
    const r = construireCorps(s);
    expect(r.ok && (r.corps.methodes as unknown[]).length).toBe(1);
    expect(r.ok && (r.corps.regles as unknown[]).length).toBe(1);
  });
  it("exige une date d'effet, une méthode et une règle", () => {
    expect(fautes({ ...valide(), valid_from: "" })).toContain("profils.faute.date_effet");
    const sansMethode = valide();
    sansMethode.methodes.reimbursement.autorisee = false;
    expect(fautes(sansMethode)).toContain("profils.faute.aucune_methode");
    const sansRegle = valide();
    sansRegle.regles.SERVICES!.incluse = false;
    expect(fautes(sansRegle)).toContain("profils.faute.aucune_regle");
  });
  it("refuse un taux de 1,5 et une allocation vide ou illisible", () => {
    const s = valide();
    s.regles.SERVICES!.taux = "1.5";
    expect(fautes(s)).toContain("profils.faute.taux");
    s.regles.SERVICES!.taux = "0.85";
    s.regles.SERVICES!.allocation = "";
    expect(fautes(s)).toContain("profils.faute.allocation");
    s.regles.SERVICES!.allocation = "1e6";
    expect(fautes(s)).toContain("profils.faute.allocation");
  });
  it("deux minimums (montant ET pourcentage) sont refusés comme au serveur", () => {
    const s = valide();
    s.methodes.reimbursement.min_pourcentage = "10";
    expect(fautes(s)).toContain("profils.faute.deux_minimums");
  });
  it("un pourcentage de plafond hors de 0 à 100 est refusé", () => {
    const s = valide();
    s.methodes.reimbursement.min_montant = "";
    s.methodes.reimbursement.min_pourcentage = "150";
    expect(fautes(s)).toContain("profils.faute.pourcentage_methode");
  });
  it("une éligibilité inversée ou une fin propre sans fin est refusée", () => {
    const s = valide();
    s.regles.SERVICES!.de = "2026-06-01";
    s.regles.SERVICES!.a = "2026-01-01";
    expect(fautes(s)).toContain("profils.faute.eligibilite");
    s.regles.SERVICES!.de = "";
    s.regles.SERVICES!.a = "";
    s.regles.SERVICES!.fin_propre = true;
    expect(fautes(s)).toContain("profils.faute.fin_propre_sans_fin");
  });
  it("un compte à plafond fixe exige un plafond, un compte à plafond variable n'en a pas", () => {
    const s = valide();
    s.comptes = [{ compte: "CD-1", devise: "USD", genre: "fixed", plafond: "", seuil: "" }];
    expect(fautes(s)).toContain("profils.faute.plafond");
    s.comptes = [{ compte: "CD-1", devise: "USD", genre: "variable", plafond: "500", seuil: "" }];
    expect(fautes(s)).toContain("profils.faute.plafond_variable");
    s.comptes = [{ compte: "CD-1", devise: "USD", genre: "fixed", plafond: "500000.50", seuil: "50" }];
    const r = construireCorps(s);
    expect(r.ok && r.corps.comptes).toEqual([{ compte: "CD-1", devise: "USD", ceiling_kind: "fixed", ceiling_amount: "500000.50", replenishment_threshold_pct: "50" }]);
  });
  it("un compte sans code est refusé", () => {
    const s = valide();
    s.comptes = [{ compte: "", devise: "USD", genre: "fixed", plafond: "1", seuil: "" }];
    expect(fautes(s)).toContain("profils.faute.compte_manquant");
  });
});
