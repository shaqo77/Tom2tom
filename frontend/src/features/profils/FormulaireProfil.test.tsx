import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";
import { projet, reponseFausse, unCompte } from "../../test/serveur";
import type { FauxServeur } from "../../test/serveur";

afterEach(nettoyer);

const ACCORD = {
  id: "a1", numero: "DON-1", libelle: "Don 1", bailleur: "BAD", statut: "actif", devise: "USD",
  montant_courant: "1000000.00", date_effet: "2026-01-01", date_fin_eligibilite: "2030-12-31", date_cloture: null,
  date_limite_decaissement: null, format_numero_demande: "standard", suffixe_agence: "",
  categories: [{ id: "c1", code: "SERVICES", label: { fr: "Services" }, parent: null, plafond: null, devise: "USD" }],
  avenants: [],
};
const BROUILLON = {
  id: "p2", accord: "DON-1", version: 2, status: "draft", valid_from: "2026-02-01", valid_to: null, regime: "transaction_based",
  exigence: null, rejection_reason: "", effectiveness_date: "2026-01-01", eligibility_date: null, closing_date: null, disbursement_deadline: null,
  methodes: [{ method: "reimbursement", is_enabled: true, supporting_docs: ["soe"], full_doc_threshold: null, min_application_amount: "100.00", min_application_pct_of_ceiling: null }],
  regles: [{ category: "SERVICES", allocation: "400000.00", funding_rate: "0.8500", tax_basis: "taxes_included", eligibility_from: null, eligibility_to: null, requires_prior_review: false, max_per_contract: null, fin_propre_a_la_categorie: false }],
  comptes: [], completude: { complet: true, bloquantes: [], avertissements: [] },
};

async function ouvrir(chemin: string, operations: Parameters<typeof projet>[1] = ["consulter", "parametrer"], extra: (s: FauxServeur) => void = () => {}) {
  const m = await monter(chemin, { comptes: [unCompte("amina", { projets: [projet("P1", operations)] })], connecteComme: "amina" });
  m.serveur.routes.push(
    { motif: /^\/projets\/id-P1\/accords\/$/, reponse: () => [{ ...ACCORD }] },
    { motif: /^\/projets\/id-P1\/accords\/a1\/$/, reponse: () => ACCORD },
    { motif: /^\/projets\/id-P1\/comptes-bancaires\/$/, reponse: () => [{ id: "b1", code: "CD-1", type: "designe", devise: "USD" }] },
    { motif: /^\/projets\/id-P1\/accords\/a1\/profils-decaissement\/$/, reponse: () => [] },
    { motif: /^\/projets\/id-P1\/accords\/a1\/profils-decaissement\/p2\/$/, reponse: () => BROUILLON },
  );
  extra(m.serveur);
  return m.serveur;
}
const ecritures = (s: FauxServeur) => s.appels.filter((a) => a.methode === "POST" || a.methode === "PUT").filter((a) => a.url.includes("profils-decaissement"));
const CREATION = "/profils-decaissement?projet=id-P1&accord=a1&mode=creation";

async function remplirMinimum() {
  await fireDate(await screen.findByLabelText("Date d'effet"), "2026-03-01");
  await userEvent.click(screen.getByRole("checkbox", { name: "Remboursement" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "Règle pour la catégorie SERVICES" }));
  await userEvent.type(screen.getByLabelText("Allocation (SERVICES)"), "400000");
}
function fireDate(el: HTMLElement, valeur: string) {
  return userEvent.type(el, valeur);
}

describe("profils de décaissement : formulaire", () => {
  it("crée un brouillon avec un corps exact, le taux saisi « 0,85 » devenant « 0.85 »", async () => {
    const s = await ouvrir(CREATION, undefined, (sv) => sv.routes.push({ motif: /profils-decaissement\/$/, methode: "POST", reponse: () => ({ ...BROUILLON, id: "p3" }) } as never));
    await remplirMinimum();
    await userEvent.type(screen.getByLabelText("Taux de financement (SERVICES)"), "0,85");
    await userEvent.click(screen.getByRole("button", { name: "Créer le brouillon" }));
    await waitFor(() => expect(ecritures(s)).toHaveLength(1));
    const e = ecritures(s)[0]!;
    expect(e.methode).toBe("POST");
    const corps = e.corps as { valid_from: string; methodes: { method: string }[]; regles: { category: string; funding_rate: string; allocation: string }[] };
    expect(corps.valid_from).toBe("2026-03-01");
    expect(corps.methodes[0]?.method).toBe("reimbursement");
    expect(corps.regles[0]).toMatchObject({ category: "SERVICES", funding_rate: "0.85", allocation: "400000" });
  });

  it("refuse un taux de 1,5 sans rien envoyer et dit pourquoi", async () => {
    const s = await ouvrir(CREATION);
    await remplirMinimum();
    await userEvent.type(screen.getByLabelText("Taux de financement (SERVICES)"), "1,5");
    await userEvent.click(screen.getByRole("button", { name: "Créer le brouillon" }));
    expect(await screen.findByText(/Le taux de SERVICES doit être supérieur à 0/)).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("affiche tel quel le refus 422 du serveur", async () => {
    const s = await ouvrir(CREATION, undefined, (sv) => sv.routes.push({ motif: /profils-decaissement\/$/, methode: "POST", reponse: () => reponseFausse(422, { code: "PROFIL_INVALIDE", message: "Une version est déjà en brouillon" }) } as never));
    await remplirMinimum();
    await userEvent.type(screen.getByLabelText("Taux de financement (SERVICES)"), "0.85");
    await userEvent.click(screen.getByRole("button", { name: "Créer le brouillon" }));
    expect(await screen.findByText("Une version est déjà en brouillon")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(1);
  });

  it("un double clic n'envoie qu'une seule création", async () => {
    const s = await ouvrir(CREATION, undefined, (sv) => sv.routes.push({ motif: /profils-decaissement\/$/, methode: "POST", reponse: async () => { await new Promise((r) => setTimeout(r, 50)); return { ...BROUILLON, id: "p3" }; } } as never));
    await remplirMinimum();
    await userEvent.type(screen.getByLabelText("Taux de financement (SERVICES)"), "0.85");
    const bouton = screen.getByRole("button", { name: "Créer le brouillon" });
    await userEvent.dblClick(bouton);
    await waitFor(() => expect(ecritures(s).length).toBeGreaterThan(0));
    expect(ecritures(s)).toHaveLength(1);
  });

  it("l'édition part des valeurs du brouillon et envoie un PUT", async () => {
    const s = await ouvrir("/profils-decaissement?projet=id-P1&accord=a1&profil=p2&mode=edition", undefined, (sv) => sv.routes.push({ motif: /profils-decaissement\/p2\/$/, methode: "PUT", reponse: () => BROUILLON } as never));
    expect(await screen.findByLabelText("Taux de financement (SERVICES)")).toHaveValue("0.8500");
    expect(screen.getByLabelText("Allocation (SERVICES)")).toHaveValue("400000.00");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer les modifications" }));
    await waitFor(() => expect(ecritures(s)).toHaveLength(1));
    expect(ecritures(s)[0]?.methode).toBe("PUT");
    expect(ecritures(s)[0]?.url).toContain("/p2/");
  });

  it("avertit quand la fin propre d'une catégorie dépasse celle de l'accord", async () => {
    await ouvrir(CREATION);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Règle pour la catégorie SERVICES" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Fin propre à la catégorie (SERVICES)" }));
    await userEvent.type(screen.getByLabelText("Éligible jusqu'au (SERVICES)"), "2031-06-30");
    expect(await screen.findByText(/dépasse celle de l'accord \(2030-12-31\)/)).toBeInTheDocument();
  });

  it("sans droit de paramétrage, aucun bouton de création ni de modification", async () => {
    await ouvrir("/profils-decaissement?projet=id-P1&accord=a1&profil=p2", ["consulter"]);
    await screen.findByRole("heading", { name: /Version 2/ });
    expect(screen.queryByRole("button", { name: "Nouveau profil" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Modifier" })).not.toBeInTheDocument();
  });

  it("avec le droit, « Nouveau profil » ouvre le formulaire accessible", async () => {
    await ouvrir("/profils-decaissement?projet=id-P1&accord=a1");
    await userEvent.click(await screen.findByRole("button", { name: "Nouveau profil" }));
    expect(await screen.findByRole("button", { name: "Créer le brouillon" })).toBeInTheDocument();
    expect(await violations(document.body)).toEqual([]);
  });
});
