import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";
import { projet, reponseFausse, unCompte } from "../../test/serveur";
import type { FauxServeur } from "../../test/serveur";
import type { ProfilDetail } from "./types";

afterEach(nettoyer);

const BASE = /^\/projets\/id-P1\/accords\/a1\/profils-decaissement\//;
const ACCORD = { id: "a1", numero: "DON-1", libelle: "Don 1", bailleur: "BAD", statut: "actif", devise: "USD" };

function profil(version: number, status: ProfilDetail["status"], extra: Partial<ProfilDetail> = {}): ProfilDetail {
  return {
    id: `p${version}`,
    accord: "DON-1",
    version,
    status,
    valid_from: `2026-0${version}-01`,
    valid_to: null,
    regime: "transaction_based",
    exigence: null,
    rejection_reason: "",
    effectiveness_date: "2026-01-01",
    eligibility_date: null,
    closing_date: "2030-12-31",
    disbursement_deadline: "2031-04-30",
    methodes: [
      { method: "reimbursement", is_enabled: true, supporting_docs: ["ifr", "soe"], full_doc_threshold: null, min_application_amount: "100.00", min_application_pct_of_ceiling: null },
      { method: "advance", is_enabled: false, supporting_docs: [], full_doc_threshold: null, min_application_amount: null, min_application_pct_of_ceiling: null },
    ],
    regles: [
      { category: "SERVICES", allocation: "400000.00", funding_rate: "0.8500", tax_basis: "taxes_included", eligibility_from: null, eligibility_to: null, requires_prior_review: false, max_per_contract: null, fin_propre_a_la_categorie: false },
    ],
    comptes: [{ compte: "CD-1", devise: "USD", ceiling_kind: "fixed", ceiling_amount: "500000.00", replenishment_threshold_pct: "50" }],
    ...extra,
  };
}

const COMPLET = { complet: true, bloquantes: [], avertissements: [] };

interface Etat {
  profils: ProfilDetail[];
}

async function ouvrir(
  profils: ProfilDetail[],
  { operations = ["consulter", "valider", "parametrer"], chemin = "/profils-decaissement?projet=id-P1&accord=a1&profil=p2", retardLecture }: { operations?: Parameters<typeof projet>[1]; chemin?: string; retardLecture?: Promise<void> } = {},
) {
  const etat: Etat = { profils };
  const m = await monter(chemin, { comptes: [unCompte("amina", { projets: [projet("P1", operations)] })], connecteComme: "amina" });
  const s: FauxServeur = m.serveur;
  const DETAIL = new Set(["methodes", "regles", "comptes", "completude"]);
  const resume = (p: ProfilDetail) => Object.fromEntries(Object.entries(p).filter(([cle]) => !DETAIL.has(cle)));
  s.routes.push(
    { motif: /^\/projets\/id-P1\/accords\/$/, reponse: () => [ACCORD] },
    { motif: new RegExp(`${BASE.source}$`), reponse: async () => { if (retardLecture) await retardLecture; return etat.profils.map(resume); } },
    { motif: new RegExp(`${BASE.source}(p\\d+)/$`), reponse: async (t) => { if (retardLecture) await retardLecture; return etat.profils.find((p) => p.id === t[1]) ?? reponseFausse(404, { code: "INTROUVABLE", message: "Introuvable" }); } },
  );
  return { m, s, etat };
}

const brouillon = () => profil(2, "draft", { completude: COMPLET });
const actions = (s: FauxServeur) => s.appels.filter((a) => a.methode !== "GET" && a.url.includes("profils-decaissement"));

describe("profils de décaissement : consulter", () => {
  it("affiche un état de chargement avant les données", async () => {
    let liberer: () => void = () => {};
    const retard = new Promise<void>((r) => (liberer = r));
    await ouvrir([profil(1, "active")], { chemin: "/profils-decaissement?projet=id-P1&accord=a1", retardLecture: retard });
    expect(await screen.findByRole("status", { name: "Chargement en cours" })).toBeInTheDocument();
    liberer();
    expect(await screen.findByRole("table", { name: "Versions du profil" })).toBeInTheDocument();
  });

  it("une liste vide dit clairement qu'il n'y a encore aucun profil", async () => {
    await ouvrir([], { chemin: "/profils-decaissement?projet=id-P1&accord=a1" });
    expect(await screen.findByText("Cet accord n'a encore aucun profil de décaissement.")).toBeInTheDocument();
  });

  it("liste les versions dans l'ordre avec leur état en toutes lettres", async () => {
    await ouvrir([profil(1, "superseded"), profil(2, "draft"), profil(3, "rejected")], { chemin: "/profils-decaissement?projet=id-P1&accord=a1" });
    const table = await screen.findByRole("table", { name: "Versions du profil" });
    const lignes = within(table).getAllByRole("row").slice(1);
    expect(lignes.map((l) => within(l).getAllByRole("cell")[0]?.textContent)).toEqual(["1", "2", "3"]);
    expect(within(lignes[0]!).getByText("Remplacé")).toBeInTheDocument();
    expect(within(lignes[1]!).getByText("Brouillon")).toBeInTheDocument();
    expect(within(lignes[2]!).getByText("Rejeté")).toBeInTheDocument();
  });

  it("ouvrir une version affiche ses méthodes, ses règles (taux en chaîne) et ses comptes", async () => {
    await ouvrir([profil(1, "active"), brouillon()], { chemin: "/profils-decaissement?projet=id-P1&accord=a1" });
    await userEvent.click(await screen.findByRole("button", { name: "Ouvrir la version 2" }));
    expect(await screen.findByRole("heading", { name: "Version 2 de l'accord DON-1" })).toBeInTheDocument();
    expect(screen.getByText("Remboursement")).toBeInTheDocument();
    expect(screen.getByText("Pièces exigées : ifr, soe")).toBeInTheDocument();
    expect(screen.getByText("SERVICES")).toBeInTheDocument();
    expect(screen.getByText("0.8500")).toBeInTheDocument(); // chaîne telle que le serveur la rend : « 0.85 » trahirait un Number
    expect(screen.getByText("CD-1")).toBeInTheDocument();
  });

  it("un refus de lecture du serveur s'affiche tel quel, jamais « undefined »", async () => {
    const { s } = await ouvrir([brouillon()]);
    s.routes.unshift({ motif: new RegExp(`${BASE.source}p2/$`), reponse: () => reponseFausse(403, { code: "ACCES_REFUSE", message: "Vous n'êtes pas habilité à consulter ce profil" }) });
    expect(await screen.findByText("Vous n'êtes pas habilité à consulter ce profil")).toBeInTheDocument();
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument();
  });

  it("est accessible", async () => {
    const { m } = await ouvrir([profil(1, "active"), brouillon()]);
    await screen.findByRole("heading", { name: "Version 2 de l'accord DON-1" });
    expect(await violations(m.rendu.container)).toEqual([]);
  });
});

describe("profils de décaissement : décider", () => {
  it("Valider est désactivé tant que le brouillon est incomplet et chaque point bloquant est lu", async () => {
    const incomplet = profil(2, "draft", {
      completude: { complet: false, bloquantes: [{ code: "SANS_METHODE", message: "Aucune méthode n'est autorisée" }, { code: "TAUX", message: "Une règle n'a pas de taux" }], avertissements: [{ code: "FIN", message: "La fin dépasse celle de l'accord" }] },
    });
    await ouvrir([incomplet]);
    expect(await screen.findByText("Aucune méthode n'est autorisée")).toBeInTheDocument();
    expect(screen.getByText("Une règle n'a pas de taux")).toBeInTheDocument();
    expect(screen.getByText("La fin dépasse celle de l'accord")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Valider" })).toBeDisabled();
  });

  it("valider un brouillon complet appelle la bonne URL et rafraîchit le profil", async () => {
    const { s, etat } = await ouvrir([brouillon()]);
    s.routes.push({
      methode: "POST",
      motif: new RegExp(`${BASE.source}p2/valider/$`),
      reponse: () => {
        etat.profils = [profil(2, "validated")];
        return etat.profils[0];
      },
    });
    await userEvent.click(await screen.findByRole("button", { name: "Valider" }));
    expect(await screen.findByText("Profil validé.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Activer" })).toBeInTheDocument();
    expect(actions(s).map((a) => `${a.methode} ${a.url}`)).toEqual(["POST /api/v1/projets/id-P1/accords/a1/profils-decaissement/p2/valider/"]);
  });

  it("valider puis activer appellent les bonnes URL dans le bon ordre", async () => {
    const { s, etat } = await ouvrir([brouillon()]);
    s.routes.push(
      { methode: "POST", motif: new RegExp(`${BASE.source}p2/valider/$`), reponse: () => (etat.profils = [profil(2, "validated")])[0] },
      { methode: "POST", motif: new RegExp(`${BASE.source}p2/activer/$`), reponse: () => (etat.profils = [profil(2, "active")])[0] },
    );
    await userEvent.click(await screen.findByRole("button", { name: "Valider" }));
    await userEvent.click(await screen.findByRole("button", { name: "Activer" }));
    expect(await screen.findByText("Profil activé.")).toBeInTheDocument();
    expect(actions(s).map((a) => a.url.split("/").slice(-2, -1)[0])).toEqual(["valider", "activer"]);
  });

  it("un 403 sur Valider affiche le message du serveur et laisse le profil inchangé", async () => {
    const { s } = await ouvrir([brouillon()]);
    s.routes.push({ methode: "POST", motif: new RegExp(`${BASE.source}p2/valider/$`), reponse: () => reponseFausse(403, { code: "ACCES_REFUSE", message: "Vous n'êtes pas habilité à valider" }) });
    await userEvent.click(await screen.findByRole("button", { name: "Valider" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Vous n'êtes pas habilité à valider");
    expect(screen.getByRole("button", { name: "Valider" })).toBeEnabled();
  });

  it("un double clic n'envoie qu'une seule demande", async () => {
    let liberer: () => void = () => {};
    const attente = new Promise<void>((r) => (liberer = r));
    const { s, etat } = await ouvrir([brouillon()]);
    s.routes.push({ methode: "POST", motif: new RegExp(`${BASE.source}p2/valider/$`), reponse: async () => { await attente; return (etat.profils = [profil(2, "validated")])[0]; } });
    const bouton = await screen.findByRole("button", { name: "Valider" });
    await userEvent.dblClick(bouton);
    liberer();
    await screen.findByText("Profil validé.");
    expect(actions(s)).toHaveLength(1);
  });

  it("rejeter exige un motif avant tout envoi puis l'envoie", async () => {
    const { s, etat } = await ouvrir([profil(2, "validated")]);
    s.routes.push({ methode: "POST", motif: new RegExp(`${BASE.source}p2/rejeter/$`), reponse: (_t, _r, corps) => (etat.profils = [profil(2, "rejected", { rejection_reason: (corps as { motif: string }).motif })])[0] });
    await userEvent.click(await screen.findByRole("button", { name: "Rejeter" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirmer le rejet" }));
    expect(screen.getByText("Saisissez le motif du rejet.")).toBeInTheDocument();
    expect(actions(s)).toHaveLength(0);
    await userEvent.type(screen.getByLabelText("Motif du rejet"), "Taux non conforme");
    await userEvent.click(screen.getByRole("button", { name: "Confirmer le rejet" }));
    expect(await screen.findByText("Profil rejeté.")).toBeInTheDocument();
    expect(actions(s)[0]?.corps).toEqual({ motif: "Taux non conforme" });
    expect(await screen.findByText("Motif du rejet : Taux non conforme")).toBeInTheDocument();
  });

  it("supprimer demande une confirmation ; annuler n'appelle rien, confirmer supprime", async () => {
    const { s } = await ouvrir([brouillon()]);
    s.routes.push({ methode: "DELETE", motif: new RegExp(`${BASE.source}p2/$`), reponse: () => ({ supprime: true }) });
    await userEvent.click(await screen.findByRole("button", { name: "Supprimer le brouillon" }));
    expect(screen.getByText("Supprimer définitivement ce brouillon ?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
    expect(actions(s)).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Supprimer le brouillon" }));
    await userEvent.click(screen.getByRole("button", { name: "Oui, supprimer" }));
    expect(await screen.findByText("Brouillon supprimé.")).toBeInTheDocument();
    expect(actions(s).map((a) => a.methode)).toEqual(["DELETE"]);
  });

  it("sans droit de décision, aucune action n'est proposée et le profil reste lisible", async () => {
    await ouvrir([brouillon()], { operations: ["consulter"] });
    expect(await screen.findByRole("heading", { name: "Version 2 de l'accord DON-1" })).toBeInTheDocument();
    for (const nom of ["Valider", "Activer", "Rejeter", "Supprimer le brouillon"]) {
      expect(screen.queryByRole("button", { name: nom })).not.toBeInTheDocument();
    }
    expect(screen.getByText(/vous n'avez pas sur ce projet/)).toBeInTheDocument();
  });

  it("changer de projet puis d'accord charge leurs profils", async () => {
    const { s } = await ouvrir([profil(1, "active")], { chemin: "/profils-decaissement" });
    expect(await screen.findByText("Choisissez un projet")).toBeInTheDocument();
    const page = within(screen.getByRole("main")); // l'en-tête a aussi un sélecteur « Projet »
    await userEvent.selectOptions(page.getByLabelText("Projet"), "id-P1");
    await userEvent.selectOptions(await page.findByLabelText("Accord"), "a1");
    expect(await screen.findByRole("table", { name: "Versions du profil" })).toBeInTheDocument();
    await waitFor(() => expect(s.appels.some((a) => a.url.endsWith("/accords/a1/profils-decaissement/"))).toBe(true));
  });
});
