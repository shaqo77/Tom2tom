/** Le thème : « système » par défaut (suit le réglage du poste), ou un choix explicite gardé en local. */
export type Theme = "systeme" | "clair" | "sombre";
const CLE = "sigf.theme";

export function themeEnregistre(): Theme {
  try {
    const v = window.localStorage.getItem(CLE);
    return v === "clair" || v === "sombre" ? v : "systeme";
  } catch {
    return "systeme"; // stockage indisponible (navigation privée, blocage) : on suit le système
  }
}

export function appliquerTheme(theme: Theme): void {
  const racine = document.documentElement;
  if (theme === "systeme") racine.removeAttribute("data-theme");
  else racine.setAttribute("data-theme", theme === "clair" ? "light" : "dark");
  try {
    if (theme === "systeme") window.localStorage.removeItem(CLE);
    else window.localStorage.setItem(CLE, theme);
  } catch {
    /* le choix vaut pour cette page seulement */
  }
}
