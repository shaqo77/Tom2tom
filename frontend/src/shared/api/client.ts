/**
 * Le client de l'API du SIGF. Toutes les requêtes passent ici : session par cookie, jeton CSRF
 * sur tout ce qui modifie, erreurs `{code, message}` du serveur rendues en `ErreurApi`.
 *
 * Les montants arrivent en CHAÎNES et le restent : ce client ne convertit rien.
 */

const BASE = "/api/v1";
const MODIFIE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ErreurApi extends Error {
  readonly statut: number;
  readonly code: string;

  constructor(statut: number, code: string, message: string) {
    super(message);
    this.name = "ErreurApi";
    this.statut = statut;
    this.code = code;
  }
}

export interface OptionsAppel {
  methode?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  corps?: unknown;
  signal?: AbortSignal;
  /** Interne : la requête a déjà été rejouée une fois avec un jeton CSRF frais. */
  rejouee?: boolean;
  /** Un 401 attendu (« suis-je connecté ? ») ne doit pas déclencher « votre session a expiré ». */
  sansAlerteSession?: boolean;
}

let langue = "fr";
let sessionPerdue: (() => void) | null = null;

/** La langue demandée au serveur (messages d'erreur, libellés). */
export function definirLangueApi(code: string): void {
  langue = code;
}

/** L'application s'abonne ici pour ramener l'utilisateur à la connexion quand sa session tombe. */
export function surNonAuthentifie(rappel: (() => void) | null): void {
  sessionPerdue = rappel;
}

function jetonDuCookie(): string | null {
  const trouve = document.cookie.split("; ").find((c) => c.startsWith("csrftoken="));
  const valeur = trouve?.slice("csrftoken=".length);
  return valeur ? decodeURIComponent(valeur) : null;
}

async function assurerJeton(): Promise<string> {
  const existant = jetonDuCookie();
  if (existant) return existant;
  await appeler("/session/csrf/"); // le serveur pose le cookie dans la réponse
  const apres = jetonDuCookie();
  if (!apres) throw new ErreurApi(0, "ERREUR_RESEAU", "Jeton CSRF indisponible");
  return apres;
}

async function lireCorps(reponse: Response): Promise<unknown> {
  const texte = await reponse.text();
  if (!texte) return undefined;
  try {
    return JSON.parse(texte) as unknown;
  } catch {
    return undefined; // ni du JSON, ni lisible : on ne montre jamais une page d'erreur brute
  }
}

export async function appeler<T = unknown>(chemin: string, options: OptionsAppel = {}): Promise<T> {
  const methode = options.methode ?? "GET";
  const entetes = new Headers({ Accept: "application/json", "Accept-Language": langue });
  if (MODIFIE.has(methode)) entetes.set("X-CSRFToken", await assurerJeton());
  const init: RequestInit = { method: methode, headers: entetes, credentials: "same-origin" };
  if (options.corps !== undefined) {
    entetes.set("Content-Type", "application/json");
    init.body = JSON.stringify(options.corps);
  }
  if (options.signal) init.signal = options.signal;

  let reponse: Response;
  try {
    reponse = await fetch(`${BASE}${chemin}`, init);
  } catch {
    throw new ErreurApi(0, "ERREUR_RESEAU", "Le serveur est injoignable.");
  }

  const corps = await lireCorps(reponse);
  if (reponse.ok) return corps as T;

  const donnees = (corps ?? {}) as { code?: unknown; message?: unknown };
  const code = typeof donnees.code === "string" ? donnees.code : "ERREUR_SERVEUR";
  const message =
    typeof donnees.message === "string" ? donnees.message : `Erreur du serveur (${reponse.status}).`;
  if (reponse.status === 403 && code === "CSRF_INVALIDE" && MODIFIE.has(methode) && !options.rejouee) {
    // Jeton périmé (cookie effacé, connexion faite dans un autre onglet) : on en demande un frais,
    // une seule fois, puis on rejoue. Si cela échoue encore, l'erreur est montrée telle quelle.
    await appeler("/session/csrf/");
    return appeler<T>(chemin, { ...options, rejouee: true });
  }
  if (reponse.status === 401 && code === "NON_AUTHENTIFIE" && !options.sansAlerteSession) sessionPerdue?.();
  throw new ErreurApi(reponse.status, code, message);
}

/** Le message du serveur (déjà dans la langue de la requête) pour un refus métier ; `null` pour une panne. */
export function messageDuServeur(erreur: unknown): string | null {
  return erreur instanceof ErreurApi && erreur.statut < 500 ? erreur.message : null;
}
