import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";
import { projet, reponseFausse, unCompte } from "../../test/serveur";
import type { FauxServeur } from "../../test/serveur";

afterEach(nettoyer);

const A1 = {
  id: "a1", numero: "DON-1", libelle: "Don 1", bailleur: "BAD", nature: "don", statut: "brouillon", devise: "USD",
  montant_initial: "1000000.00", montant_courant: "1000000.00", date_effet: null, date_fin_eligibilite: null, date_cloture: null,
  date_limite_decaissement: null, format_numero_demande: "standard", suffixe_agence: "",
};
const DETAIL = { ...A1, categories: [{ id: "c1", code: "BIENS", label: { fr: "Biens" }, parent: null, plafond: null, devise: "USD" }], avenants: [] };

const bailleurs = [{ id: "b1", code: "BAD", nom: "Banque africaine" }];

async function ouvrir(chemin: string, operations: Parameters<typeof projet>[1] = ["consulter", "parametrer"], extra: (s: FauxServeur) => void = () => {}) {
  const m = await monter(chemin, { comptes: [unCompte("amina", { projets: [projet("P1", operations)] })], connecteComme: "amina" });
  m.serveur.routes.push(
    { motif: /^\/bailleurs\/$/, reponse: () => bailleurs },
    { motif: /^\/projets\/id-P1\/documents\/$/, reponse: () => [{ id: "doc-1", kind: "financing_agreement", title: "Accord de don", version: "v2", issued_on: "2026-05-01", sha256: "ab", remplace_par: null }] },
    { motif: /^\/projets\/id-P1\/accords\/$/, reponse: () => [A1] },
    { motif: /^\/projets\/id-P1\/accords\/a1\/$/, reponse: () => DETAIL },
  );
  extra(m.serveur);
  return m.serveur;
}
const ecritures = (s: FauxServeur) => s.appels.filter((a) => a.methode === "POST" && (a.url.endsWith("/accords/") || a.url.endsWith("/categories/") || a.url.endsWith("/avenants/") || a.url.endsWith("/bailleurs/")));

async function remplirAccord() {
  await userEvent.selectOptions(await screen.findByLabelText("Bailleur"), "BAD");
  await userEvent.type(screen.getByLabelText("Numéro de l'accord"), "DON-9");
  await userEvent.type(screen.getByLabelText("Devise (3 lettres)"), "usd");
  await userEvent.type(screen.getByLabelText("Montant initial"), "1 250 000,50");
}

describe("accords : création", () => {
  it("crée un accord : corps exact, montant en chaîne canonique, devise en majuscules", async () => {
    const s = await ouvrir("/accords?projet=id-P1", undefined, (sv) => sv.routes.push({ motif: /accords\/$/, methode: "POST", reponse: () => ({ ...A1, id: "a1", numero: "DON-9" }) } as never));
    await userEvent.click(await screen.findByRole("button", { name: "Nouvel accord" }));
    await remplirAccord();
    await userEvent.click(screen.getByRole("button", { name: "Créer l'accord" }));
    await waitFor(() => expect(ecritures(s)).toHaveLength(1));
    expect(ecritures(s)[0]?.corps).toEqual({ bailleur: "BAD", numero: "DON-9", nature: "don", devise: "USD", montant_initial: "1250000.50" });
    expect(await screen.findByText("Accord DON-9 créé en brouillon.")).toBeInTheDocument();
  });

  it("un double clic n'envoie qu'une seule création", async () => {
    const s = await ouvrir("/accords?projet=id-P1", undefined, (sv) => sv.routes.push({ motif: /accords\/$/, methode: "POST", reponse: async () => { await new Promise((r) => setTimeout(r, 50)); return A1; } } as never));
    await userEvent.click(await screen.findByRole("button", { name: "Nouvel accord" }));
    await remplirAccord();
    await userEvent.dblClick(screen.getByRole("button", { name: "Créer l'accord" }));
    await waitFor(() => expect(ecritures(s).length).toBeGreaterThan(0));
    expect(ecritures(s)).toHaveLength(1);
  });

  it("refuse un formulaire incomplet sans rien envoyer et dit quoi corriger", async () => {
    const s = await ouvrir("/accords?projet=id-P1");
    await userEvent.click(await screen.findByRole("button", { name: "Nouvel accord" }));
    await userEvent.click(await screen.findByRole("button", { name: "Créer l'accord" }));
    expect(await screen.findByText("Choisissez un bailleur.")).toBeInTheDocument();
    expect(screen.getByText("Le numéro de l'accord est obligatoire.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("affiche tel quel le refus du serveur, par exemple un numéro déjà pris", async () => {
    const s = await ouvrir("/accords?projet=id-P1", undefined, (sv) => sv.routes.push({ motif: /accords\/$/, methode: "POST", reponse: () => reponseFausse(422, { code: "ACCORD_EXISTANT", message: "Ce numéro d'accord existe déjà" }) } as never));
    await userEvent.click(await screen.findByRole("button", { name: "Nouvel accord" }));
    await remplirAccord();
    await userEvent.click(screen.getByRole("button", { name: "Créer l'accord" }));
    expect(await screen.findByText("Ce numéro d'accord existe déjà")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(1);
  });

  it("sans le droit de paramétrage, aucun bouton de création", async () => {
    await ouvrir("/accords?projet=id-P1&accord=a1", ["consulter"]);
    await screen.findByRole("table", { name: "Accords du projet" });
    expect(screen.queryByRole("button", { name: "Nouvel accord" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ajouter une catégorie" })).not.toBeInTheDocument();
  });

  it("le formulaire est accessible", async () => {
    await ouvrir("/accords?projet=id-P1");
    await userEvent.click(await screen.findByRole("button", { name: "Nouvel accord" }));
    await screen.findByRole("button", { name: "Créer l'accord" });
    expect(await violations(document.body)).toEqual([]);
  });
});

describe("accords : ajout d'une catégorie", () => {
  it("crée une sous-catégorie rattachée à une racine, plafond en chaîne", async () => {
    const s = await ouvrir("/accords?projet=id-P1&accord=a1", undefined, (sv) => sv.routes.push({ motif: /categories\/$/, methode: "POST", reponse: () => ({ id: "c2", code: "BIENS-A", label: { fr: "Biens A" }, parent: "BIENS", plafond: "400000.5", devise: "USD" }) } as never));
    await userEvent.click(await screen.findByRole("button", { name: "Ajouter une catégorie" }));
    await userEvent.type(screen.getByLabelText("Code de la catégorie"), "BIENS-A");
    await userEvent.type(screen.getByLabelText("Libellé en français"), "Biens A");
    await userEvent.selectOptions(screen.getByLabelText("Catégorie parente"), "BIENS");
    await userEvent.type(screen.getByLabelText("Plafond (facultatif)"), "400000,5");
    await userEvent.click(screen.getByRole("button", { name: "Créer la catégorie" }));
    await waitFor(() => expect(ecritures(s)).toHaveLength(1));
    expect(ecritures(s)[0]?.corps).toEqual({ code: "BIENS-A", label: { fr: "Biens A" }, parent: "BIENS", plafond: "400000.5" });
  });

  it("un code manquant est refusé localement", async () => {
    const s = await ouvrir("/accords?projet=id-P1&accord=a1");
    await userEvent.click(await screen.findByRole("button", { name: "Ajouter une catégorie" }));
    await userEvent.click(screen.getByRole("button", { name: "Créer la catégorie" }));
    expect(await screen.findByText("Le code de la catégorie est obligatoire.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });
});

describe("accords : avenant", () => {
  async function remplirAvenant() {
    await userEvent.type(await screen.findByLabelText("Référence de l'avenant"), "AV-2");
    await userEvent.type(screen.getByLabelText("Date de l'avenant"), "2026-06-01");
    await screen.findByRole("option", { name: "Accord de don · v2" });
    await userEvent.selectOptions(screen.getByLabelText("Document de référence"), "doc-1");
    await userEvent.type(screen.getByLabelText("Montant révisé de l'accord"), "1 500 000,75");
  }

  it("enregistre un avenant : corps exact, et la situation avant/après est celle du serveur", async () => {
    const s = await ouvrir("/accords?projet=id-P1&accord=a1", undefined, (sv) => sv.routes.push({ motif: /avenants\/$/, methode: "POST", reponse: () => ({ reference: "AV-2", date: "2026-06-01", montant_avant: "1000000.0000", montant_apres: "1500000.7500", variation: "500000.7500" }) } as never));
    await userEvent.click(await screen.findByRole("button", { name: "Enregistrer un avenant" }));
    await remplirAvenant();
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer l'avenant" }));
    await waitFor(() => expect(ecritures(s)).toHaveLength(1));
    expect(ecritures(s)[0]?.corps).toEqual({ reference: "AV-2", date_avenant: "2026-06-01", document_id: "doc-1", montant_revise: "1500000.75" });
    expect(await screen.findByText("Avenant AV-2 enregistré : le montant passe de 1000000.0000 à 1500000.7500 (variation 500000.7500).")).toBeInTheDocument();
  });

  it("refuse sans rien envoyer un avenant sans document ni montant", async () => {
    const s = await ouvrir("/accords?projet=id-P1&accord=a1");
    await userEvent.click(await screen.findByRole("button", { name: "Enregistrer un avenant" }));
    await userEvent.click(await screen.findByRole("button", { name: "Enregistrer l'avenant" }));
    expect(await screen.findByText("Choisissez le document qui appuie l'avenant.")).toBeInTheDocument();
    expect(screen.getByText("Le montant révisé est obligatoire : un nombre positif ou nul.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("affiche tel quel le refus du serveur", async () => {
    await ouvrir("/accords?projet=id-P1&accord=a1", undefined, (sv) => sv.routes.push({ motif: /avenants\/$/, methode: "POST", reponse: () => reponseFausse(422, { code: "REGLE_INVALIDE", message: "Cet accord n'est pas actif" }) } as never));
    await userEvent.click(await screen.findByRole("button", { name: "Enregistrer un avenant" }));
    await remplirAvenant();
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer l'avenant" }));
    expect(await screen.findByText("Cet accord n'est pas actif")).toBeInTheDocument();
  });

  it("un double clic n'envoie qu'un avenant", async () => {
    const s = await ouvrir("/accords?projet=id-P1&accord=a1", undefined, (sv) => sv.routes.push({ motif: /avenants\/$/, methode: "POST", reponse: async () => { await new Promise((r) => setTimeout(r, 50)); return { reference: "AV-2", date: "2026-06-01", montant_avant: "1.0000", montant_apres: "2.0000", variation: "1.0000" }; } } as never));
    await userEvent.click(await screen.findByRole("button", { name: "Enregistrer un avenant" }));
    await remplirAvenant();
    await userEvent.dblClick(screen.getByRole("button", { name: "Enregistrer l'avenant" }));
    await waitFor(() => expect(ecritures(s).length).toBeGreaterThan(0));
    expect(ecritures(s)).toHaveLength(1);
  });

  it("sans le droit de paramétrer, aucun bouton d'avenant", async () => {
    await ouvrir("/accords?projet=id-P1&accord=a1", ["consulter"]);
    await screen.findByRole("table", { name: "Accords du projet" });
    expect(screen.queryByRole("button", { name: "Enregistrer un avenant" })).not.toBeInTheDocument();
  });
});

describe("accords : nouveau bailleur", () => {
  it("crée un bailleur depuis le formulaire d'accord, le propose aussitôt et le sélectionne", async () => {
    const s = await ouvrir("/accords?projet=id-P1", undefined, (sv) => sv.routes.push({ motif: /^\/bailleurs\/$/, methode: "POST", reponse: () => { bailleurs.push({ id: "b2", code: "UE", nom: "Union européenne" }); return { id: "b2", code: "UE", nom: "Union européenne" }; } } as never));
    await userEvent.click(await screen.findByRole("button", { name: "Nouvel accord" }));
    await userEvent.click(await screen.findByRole("button", { name: "Nouveau bailleur" }));
    await userEvent.type(screen.getByLabelText("Code du bailleur"), "UE");
    await userEvent.type(screen.getByLabelText("Nom du bailleur"), "Union européenne");
    await userEvent.type(screen.getByLabelText("Pays (deux lettres, facultatif)"), "fr");
    await userEvent.click(screen.getByRole("button", { name: "Créer le bailleur" }));
    await waitFor(() => expect(ecritures(s).filter((a) => a.url.endsWith("/bailleurs/"))).toHaveLength(1));
    expect(ecritures(s).find((a) => a.url.endsWith("/bailleurs/"))?.corps).toEqual({ code: "UE", nom: "Union européenne", pays: "FR" });
    expect(await screen.findByRole("option", { name: "UE · Union européenne" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Bailleur")).toHaveValue("UE"));
    bailleurs.pop();
  });

  it("refuse un code vide ou un pays de trois lettres avant tout envoi", async () => {
    const s = await ouvrir("/accords?projet=id-P1");
    await userEvent.click(await screen.findByRole("button", { name: "Nouvel accord" }));
    await userEvent.click(await screen.findByRole("button", { name: "Nouveau bailleur" }));
    await userEvent.type(screen.getByLabelText("Pays (deux lettres, facultatif)"), "FR");
    await userEvent.click(screen.getByRole("button", { name: "Créer le bailleur" }));
    expect(await screen.findByText("Le code du bailleur est obligatoire.")).toBeInTheDocument();
    expect(screen.getByText("Le nom du bailleur est obligatoire.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });
});
