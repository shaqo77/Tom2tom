import { createRootRoute, createRoute, createRouter } from "@tanstack/react-router";

import { Accueil } from "../features/accueil/Accueil";
import { Conception } from "../features/accueil/Conception";
import { MiseEnPage } from "./MiseEnPage";

const racine = createRootRoute({ component: MiseEnPage });
const accueil = createRoute({ getParentRoute: () => racine, path: "/", component: Accueil });
const conception = createRoute({ getParentRoute: () => racine, path: "/conception", component: Conception });

export const arbre = racine.addChildren([accueil, conception]);

export function creerRouteur(options?: { history?: Parameters<typeof createRouter>[0]["history"] }) {
  return createRouter({ routeTree: arbre, ...(options?.history ? { history: options.history } : {}) });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof creerRouteur>;
  }
}
