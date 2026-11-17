import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const DOSSIER = join(process.cwd(), "src") + "/";
const tokens = readFileSync(join(DOSSIER, "shared/styles/tokens.css"), "utf8");

function bloc(source: string, ouverture: string): Record<string, string> {
  const debut = source.indexOf(ouverture);
  expect(debut, `bloc introuvable : ${ouverture}`).toBeGreaterThan(-1);
  const fin = source.indexOf("\n}", debut);
  const resultat: Record<string, string> = {};
  for (const [, nom, valeur] of source.slice(debut, fin).matchAll(/(--[\w-]+):\s*([^;]+);/g)) {
    resultat[nom as string] = (valeur as string).trim();
  }
  return resultat;
}

const clair = bloc(tokens, ":root {");
const sombreAuto = bloc(tokens, ':root:not([data-theme="light"]) {');
const sombreChoisi = bloc(tokens, ':root[data-theme="dark"] {');

function resoudre(theme: Record<string, string>, nom: string): string {
  let valeur = theme[nom] ?? clair[nom];
  const alias = valeur?.match(/^var\((--[\w-]+)\)$/);
  if (alias) valeur = resoudre(theme, alias[1] as string);
  return valeur as string;
}

function luminance(hex: string): number {
  const n = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(n.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contraste(a: string, b: string): number {
  const [haut, bas] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (haut + 0.05) / (bas + 0.05);
}

// Chaque paire (texte, fond) qui s'affichera réellement ensemble.
const PAIRES: [string, string][] = [
  ["--texte", "--fond"],
  ["--texte", "--surface"],
  ["--texte", "--surface-2"],
  ["--texte-2", "--surface"],
  ["--texte-2", "--surface-2"],
  ["--texte-3", "--surface"],
  ["--accent-contraste", "--accent"],
  ["--accent-contraste", "--accent-survol"],
  ["--accent-texte", "--accent-fond"],
  ["--accent-texte", "--surface"],
  ["--succes", "--succes-fond"],
  ["--attention", "--attention-fond"],
  ["--danger", "--danger-fond"],
  ["--info", "--info-fond"],
  ["--texte", "--succes-fond"],
  ["--texte", "--attention-fond"],
  ["--texte", "--danger-fond"],
  ["--texte", "--info-fond"],
  ["--texte", "--accent-fond"],
  ["--texte-2", "--surface"],
  ["--danger", "--surface-2"],
  ["--succes", "--surface"],
  ["--danger", "--surface"],
  // Les trois autres rôles de couleur
  ["--secondaire-contraste", "--secondaire"],
  ["--secondaire-contraste", "--secondaire-survol"],
  ["--secondaire-texte", "--secondaire-fond"],
  ["--secondaire-texte", "--surface"],
  ["--secondaire", "--surface"],
  ["--tertiaire-texte", "--tertiaire-fond"],
  ["--tertiaire", "--surface"],
  ["--chaud-texte", "--chaud-fond"],
  ["--chaud", "--surface"],
  ["--texte", "--secondaire-fond"],
  ["--texte", "--tertiaire-fond"],
  ["--texte", "--chaud-fond"],
];

describe("jeu de couleurs", () => {
  for (const [nomTheme, theme] of [
    ["clair", clair],
    ["sombre (système)", sombreAuto],
    ["sombre (choisi)", sombreChoisi],
  ] as const) {
    it(`toutes les paires texte/fond atteignent 4,5:1 en thème ${nomTheme}`, () => {
      const trop_faibles = PAIRES.map(([t, f]) => ({
        paire: `${t} sur ${f}`,
        ratio: contraste(resoudre(theme, t), resoudre(theme, f)),
      })).filter((p) => p.ratio < 4.5);
      expect(trop_faibles).toEqual([]);
    });
  }

  it("le thème sombre du système et le thème sombre choisi sont identiques", () => {
    expect(sombreAuto).toEqual(sombreChoisi);
  });

  it("les quatre séries de graphiques sont les quatre rôles, toutes différentes", () => {
    const series = ["--serie-1", "--serie-2", "--serie-3", "--serie-4"].map((nom) => resoudre(clair, nom));
    expect(new Set(series).size).toBe(4);
    expect(series).toEqual([
      resoudre(clair, "--accent"),
      resoudre(clair, "--secondaire"),
      resoudre(clair, "--tertiaire"),
      resoudre(clair, "--chaud"),
    ]);
  });

  it("chaque rôle de couleur existe dans les trois thèmes", () => {
    for (const nom of ["--secondaire", "--tertiaire", "--chaud"]) {
      for (const theme of [clair, sombreAuto, sombreChoisi]) expect(resoudre(theme, nom), nom).toMatch(/^#/);
    }
  });

  it("les focus sont visibles : un anneau de 2 px d'écart avec la couleur d'accent", () => {
    expect(clair["--focus"]).toContain("var(--accent)");
  });
});

function fichiers(dossier: string, extension: RegExp): string[] {
  return readdirSync(dossier).flatMap((nom) => {
    const chemin = join(dossier, nom);
    if (statSync(chemin).isDirectory()) return nom === "node_modules" ? [] : fichiers(chemin, extension);
    return extension.test(nom) ? [chemin] : [];
  });
}

describe("droite-à-gauche : aucun positionnement physique", () => {
  const PHYSIQUE =
    /(^|[^\w-])(left|right)\s*:|margin-(left|right)|padding-(left|right)|border-(left|right)|text-align:\s*(left|right)|float:\s*(left|right)|\b(left|right)\b\s*:/;
  for (const chemin of fichiers(DOSSIER, /\.css$/)) {
    it(`${chemin.replace(DOSSIER, "")} n'utilise ni left ni right`, () => {
      const css = readFileSync(chemin, "utf8");
      expect(css.match(PHYSIQUE)).toBeNull();
    });
  }
  it("des fichiers CSS existent bien (le test ne passe pas à vide)", () => {
    expect(fichiers(DOSSIER, /\.css$/).length).toBeGreaterThanOrEqual(2);
  });
});
