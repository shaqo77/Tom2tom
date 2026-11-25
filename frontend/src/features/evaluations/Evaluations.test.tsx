import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { violations } from "../../test/accessibilite";
import { monter, nettoyer } from "../../test/monter";
import { projet, reponseFausse, unCompte } from "../../test/serveur";
import type { FauxServeur } from "../../test/serveur";
import type { Derogation, EvaluationDetail } from "./types";

afterEach(nettoyer);

const evaluation = (id: string, controle: string, resultat: EvaluationDetail["resultat"], extra: Partial<EvaluationDetail> = {}): EvaluationDetail => ({
  id,
  controle,
  controle_version: 1,
  objet_type: "ligne_ecriture",
  objet_id: "o1",
  resultat,
  severity: "bloquant",
  message: `Message de ${controle}`,
  action_corrective: { fr: "Joindre la pièce", en: "Attach the document" },
  valeur_constatee: "1250.00",
  valeur_attendue: "1000.00",
  exigence: null,
  evaluee_le: "2026-03-02T10:00:00Z",
  decisions: [],
  justifications: [],
  derogations: [],
  ...extra,
});
const derogation = (id: string, statut: Derogation["statut"], extra: Partial<Derogation> = {}): Derogation => ({
  id,
  evaluation: "e1",
  controle: "BUD-LIGNE",
  objet_type: "ligne_ecriture",
  objet_id: "o1",
  motif: "Urgence",
  justificatif: "REF-12",
  valide_du: "2026-03-01",
  valide_jusquau: "2026-04-01",
  statut,
  motif_decision: "",
  ...extra,
});

async function ouvrir(
  evaluations: EvaluationDetail[],
  { operations = ["consulter", "saisir", "valider"], chemin = "/evaluations?projet=id-P1", derogations = [] as Derogation[], retard }: { operations?: Parameters<typeof projet>[1]; chemin?: string; derogations?: Derogation[]; retard?: Promise<void> } = {},
) {
  const etat = { evaluations, derogations };
  const m = await monter(chemin, { comptes: [unCompte("amina", { projets: [projet("P1", operations)] })], connecteComme: "amina" });
  const s: FauxServeur = m.serveur;
  s.routes.push(
    {
      motif: /^\/projets\/id-P1\/evaluations-controles\/$/,
      reponse: async (_t, r) => {
        if (retard) await retard;
        return etat.evaluations
          .filter((e) => (!r.get("resultat") || e.resultat === r.get("resultat")) && (!r.get("controle") || e.controle === r.get("controle")) && (!r.get("objet_type") || e.objet_type === r.get("objet_type")))
          .map((e) => ({ ...e, decisions: undefined, justifications: undefined, derogations: undefined }));
      },
    },
    { motif: /^\/projets\/id-P1\/evaluations-controles\/(e\d)\/$/, reponse: (t) => etat.evaluations.find((e) => e.id === t[1]) ?? reponseFausse(404, { code: "INTROUVABLE", message: "Introuvable" }) },
    { motif: /^\/projets\/id-P1\/derogations\/$/, reponse: (_t, r) => etat.derogations.filter((d) => !r.get("statut") || d.statut === r.get("statut")) },
  );
  return { m, s, etat };
}
const ecritures = (s: FauxServeur) => s.appels.filter((a) => a.methode === "POST");

describe("évaluations : consulter", () => {
  it("affiche un état de chargement", async () => {
    let liberer: () => void = () => {};
    await ouvrir([evaluation("e1", "BUD-LIGNE", "bloquant")], { retard: new Promise<void>((r) => (liberer = r)) });
    expect(await screen.findByRole("status", { name: "Chargement en cours" })).toBeInTheDocument();
    liberer();
    expect(await screen.findByRole("table", { name: "Journal des évaluations" })).toBeInTheDocument();
  });

  it("un journal vide le dit clairement", async () => {
    await ouvrir([]);
    expect(await screen.findByText("Aucune évaluation ne correspond à ce filtre.")).toBeInTheDocument();
  });

  it("liste les évaluations avec leur résultat en toutes lettres", async () => {
    await ouvrir([evaluation("e1", "BUD-LIGNE", "bloquant"), evaluation("e2", "PIE-DOUBLON", "a_verifier"), evaluation("e3", "COD-CATEGORIE", "reussi")]);
    const table = await screen.findByRole("table", { name: "Journal des évaluations" });
    const lignes = within(table).getAllByRole("row").slice(1);
    expect(within(lignes[0]!).getByText("Bloquant")).toBeInTheDocument();
    expect(within(lignes[1]!).getByText("À vérifier")).toBeInTheDocument();
    expect(within(lignes[2]!).getByText("Réussi")).toBeInTheDocument();
  });

  it("filtrer par résultat et par contrôle redemande le journal avec ces filtres", async () => {
    const { s } = await ouvrir([evaluation("e1", "BUD-LIGNE", "bloquant"), evaluation("e2", "PIE-DOUBLON", "a_verifier")]);
    await screen.findByRole("table", { name: "Journal des évaluations" });
    await userEvent.selectOptions(screen.getByLabelText("Filtrer par résultat"), "a_verifier");
    expect(await screen.findByText("PIE-DOUBLON")).toBeInTheDocument();
    expect(screen.queryByText("BUD-LIGNE")).not.toBeInTheDocument();
    expect(s.appels.some((a) => a.url.includes("resultat=a_verifier"))).toBe(true);
  });

  it("le détail montre le message, les valeurs constatée et attendue telles quelles, et l'action corrective", async () => {
    await ouvrir([evaluation("e1", "BUD-LIGNE", "bloquant")], { chemin: "/evaluations?projet=id-P1&evaluation=e1" });
    expect(await screen.findByRole("heading", { name: "Évaluation de BUD-LIGNE · version 1" })).toBeInTheDocument();
    expect(screen.getAllByText("Message de BUD-LIGNE")).toHaveLength(2); // dans le journal et dans le détail
    expect(screen.getByText("Constaté : 1250.00")).toBeInTheDocument();
    expect(screen.getByText("Attendu : 1000.00")).toBeInTheDocument();
    expect(screen.getByText("Joindre la pièce")).toBeInTheDocument();
  });

  it("un refus de lecture du serveur s'affiche tel quel", async () => {
    const { s } = await ouvrir([]);
    s.routes.unshift({ motif: /^\/projets\/id-P1\/evaluations-controles\/$/, reponse: () => reponseFausse(403, { code: "ACCES_REFUSE", message: "Vous n'êtes pas habilité à consulter le journal" }) });
    expect(await screen.findByText("Vous n'êtes pas habilité à consulter le journal")).toBeInTheDocument();
  });

  it("est accessible", async () => {
    const { m } = await ouvrir([evaluation("e1", "BUD-LIGNE", "bloquant")], { chemin: "/evaluations?projet=id-P1&evaluation=e1" });
    await screen.findByRole("heading", { name: "Évaluation de BUD-LIGNE · version 1" });
    expect(await violations(m.rendu.container)).toEqual([]);
  });
});

describe("évaluations : trancher et justifier", () => {
  const chemin = "/evaluations?projet=id-P1&evaluation=e1";
  const url = (fin: string) => new RegExp(`^\\/projets\\/id-P1\\/evaluations-controles\\/e1\\/${fin}\\/$`);

  it("trancher un contrôle à vérifier envoie la décision et son motif", async () => {
    const { s, etat } = await ouvrir([evaluation("e1", "PIE-DOUBLON", "a_verifier")], { chemin });
    s.routes.push({ methode: "POST", motif: url("decision"), reponse: (_t, _r, c) => { const corps = c as { decision: "conforme" | "non_conforme"; motif: string }; etat.evaluations = [evaluation("e1", "PIE-DOUBLON", "a_verifier", { decisions: [{ ...corps, decided_at: "2026-03-03T09:00:00Z" }] })]; return reponseFausse(201, etat.evaluations[0]); } });
    await screen.findByRole("heading", { name: "Évaluation de PIE-DOUBLON · version 1" });
    await userEvent.selectOptions(screen.getByLabelText("Décision"), "non_conforme");
    await userEvent.type(screen.getByLabelText("Motif de la décision"), "Facture déjà payée");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer la décision" }));
    expect(await screen.findByText("Décision enregistrée.")).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({ decision: "non_conforme", motif: "Facture déjà payée" });
    expect(await screen.findByText("Non conforme : Facture déjà payée")).toBeInTheDocument();
  });

  it("n'offre pas de décision pour un résultat qui n'est pas « à vérifier »", async () => {
    await ouvrir([evaluation("e1", "BUD-LIGNE", "bloquant")], { chemin });
    await screen.findByRole("heading", { name: "Évaluation de BUD-LIGNE · version 1" });
    expect(screen.queryByRole("button", { name: "Enregistrer la décision" })).not.toBeInTheDocument();
  });

  it("sans le droit de valider, aucune décision n'est proposée", async () => {
    await ouvrir([evaluation("e1", "PIE-DOUBLON", "a_verifier")], { operations: ["consulter", "saisir"], chemin });
    await screen.findByRole("heading", { name: "Évaluation de PIE-DOUBLON · version 1" });
    expect(screen.queryByRole("button", { name: "Enregistrer la décision" })).not.toBeInTheDocument();
    expect(screen.getByText(/droit de valider/)).toBeInTheDocument();
  });

  it("justifier exige un texte avant tout envoi puis l'envoie", async () => {
    const { s, etat } = await ouvrir([evaluation("e1", "BUD-LIGNE", "bloquant")], { chemin });
    s.routes.push({ methode: "POST", motif: url("justification"), reponse: () => { etat.evaluations = [evaluation("e1", "BUD-LIGNE", "bloquant", { justifications: [{ texte: "Marché en cours d'avenant", auteur: "amina", created_at: "2026-03-03T09:00:00Z" }] })]; return reponseFausse(201, etat.evaluations[0]); } });
    await screen.findByRole("heading", { name: "Évaluation de BUD-LIGNE · version 1" });
    await userEvent.click(screen.getByRole("button", { name: "Ajouter la justification" }));
    expect(screen.getByText("Saisissez le texte de la justification.")).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
    await userEvent.type(screen.getByLabelText("Justification"), "Marché en cours d'avenant");
    await userEvent.click(screen.getByRole("button", { name: "Ajouter la justification" }));
    expect(await screen.findByText("Justification ajoutée.")).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({ texte: "Marché en cours d'avenant" });
    expect(await screen.findByText("Marché en cours d'avenant")).toBeInTheDocument();
  });

  it("affiche le refus du serveur et un double clic n'envoie qu'une justification", async () => {
    let liberer: () => void = () => {};
    const attente = new Promise<void>((r) => (liberer = r));
    const { s } = await ouvrir([evaluation("e1", "BUD-LIGNE", "bloquant")], { chemin });
    s.routes.push({ methode: "POST", motif: url("justification"), reponse: async () => { await attente; return reponseFausse(422, { code: "REGLE_INVALIDE", message: "Une évaluation dépassée ne se justifie plus" }); } });
    await screen.findByRole("heading", { name: "Évaluation de BUD-LIGNE · version 1" });
    await userEvent.type(screen.getByLabelText("Justification"), "x");
    await userEvent.dblClick(screen.getByRole("button", { name: "Ajouter la justification" }));
    liberer();
    expect(await screen.findByRole("alert")).toHaveTextContent("Une évaluation dépassée ne se justifie plus");
    expect(ecritures(s)).toHaveLength(1);
  });
});

describe("évaluations : dérogations", () => {
  const chemin = "/evaluations?projet=id-P1&evaluation=e1";
  const url = new RegExp("^\\/projets\\/id-P1\\/evaluations-controles\\/e1\\/derogation\\/$");

  async function remplir(motif = "Urgence", justificatif = "REF-12", du = "2026-03-01", jusquau = "2026-04-01") {
    if (motif) await userEvent.type(screen.getByLabelText("Motif de la dérogation"), motif);
    if (justificatif) await userEvent.type(screen.getByLabelText("Référence du justificatif"), justificatif);
    if (du) await userEvent.type(screen.getByLabelText("Valable du"), du);
    if (jusquau) await userEvent.type(screen.getByLabelText("Jusqu'au (exclu)"), jusquau);
  }

  it("demande une dérogation pour un résultat bloquant, fin exclue", async () => {
    const { s } = await ouvrir([evaluation("e1", "BUD-LIGNE", "bloquant")], { chemin });
    s.routes.push({ methode: "POST", motif: url, reponse: () => reponseFausse(201, derogation("d1", "demandee")) });
    await screen.findByRole("heading", { name: "Évaluation de BUD-LIGNE · version 1" });
    await remplir();
    await userEvent.click(screen.getByRole("button", { name: "Demander la dérogation" }));
    expect(await screen.findByText("Dérogation demandée.")).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({ motif: "Urgence", justificatif: "REF-12", valide_du: "2026-03-01", valide_jusquau: "2026-04-01" });
  });

  it("n'offre la demande que pour un résultat bloquant", async () => {
    await ouvrir([evaluation("e1", "PIE-DOUBLON", "a_verifier")], { chemin });
    await screen.findByRole("heading", { name: "Évaluation de PIE-DOUBLON · version 1" });
    expect(screen.queryByRole("button", { name: "Demander la dérogation" })).not.toBeInTheDocument();
  });

  it.each([
    [{ motif: "" }, "Saisissez le motif de la dérogation."],
    [{ justificatif: "" }, "Saisissez la référence du justificatif."],
    [{ du: "" }, "Choisissez les deux dates de validité."],
    [{ jusquau: "" }, "Choisissez les deux dates de validité."],
    [{ du: "2026-04-01", jusquau: "2026-04-01" }, "La période doit commencer avant sa fin (la fin est exclue)."],
    [{ du: "2026-05-01", jusquau: "2026-04-01" }, "La période doit commencer avant sa fin (la fin est exclue)."],
  ] as [{ motif?: string; justificatif?: string; du?: string; jusquau?: string }, string][])("refuse la demande incomplète ou incohérente %j avant tout envoi", async (champs, message) => {
    const { s } = await ouvrir([evaluation("e1", "BUD-LIGNE", "bloquant")], { chemin });
    await screen.findByRole("heading", { name: "Évaluation de BUD-LIGNE · version 1" });
    await remplir(champs.motif ?? "Urgence", champs.justificatif ?? "REF-12", champs.du ?? "2026-03-01", champs.jusquau ?? "2026-04-01");
    await userEvent.click(screen.getByRole("button", { name: "Demander la dérogation" }));
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(ecritures(s)).toHaveLength(0);
  });

  it("la liste des dérogations s'affiche avec leur statut et leur période", async () => {
    await ouvrir([], { derogations: [derogation("d1", "demandee"), derogation("d2", "approuvee", { valide_jusquau: "2026-06-01" })] });
    const table = await screen.findByRole("table", { name: "Dérogations du projet" });
    const lignes = within(table).getAllByRole("row").slice(1);
    expect(within(lignes[0]!).getByText("Demandée")).toBeInTheDocument();
    expect(within(lignes[1]!).getByText("Approuvée")).toBeInTheDocument();
    expect(within(lignes[1]!).getByText("2026-03-01 → 2026-06-01 (exclu)")).toBeInTheDocument();
  });

  it("approuver ou refuser une dérogation demandée envoie la décision et son motif", async () => {
    const { s } = await ouvrir([], { derogations: [derogation("d1", "demandee")] });
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/derogations\/d1\/decision\/$/, reponse: (_t, _r, c) => derogation("d1", (c as { approuver: boolean }).approuver ? "approuvee" : "refusee") });
    await userEvent.click(await screen.findByRole("button", { name: "Approuver la dérogation de BUD-LIGNE" }));
    await userEvent.type(screen.getByLabelText("Motif de la décision"), "Justifiée");
    await userEvent.click(screen.getByRole("button", { name: "Confirmer l'approbation" }));
    expect(await screen.findByText("Dérogation approuvée.")).toBeInTheDocument();
    expect(ecritures(s)[0]?.corps).toEqual({ approuver: true, motif: "Justifiée" });
  });

  it("le refus du serveur (demandeur = approbateur) s'affiche tel quel", async () => {
    const { s } = await ouvrir([], { derogations: [derogation("d1", "demandee")] });
    s.routes.push({ methode: "POST", motif: /^\/projets\/id-P1\/derogations\/d1\/decision\/$/, reponse: () => reponseFausse(403, { code: "ACCES_REFUSE", message: "Le demandeur ne peut pas approuver sa propre dérogation" }) });
    await userEvent.click(await screen.findByRole("button", { name: "Refuser la dérogation de BUD-LIGNE" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirmer le refus" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Le demandeur ne peut pas approuver sa propre dérogation");
  });

  it("sans le droit de valider, aucune décision de dérogation n'est proposée", async () => {
    await ouvrir([], { operations: ["consulter", "saisir"], derogations: [derogation("d1", "demandee")] });
    await screen.findByRole("table", { name: "Dérogations du projet" });
    expect(screen.queryByRole("button", { name: /^Approuver/ })).not.toBeInTheDocument();
  });

  it("une dérogation déjà décidée n'est plus décidable", async () => {
    await ouvrir([], { derogations: [derogation("d2", "approuvee")] });
    await screen.findByRole("table", { name: "Dérogations du projet" });
    expect(screen.queryByRole("button", { name: /^Approuver/ })).not.toBeInTheDocument();
  });
});

describe("évaluations : dossier de conformité d'un objet", () => {
  const OBJET = "3f2b8c1e-5a47-4d9e-9b1a-0c6d2e7f8a90";
  const FIL = [
    { le: "2026-03-02T10:00:00Z", genre: "evaluation", controle: "BUD-LIGNE", detail: "bloquant" },
    { le: "2026-03-02T11:30:00Z", genre: "justification", controle: "BUD-LIGNE", detail: "Urgence sanitaire, accord oral du bailleur" },
    { le: "2026-03-03T09:00:00Z", genre: "derogation", controle: "BUD-LIGNE", detail: "approuvee" },
  ];
  const ATTENTE = [{ evaluation: "e1", controle: "PIE-ETAT-CERTIFIE", raison: "Résultat bloquant, aucune dérogation approuvée" }];

  async function ouvrirDossier(extra: (s: FauxServeur) => void = () => {}, operations?: Parameters<typeof projet>[1]) {
    const r = await ouvrir([], operations ? { operations } : {});
    r.s.routes.push(
      { motif: /^\/projets\/id-P1\/controles-en-attente\/$/, reponse: () => ATTENTE },
      { motif: /^\/projets\/id-P1\/dossier-conformite-objet\/$/, reponse: () => FIL },
    );
    extra(r.s);
    return r;
  }
  const lectures = (s: FauxServeur, fin: string) => s.appels.filter((a) => a.methode === "GET" && a.url.includes(fin));

  it("affiche ce qui bloque, puis le fil dans l'ordre, avec les résultats et statuts en toutes lettres", async () => {
    const { s } = await ouvrirDossier();
    await userEvent.type(await screen.findByLabelText("Type d'objet (par exemple ecriture)"), "ecriture");
    await userEvent.type(screen.getByLabelText("Identifiant de l'objet (facultatif)"), OBJET);
    await userEvent.click(screen.getByRole("button", { name: "Consulter le dossier" }));
    expect(await screen.findByText(/Résultat bloquant, aucune dérogation approuvée/)).toBeInTheDocument();
    const fil = await screen.findByRole("table", { name: "Fil de conformité" });
    const lignes = within(fil).getAllByRole("row").slice(1);
    const texte = (l: HTMLElement) => [...within(l).getAllByRole("cell"), within(l).getByRole("rowheader")].map((c) => c.textContent);
    expect(lignes.map(texte)).toEqual([
      ["2026-03-02 10:00", "Évaluation", "Bloquant", "BUD-LIGNE"],
      ["2026-03-02 11:30", "Justification", "Urgence sanitaire, accord oral du bailleur", "BUD-LIGNE"],
      ["2026-03-03 09:00", "Dérogation", "Approuvée", "BUD-LIGNE"],
    ]);
    expect(lectures(s, "dossier-conformite-objet")[0]?.url).toContain(`objet_type=ecriture&objet_id=${OBJET}`);
  });

  it("refuse sans appel un type vide ou un identifiant qui n'est pas un UUID", async () => {
    const { s } = await ouvrirDossier();
    await userEvent.click(await screen.findByRole("button", { name: "Consulter le dossier" }));
    expect(await screen.findByText("Indiquez le type d'objet.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Type d'objet (par exemple ecriture)"), "ecriture");
    await userEvent.type(screen.getByLabelText("Identifiant de l'objet (facultatif)"), "abc");
    await userEvent.click(screen.getByRole("button", { name: "Consulter le dossier" }));
    expect(await screen.findByText(/L'identifiant doit être un UUID/)).toBeInTheDocument();
    expect(lectures(s, "dossier-conformite-objet")).toHaveLength(0);
    expect(lectures(s, "controles-en-attente")).toHaveLength(0);
  });

  it("dit clairement quand rien ne bloque et que le fil est vide", async () => {
    await ouvrirDossier((sv) => sv.routes.unshift(
      { motif: /^\/projets\/id-P1\/controles-en-attente\/$/, reponse: () => [] },
      { motif: /^\/projets\/id-P1\/dossier-conformite-objet\/$/, reponse: () => [] },
    ));
    await userEvent.type(await screen.findByLabelText("Type d'objet (par exemple ecriture)"), "ecriture");
    await userEvent.click(screen.getByRole("button", { name: "Consulter le dossier" }));
    expect(await screen.findByText("Rien n'empêche d'avancer.")).toBeInTheDocument();
    expect(await screen.findByText("Aucun échec, justification ni dérogation pour cet objet.")).toBeInTheDocument();
  });

  it("affiche tel quel un refus du serveur", async () => {
    await ouvrirDossier((sv) => sv.routes.unshift({ motif: /^\/projets\/id-P1\/dossier-conformite-objet\/$/, reponse: () => reponseFausse(403, { code: "ACCES_REFUSE", message: "Vous n'êtes pas habilité à consulter ce projet" }) }));
    await userEvent.type(await screen.findByLabelText("Type d'objet (par exemple ecriture)"), "ecriture");
    await userEvent.click(screen.getByRole("button", { name: "Consulter le dossier" }));
    await waitFor(() => expect(screen.getByText("Vous n'êtes pas habilité à consulter ce projet")).toBeInTheDocument());
  });

  it("la consultation du dossier est accessible", async () => {
    await ouvrirDossier();
    await userEvent.type(await screen.findByLabelText("Type d'objet (par exemple ecriture)"), "ecriture");
    await userEvent.click(screen.getByRole("button", { name: "Consulter le dossier" }));
    await screen.findByRole("table", { name: "Fil de conformité" });
    expect(await violations(document.body)).toEqual([]);
  });
});
