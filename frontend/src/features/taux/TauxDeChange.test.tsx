import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";
import { projet, reponseFausse, unCompte } from "../../test/serveur";
import type { FauxServeur } from "../../test/serveur";
import type { TauxDeChange } from "./types";

afterEach(nettoyer);

const CATALOGUE = [
  { code: "DJF", label: { fr: "Franc djiboutien", en: "Djiboutian franc" }, decimales: 0 },
  { code: "EUR", label: { fr: "Euro", en: "Euro" }, decimales: 2 },
  { code: "USD", label: { fr: "Dollar des États-Unis", en: "US dollar" }, decimales: 2 },
];

const taux = (id: string, devise: string, date: string, valeur: string, type_taux: TauxDeChange["type_taux"] = "officiel"): TauxDeChange => ({
  id,
  devise,
  devise_id: devise,
  date,
  taux: valeur,
  type_taux,
  source: "BCD",
});

async function ouvrir(liste: TauxDeChange[], operations: Parameters<typeof projet>[1] = ["consulter", "parametrer"], retard?: Promise<void>) {
  const m = await monter("/taux-de-change", { comptes: [unCompte("amina", { projets: [projet("P1", operations)] })], connecteComme: "amina" });
  const etat = { liste };
  m.serveur.routes.push(
    {
      motif: /^\/taux\/$/,
      reponse: async (_t, recherche) => {
        if (retard) await retard;
        return etat.liste.filter((x) => (!recherche.get("devise") || x.devise === recherche.get("devise")) && (!recherche.get("type_taux") || x.type_taux === recherche.get("type_taux")));
      },
    },
    { motif: /^\/devises\/$/, reponse: () => CATALOGUE },
  );
  return { m, s: m.serveur as FauxServeur, etat };
}
const ecritures = (s: FauxServeur) => s.appels.filter((a) => a.methode === "POST" && a.url.endsWith("/taux/"));

async function remplir({ devise = "USD", date = "2026-03-01", valeur = "177.5", type = "officiel" } = {}) {
  await userEvent.selectOptions(screen.getByLabelText("Devise"), devise);
  await userEvent.type(screen.getByLabelText("Date"), date);
  await userEvent.selectOptions(screen.getByLabelText("Type de taux"), type);
  if (valeur) await userEvent.type(screen.getByLabelText("Taux (unités de monnaie de tenue pour 1 unité)"), valeur);
}

describe("taux de change : consulter", () => {
  it("affiche un état de chargement puis la liste", async () => {
    let liberer: () => void = () => {};
    await ouvrir([taux("t1", "USD", "2026-03-01", "177.5000000000")], ["consulter"], new Promise<void>((r) => (liberer = r)));
    expect(await screen.findByRole("status", { name: "Chargement en cours" })).toBeInTheDocument();
    liberer();
    expect(await screen.findByRole("table", { name: "Taux enregistrés" })).toBeInTheDocument();
  });

  it("une liste vide le dit clairement", async () => {
    await ouvrir([]);
    expect(await screen.findByText("Aucun taux enregistré pour ce filtre.")).toBeInTheDocument();
  });

  it("garde l'ordre du serveur et les taux tels quels, en chaîne", async () => {
    await ouvrir([taux("t2", "USD", "2026-04-01", "178.0000000000"), taux("t1", "EUR", "2026-03-01", "0.1000000000")]);
    const table = await screen.findByRole("table", { name: "Taux enregistrés" });
    const lignes = within(table).getAllByRole("row").slice(1);
    expect(lignes.map((l) => within(l).getAllByRole("cell")[0]?.textContent)).toEqual(["2026-04-01", "2026-03-01"]);
    expect(within(table).getByText("0.1000000000")).toBeInTheDocument(); // « 0.1 » trahirait un Number
    expect(within(table).getByText("178.0000000000")).toBeInTheDocument(); // « 178 » aussi
  });

  it("filtrer par devise redemande la liste avec ce filtre", async () => {
    const { s } = await ouvrir([taux("t1", "USD", "2026-03-01", "177.5"), taux("t2", "EUR", "2026-03-01", "190")]);
    await screen.findByRole("table", { name: "Taux enregistrés" });
    await userEvent.selectOptions(screen.getByLabelText("Filtrer par devise"), "EUR");
    expect(await screen.findByText("190")).toBeInTheDocument();
    expect(screen.queryByText("177.5")).not.toBeInTheDocument();
    expect(s.appels.some((a) => a.url.includes("devise=EUR"))).toBe(true);
  });

  it("un refus de lecture du serveur s'affiche tel quel", async () => {
    const { s } = await ouvrir([]);
    s.routes.unshift({ motif: /^\/taux\/$/, reponse: () => reponseFausse(403, { code: "ACCES_REFUSE", message: "Lecture refusée par le serveur" }) });
    await userEvent.selectOptions(await screen.findByLabelText("Filtrer par type de taux"), "budget");
    expect(await screen.findByText("Lecture refusée par le serveur")).toBeInTheDocument();
  });

  it("est accessible", async () => {
    const { m } = await ouvrir([taux("t1", "USD", "2026-03-01", "177.5")]);
    await screen.findByRole("table", { name: "Taux enregistrés" });
    expect(await violations(m.rendu.container)).toEqual([]);
  });
});

describe("taux de change : enregistrer", () => {
  it("sans le droit de paramétrer, aucun formulaire n'est proposé", async () => {
    await ouvrir([taux("t1", "USD", "2026-03-01", "177.5")], ["consulter"]);
    await screen.findByRole("table", { name: "Taux enregistrés" });
    expect(screen.queryByRole("button", { name: "Enregistrer le taux" })).not.toBeInTheDocument();
    expect(screen.getByText(/droit de paramétrer/)).toBeInTheDocument();
  });

  it("envoie le taux en chaîne, tel que saisi (virgule acceptée), puis rafraîchit la liste", async () => {
    const { s, etat } = await ouvrir([]);
    s.routes.push({
      methode: "POST",
      motif: /^\/taux\/$/,
      reponse: (_t, _r, corps) => {
        const c = corps as { devise: string; date: string; taux: string; type_taux: TauxDeChange["type_taux"] };
        etat.liste = [taux("t9", c.devise, c.date, c.taux, c.type_taux)];
        return reponseFausse(201, etat.liste[0]);
      },
    });
    await screen.findByText("Aucun taux enregistré pour ce filtre.");
    await remplir({ valeur: "177,5" });
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer le taux" }));
    expect(await screen.findByText("Taux enregistré.")).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({ devise: "USD", date: "2026-03-01", taux: "177.5", type_taux: "officiel" });
    expect(await screen.findByText("177.5")).toBeInTheDocument();
  });

  it("garde la précision d'un taux sans le passer par un nombre", async () => {
    const { s } = await ouvrir([]);
    s.routes.push({ methode: "POST", motif: /^\/taux\/$/, reponse: () => reponseFausse(201, taux("t9", "USD", "2026-03-01", "0.3")) });
    await screen.findByText("Aucun taux enregistré pour ce filtre.");
    await remplir({ valeur: "0.1000000000000000001" });
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer le taux" }));
    await screen.findByText("Taux enregistré.");
    expect((ecritures(s)[0]?.corps as { taux: string }).taux).toBe("0.1000000000000000001");
  });

  it.each(["abc", "0", "-1", "1e3", "1.2.3", "", " "])("refuse le taux « %s » avant tout envoi", async (valeur) => {
    const { s } = await ouvrir([]);
    await screen.findByText("Aucun taux enregistré pour ce filtre.");
    await remplir({ valeur });
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer le taux" }));
    expect(await screen.findByText("Saisissez un taux strictement positif, par exemple 177.5.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("exige une date avant tout envoi", async () => {
    const { s } = await ouvrir([]);
    await screen.findByText("Aucun taux enregistré pour ce filtre.");
    await userEvent.type(screen.getByLabelText("Taux (unités de monnaie de tenue pour 1 unité)"), "177.5");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer le taux" }));
    expect(await screen.findByText("Choisissez la date du taux.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("affiche le refus du serveur (taux déjà enregistré) sans rien effacer", async () => {
    const { s } = await ouvrir([]);
    s.routes.push({ methode: "POST", motif: /^\/taux\/$/, reponse: () => reponseFausse(422, { code: "REGLE_INVALIDE", message: "Un taux existe déjà à cette date pour ce type" }) });
    await screen.findByText("Aucun taux enregistré pour ce filtre.");
    await remplir();
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer le taux" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Un taux existe déjà à cette date pour ce type");
    expect(screen.getByLabelText("Taux (unités de monnaie de tenue pour 1 unité)")).toHaveValue("177.5");
  });

  it("un double clic n'envoie qu'un taux", async () => {
    let liberer: () => void = () => {};
    const attente = new Promise<void>((r) => (liberer = r));
    const { s } = await ouvrir([]);
    s.routes.push({ methode: "POST", motif: /^\/taux\/$/, reponse: async () => { await attente; return reponseFausse(201, taux("t9", "USD", "2026-03-01", "177.5")); } });
    await screen.findByText("Aucun taux enregistré pour ce filtre.");
    await remplir();
    await userEvent.dblClick(screen.getByRole("button", { name: "Enregistrer le taux" }));
    liberer();
    await screen.findByText("Taux enregistré.");
    expect(ecritures(s)).toHaveLength(1);
  });
});
