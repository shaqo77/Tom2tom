import { ErreurApi, appeler } from "../shared/api/client";
import { nettoyer } from "./monter";
import { demarrerServeur, reponseFausse, unCompte } from "./serveur";

afterEach(nettoyer);

function serveurConnecte() {
  const serveur = demarrerServeur([unCompte("amina")]);
  serveur.ouvrirSession("amina");
  return serveur;
}

describe("le faux serveur répond aux écritures", () => {
  it("une route POST répond avec le corps voulu et enregistre l'appel avec son corps", async () => {
    const serveur = serveurConnecte();
    serveur.routes.push({
      methode: "POST",
      motif: /^\/choses\/$/,
      reponse: (_t, _r, corps) => ({ recu: corps, id: "c1" }),
    });
    const retour = await appeler<{ id: string; recu: unknown }>("/choses/", { methode: "POST", corps: { nom: "x" } });
    expect(retour).toEqual({ id: "c1", recu: { nom: "x" } });
    expect(serveur.appels.at(-1)).toEqual({ methode: "POST", url: "/api/v1/choses/", corps: { nom: "x" } });
  });

  it("PUT, PATCH et DELETE se déclarent de la même façon", async () => {
    const serveur = serveurConnecte();
    for (const methode of ["PUT", "PATCH", "DELETE"] as const) {
      serveur.routes.push({ methode, motif: /^\/choses\/c1\/$/, reponse: () => ({ methode }) });
    }
    for (const methode of ["PUT", "PATCH", "DELETE"] as const) {
      expect(await appeler("/choses/c1/", { methode, corps: {} })).toEqual({ methode });
    }
  });

  it("une route peut répondre un statut précis avec le format {code, message} du serveur", async () => {
    const serveur = serveurConnecte();
    serveur.routes.push({
      methode: "POST",
      motif: /^\/choses\/$/,
      reponse: () => reponseFausse(422, { code: "REGLE_INVALIDE", message: "Taux invalide" }),
    });
    const erreur = await appeler("/choses/", { methode: "POST", corps: {} }).catch((e: unknown) => e);
    expect(erreur).toBeInstanceOf(ErreurApi);
    expect(erreur).toMatchObject({ statut: 422, code: "REGLE_INVALIDE", message: "Taux invalide" });
  });

  it("un statut 204 répond sans corps", async () => {
    const serveur = serveurConnecte();
    serveur.routes.push({ methode: "DELETE", motif: /^\/choses\/c1\/$/, reponse: () => reponseFausse(204) });
    expect(await appeler("/choses/c1/", { methode: "DELETE" })).toBeUndefined();
  });

  it("sans jeton CSRF, une écriture est refusée en 403 CSRF_INVALIDE", async () => {
    const serveur = serveurConnecte();
    serveur.routes.push({ methode: "POST", motif: /^\/choses\/$/, reponse: () => ({}) });
    const reponse = await fetch("/api/v1/choses/", { method: "POST", body: "{}" });
    expect(reponse.status).toBe(403);
    expect(((await reponse.json()) as { code: string }).code).toBe("CSRF_INVALIDE");
    expect(serveur.appels.at(-1)?.methode).toBe("POST");
  });

  it("une session perdue répond 401 NON_AUTHENTIFIE, lecture comme écriture", async () => {
    const serveur = serveurConnecte();
    serveur.routes.push(
      { motif: /^\/choses\/$/, reponse: () => ({}) },
      { methode: "POST", motif: /^\/choses\/$/, reponse: () => ({}) },
    );
    serveur.expirer();
    for (const methode of ["GET", "POST"] as const) {
      const erreur = await appeler("/choses/", { methode, corps: {}, sansAlerteSession: true }).catch((e: unknown) => e);
      expect(erreur).toMatchObject({ statut: 401, code: "NON_AUTHENTIFIE" });
    }
  });

  it("une route inconnue répond 404, et une route GET ne répond pas à un POST", async () => {
    const serveur = serveurConnecte();
    serveur.routes.push({ motif: /^\/choses\/$/, reponse: () => ({ ok: true }) });
    expect(await appeler("/choses/")).toEqual({ ok: true }); // GET par défaut : comportement inchangé
    for (const [methode, chemin] of [["POST", "/choses/"], ["GET", "/inconnue/"]] as const) {
      const erreur = await appeler(chemin, { methode, corps: {} }).catch((e: unknown) => e);
      expect(erreur).toMatchObject({ statut: 404 });
    }
  });

  it("la recherche d'adresse est passée à la route", async () => {
    const serveur = serveurConnecte();
    serveur.routes.push({ motif: /^\/choses\/$/, reponse: (_t, recherche) => ({ avec: recherche.get("avec") }) });
    expect(await appeler("/choses/?avec=3")).toEqual({ avec: "3" });
  });
});
