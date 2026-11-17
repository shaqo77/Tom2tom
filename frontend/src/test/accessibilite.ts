import axe from "axe-core";

/** Les violations d'accessibilité que jsdom sait détecter (le contraste, lui, est testé sur les couleurs). */
export async function violations(conteneur: HTMLElement): Promise<string[]> {
  const resultat = await axe.run(conteneur, { rules: { "color-contrast": { enabled: false } } });
  return resultat.violations.map((v) => `${v.id} : ${v.help}`);
}
