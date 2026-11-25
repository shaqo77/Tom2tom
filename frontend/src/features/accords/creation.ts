import { lireSaisie } from "../../shared/money/montant";

/** Une faute de saisie : la clé d'un message `accords.faute.*` et ses paramètres. */
export interface Faute {
  cle: string;
  params?: Record<string, string>;
}
export type Resultat = { ok: true; corps: Record<string, unknown> } | { ok: false; fautes: Faute[] };

export interface SaisieAccord {
  bailleur: string;
  numero: string;
  libelle: string;
  nature: "don" | "pret" | "contrepartie";
  devise: string;
  montant_initial: string;
  date_effet: string;
  date_fin_eligibilite: string;
  date_cloture: string;
  date_limite_decaissement: string;
}

export const accordVide = (): SaisieAccord => ({
  bailleur: "",
  numero: "",
  libelle: "",
  nature: "don",
  devise: "",
  montant_initial: "",
  date_effet: "",
  date_fin_eligibilite: "",
  date_cloture: "",
  date_limite_decaissement: "",
});

const DATES = ["date_effet", "date_fin_eligibilite", "date_cloture", "date_limite_decaissement"] as const;

/** Un montant positif ou nul tel que le serveur l'attend : une chaîne décimale, jamais un nombre. */
function montant(texte: string, langue: string): string | null {
  const v = lireSaisie(texte, langue);
  return v !== null && v !== "" && !v.startsWith("-") ? v : null;
}

export function construireAccord(s: SaisieAccord, langue: string): Resultat {
  const fautes: Faute[] = [];
  if (!s.bailleur) fautes.push({ cle: "accords.faute.bailleur" });
  if (!s.numero.trim()) fautes.push({ cle: "accords.faute.numero" });
  const devise = s.devise.trim().toUpperCase();
  if (!/^[A-Z]{3}$/.test(devise)) fautes.push({ cle: "accords.faute.devise" });
  const initial = montant(s.montant_initial, langue);
  if (initial === null) fautes.push({ cle: "accords.faute.montant" });
  const dates = Object.fromEntries(DATES.map((d) => [d, s[d] || null]));
  const ordre = DATES.map((d) => s[d]).filter(Boolean);
  if (s.date_effet && s.date_fin_eligibilite && s.date_fin_eligibilite < s.date_effet) {
    fautes.push({ cle: "accords.faute.ordre_dates" });
  } else if (ordre.length > 1 && ordre.some((d, i) => i > 0 && d < (ordre[0] ?? ""))) {
    fautes.push({ cle: "accords.faute.ordre_dates" });
  }
  if (fautes.length > 0) return { ok: false, fautes };
  const corps: Record<string, unknown> = {
    bailleur: s.bailleur,
    numero: s.numero.trim(),
    nature: s.nature,
    devise,
    montant_initial: initial,
  };
  if (s.libelle.trim()) corps.libelle = s.libelle.trim();
  for (const [d, v] of Object.entries(dates)) if (v) corps[d] = v;
  return { ok: true, corps };
}

export interface SaisieCategorie {
  code: string;
  fr: string;
  en: string;
  parent: string;
  plafond: string;
  devise: string;
}
export const categorieVide = (): SaisieCategorie => ({ code: "", fr: "", en: "", parent: "", plafond: "", devise: "" });

export function construireCategorie(s: SaisieCategorie, langue: string): Resultat {
  const fautes: Faute[] = [];
  if (!s.code.trim()) fautes.push({ cle: "accords.faute.code" });
  if (!s.fr.trim() && !s.en.trim()) fautes.push({ cle: "accords.faute.libelle" });
  let plafond: string | null = null;
  if (s.plafond.trim()) {
    plafond = montant(s.plafond, langue);
    if (plafond === null) fautes.push({ cle: "accords.faute.plafond" });
  }
  const devise = s.devise.trim().toUpperCase();
  if (devise && !/^[A-Z]{3}$/.test(devise)) fautes.push({ cle: "accords.faute.devise" });
  if (fautes.length > 0) return { ok: false, fautes };
  const label: Record<string, string> = {};
  if (s.fr.trim()) label.fr = s.fr.trim();
  if (s.en.trim()) label.en = s.en.trim();
  const corps: Record<string, unknown> = { code: s.code.trim(), label };
  if (s.parent) corps.parent = s.parent;
  if (plafond !== null) corps.plafond = plafond;
  if (devise) corps.devise = devise;
  return { ok: true, corps };
}

export interface SaisieAvenant {
  reference: string;
  date: string;
  document: string;
  montant: string;
  motif: string;
}
export const avenantVide = (): SaisieAvenant => ({ reference: "", date: "", document: "", montant: "", motif: "" });

export function construireAvenant(s: SaisieAvenant, langue: string): Resultat {
  const fautes: Faute[] = [];
  if (!s.reference.trim()) fautes.push({ cle: "accords.faute.reference" });
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s.date)) fautes.push({ cle: "accords.faute.date_avenant" });
  if (!s.document) fautes.push({ cle: "accords.faute.document" });
  const revise = montant(s.montant, langue);
  if (revise === null) fautes.push({ cle: "accords.faute.montant_revise" });
  if (fautes.length > 0) return { ok: false, fautes };
  const corps: Record<string, unknown> = { reference: s.reference.trim(), date_avenant: s.date, document_id: s.document, montant_revise: revise };
  if (s.motif.trim()) corps.motif = s.motif.trim();
  return { ok: true, corps };
}

export interface SaisieBailleur {
  code: string;
  nom: string;
  pays: string;
}
export const bailleurVide = (): SaisieBailleur => ({ code: "", nom: "", pays: "" });

export function construireBailleur(s: SaisieBailleur): Resultat {
  const fautes: Faute[] = [];
  if (!s.code.trim()) fautes.push({ cle: "accords.faute.code_bailleur" });
  if (!s.nom.trim()) fautes.push({ cle: "accords.faute.nom_bailleur" });
  const pays = s.pays.trim().toUpperCase();
  if (pays && !/^[A-Z]{2}$/.test(pays)) fautes.push({ cle: "accords.faute.pays" });
  if (fautes.length > 0) return { ok: false, fautes };
  const corps: Record<string, unknown> = { code: s.code.trim(), nom: s.nom.trim() };
  if (pays) corps.pays = pays;
  return { ok: true, corps };
}
