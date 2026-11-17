/**
 * Un faux serveur fidèle à `/api/v1/session/` : mêmes statuts, mêmes codes, même exigence de jeton
 * CSRF, même limitation des tentatives. Il permet de tester des parcours entiers sans réseau.
 */
import type { Moi } from "../shared/session/types";

export interface Compte {
  identifiant: string;
  motDePasse: string;
  moi: Moi;
}

export interface FauxServeur {
  appels: { methode: string; url: string; corps: unknown }[];
  /** La session tombe (comme une expiration côté serveur). */
  expirer(): void;
  panneReseau: boolean;
  panneServeur: boolean;
  connecte(): Compte | null;
  /** Ce que renvoie `GET /tableau-de-bord/` selon les paramètres demandés. */
  tableau: ((recherche: URLSearchParams) => unknown) | null;
  /** Quand défini, le serveur attend cette promesse avant de répondre au tableau de bord. */
  retard: Promise<void> | null;
  /** Ouvre directement une session (comme si la personne s'était déjà connectée). */
  ouvrirSession(identifiant: string): void;
}

const TENTATIVES_MAX = 5;

export function demarrerServeur(comptes: Compte[]): FauxServeur {
  let connecte: Compte | null = null;
  let echecs = 0;
  const serveur: FauxServeur = {
    appels: [],
    expirer: () => {
      connecte = null;
    },
    panneReseau: false,
    panneServeur: false,
    tableau: null,
    retard: null,
    connecte: () => connecte,
    ouvrirSession: (identifiant) => {
      connecte = comptes.find((c) => c.identifiant === identifiant) ?? null;
    },
  };

  const json = (corps: unknown, statut = 200, entetes: Record<string, string> = {}) =>
    new Response(JSON.stringify(corps), {
      status: statut,
      headers: { "Content-Type": "application/json", ...entetes },
    });

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const methode = (init.method ?? "GET").toUpperCase();
      const corps = init.body ? (JSON.parse(init.body as string) as Record<string, unknown>) : undefined;
      serveur.appels.push({ methode, url, corps });
      if (serveur.panneReseau) throw new TypeError("Failed to fetch");
      if (serveur.panneServeur) return new Response("<html>boom</html>", { status: 500 });

      const entetes = new Headers(init.headers);
      const chemin = url.replace("/api/v1", "");

      if (chemin === "/session/csrf/") {
        document.cookie = "csrftoken=jeton-de-test; path=/";
        return json({ csrf: "jeton-de-test" });
      }
      if (methode !== "GET" && entetes.get("X-CSRFToken") !== "jeton-de-test") {
        return json({ code: "CSRF_INVALIDE", message: "La page a expiré" }, 403);
      }
      if (chemin.startsWith("/tableau-de-bord/") && methode === "GET") {
        if (!connecte) return json({ code: "NON_AUTHENTIFIE", message: "Connexion requise" }, 401);
        const recherche = new URLSearchParams(chemin.split("?")[1] ?? "");
        if (serveur.retard) await serveur.retard;
        return serveur.tableau ? json(serveur.tableau(recherche)) : json({ code: "INTROUVABLE", message: "?" }, 404);
      }
      if (chemin === "/session/moi/" && methode === "GET") {
        return connecte
          ? json(connecte.moi)
          : json({ code: "NON_AUTHENTIFIE", message: "Connexion requise" }, 401);
      }
      if (chemin === "/session/moi/" && methode === "PATCH") {
        if (!connecte) return json({ code: "NON_AUTHENTIFIE", message: "Connexion requise" }, 401);
        connecte.moi = { ...connecte.moi, langue: String(corps?.langue) };
        return json(connecte.moi);
      }
      if (chemin === "/session/connexion/" && methode === "POST") {
        if (echecs >= TENTATIVES_MAX) {
          return json({ code: "TROP_DE_TENTATIVES", message: "Trop de tentatives" }, 429, {
            "Retry-After": "900",
          });
        }
        const trouve = comptes.find(
          (c) => c.identifiant === corps?.identifiant && c.motDePasse === corps?.mot_de_passe,
        );
        if (!trouve) {
          echecs += 1;
          return json({ code: "IDENTIFIANTS_INVALIDES", message: "Identifiant ou mot de passe incorrect." }, 401);
        }
        echecs = 0;
        connecte = trouve;
        return json(trouve.moi);
      }
      if (chemin === "/session/deconnexion/" && methode === "POST") {
        connecte = null;
        return new Response(null, { status: 204 });
      }
      return json({ code: "INTROUVABLE", message: "?" }, 404);
    }),
  );
  return serveur;
}

export function projet(code: string, operations: Moi["projets"][number]["operations"] = ["consulter"]) {
  return {
    id: `id-${code}`,
    code,
    libelle: { fr: `Projet ${code}`, en: `Project ${code}` },
    statut: "active",
    operations,
    operations_par_site: {},
  };
}

export function unCompte(
  identifiant: string,
  options: Partial<Pick<Moi, "projets" | "langue" | "organisation">> = {},
): Compte {
  return {
    identifiant,
    motDePasse: "motdepasse-solide",
    moi: {
      id: `u-${identifiant}`,
      identifiant,
      nom_complet: `${identifiant[0]?.toUpperCase()}${identifiant.slice(1)} Test`,
      langue: options.langue ?? "fr",
      organisation:
        options.organisation === undefined
          ? { id: "o1", code: "ORG-A", raison_sociale: "Organisation A", monnaie_tenue: "DJF", langues_actives: ["fr", "en"] }
          : options.organisation,
      projets: options.projets ?? [projet("P1", ["consulter", "saisir"])],
    },
  };
}
