import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";
import { projet, reponseFausse, unCompte } from "../../test/serveur";
import type { FauxServeur } from "../../test/serveur";
import type { EcritureDetail } from "./types";

afterEach(nettoyer);

const ligne = (n: number, compte: string, debit: string, credit: string, accord: string | null = null) => ({ line_no: n, compte, debit, credit, label: "", accord, cle_version: null });
const ecriture = (id: string, status: EcritureDetail["status"], extra: Partial<EcritureDetail> = {}): EcritureDetail => ({
  id, number: status === "posted" ? "OD-2026-0001" : null, status, label: `Pièce ${id}`, document_ref: "", fx_rate: "1.0000", journal: "OD",
  date_comptable: "2026-03-10", devise: "DJF",
  lignes: [ligne(1, "6011", "600.0000", "0.0000", "IDA-1"), ligne(2, "6011", "401.0000", "0.0000", "GOV-1"), ligne(3, "5211", "0.0000", "1001.0000")],
  total_debit: "1001.0000", total_credit: "1001.0000", ...extra,
});
const resume = (e: EcritureDetail) => ({ ...e, lignes: undefined });

async function ouvrir(chemin: string, operations: Parameters<typeof projet>[1] = ["consulter", "saisir", "valider", "comptabiliser"], ecritures: EcritureDetail[] = [ecriture("e1", "draft")], extra: (s: FauxServeur) => void = () => {}) {
  const m = await monter(chemin, { comptes: [unCompte("amina", { projets: [projet("P1", operations)] })], connecteComme: "amina" });
  m.serveur.routes.push(
    { motif: /^\/projets\/id-P1\/cles-cofinancement\/$/, reponse: () => [{ id: "k1", code: "CHARGES", label: { fr: "Charges" }, version_en_vigueur: null }] },
    { motif: /^\/projets\/id-P1\/ecritures\/$/, reponse: (_t, q) => ecritures.filter((e) => !q.get("statut") || e.status === q.get("statut")).map(resume) },
    { motif: /^\/projets\/id-P1\/ecritures\/(e\d)\/$/, reponse: (t) => ecritures.find((e) => e.id === t[1]) ?? reponseFausse(404, { code: "INTROUVABLE", message: "Introuvable" }) },
  );
  extra(m.serveur);
  return m.serveur;
}
const ecritesPost = (s: FauxServeur) => s.appels.filter((a) => a.methode === "POST" && a.url.includes("/ecritures/"));

async function remplir() {
  await userEvent.type(await screen.findByLabelText("Journal (code)"), "OD");
  await userEvent.type(screen.getByLabelText("Date comptable"), "2026-03-10");
  await userEvent.type(screen.getByLabelText("Libellé de la pièce"), "Charge commune");
  await userEvent.type(screen.getByLabelText("Compte de la ligne 1"), "6011");
  await userEvent.type(screen.getByLabelText("Débit de la ligne 1"), "1 001,50");
  await userEvent.selectOptions(screen.getByLabelText("Clé de cofinancement de la ligne 1"), "CHARGES");
  await userEvent.type(screen.getByLabelText("Compte de la ligne 2"), "5211");
  await userEvent.type(screen.getByLabelText("Crédit de la ligne 2"), "1001,50");
}

describe("écritures : consulter", () => {
  it("liste les écritures avec leur état en toutes lettres, sans numéro avant la comptabilisation", async () => {
    await ouvrir("/ecritures?projet=id-P1", undefined, [ecriture("e1", "draft"), ecriture("e2", "posted")]);
    const table = await screen.findByRole("table", { name: "Écritures du projet" });
    const lignes = within(table).getAllByRole("row").slice(1);
    expect(within(lignes[0]!).getByText("Brouillon")).toBeInTheDocument();
    expect(within(lignes[0]!).getByText("—")).toBeInTheDocument();
    expect(within(lignes[1]!).getByText("Comptabilisée")).toBeInTheDocument();
    expect(within(lignes[1]!).getByText("OD-2026-0001")).toBeInTheDocument();
  });

  it("filtrer par état n'affiche que cet état", async () => {
    await ouvrir("/ecritures?projet=id-P1", undefined, [ecriture("e1", "draft"), ecriture("e2", "posted")]);
    await screen.findByRole("table", { name: "Écritures du projet" });
    await userEvent.selectOptions(screen.getByLabelText("Filtrer par état"), "posted");
    await waitFor(() => expect(within(screen.getByRole("table", { name: "Écritures du projet" })).getAllByRole("row")).toHaveLength(2));
  });

  it("le détail montre l'accord de chaque ligne ventilée et les montants tels que le serveur les rend", async () => {
    await ouvrir("/ecritures?projet=id-P1&ecriture=e1");
    const table = await screen.findByRole("table", { name: "Lignes de l'écriture" });
    expect(within(table).getByText("IDA-1")).toBeInTheDocument();
    expect(within(table).getByText("GOV-1")).toBeInTheDocument();
    expect(within(table).getByText("600.0000")).toBeInTheDocument();
    expect(within(table).getAllByText("1001.0000")).toHaveLength(3); // une ligne + les deux totaux : jamais reformaté
  });

  it("une liste vide le dit clairement", async () => {
    await ouvrir("/ecritures?projet=id-P1", undefined, []);
    expect(await screen.findByText("Aucune écriture pour ce filtre.")).toBeInTheDocument();
  });
});

describe("écritures : saisir", () => {
  it("envoie un corps exact : montants en chaînes, clé sur la ligne, clé d'idempotence", async () => {
    const s = await ouvrir("/ecritures?projet=id-P1", undefined, undefined, (sv) => sv.routes.push({ motif: /ecritures\/$/, methode: "POST", reponse: () => ecriture("e1", "draft") } as never));
    await userEvent.click(await screen.findByRole("button", { name: "Nouvelle écriture" }));
    await remplir();
    expect(screen.getByRole("status")).toHaveTextContent("Total débit 1001.5, total crédit 1001.5. La pièce est équilibrée.");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer le brouillon" }));
    await waitFor(() => expect(ecritesPost(s)).toHaveLength(1));
    const corps = ecritesPost(s)[0]!.corps as Record<string, unknown>;
    expect(corps).toMatchObject({
      journal: "OD",
      date_comptable: "2026-03-10",
      libelle: "Charge commune",
      lignes: [
        { compte: "6011", debit: "1001.50", cle: "CHARGES" },
        { compte: "5211", credit: "1001.50" },
      ],
    });
    expect(typeof corps.cle_idempotence).toBe("string");
    expect(await screen.findByText("Brouillon enregistré.")).toBeInTheDocument();
  });

  it("refuse une pièce déséquilibrée avant l'envoi et le dit", async () => {
    const s = await ouvrir("/ecritures?projet=id-P1");
    await userEvent.click(await screen.findByRole("button", { name: "Nouvelle écriture" }));
    await remplir();
    await userEvent.clear(screen.getByLabelText("Crédit de la ligne 2"));
    await userEvent.type(screen.getByLabelText("Crédit de la ligne 2"), "900");
    expect(screen.getByRole("status")).toHaveTextContent("La pièce n'est pas équilibrée.");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer le brouillon" }));
    expect(await screen.findByText("La pièce est déséquilibrée : débit 1001.5, crédit 900.")).toBeInTheDocument();
    expect(ecritesPost(s)).toHaveLength(0);
  });

  it("affiche tel quel le refus du serveur, par exemple une période close", async () => {
    await ouvrir("/ecritures?projet=id-P1", undefined, undefined, (sv) => sv.routes.push({ motif: /ecritures\/$/, methode: "POST", reponse: () => reponseFausse(422, { code: "REGLE_INVALIDE", message: "La période est close" }) } as never));
    await userEvent.click(await screen.findByRole("button", { name: "Nouvelle écriture" }));
    await remplir();
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer le brouillon" }));
    expect(await screen.findByText("La période est close")).toBeInTheDocument();
  });

  it("un double clic n'envoie qu'une seule pièce", async () => {
    const s = await ouvrir("/ecritures?projet=id-P1", undefined, undefined, (sv) => sv.routes.push({ motif: /ecritures\/$/, methode: "POST", reponse: async () => { await new Promise((r) => setTimeout(r, 50)); return ecriture("e1", "draft"); } } as never));
    await userEvent.click(await screen.findByRole("button", { name: "Nouvelle écriture" }));
    await remplir();
    await userEvent.dblClick(screen.getByRole("button", { name: "Enregistrer le brouillon" }));
    await waitFor(() => expect(ecritesPost(s).length).toBeGreaterThan(0));
    expect(ecritesPost(s)).toHaveLength(1);
  });

  it("on peut ajouter puis retirer une ligne, jamais descendre sous deux", async () => {
    await ouvrir("/ecritures?projet=id-P1");
    await userEvent.click(await screen.findByRole("button", { name: "Nouvelle écriture" }));
    expect(screen.queryByRole("button", { name: "Retirer la ligne 1" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ajouter une ligne" }));
    expect(screen.getByLabelText("Compte de la ligne 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retirer la ligne 3" }));
    expect(screen.queryByLabelText("Compte de la ligne 3")).not.toBeInTheDocument();
  });

  it("sans le droit de saisir, pas de bouton", async () => {
    await ouvrir("/ecritures?projet=id-P1", ["consulter"]);
    await screen.findByRole("table", { name: "Écritures du projet" });
    expect(screen.queryByRole("button", { name: "Nouvelle écriture" })).not.toBeInTheDocument();
  });

  it("le formulaire ouvert est accessible", async () => {
    await ouvrir("/ecritures?projet=id-P1");
    await userEvent.click(await screen.findByRole("button", { name: "Nouvelle écriture" }));
    await screen.findByRole("button", { name: "Enregistrer le brouillon" });
    expect(await violations(document.body)).toEqual([]);
  });
});

describe("écritures : valider et comptabiliser", () => {
  it("valider appelle la bonne URL puis propose de comptabiliser", async () => {
    const s = await ouvrir("/ecritures?projet=id-P1&ecriture=e1", undefined, undefined, (sv) => sv.routes.push({ motif: /e1\/valider\/$/, methode: "POST", reponse: () => ecriture("e1", "validated", { avertissements: ["Dépassement budgétaire de 5 %"] }) } as never));
    await userEvent.click(await screen.findByRole("button", { name: "Valider" }));
    expect(await screen.findByText("Dépassement budgétaire de 5 %")).toBeInTheDocument();
    expect(s.appels.some((a) => a.methode === "POST" && a.url.endsWith("/e1/valider/"))).toBe(true);
    expect(await screen.findByRole("button", { name: "Comptabiliser" })).toBeInTheDocument();
  });

  it("le refus de séparation des tâches s'affiche tel quel", async () => {
    await ouvrir("/ecritures?projet=id-P1&ecriture=e1", undefined, undefined, (sv) => sv.routes.push({ motif: /e1\/valider\/$/, methode: "POST", reponse: () => reponseFausse(403, { code: "ACCES_REFUSE", message: "L'auteur d'une pièce ne la valide pas" }) } as never));
    await userEvent.click(await screen.findByRole("button", { name: "Valider" }));
    expect(await screen.findByText("L'auteur d'une pièce ne la valide pas")).toBeInTheDocument();
  });

  it("sans le droit de valider, un brouillon n'offre pas « Valider »", async () => {
    await ouvrir("/ecritures?projet=id-P1&ecriture=e1", ["consulter", "saisir"]);
    await screen.findByRole("table", { name: "Lignes de l'écriture" });
    expect(screen.queryByRole("button", { name: "Valider" })).not.toBeInTheDocument();
  });

  it("comptabiliser n'est proposé qu'à une pièce validée et à qui en a le droit", async () => {
    await ouvrir("/ecritures?projet=id-P1&ecriture=e2", ["consulter", "valider"], [ecriture("e2", "validated")]);
    await screen.findByRole("table", { name: "Lignes de l'écriture" });
    expect(screen.queryByRole("button", { name: "Comptabiliser" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Valider" })).not.toBeInTheDocument();
  });
});
