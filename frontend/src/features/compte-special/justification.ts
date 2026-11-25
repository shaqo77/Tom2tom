import { lireSaisie } from "../../shared/money/montant";

export interface Faute {
  cle: string;
}
export type Resultat = { ok: true; corps: Record<string, unknown> } | { ok: false; fautes: Faute[] };

/**
 * Le corps d'une justification soumise à la Banque. La demande est obligatoire ; le montant et la date sont facultatifs
 * (le serveur reprend alors ses valeurs par défaut). Un montant s'envoie en chaîne canonique, jamais en nombre.
 */
export function construireJustification(demande: string, montant: string, date: string, langue: string): Resultat {
  const fautes: Faute[] = [];
  if (!demande) fautes.push({ cle: "special.faute.demande" });
  let valeur: string | null = null;
  if (montant.trim()) {
    valeur = lireSaisie(montant, langue);
    if (valeur === null || valeur.startsWith("-") || !/[1-9]/.test(valeur)) fautes.push({ cle: "special.faute.montant" });
  }
  if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) fautes.push({ cle: "special.faute.date" });
  if (fautes.length > 0) return { ok: false, fautes };
  const corps: Record<string, unknown> = { demande };
  if (valeur !== null) corps.montant = valeur;
  if (date) corps.date_soumission = date;
  return { ok: true, corps };
}
