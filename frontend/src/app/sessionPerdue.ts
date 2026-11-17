import type { QueryClient } from "@tanstack/react-query";

import { surNonAuthentifie } from "../shared/api/client";
import type { creerRouteur } from "./routes";

/**
 * Session perdue en cours d'usage (le serveur répond « connexion requise ») : on oublie « moi » et on
 * revient à la connexion avec un avis, puis, une fois reconnecté, à la page où l'on était.
 */
export function brancherSessionPerdue(queryClient: QueryClient, routeur: ReturnType<typeof creerRouteur>) {
  surNonAuthentifie(() => {
    queryClient.setQueryData(["moi"], null);
    if (routeur.state.location.pathname.startsWith("/connexion")) return;
    void routeur.navigate({
      to: "/connexion",
      search: { retour: routeur.state.location.href, expiree: true },
    });
  });
}
