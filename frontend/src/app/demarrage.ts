import type { QueryClient } from "@tanstack/react-query";

import { moiQuery } from "../shared/session/moi";

/**
 * La langue avec laquelle démarrer : celle demandée dans l'adresse (développement), sinon celle
 * enregistrée sur le compte de la personne déjà connectée, sinon celle du navigateur. Un serveur
 * injoignable ne bloque jamais le démarrage.
 */
export async function langueDeDepart(
  queryClient: QueryClient,
  options: { navigateur: string; demandee?: string | null },
): Promise<string> {
  if (options.demandee) return options.demandee;
  const moi = await queryClient.fetchQuery(moiQuery).catch(() => null);
  return moi?.langue ?? options.navigateur;
}
