import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";
import { projet, reponseFausse, unCompte } from "../../test/serveur";
import type { FauxServeur } from "../../test/serveur";
import type { DocumentReference } from "./types";

afterEach(nettoyer);

const HASH = "a".repeat(64);
const doc = (id: string, title: string, extra: Partial<DocumentReference> = {}): DocumentReference => ({
  id,
  kind: "financing_agreement",
  title,
  version: "1",
  issued_on: "2026-01-15",
  sha256: HASH,
  remplace_par: null,
  ...extra,
});

async function ouvrir(documents: DocumentReference[], { operations = ["consulter", "parametrer"], retard }: { operations?: Parameters<typeof projet>[1]; retard?: Promise<void> } = {}) {
  const etat = { documents };
  const m = await monter("/documents?projet=id-P1", { comptes: [unCompte("amina", { projets: [projet("P1", operations)] })], connecteComme: "amina" });
  m.serveur.routes.push({ motif: /^\/projets\/id-P1\/documents\/$/, reponse: async () => { if (retard) await retard; return etat.documents; } });
  return { m, s: m.serveur as FauxServeur, etat };
}
const ecritures = (s: FauxServeur) => s.appels.filter((a) => a.methode === "POST");
const pdf = (nom = "accord.pdf", taille?: number) => {
  const f = new File(["%PDF-1.4 contenu"], nom, { type: "application/pdf" });
  if (taille !== undefined) Object.defineProperty(f, "size", { value: taille });
  return f;
};

describe("documents : consulter", () => {
  it("affiche un état de chargement", async () => {
    let liberer: () => void = () => {};
    await ouvrir([doc("d1", "Accord DON-1")], { retard: new Promise<void>((r) => (liberer = r)) });
    expect(await screen.findByRole("status", { name: "Chargement en cours" })).toBeInTheDocument();
    liberer();
    expect(await screen.findByRole("table", { name: "Documents du projet" })).toBeInTheDocument();
  });

  it("une liste vide le dit clairement", async () => {
    await ouvrir([]);
    expect(await screen.findByText("Ce projet n'a encore aucun document.")).toBeInTheDocument();
  });

  it("liste les documents avec leur genre, leur empreinte abrégée et leur état", async () => {
    await ouvrir([doc("d1", "Accord DON-1"), doc("d2", "Ancien manuel", { kind: "implementation_manual", remplace_par: "d3" })]);
    const table = await screen.findByRole("table", { name: "Documents du projet" });
    const lignes = within(table).getAllByRole("row").slice(1);
    expect(within(lignes[0]!).getByText("Accord de financement")).toBeInTheDocument();
    expect(within(lignes[0]!).getByText("aaaaaaaaaaaa…")).toBeInTheDocument();
    expect(within(lignes[1]!).getByText("Manuel d'exécution")).toBeInTheDocument();
    expect(within(lignes[1]!).getByText("Remplacé")).toBeInTheDocument();
  });

  it("le téléchargement ouvre l'adresse du contenu telle quelle", async () => {
    await ouvrir([doc("d1", "Accord DON-1")]);
    const lien = await screen.findByRole("link", { name: "Télécharger Accord DON-1" });
    expect(lien).toHaveAttribute("href", "/api/v1/projets/id-P1/documents/d1/contenu/");
  });

  it("un refus de lecture du serveur s'affiche tel quel", async () => {
    const { s } = await ouvrir([]);
    s.routes.unshift({ motif: /^\/projets\/id-P1\/documents\/$/, reponse: () => reponseFausse(403, { code: "ACCES_REFUSE", message: "Vous n'êtes pas habilité à consulter les documents" }) });
    expect(await screen.findByText("Vous n'êtes pas habilité à consulter les documents")).toBeInTheDocument();
  });

  it("est accessible", async () => {
    const { m } = await ouvrir([doc("d1", "Accord DON-1")]);
    await screen.findByRole("table", { name: "Documents du projet" });
    expect(await violations(m.rendu.container)).toEqual([]);
  });
});

describe("documents : intégrité", () => {
  it("un fichier intact est annoncé comme tel", async () => {
    const { s } = await ouvrir([doc("d1", "Accord DON-1")]);
    s.routes.push({ motif: /^\/projets\/id-P1\/documents\/d1\/integrite\/$/, reponse: () => ({ integre: true, probleme: null }) });
    await userEvent.click(await screen.findByRole("button", { name: "Vérifier l'intégrité de Accord DON-1" }));
    expect(await screen.findByText("Le fichier correspond à son empreinte.")).toBeInTheDocument();
  });

  it("un fichier altéré est signalé avec la raison du serveur, en alerte", async () => {
    const { s } = await ouvrir([doc("d1", "Accord DON-1")]);
    s.routes.push({ motif: /^\/projets\/id-P1\/documents\/d1\/integrite\/$/, reponse: () => ({ integre: false, probleme: "Le fichier stocké ne correspond plus à son empreinte" }) });
    await userEvent.click(await screen.findByRole("button", { name: "Vérifier l'intégrité de Accord DON-1" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Le fichier stocké ne correspond plus à son empreinte");
  });
});

describe("documents : déposer", () => {
  async function remplir({ titre = "Accord DON-1", fichier = pdf() as File | null } = {}) {
    await userEvent.selectOptions(screen.getByLabelText("Genre de document"), "financing_agreement");
    if (titre) await userEvent.type(screen.getByLabelText("Titre"), titre);
    await userEvent.type(screen.getByLabelText("Version (facultative)"), "2");
    await userEvent.type(screen.getByLabelText("Date d'émission (facultative)"), "2026-01-15");
    if (fichier) await userEvent.upload(screen.getByLabelText("Fichier à déposer"), fichier);
  }

  it("sans le droit de paramétrer, aucun dépôt n'est proposé mais la consultation reste", async () => {
    await ouvrir([doc("d1", "Accord DON-1")], { operations: ["consulter"] });
    await screen.findByRole("table", { name: "Documents du projet" });
    expect(screen.queryByRole("button", { name: "Déposer le document" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Remplacer/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Télécharger Accord DON-1" })).toBeInTheDocument();
    expect(screen.getByText(/droit de paramétrer/)).toBeInTheDocument();
  });

  it("envoie le formulaire multipart avec le fichier, puis rafraîchit la liste", async () => {
    const { s, etat } = await ouvrir([]);
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/documents\/$/, reponse: () => { etat.documents = [doc("d9", "Accord DON-1")]; return reponseFausse(201, etat.documents[0]); } });
    await screen.findByText("Ce projet n'a encore aucun document.");
    await remplir();
    await userEvent.click(screen.getByRole("button", { name: "Déposer le document" }));
    expect(await screen.findByText("Document déposé.")).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({
      kind: "financing_agreement",
      title: "Accord DON-1",
      version: "2",
      issued_on: "2026-01-15",
      fichier: { nom: "accord.pdf", taille: 16, type: "application/pdf" },
    });
    expect((await screen.findAllByText("Accord DON-1")).length).toBeGreaterThan(0);
  });

  it("exige un titre et un fichier avant tout envoi", async () => {
    const { s } = await ouvrir([]);
    await screen.findByText("Ce projet n'a encore aucun document.");
    await userEvent.click(screen.getByRole("button", { name: "Déposer le document" }));
    expect(await screen.findByText("Saisissez le titre du document.")).toBeInTheDocument();
    expect(screen.getByText("Choisissez le fichier à déposer.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("refuse un fichier sans titre avant tout envoi", async () => {
    const { s } = await ouvrir([]);
    await screen.findByText("Ce projet n'a encore aucun document.");
    await remplir({ titre: "" });
    await userEvent.click(screen.getByRole("button", { name: "Déposer le document" }));
    expect(await screen.findByText("Saisissez le titre du document.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("refuse avant tout envoi un fichier de plus de 50 Mio, et accepte exactement 50 Mio", async () => {
    const { s } = await ouvrir([]);
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/documents\/$/, reponse: () => reponseFausse(201, doc("d9", "Gros")) });
    await screen.findByText("Ce projet n'a encore aucun document.");
    await remplir({ titre: "Gros", fichier: pdf("gros.pdf", 50 * 1024 * 1024 + 1) });
    await userEvent.click(screen.getByRole("button", { name: "Déposer le document" }));
    expect(await screen.findByText("Le fichier dépasse 50 Mio.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
    await userEvent.upload(screen.getByLabelText("Fichier à déposer"), pdf("pile.pdf", 50 * 1024 * 1024));
    await userEvent.click(screen.getByRole("button", { name: "Déposer le document" }));
    expect(await screen.findByText("Document déposé.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(1);
  });

  it("affiche le refus du serveur sans effacer la saisie", async () => {
    const { s } = await ouvrir([]);
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/documents\/$/, reponse: () => reponseFausse(422, { code: "REGLE_INVALIDE", message: "Le type de fichier n'est pas accepté" }) });
    await screen.findByText("Ce projet n'a encore aucun document.");
    await remplir();
    await userEvent.click(screen.getByRole("button", { name: "Déposer le document" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Le type de fichier n'est pas accepté");
    expect(screen.getByLabelText("Titre")).toHaveValue("Accord DON-1");
  });

  it("indique l'envoi en cours et n'envoie qu'un dépôt malgré un double clic", async () => {
    let liberer: () => void = () => {};
    const attente = new Promise<void>((r) => (liberer = r));
    const { s } = await ouvrir([]);
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/documents\/$/, reponse: async () => { await attente; return reponseFausse(201, doc("d9", "Accord DON-1")); } });
    await screen.findByText("Ce projet n'a encore aucun document.");
    await remplir();
    await userEvent.dblClick(screen.getByRole("button", { name: "Déposer le document" }));
    expect(await screen.findByRole("progressbar", { name: "Envoi du fichier en cours" })).toBeInTheDocument();
    liberer();
    await screen.findByText("Document déposé.");
    expect(ecritures(s)).toHaveLength(1);
    await waitFor(() => expect(screen.queryByRole("progressbar")).not.toBeInTheDocument());
  });
});

describe("documents : remplacer", () => {
  it("envoie le nouveau fichier et nomme les exigences à revérifier", async () => {
    const { s } = await ouvrir([doc("d1", "Accord DON-1")]);
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/documents\/d1\/remplacement\/$/, reponse: () => reponseFausse(201, { ...doc("d2", "Accord DON-1", { version: "2" }), exigences_a_reverifier: ["BAD-DELAI", "BAD-PIECES"] }) });
    await userEvent.click(await screen.findByRole("button", { name: "Remplacer Accord DON-1" }));
    await userEvent.upload(screen.getByLabelText("Nouveau fichier"), pdf("v2.pdf"));
    await userEvent.type(screen.getByLabelText("Version du remplaçant (facultative)"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Remplacer le document" }));
    expect(await screen.findByText("Document remplacé. Exigences à revérifier : BAD-DELAI, BAD-PIECES")).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({ version: "2", fichier: { nom: "v2.pdf", taille: 16, type: "application/pdf" } });
  });

  it("exige un fichier avant tout envoi", async () => {
    const { s } = await ouvrir([doc("d1", "Accord DON-1")]);
    await userEvent.click(await screen.findByRole("button", { name: "Remplacer Accord DON-1" }));
    await userEvent.click(screen.getByRole("button", { name: "Remplacer le document" }));
    expect(await screen.findByText("Choisissez le fichier à déposer.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("un document déjà remplacé ne se remplace plus", async () => {
    await ouvrir([doc("d1", "Ancien", { remplace_par: "d2" })]);
    await screen.findByRole("table", { name: "Documents du projet" });
    expect(screen.queryByRole("button", { name: "Remplacer Ancien" })).not.toBeInTheDocument();
  });
});
