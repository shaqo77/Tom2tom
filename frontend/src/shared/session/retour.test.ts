import { retourSur } from "./retour";

describe("page de retour après connexion", () => {
  it("accepte un chemin de ce site", () => {
    expect(retourSur("/projets/abc")).toBe("/projets/abc");
    expect(retourSur("/projets/abc?x=1#haut")).toBe("/projets/abc?x=1#haut");
  });

  it("refuse tout ce qui mènerait ailleurs (redirection ouverte)", () => {
    for (const piege of [
      "https://pirate.example",
      "http://pirate.example/x",
      "//pirate.example",
      "/\\pirate.example",
      "javascript:alert(1)",
      "pirate.example",
      "/ok\r\nSet-Cookie: a=b",
      "",
    ]) {
      expect(retourSur(piege), piege).toBe("/");
    }
  });

  it("ne renvoie jamais sur la page de connexion elle-même ni sur autre chose qu'une chaîne", () => {
    expect(retourSur("/connexion?retour=/")).toBe("/");
    expect(retourSur(undefined)).toBe("/");
    expect(retourSur(42)).toBe("/");
    expect(retourSur(["/a"])).toBe("/");
  });
});
