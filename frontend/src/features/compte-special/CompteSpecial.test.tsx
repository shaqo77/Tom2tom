import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";
import { projet, reponseFausse, unCompte } from "../../test/serveur";
import type { FauxServeur } from "../../test/serveur";
import type { CompteBancaire, JustificationBanque, Situation } from "./types";

afterEach(nettoyer);

const COMPTES: CompteBancaire[] = [
  { id: "c1", code: "CS-1", libelle: "Compte spécial USD", type: "special", devise: "USD", accord: "DON-1", numero_masque: "••••4321", actif: true },
  { id: "c2", code: "CD-1", libelle: "Compte désigné", type: "designe", devise: "USD", accord: "DON-1", numero_masque: "••••9999", actif: true },
];
const SITUATION: Situation = {
  compte: "CS-1",
  devise: "USD",
  date: "2026-03-31",
  complet: true,
  manques: [],
  avances: [{ demande: "0001ADB", montant: "500000.0000" }],
  justifications: [
    { demande: "0001ADB", montant: "200000.1000", date_soumission: "2026-03-20", en_cours: true, comptee: true },
    { demande: "0002ADB", montant: "100000.2000", date_soumission: "2026-03-25", en_cours: false, comptee: true },
  ],
  total_avances: "500000.0000",
  solde_cloture: "199999.7000",
  justifie_cette_demande: "200000.1000",
  justifie_precedemment: "100000.2000",
  total_justifie: "500000.0000",
  ecart: "0.0000",
};
const JUSTIFS: JustificationBanque[] = [
  { id: "j1", demande: "0001ADB", montant: "200000.1000", date_soumission: "2026-03-20", annulee: false, motif_annulation: "" },
  { id: "j2", demande: "0002ADB", montant: "100000.2000", date_soumission: "2026-03-25", annulee: true, motif_annulation: "Montant erroné" },
];

async function ouvrir(
  { operations = ["consulter", "saisir", "publier"], chemin = "/compte-special?projet=id-P1&compte=c1&date=2026-03-31", situation = SITUATION, justifs = JUSTIFS, retard }: { operations?: Parameters<typeof projet>[1]; chemin?: string; situation?: Situation; justifs?: JustificationBanque[]; retard?: Promise<void> } = {},
) {
  const etat = { justifs };
  const m = await monter(chemin, { comptes: [unCompte("amina", { projets: [projet("P1", operations)] })], connecteComme: "amina" });
  m.serveur.routes.push(
    { motif: /^\/projets\/id-P1\/comptes-bancaires\/$/, reponse: () => COMPTES },
    { motif: /^\/comptes\/c1\/situation-compte-special\/$/, reponse: async () => { if (retard) await retard; return situation; } },
    { motif: /^\/comptes\/c1\/justifications-banque\/$/, reponse: () => etat.justifs },
  );
  return { m, s: m.serveur as FauxServeur, etat };
}
const ecritures = (s: FauxServeur) => s.appels.filter((a) => a.methode === "POST");

describe("compte spécial : consulter", () => {
  it("affiche un état de chargement de la situation", async () => {
    let liberer: () => void = () => {};
    await ouvrir({ retard: new Promise<void>((r) => (liberer = r)) });
    expect(await screen.findByRole("status", { name: "Chargement en cours" })).toBeInTheDocument();
    liberer();
    expect(await screen.findByRole("table", { name: "Avances reçues" })).toBeInTheDocument();
  });

  it("ne propose que les comptes spéciaux, avec leur numéro masqué", async () => {
    await ouvrir({ chemin: "/compte-special?projet=id-P1" });
    const choix = await screen.findByLabelText("Compte spécial");
    const options = within(choix).getAllByRole("option").map((o) => o.textContent);
    expect(options).toContain("CS-1 · USD · ••••4321");
    expect(options.some((o) => o?.includes("CD-1"))).toBe(false);
  });

  it("montre la situation à la date avec tous les montants tels quels, en chaînes", async () => {
    await ouvrir();
    const avances = await screen.findByRole("table", { name: "Avances reçues" });
    expect(within(avances).getByText("500000.0000")).toBeInTheDocument();
    const justifs = screen.getByRole("table", { name: "Justifications soumises" });
    expect(within(justifs).getByText("200000.1000")).toBeInTheDocument(); // jamais 200000.1
    expect(screen.getByText("Solde de clôture : 199999.7000 USD")).toBeInTheDocument();
    expect(screen.getByText("Écart : 0.0000 USD")).toBeInTheDocument();
    expect(screen.getByText("Demande en cours d'examen")).toBeInTheDocument();
  });

  it("une situation incomplète nomme ce qui manque et ne montre aucun écart inventé", async () => {
    await ouvrir({ situation: { ...SITUATION, complet: false, manques: ["Aucun solde de relevé à cette date"], solde_cloture: null, total_justifie: null, ecart: null } });
    expect(await screen.findByText("Aucun solde de relevé à cette date")).toBeInTheDocument();
    expect(screen.getByText("La situation est incomplète : elle ne permet pas de conclure.")).toBeInTheDocument();
    expect(screen.queryByText(/Écart :/)).not.toBeInTheDocument();
  });

  it("changer la date redemande la situation à cette date", async () => {
    const { s } = await ouvrir();
    await screen.findByRole("table", { name: "Avances reçues" });
    const champ = screen.getByLabelText("Date de la situation");
    await userEvent.clear(champ);
    await userEvent.type(champ, "2026-02-28");
    expect(await screen.findByRole("table", { name: "Avances reçues" })).toBeInTheDocument();
    expect(s.appels.some((a) => a.url.includes("date=2026-02-28"))).toBe(true);
  });

  it("un champ date incomplet (vide) ne change pas la situation et ne produit aucune requête sans date", async () => {
    const { s } = await ouvrir();
    await screen.findByRole("table", { name: "Avances reçues" });
    const avant = s.appels.length;
    fireEvent.change(screen.getByLabelText("Date de la situation"), { target: { value: "" } });
    await new Promise((r) => setTimeout(r, 50));
    expect(s.appels.slice(avant).filter((a) => a.url.includes("situation-compte-special"))).toHaveLength(0);
    expect(screen.getByRole("table", { name: "Avances reçues" })).toBeInTheDocument();
  });

  it("un refus de lecture du serveur s'affiche tel quel", async () => {
    const { s } = await ouvrir();
    s.routes.unshift({ motif: /^\/comptes\/c1\/situation-compte-special\/$/, reponse: () => reponseFausse(403, { code: "ACCES_REFUSE", message: "Vous n'avez pas le droit de consulter ce compte" }) });
    expect(await screen.findByText("Vous n'avez pas le droit de consulter ce compte")).toBeInTheDocument();
  });

  it("est accessible", async () => {
    const { m } = await ouvrir();
    await screen.findByRole("table", { name: "Avances reçues" });
    expect(await violations(m.rendu.container)).toEqual([]);
  });
});

describe("compte spécial : annuler une justification", () => {
  it("les justifications annulées sont signalées avec leur motif et ne proposent plus d'annulation", async () => {
    await ouvrir();
    const table = await screen.findByRole("table", { name: "Justifications à la Banque" });
    expect(within(table).getByText("Annulée : Montant erroné")).toBeInTheDocument();
    expect(within(table).getAllByRole("button", { name: /^Annuler la justification/ })).toHaveLength(1);
  });

  it("annuler exige un motif avant tout envoi puis l'envoie et rafraîchit", async () => {
    const { s, etat } = await ouvrir();
    s.routes.push({ methode: "POST", motif: /^\/justifications-banque\/j1\/annulation\/$/, reponse: (_t, _r, c) => { etat.justifs = [{ ...JUSTIFS[0]!, annulee: true, motif_annulation: (c as { motif: string }).motif }, JUSTIFS[1]!]; return etat.justifs[0]; } });
    await userEvent.click(await screen.findByRole("button", { name: "Annuler la justification 0001ADB" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirmer l'annulation" }));
    expect(screen.getByText("Saisissez le motif de l'annulation.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
    await userEvent.type(screen.getByLabelText("Motif de l'annulation"), "Doublon");
    await userEvent.click(screen.getByRole("button", { name: "Confirmer l'annulation" }));
    expect(await screen.findByText("Justification annulée.")).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({ motif: "Doublon" });
    expect(await screen.findByText("Annulée : Doublon")).toBeInTheDocument();
  });

  it("affiche le refus du serveur et un double clic n'envoie qu'une annulation", async () => {
    let liberer: () => void = () => {};
    const attente = new Promise<void>((r) => (liberer = r));
    const { s } = await ouvrir();
    s.routes.push({ methode: "POST", motif: /^\/justifications-banque\/j1\/annulation\/$/, reponse: async () => { await attente; return reponseFausse(422, { code: "REGLE_INVALIDE", message: "Cette justification est déjà annulée" }); } });
    await userEvent.click(await screen.findByRole("button", { name: "Annuler la justification 0001ADB" }));
    await userEvent.type(screen.getByLabelText("Motif de l'annulation"), "x");
    await userEvent.dblClick(screen.getByRole("button", { name: "Confirmer l'annulation" }));
    liberer();
    expect(await screen.findByRole("alert")).toHaveTextContent("Cette justification est déjà annulée");
    expect(ecritures(s)).toHaveLength(1);
  });

  it("sans le droit de saisir, aucune annulation n'est proposée", async () => {
    await ouvrir({ operations: ["consulter"] });
    await screen.findByRole("table", { name: "Justifications à la Banque" });
    expect(screen.queryByRole("button", { name: /^Annuler la justification/ })).not.toBeInTheDocument();
  });
});

describe("compte spécial : publier le rapport", () => {
  async function pret(operations: Parameters<typeof projet>[1] = ["consulter", "saisir", "publier"]) {
    const o = await ouvrir({ operations });
    await screen.findByRole("table", { name: "Avances reçues" });
    return o;
  }

  it("sans le droit de publier, aucun formulaire de publication", async () => {
    await pret(["consulter"]);
    expect(screen.queryByRole("button", { name: "Publier le rapport" })).not.toBeInTheDocument();
    expect(screen.getByText(/droit de publier/)).toBeInTheDocument();
  });

  it("publie avec la date, la demande et la note d'écart, et affiche le sceau", async () => {
    const { s } = await pret();
    s.routes.push({ methode: "POST", motif: /^\/comptes\/c1\/rapport-compte-special\/$/, reponse: () => reponseFausse(201, { id: "r1", modele: "BAD_RECONCILIATION_CS", scelle: "ab".repeat(32), valeurs: {} }) });
    await userEvent.type(screen.getByLabelText("Numéro de la demande (facultatif)"), "0001ADB");
    await userEvent.type(screen.getByLabelText("Note expliquant l'écart (facultative)"), "Intérêts bancaires non encore reçus");
    await userEvent.click(screen.getByRole("button", { name: "Publier le rapport" }));
    expect(await screen.findByText("Rapport publié et scellé.")).toBeInTheDocument();
    expect(screen.getByText(/abababababababab/)).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({ date_fin: "2026-03-31", demande: "0001ADB", note_ecart: "Intérêts bancaires non encore reçus" });
  });

  it("refuse une note de plus de 4000 caractères avant tout envoi", async () => {
    const { s } = await pret();
    const note = screen.getByLabelText("Note expliquant l'écart (facultative)");
    await userEvent.click(note);
    await userEvent.paste("x".repeat(4001));
    await userEvent.click(screen.getByRole("button", { name: "Publier le rapport" }));
    expect(await screen.findByText("La note dépasse 4000 caractères.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("accepte une note d'exactement 4000 caractères", async () => {
    const { s } = await pret();
    s.routes.push({ methode: "POST", motif: /^\/comptes\/c1\/rapport-compte-special\/$/, reponse: () => reponseFausse(201, { id: "r1", modele: "BAD_RECONCILIATION_CS", scelle: "cd".repeat(32), valeurs: {} }) });
    await userEvent.click(screen.getByLabelText("Note expliquant l'écart (facultative)"));
    await userEvent.paste("x".repeat(4000));
    await userEvent.click(screen.getByRole("button", { name: "Publier le rapport" }));
    expect(await screen.findByText("Rapport publié et scellé.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(1);
  });

  it("affiche le refus du serveur (assertions violées, mapping incomplet) sans rien perdre", async () => {
    const { s } = await pret();
    s.routes.push({ methode: "POST", motif: /^\/comptes\/c1\/rapport-compte-special\/$/, reponse: () => reponseFausse(422, { code: "REGLE_INVALIDE", message: "La situation du compte spécial est incomplète" }) });
    await userEvent.click(screen.getByRole("button", { name: "Publier le rapport" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("La situation du compte spécial est incomplète");
  });
});
