import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";
import { projet, reponseFausse, unCompte } from "../../test/serveur";
import type { FauxServeur } from "../../test/serveur";
import type { ControleDetail, ControleLivre } from "./types";

afterEach(nettoyer);

const controle = (id: string, code: string, status: ControleDetail["status"], extra: Partial<ControleDetail> = {}): ControleDetail => ({
  id,
  code,
  version: 1,
  status,
  mode: "bloquant",
  type_regle: "budget",
  severity: "bloquant",
  label: { fr: `Contrôle ${code}`, en: `Control ${code}` },
  valid_from: "2026-01-01",
  valid_to: null,
  expression: { type_regle: "budget", conditions: [{ champ: "disponible_categorie", op: ">=", valeur: "0" }] },
  applicable_si: null,
  parametres: null,
  action_corrective: { fr: "Vérifier le budget", en: "Check the budget" },
  ...extra,
});
const LIVRES: ControleLivre[] = [
  { code: "BUD-LIGNE", famille: "budget", type_regle: "budget", severity: "bloquant", label: { fr: "Ligne budgétaire dépassée" }, action_corrective: null, installe: true },
  { code: "PIE-DOUBLON", famille: "pieces", type_regle: "pieces", severity: "avertissement", label: { fr: "Pièce en double" }, action_corrective: null, installe: false },
  { code: "RIS-CATEGORIE-SEUIL", famille: "risque", type_regle: "risque", severity: "avertissement", label: { fr: "Catégorie consommée" }, action_corrective: null, installe: false },
  { code: "RIS-AVANCE-NON-APUREE", famille: "risque", type_regle: "avances", severity: "avertissement", label: { fr: "Avance non apurée" }, action_corrective: null, installe: false },
];

async function ouvrir(controles: ControleDetail[], { operations = ["consulter", "valider", "parametrer"], chemin = "/controles?projet=id-P1", retard }: { operations?: Parameters<typeof projet>[1]; chemin?: string; retard?: Promise<void> } = {}) {
  const etat = { controles, livres: LIVRES };
  const m = await monter(chemin, { comptes: [unCompte("amina", { projets: [projet("P1", operations)] })], connecteComme: "amina" });
  const s: FauxServeur = m.serveur;
  s.routes.push(
    {
      motif: /^\/projets\/id-P1\/controles\/$/,
      reponse: async (_t, r) => {
        if (retard) await retard;
        const statut = r.get("status");
        return etat.controles.filter((c) => !statut || c.status === statut).map((c) => ({ ...c, expression: undefined, applicable_si: undefined, parametres: undefined, action_corrective: undefined }));
      },
    },
    { motif: /^\/projets\/id-P1\/controles\/bibliotheque\/$/, reponse: () => etat.livres },
    { motif: /^\/projets\/id-P1\/controles\/(c\d)\/$/, reponse: (t) => etat.controles.find((c) => c.id === t[1]) ?? reponseFausse(404, { code: "INTROUVABLE", message: "Introuvable" }) },
  );
  return { m, s, etat };
}
const ecritures = (s: FauxServeur) => s.appels.filter((a) => a.methode === "POST");

describe("contrôles : consulter", () => {
  it("affiche un état de chargement", async () => {
    let liberer: () => void = () => {};
    await ouvrir([controle("c1", "BUD-LIGNE", "active")], { retard: new Promise<void>((r) => (liberer = r)) });
    expect(await screen.findByRole("status", { name: "Chargement en cours" })).toBeInTheDocument();
    liberer();
    expect(await screen.findByRole("table", { name: "Contrôles du projet" })).toBeInTheDocument();
  });

  it("une liste vide le dit clairement", async () => {
    await ouvrir([]);
    expect(await screen.findByText("Ce projet n'a encore installé aucun contrôle.")).toBeInTheDocument();
  });

  it("liste les contrôles avec leur état et leur sévérité en toutes lettres", async () => {
    await ouvrir([controle("c1", "BUD-LIGNE", "active"), controle("c2", "PIE-DOUBLON", "draft", { severity: "avertissement" })]);
    const table = await screen.findByRole("table", { name: "Contrôles du projet" });
    const lignes = within(table).getAllByRole("row").slice(1);
    expect(within(lignes[0]!).getByText("Actif")).toBeInTheDocument();
    expect(within(lignes[0]!).getByText("Bloquant")).toBeInTheDocument();
    expect(within(lignes[1]!).getByText("Brouillon")).toBeInTheDocument();
    expect(within(lignes[1]!).getByText("Avertissement")).toBeInTheDocument();
  });

  it("filtrer par état redemande la liste avec ce filtre", async () => {
    const { s } = await ouvrir([controle("c1", "BUD-LIGNE", "active"), controle("c2", "PIE-DOUBLON", "draft")]);
    await screen.findByRole("table", { name: "Contrôles du projet" });
    await userEvent.selectOptions(screen.getByLabelText("Filtrer par état"), "draft");
    expect(await screen.findByText("PIE-DOUBLON")).toBeInTheDocument();
    expect(screen.queryByText("BUD-LIGNE")).not.toBeInTheDocument();
    expect(s.appels.some((a) => a.url.includes("status=draft"))).toBe(true);
  });

  it("le détail montre la règle en lecture seule et l'action corrective", async () => {
    await ouvrir([controle("c1", "BUD-LIGNE", "active")], { chemin: "/controles?projet=id-P1&controle=c1" });
    expect(await screen.findByRole("heading", { name: "Contrôle BUD-LIGNE · version 1" })).toBeInTheDocument();
    expect(screen.getByText("Vérifier le budget")).toBeInTheDocument();
    expect(screen.getByLabelText("Règle (lecture seule)")).toHaveTextContent("disponible_categorie");
  });

  it("un refus de lecture du serveur s'affiche tel quel", async () => {
    const { s } = await ouvrir([]);
    s.routes.unshift({ motif: /^\/projets\/id-P1\/controles\/$/, reponse: () => reponseFausse(403, { code: "ACCES_REFUSE", message: "Vous n'êtes pas habilité à consulter les contrôles" }) });
    expect(await screen.findByText("Vous n'êtes pas habilité à consulter les contrôles")).toBeInTheDocument();
  });

  it("est accessible", async () => {
    const { m } = await ouvrir([controle("c1", "BUD-LIGNE", "draft")], { chemin: "/controles?projet=id-P1&controle=c1" });
    await screen.findByRole("heading", { name: "Contrôle BUD-LIGNE · version 1" });
    expect(await violations(m.rendu.container)).toEqual([]);
  });
});

describe("contrôles : décider", () => {
  const url = (fin: string) => new RegExp(`^\\/projets\\/id-P1\\/controles\\/c1\\/${fin}\\/$`);

  it("valider un brouillon puis l'activer appelle les bonnes URL dans l'ordre", async () => {
    const { s, etat } = await ouvrir([controle("c1", "BUD-LIGNE", "draft")], { chemin: "/controles?projet=id-P1&controle=c1" });
    s.routes.push(
      { methode: "POST", motif: url("valider"), reponse: () => (etat.controles = [controle("c1", "BUD-LIGNE", "validated")])[0] },
      { methode: "POST", motif: url("activer"), reponse: () => (etat.controles = [controle("c1", "BUD-LIGNE", "active")])[0] },
    );
    await userEvent.click(await screen.findByRole("button", { name: "Valider" }));
    await userEvent.click(await screen.findByRole("button", { name: "Activer" }));
    expect(await screen.findByText("Contrôle activé.")).toBeInTheDocument();
    expect(ecritures(s).map((a) => a.url.split("/").slice(-2, -1)[0])).toEqual(["valider", "activer"]);
  });

  it("rejeter exige un motif avant tout envoi puis l'envoie", async () => {
    const { s, etat } = await ouvrir([controle("c1", "BUD-LIGNE", "validated")], { chemin: "/controles?projet=id-P1&controle=c1" });
    s.routes.push({ methode: "POST", motif: url("rejeter"), reponse: () => (etat.controles = [controle("c1", "BUD-LIGNE", "rejected")])[0] });
    await userEvent.click(await screen.findByRole("button", { name: "Rejeter" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirmer le rejet" }));
    expect(screen.getByText("Saisissez le motif du rejet.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
    await userEvent.type(screen.getByLabelText("Motif du rejet"), "Seuil inadapté");
    await userEvent.click(screen.getByRole("button", { name: "Confirmer le rejet" }));
    expect(await screen.findByText("Contrôle rejeté.")).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({ motif: "Seuil inadapté" });
  });

  it("affiche le refus du serveur et un double clic n'envoie qu'une demande", async () => {
    let liberer: () => void = () => {};
    const attente = new Promise<void>((r) => (liberer = r));
    const { s } = await ouvrir([controle("c1", "BUD-LIGNE", "draft")], { chemin: "/controles?projet=id-P1&controle=c1" });
    s.routes.push({ methode: "POST", motif: url("valider"), reponse: async () => { await attente; return reponseFausse(403, { code: "ACCES_REFUSE", message: "Vous n'êtes pas habilité à valider" }); } });
    await userEvent.dblClick(await screen.findByRole("button", { name: "Valider" }));
    liberer();
    expect(await screen.findByRole("alert")).toHaveTextContent("Vous n'êtes pas habilité à valider");
    expect(ecritures(s)).toHaveLength(1);
  });

  it("sans les droits, aucune action n'est proposée", async () => {
    await ouvrir([controle("c1", "BUD-LIGNE", "draft")], { operations: ["consulter"], chemin: "/controles?projet=id-P1&controle=c1" });
    await screen.findByRole("heading", { name: "Contrôle BUD-LIGNE · version 1" });
    for (const nom of ["Valider", "Activer", "Rejeter"]) expect(screen.queryByRole("button", { name: nom })).not.toBeInTheDocument();
    expect(screen.getByText(/droit que vous n'avez pas sur ce projet/)).toBeInTheDocument();
  });

  it("un contrôle actif ne propose aucune action et n'invoque aucun droit manquant, même sans droits", async () => {
    await ouvrir([controle("c1", "BUD-LIGNE", "active")], { operations: ["consulter"], chemin: "/controles?projet=id-P1&controle=c1" });
    await screen.findByRole("heading", { name: "Contrôle BUD-LIGNE · version 1" });
    for (const nom of ["Valider", "Activer", "Rejeter"]) expect(screen.queryByRole("button", { name: nom })).not.toBeInTheDocument();
    expect(screen.queryByText(/droit que vous n'avez pas sur ce projet/)).not.toBeInTheDocument();
  });
});

describe("contrôles : installer la bibliothèque", () => {
  async function pret(operations: Parameters<typeof projet>[1] = ["consulter", "valider", "parametrer"]) {
    const o = await ouvrir([], { operations });
    await screen.findByRole("table", { name: "Contrôles livrés" });
    return o;
  }
  const cocher = (code: string) => userEvent.click(screen.getByRole("checkbox", { name: new RegExp(`^${code}`) }));

  it("les contrôles déjà installés ne peuvent pas être cochés et le disent", async () => {
    await pret();
    expect(screen.getByRole("checkbox", { name: /^BUD-LIGNE/ })).toBeDisabled();
    expect(screen.getByText("Installé")).toBeInTheDocument();
  });

  it("sans le droit de paramétrer, aucune installation n'est proposée", async () => {
    await pret(["consulter"]);
    expect(screen.queryByRole("button", { name: "Installer les contrôles choisis" })).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /^PIE-DOUBLON/ })).toBeDisabled();
    expect(screen.getByText(/droit de paramétrer/)).toBeInTheDocument();
  });

  it("installe les contrôles cochés à la date d'effet, en brouillon, puis rafraîchit", async () => {
    const { s } = await pret();
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/controles\/bibliotheque\/installer\/$/, reponse: () => reponseFausse(201, { crees: ["PIE-DOUBLON"], deja_presents: [] }) });
    await cocher("PIE-DOUBLON");
    await userEvent.type(screen.getByLabelText("Date d'effet"), "2026-04-01");
    await userEvent.click(screen.getByRole("button", { name: "Installer les contrôles choisis" }));
    expect(await screen.findByText("1 contrôle installé en brouillon : PIE-DOUBLON.")).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({ codes: ["PIE-DOUBLON"], valid_from: "2026-04-01" });
  });

  it("exige au moins un contrôle et une date avant tout envoi", async () => {
    const { s } = await pret();
    await userEvent.click(screen.getByRole("button", { name: "Installer les contrôles choisis" }));
    expect(await screen.findByText("Cochez au moins un contrôle à installer.")).toBeInTheDocument();
    await cocher("PIE-DOUBLON");
    await userEvent.click(screen.getByRole("button", { name: "Installer les contrôles choisis" }));
    expect(await screen.findByText("Choisissez la date d'effet.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("un contrôle de risque coché propose son seuil, envoyé exact (pourcentage en chaîne, jours en entier)", async () => {
    const { s } = await pret();
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/controles\/bibliotheque\/installer\/$/, reponse: () => reponseFausse(201, { crees: ["RIS-AVANCE-NON-APUREE", "RIS-CATEGORIE-SEUIL"], deja_presents: [] }) });
    await cocher("RIS-CATEGORIE-SEUIL");
    await cocher("RIS-AVANCE-NON-APUREE");
    await userEvent.type(screen.getByLabelText("Seuil de RIS-CATEGORIE-SEUIL (%)"), "75.5");
    await userEvent.type(screen.getByLabelText("Délai de RIS-AVANCE-NON-APUREE (jours)"), "60");
    await userEvent.type(screen.getByLabelText("Date d'effet"), "2026-04-01");
    await userEvent.click(screen.getByRole("button", { name: "Installer les contrôles choisis" }));
    await screen.findByText(/contrôles installés en brouillon/);
    expect(ecritures(s)[0]?.corps).toEqual({
      codes: ["RIS-AVANCE-NON-APUREE", "RIS-CATEGORIE-SEUIL"],
      valid_from: "2026-04-01",
      seuils: { "RIS-CATEGORIE-SEUIL": "75.5", "RIS-AVANCE-NON-APUREE": 60 },
    });
  });

  it("un contrôle de risque coché sans seuil n'envoie aucun seuil : le serveur applique le sien", async () => {
    const { s } = await pret();
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/controles\/bibliotheque\/installer\/$/, reponse: () => reponseFausse(201, { crees: ["RIS-CATEGORIE-SEUIL"], deja_presents: [] }) });
    await cocher("RIS-CATEGORIE-SEUIL");
    await userEvent.type(screen.getByLabelText("Date d'effet"), "2026-04-01");
    await userEvent.click(screen.getByRole("button", { name: "Installer les contrôles choisis" }));
    await screen.findByText("1 contrôle installé en brouillon : RIS-CATEGORIE-SEUIL.");
    expect(ecritures(s)[0]?.corps).toEqual({ codes: ["RIS-CATEGORIE-SEUIL"], valid_from: "2026-04-01" });
  });

  it.each([
    ["Seuil de RIS-CATEGORIE-SEUIL (%)", "101"],
    ["Seuil de RIS-CATEGORIE-SEUIL (%)", "-1"],
    ["Seuil de RIS-CATEGORIE-SEUIL (%)", "abc"],
    ["Seuil de RIS-CATEGORIE-SEUIL (%)", "1e2"],
  ])("refuse le pourcentage « %s = %s » avant tout envoi", async (etiquette, valeur) => {
    const { s } = await pret();
    await cocher("RIS-CATEGORIE-SEUIL");
    await userEvent.type(screen.getByLabelText(etiquette), valeur);
    await userEvent.type(screen.getByLabelText("Date d'effet"), "2026-04-01");
    await userEvent.click(screen.getByRole("button", { name: "Installer les contrôles choisis" }));
    expect(await screen.findByText("Un pourcentage entre 0 et 100, par exemple 75.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it.each(["0", "-3", "1.5", "abc"])("refuse le délai « %s » avant tout envoi", async (valeur) => {
    const { s } = await pret();
    await cocher("RIS-AVANCE-NON-APUREE");
    await userEvent.type(screen.getByLabelText("Délai de RIS-AVANCE-NON-APUREE (jours)"), valeur);
    await userEvent.type(screen.getByLabelText("Date d'effet"), "2026-04-01");
    await userEvent.click(screen.getByRole("button", { name: "Installer les contrôles choisis" }));
    expect(await screen.findByText("Un nombre entier de jours supérieur à 0, par exemple 60.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("affiche le refus du serveur sans effacer la saisie", async () => {
    const { s } = await pret();
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/controles\/bibliotheque\/installer\/$/, reponse: () => reponseFausse(422, { code: "REGLE_INVALIDE", message: "Le seuil est invalide pour RIS-CATEGORIE-SEUIL" }) });
    await cocher("PIE-DOUBLON");
    await userEvent.type(screen.getByLabelText("Date d'effet"), "2026-04-01");
    await userEvent.click(screen.getByRole("button", { name: "Installer les contrôles choisis" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Le seuil est invalide");
    expect(screen.getByLabelText("Date d'effet")).toHaveValue("2026-04-01");
  });
});
