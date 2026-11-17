/**
 * Les montants du SIGF : des CHAÎNES décimales, jamais des nombres JavaScript.
 *
 * Le serveur envoie `"1250.0000"` ; un `Number` perdrait des chiffres et additionnerait mal
 * (0,1 + 0,2). Tout passe par `decimal.js`. L'arrondi est celui du serveur : à la moitié, en
 * s'éloignant de zéro (`ROUND_HALF_UP`).
 */
import Decimal from "decimal.js";

export class MontantInvalide extends Error {
  constructor(valeur: string) {
    super(`Montant invalide : « ${valeur} »`);
    this.name = "MontantInvalide";
  }
}

const Exact = Decimal.clone({ precision: 60, rounding: Decimal.ROUND_HALF_UP, toExpNeg: -60, toExpPos: 60 });
const DECIMAL = /^-?\d+(\.\d+)?$/;

export function lire(valeur: string): Decimal {
  if (typeof valeur !== "string" || !DECIMAL.test(valeur)) throw new MontantInvalide(String(valeur));
  return new Exact(valeur);
}

export function additionner(...valeurs: string[]): string {
  return valeurs.reduce((total, v) => total.plus(lire(v)), new Exact(0)).toFixed();
}

export function soustraire(a: string, b: string): string {
  return lire(a).minus(lire(b)).toFixed();
}

export function comparer(a: string, b: string): number {
  return lire(a).comparedTo(lire(b));
}

export function estNul(valeur: string): boolean {
  return lire(valeur).isZero();
}

function separateurs(langue: string): { decimal: string; groupe: string } {
  const parties = new Intl.NumberFormat(langue).formatToParts(1000.5);
  return {
    decimal: parties.find((p) => p.type === "decimal")?.value ?? ".",
    groupe: parties.find((p) => p.type === "group")?.value ?? ",",
  };
}

/** `"1250.5"` → `"1 250,50"` (fr) ou `"1,250.50"` (en), sans jamais passer par un nombre flottant. */
export function formater(valeur: string, langue: string, decimales: number): string {
  const arrondi = lire(valeur).toDecimalPlaces(decimales, Decimal.ROUND_HALF_UP);
  const negatif = arrondi.isNegative() && !arrondi.isZero();
  const [entier = "0", fraction = ""] = arrondi.abs().toFixed(decimales).split(".");
  const { decimal } = separateurs(langue);
  const groupe = new Intl.NumberFormat(langue).format(BigInt(entier)); // BigInt : exact
  return `${negatif ? "-" : ""}${groupe}${decimales > 0 ? decimal + fraction : ""}`;
}

/**
 * Ce que tape l'utilisateur → une chaîne décimale canonique, ou `null` si le texte est invalide
 * ou ambigu. Seul le séparateur décimal de la langue est accepté : « 1.250 » en français pourrait
 * être mille deux cent cinquante ou un virgule vingt-cinq, on ne devine pas.
 */
export function lireSaisie(texte: string, langue: string): string | null {
  const { decimal } = separateurs(langue);
  const sansEspaces = texte.replace(/[\s\u00a0\u202f]/g, "");
  const groupes = langue.startsWith("en") ? "," : "";
  const net = groupes ? sansEspaces.split(groupes).join("") : sansEspaces;
  if (decimal !== "." && net.includes(".")) return null; // le point n'est pas la virgule
  if (net.split(decimal).length > 2) return null;
  const canonique = net.replace(decimal, ".");
  return DECIMAL.test(canonique) ? canonique : null;
}
