import { lireObjet } from "./objet";

describe("lecture de l'objet d'un dossier", () => {
  it("le type est obligatoire, l'identifiant facultatif", () => {
    expect(lireObjet("", "")).toEqual({ ok: false, cle: "evaluations.dossier.faute_type" });
    expect(lireObjet(" ecriture ", "")).toEqual({ ok: true, type: "ecriture", id: "" });
  });
  it("un identifiant donné doit être un UUID", () => {
    expect(lireObjet("ecriture", "pas-un-uuid")).toEqual({ ok: false, cle: "evaluations.dossier.faute_id" });
    expect(lireObjet("ecriture", " 3f2b8c1e-5a47-4d9e-9b1a-0c6d2e7f8a90 ")).toEqual({ ok: true, type: "ecriture", id: "3f2b8c1e-5a47-4d9e-9b1a-0c6d2e7f8a90" });
  });
});
