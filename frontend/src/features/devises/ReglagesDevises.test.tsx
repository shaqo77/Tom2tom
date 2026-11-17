import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";
import { projet, unCompte } from "../../test/serveur";

afterEach(nettoyer);

// Une fabrique : le faux serveur modifie le compte (droits retirés dans un test), il ne doit pas fuir.
const unAdmin = () =>
  unCompte("amina", { projets: [projet("P1", ["consulter", "parametrer"]), projet("P2", ["consulter"])] });

const version = (surcharge: Record<string, unknown> = {}) => ({
  version: 1,
  project_id: null,
  devise_reference: null,
  devises_autorisees: null,
  type_taux: null,
  valid_from: "2026-01-01",
  valid_to: null,
  motif: "",
  ...surcharge,
});

describe("réglages de devises", () => {
  it("affiche « non paramétré » quand rien n'est réglé, jamais une valeur inventée", async () => {
    await monter("/parametres-devises", { comptes: [unAdmin()], connecteComme: "amina" });
    expect(await screen.findByRole("heading", { name: /En vigueur le/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("Non paramétré").length).toBeGreaterThanOrEqual(3));
    expect(screen.getByText("Aucune restriction")).toBeInTheDocument();
    expect(screen.queryByText("DJF", { selector: "strong" })).not.toBeInTheDocument();
  });

  it("montre la provenance : hérité de l'organisation, propre au projet", async () => {
    const m = await monter("/parametres-devises", { comptes: [unAdmin()], connecteComme: "amina" });
    m.serveur.reglages.org = [version({ devise_reference: "USD", devises_autorisees: ["DJF", "USD"] })];
    m.serveur.reglages["id-P1"] = [version({ project_id: "id-P1", type_taux: "officiel" })];
    await m.routeur.navigate({ to: "/parametres-devises", search: { portee: "id-P1" } });
    expect((await screen.findAllByText("Hérité de l'organisation", {}, { timeout: 3000 })).length).toBe(2);
    expect(screen.getByText("Propre au projet")).toBeInTheDocument();
    expect(screen.getByText("DJF, USD")).toBeInTheDocument();
    expect(screen.getByText("Taux officiel", { selector: "strong" })).toBeInTheDocument();
  });

  it("pose une nouvelle version et la voit dans l'historique", async () => {
    const m = await monter("/parametres-devises", { comptes: [unAdmin()], connecteComme: "amina" });
    const u = userEvent.setup();
    await u.selectOptions(await screen.findByLabelText("Devise de référence"), "USD");
    await u.selectOptions(screen.getByLabelText("Type de taux"), "budget");
    await u.click(screen.getByRole("checkbox", { name: "Restreindre les devises utilisables" }));
    await u.click(screen.getByRole("checkbox", { name: "DJF" }));
    await u.click(screen.getByRole("checkbox", { name: "USD" }));
    await u.type(screen.getByLabelText("Motif"), "Départ");
    await u.click(screen.getByRole("button", { name: "Enregistrer la nouvelle version" }));
    expect(await screen.findByText("La nouvelle version est enregistrée.")).toBeInTheDocument();
    const envoi = m.serveur.appels.find((a) => a.methode === "POST" && a.url.endsWith("/parametres-devises/"));
    expect(envoi?.corps).toMatchObject({
      devise_reference: "USD",
      type_taux: "budget",
      devises_autorisees: ["DJF", "USD"],
      motif: "Départ",
    });
    const tableau = await screen.findByRole("table");
    expect(within(tableau).getByText("En cours")).toBeInTheDocument();
    expect(within(tableau).getByText("DJF, USD")).toBeInTheDocument();
  });

  it("refuse en local un formulaire vide, sans appeler le serveur", async () => {
    const m = await monter("/parametres-devises", { comptes: [unAdmin()], connecteComme: "amina" });
    const u = userEvent.setup();
    await u.click(await screen.findByRole("button", { name: "Enregistrer la nouvelle version" }));
    expect(await screen.findByText(/Choisissez au moins/)).toBeInTheDocument();
    expect(m.serveur.appels.some((a) => a.methode === "POST" && a.url.includes("parametres-devises"))).toBe(false);
  });

  it("affiche le refus du serveur tel quel", async () => {
    const m = await monter("/parametres-devises", { comptes: [unAdmin()], connecteComme: "amina" });
    const u = userEvent.setup();
    await u.selectOptions(await screen.findByLabelText("Type de taux"), "budget");
    m.serveur.reglages.org = [];
    // le serveur refuse : plus aucune habilitation
    m.serveur.connecte()!.moi.projets.forEach((p) => (p.operations = ["consulter"]));
    await u.click(screen.getByRole("button", { name: "Enregistrer la nouvelle version" }));
    expect(await screen.findByText("Refusé")).toBeInTheDocument();
  });

  it("la lecture seule masque le formulaire pour qui n'a pas « Paramétrer »", async () => {
    const lecteur = unCompte("luc", { projets: [projet("P1", ["consulter"])] });
    await monter("/parametres-devises", { comptes: [lecteur], connecteComme: "luc" });
    expect(await screen.findByText(/demande l'habilitation/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enregistrer la nouvelle version" })).not.toBeInTheDocument();
  });

  it("la portée « projet » sans droit sur ce projet est en lecture seule, même si on paramètre ailleurs", async () => {
    await monter("/parametres-devises?portee=id-P2", { comptes: [unAdmin()], connecteComme: "amina" });
    expect(await screen.findByText(/demande l'habilitation/)).toBeInTheDocument();
  });

  it("un projet inconnu est signalé", async () => {
    await monter("/parametres-devises?portee=id-ZZ", { comptes: [unAdmin()], connecteComme: "amina" });
    expect(await screen.findByText(/n.existe pas, ou vous/)).toBeInTheDocument();
  });

  it("le formulaire reprend la version ouverte (une nouvelle version remplace l'ancienne)", async () => {
    const m = await monter("/", { comptes: [unAdmin()], connecteComme: "amina" });
    m.serveur.reglages.org = [version({ devise_reference: "EUR", type_taux: "cloture", devises_autorisees: ["DJF", "EUR"] })];
    await m.routeur.navigate({ to: "/parametres-devises", search: {} });
    await waitFor(() => expect(screen.getByLabelText("Devise de référence")).toHaveValue("EUR"));
    expect(screen.getByLabelText("Type de taux")).toHaveValue("cloture");
    expect(screen.getByRole("checkbox", { name: "Restreindre les devises utilisables" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "DJF" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "USD" })).not.toBeChecked();
  });

  it("n'affiche le formulaire qu'une fois l'historique chargé, pour qu'il parte des bonnes valeurs", async () => {
    const m = await monter("/", { comptes: [unAdmin()], connecteComme: "amina" });
    m.serveur.reglages.org = [version({ devise_reference: "EUR" })];
    let ouvrir!: () => void;
    m.serveur.retard = new Promise<void>((r) => (ouvrir = r));
    await m.routeur.navigate({ to: "/parametres-devises", search: {} });
    await screen.findByRole("heading", { name: "Nouvelle version" });
    // le catalogue (non retardé) est arrivé, mais l'historique non : pas encore de formulaire
    await waitFor(() => expect(m.serveur.appels.some((x) => x.url.endsWith("/devises/"))).toBe(true));
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("button", { name: "Enregistrer la nouvelle version" })).not.toBeInTheDocument();
    ouvrir();
    await waitFor(() => expect(screen.getByLabelText("Devise de référence")).toHaveValue("EUR"));
  });

  it("refuse en local une restriction sans aucune devise cochée", async () => {
    const m = await monter("/parametres-devises", { comptes: [unAdmin()], connecteComme: "amina" });
    const u = userEvent.setup();
    await u.selectOptions(await screen.findByLabelText("Type de taux"), "budget");
    await u.click(screen.getByRole("checkbox", { name: "Restreindre les devises utilisables" }));
    await u.click(screen.getByRole("button", { name: "Enregistrer la nouvelle version" }));
    expect(await screen.findByText(/Cochez au moins une devise/)).toBeInTheDocument();
    expect(m.serveur.appels.some((a) => a.methode === "POST" && a.url.includes("parametres-devises"))).toBe(false);
  });

  it("au niveau d'un projet, une valeur vide s'appelle « hériter »", async () => {
    await monter("/parametres-devises?portee=id-P1", { comptes: [unAdmin()], connecteComme: "amina" });
    const liste = await screen.findByLabelText("Type de taux");
    expect(within(liste).getByRole("option", { name: "Hériter du niveau au-dessus" })).toBeInTheDocument();
  });

  it("à l'organisation, une valeur vide s'appelle « non paramétré » (il n'y a rien au-dessus)", async () => {
    await monter("/parametres-devises", { comptes: [unAdmin()], connecteComme: "amina" });
    const liste = await screen.findByLabelText("Type de taux");
    expect(within(liste).queryByRole("option", { name: "Hériter du niveau au-dessus" })).not.toBeInTheDocument();
    expect(within(liste).getByRole("option", { name: "Non paramétré" })).toBeInTheDocument();
  });

  it("est accessible", async () => {
    const m = await monter("/parametres-devises", { comptes: [unAdmin()], connecteComme: "amina" });
    await screen.findByRole("button", { name: "Enregistrer la nouvelle version" });
    expect(await violations(m.rendu.container)).toEqual([]);
  });
});
