import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";
import { projet, unCompte } from "../../test/serveur";
import type { ConsolidationDto, DetailDto, EcritureDto, EcrituresDuDetailDto, TableauDto } from "./types";

afterEach(nettoyer);

const compte = () => unCompte("amina", { projets: [projet("P1", ["consulter"]), projet("P2", ["consulter"])] });

const details: DetailDto[] = [
  { type: "compte_bancaire", id: "d1", libelle: "CB-USD", devise: "USD", montant: "50.0000", a_une_ecriture: true },
  { type: "compte_bancaire", id: "d2", libelle: "CB-DJF", devise: "DJF", montant: "1200.0000", a_une_ecriture: true },
  { type: "ligne_budget", id: "d3", libelle: "Ligne 1", devise: "DJF", montant: "300.0000", a_une_ecriture: false },
];
const ecritures: EcrituresDuDetailDto = {
  detail: details[0] as DetailDto,
  ecritures: [{ ecriture_id: "e1", numero: "OD-0001", date: "2026-02-10", libelle: "Réception USD", montant: "50.0000" }],
};
const ecriture: EcritureDto = {
  id: "e1",
  numero: "OD-0001",
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

async function ouvrirDescente(chemin: string) {
  const m = await monter(chemin, { comptes: [compte()], connecteComme: "amina" });
  m.serveur.routes.push(
    {
      motif: /^\/devises\/$/,
      reponse: () => [
        { code: "DJF", label: { fr: "Franc djiboutien" }, decimales: 0 },
        { code: "USD", label: { fr: "Dollar" }, decimales: 2 },
      ],
    },
    { motif: /^\/projets\/[^/]+\/tableau-de-bord\/[a-z_]+\/detail\/$/, reponse: () => details },
    { motif: /^\/projets\/[^/]+\/tableau-de-bord\/[a-z_]+\/detail\/d1\/ecritures\/$/, reponse: () => ecritures },
    { motif: /^\/projets\/[^/]+\/tableau-de-bord\/ecritures\/e1\/$/, reponse: () => ecriture },
  );
  return m;
}
const BASE = "/tableau-de-bord/descente?projet=id-P1&indicateur=soldes_comptables&jour=2026-06-30";

describe("la descente du tableau de bord", () => {
  it("liste ce qui compose le chiffre et donne le total par devise, sans mélanger les devises", async () => {
    await ouvrirDescente(BASE);
    const tableau = await screen.findByRole("table", { name: "Ce qui compose le chiffre" });
    expect(within(tableau).getByText("CB-USD")).toBeInTheDocument();
    const pied = tableau.querySelector("tfoot") as HTMLElement;
    const totaux = [...pied.querySelectorAll("tr")].map((l) => (l.textContent ?? "").replace(/\s/g, " "));
    expect(totaux).toHaveLength(2); // DJF et USD : deux lignes
    // 1200 + 300, sans décimales : le nombre de décimales vient du catalogue du serveur
    expect(totaux.some((l) => /1 500(?!,)/.test(l) && l.includes("DJF"))).toBe(true);
    expect(totaux.some((l) => l.includes("50,00") && l.includes("USD"))).toBe(true);
  });

  it("n'offre les écritures que pour ce qui en a, et dit pourquoi pour le reste", async () => {
    await ouvrirDescente(BASE);
    const tableau = await screen.findByRole("table", { name: "Ce qui compose le chiffre" });
    expect(within(tableau).getAllByRole("button", { name: /Voir les écritures/ })).toHaveLength(2);
    expect(within(tableau).getByText(/ne vient pas du grand livre/)).toBeInTheDocument();
  });

  it("descend de l'élément aux écritures, puis à l'écriture : lignes et pièces", async () => {
    const m = await ouvrirDescente(BASE);
    const u = userEvent.setup();
    await u.click(await screen.findByRole("button", { name: /Voir les écritures.*CB-USD/ }));
    expect(await screen.findByText("Réception USD")).toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: "Ouvrir l'écriture OD-0001" }));
    const lignes = await screen.findByRole("table", { name: "Lignes de l'écriture" });
    expect(within(lignes).getByText("5211")).toBeInTheDocument();
    expect(within(lignes).getByText("7061")).toBeInTheDocument();
    expect(screen.getByText("facture-001.pdf")).toBeInTheDocument();
    expect(screen.getByText(/Facture/)).toBeInTheDocument();
    // l'adresse porte la descente : elle est partageable
    expect(m.routeur.state.location.search).toMatchObject({ detail: "d1", ecriture: "e1" });
  });

  it("une adresse partagée rouvre directement l'écriture", async () => {
    await ouvrirDescente(`${BASE}&detail=d1&ecriture=e1`);
    expect(await screen.findByRole("table", { name: "Lignes de l'écriture" })).toBeInTheDocument();
    expect(await screen.findByText("Réception USD", { selector: "td" })).toBeInTheDocument();
  });

  it("des paramètres invalides retombent sur des valeurs sûres, sans planter", async () => {
    const m = await ouvrirDescente("/tableau-de-bord/descente?projet=id-P1&indicateur=nimporte&jour=pas-une-date");
    await screen.findByRole("heading", { level: 1 });
    expect(m.routeur.state.location.search).toMatchObject({ indicateur: "budget_approuve" });
  });

  it("est accessible", async () => {
    const m = await ouvrirDescente(`${BASE}&detail=d1&ecriture=e1`);
    await screen.findByRole("table", { name: "Lignes de l'écriture" });
    expect(await violations(m.rendu.container)).toEqual([]);
  });
});

describe("la consolidation", () => {
  const dto = (surcharge: Partial<ConsolidationDto>): ConsolidationDto => ({
    indicateur: "financements_accordes",
    devise_reference: "DJF",
    type_taux: "officiel",
    origine: { devise_reference: "organisation", type_taux: "organisation" },
    jour: "2026-06-30",
    consolide: true,
    montant: "100001000.0000",
    par_projet: {},
    taux: { EUR: { taux: "200.0000", date: "2026-06-01" } },
    methode: "Taux « officiel » le plus récent au 2026-06-30, en DJF",
    raison: null,
    ...surcharge,
  });
  const CODES = [
    "budget_approuve", "budget_initial", "financements_accordes", "financements_recus", "execution_budget",
    "execution_engage", "execution_consomme", "soldes_comptables", "soldes_releves", "engagements_ouverts",
    "avances_non_justifiees",
  ];
  const vide = { par_projet: {}, total_par_devise: {} };
  const tableau = (): TableauDto =>
    ({
      jour: "2026-06-30",
      projets: [{ id: "id-P1", code: "P1", libelle: { fr: "P1" }, statut: "active", configuration: "configure", bailleurs: [] }],
      indicateurs: Object.fromEntries(CODES.map((c) => [c, vide])),
      taux_execution: {},
      par_composante: {},
      conformite: {
        par_projet: {},
        totaux: { echeances_a_remettre: 0, echeances_imminentes: 0, echeances_en_retard: 0, echeances_en_escalade: 0, rapports_en_attente: 0, anomalies_ouvertes: 0, premiers_envois_acceptes: 0, premiers_envois_decides: 0 },
        taux_acceptation: null,
      },
      avertissements: [],
      devises: { DJF: 0, EUR: 2, USD: 2 },
    }) as unknown as TableauDto;

  async function ouvrir(reponse: (r: URLSearchParams) => ConsolidationDto) {
    const m = await monter("/tableau-de-bord?jour=2026-06-30&statut=tous&projets=%5B%22id-P1%22%5D", { comptes: [compte()], connecteComme: "amina", tableau });
    m.serveur.routes.push({ motif: /^\/tableau-de-bord\/[a-z_]+\/consolidation\/$/, reponse: (_t, r) => reponse(r) });
    return m;
  }
  const carte = async () => (await screen.findByRole("heading", { level: 2, name: "Total consolidé" })).closest("section") as HTMLElement;

  it("affiche le total consolidé, sa méthode, ses taux et d'où viennent la devise et le type de taux", async () => {
    await ouvrir(() => dto({}));
    const c = await carte();
    expect(await within(c).findByText("100 001 000")).toBeInTheDocument(); // DJF : aucune décimale
    expect(within(c).getAllByText("Réglage de l'organisation")).toHaveLength(2);
    expect(within(c).getByText(/le plus récent au 2026-06-30/)).toBeInTheDocument();
    expect(within(c).getByText(/EUR · 200 · 2026-06-01/)).toBeInTheDocument();
  });

  it("répète la raison du serveur quand il ne consolide pas, sans inventer de montant", async () => {
    await ouvrir(() => dto({ consolide: false, montant: null, devise_reference: null, type_taux: null, origine: { devise_reference: null, type_taux: null }, methode: null, taux: {}, raison: "Aucune devise de référence n'est paramétrée au 2026-06-30." }));
    const c = await carte();
    expect(await within(c).findByText(/Aucune devise de référence n'est paramétrée/)).toBeInTheDocument();
    expect(c.querySelector(".montant")).toBeNull();
  });

  it("envoie le choix de la personne, qui l'emporte sur les réglages", async () => {
    const m = await ouvrir((r) =>
      r.get("devise_reference") === "EUR" ? dto({ devise_reference: "EUR", montant: "500000.0000", origine: { devise_reference: "demande", type_taux: "organisation" } }) : dto({}),
    );
    const c = await carte();
    const u = userEvent.setup();
    await within(c).findByText("100 001 000");
    await u.selectOptions(within(c).getByLabelText("Devise de référence"), "EUR");
    expect(await within(c).findByText("500 000,00")).toBeInTheDocument();
    expect(within(c).getByText("Choisi ici")).toBeInTheDocument();
    const demandes = m.serveur.appels.filter((a) => a.url.includes("/consolidation/")).map((a) => new URLSearchParams(a.url.split("?")[1]));
    expect(demandes.at(-1)?.get("devise_reference")).toBe("EUR");
    expect(demandes[0]?.has("devise_reference")).toBe(false); // par défaut : les réglages décident
    // les filtres du tableau (date, statut, projets) suivent jusqu'à la consolidation
    expect(demandes.at(-1)?.get("jour")).toBe("2026-06-30");
    expect(demandes.at(-1)?.get("statut_projet")).toBe("tous");
    expect(demandes.at(-1)?.get("projets")).toBe("id-P1");
  });
});
