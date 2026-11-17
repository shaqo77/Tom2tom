import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { appeler } from "../shared/api/client";
import { violations } from "../test/accessibilite";
import { monter, nettoyer } from "../test/monter";
import { projet, unCompte } from "../test/serveur";

afterEach(nettoyer);

const chemin = (m: Awaited<ReturnType<typeof monter>>) => m.routeur.state.location.pathname;

async function seConnecter(identifiant = "amina", motDePasse = "motdepasse-solide") {
  await userEvent.type(screen.getByLabelText("Identifiant"), identifiant);
  await userEvent.type(screen.getByLabelText("Mot de passe"), motDePasse);
  await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));
}

describe("accès protégé", () => {
  it("sans session, toute page protégée renvoie à la connexion en gardant la page voulue", async () => {
    const m = await monter("/projets/id-P1");
    expect(await screen.findByRole("heading", { level: 1, name: "Connexion" })).toBeInTheDocument();
    expect(chemin(m)).toBe("/connexion");
    expect(m.routeur.state.location.search).toMatchObject({ retour: "/projets/id-P1" });
  });

  it("se connecter ramène à la page voulue", async () => {
    const m = await monter("/projets/id-P1");
    await screen.findByRole("heading", { name: "Connexion" });
    await seConnecter();
    expect(await screen.findByRole("heading", { level: 1, name: /P1/ })).toBeInTheDocument();
    expect(chemin(m)).toBe("/projets/id-P1");
  });

  it("n'accepte jamais un retour vers un autre site (redirection ouverte)", async () => {
    const m = await monter("/connexion?retour=//pirate.example/vol");
    await screen.findByRole("heading", { name: "Connexion" });
    await seConnecter();
    expect(await screen.findByRole("heading", { level: 1, name: /Bonjour/ })).toBeInTheDocument();
    expect(chemin(m)).toBe("/");
  });

  it("déjà connecté, la page de connexion renvoie à l'accueil", async () => {
    const m = await monter("/connexion", { connecteComme: "amina" });
    expect(await screen.findByRole("heading", { level: 1, name: /Bonjour/ })).toBeInTheDocument();
    expect(chemin(m)).toBe("/");
  });
});

describe("connexion", () => {
  it("réussit, accueille par le nom et propose les projets", async () => {
    await monter("/connexion");
    await screen.findByRole("heading", { name: "Connexion" });
    await seConnecter();
    expect(await screen.findByRole("heading", { level: 1, name: "Bonjour, Amina Test" })).toBeInTheDocument();
    expect(screen.getByText("Organisation A")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ouvrir le projet P1" })).toBeInTheDocument();
  });

  it("valide les champs avant tout envoi et place le curseur sur le premier à corriger", async () => {
    const m = await monter("/connexion");
    await screen.findByRole("heading", { name: "Connexion" });
    await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(screen.getByText("Saisissez votre identifiant.")).toBeInTheDocument();
    expect(screen.getByText("Saisissez votre mot de passe.")).toBeInTheDocument();
    expect(screen.getByLabelText("Identifiant")).toHaveFocus();
    expect(m.serveur.appels.some((a) => a.url.includes("connexion"))).toBe(false);
  });

  it("un mauvais mot de passe est annoncé, vidé de l'écran, et le curseur y revient", async () => {
    await monter("/connexion");
    await screen.findByRole("heading", { name: "Connexion" });
    await seConnecter("amina", "faux-mot-de-passe");
    expect(await screen.findByRole("alert")).toHaveTextContent("Identifiant ou mot de passe incorrect.");
    const champ = screen.getByLabelText("Mot de passe");
    expect(champ).toHaveValue("");
    expect(champ).toHaveFocus();
    expect(screen.getByRole("heading", { name: "Connexion" })).toBeInTheDocument();
  });

  it("ne garde jamais le mot de passe dans le stockage du navigateur", async () => {
    await monter("/connexion");
    await screen.findByRole("heading", { name: "Connexion" });
    await seConnecter("amina", "faux-mot-de-passe");
    await screen.findByRole("alert");
    const tout = JSON.stringify({ ...window.localStorage }) + JSON.stringify({ ...window.sessionStorage });
    expect(tout).not.toContain("faux-mot-de-passe");
    expect(document.cookie).not.toContain("faux-mot-de-passe");
  });

  it("dit clairement qu'il y a eu trop de tentatives, même avec le bon mot de passe", async () => {
    await monter("/connexion");
    await screen.findByRole("heading", { name: "Connexion" });
    for (let i = 0; i < 5; i++) {
      await seConnecter("amina", `faux-${i}`);
      await screen.findByRole("alert");
      await userEvent.clear(screen.getByLabelText("Identifiant"));
    }
    await seConnecter("amina", "motdepasse-solide");
    expect(await screen.findByRole("alert")).toHaveTextContent("Trop de tentatives");
  });

  it("distingue un serveur injoignable d'une erreur du serveur", async () => {
    const m = await monter("/connexion");
    await screen.findByRole("heading", { name: "Connexion" });
    m.serveur.panneReseau = true;
    await seConnecter();
    expect(await screen.findByRole("alert")).toHaveTextContent("injoignable");
    m.serveur.panneReseau = false;
    m.serveur.panneServeur = true;
    await userEvent.type(screen.getByLabelText("Mot de passe"), "motdepasse-solide"); // vidé après l'échec
    await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("côté serveur"));
  });

  it("n'affiche jamais le contenu d'une page d'erreur du serveur", async () => {
    const m = await monter("/connexion");
    await screen.findByRole("heading", { name: "Connexion" });
    m.serveur.panneServeur = true;
    await seConnecter();
    await screen.findByRole("alert");
    expect(document.body).not.toHaveTextContent("boom");
  });

  it("se soumet au clavier avec Entrée et laisse le gestionnaire de mots de passe travailler", async () => {
    await monter("/connexion");
    await screen.findByRole("heading", { name: "Connexion" });
    expect(screen.getByLabelText("Identifiant")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Mot de passe")).toHaveAttribute("autocomplete", "current-password");
    await userEvent.type(screen.getByLabelText("Identifiant"), "amina");
    await userEvent.type(screen.getByLabelText("Mot de passe"), "motdepasse-solide{Enter}");
    expect(await screen.findByRole("heading", { level: 1, name: /Bonjour/ })).toBeInTheDocument();
  });

  it("le curseur est déjà dans le champ identifiant à l'ouverture", async () => {
    await monter("/connexion");
    await screen.findByRole("heading", { name: "Connexion" });
    expect(screen.getByLabelText("Identifiant")).toHaveFocus();
  });

  it("permet de voir le mot de passe saisi, et de le recacher", async () => {
    await monter("/connexion");
    await screen.findByRole("heading", { name: "Connexion" });
    const champ = screen.getByLabelText("Mot de passe");
    expect(champ).toHaveAttribute("type", "password");
    const bascule = screen.getByRole("button", { name: "Afficher le mot de passe" });
    await userEvent.click(bascule);
    expect(champ).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Masquer le mot de passe" })).toHaveAttribute("aria-pressed", "true");
  });

  it("applique la langue enregistrée sur le compte", async () => {
    await monter("/connexion", { comptes: [unCompte("amina", { langue: "en" })] });
    await screen.findByRole("heading", { name: "Connexion" });
    await seConnecter();
    expect(await screen.findByRole("heading", { level: 1, name: "Hello, Amina Test" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");
  });
});

describe("déconnexion et session perdue", () => {
  it("se déconnecter ferme la session, vide la mémoire et protège de nouveau les pages", async () => {
    const m = await monter("/", { connecteComme: "amina" });
    await screen.findByRole("heading", { level: 1, name: /Bonjour/ });
    await userEvent.click(screen.getByRole("button", { name: "Se déconnecter" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Connexion" })).toBeInTheDocument();
    expect(m.serveur.connecte()).toBeNull();
    expect(m.queryClient.getQueryData(["moi"]) ?? null).toBeNull(); // plus aucun compte en mémoire
    await m.routeur.navigate({ to: "/" });
    expect(await screen.findByRole("heading", { level: 1, name: "Connexion" })).toBeInTheDocument();
  });

  it("si la déconnexion échoue, on ne fait pas semblant d'être déconnecté", async () => {
    const m = await monter("/", { connecteComme: "amina" });
    await screen.findByRole("heading", { level: 1, name: /Bonjour/ });
    m.serveur.panneReseau = true;
    await userEvent.click(screen.getByRole("button", { name: "Se déconnecter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("injoignable");
    expect(screen.getByRole("heading", { level: 1, name: /Bonjour/ })).toBeInTheDocument();
    expect(m.serveur.connecte()).not.toBeNull();
  });

  it("une session qui tombe en cours d'usage ramène à la connexion avec un avis, puis à la même page", async () => {
    const m = await monter("/projets/id-P1", { connecteComme: "amina" });
    await screen.findByRole("heading", { level: 1, name: /P1/ });
    m.serveur.expirer();
    await appeler("/session/moi/").catch(() => undefined); // n'importe quel appel métier qui échoue en 401
    expect(await screen.findByRole("heading", { level: 1, name: "Connexion" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Votre session a expiré");
    await seConnecter();
    expect(await screen.findByRole("heading", { level: 1, name: /P1/ })).toBeInTheDocument();
    expect(chemin(m)).toBe("/projets/id-P1");
  });

  it("l'ouverture de l'application sans session n'annonce pas une session expirée", async () => {
    await monter("/");
    await screen.findByRole("heading", { level: 1, name: "Connexion" });
    expect(screen.queryByText(/session a expiré/)).not.toBeInTheDocument();
  });
});

describe("projets et droits", () => {
  const deuxProjets = unCompte("amina", {
    projets: [projet("P1", ["consulter", "saisir"]), projet("P2", ["consulter"])],
  });

  it("le sélecteur de projet liste les projets accessibles et mène au projet choisi", async () => {
    const m = await monter("/", { comptes: [deuxProjets], connecteComme: "amina" });
    await screen.findByRole("heading", { level: 1, name: /Bonjour/ });
    const selecteur = screen.getByLabelText("Projet");
    expect(within(selecteur).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Tous les projets",
      "P1 — Projet P1",
      "P2 — Projet P2",
    ]);
    await userEvent.selectOptions(selecteur, "id-P2");
    expect(await screen.findByRole("heading", { level: 1, name: /P2/ })).toBeInTheDocument();
    expect(chemin(m)).toBe("/projets/id-P2");
    expect(screen.getByLabelText("Projet")).toHaveValue("id-P2");
    await userEvent.selectOptions(screen.getByLabelText("Projet"), "");
    expect(await screen.findByRole("heading", { level: 1, name: /Bonjour/ })).toBeInTheDocument();
  });

  it("la page d'un projet dit en clair ce que la personne y peut faire", async () => {
    await monter("/projets/id-P1", { connecteComme: "amina" });
    await screen.findByRole("heading", { level: 1, name: /P1/ });
    const droits = screen.getByRole("list", { name: "Vos droits sur ce projet" });
    expect(within(droits).getAllByRole("listitem").map((l) => l.textContent)).toEqual(["Consulter", "Saisir"]);
    expect(within(droits).queryByText("Valider")).not.toBeInTheDocument();
  });

  it("un droit limité à un site est présenté à part, jamais comme un droit du projet", async () => {
    const compte = unCompte("amina", {
      projets: [{ ...projet("P1", []), operations_par_site: { DJI: ["exporter"] } }],
    });
    await monter("/projets/id-P1", { comptes: [compte], connecteComme: "amina" });
    await screen.findByRole("heading", { level: 1, name: /P1/ });
    expect(screen.getByText("Aucune opération n'est accordée sur l'ensemble de ce projet.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Limité au site DJI" })).toBeInTheDocument();
  });

  it("un projet inconnu ou inaccessible ne révèle rien", async () => {
    await monter("/projets/id-secret", { connecteComme: "amina" });
    expect(await screen.findByText("Ce projet n'existe pas, ou vous n'y avez pas accès.")).toBeInTheDocument();
    expect(screen.queryByText(/secret/)).not.toBeInTheDocument();
  });

  it("sans projet, le dit clairement et ne montre pas de sélecteur vide", async () => {
    const vide = unCompte("amina", { projets: [] });
    await monter("/", { comptes: [vide], connecteComme: "amina" });
    expect(await screen.findByText(/aucun projet/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Projet")).not.toBeInTheDocument();
  });

  it("un compte de plateforme comprend pourquoi il ne voit rien", async () => {
    const plateforme = unCompte("plateforme", { projets: [], organisation: null });
    await monter("/", { comptes: [plateforme], connecteComme: "plateforme" });
    expect(await screen.findByText(/n'est rattaché à aucune organisation/)).toBeInTheDocument();
  });
});

describe("langue", () => {
  it("changer de langue connecté l'enregistre sur le compte", async () => {
    const m = await monter("/", { connecteComme: "amina" });
    await screen.findByRole("heading", { level: 1, name: /Bonjour/ });
    await userEvent.selectOptions(screen.getByLabelText("Langue"), "English");
    expect(await screen.findByRole("heading", { level: 1, name: "Hello, Amina Test" })).toBeInTheDocument();
    await waitFor(() =>
      expect(m.serveur.appels.some((a) => a.methode === "PATCH" && (a.corps as { langue: string }).langue === "en")).toBe(true),
    );
  });

  it("non connecté, rien n'est envoyé au serveur", async () => {
    const m = await monter("/connexion");
    await screen.findByRole("heading", { name: "Connexion" });
    await userEvent.selectOptions(screen.getByLabelText("Langue"), "English");
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(m.serveur.appels.some((a) => a.methode === "PATCH")).toBe(false);
  });

  it("la pseudo-langue (développement) n'est jamais enregistrée sur le compte", async () => {
    const m = await monter("/", { connecteComme: "amina" });
    await screen.findByRole("heading", { level: 1, name: /Bonjour/ });
    await userEvent.selectOptions(screen.getByLabelText("Langue"), "Pseudo (RTL)");
    await waitFor(() => expect(document.documentElement.dir).toBe("rtl"));
    expect(m.serveur.appels.some((a) => a.methode === "PATCH")).toBe(false);
  });
});

describe("structure et accessibilité", () => {
  it("le lien d'évitement mène au contenu et chaque page a un seul titre de premier niveau", async () => {
    await monter("/", { connecteComme: "amina" });
    await screen.findByRole("heading", { level: 1, name: /Bonjour/ });
    expect(screen.getByRole("link", { name: "Aller au contenu" })).toHaveAttribute("href", "#contenu");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("le thème sombre se choisit et se retient", async () => {
    await monter("/connexion");
    await screen.findByRole("heading", { name: "Connexion" });
    await userEvent.selectOptions(screen.getByLabelText("Thème"), "Sombre");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(window.localStorage.getItem("sigf.theme")).toBe("sombre");
    document.documentElement.removeAttribute("data-theme");
  });

  for (const [nom, chemin_, options] of [
    ["la connexion", "/connexion", {}],
    ["l'accueil", "/", { connecteComme: "amina" }],
    ["un projet", "/projets/id-P1", { connecteComme: "amina" }],
  ] as const) {
    it(`${nom} n'a aucune violation d'accessibilité détectable`, async () => {
      const { rendu } = await monter(chemin_, options);
      await screen.findByRole("main");
      await screen.findAllByRole("heading", { level: 1 });
      expect(await violations(rendu.container)).toEqual([]);
    });
  }

  it("la connexion en erreur n'a pas non plus de violation", async () => {
    const { rendu } = await monter("/connexion");
    await screen.findByRole("heading", { name: "Connexion" });
    await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    await screen.findByText("Saisissez votre identifiant.");
    expect(await violations(rendu.container)).toEqual([]);
  });
});
