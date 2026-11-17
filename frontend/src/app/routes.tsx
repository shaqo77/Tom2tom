import type { QueryClient } from "@tanstack/react-query";
import { createRootRouteWithContext, createRoute, createRouter, redirect } from "@tanstack/react-router";

import { Accueil } from "../features/accueil/Accueil";
import { Conception } from "../features/accueil/Conception";
import { Connexion } from "../features/connexion/Connexion";
import { ProjetPage } from "../features/projets/ProjetPage";
import { moiQuery } from "../shared/session/moi";
import { MiseEnPage } from "./MiseEnPage";

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

// Le guide de style n'existe qu'en développement.
const conception = createRoute({ getParentRoute: () => racine, path: "/conception", component: Conception });

export const arbre = racine.addChildren([
  connexion,
  protege.addChildren([accueil, projet]),
  ...(import.meta.env.DEV ? [conception] : []),
]);

export function creerRouteur(options: {
  queryClient: QueryClient;
  history?: Parameters<typeof createRouter>[0]["history"];
}) {
  return createRouter({
    routeTree: arbre,
    context: { queryClient: options.queryClient },
    ...(options.history ? { history: options.history } : {}),
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof creerRouteur>;
  }
}
