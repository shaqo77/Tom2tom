import { additionner, comparer, lireSaisie } from "../../shared/money/montant";

/** Une faute de saisie : la clé d'un message `ecritures.faute.*` et ses paramètres. */
export interface Faute {
  cle: string;
  params?: Record<string, string>;
}
export type Resultat = { ok: true; corps: Record<string, unknown> } | { ok: false; fautes: Faute[] };

export interface SaisieLigne {
  compte: string;
  debit: string;
  credit: string;
  label: string;
  /** Le code d'une clé de cofinancement : le serveur ventile la ligne entre les accords. */
  cle: string;
  /** Le numéro d'un accord, pour imputer la ligne à un seul accord. */
  accord: string;
}
export interface SaisieEcriture {
  journal: string;
  date: string;
  libelle: string;
  reference: string;
  lignes: SaisieLigne[];
}

export const ligneVide = (): SaisieLigne => ({ compte: "", debit: "", credit: "", label: "", cle: "", accord: "" });
export const ecritureVide = (): SaisieEcriture => ({ journal: "", date: "", libelle: "", reference: "", lignes: [ligneVide(), ligneVide()] });

/** Un montant saisi : `""` s'il est vide, `null` s'il est illisible ou négatif, sinon la chaîne décimale canonique. Jamais un `number`. */
function montant(texte: string, langue: string): string | "" | null {
  if (!texte.trim()) return "";
  const v = lireSaisie(texte, langue);
  return v === null || v.startsWith("-") ? null : v;
}

const nul = (v: string) => !/[1-9]/.test(v);

/** Les totaux affichés pendant la saisie : seules les lignes lisibles comptent, le serveur reste l'autorité. */
export function totaux(lignes: SaisieLigne[], langue: string): { debit: string; credit: string; equilibre: boolean } {
  const somme = (champ: "debit" | "credit") =>
    additionner("0", ...lignes.map((l) => montant(l[champ], langue)).filter((v): v is string => v !== null && v !== ""));
  const debit = somme("debit");
  const credit = somme("credit");
  return { debit, credit, equilibre: comparer(debit, credit) === 0 };
}

export function construireEcriture(s: SaisieEcriture, langue: string): Resultat {
  const fautes: Faute[] = [];
  if (!s.journal.trim()) fautes.push({ cle: "ecritures.faute.journal" });
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s.date)) fautes.push({ cle: "ecritures.faute.date" });
  if (!s.libelle.trim()) fautes.push({ cle: "ecritures.faute.libelle" });
  if (s.lignes.length < 2) fautes.push({ cle: "ecritures.faute.deux_lignes" });

  const lignes: Record<string, unknown>[] = [];
  s.lignes.forEach((l, i) => {
    const n = String(i + 1);
    if (!l.compte.trim()) fautes.push({ cle: "ecritures.faute.compte", params: { n } });
    const d = montant(l.debit, langue);
    const c = montant(l.credit, langue);
    if (d === null || c === null) {
      fautes.push({ cle: "ecritures.faute.montant_illisible", params: { n } });
    } else if ((d === "" || nul(d)) && (c === "" || nul(c))) {
      fautes.push({ cle: "ecritures.faute.sans_montant", params: { n } });
    } else if (d !== "" && c !== "" && !nul(d) && !nul(c)) {
      fautes.push({ cle: "ecritures.faute.deux_montants", params: { n } });
    }
    if (l.cle && l.accord) fautes.push({ cle: "ecritures.faute.cle_et_accord", params: { n } });
    const ligne: Record<string, unknown> = { compte: l.compte.trim() };
    if (d) ligne.debit = d;
    if (c) ligne.credit = c;
    if (l.label.trim()) ligne.label = l.label.trim();
    if (l.cle) ligne.cle = l.cle;
    if (l.accord.trim()) ligne.accord = l.accord.trim();
    lignes.push(ligne);
  });

  if (fautes.length === 0) {
    const t = totaux(s.lignes, langue);
    if (!t.equilibre) fautes.push({ cle: "ecritures.faute.desequilibre", params: { debit: t.debit, credit: t.credit } });
  }
  if (fautes.length > 0) return { ok: false, fautes };
  const corps: Record<string, unknown> = { journal: s.journal.trim(), date_comptable: s.date, libelle: s.libelle.trim(), lignes };
  if (s.reference.trim()) corps.reference_piece = s.reference.trim();
  return { ok: true, corps };
}
