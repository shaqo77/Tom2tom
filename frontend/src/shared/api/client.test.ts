import { ErreurApi, appeler, definirLangueApi, surNonAuthentifie } from "./client";

type Appel = { url: string; init: RequestInit };
let appels: Appel[];

function simuler(...reponses: (Response | Error)[]) {
  appels = [];
  const file = [...reponses];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      appels.push({ url, init });
      const suivante = file.shift();
      if (!suivante) throw new Error("appel non prévu");
      if (suivante instanceof Error) throw suivante;
      return suivante;
    }),
  );
}

const json = (corps: unknown, statut = 200) =>
  new Response(JSON.stringify(corps), { status: statut, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
  definirLangueApi("fr");
  surNonAuthentifie(null);
});
afterEach(() => vi.unstubAllGlobals());

describe("requêtes", () => {
  it("lit en GET sous /api/v1, avec la session et la langue, sans jeton CSRF", async () => {
    simuler(json({ bonjour: "monde" }));
    expect(await appeler("/session/moi/")).toEqual({ bonjour: "monde" });
    const { url, init } = appels[0] as Appel;
    expect(url).toBe("/api/v1/session/moi/");
    expect(init.credentials).toBe("same-origin");
    const entetes = new Headers(init.headers);
    expect(entetes.get("Accept-Language")).toBe("fr");
    expect(entetes.get("X-CSRFToken")).toBeNull();
  });

  it("demande les messages dans la langue choisie par l'utilisateur", async () => {
    definirLangueApi("en");
    simuler(json({}));
    await appeler("/session/moi/");
    expect(new Headers((appels[0] as Appel).init.headers).get("Accept-Language")).toBe("en");
  });

  it("joint le jeton CSRF du cookie à toute requête qui modifie", async () => {
    document.cookie = "csrftoken=jeton-abc; path=/";
    simuler(json({ ok: true }));
    await appeler("/session/connexion/", { methode: "POST", corps: { identifiant: "a" } });
    const { init } = appels[0] as Appel;
    expect(new Headers(init.headers).get("X-CSRFToken")).toBe("jeton-abc");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(init.body).toBe('{"identifiant":"a"}');
  });

  it("demande d'abord le jeton quand le cookie manque, puis rejoue la requête avec lui", async () => {
    appels = [];
    const reponses = [json({ csrf: "frais" }), json({ ok: true })];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit) => {
        appels.push({ url, init });
        if (url.endsWith("/session/csrf/")) document.cookie = "csrftoken=frais; path=/"; // le navigateur
        return reponses.shift() as Response;
      }),
    );
    await appeler("/session/deconnexion/", { methode: "POST" });
    expect(appels.map((a) => a.url)).toEqual(["/api/v1/session/csrf/", "/api/v1/session/deconnexion/"]);
    expect(new Headers((appels[1] as Appel).init.headers).get("X-CSRFToken")).toBe("frais");
  });

  it("rend undefined pour une réponse sans contenu", async () => {
    simuler(new Response(null, { status: 204 }));
    document.cookie = "csrftoken=x; path=/";
    expect(await appeler("/session/deconnexion/", { methode: "POST" })).toBeUndefined();
  });
});

describe("erreurs", () => {
  it("transforme {code, message} du serveur en ErreurApi", async () => {
    simuler(json({ code: "REGLE_INVALIDE", message: "Montant invalide" }, 422));
    const erreur = await appeler("/x/").catch((e) => e);
    expect(erreur).toBeInstanceOf(ErreurApi);
    expect(erreur).toMatchObject({ statut: 422, code: "REGLE_INVALIDE", message: "Montant invalide" });
  });

  it("n'expose jamais une page d'erreur HTML : un code stable, pas le contenu", async () => {
    simuler(new Response("<html>Traceback secret</html>", { status: 500 }));
    const erreur = (await appeler("/x/").catch((e) => e)) as ErreurApi;
    expect(erreur).toMatchObject({ statut: 500, code: "ERREUR_SERVEUR" });
    expect(erreur.message).not.toContain("Traceback");
  });

  it("distingue une coupure réseau d'une erreur du serveur", async () => {
    simuler(new TypeError("Failed to fetch"));
    expect(await appeler("/x/").catch((e) => e)).toMatchObject({ statut: 0, code: "ERREUR_RESEAU" });
  });

  it("signale une session perdue (401 NON_AUTHENTIFIE) à l'application, une seule fois", async () => {
    const perdue = vi.fn();
    surNonAuthentifie(perdue);
    simuler(json({ code: "NON_AUTHENTIFIE", message: "Connexion requise" }, 401));
    await appeler("/session/moi/").catch(() => undefined);
    expect(perdue).toHaveBeenCalledTimes(1);
  });

  it("ne déclenche pas « session expirée » pour une lecture dont le 401 est attendu", async () => {
    const perdue = vi.fn();
    surNonAuthentifie(perdue);
    simuler(json({ code: "NON_AUTHENTIFIE", message: "Connexion requise" }, 401));
    await appeler("/session/moi/", { sansAlerteSession: true }).catch(() => undefined);
    expect(perdue).not.toHaveBeenCalled();
  });

  it("ne confond pas un mauvais mot de passe avec une session perdue", async () => {
    const perdue = vi.fn();
    surNonAuthentifie(perdue);
    document.cookie = "csrftoken=x; path=/";
    simuler(json({ code: "IDENTIFIANTS_INVALIDES", message: "Incorrect" }, 401));
    await appeler("/session/connexion/", { methode: "POST", corps: {} }).catch(() => undefined);
    expect(perdue).not.toHaveBeenCalled();
  });
});
