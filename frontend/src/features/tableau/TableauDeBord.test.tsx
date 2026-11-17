import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";
import { projet, unCompte } from "../../test/serveur";
import type { IndicateurDto, TableauDto } from "./types";
import { aujourdhui } from "./api";

afterEach(nettoyer);

const ind = (parProjet: Record<string, Record<string, string>> = {}): IndicateurDto => {
  const total: Record<string, string> = {};
  for (const montants of Object.values(parProjet)) {
    for (const [devise, valeur] of Object.entries(montants)) total[devise] = String(Number(total[devise] ?? 0) + Number(valeur));
  }
  return { par_projet: parProjet, total_par_devise: total };
};

function fixture(surcharge: Partial<TableauDto> = {}): TableauDto {
  const p1 = "id-P1";
  const p2 = "id-P2";
  return {
    jour: "2026-06-30",
    projets: [
      { id: p1, code: "P1", libelle: { fr: "Projet P1" }, statut: "active", configuration: "configure", bailleurs: ["IDA"] },
      { id: p2, code: "P2", libelle: { fr: "Projet P2" }, statut: "active", configuration: "non_configure", bailleurs: ["BAD"] },
    ],
    indicateurs: {
      budget_approuve: ind({ [p1]: { DJF: "12400000" }, [p2]: { EUR: "20000.5" } }),
      budget_initial: ind({ [p1]: { DJF: "10000000" } }),
      financements_accordes: ind({ [p1]: { DJF: "1000" }, [p2]: { EUR: "500000" } }),
      financements_recus: ind({ [p1]: { DJF: "300" } }),
      execution_budget: ind({ [p1]: { DJF: "12400000" } }),
      execution_engage: ind({ [p1]: { DJF: "3000" } }),
      execution_consomme: ind({ [p1]: { DJF: "8432000" } }),
      soldes_comptables: ind({ [p1]: { DJF: "1200" }, [p2]: { USD: "50" } }),
      soldes_releves: ind(),
      engagements_ouverts: ind({ [p1]: { DJF: "3000" } }),
      avances_non_justifiees: ind({ [p1]: { DJF: "60" } }),
    },
    taux_execution: { DJF: "0.68", EUR: null },
    par_composante: {
      "": {
        budget: ind({ [p1]: { DJF: "12400000" } }),
        engage: ind({ [p1]: { DJF: "3000" } }),
        consomme: ind({ [p1]: { DJF: "8432000" } }),
        taux_execution: { DJF: "0.68" },
      },
      "COMP-A": {
        budget: ind({ [p1]: { DJF: "1000" } }),
        engage: ind(),
        consomme: ind({ [p1]: { DJF: "250" } }),
        taux_execution: { DJF: "0.25" },
      },
    },
    conformite: {
      par_projet: {
        [p1]: { echeances_a_remettre: 4, echeances_imminentes: 1, echeances_en_retard: 1, echeances_en_escalade: 1, rapports_en_attente: 1, anomalies_ouvertes: 2, premiers_envois_acceptes: 2, premiers_envois_decides: 3 },
        [p2]: { echeances_a_remettre: 0, echeances_imminentes: 0, echeances_en_retard: 0, echeances_en_escalade: 0, rapports_en_attente: 0, anomalies_ouvertes: 0, premiers_envois_acceptes: 0, premiers_envois_decides: 0 },
      },
      totaux: { echeances_a_remettre: 4, echeances_imminentes: 1, echeances_en_retard: 1, echeances_en_escalade: 1, rapports_en_attente: 1, anomalies_ouvertes: 2, premiers_envois_acceptes: 2, premiers_envois_decides: 3 },
      taux_acceptation: "0.6667",
    },
    avertissements: [{ code: "tableau_de_bord.execution_recouvrement", message: "Le consommé global additionne les lignes de la version approuvée." }],
    devises: { DJF: 0, EUR: 2, USD: 2 },
    ...surcharge,
  };
}

const deuxProjets = () =>
  unCompte("amina", { projets: [projet("P1", ["consulter"]), projet("P2", ["consulter"])] });

async function ouvrir(chemin = "/tableau-de-bord", dto: TableauDto | ((r: URLSearchParams) => TableauDto) = fixture()) {
  return monter(chemin, {
    comptes: [deuxProjets()],
    connecteComme: "amina",
    tableau: typeof dto === "function" ? dto : () => dto,
  });
}

const valeurs = (carte: HTMLElement) =>
  [...carte.querySelectorAll(".montant__valeur")].map((e) => (e.textContent ?? "").replace(/\s/g, " "));

const demandes = (m: Awaited<ReturnType<typeof ouvrir>>) =>
  m.serveur.appels.filter((a) => a.url.includes("/tableau-de-bord/")).map((a) => new URLSearchParams(a.url.split("?")[1]));

describe("le tableau de bord", () => {
  it("affiche chaque indicateur, par devise, exactement comme le serveur le donne", async () => {
    await ouvrir();
    expect(await screen.findByRole("heading", { level: 1, name: "Tableau de bord" })).toBeInTheDocument();
    const budget = (await screen.findByRole("heading", { level: 2, name: "Budget et exécution" })).closest("section") as HTMLElement;
    const approuve = within(budget).getByRole("heading", { level: 3, name: "Budget approuvé" }).closest(".indicateur") as HTMLElement;
    expect(valeurs(approuve)).toEqual(["12 400 000", "20 000,50"]); // DJF sans décimales, EUR à deux
    const consomme = within(budget).getByRole("heading", { level: 3, name: "Consommé" }).closest(".indicateur") as HTMLElement;
    expect(valeurs(consomme)).toEqual(["8 432 000"]);
    const fin = (await screen.findByRole("heading", { level: 2, name: "Financements" })).closest("section") as HTMLElement;
    expect(valeurs(within(fin).getByRole("heading", { level: 3, name: "Financements accordés" }).closest(".indicateur") as HTMLElement)).toEqual(["1 000", "500 000,00"]);
  });

  it("ne mélange jamais deux devises dans un même chiffre, et le dit", async () => {
    await ouvrir();
    const treso = (await screen.findByRole("heading", { level: 2, name: "Trésorerie" })).closest("section") as HTMLElement;
    const carte = within(treso).getByRole("heading", { level: 3, name: "Soldes bancaires (comptabilité)" }).closest(".indicateur") as HTMLElement;
    expect(within(carte).getAllByRole("listitem")).toHaveLength(2); // DJF et USD, deux lignes
    expect(within(carte).getByText("DJF")).toBeInTheDocument();
    expect(within(carte).getByText("USD")).toBeInTheDocument();
    expect(screen.getByText(/jamais additionnés/)).toBeInTheDocument();
  });

  it("écrit le taux d'exécution en pourcentage exact, sans taux inventé quand le budget est nul", async () => {
    await ouvrir();
    const carte = (await screen.findByRole("heading", { level: 3, name: "Taux d'exécution" })).closest(".indicateur") as HTMLElement;
    expect(within(carte).getByText(/68,0\s%/)).toBeInTheDocument();
    expect(within(carte).getByText("—")).toBeInTheDocument(); // EUR : budget nul
  });

  it("la jauge reflète exactement le taux écrit à côté, et ne dépasse jamais 100 %", async () => {
    const dto = fixture({ taux_execution: { DJF: "0.68", EUR: "12.5" } });
    await ouvrir("/tableau-de-bord", dto);
    const carte = (await screen.findByRole("heading", { level: 3, name: "Taux d'exécution" })).closest(".indicateur") as HTMLElement;
    const largeurs = [...carte.querySelectorAll<HTMLElement>(".jauge__remplie")].map((e) => e.style.inlineSize);
    expect(largeurs).toEqual(["68%", "100%"]); // DJF 68 %, EUR 1 250 % borné
    expect(within(carte).getByText(/1\s250,0\s%/)).toBeInTheDocument(); // le chiffre, lui, dit la vérité
  });

  it("montre l'exécution par composante, avec le taux calculé par le serveur", async () => {
    await ouvrir();
    const tableau = (await screen.findByRole("heading", { level: 3, name: "Exécution par composante" })).closest("section") as HTMLElement;
    const lignes = within(tableau).getAllByRole("row");
    expect(lignes).toHaveLength(3); // en-tête + « Sans composante » + COMP-A
    expect(within(lignes[2] as HTMLElement).getByText("COMP-A")).toBeInTheDocument();
    expect(within(lignes[2] as HTMLElement).getByText(/25,0\s%/)).toBeInTheDocument();
  });

  it("affiche les points d'attention du serveur, avec leur texte", async () => {
    await ouvrir();
    const alerte = await screen.findByText(/additionne les lignes de la version approuvée/);
    expect(alerte.closest("[role=alert]")).toHaveTextContent("Attention");
  });

  it("présente la conformité : échéances, rapports, anomalies et taux d'acceptation", async () => {
    await ouvrir();
    const c = (await screen.findByRole("heading", { level: 2, name: "Conformité" })).closest("section") as HTMLElement;
    const valeur = (titre: string) => within(within(c).getByRole("heading", { level: 3, name: titre }).closest(".indicateur") as HTMLElement);
    expect(valeur("Échéances à remettre").getByText("4")).toBeInTheDocument();
    expect(valeur("En escalade").getByText("1")).toBeInTheDocument();
    expect(valeur("Anomalies ouvertes").getByText("2")).toBeInTheDocument();
    expect(valeur("Acceptés au premier envoi").getByText(/66,7\s%/)).toBeInTheDocument();
  });

  it("sans envoi décidé, le taux d'acceptation le dit au lieu de montrer zéro", async () => {
    const dto = fixture();
    dto.conformite.taux_acceptation = null;
    await ouvrir("/tableau-de-bord", dto);
    expect(await screen.findByText("Aucun envoi décidé sur la période")).toBeInTheDocument();
  });

  it("le tableau par projet liste chaque projet, mène à lui et signale retards et anomalies", async () => {
    await ouvrir();
    const t = (await screen.findByRole("table", { name: "Détail par projet" })) as HTMLElement;
    const lignes = within(t).getAllByRole("row");
    expect(lignes).toHaveLength(3);
    const p1 = lignes[1] as HTMLElement;
    expect(within(p1).getByRole("link", { name: "P1" })).toHaveAttribute("href", "/projets/id-P1");
    expect(within(p1).getByText("2 en retard")).toBeInTheDocument(); // retard + escalade
    expect(within(p1).getByText("2 anomalies")).toBeInTheDocument();
    expect(within(lignes[2] as HTMLElement).getByText("Rien à signaler")).toBeInTheDocument();
    for (const entete of within(t).getAllByRole("columnheader")) expect(entete).toHaveAttribute("scope", "col");
  });

  it("un projet dont les échéances sont seulement en escalade est signalé en retard", async () => {
    const dto = fixture();
    const c = dto.conformite.par_projet["id-P2"];
    if (c) Object.assign(c, { echeances_en_retard: 0, echeances_en_escalade: 1 });
    await ouvrir("/tableau-de-bord", dto);
    const t = (await screen.findByRole("table", { name: "Détail par projet" })) as HTMLElement;
    expect(within(within(t).getAllByRole("row")[2] as HTMLElement).getByText("1 en retard")).toBeInTheDocument();
  });

  it("sans projet dans le périmètre, explique quoi faire", async () => {
    const dto = fixture({ projets: [] });
    await ouvrir("/tableau-de-bord", dto);
    expect(await screen.findByText(/Aucun projet dans ce périmètre/)).toBeInTheDocument();
  });
});

describe("filtres (dans l'adresse, donc partageables)", () => {
  it("demande d'abord le jour courant, projets actifs seulement", async () => {
    const m = await ouvrir();
    await screen.findByRole("heading", { level: 2, name: "Conformité" });
    const premiere = demandes(m)[0] as URLSearchParams;
    expect(premiere.get("jour")).toBe(aujourdhui());
    expect(premiere.get("statut_projet")).toBeNull();
    expect(premiere.get("devise")).toBeNull();
  });

  it("reprend les filtres de l'adresse", async () => {
    const m = await ouvrir("/tableau-de-bord?jour=2026-03-31&statut=tous&devise=EUR");
    await screen.findByRole("heading", { level: 2, name: "Conformité" });
    const demande = demandes(m).at(-1) as URLSearchParams;
    expect(demande.get("jour")).toBe("2026-03-31");
    expect(demande.get("statut_projet")).toBe("tous");
    expect(demande.get("devise")).toBe("EUR");
    expect(screen.getByLabelText("Date")).toHaveValue("2026-03-31");
  });

  it("changer la date recharge le tableau et met à jour l'adresse", async () => {
    const m = await ouvrir();
    await screen.findByRole("heading", { level: 2, name: "Conformité" });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-01-15" } });
    await waitFor(() => expect((demandes(m).at(-1) as URLSearchParams).get("jour")).toBe("2026-01-15"));
    expect(m.routeur.state.location.search).toMatchObject({ jour: "2026-01-15" });
  });

  it("le filtre de statut et celui de devise partent vers le serveur", async () => {
    const m = await ouvrir();
    await screen.findByRole("heading", { level: 2, name: "Conformité" });
    await userEvent.selectOptions(screen.getByLabelText("Statut des projets"), "Tous les projets");
    await waitFor(() => expect((demandes(m).at(-1) as URLSearchParams).get("statut_projet")).toBe("tous"));
    await userEvent.selectOptions(screen.getByLabelText("Devise"), "EUR");
    await waitFor(() => expect((demandes(m).at(-1) as URLSearchParams).get("devise")).toBe("EUR"));
  });

  it("décocher un projet restreint le périmètre ; tout recocher le rétablit", async () => {
    const m = await ouvrir();
    await screen.findByRole("heading", { level: 2, name: "Conformité" });
    await userEvent.click(screen.getByRole("checkbox", { name: "P2" }));
    await waitFor(() => expect((demandes(m).at(-1) as URLSearchParams).get("projets")).toBe("id-P1"));
    await userEvent.click(screen.getByRole("checkbox", { name: "P2" }));
    await waitFor(() => expect((demandes(m).at(-1) as URLSearchParams).get("projets")).toBeNull());
  });

  it("réinitialiser efface tous les filtres", async () => {
    const m = await ouvrir("/tableau-de-bord?jour=2026-03-31&devise=EUR&statut=tous");
    await screen.findByRole("heading", { level: 2, name: "Conformité" });
    await userEvent.click(screen.getByRole("button", { name: "Réinitialiser les filtres" }));
    await waitFor(() => expect(m.routeur.state.location.search).toEqual({}));
  });

  it("ignore des filtres invalides dans l'adresse au lieu de les envoyer", async () => {
    const m = await ouvrir("/tableau-de-bord?jour=pas-une-date&devise=euro");
    await screen.findByRole("heading", { level: 2, name: "Conformité" });
    const demande = demandes(m).at(-1) as URLSearchParams;
    expect(demande.get("jour")).toBe(aujourdhui());
    expect(demande.get("devise")).toBeNull();
  });
});

describe("états de chargement et d'erreur", () => {
  it("annonce le chargement puis le contenu", async () => {
    const m = await ouvrir();
    expect(await screen.findByRole("heading", { level: 2, name: "Conformité" })).toBeInTheDocument();
    expect(m.serveur.appels.some((a) => a.url.includes("/tableau-de-bord/"))).toBe(true);
  });

  it("signale qu'un rechargement est en cours (aria-busy), puis que c'est fini", async () => {
    const m = await ouvrir();
    await screen.findByRole("heading", { level: 2, name: "Conformité" });
    const zone = document.querySelector(".tableau__etat") as HTMLElement;
    expect(zone).toHaveAttribute("aria-busy", "false");
    let finir = () => undefined as void;
    m.serveur.retard = new Promise<void>((resolve) => {
      finir = resolve;
    });
    await userEvent.selectOptions(screen.getByLabelText("Statut des projets"), "Tous les projets");
    await waitFor(() => expect(zone).toHaveAttribute("aria-busy", "true"));
    expect(screen.getByRole("heading", { level: 2, name: "Conformité" })).toBeInTheDocument(); // l'ancien contenu reste
    finir();
    await waitFor(() => expect(zone).toHaveAttribute("aria-busy", "false"));
  });

  it("un serveur en panne affiche une erreur claire et permet de réessayer", async () => {
    const m = await monter("/", { comptes: [deuxProjets()], connecteComme: "amina" });
    await screen.findByRole("heading", { level: 1, name: /Bonjour/ });
    m.serveur.panneServeur = true;
    await m.routeur.navigate({ to: "/tableau-de-bord" });
    expect(await screen.findByRole("alert")).toHaveTextContent("n'a pas pu être chargé");
    m.serveur.panneServeur = false;
    m.serveur.tableau = () => fixture();
    await userEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Conformité" })).toBeInTheDocument();
    expect(screen.queryByRole("alert", { name: /chargé/ })).not.toBeInTheDocument();
  });

  it("une session perdue ramène à la connexion", async () => {
    const m = await ouvrir();
    await screen.findByRole("heading", { level: 2, name: "Conformité" });
    m.serveur.expirer();
    await userEvent.selectOptions(screen.getByLabelText("Statut des projets"), "Tous les projets");
    expect(await screen.findByRole("heading", { level: 1, name: "Connexion" })).toBeInTheDocument();
  });

  it("sans session, l'adresse du tableau de bord renvoie à la connexion", async () => {
    const m = await monter("/tableau-de-bord", { comptes: [deuxProjets()] });
    expect(await screen.findByRole("heading", { level: 1, name: "Connexion" })).toBeInTheDocument();
    expect(m.routeur.state.location.search).toMatchObject({ retour: "/tableau-de-bord" });
  });
});

describe("pages d'erreur", () => {
  it("une adresse inconnue donne une page « introuvable » dans la langue, pas celle du routeur", async () => {
    await monter("/nimporte-quoi", { comptes: [deuxProjets()], connecteComme: "amina" });
    expect(await screen.findByRole("heading", { level: 1, name: "Page introuvable" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Retour à l'accueil" })).toHaveAttribute("href", "/");
    expect(document.body).not.toHaveTextContent("Not Found");
  });
});

describe("navigation et accessibilité", () => {
  it("l'en-tête mène au tableau de bord et marque la page courante", async () => {
    await monter("/", { comptes: [deuxProjets()], connecteComme: "amina" });
    const lien = await screen.findByRole("link", { name: "Tableau de bord" });
    expect(lien).not.toHaveAttribute("aria-current", "page");
    await userEvent.click(lien);
    expect(await screen.findByRole("heading", { level: 1, name: "Tableau de bord" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tableau de bord" })).toHaveAttribute("aria-current", "page");
  });

  it("la page n'a aucune violation d'accessibilité détectable", async () => {
    await ouvrir();
    await screen.findByRole("heading", { level: 2, name: "Conformité" });
    expect(await violations(document.body)).toEqual([]);
  });

  it("la page vide non plus", async () => {
    await ouvrir("/tableau-de-bord", fixture({ projets: [] }));
    await screen.findByText(/Aucun projet dans ce périmètre/);
    expect(await violations(document.body)).toEqual([]);
  });
});
