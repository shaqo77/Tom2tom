import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { appliquerLangue } from "../i18n";
import { violations } from "../test/accessibilite";
import { creerRouteur } from "./routes";

async function afficher(chemin: string) {
  const routeur = creerRouteur({ history: createMemoryHistory({ initialEntries: [chemin] }) });
  const rendu = render(<RouterProvider router={routeur} />);
  await screen.findByRole("main");
  return rendu;
}

beforeEach(async () => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  await appliquerLangue("fr");
});

describe("navigation", () => {
  it("l'accueil porte le titre de l'application et mène au guide de style", async () => {
    await afficher("/");
    expect(screen.getByRole("heading", { level: 1, name: "SIGF" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Voir le guide de style" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Guide de style" })).toBeInTheDocument();
  });

  it("le lien d'évitement mène au contenu", async () => {
    await afficher("/");
    expect(screen.getByRole("link", { name: "Aller au contenu" })).toHaveAttribute("href", "#contenu");
    expect(screen.getByRole("main")).toHaveAttribute("id", "contenu");
  });

  it("chaque page a un seul titre de premier niveau", async () => {
    for (const chemin of ["/", "/conception"]) {
      const { unmount } = await afficher(chemin);
      expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
      unmount();
    }
  });
});

describe("accessibilité", () => {
  for (const chemin of ["/", "/conception"]) {
    it(`la page ${chemin} n'a aucune violation détectable`, async () => {
      const { container } = await afficher(chemin);
      expect(await violations(container)).toEqual([]);
    });
  }
});

describe("langue et thème", () => {
  it("changer de langue traduit toute la page et le sens d'écriture suit", async () => {
    await afficher("/conception");
    await userEvent.selectOptions(screen.getByLabelText("Langue"), "English");
    expect(await screen.findByRole("heading", { level: 1, name: "Style guide" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");
    expect(screen.getByLabelText("Language")).toBeInTheDocument();
  });

  it("le sélecteur de langue nomme chaque langue dans sa propre langue", async () => {
    await afficher("/");
    const choix = screen.getByLabelText("Langue");
    expect(choix).toHaveDisplayValue("Français");
    expect([...(choix as HTMLSelectElement).options].map((o) => o.text)).toEqual(
      expect.arrayContaining(["Français", "English"]),
    );
  });

  it("la pseudo-langue droite-à-gauche inverse le sens d'écriture du document", async () => {
    await afficher("/");
    await userEvent.selectOptions(screen.getByLabelText("Langue"), "Pseudo (RTL)");
    await waitFor(() => expect(document.documentElement.dir).toBe("rtl"));
  });

  it("choisir le thème sombre le pose sur le document et le retient", async () => {
    await afficher("/");
    await userEvent.selectOptions(screen.getByLabelText("Thème"), "sombre");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(window.localStorage.getItem("sigf.theme")).toBe("sombre");
  });
});
