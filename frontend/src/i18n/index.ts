/**
 * L'internationalisation : français, anglais, et une pseudo-langue DROITE-À-GAUCHE pour traquer,
 * dès maintenant, tout ce qui casserait en arabe (décision D-04). Aucun libellé n'est écrit dans un
 * composant : tout passe par `t("domaine.cle")`.
 */
import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import { definirLangueApi } from "../shared/api/client";
import en from "./locales/en.json";
import fr from "./locales/fr.json";

export const LANGUES = ["fr", "en"] as const;
export type Langue = (typeof LANGUES)[number];
export const PSEUDO = "pseudo";

/** Noms des langues dans leur propre langue (jamais traduits : c'est la convention des sélecteurs). */
export const NOMS_LANGUES: Record<string, string> = { fr: "Français", en: "English", [PSEUDO]: "Pseudo (RTL)" };
const SENS_DROITE_A_GAUCHE = new Set([PSEUDO, "ar"]);

const ACCENTS: Record<string, string> = {
  a: "á", e: "é", i: "í", o: "ó", u: "ú", c: "ç", n: "ñ",
  A: "Á", E: "É", I: "Í", O: "Ó", U: "Ú", C: "Ç", N: "Ñ",
};

/** Texte allongé d'environ 40 %, accentué et encadré : repère visuel, jamais traduit pour de bon. */
export function pseudoTraduire(texte: string): string {
  const morceaux = texte.split(/(\{\{[^}]+\}\})/); // les paramètres restent intacts
  const transforme = morceaux
    .map((m) => (m.startsWith("{{") ? m : [...m].map((c) => ACCENTS[c] ?? c).join("")))
    .join("");
  const rallonge = "~".repeat(Math.max(2, Math.ceil(texte.length * 0.4)));
  return `‏⟦${transforme} ${rallonge}⟧`;
}

const pseudo = Object.fromEntries(Object.entries(fr).map(([cle, texte]) => [cle, pseudoTraduire(texte)]));

void i18next.use(initReactI18next).init({
  resources: {
    fr: { translation: fr },
    en: { translation: en },
    [PSEUDO]: { translation: pseudo },
  },
  lng: "fr",
  fallbackLng: "fr",
  interpolation: { escapeValue: false }, // React échappe déjà
  returnNull: false,
});

export const i18n = i18next;

/** Change la langue de l'interface, du document (lang, dir) et des messages renvoyés par l'API. */
export async function appliquerLangue(demandee: string): Promise<string> {
  // La pseudo-langue sert à tester la mise en page : jamais proposée ni acceptée en production.
  const pseudoPermise = demandee === PSEUDO && import.meta.env.DEV;
  const connue = pseudoPermise || (LANGUES as readonly string[]).includes(demandee);
  const langue = connue ? demandee : "fr";
  await i18next.changeLanguage(langue);
  document.documentElement.lang = langue === PSEUDO ? "ar" : langue;
  document.documentElement.dir = SENS_DROITE_A_GAUCHE.has(langue) ? "rtl" : "ltr";
  definirLangueApi(langue === PSEUDO ? "fr" : langue);
  return langue;
}
