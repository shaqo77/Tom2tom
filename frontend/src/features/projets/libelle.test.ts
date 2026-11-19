import { libelleProjet } from "./libelle";

describe("libellé d'un projet", () => {
  const projet = { code: "P1", libelle: { fr: "Projet un", en: "Project one" } };
  it("suit la langue de l'interface", () => {
    expect(libelleProjet(projet, "fr")).toBe("Projet un");
    expect(libelleProjet(projet, "en")).toBe("Project one");
  });
  it("se replie sur l'autre langue, puis sur le code", () => {
    expect(libelleProjet({ code: "P1", libelle: { fr: "Seulement" } }, "en")).toBe("Seulement");
    expect(libelleProjet({ code: "P1", libelle: { en: "Only" } }, "fr")).toBe("Only");
    expect(libelleProjet({ code: "P1", libelle: {} }, "fr")).toBe("P1");
    expect(libelleProjet({ code: "P1", libelle: { fr: "  " } }, "fr")).toBe("P1");
  });
});
