import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";
import { projet, reponseFausse, unCompte } from "../../test/serveur";
import type { FauxServeur } from "../../test/serveur";
import type { CleDetail, CleResume, VersionCle } from "./types";

afterEach(nettoyer);

const version = (n: number, extra: Partial<VersionCle> = {}): VersionCle => ({
  id: `v${n}`,
  version: n,
  valid_from: `2026-0${n}-01`,
  valid_to: null,
  porteur: "DON-1",
  motif: "",
  parts: [
    { accord: "DON-1", part: "0.600000" },
    { accord: "PRET-2", part: "0.400000" },
  ],
  ...extra,
});
const cle = (id: string, code: string, v: VersionCle | null = version(1)): CleResume => ({ id, code, label: { fr: `Clé ${code}`, en: `Key ${code}` }, version_en_vigueur: v });
const ACCORDS = [
  { id: "a1", numero: "DON-1", bailleur: "BAD", statut: "actif" },
  { id: "a2", numero: "PRET-2", bailleur: "IDA", statut: "actif" },
  { id: "a3", numero: "DON-3", bailleur: "UE", statut: "actif" },
];

async function ouvrir(
  cles: CleResume[],
  { operations = ["consulter", "parametrer"], chemin = "/cles-cofinancement?projet=id-P1", retard }: { operations?: Parameters<typeof projet>[1]; chemin?: string; retard?: Promise<void> } = {},
) {
  const etat = { cles };
  const m = await monter(chemin, { comptes: [unCompte("amina", { projets: [projet("P1", operations)] })], connecteComme: "amina" });
  const s: FauxServeur = m.serveur;
  s.routes.push(
    { motif: /^\/projets\/id-P1\/cles-cofinancement\/$/, reponse: async () => { if (retard) await retard; return etat.cles; } },
    {
      motif: /^\/projets\/id-P1\/cles-cofinancement\/(k\d)\/$/,
      reponse: (t): CleDetail | unknown => {
        const c = etat.cles.find((x) => x.id === t[1]);
        return c ? { id: c.id, code: c.code, label: c.label, versions: c.version_en_vigueur ? [c.version_en_vigueur] : [] } : reponseFausse(404, { code: "INTROUVABLE", message: "Introuvable" });
      },
    },
    { motif: /^\/projets\/id-P1\/accords\/$/, reponse: () => ACCORDS },
  );
  return { m, s, etat };
}
const ecritures = (s: FauxServeur) => s.appels.filter((a) => a.methode === "POST");

describe("clés de cofinancement : consulter", () => {
  it("affiche un état de chargement", async () => {
    let liberer: () => void = () => {};
    await ouvrir([cle("k1", "COF")], { retard: new Promise<void>((r) => (liberer = r)) });
    expect(await screen.findByRole("status", { name: "Chargement en cours" })).toBeInTheDocument();
    liberer();
    expect(await screen.findByRole("table", { name: "Clés du projet" })).toBeInTheDocument();
  });

  it("une liste vide le dit clairement", async () => {
    await ouvrir([]);
    expect(await screen.findByText("Ce projet n'a encore aucune clé de cofinancement.")).toBeInTheDocument();
  });

  it("liste les clés avec les parts de leur version en vigueur en pourcentage exact", async () => {
    await ouvrir([cle("k1", "COF"), cle("k2", "SANS", null)]);
    const table = await screen.findByRole("table", { name: "Clés du projet" });
    const lignes = within(table).getAllByRole("row").slice(1);
    expect(within(lignes[0]!).getByText("DON-1 60 %")).toBeInTheDocument();
    expect(within(lignes[0]!).getByText("PRET-2 40 %")).toBeInTheDocument();
    expect(within(lignes[1]!).getByText("Aucune version en vigueur")).toBeInTheDocument();
  });

  it("convertit une part en pourcentage sans erreur de flottant (0.07 × 100 = 7, pas 7.000000000000001)", async () => {
    await ouvrir([cle("k1", "COF", version(1, { parts: [{ accord: "DON-1", part: "0.070000" }, { accord: "PRET-2", part: "0.930000" }] }))]);
    expect(await screen.findByText("DON-1 7 %")).toBeInTheDocument();
    expect(screen.getByText("PRET-2 93 %")).toBeInTheDocument();
  });

  it("le détail montre toutes les versions avec leur porteur d'arrondi", async () => {
    await ouvrir([cle("k1", "COF")], { chemin: "/cles-cofinancement?projet=id-P1&cle=k1" });
    expect(await screen.findByRole("heading", { name: "Clé COF" })).toBeInTheDocument();
    const versions = screen.getByRole("table", { name: "Versions de la clé" });
    expect(versions).toHaveTextContent("DON-1");
    expect(within(versions).getByText("Porteur : DON-1")).toBeInTheDocument();
  });

  it("un refus de lecture du serveur s'affiche tel quel", async () => {
    const { s } = await ouvrir([]);
    s.routes.unshift({ motif: /^\/projets\/id-P1\/cles-cofinancement\/$/, reponse: () => reponseFausse(403, { code: "ACCES_REFUSE", message: "Vous n'êtes pas habilité à consulter les clés" }) });
    expect(await screen.findByText("Vous n'êtes pas habilité à consulter les clés")).toBeInTheDocument();
  });

  it("est accessible", async () => {
    const { m } = await ouvrir([cle("k1", "COF")], { chemin: "/cles-cofinancement?projet=id-P1&cle=k1" });
    await screen.findByRole("heading", { name: "Clé COF" });
    expect(await violations(m.rendu.container)).toEqual([]);
  });
});

describe("clés de cofinancement : créer une clé", () => {
  it("sans le droit de paramétrer, aucun formulaire", async () => {
    await ouvrir([cle("k1", "COF")], { operations: ["consulter"] });
    await screen.findByRole("table", { name: "Clés du projet" });
    expect(screen.queryByRole("button", { name: "Créer la clé" })).not.toBeInTheDocument();
    expect(screen.getByText(/droit de paramétrer/)).toBeInTheDocument();
  });

  it("exige un code et un libellé avant tout envoi", async () => {
    const { s } = await ouvrir([]);
    await screen.findByText("Ce projet n'a encore aucune clé de cofinancement.");
    await userEvent.click(screen.getByRole("button", { name: "Créer la clé" }));
    expect(await screen.findByText("Saisissez le code de la clé.")).toBeInTheDocument();
    expect(screen.getByText("Saisissez au moins un libellé.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("refuse un code sans aucun libellé avant tout envoi", async () => {
    const { s } = await ouvrir([]);
    await screen.findByText("Ce projet n'a encore aucune clé de cofinancement.");
    await userEvent.type(screen.getByLabelText("Code de la clé"), "COF");
    await userEvent.click(screen.getByRole("button", { name: "Créer la clé" }));
    expect(await screen.findByText("Saisissez au moins un libellé.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("envoie le code et les libellés non vides, puis rafraîchit", async () => {
    const { s, etat } = await ouvrir([]);
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/cles-cofinancement\/$/, reponse: (_t, _r, c) => { etat.cles = [cle("k9", (c as { code: string }).code, null)]; return reponseFausse(201, { id: "k9", code: "COF" }); } });
    await screen.findByText("Ce projet n'a encore aucune clé de cofinancement.");
    await userEvent.type(screen.getByLabelText("Code de la clé"), "COF");
    await userEvent.type(screen.getByLabelText("Libellé (français)"), "Cofinancement standard");
    await userEvent.click(screen.getByRole("button", { name: "Créer la clé" }));
    expect(await screen.findByText("Clé créée.")).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({ code: "COF", label: { fr: "Cofinancement standard" } });
    expect(await screen.findByText("COF")).toBeInTheDocument();
  });

  it("affiche le refus du serveur pour un code déjà utilisé", async () => {
    const { s } = await ouvrir([]);
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/cles-cofinancement\/$/, reponse: () => reponseFausse(422, { code: "REGLE_INVALIDE", message: "Une clé « COF » existe déjà pour ce projet" }) });
    await screen.findByText("Ce projet n'a encore aucune clé de cofinancement.");
    await userEvent.type(screen.getByLabelText("Code de la clé"), "COF");
    await userEvent.type(screen.getByLabelText("Libellé (français)"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Créer la clé" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("existe déjà pour ce projet");
  });
});

describe("clés de cofinancement : nouvelle version", () => {
  async function pret() {
    const o = await ouvrir([cle("k1", "COF")], { chemin: "/cles-cofinancement?projet=id-P1&cle=k1" });
    await screen.findByRole("heading", { name: "Clé COF" });
    await screen.findByLabelText("DON-1 · BAD");
    return o;
  }
  const part = (numero: string) => screen.getByLabelText(`Part de ${numero} (%)`);
  const choisir = (nom: string) => userEvent.click(screen.getByLabelText(nom));

  async function remplir(parts: Record<string, string>, { porteur = "DON-1", date = "2027-01-01" } = {}) {
    for (const [numero, valeur] of Object.entries(parts)) {
      await choisir(`${numero} · ${numero.startsWith("DON-1") ? "BAD" : numero === "PRET-2" ? "IDA" : "UE"}`);
      await userEvent.type(part(numero), valeur);
    }
    await userEvent.selectOptions(screen.getByLabelText("Porteur de l'arrondi"), porteur);
    await userEvent.type(screen.getByLabelText("Date d'effet"), date);
  }

  it("envoie des parts en chaînes dont le total est exactement 100 %", async () => {
    const { s } = await pret();
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/cles-cofinancement\/k1\/versions\/$/, reponse: () => reponseFausse(201, version(2)) });
    await remplir({ "DON-1": "60", "PRET-2": "40" });
    await userEvent.type(screen.getByLabelText("Motif"), "Nouvelle répartition");
    await userEvent.click(screen.getByRole("button", { name: "Créer la version" }));
    expect(await screen.findByText("Version créée.")).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({ parts: { "DON-1": "60", "PRET-2": "40" }, porteur: "DON-1", valid_from: "2027-01-01", motif: "Nouvelle répartition" });
  });

  it("calcule le total sans erreur de flottant : 0,1 + 66,6 + 33,3 (dans l'ordre des numéros) font bien 100 (en flottant : 99,99999999999999)", async () => {
    const { s } = await pret();
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/cles-cofinancement\/k1\/versions\/$/, reponse: () => reponseFausse(201, version(2)) });
    await remplir({ "DON-1": "0.1", "DON-3": "66.6", "PRET-2": "33.3" });
    expect(screen.getByText("Total : 100 %")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Créer la version" }));
    expect(await screen.findByText("Version créée.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(1);
  });

  it.each([
    ["99.99", "0.01", "99.99"],
    ["100.01", "0", "100.01"],
  ])("refuse un total à un centième de 100 % (%s) : l'exactitude n'est pas une tolérance", async (a, _b, attendu) => {
    const { s } = await pret();
    await remplir({ "DON-1": a });
    expect(screen.getByText(`Total : ${attendu} %`)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Créer la version" }));
    expect(await screen.findByText(`Le total des parts doit être exactement 100 % (actuellement ${attendu} %).`)).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("refuse un total différent de 100 % avant tout envoi et dit le total saisi", async () => {
    const { s } = await pret();
    await remplir({ "DON-1": "60", "PRET-2": "30" });
    expect(screen.getByText("Total : 90 %")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Créer la version" }));
    expect(await screen.findByText("Le total des parts doit être exactement 100 % (actuellement 90 %).")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it.each(["abc", "0", "-5", "1e2", "1.2.3"])("refuse la part « %s » avant tout envoi", async (valeur) => {
    const { s } = await pret();
    await remplir({ "DON-1": valeur, "PRET-2": "40" });
    await userEvent.click(screen.getByRole("button", { name: "Créer la version" }));
    expect(await screen.findByText("Chaque part est un nombre strictement positif, par exemple 60 ou 33.5.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("exige au moins un accord, un porteur parmi les accords choisis et une date", async () => {
    const { s } = await pret();
    await userEvent.click(screen.getByRole("button", { name: "Créer la version" }));
    expect(await screen.findByText("Choisissez au moins un accord.")).toBeInTheDocument();
    await remplir({ "DON-1": "100" }, { date: "2027-01-01" });
    await userEvent.clear(screen.getByLabelText("Date d'effet"));
    await userEvent.click(screen.getByRole("button", { name: "Créer la version" }));
    expect(await screen.findByText("Choisissez la date d'effet.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("affiche le refus du serveur (accord clos, date trop ancienne) sans effacer la saisie", async () => {
    const { s } = await pret();
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/cles-cofinancement\/k1\/versions\/$/, reponse: () => reponseFausse(422, { code: "REGLE_INVALIDE", message: "La nouvelle version doit prendre effet après le 2026-01-01" }) });
    await remplir({ "DON-1": "60", "PRET-2": "40" });
    await userEvent.click(screen.getByRole("button", { name: "Créer la version" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("doit prendre effet après le 2026-01-01");
    expect(part("DON-1")).toHaveValue("60");
  });

  it("un double clic n'envoie qu'une version", async () => {
    let liberer: () => void = () => {};
    const attente = new Promise<void>((r) => (liberer = r));
    const { s } = await pret();
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/cles-cofinancement\/k1\/versions\/$/, reponse: async () => { await attente; return reponseFausse(201, version(2)); } });
    await remplir({ "DON-1": "60", "PRET-2": "40" });
    await userEvent.dblClick(screen.getByRole("button", { name: "Créer la version" }));
    liberer();
    await screen.findByText("Version créée.");
    expect(ecritures(s)).toHaveLength(1);
  });
});
