import { queryOptions, useQuery } from "@tanstack/react-query";

import { lireMoi } from "./api";

/** La requête de « moi » : partagée par les gardes de route, l'en-tête et les pages. */
export const moiQuery = queryOptions({
  queryKey: ["moi"],
  queryFn: lireMoi,
  staleTime: 5 * 60_000,
  retry: false,
});

export function useMoi() {
  return useQuery(moiQuery);
}
