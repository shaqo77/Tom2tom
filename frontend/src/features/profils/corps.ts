/**
 * Le corps d'un profil de décaissement à partir de ce qui est saisi : toute la validation vit ici, sans interface,
 * pour être testée seule. Les montants et les taux restent des CHAÎNES décimales exactes (`decimal.js`), jamais
 * des `number`. Le serveur revérifie tout : ces contrôles évitent seulement un envoi inutile.
 */
import { comparer, lire } from "../../shared/money/montant";
import type { Regime } from "./types";

export const CODES_METHODE = ["advance", "reimbursement", "direct_payment", "special_commitment"] as const;
export type CodeMethode = (typeof CODES_METHODE)[number];
export const PIECES = ["soe", "records", "ifr", "summary_sheet"] as const;
export const JALONS = ["effectiveness_date", "eligibility_date", "closing_date", "disbursement_deadline"] as const;
export type Jalon = (typeof JALONS)[number];

export interface SaisieMethode {
  autorisee: boolean;
  pieces: string[];
  seuil_complet: string;
  min_montant: string;
  min_pourcentage: string;
}
export interface SaisieRegle {
  incluse: boolean;
  allocation: string;
  taux: string;
  assiette: "taxes_included" | "net_of_taxes";
  de: string;
  a: string;
  revue: boolean;
  max_contrat: string;
  fin_propre: boolean;
}
export interface SaisieCompte {
  compte: string;
  devise: string;
  genre: "fixed" | "variable";
  plafond: string;
  seuil: string;
}
export interface Saisie {
  valid_from: string;
  regime: Regime;
  exigence: string;
  jalons: Record<Jalon, string>;
  methodes: Record<CodeMethode, SaisieMethode>;
  regles: Record<string, SaisieRegle>;
  comptes: SaisieCompte[];
}

/** Une erreur : une clé de traduction et ses paramètres. */
export interface Faute {
  cle: string;
  params?: Record<string, string>;
}

export type Resultat = { ok: true; corps: Record<string, unknown> } | { ok: false; fautes: Faute[] };

const normaliser = (brut: string) => brut.trim().replace(",", ".");
const DECIMAL = /^\d+(\.\d+)?$/;

/** Un décimal exact positif ou nul (« 0.1 », « 1000 ») : la chaîne normalisée, `""` si vide, `null` si illisible. */
export function decimal(brut: string): string | "" | null {
  const v = normaliser(brut);
  if (v === "") return "";
  return DECIMAL.test(v) ? v : null;
}
/** Un taux : strictement supérieur à 0 et au plus 1. */
export function taux(brut: string): string | null {
  const v = decimal(brut);
  if (!v || !/[1-9]/.test(v)) return null;
  return comparer(v, "1") <= 0 ? lire(v).toFixed() : null;
}
/** Un pourcentage de 0 à 100. */
export function pourcentage(brut: string): string | "" | null {
  const v = decimal(brut);
  if (v === null) return null;
  if (v === "") return "";
  return comparer(v, "100") <= 0 ? v : null;
}

export function saisieVide(categories: string[]): Saisie {
  return {
    valid_from: "",
    regime: "transaction_based",
    exigence: "",
    jalons: { effectiveness_date: "", eligibility_date: "", closing_date: "", disbursement_deadline: "" },
    methodes: Object.fromEntries(CODES_METHODE.map((m) => [m, { autorisee: false, pieces: [], seuil_complet: "", min_montant: "", min_pourcentage: "" }])) as unknown as Record<CodeMethode, SaisieMethode>,
    regles: Object.fromEntries(categories.map((c) => [c, { incluse: false, allocation: "", taux: "", assiette: "taxes_included", de: "", a: "", revue: false, max_contrat: "", fin_propre: false }])),
    comptes: [],
  };
}

export function construireCorps(s: Saisie): Resultat {
  const fautes: Faute[] = [];
  if (!s.valid_from) fautes.push({ cle: "profils.faute.date_effet" });

  const methodes: Record<string, unknown>[] = [];
  for (const code of CODES_METHODE) {
    const m = s.methodes[code];
    if (!m.autorisee) continue;
    const seuil = decimal(m.seuil_complet);
    const minimum = decimal(m.min_montant);
    const pct = pourcentage(m.min_pourcentage);
    if (seuil === null || minimum === null) fautes.push({ cle: "profils.faute.montant_methode", params: { methode: code } });
    if (pct === null) fautes.push({ cle: "profils.faute.pourcentage_methode", params: { methode: code } });
    if (minimum && pct) fautes.push({ cle: "profils.faute.deux_minimums", params: { methode: code } });
    methodes.push({
      method: code,
      is_enabled: true,
      supporting_docs: [...m.pieces].sort(),
      ...(seuil ? { full_doc_threshold: seuil } : {}),
      ...(minimum ? { min_application_amount: minimum } : {}),
      ...(pct ? { min_application_pct_of_ceiling: pct } : {}),
    });
  }
  if (methodes.length === 0) fautes.push({ cle: "profils.faute.aucune_methode" });

  const regles: Record<string, unknown>[] = [];
  for (const [categorie, r] of Object.entries(s.regles)) {
    if (!r.incluse) continue;
    const allocation = decimal(r.allocation);
    const t = taux(r.taux);
    const maximum = decimal(r.max_contrat);
    if (!allocation) fautes.push({ cle: "profils.faute.allocation", params: { categorie } });
    if (t === null) fautes.push({ cle: "profils.faute.taux", params: { categorie } });
    if (maximum === null) fautes.push({ cle: "profils.faute.maximum_contrat", params: { categorie } });
    if (r.de && r.a && r.de > r.a) fautes.push({ cle: "profils.faute.eligibilite", params: { categorie } });
    if (r.fin_propre && !r.a) fautes.push({ cle: "profils.faute.fin_propre_sans_fin", params: { categorie } });
    regles.push({
      category: categorie,
      allocation: allocation ?? "",
      funding_rate: t ?? "",
      tax_basis: r.assiette,
      ...(r.de ? { eligibility_from: r.de } : {}),
      ...(r.a ? { eligibility_to: r.a } : {}),
      requires_prior_review: r.revue,
      ...(maximum ? { max_per_contract: maximum } : {}),
      fin_propre_a_la_categorie: r.fin_propre,
    });
  }
  if (regles.length === 0) fautes.push({ cle: "profils.faute.aucune_regle" });

  const comptes: Record<string, unknown>[] = [];
  for (const c of s.comptes) {
    if (!c.compte) {
      fautes.push({ cle: "profils.faute.compte_manquant" });
      continue;
    }
    const plafond = decimal(c.plafond);
    const seuil = pourcentage(c.seuil);
    if (plafond === null || (c.genre === "fixed" && !plafond)) fautes.push({ cle: "profils.faute.plafond", params: { compte: c.compte } });
    if (c.genre === "variable" && plafond) fautes.push({ cle: "profils.faute.plafond_variable", params: { compte: c.compte } });
    if (seuil === null) fautes.push({ cle: "profils.faute.seuil_compte", params: { compte: c.compte } });
    comptes.push({
      compte: c.compte,
      devise: c.devise,
      ceiling_kind: c.genre,
      ...(plafond ? { ceiling_amount: plafond } : {}),
      ...(seuil ? { replenishment_threshold_pct: seuil } : {}),
    });
  }

  if (fautes.length) return { ok: false, fautes };
  return {
    ok: true,
    corps: {
      valid_from: s.valid_from,
      regime: s.regime,
      ...Object.fromEntries(JALONS.map((j) => [j, s.jalons[j] || null])),
      ...(s.exigence.trim() ? { exigence: s.exigence.trim() } : {}),
      methodes,
      regles,
      ...(comptes.length ? { comptes } : {}),
    },
  };
}
