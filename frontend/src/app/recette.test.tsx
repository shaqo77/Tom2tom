import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../test/accessibilite";
import { monter, nettoyer } from "../test/monter";
import { projet, unCompte } from "../test/serveur";
import type { ConsolidationDto, DetailDto, EcritureDto, EcrituresDuDetailDto, IndicateurDto, TableauDto } from "../features/tableau/types";

afterEach(nettoyer);

/**
 * Recette de parcours (L6, version 1) : ce qu'une personne fait vraiment, d'un bout à l'autre, dans le navigateur
 * simulé : se connecter, ouvrir un projet, lire le tableau de bord, consolider, descendre d'un chiffre jusqu'à
 * l'écriture et sa pièce. Le serveur est le faux serveur des tests : ce test prouve que l'écran enchaîne les bons
 * appels, n'invente aucun chiffre et n'en mélange aucun (devises distinctes) ; il ne prouve pas le serveur lui-même
 * (c'est le rôle de la recette backend `test_recette_multibailleur_bd.py`).
 */

const ind = (parProjet: Record<string, Record<string, string>>, total: Record<string, string>): IndicateurDto => ({ par_projet: parProjet, total_par_devise: total });
const VIDE = ind({}, {});

const TABLEAU: TableauDto = {
  jour: "2026-06-30",
  projets: [
    { id: "id-P1", code: "P1", libelle: { fr: "Projet P1" }, statut: "active", configuration: "configure", bailleurs: ["IDA", "BAD"] },
    { id: "id-P2", code: "P2", libelle: { fr: "Projet P2" }, statut: "active", configuration: "configure", bailleurs: ["UE"] },
  ],
  indicateurs: {
    budget_approuve: VIDE,
    budget_initial: VIDE,
    financements_accordes: ind({ "id-P1": { DJF: "200000" }, "id-P2": { EUR: "1500.50" } }, { DJF: "200000", EUR: "1500.50" }),
    financements_recus: VIDE,
    execution_budget: VIDE,
    execution_engage: VIDE,
    execution_consomme: VIDE,
    soldes_comptables: ind({ "id-P1": { DJF: "1200", USD: "50" } }, { DJF: "1200", USD: "50" }),
    soldes_releves: VIDE,
    engagements_ouverts: VIDE,
    avances_non_justifiees: VIDE,
  },
  taux_execution: {},
  par_composante: {},
  conformite: {
    par_projet: {},
    totaux: { echeances_a_remettre: 0, echeances_imminentes: 0, echeances_en_retard: 0, echeances_en_escalade: 0, rapports_en_attente: 0, anomalies_ouvertes: 0, premiers_envois_acceptes: 0, premiers_envois_decides: 0 },
    taux_acceptation: null,
  },
  avertissements: [],
  devises: { DJF: 0, EUR: 2, USD: 2 },
};

const CONSOLIDATION: ConsolidationDto = {
  indicateur: "financements_accordes",
  devise_reference: "DJF",
  type_taux: "officiel",
  origine: { devise_reference: "demande", type_taux: "organisation" },
  jour: "2026-06-30",
  consolide: true,
  montant: "466789",
  par_projet: { "id-P1": "200000", "id-P2": "266789" },
  taux: { EUR: { taux: "177.7", date: "2026-06-30" } },
  methode: "taux du jour",
  raison: null,
};

const DETAILS: DetailDto[] = [
  { type: "compte_bancaire", id: "d1", libelle: "CB-USD", devise: "USD", montant: "50.0000", a_une_ecriture: true },
  { type: "compte_bancaire", id: "d2", libelle: "CB-DJF", devise: "DJF", montant: "1200.0000", a_une_ecriture: true },
];
const ECRITURES: EcrituresDuDetailDto = {
  detail: DETAILS[0] as DetailDto,
  ecritures: [{ ecriture_id: "e1", numero: "OD-2026-0001", date: "2026-02-10", libelle: "Réception USD", montant: "50.0000" }],
};
const ECRITURE: EcritureDto = {
  id: "e1",
  numero: "OD-2026-0001",
  journal: "OD",
  date: "2026-02-10",
  libelle: "Réception USD",
  devise: "USD",
  lignes: [
    { id: "l1", compte: "5211", montant: "50.0000" },
    { id: "l2", compte: "7061", montant: "-50.0000" },
  ],
  pieces: [{ id: "p1", type: "facture", nom: "facture-001.pdf", taille: 9 }],
};

describe("recette de parcours : de la connexion à l'écriture", () => {
  it("se connecter, ouvrir un projet, lire le tableau, consolider, descendre jusqu'à l'écriture et sa pièce", async () => {
    const compte = unCompte("amina", { projets: [projet("P1", ["consulter"]), projet("P2", ["consulter"])] });
    const m = await monter("/connexion", { comptes: [compte], tableau: () => TABLEAU });
    m.serveur.routes.push(
      { motif: /^\/tableau-de-bord\/[a-z_]+\/consolidation\/$/, reponse: () => CONSOLIDATION },
      { motif: /^\/projets\/id-P1\/tableau-de-bord\/soldes_comptables\/detail\/$/, reponse: () => DETAILS },
      { motif: /^\/projets\/id-P1\/tableau-de-bord\/soldes_comptables\/detail\/d1\/ecritures\/$/, reponse: () => ECRITURES },
      { motif: /^\/projets\/id-P1\/tableau-de-bord\/ecritures\/e1\/$/, reponse: () => ECRITURE },
    );
    const u = userEvent.setup();
    const appels = () => m.serveur.appels.map((a) => `${a.methode} ${a.url.replace("/api/v1", "").split("?")[0]}`);

    // 1. Connexion : l'identifiant et le mot de passe partent une fois, l'accueil salue par le nom.
    await screen.findByRole("heading", { name: "Connexion" });
    await u.type(screen.getByLabelText("Identifiant"), "amina");
    await u.type(screen.getByLabelText("Mot de passe"), "motdepasse-solide");
    await u.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Bonjour, Amina Test" })).toBeInTheDocument();
    expect(appels().filter((a) => a.includes("connexion") && a.startsWith("POST"))).toHaveLength(1);

    // 2. Le projet : l'accueil propose ceux de la personne, et seulement les siens.
    expect(screen.getByRole("link", { name: "Ouvrir le projet P1" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ouvrir le projet P2" })).toBeInTheDocument();
    await u.click(screen.getByRole("link", { name: "Ouvrir le projet P1" }));
    expect(await screen.findByRole("heading", { level: 1, name: /P1/ })).toBeInTheDocument();

    // 3. Le tableau de bord : les montants sont ceux du serveur, UNE devise par ligne, jamais additionnées entre elles.
    await u.click(screen.getByRole("link", { name: "Tableau de bord" }));
    expect(await screen.findByRole("heading", { level: 1, name: /Tableau de bord/ })).toBeInTheDocument();
    const fin = (await screen.findByRole("heading", { level: 2, name: "Financements" })).closest("section") as HTMLElement;
    const accordes = within(fin).getByRole("heading", { level: 3, name: "Financements accordés" }).closest(".indicateur") as HTMLElement;
    const lignesAccordes = within(accordes).getAllByRole("listitem").map((l) => (l.textContent ?? "").replace(/\s/g, " "));
    expect(lignesAccordes).toHaveLength(2); // une ligne par devise : DJF et EUR, jamais additionnées
    expect(lignesAccordes[0]).toMatch(/200 000/);
    expect(lignesAccordes[1]).toMatch(/1 500,50/);
    expect(accordes.textContent).not.toMatch(/201 500/);

    // 4. La consolidation : un total dans UNE devise de référence, avec les taux utilisés, tels que le serveur les donne.
    await u.selectOptions(await screen.findByLabelText("Devise de référence"), "DJF");
    const consolidation = (await screen.findByText("Total consolidé")).closest("section, article, div") as HTMLElement;
    await waitFor(() => expect(consolidation.textContent?.replace(/\s/g, " ")).toMatch(/466 789/));
    expect(consolidation.textContent).toMatch(/177[.,]7/); // le taux utilisé est montré, rien n'est deviné
    expect(appels().some((a) => a.includes("/tableau-de-bord/financements_accordes/consolidation/"))).toBe(true);
    const demande = m.serveur.appels.find((a) => a.url.includes("consolidation") && a.url.includes("devise_reference=DJF"));
    expect(demande).toBeDefined();

    // 5. La descente : du chiffre à ce qui le compose, puis aux écritures, puis à l'écriture : lignes et pièce.
    const detail = screen.getAllByRole("link", { name: /Voir le détail.*Soldes bancaires \(comptabilité\).*P1/ })[0]!;
    await u.click(detail);
    const tableau = await screen.findByRole("table", { name: "Ce qui compose le chiffre" });
    expect(within(tableau).getByText("CB-USD")).toBeInTheDocument();
    await u.click(within(tableau).getByRole("button", { name: /Voir les écritures.*CB-USD/ }));
    expect(await screen.findByText("Réception USD")).toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: "Ouvrir l'écriture OD-2026-0001" }));
    const lignes = await screen.findByRole("table", { name: "Lignes de l'écriture" });
    expect(within(lignes).getByText("5211")).toBeInTheDocument();
    expect(within(lignes).getByText("7061")).toBeInTheDocument();
    expect(screen.getByText("facture-001.pdf")).toBeInTheDocument();

    // 6. Le parcours n'a rien écrit : seules la connexion (et son jeton) sont des écritures.
    const ecritures = m.serveur.appels.filter((a) => a.methode !== "GET");
    expect(ecritures.every((a) => a.url.includes("connexion") || a.url.includes("csrf"))).toBe(true);

    // 7. Et l'écran final reste accessible.
    expect(await violations(document.body)).toEqual([]);
  });
});
