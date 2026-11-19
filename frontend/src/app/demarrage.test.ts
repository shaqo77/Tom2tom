import { QueryClient } from "@tanstack/react-query";

import { demarrerServeur, unCompte } from "../test/serveur";
import { nettoyer } from "../test/monter";
import { langueDeDepart } from "./demarrage";

afterEach(nettoyer);
const client = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

describe("langue au démarrage", () => {
  it("reprend la langue enregistrée sur le compte, même si le navigateur est dans une autre", async () => {
    const serveur = demarrerServeur([unCompte("amina", { langue: "en" })]);
    serveur.ouvrirSession("amina");
    expect(await langueDeDepart(client(), { navigateur: "fr" })).toBe("en");
  });

  it("sans session, suit le navigateur", async () => {
    demarrerServeur([unCompte("amina", { langue: "en" })]);
    expect(await langueDeDepart(client(), { navigateur: "fr" })).toBe("fr");
  });

  it("une langue demandée explicitement dans l'adresse l'emporte (développement)", async () => {
    const serveur = demarrerServeur([unCompte("amina", { langue: "en" })]);
    serveur.ouvrirSession("amina");
    expect(await langueDeDepart(client(), { navigateur: "fr", demandee: "pseudo" })).toBe("pseudo");
  });

  it("serveur injoignable : on démarre quand même, dans la langue du navigateur", async () => {
    const serveur = demarrerServeur([unCompte("amina")]);
    serveur.panneReseau = true;
    expect(await langueDeDepart(client(), { navigateur: "en" })).toBe("en");
  });

  it("ne fait qu'une requête : « moi » reste en mémoire pour les gardes de route", async () => {
    const serveur = demarrerServeur([unCompte("amina")]);
    serveur.ouvrirSession("amina");
    const requetes = client();
    await langueDeDepart(requetes, { navigateur: "fr" });
    expect(requetes.getQueryData(["moi"])).toMatchObject({ identifiant: "amina" });
    expect(serveur.appels.filter((a) => a.url.includes("/session/moi/"))).toHaveLength(1);
  });
});
