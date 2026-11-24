import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";

afterEach(nettoyer);

const ACTUEL = "motdepasse-solide";
const NOUVEAU = "un-autre-mot-de-passe-solide";

async function ouvrir() {
  const m = await monter("/mot-de-passe", { connecteComme: "amina" });
  await screen.findByRole("heading", { level: 1, name: "Changer de mot de passe" });
  return m;
}
const envois = (m: Awaited<ReturnType<typeof ouvrir>>) =>
  m.serveur.appels.filter((a) => a.url.includes("/session/mot-de-passe/"));

async function remplir(actuel: string, nouveau: string, confirmation: string) {
  if (actuel) await userEvent.type(screen.getByLabelText("Mot de passe actuel"), actuel);
  if (nouveau) await userEvent.type(screen.getByLabelText("Nouveau mot de passe"), nouveau);
  if (confirmation) await userEvent.type(screen.getByLabelText("Confirmer le nouveau mot de passe"), confirmation);
}
const valider = () => userEvent.click(screen.getByRole("button", { name: "Changer le mot de passe" }));

describe("changer son mot de passe", () => {
  it("refuse des champs vides avant tout envoi et place le curseur sur le premier", async () => {
    const m = await ouvrir();
    await valider();
    expect(screen.getByText("Saisissez votre mot de passe actuel.")).toBeInTheDocument();
    expect(screen.getByText("Saisissez le nouveau mot de passe.")).toBeInTheDocument();
    expect(screen.getByLabelText("Mot de passe actuel")).toHaveFocus();
    expect(envois(m)).toHaveLength(0);
  });

  it("refuse une confirmation différente, sans rien envoyer", async () => {
    const m = await ouvrir();
    await remplir(ACTUEL, NOUVEAU, `${NOUVEAU}x`);
    await valider();
    expect(screen.getByText("La confirmation est différente du nouveau mot de passe.")).toBeInTheDocument();
    expect(screen.getByLabelText("Confirmer le nouveau mot de passe")).toHaveFocus();
    expect(envois(m)).toHaveLength(0);
  });

  it("affiche le message du serveur quand le mot de passe actuel est faux, et vide les champs secrets", async () => {
    const m = await ouvrir();
    await remplir("faux-mot-de-passe", NOUVEAU, NOUVEAU);
    await valider();
    expect(await screen.findByRole("alert")).toHaveTextContent("Le mot de passe actuel est incorrect.");
    expect(screen.getByLabelText("Mot de passe actuel")).toHaveValue("");
    expect(screen.getByLabelText("Nouveau mot de passe")).toHaveValue("");
    expect(envois(m)).toHaveLength(1);
  });

  it("affiche le refus de robustesse du serveur sans inventer de règle côté écran", async () => {
    await ouvrir();
    await remplir(ACTUEL, "court", "court");
    await valider();
    expect(await screen.findByRole("alert")).toHaveTextContent("Mot de passe refusé");
  });

  it("confirme le succès, vide les champs et envoie les bons champs", async () => {
    const m = await ouvrir();
    await remplir(ACTUEL, NOUVEAU, NOUVEAU);
    await valider();
    expect(await screen.findByText("Votre mot de passe a été changé.")).toBeInTheDocument();
    expect(screen.getByLabelText("Mot de passe actuel")).toHaveValue("");
    expect(screen.getByLabelText("Nouveau mot de passe")).toHaveValue("");
    expect(envois(m)[0]?.corps).toEqual({ actuel: ACTUEL, nouveau: NOUVEAU });
  });

  it("désactive le bouton pendant l'envoi pour éviter un double envoi", async () => {
    const m = await ouvrir();
    let liberer: () => void = () => {};
    m.serveur.retard = new Promise<void>((resolu) => {
      liberer = resolu;
    });
    await remplir(ACTUEL, NOUVEAU, NOUVEAU);
    await valider();
    await waitFor(() => expect(screen.getByRole("button", { name: "Changer le mot de passe" })).toBeDisabled());
    liberer();
    await screen.findByText("Votre mot de passe a été changé.");
    expect(envois(m)).toHaveLength(1);
  });

  it("est accessible", async () => {
    const m = await ouvrir();
    expect(await violations(m.rendu.container)).toEqual([]);
  });

  it("sans session, renvoie à la connexion", async () => {
    await monter("/mot-de-passe");
    expect(await screen.findByRole("heading", { level: 1, name: "Connexion" })).toBeInTheDocument();
  });
});
