import type { QueryClient } from "@tanstack/react-query";
import { createRootRouteWithContext, createRoute, createRouter, redirect } from "@tanstack/react-router";

import { Accueil } from "../features/accueil/Accueil";
import { Conception } from "../features/accueil/Conception";
import { ChangerMotDePasse } from "../features/connexion/ChangerMotDePasse";
import { Cles } from "../features/cles/Cles";
import { Accords } from "../features/accords/Accords";
import { CompteSpecial } from "../features/compte-special/CompteSpecial";
import { Connexion } from "../features/connexion/Connexion";
import { Evaluations } from "../features/evaluations/Evaluations";
import { Controles } from "../features/controles/Controles";
import { Documents } from "../features/documents/Documents";
import { TauxDeChange } from "../features/taux/TauxDeChange";
import { ProfilsDecaissement } from "../features/profils/ProfilsDecaissement";
import { ReglagesDevises } from "../features/devises/ReglagesDevises";
import { ProjetPage } from "../features/projets/ProjetPage";
import { Descente } from "../features/tableau/Descente";
import { TableauDeBord } from "../features/tableau/TableauDeBord";
import { aujourdhui, dateIsoValide } from "../features/tableau/api";
import type { CodeIndicateur, RechercheTableau } from "../features/tableau/types";
import { moiQuery } from "../shared/session/moi";
import { MiseEnPage } from "./MiseEnPage";
import { PageErreur, PageIntrouvable } from "./PagesSpeciales";

export interface ContexteRouteur {
  queryClient: QueryClient;
}

const racine = createRootRouteWithContext<ContexteRouteur>()({ component: MiseEnPage });

const connexion = createRoute({
  getParentRoute: () => racine,
  path: "/connexion",
  validateSearch: (recherche: Record<string, unknown>): { retour?: string; expiree?: true } => ({
    ...(typeof recherche.retour === "string" ? { retour: recherche.retour } : {}),
    ...(recherche.expiree === true || recherche.expiree === "true" ? { expiree: true as const } : {}),
  }),
  // Déjà connecté : la page de connexion n'a rien à offrir.
  beforeLoad: async ({ context }) => {
    if (await context.queryClient.ensureQueryData(moiQuery)) throw redirect({ to: "/" });
  },
  component: Connexion,
});

/** Tout ce qui est derrière la connexion : sans session, retour à la connexion — puis ici. */
const protege = createRoute({
  getParentRoute: () => racine,
  id: "protege",
  beforeLoad: async ({ context, location }) => {
    if (!(await context.queryClient.ensureQueryData(moiQuery))) {
      throw redirect({ to: "/connexion", search: { retour: location.href } });
    }
  },
});
const accueil = createRoute({ getParentRoute: () => protege, path: "/", component: Accueil });
const projet = createRoute({
  getParentRoute: () => protege,
  path: "/projets/$projetId",
  component: ProjetPage,
});

const tableau = createRoute({
  getParentRoute: () => protege,
  path: "/tableau-de-bord",
  // Le routeur FUSIONNE la recherche brute de l'adresse avec ce que renvoie ce validateur : une valeur
  // invalide doit donc être écrasée explicitement (`undefined`), pas seulement omise.
  validateSearch: (recherche: Record<string, unknown>): RechercheTableau => ({
    jour: dateIsoValide(recherche.jour) ? recherche.jour : undefined,
    statut: recherche.statut === "tous" ? "tous" : undefined,
    devise: typeof recherche.devise === "string" && /^[A-Z]{3}$/.test(recherche.devise) ? recherche.devise : undefined,
    projets:
      Array.isArray(recherche.projets) && recherche.projets.length > 0 && recherche.projets.every((p) => typeof p === "string" && p !== "")
        ? (recherche.projets as string[])
        : undefined,
  }),
  component: TableauDeBord,
});

const INDICATEURS_DESCENDABLES: CodeIndicateur[] = [
  "budget_approuve",
  "budget_initial",
  "financements_accordes",
  "financements_recus",
  "execution_budget",
  "execution_engage",
  "execution_consomme",
  "soldes_comptables",
  "soldes_releves",
  "engagements_ouverts",
  "avances_non_justifiees",
];
const texteNonVide = (v: unknown): v is string => typeof v === "string" && v !== "";

/** La descente : l'adresse porte tout (projet, indicateur, jour, objet, écriture) pour être partageable. */
const descente = createRoute({
  getParentRoute: () => protege,
  path: "/tableau-de-bord/descente",
  validateSearch: (
    recherche: Record<string, unknown>,
  ): {
    projet: string;
    indicateur: CodeIndicateur;
    jour: string;
    devise?: string | undefined;
    detail?: string | undefined;
    ecriture?: string | undefined;
  } => ({
    projet: texteNonVide(recherche.projet) ? recherche.projet : "",
    indicateur: INDICATEURS_DESCENDABLES.includes(recherche.indicateur as CodeIndicateur)
      ? (recherche.indicateur as CodeIndicateur)
      : "budget_approuve",
    jour: dateIsoValide(recherche.jour) ? recherche.jour : aujourdhui(),
    devise: typeof recherche.devise === "string" && /^[A-Z]{3}$/.test(recherche.devise) ? recherche.devise : undefined,
    detail: texteNonVide(recherche.detail) ? recherche.detail : undefined,
    ecriture: texteNonVide(recherche.ecriture) ? recherche.ecriture : undefined,
  }),
  component: Descente,
});

const accords = createRoute({
  getParentRoute: () => protege,
  path: "/accords",
  // (valeur invalide écrasée par `undefined` : le routeur fusionne la recherche brute avec ce validateur)
  validateSearch: (recherche: Record<string, unknown>): { projet?: string | undefined; accord?: string | undefined } => ({
    projet: texteNonVide(recherche.projet) ? recherche.projet : undefined,
    accord: texteNonVide(recherche.accord) ? recherche.accord : undefined,
  }),
  component: Accords,
});

const tauxDeChange = createRoute({
  getParentRoute: () => protege,
  path: "/taux-de-change",
  component: TauxDeChange,
});

const profilsDecaissement = createRoute({
  getParentRoute: () => protege,
  path: "/profils-decaissement",
  // (valeur invalide écrasée par `undefined` : le routeur fusionne la recherche brute avec ce validateur)
  validateSearch: (
    recherche: Record<string, unknown>,
  ): { projet?: string | undefined; accord?: string | undefined; profil?: string | undefined; mode?: "creation" | "edition" | "version" | undefined } => ({
    projet: texteNonVide(recherche.projet) ? recherche.projet : undefined,
    accord: texteNonVide(recherche.accord) ? recherche.accord : undefined,
    profil: texteNonVide(recherche.profil) ? recherche.profil : undefined,
    mode: recherche.mode === "creation" || recherche.mode === "edition" || recherche.mode === "version" ? recherche.mode : undefined,
  }),
  component: ProfilsDecaissement,
});

const controles = createRoute({
  getParentRoute: () => protege,
  path: "/controles",
  // (valeur invalide écrasée par `undefined` : le routeur fusionne la recherche brute avec ce validateur)
  validateSearch: (recherche: Record<string, unknown>): { projet?: string | undefined; controle?: string | undefined } => ({
    projet: texteNonVide(recherche.projet) ? recherche.projet : undefined,
    controle: texteNonVide(recherche.controle) ? recherche.controle : undefined,
  }),
  component: Controles,
});

const compteSpecial = createRoute({
  getParentRoute: () => protege,
  path: "/compte-special",
  // (valeur invalide écrasée par `undefined` : le routeur fusionne la recherche brute avec ce validateur)
  validateSearch: (recherche: Record<string, unknown>): { projet?: string | undefined; compte?: string | undefined; date?: string | undefined } => ({
    projet: texteNonVide(recherche.projet) ? recherche.projet : undefined,
    compte: texteNonVide(recherche.compte) ? recherche.compte : undefined,
    date: dateIsoValide(recherche.date) ? recherche.date : undefined,
  }),
  component: CompteSpecial,
});

const documents = createRoute({
  getParentRoute: () => protege,
  path: "/documents",
  // (valeur invalide écrasée par `undefined` : le routeur fusionne la recherche brute avec ce validateur)
  validateSearch: (recherche: Record<string, unknown>): { projet?: string | undefined } => ({
    projet: texteNonVide(recherche.projet) ? recherche.projet : undefined,
  }),
  component: Documents,
});

const clesCofinancement = createRoute({
  getParentRoute: () => protege,
  path: "/cles-cofinancement",
  // (valeur invalide écrasée par `undefined` : le routeur fusionne la recherche brute avec ce validateur)
  validateSearch: (recherche: Record<string, unknown>): { projet?: string | undefined; cle?: string | undefined } => ({
    projet: texteNonVide(recherche.projet) ? recherche.projet : undefined,
    cle: texteNonVide(recherche.cle) ? recherche.cle : undefined,
  }),
  component: Cles,
});

const evaluations = createRoute({
  getParentRoute: () => protege,
  path: "/evaluations",
  // (valeur invalide écrasée par `undefined` : le routeur fusionne la recherche brute avec ce validateur)
  validateSearch: (recherche: Record<string, unknown>): { projet?: string | undefined; evaluation?: string | undefined } => ({
    projet: texteNonVide(recherche.projet) ? recherche.projet : undefined,
    evaluation: texteNonVide(recherche.evaluation) ? recherche.evaluation : undefined,
  }),
  component: Evaluations,
});

const motDePasse = createRoute({
  getParentRoute: () => protege,
  path: "/mot-de-passe",
  component: ChangerMotDePasse,
});

const reglagesDevises = createRoute({
  getParentRoute: () => protege,
  path: "/parametres-devises",
  // (valeur invalide écrasée par `undefined` : le routeur fusionne la recherche brute avec ce validateur)
  validateSearch: (recherche: Record<string, unknown>): { portee?: string | undefined } => ({
    portee: typeof recherche.portee === "string" && recherche.portee !== "" ? recherche.portee : undefined,
  }),
  component: ReglagesDevises,
});

// Le guide de style n'existe qu'en développement.
const conception = createRoute({ getParentRoute: () => racine, path: "/conception", component: Conception });

export const arbre = racine.addChildren([
  connexion,
  protege.addChildren([accueil, tableau, descente, reglagesDevises, tauxDeChange, profilsDecaissement, accords, clesCofinancement, documents, compteSpecial, controles, evaluations, motDePasse, projet]),
  ...(import.meta.env.DEV ? [conception] : []),
]);

export function creerRouteur(options: {
  queryClient: QueryClient;
  history?: Parameters<typeof createRouter>[0]["history"];
}) {
  return createRouter({
    routeTree: arbre,
    defaultErrorComponent: PageErreur,
    defaultNotFoundComponent: PageIntrouvable,
    context: { queryClient: options.queryClient },
    ...(options.history ? { history: options.history } : {}),
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof creerRouteur>;
  }
}
