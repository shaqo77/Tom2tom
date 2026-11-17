import { Link, Outlet } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { LANGUES, NOMS_LANGUES, PSEUDO, appliquerLangue } from "../i18n";
import { appliquerTheme, themeEnregistre } from "../shared/theme";
import type { Theme } from "../shared/theme";
import "./app.css";

const THEMES: Theme[] = ["systeme", "clair", "sombre"];

/** L'enveloppe de toutes les pages : lien d'évitement, en-tête, choix de langue et de thème. */
export function MiseEnPage() {
  const { t, i18n } = useTranslation();
  const [theme, definirTheme] = useState<Theme>(themeEnregistre);
  const langues = import.meta.env.DEV ? [...LANGUES, PSEUDO] : [...LANGUES];

  return (
    <>
      <a className="evitement" href="#contenu">
        {t("commun.aller_au_contenu")}
      </a>
      <header className="entete">
        <Link to="/" className="entete__marque">
          {t("accueil.titre")}
        </Link>
        <div className="entete__reglages">
          <label className="reglage">
            <span className="reglage__nom">{t("commun.langue")}</span>
            <select
              value={i18n.language}
              onChange={(e) => void appliquerLangue(e.target.value)}
              className="reglage__choix"
            >
              {langues.map((code) => (
                <option key={code} value={code}>
                  {NOMS_LANGUES[code]}
                </option>
              ))}
            </select>
          </label>
          <label className="reglage">
            <span className="reglage__nom">{t("commun.theme")}</span>
            <select
              value={theme}
              onChange={(e) => {
                const choisi = e.target.value as Theme;
                definirTheme(choisi);
                appliquerTheme(choisi);
              }}
              className="reglage__choix"
            >
              {THEMES.map((valeur) => (
                <option key={valeur} value={valeur}>
                  {t(`commun.theme_${valeur}`)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>
      <main id="contenu" className="contenu" tabIndex={-1}>
        <Outlet />
      </main>
    </>
  );
}
