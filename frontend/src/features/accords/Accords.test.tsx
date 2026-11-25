import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";
import { projet, reponseFausse, unCompte } from "../../test/serveur";
import type { FauxServeur } from "../../test/serveur";
import type { AccordDetail, AccordResume } from "./types";

afterEach(nettoyer);

const accord = (id: string, numero: string, extra: Partial<AccordResume> = {}): AccordResume => ({
  id,
  numero,
  libelle: `Don ${numero}`,
  bailleur: "BAD",
  nature: "don",
  statut: "actif",
  devise: "USD",
  montant_initial: "1000000.00",
  montant_courant: "1250000.50",
  date_effet: "2026-01-01",
  date_fin_eligibilite: null,
  date_cloture: "2030-12-31",
  date_limite_decaissement: null,
  format_numero_demande: "standard",
  suffixe_agence: "",
  ...extra,
});
const detail = (a: AccordResume): AccordDetail => ({
  ...a,
  categories: [
    { id: "c1", code: "BIENS", label: { fr: "Biens", en: "Goods" }, parent: null, plafond: "600000.00", devise: "USD" },
    { id: "c2", code: "BIENS-A", label: { fr: "Biens A", en: "Goods A" }, parent: "BIENS", plafond: "400000.00", devise: "USD" },
  ],
  avenants: [{ id: "v1", reference: "AV-1", date_avenant: "2027-03-01", montant_revise: "1250000.50", motif: "Rallonge", document_id: null }],
});

async function ouvrir(
  accords: AccordResume[],
  { operations = ["consulter", "parametrer"], chemin = "/accords?projet=id-P1&accord=a1", retard }: { operations?: Parameters<typeof projet>[1]; chemin?: string; retard?: Promise<void> } = {},
) {
  const etat = { accords };
  const m = await monter(chemin, { comptes: [unCompte("amina", { projets: [projet("P1", operations)] })], connecteComme: "amina" });
  const s: FauxServeur = m.serveur;
  s.routes.push(
    { motif: /^\/projets\/id-P1\/accords\/$/, reponse: async () => { if (retard) await retard; return etat.accords; } },
    { motif: /^\/projets\/id-P1\/accords\/(a\d)\/$/, reponse: async (t) => { if (retard) await retard; const a = etat.accords.find((x) => x.id === t[1]); return a ? detail(a) : reponseFausse(404, { code: "INTROUVABLE", message: "Introuvable" }); } },
  );
  return { m, s, etat };
}
const ecritures = (s: FauxServeur) => s.appels.filter((a) => a.methode === "POST");

describe("accords : consulter", () => {
  it("affiche un état de chargement", async () => {
    let liberer: () => void = () => {};
    await ouvrir([accord("a1", "DON-1")], { chemin: "/accords?projet=id-P1", retard: new Promise<void>((r) => (liberer = r)) });
    expect(await screen.findByRole("status", { name: "Chargement en cours" })).toBeInTheDocument();
    liberer();
    expect(await screen.findByRole("table", { name: "Accords du projet" })).toBeInTheDocument();
  });

  it("une liste vide le dit clairement", async () => {
    await ouvrir([], { chemin: "/accords?projet=id-P1" });
    expect(await screen.findByText("Ce projet n'a encore aucun accord.")).toBeInTheDocument();
  });

  it("liste les accords avec leur état en toutes lettres et leurs montants en chaînes", async () => {
    await ouvrir([accord("a1", "DON-1"), accord("a2", "PRET-2", { statut: "suspendu", nature: "pret" })], { chemin: "/accords?projet=id-P1" });
    const table = await screen.findByRole("table", { name: "Accords du projet" });
    const lignes = within(table).getAllByRole("row").slice(1);
    expect(within(lignes[0]!).getByText("DON-1")).toBeInTheDocument();
    expect(within(lignes[0]!).getByText("Actif")).toBeInTheDocument();
    expect(within(lignes[1]!).getByText("Suspendu")).toBeInTheDocument();
    expect(within(lignes[0]!).getByText("1250000.50 USD")).toBeInTheDocument(); // jamais reformaté en nombre
  });

  it("le détail montre les catégories en arbre, les avenants et la numérotation", async () => {
    await ouvrir([accord("a1", "DON-1", { format_numero_demande: "bad", suffixe_agence: "ADB" })]);
    expect(await screen.findByRole("heading", { name: "Accord DON-1" })).toBeInTheDocument();
    const arbre = screen.getByRole("table", { name: "Catégories de dépenses" });
    expect(within(arbre).getByText("BIENS-A")).toBeInTheDocument();
    expect(within(arbre).getByText("sous BIENS")).toBeInTheDocument();
    expect(within(arbre).getByText("400000.00")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Avenants" })).toHaveTextContent("AV-1");
    expect(screen.getByText("Format BAD · suffixe ADB")).toBeInTheDocument();
  });

  it("un refus de lecture du serveur s'affiche tel quel", async () => {
    const { s } = await ouvrir([accord("a1", "DON-1")], { chemin: "/accords?projet=id-P1" });
    s.routes.unshift({ motif: /^\/projets\/id-P1\/accords\/$/, reponse: () => reponseFausse(403, { code: "ACCES_REFUSE", message: "Vous n'êtes pas habilité à consulter ce projet" }) });
    expect(await screen.findByText("Vous n'êtes pas habilité à consulter ce projet")).toBeInTheDocument();
  });

  it("est accessible", async () => {
    const { m } = await ouvrir([accord("a1", "DON-1")]);
    await screen.findByRole("heading", { name: "Accord DON-1" });
    expect(await violations(m.rendu.container)).toEqual([]);
  });
});

describe("accords : décider", () => {
  it("sans le droit de paramétrer, aucune action n'est proposée", async () => {
    await ouvrir([accord("a1", "DON-1")], { operations: ["consulter"] });
    await screen.findByRole("heading", { name: "Accord DON-1" });
    expect(screen.queryByRole("button", { name: "Changer le statut" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Régler la numérotation" })).not.toBeInTheDocument();
    expect(screen.getByText(/droit de paramétrer/)).toBeInTheDocument();
  });

  it("change le statut avec son motif puis rafraîchit", async () => {
    const { s, etat } = await ouvrir([accord("a1", "DON-1")]);
    s.routes.push({
      methode: "POST",
      motif: /^\/projets\/id-P1\/accords\/a1\/statut\/$/,
      reponse: (_t, _r, corps) => {
        etat.accords = [accord("a1", "DON-1", { statut: (corps as { statut: AccordResume["statut"] }).statut })];
        return etat.accords[0];
      },
    });
    await screen.findByRole("heading", { name: "Accord DON-1" });
    await userEvent.selectOptions(screen.getByLabelText("Nouveau statut"), "suspendu");
    await userEvent.type(screen.getByLabelText("Motif (exigé pour suspendre, clore ou annuler)"), "Audit en cours");
    await userEvent.click(screen.getByRole("button", { name: "Changer le statut" }));
    expect(await screen.findByText("Statut modifié.")).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({ statut: "suspendu", motif: "Audit en cours" });
    expect((await screen.findAllByText("Suspendu")).length).toBeGreaterThan(0);
  });

  it("affiche le refus du serveur pour une transition interdite, sans rien changer", async () => {
    const { s } = await ouvrir([accord("a1", "DON-1")]);
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/accords\/a1\/statut\/$/, reponse: () => reponseFausse(409, { code: "TRANSITION_INTERDITE", message: "Transition d'accord interdite : actif vers brouillon" }) });
    await screen.findByRole("heading", { name: "Accord DON-1" });
    await userEvent.selectOptions(screen.getByLabelText("Nouveau statut"), "brouillon");
    await userEvent.click(screen.getByRole("button", { name: "Changer le statut" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Transition d'accord interdite : actif vers brouillon");
  });

  it("un double clic n'envoie qu'un changement", async () => {
    let liberer: () => void = () => {};
    const attente = new Promise<void>((r) => (liberer = r));
    const { s } = await ouvrir([accord("a1", "DON-1")]);
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/accords\/a1\/statut\/$/, reponse: async () => { await attente; return accord("a1", "DON-1", { statut: "clos" }); } });
    await screen.findByRole("heading", { name: "Accord DON-1" });
    await userEvent.selectOptions(screen.getByLabelText("Nouveau statut"), "clos");
    await userEvent.dblClick(screen.getByRole("button", { name: "Changer le statut" }));
    liberer();
    await screen.findByText("Statut modifié.");
    expect(ecritures(s)).toHaveLength(1);
  });

  it("règle la numérotation BAD avec un suffixe de 3 lettres majuscules", async () => {
    const { s } = await ouvrir([accord("a1", "DON-1")]);
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/accords\/a1\/numerotation\/$/, reponse: (_t, _r, c) => accord("a1", "DON-1", { format_numero_demande: "bad", suffixe_agence: (c as { suffixe_agence: string }).suffixe_agence }) });
    await screen.findByRole("heading", { name: "Accord DON-1" });
    await userEvent.selectOptions(screen.getByLabelText("Format de numérotation"), "bad");
    await userEvent.type(screen.getByLabelText("Suffixe d'agence (3 lettres majuscules)"), "ADB");
    await userEvent.click(screen.getByRole("button", { name: "Régler la numérotation" }));
    expect(await screen.findByText("Numérotation réglée.")).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({ format: "bad", suffixe_agence: "ADB" });
  });

  it.each(["", "AB", "ABCD", "abc", "A1C"])("refuse le suffixe « %s » avant tout envoi", async (suffixe) => {
    const { s } = await ouvrir([accord("a1", "DON-1")]);
    await screen.findByRole("heading", { name: "Accord DON-1" });
    await userEvent.selectOptions(screen.getByLabelText("Format de numérotation"), "bad");
    if (suffixe) await userEvent.type(screen.getByLabelText("Suffixe d'agence (3 lettres majuscules)"), suffixe);
    await userEvent.click(screen.getByRole("button", { name: "Régler la numérotation" }));
    expect(await screen.findByText("Le suffixe d'agence est de 3 lettres majuscules, par exemple ABC.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("le format standard n'envoie aucun suffixe", async () => {
    const { s } = await ouvrir([accord("a1", "DON-1", { format_numero_demande: "bad", suffixe_agence: "ADB" })]);
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/accords\/a1\/numerotation\/$/, reponse: () => accord("a1", "DON-1") });
    await screen.findByRole("heading", { name: "Accord DON-1" });
    await userEvent.selectOptions(screen.getByLabelText("Format de numérotation"), "standard");
    await userEvent.click(screen.getByRole("button", { name: "Régler la numérotation" }));
    await screen.findByText("Numérotation réglée.");
    expect(ecritures(s)[0]?.corps).toEqual({ format: "standard", suffixe_agence: "" });
  });

  it("affiche le refus du serveur quand l'accord a déjà des demandes", async () => {
    const { s } = await ouvrir([accord("a1", "DON-1")]);
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/accords\/a1\/numerotation\/$/, reponse: () => reponseFausse(422, { code: "REGLE_INVALIDE", message: "L'accord DON-1 a déjà des demandes : son format de numérotation ne change plus" }) });
    await screen.findByRole("heading", { name: "Accord DON-1" });
    await userEvent.selectOptions(screen.getByLabelText("Format de numérotation"), "bad");
    await userEvent.type(screen.getByLabelText("Suffixe d'agence (3 lettres majuscules)"), "ADB");
    await userEvent.click(screen.getByRole("button", { name: "Régler la numérotation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("a déjà des demandes");
  });
});
