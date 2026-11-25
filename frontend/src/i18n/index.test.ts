import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import en from "./locales/en.json";
import fr from "./locales/fr.json";
import { appliquerLangue, i18n, pseudoTraduire } from "./index";
import { appeler, definirLangueApi } from "../shared/api/client";

const parametres = (texte: string) => [...texte.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]).sort();

describe("catalogues", () => {
  it("français et anglais ont exactement les mêmes clés", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(fr).sort());
  });

  it("chaque message a les mêmes paramètres dans les deux langues, et aucun n'est vide", () => {
    const ecarts: string[] = [];
    for (const [cle, texte] of Object.entries(fr)) {
      const autre = (en as Record<string, string>)[cle] ?? "";
      if (!texte.trim() || !autre.trim()) ecarts.push(`${cle} : vide`);
      if (parametres(texte).join() !== parametres(autre).join()) ecarts.push(`${cle} : paramètres`);
    }
    expect(ecarts).toEqual([]);
  });

  it("aucune traduction n'est identique au français, sauf les noms propres", () => {
    const IDENTIQUES = new Set([ // mots identiques dans les deux langues
      "accueil.titre",
      "ecritures.col_journal",
      "ecritures.col_date",
      "ecritures.col_action",
      "ecritures.form.journal",
      "conception.messages",
      "message.info",
      "session.organisation",
      "conception.badge_action",
      "tableau.jour",
      "tableau.anomalies",
      "devises.col_version",
      "tableau.descente.total",
      "tableau.descente.col_date",
      "profils.col_version",
      "profils.col_action",
      "profils.col_allocation",
      "profils.plafond.variable",
      "evaluations.resultat.information",
      "evaluations.col_message",
      "evaluations.col_action",
      "evaluations.justifications",
      "evaluations.justification_champ",
      "documents.nav",
      "documents.col_version",
      "documents.col_actions",
      "cles.col_code",
      "cles.col_action",
      "cles.col_version",
      "accords.col_action",
      "accords.col_code",
      "accords.col_date",
      "taux.col_date",
      "taux.col_type",
      "taux.col_source",
      "taux.date",
      "profils.col_version",
      "profils.col_action",
      "profils.col_allocation",
      "profils.plafond.variable",
      "controles.severite.information",
      "controles.col_code",
      "controles.col_version",
      "controles.col_action",
      "special.col_action",
    ]);
    const memes = Object.entries(fr).filter(
      ([cle, texte]) => (en as Record<string, string>)[cle] === texte && !IDENTIQUES.has(cle),
    );
    expect(memes.map(([cle]) => cle)).toEqual([]);
  });
});

describe("pseudo-langue droite-à-gauche", () => {
  it("allonge le texte, le marque et conserve les paramètres intacts", () => {
    const texte = pseudoTraduire("Bienvenue, {{nom}}");
    expect(texte).toContain("{{nom}}");
    expect(texte.length).toBeGreaterThan("Bienvenue, {{nom}}".length * 1.3);
    expect(texte).not.toBe("Bienvenue, {{nom}}");
  });

  it("est déterministe", () => {
    expect(pseudoTraduire("Valider")).toBe(pseudoTraduire("Valider"));
  });
});

describe("changement de langue", () => {
  afterEach(async () => appliquerLangue("fr"));

  it("pose la langue et le sens d'écriture du document, et celle envoyée au serveur", async () => {
    await appliquerLangue("en");
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
    expect(i18n.t("commun.valider")).toBe("Confirm");

    await appliquerLangue("pseudo");
    expect(document.documentElement.dir).toBe("rtl");
    expect(i18n.t("accueil.bienvenue", { nom: "Awaleh" })).toContain("Awaleh");
  });

  it("transmet la langue choisie à l'API", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    definirLangueApi("fr");
    await appliquerLangue("en");
    await appeler("/session/moi/");
    const entetes = new Headers((fetch as ReturnType<typeof vi.fn>).mock.calls[0]?.[1]?.headers);
    expect(entetes.get("Accept-Language")).toBe("en");
    vi.unstubAllGlobals();
  });

  it("la pseudo-langue n'existe pas en production : elle retombe sur le français", async () => {
    vi.stubEnv("DEV", false);
    expect(await appliquerLangue("pseudo")).toBe("fr");
    expect(document.documentElement.dir).toBe("ltr");
    vi.unstubAllEnvs();
  });

  it("repli sur le français pour une langue inconnue", async () => {
    await appliquerLangue("zz");
    expect(document.documentElement.lang).toBe("fr");
  });
});

function fichiers(dossier: string, extension: RegExp): string[] {
  return readdirSync(dossier).flatMap((nom) => {
    const chemin = join(dossier, nom);
    if (statSync(chemin).isDirectory()) return fichiers(chemin, extension);
    return extension.test(nom) && !/\.test\./.test(nom) ? [chemin] : [];
  });
}

describe("aucun libellé en dur", () => {
  it("aucun texte visible n'est écrit directement dans un composant", () => {
    const fautes: string[] = [];
    for (const chemin of fichiers(join(process.cwd(), "src"), /\.tsx$/)) {
      const source = readFileSync(chemin, "utf8");
      // Du texte entre deux balises, hors expression `{…}`.
      for (const m of source.matchAll(/>([^<>{}\n]*[A-Za-zÀ-ÿ]{2,}[^<>{}\n]*)</g)) {
        fautes.push(`${chemin.replace(process.cwd() + "/", "")} : « ${(m[1] as string).trim()} »`);
      }
      for (const m of source.matchAll(/\b(aria-label|placeholder|title|alt)="([^"{}]*[A-Za-zÀ-ÿ]{2,}[^"{}]*)"/g)) {
        fautes.push(`${chemin.replace(process.cwd() + "/", "")} : ${m[1]}="${m[2]}"`);
      }
    }
    expect(fautes).toEqual([]);
  });
});
