import { lireSaisie } from "../../shared/money/montant";
import type { ChampLangage, Langage, Severite, TypeChamp } from "./types";

/** Une faute de saisie : la clé d'un message `controles.faute.*` et ses paramètres. */
export interface Faute {
  cle: string;
  params?: Record<string, string>;
}
export type Resultat = { ok: true; corps: Record<string, unknown> } | { ok: false; fautes: Faute[] };

export interface SaisieCondition {
  champ: string;
  op: string;
  /** Le texte saisi ; pour une liste de valeurs, séparées par des points-virgules ; pour « entre », la première date. */
  valeur: string;
  /** La seconde date de « entre ». */
  valeur2: string;
  /** Pour « somme ≤ » : le champ numérique des éléments à additionner. */
  somme_de: string;
}
export interface SaisieControle {
  code: string;
  fr: string;
  en: string;
  type_regle: string;
  severity: Severite;
  valid_from: string;
  action_fr: string;
  action_en: string;
  manuel: boolean;
  conditions: SaisieCondition[];
}

export const conditionVide = (): SaisieCondition => ({ champ: "", op: "", valeur: "", valeur2: "", somme_de: "" });
export const controleVide = (): SaisieControle => ({
  code: "",
  fr: "",
  en: "",
  type_regle: "",
  severity: "avertissement",
  valid_from: "",
  action_fr: "",
  action_en: "",
  manuel: false,
  conditions: [conditionVide()],
});

/** Les opérateurs que le langage propose pour un champ : ceux dont les types acceptés contiennent le sien. */
export function operateursDuChamp(langage: Langage, champ: ChampLangage | undefined): string[] {
  if (!champ) return [];
  return Object.entries(langage.operateurs)
    .filter(([, regle]) => regle.types.includes(champ.type))
    .map(([op]) => op);
}

/** Ce que l'écran doit demander pour un opérateur : rien, une valeur, une liste, deux dates, ou une somme. */
export type Saisie = "aucune" | "valeur" | "liste" | "deux_dates" | "somme" | "entier";
export function saisieDe(op: string, type: TypeChamp, langage: Langage): Saisie {
  if (langage.operateurs[op]?.sans_valeur) return "aucune";
  if (op === "in" || op === "not_in") return "liste";
  if (op === "entre") return "deux_dates";
  if (op === "somme_lte") return "somme";
  if (op === "nombre_eq") return "entier";
  void type;
  return "valeur";
}

function valeurScalaire(texte: string, type: TypeChamp, langue: string): string | number | null {
  const t = texte.trim();
  if (!t) return null;
  if (type === "texte") return t;
  if (type === "date") return /^\d{4}-\d{2}-\d{2}$/.test(t) ? t : null;
  if (type === "entier") return /^-?\d+$/.test(t) ? Number.parseInt(t, 10) : null;
  if (type === "decimal") return lireSaisie(t, langue);
  return null;
}

/** Une condition → le JSON du langage, ou la liste de ses fautes. Jamais de nombre à virgule : un décimal part en chaîne. */
function construireCondition(c: SaisieCondition, n: string, champs: Record<string, ChampLangage>, langage: Langage, langue: string): { condition?: Record<string, unknown>; fautes: Faute[] } {
  const fautes: Faute[] = [];
  const champ = champs[c.champ];
  if (!champ) return { fautes: [{ cle: "controles.faute.champ", params: { n } }] };
  if (!operateursDuChamp(langage, champ).includes(c.op)) return { fautes: [{ cle: "controles.faute.operateur", params: { n } }] };
  const condition: Record<string, unknown> = { champ: c.champ, op: c.op };
  const saisie = saisieDe(c.op, champ.type, langage);
  if (saisie === "valeur") {
    const v = valeurScalaire(c.valeur, champ.type, langue);
    if (v === null) fautes.push({ cle: "controles.faute.valeur", params: { n } });
    else condition.valeur = v;
  } else if (saisie === "entier") {
    const v = valeurScalaire(c.valeur, "entier", langue);
    if (v === null) fautes.push({ cle: "controles.faute.valeur", params: { n } });
    else condition.valeur = v;
  } else if (saisie === "liste") {
    const morceaux = c.valeur.split(";").map((m) => m.trim()).filter(Boolean);
    const valeurs = morceaux.map((m) => valeurScalaire(m, champ.type, langue));
    if (morceaux.length === 0 || valeurs.some((v) => v === null)) fautes.push({ cle: "controles.faute.liste", params: { n } });
    else condition.valeur = valeurs;
  } else if (saisie === "deux_dates") {
    const du = valeurScalaire(c.valeur, "date", langue);
    const au = valeurScalaire(c.valeur2, "date", langue);
    if (du === null || au === null) fautes.push({ cle: "controles.faute.dates", params: { n } });
    else if (String(du) >= String(au)) fautes.push({ cle: "controles.faute.intervalle", params: { n } });
    else condition.valeur = [du, au];
  } else if (saisie === "somme") {
    const numeriques = Object.entries(champ.elements ?? {}).filter(([, t]) => t === "decimal" || t === "entier").map(([nom]) => nom);
    if (!numeriques.includes(c.somme_de)) fautes.push({ cle: "controles.faute.somme_de", params: { n } });
    else condition.somme_de = c.somme_de;
    const v = valeurScalaire(c.valeur, "decimal", langue);
    if (v === null) fautes.push({ cle: "controles.faute.valeur", params: { n } });
    else condition.valeur = v;
  }
  return fautes.length > 0 ? { fautes } : { condition, fautes };
}

export function construireControle(s: SaisieControle, langage: Langage, langue: string): Resultat {
  const fautes: Faute[] = [];
  if (!s.code.trim()) fautes.push({ cle: "controles.faute.code" });
  if (!s.fr.trim() && !s.en.trim()) fautes.push({ cle: "controles.faute.libelle" });
  const champs = langage.types_regle[s.type_regle];
  if (!champs) fautes.push({ cle: "controles.faute.type_regle" });
  if (!langage.severites.includes(s.severity)) fautes.push({ cle: "controles.faute.severite" });
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s.valid_from)) fautes.push({ cle: "controles.faute.date_effet" });

  const conditions: Record<string, unknown>[] = [];
  if (!s.manuel && champs) {
    if (s.conditions.length === 0) fautes.push({ cle: "controles.faute.aucune_condition" });
    if (s.conditions.length > langage.max_conditions) fautes.push({ cle: "controles.faute.trop_de_conditions", params: { max: String(langage.max_conditions) } });
    s.conditions.forEach((c, i) => {
      const r = construireCondition(c, String(i + 1), champs, langage, langue);
      fautes.push(...r.fautes);
      if (r.condition) conditions.push(r.condition);
    });
  }
  if (fautes.length > 0) return { ok: false, fautes };

  const label: Record<string, string> = {};
  if (s.fr.trim()) label.fr = s.fr.trim();
  if (s.en.trim()) label.en = s.en.trim();
  const corps: Record<string, unknown> = { code: s.code.trim(), label, type_regle: s.type_regle, severity: s.severity, valid_from: s.valid_from };
  const action: Record<string, string> = {};
  if (s.action_fr.trim()) action.fr = s.action_fr.trim();
  if (s.action_en.trim()) action.en = s.action_en.trim();
  if (Object.keys(action).length > 0) corps.action_corrective = action;
  if (s.manuel) corps.manuel = true;
  else corps.expression = { type_regle: s.type_regle, conditions };
  return { ok: true, corps };
}
