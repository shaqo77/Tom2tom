import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render } from "@testing-library/react";

import { creerRouteur } from "../app/routes";
import { brancherSessionPerdue } from "../app/sessionPerdue";
import { appliquerLangue } from "../i18n";
import { surNonAuthentifie } from "../shared/api/client";
import type { Compte, FauxServeur } from "./serveur";
import { demarrerServeur, unCompte } from "./serveur";

export interface Monte {
  serveur: FauxServeur;
  routeur: ReturnType<typeof creerRouteur>;
  queryClient: QueryClient;
  comptes: Compte[];
}

/** L'application complète (routes, gardes, session perdue) devant un faux serveur. */
export async function monter(
  chemin: string,
  options: { comptes?: Compte[]; connecteComme?: string } = {},
): Promise<Monte & { rendu: ReturnType<typeof render> }> {
  const comptes = options.comptes ?? [unCompte("amina")];
  const serveur = demarrerServeur(comptes);
  if (options.connecteComme) serveur.ouvrirSession(options.connecteComme);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const routeur = creerRouteur({
    queryClient,
    history: createMemoryHistory({ initialEntries: [chemin] }),
  });
  brancherSessionPerdue(queryClient, routeur);
  await appliquerLangue("fr");
  const rendu = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={routeur} />
    </QueryClientProvider>,
  );
  return { serveur, routeur, queryClient, comptes, rendu };
}

export function nettoyer() {
  surNonAuthentifie(null);
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
  window.localStorage.clear();
  window.sessionStorage.clear();
}
