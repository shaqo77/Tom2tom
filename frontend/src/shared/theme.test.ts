import { appliquerTheme, themeEnregistre } from "./theme";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("thème", () => {
  it("suit le système tant que l'utilisateur n'a rien choisi", () => {
    expect(themeEnregistre()).toBe("systeme");
    appliquerTheme("systeme");
    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });

  it("garde un choix explicite et le pose sur le document", () => {
    appliquerTheme("sombre");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(themeEnregistre()).toBe("sombre");
    appliquerTheme("clair");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });

  it("revenir au système efface le choix", () => {
    appliquerTheme("sombre");
    appliquerTheme("systeme");
    expect(themeEnregistre()).toBe("systeme");
    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });

  it("ne casse pas quand le stockage local est indisponible", () => {
    const espion = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("bloqué");
    });
    const ecriture = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("bloqué");
    });
    expect(themeEnregistre()).toBe("systeme");
    expect(() => appliquerTheme("sombre")).not.toThrow();
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    espion.mockRestore();
    ecriture.mockRestore();
  });

  it("ignore une valeur enregistrée qui n'est pas un thème", () => {
    window.localStorage.setItem("sigf.theme", "violet");
    expect(themeEnregistre()).toBe("systeme");
  });
});
